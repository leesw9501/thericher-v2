"""Collect one isolated, bounded KIS Paper SPY 1m prefix attempt."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from thericher_v2.data.kis_spy_paginated_prefix_capability import (
    KIS_SPY_PAGINATED_PREFIX_CACHE_DIRECTORY,
    KIS_SPY_PAGINATED_PREFIX_COLLECTION_KIND,
    KIS_SPY_PAGINATED_PREFIX_MAX_PAGES,
    collect_spy_paginated_prefix_pages,
    is_spy_paginated_prefix_positive_window,
    run_id_for_session,
    write_spy_paginated_prefix_collection_run,
)
from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataClient,
    KisPaperMarketDataConfig,
    KisPaperMarketDataError,
    KisPaperMinuteQuery,
    UrllibKisPaperMarketDataTransport,
    load_kis_paper_market_data_config,
)
from thericher_v2.execution.kis_market_data_rate_gate import (
    KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY,
    KisPaperMarketDataRateGate,
    KisPaperMarketDataTokenStartGate,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CACHE_ROOT = (
    Path(r"D:\market_data\us_equities\kis_paper_private") / KIS_SPY_PAGINATED_PREFIX_CACHE_DIRECTORY
)


def main(
    argv: Sequence[str] | None = None,
    *,
    config_loader: Callable[[Path], KisPaperMarketDataConfig] = load_kis_paper_market_data_config,
    now_utc: Callable[[], datetime] | None = None,
) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.run_id != run_id_for_session(args.session_date):
        parser.error("run id must match the planned Eastern session")
    if not args.execute:
        print(
            json.dumps(
                {
                    "kind": KIS_SPY_PAGINATED_PREFIX_COLLECTION_KIND,
                    "status": "not_executed",
                    "reason": "execute_flag_required",
                    "run_id": args.run_id,
                },
                sort_keys=True,
            )
        )
        return 0
    collection_started_at = (now_utc or _now_utc)()
    if not is_spy_paginated_prefix_positive_window(
        session_date=args.session_date,
        observed_at=collection_started_at,
    ):
        print(
            json.dumps(
                {
                    "kind": KIS_SPY_PAGINATED_PREFIX_COLLECTION_KIND,
                    "status": "collection_unavailable",
                    "reason": "outside_stage_window",
                    "run_id": args.run_id,
                    "collection_started_at": _utc_marker(collection_started_at),
                },
                sort_keys=True,
            )
        )
        return 20
    try:
        config = config_loader(args.dotenv_path)
        control_root = args.control_root or (
            args.cache_root.parent / KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY
        )
        client = KisPaperMarketDataClient(
            config=config,
            transport=UrllibKisPaperMarketDataTransport(
                request_gate=KisPaperMarketDataRateGate(control_root=control_root),
                token_start_gate=KisPaperMarketDataTokenStartGate(control_root=control_root),
            ),
            max_minute_page_attempts=KIS_SPY_PAGINATED_PREFIX_MAX_PAGES,
        )
        collection = collect_spy_paginated_prefix_pages(
            fetch_page=lambda continuation_next, continuation_key: client.fetch_minute_page(
                KisPaperMinuteQuery(
                    exchange="AMS",
                    symbol="SPY",
                    continuation_next=continuation_next,
                    continuation_key=continuation_key,
                )
            )
        )
        run = write_spy_paginated_prefix_collection_run(
            collection=collection,
            cache_root=args.cache_root,
            repository_root=args.repository_root,
            run_id=args.run_id,
            session_date=args.session_date,
            collection_started_at=collection_started_at,
            token_attempts=client.call_counts.token_attempts,
            minute_page_attempts=client.call_counts.minute_page_attempts,
        )
    except (KisPaperMarketDataError, OSError, ValueError) as error:
        print(
            json.dumps(
                {
                    "kind": KIS_SPY_PAGINATED_PREFIX_COLLECTION_KIND,
                    "status": "collection_unavailable",
                    "reason": _safe_reason(error),
                    "run_id": args.run_id,
                    "collection_started_at": _utc_marker(collection_started_at),
                },
                sort_keys=True,
            )
        )
        return 20
    print(json.dumps(run.safe_payload(), sort_keys=True))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect one KIS Paper SPY prefix capability run")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--session-date", required=True, type=_parse_date)
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE_ROOT)
    parser.add_argument("--control-root", type=Path)
    parser.add_argument("--repository-root", type=Path, default=_REPOSITORY_ROOT)
    parser.add_argument("--dotenv-path", type=Path, default=_REPOSITORY_ROOT / ".env")
    return parser


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("session date must be YYYY-MM-DD") from error


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _utc_marker(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _safe_reason(error: BaseException) -> str:
    candidate = str(error)
    return (
        candidate
        if candidate.isascii() and candidate.replace("_", "").isalnum()
        else "collector_error"
    )


if __name__ == "__main__":
    raise SystemExit(main())
