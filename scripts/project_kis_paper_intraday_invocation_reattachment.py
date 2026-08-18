"""Print one source-safe intraday invocation-to-terminal reattachment."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.data.kis_paper_intraday_capture_topology import (
    KisPaperIntradayCaptureTaskFacts,
)
from thericher_v2.ops.kis_paper_intraday_head_invocation_receipt import (
    DEFAULT_KIS_PAPER_INTRADAY_HEAD_INVOCATION_ARTIFACT_ROOT,
)
from thericher_v2.ops.kis_paper_intraday_invocation_reattachment import (
    reattach_kis_paper_intraday_invocation_from_artifact_root,
)
from thericher_v2.research.kis_intraday_prospective_head_observation import (
    KIS_INTRADAY_PROSPECTIVE_HEAD_HISTORICAL_DEVELOPMENT_SESSION_DATES,
    KIS_INTRADAY_PROSPECTIVE_HEAD_REQUIRED_SESSION_COUNT,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_HEAD_CACHE_ROOT = Path(
    r"D:\market_data\us_equities\kis_paper_private\intraday-head"
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=DEFAULT_KIS_PAPER_INTRADAY_HEAD_INVOCATION_ARTIFACT_ROOT,
    )
    parser.add_argument("--head-cache-root", type=Path, default=_DEFAULT_HEAD_CACHE_ROOT)
    parser.add_argument("--task-name", required=True)
    parser.add_argument("--task-state", required=True)
    parser.add_argument("--task-enabled", type=_boolean, required=True)
    parser.add_argument("--task-action-count", type=int, required=True)
    parser.add_argument("--trigger-start-boundary", action="append", default=[])
    parser.add_argument("--last-run-at")
    parser.add_argument("--next-run-at")
    parser.add_argument("--last-task-result", type=int, required=True)
    parser.add_argument("--missed-run-count", type=int, required=True)
    parser.add_argument(
        "--operational-log-state",
        choices=("enabled", "disabled", "unavailable"),
        required=True,
    )
    arguments = parser.parse_args(argv)
    task_facts = KisPaperIntradayCaptureTaskFacts(
        task_name=arguments.task_name,
        state=arguments.task_state,
        enabled=arguments.task_enabled,
        action_count=arguments.task_action_count,
        trigger_start_boundaries=tuple(
            _utc(value, "trigger start boundary") for value in arguments.trigger_start_boundary
        ),
        last_run_at=(
            None if arguments.last_run_at is None else _utc(arguments.last_run_at, "last run")
        ),
        next_run_at=(
            None if arguments.next_run_at is None else _utc(arguments.next_run_at, "next run")
        ),
        last_task_result=arguments.last_task_result,
        missed_run_count=arguments.missed_run_count,
        operational_log_state=arguments.operational_log_state,
    )
    result = reattach_kis_paper_intraday_invocation_from_artifact_root(
        artifact_root=arguments.artifact_root,
        capture_cache_root=arguments.head_cache_root,
        repository_root=_REPOSITORY_ROOT,
        task_facts=task_facts,
        after_session_date=KIS_INTRADAY_PROSPECTIVE_HEAD_HISTORICAL_DEVELOPMENT_SESSION_DATES[-1],
        required_complete_session_count=KIS_INTRADAY_PROSPECTIVE_HEAD_REQUIRED_SESSION_COUNT,
    )
    print(json.dumps(result.safe_payload(), sort_keys=True))
    return 0


def _boolean(value: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise argparse.ArgumentTypeError("boolean values must be true or false")


def _utc(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"{label} is invalid") from error
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError(f"{label} is invalid")
    return parsed.astimezone(UTC)


if __name__ == "__main__":
    raise SystemExit(main())
