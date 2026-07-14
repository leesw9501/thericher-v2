"""Generate one concise daily operator-review bundle."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def run_git(args: list[str]) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError as exc:
        return f"git unavailable: {exc}"
    output = completed.stdout.strip() or completed.stderr.strip()
    return output


@dataclass(frozen=True)
class DailyBundle:
    date: str
    summary_path: Path
    metrics_path: Path
    next_goal_path: Path
    metrics: dict[str, Any]


def build_metrics(now: datetime) -> dict[str, Any]:
    status = run_git(["status", "--short", "--branch"])
    last_commit = run_git(["log", "-1", "--oneline", "--decorate"])
    return {
        "artifact_kind": "daily_operator_review",
        "created_at_utc": now.astimezone(UTC).isoformat(),
        "git_status": status,
        "last_commit": last_commit,
        "mode": "off",
        "broker_calls": False,
        "kis_api_calls": False,
        "paper_orders": False,
        "live_orders": False,
        "recommended_next_goal": (
            "Implement the first real data adapter after reviewing the v2 skeleton."
        ),
    }


def write_bundle(output_dir: Path, *, now: datetime | None = None) -> DailyBundle:
    now = now or datetime.now(UTC)
    date = now.date().isoformat()
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics = build_metrics(now)
    summary_path = output_dir / f"{date}-summary.md"
    metrics_path = output_dir / f"{date}-metrics.json"
    next_goal_path = output_dir / f"{date}-next-goal.md"

    summary_path.write_text(
        "\n".join(
            [
                f"# Daily Summary - {date}",
                "",
                "## Status",
                "",
                f"- Mode: `{metrics['mode']}`",
                f"- Broker calls: `{metrics['broker_calls']}`",
                f"- KIS API calls: `{metrics['kis_api_calls']}`",
                f"- Paper orders: `{metrics['paper_orders']}`",
                f"- Live orders: `{metrics['live_orders']}`",
                "",
                "## Git",
                "",
                f"- Last commit: `{metrics['last_commit']}`",
                f"- Status: `{metrics['git_status']}`",
                "",
                "## Next",
                "",
                metrics["recommended_next_goal"],
                "",
            ]
        ),
        encoding="utf-8",
    )
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
    next_goal_path.write_text(
        "\n".join(
            [
                f"# Next Goal - {date}",
                "",
                "Continue from the v2 skeleton and implement the next smallest engine-first slice.",
                "",
                "Hard boundaries remain:",
                "",
                "- no KIS API calls,",
                "- no paper or live orders,",
                "- no credential reads,",
                "- no report sprawl.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return DailyBundle(
        date=date,
        summary_path=summary_path,
        metrics_path=metrics_path,
        next_goal_path=next_goal_path,
        metrics=metrics,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("reports/daily"))
    parser.add_argument("--print-summary", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    bundle = write_bundle(args.output_dir)
    if args.print_summary:
        print(
            json.dumps(
                {
                    "status": "daily_bundle_written",
                    "summary": str(bundle.summary_path),
                    "metrics": str(bundle.metrics_path),
                    "next_goal": str(bundle.next_goal_path),
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
