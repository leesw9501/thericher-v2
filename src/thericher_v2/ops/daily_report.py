"""Generate one concise, evidence-aware daily operator summary."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DEFAULT_REPO_ROOT = Path(os.environ.get("THERICHER_REPO_ROOT", Path.cwd()))
DEFAULT_MARKET_DATA_ROOT = Path(
    os.environ.get("THERICHER_MARKET_DATA_ROOT", "D:/market_data")
)
DEFAULT_RUNTIME_STATUS = Path(
    os.environ.get("THERICHER_RUNTIME_STATUS", "runtime/operator_status.json")
)
KST = timezone(timedelta(hours=9), name="KST")
RUNTIME_STATUS_MAX_AGE = timedelta(minutes=15)
RUNTIME_STATUS_FUTURE_TOLERANCE = timedelta(minutes=5)


def read_operator_help_needed(path: Path) -> list[str]:
    if not path.exists():
        return [f"stateboard unavailable: {path}"]
    lines = path.read_text(encoding="utf-8").splitlines()
    in_section = False
    items: list[str] = []
    for line in lines:
        if line.startswith("## "):
            if in_section:
                break
            in_section = line.strip() == "## Operator Help Needed"
            continue
        if in_section and line.startswith("- "):
            item = line[2:].strip()
            if item and not item.lower().startswith("none now"):
                items.append(item)
    return items


def read_current_objective(path: Path) -> str:
    if not path.exists():
        return f"objective unavailable: {path}"
    lines = path.read_text(encoding="utf-8").splitlines()
    in_objective = False
    objective: list[str] = []
    for line in lines:
        if line.startswith("## "):
            if in_objective:
                break
            in_objective = line.strip() == "## Objective"
            continue
        if in_objective and line.strip():
            objective.append(line.strip())
    return " ".join(objective) or f"objective unavailable: {path}"


def _optional_count(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def load_runtime_status(
    path: Path,
    *,
    configured_mode: str | None,
    now: datetime,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "evidence_status": "missing",
        "evidence_path": str(path),
        "observed_at_utc": None,
        "configured_mode": configured_mode or "unknown",
        "mode": "unknown",
        "broker_calls": None,
        "kis_api_calls": None,
        "kis_paper_orders": None,
        "live_orders": None,
        "local_paper_fills": None,
        "after_cost_pnl": None,
        "outcomes": [],
        "role_work": {},
        "recovery_anomalies": [],
        "operator_decisions": [],
    }
    if not path.exists():
        return base
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {**base, "evidence_status": "invalid"}
    if not isinstance(payload, dict):
        return {**base, "evidence_status": "invalid"}

    observed_at = payload.get("observed_at_utc")
    if not isinstance(observed_at, str):
        return {**base, "evidence_status": "invalid"}
    try:
        observed = datetime.fromisoformat(observed_at)
    except ValueError:
        return {**base, "evidence_status": "invalid"}
    if observed.tzinfo is None or observed.utcoffset() is None:
        return {**base, "evidence_status": "invalid"}

    age = now.astimezone(UTC) - observed.astimezone(UTC)
    if age < -RUNTIME_STATUS_FUTURE_TOLERANCE:
        return {
            **base,
            "evidence_status": "invalid",
            "observed_at_utc": observed_at,
        }
    if age > RUNTIME_STATUS_MAX_AGE:
        return {
            **base,
            "evidence_status": "stale",
            "observed_at_utc": observed_at,
        }

    mode = payload.get("mode")
    role_work = payload.get("role_work")
    return {
        **base,
        "evidence_status": "available",
        "observed_at_utc": observed_at,
        "mode": mode if isinstance(mode, str) and mode else "unknown",
        "broker_calls": _optional_count(payload.get("broker_calls")),
        "kis_api_calls": _optional_count(payload.get("kis_api_calls")),
        "kis_paper_orders": _optional_count(payload.get("kis_paper_orders")),
        "live_orders": _optional_count(payload.get("live_orders")),
        "local_paper_fills": _optional_count(payload.get("local_paper_fills")),
        "after_cost_pnl": payload.get("after_cost_pnl"),
        "outcomes": _string_list(payload.get("outcomes")),
        "role_work": role_work if isinstance(role_work, dict) else {},
        "recovery_anomalies": _string_list(payload.get("recovery_anomalies")),
        "operator_decisions": _string_list(payload.get("operator_decisions")),
    }


def _free_percent(path: Path) -> float | None:
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return None
    return round((usage.free / usage.total) * 100, 2) if usage.total else None


@dataclass(frozen=True)
class DailyBundle:
    date: str
    summary_path: Path
    metrics: dict[str, Any]
    metrics_path: Path | None = None
    next_goal_path: Path | None = None


def build_metrics(
    now: datetime,
    *,
    repo_root: Path = DEFAULT_REPO_ROOT,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    runtime_status_path: Path = DEFAULT_RUNTIME_STATUS,
    configured_mode: str | None = None,
) -> dict[str, Any]:
    runtime = load_runtime_status(
        runtime_status_path,
        configured_mode=configured_mode or os.environ.get("THERICHER_MODE"),
        now=now,
    )
    return {
        "artifact_kind": "daily_operator_summary",
        "created_at_utc": now.astimezone(UTC).isoformat(),
        **runtime,
        "market_data_root": str(market_data_root),
        "market_data_root_exists": market_data_root.exists(),
        "market_data_free_percent": _free_percent(market_data_root),
        "data_operator_help_needed": read_operator_help_needed(
            repo_root / "agents" / "data.md"
        ),
        "current_objective": read_current_objective(repo_root / "NEXT_CODEX_GOAL.md"),
    }


def _display(value: object) -> str:
    return "unknown" if value is None else str(value)


def _bullet_items(items: list[str], *, empty: str) -> list[str]:
    return [f"- {item}" for item in items] if items else [f"- {empty}"]


def _role_items(role_work: object) -> list[str]:
    if not isinstance(role_work, dict) or not role_work:
        return ["- No authoritative role snapshot."]
    return [f"- {role}: {status}" for role, status in sorted(role_work.items())]


def write_bundle(
    output_dir: Path,
    *,
    now: datetime | None = None,
    repo_root: Path = DEFAULT_REPO_ROOT,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    runtime_status_path: Path = DEFAULT_RUNTIME_STATUS,
    configured_mode: str | None = None,
) -> DailyBundle:
    now = now or datetime.now(UTC)
    date = now.astimezone(KST).date().isoformat()
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics = build_metrics(
        now,
        repo_root=repo_root,
        market_data_root=market_data_root,
        runtime_status_path=runtime_status_path,
        configured_mode=configured_mode,
    )
    summary_path = output_dir / f"{date}-summary.md"
    summary_path.write_text(
        "\n".join(
            [
                f"# Daily Summary - {date}",
                "",
                "## Status",
                "",
                f"- Runtime evidence: `{metrics['evidence_status']}`",
                f"- Observed at: `{_display(metrics['observed_at_utc'])}`",
                f"- Configured mode: `{metrics['configured_mode']}`",
                f"- Observed mode: `{metrics['mode']}`",
                f"- Broker calls: `{_display(metrics['broker_calls'])}`",
                f"- KIS API calls: `{_display(metrics['kis_api_calls'])}`",
                f"- KIS paper orders: `{_display(metrics['kis_paper_orders'])}`",
                f"- Live orders: `{_display(metrics['live_orders'])}`",
                f"- Local-paper fills: `{_display(metrics['local_paper_fills'])}`",
                "",
                "## Outcomes",
                "",
                *_bullet_items(metrics["outcomes"], empty="No authoritative outcomes."),
                f"- After-cost PnL: `{_display(metrics['after_cost_pnl'])}`",
                "",
                "## Market Data",
                "",
                f"- Root: `{metrics['market_data_root']}`",
                f"- Root exists: `{metrics['market_data_root_exists']}`",
                f"- Free space: `{_display(metrics['market_data_free_percent'])}%`",
                *_bullet_items(
                    metrics["data_operator_help_needed"],
                    empty="No operator data request.",
                ),
                "",
                "## Role Work",
                "",
                *_role_items(metrics["role_work"]),
                "",
                "## Recovery",
                "",
                *_bullet_items(
                    metrics["recovery_anomalies"], empty="No reported anomaly."
                ),
                "",
                "## Operator Decisions",
                "",
                *_bullet_items(
                    metrics["operator_decisions"], empty="No decision requested."
                ),
                "",
                "## Next",
                "",
                metrics["current_objective"],
                "",
                "Source: [NEXT_CODEX_GOAL.md](../../NEXT_CODEX_GOAL.md)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return DailyBundle(date=date, summary_path=summary_path, metrics=metrics)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("reports/daily"))
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    parser.add_argument(
        "--market-data-root", type=Path, default=DEFAULT_MARKET_DATA_ROOT
    )
    parser.add_argument(
        "--runtime-status", type=Path, default=DEFAULT_RUNTIME_STATUS
    )
    parser.add_argument("--print-summary", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    bundle = write_bundle(
        args.output_dir,
        repo_root=args.repo_root,
        market_data_root=args.market_data_root,
        runtime_status_path=args.runtime_status,
    )
    if args.print_summary:
        print(
            json.dumps(
                {
                    "status": "daily_summary_written",
                    "summary": str(bundle.summary_path),
                    "metrics": None,
                    "next_goal": None,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
