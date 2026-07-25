"""Run one bounded private KIS Paper 1m cache collection cycle."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.data.kis_paper_intraday import (
    build_kis_paper_private_intraday_freshness_snapshot,
)
from thericher_v2.data.market_data_freshness_runtime import write_market_data_freshness_runtime
from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataClient,
    KisPaperMarketDataConfig,
    KisPaperMarketDataError,
    UrllibKisPaperMarketDataTransport,
    load_kis_paper_market_data_config,
)
from thericher_v2.execution.kis_market_data_rate_gate import (
    KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY,
    KisPaperMarketDataRateGate,
    KisPaperMarketDataTokenStartGate,
)
from thericher_v2.execution.kis_private_intraday_backfill import (
    KIS_PAPER_PRIVATE_INTRADAY_CACHE_ROOT,
    KIS_PAPER_PRIVATE_INTRADAY_TARGETS,
    KisPaperPrivateIntradayBackfillRun,
    run_kis_paper_private_intraday_backfill_cycle,
    sanitize_kis_paper_private_intraday_failure_reason,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_HEAD_PREPARATION_SCRIPT = (
    _REPO_ROOT / "scripts" / "prepare_kis_intraday_prospective_head_observation.py"
)
_HEAD_PREPARATION_RUN_LABEL = "scheduled-head-v1"
_HEAD_PREPARATION_TIMEOUT_SECONDS = 10.0
_HEAD_PREPARATION_STATUSES = frozenset({"pending", "prepared"})
_HEAD_PREPARATION_TARGET_KEY = "QQQ/NAS/1m"
_HEAD_PREPARATION_INPUT_STATUSES = frozenset({"collected", "recovered"})
_DEFAULT_PREPARATION_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")


def main(
    argv: Sequence[str] | None = None,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    dotenv_path: Path = _REPO_ROOT / ".env",
    code_revision: Callable[[Path], str] | None = None,
) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--project-only", action="store_true")
    parser.add_argument("--pages-per-target", type=int, default=2)
    parser.add_argument(
        "--mode",
        choices=("backfill", "head", "historical-probe"),
        default="backfill",
    )
    parser.add_argument(
        "--preparation-artifact-root",
        type=Path,
        default=_preparation_artifact_root_from_environment(),
    )
    parser.add_argument("--runtime-projection", type=Path)
    args = parser.parse_args(argv)
    observed_at = clock()
    if args.project_only:
        if args.runtime_projection is None:
            parser.error("--project-only requires --runtime-projection")
        _write_freshness_projection(
            cache_root=_base_cache_root(),
            runtime_projection=args.runtime_projection,
            observed_at=observed_at,
        )
        print(
            json.dumps(
                {"scope": "backfill_and_head", "status": "freshness_projected"},
                sort_keys=True,
            )
        )
        return 0
    if not args.execute:
        print(json.dumps({"status": "not_executed", "reason": "execute_flag_required"}))
        return 0
    if args.pages_per_target <= 0:
        parser.error("--pages-per-target must be positive")

    try:
        config = _load_paper_config(dotenv_path)
        request_gate = KisPaperMarketDataRateGate(
            control_root=_base_cache_root().parent / KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY
        )
        token_start_gate = KisPaperMarketDataTokenStartGate(
            control_root=_base_cache_root().parent / KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY
        )
        client = KisPaperMarketDataClient(
            config=config,
            transport=UrllibKisPaperMarketDataTransport(
                request_gate=request_gate,
                token_start_gate=token_start_gate,
            ),
            max_minute_page_attempts=len(KIS_PAPER_PRIVATE_INTRADAY_TARGETS)
            * args.pages_per_target,
        )
        results = run_kis_paper_private_intraday_backfill_cycle(
            client=client,
            cache_root=_cache_root(args.mode),
            repo_root=_REPO_ROOT,
            code_revision=(code_revision or _current_code_revision)(_REPO_ROOT),
            pages_per_target=args.pages_per_target,
            resume_cursor=args.mode == "backfill",
            observed_at=observed_at,
        )
    except KisPaperMarketDataError as error:
        _print_with_optional_freshness(
            {
                "status": "not_executed",
                "reason": sanitize_kis_paper_private_intraday_failure_reason(error),
            },
            cache_root=_base_cache_root(),
            runtime_projection=args.runtime_projection,
            observed_at=observed_at,
        )
        return 1
    except (OSError, ValueError):
        _print_with_optional_freshness(
            {"status": "indeterminate", "reason": "backfill_worker_unavailable"},
            cache_root=_base_cache_root(),
            runtime_projection=args.runtime_projection,
            observed_at=observed_at,
        )
        return 1
    collection_succeeded = _collection_succeeded(results)
    payload: dict[str, object] = {
        "status": "complete" if collection_succeeded else "incomplete",
        "mode": args.mode,
        "targets": [
            {
                "target_key": result.target_key,
                "status": result.status,
                "row_count": result.row_count,
                "exact_overlap_rows": result.exact_overlap_rows,
                "reason": result.reason,
            }
            for result in results
        ],
    }
    if args.mode == "head" and _head_preparation_input_succeeded(results):
        payload["preparation"] = _prepare_head_observation(
            head_cache_root=_cache_root("head"),
            artifact_root=Path(args.preparation_artifact_root),
        )
    if args.runtime_projection is not None:
        _print_with_optional_freshness(
            payload,
            cache_root=_base_cache_root(),
            runtime_projection=args.runtime_projection,
            observed_at=observed_at,
        )
        return 0 if collection_succeeded else 1
    print(json.dumps(payload, sort_keys=True))
    return 0 if collection_succeeded else 1


def _current_code_revision(repo_root: Path) -> str:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=normal"],
                cwd=repo_root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
    except (OSError, subprocess.SubprocessError):
        return "git:unavailable"
    return f"git:{revision}" + ("+dirty" if dirty else "")


def _load_paper_config(dotenv_path: Path) -> KisPaperMarketDataConfig:
    if os.environ.get("THERICHER_MODE", "off").strip().lower() in {"live", "kis_live"}:
        raise KisPaperMarketDataError("config_missing")
    app_key = os.environ.get("KIS_PAPER_APP_KEY")
    app_secret = os.environ.get("KIS_PAPER_APP_SECRET")
    if app_key is None and app_secret is None:
        return load_kis_paper_market_data_config(dotenv_path)
    if not app_key or not app_secret:
        raise KisPaperMarketDataError("config_missing")
    return KisPaperMarketDataConfig(app_key=app_key, app_secret=app_secret)


def _preparation_artifact_root_from_environment() -> Path:
    configured = os.environ.get("THERICHER_MODEL_ARTIFACT_ROOT")
    return Path(configured) if configured else _DEFAULT_PREPARATION_ARTIFACT_ROOT


def _collection_succeeded(results: Sequence[KisPaperPrivateIntradayBackfillRun]) -> bool:
    expected_targets = {
        f"{symbol}/{exchange}/1m" for symbol, exchange in KIS_PAPER_PRIVATE_INTRADAY_TARGETS
    }
    return (
        len(results) == len(expected_targets)
        and {result.target_key for result in results} == expected_targets
        and all(
            result.status in {"collected", "recovered", "source_exhausted"}
            for result in results
        )
    )


def _head_preparation_input_succeeded(
    results: Sequence[KisPaperPrivateIntradayBackfillRun],
) -> bool:
    qqq_results = [
        result for result in results if result.target_key == _HEAD_PREPARATION_TARGET_KEY
    ]
    return len(qqq_results) == 1 and qqq_results[0].status in _HEAD_PREPARATION_INPUT_STATUSES


def _prepare_head_observation(*, head_cache_root: Path, artifact_root: Path) -> dict[str, str]:
    command = [
        sys.executable,
        str(_HEAD_PREPARATION_SCRIPT),
        "--run-label",
        _HEAD_PREPARATION_RUN_LABEL,
        "--head-cache-root",
        str(head_cache_root),
        "--artifact-root",
        str(artifact_root),
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            cwd=_REPO_ROOT,
            env=_head_preparation_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=_HEAD_PREPARATION_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return _preparation_unavailable("child_timeout")
    except UnicodeError:
        return _preparation_unavailable("child_output_invalid")
    except OSError:
        return _preparation_unavailable("child_unavailable")
    if completed.returncode != 0:
        return _preparation_unavailable("child_exit_nonzero")
    return _categorize_preparation_output(completed.stdout)


def _head_preparation_environment() -> dict[str, str]:
    environment = {"PYTHONPATH": str(_REPO_ROOT / "src")}
    for name in ("PATH", "SYSTEMROOT"):
        value = os.environ.get(name)
        if value:
            environment[name] = value
    return environment


def _categorize_preparation_output(stdout: object) -> dict[str, str]:
    try:
        payload = json.loads(stdout)
    except (TypeError, json.JSONDecodeError):
        return _preparation_unavailable("child_output_invalid")
    if not isinstance(payload, dict):
        return _preparation_unavailable("child_output_invalid")
    status = payload.get("status")
    if status not in _HEAD_PREPARATION_STATUSES:
        return _preparation_unavailable("child_output_invalid")
    return {"status": status}


def _preparation_unavailable(reason: str) -> dict[str, str]:
    return {"status": "preparation_unavailable", "reason": reason}


def _cache_root(mode: str = "backfill") -> Path:
    if mode not in {"backfill", "head", "historical-probe"}:
        raise ValueError("private intraday mode is invalid")
    base = _base_cache_root()
    if mode == "backfill":
        return base
    suffix = "head" if mode == "head" else "historical-probe"
    return base.with_name(f"{base.name}-{suffix}")


def _base_cache_root() -> Path:
    market_data_root = os.environ.get("THERICHER_MARKET_DATA_ROOT")
    if not market_data_root:
        return KIS_PAPER_PRIVATE_INTRADAY_CACHE_ROOT
    return Path(market_data_root) / "us_equities" / "kis_paper_private" / "intraday"


def _write_freshness_projection(
    *,
    cache_root: Path,
    runtime_projection: Path,
    observed_at: datetime,
) -> None:
    snapshot = build_kis_paper_private_intraday_freshness_snapshot(
        cache_root=cache_root,
        repo_root=_REPO_ROOT,
        observed_at=observed_at,
    )
    write_market_data_freshness_runtime(snapshot, runtime_projection)


def _print_with_optional_freshness(
    payload: dict[str, object],
    *,
    cache_root: Path,
    runtime_projection: Path | None,
    observed_at: datetime,
) -> None:
    if runtime_projection is not None:
        try:
            _write_freshness_projection(
                cache_root=cache_root,
                runtime_projection=runtime_projection,
                observed_at=observed_at,
            )
        except (OSError, ValueError):
            payload["freshness_projection"] = "unavailable"
        else:
            payload["freshness_projection"] = "written"
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
