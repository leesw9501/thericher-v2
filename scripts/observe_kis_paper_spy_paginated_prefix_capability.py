"""Run the credential-free observer for the isolated SPY prefix capability."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from thericher_v2.data.kis_spy_paginated_prefix_capability import (
    KIS_SPY_PAGINATED_PREFIX_CACHE_DIRECTORY,
    observe_spy_paginated_prefix_positive,
    preflight_spy_paginated_prefix_positive,
    record_spy_paginated_prefix_negative_control,
    run_id_for_session,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CACHE_ROOT = (
    Path(r"D:\market_data\us_equities\kis_paper_private") / KIS_SPY_PAGINATED_PREFIX_CACHE_DIRECTORY
)
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")


def main(
    argv: Sequence[str] | None = None,
    *,
    now_utc: Callable[[], datetime] | None = None,
) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.run_id != run_id_for_session(args.session_date):
        parser.error("run id must match the planned Eastern session")
    observed_at = (now_utc or _now_utc)()
    if args.phase == "negative-control":
        outcome = record_spy_paginated_prefix_negative_control(
            cache_root=args.cache_root,
            artifact_root=args.artifact_root,
            repository_root=args.repository_root,
            session_date=args.session_date,
            run_id=args.run_id,
            observed_at=observed_at,
        )
        print(json.dumps(outcome.safe_payload(), sort_keys=True))
        return 0
    if args.phase == "positive-preflight":
        outcome = preflight_spy_paginated_prefix_positive(
            artifact_root=args.artifact_root,
            repository_root=args.repository_root,
            session_date=args.session_date,
            run_id=args.run_id,
            observed_at=observed_at,
        )
        print(json.dumps(outcome.safe_payload(), sort_keys=True))
        return 0
    if args.collection_started_at is None or args.collector_returned_at is None:
        parser.error("positive observation requires collector timing")
    outcome = observe_spy_paginated_prefix_positive(
        cache_root=args.cache_root,
        artifact_root=args.artifact_root,
        repository_root=args.repository_root,
        session_date=args.session_date,
        run_id=args.run_id,
        collection_started_at=args.collection_started_at,
        collector_returned_at=args.collector_returned_at,
        collection_exit_code=args.collection_exit_code,
        observer_started_at=observed_at,
    )
    print(json.dumps(outcome.safe_payload(), sort_keys=True))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Observe one SPY prefix capability run")
    parser.add_argument(
        "--phase",
        choices=("negative-control", "positive-preflight", "positive-observation"),
        required=True,
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--session-date", required=True, type=_parse_date)
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--repository-root", type=Path, default=_REPOSITORY_ROOT)
    parser.add_argument("--collection-started-at", type=_parse_utc)
    parser.add_argument("--collector-returned-at", type=_parse_utc)
    parser.add_argument("--collection-exit-code", type=int, default=0)
    return parser


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("session date must be YYYY-MM-DD") from error


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("timestamp must be UTC") from error
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise argparse.ArgumentTypeError("timestamp must be UTC")
    return parsed.astimezone(UTC)


if __name__ == "__main__":
    raise SystemExit(main())
