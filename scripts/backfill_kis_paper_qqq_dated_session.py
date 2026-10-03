"""One bounded fixed-date native QQQ retention invocation, never a scheduled loop."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path

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
    KIS_PAPER_QQQ_DATED_CACHE_ROOT,
    KIS_PAPER_QQQ_DATED_INITIAL_KEY,
    KIS_PAPER_QQQ_DATED_SESSION,
    kis_paper_qqq_dated_session_complete,
    run_kis_paper_qqq_dated_session_cycle,
    sanitize_kis_paper_private_intraday_failure_reason,
    validate_kis_paper_qqq_dated_session_request,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--pages", type=int, default=4)
    parser.add_argument(
        "--session-date", type=date.fromisoformat, default=KIS_PAPER_QQQ_DATED_SESSION
    )
    parser.add_argument("--cache-root", type=Path, default=KIS_PAPER_QQQ_DATED_CACHE_ROOT)
    parser.add_argument("--code-revision")
    args = parser.parse_args(argv)
    try:
        validate_kis_paper_qqq_dated_session_request(
            cache_root=args.cache_root,
            repo_root=_REPO_ROOT,
            session_date=args.session_date,
            pages=args.pages,
            inspect_paths=False,
        )
    except ValueError:
        parser.error("fixed September 1 QQQ scope and 1..4 pages required")
    if not args.execute:
        print(
            json.dumps(
                {
                    "status": "not_executed",
                    "keyb": KIS_PAPER_QQQ_DATED_INITIAL_KEY,
                    "max_gets": args.pages,
                    "reason": "execute_flag_required",
                }
            )
        )
        return 0
    if not args.code_revision or not args.code_revision.strip() or "\n" in args.code_revision:
        parser.error("--code-revision is required for execution")
    try:
        validate_kis_paper_qqq_dated_session_request(
            cache_root=args.cache_root,
            repo_root=_REPO_ROOT,
            session_date=args.session_date,
            pages=args.pages,
        )
        config = _load_paper_config()
        control_root = KIS_PAPER_PRIVATE_INTRADAY_CACHE_ROOT.parent / (
            KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY
        )
        client = KisPaperMarketDataClient(
            config=config,
            max_minute_page_attempts=args.pages,
            transport=UrllibKisPaperMarketDataTransport(
                request_gate=KisPaperMarketDataRateGate(control_root=control_root),
                token_start_gate=KisPaperMarketDataTokenStartGate(control_root=control_root),
            ),
        )
        result = run_kis_paper_qqq_dated_session_cycle(
            client=client,
            cache_root=args.cache_root,
            repo_root=_REPO_ROOT,
            code_revision=args.code_revision,
            session_date=args.session_date,
            pages=args.pages,
        )
        complete = result.status in {"collected", "partial", "recovered"} and (
            kis_paper_qqq_dated_session_complete(
                cache_root=args.cache_root,
                repo_root=_REPO_ROOT,
            )
        )
        payload = {
            "status": "complete" if complete else "incomplete",
            "collection_status": result.status,
            "reason": result.reason,
            "row_count": result.row_count,
            "exact_overlap_rows": result.exact_overlap_rows,
            "manifest_path": str(result.manifest_path) if result.manifest_path else None,
            "manifest_hash": result.manifest_hash,
            "regular_session_complete": complete,
        }
    except KisPaperMarketDataError as error:
        payload = {
            "status": "incomplete",
            "reason": sanitize_kis_paper_private_intraday_failure_reason(error),
        }
        complete = False
    except (OSError, ValueError):
        payload = {"status": "indeterminate", "reason": "dated_session_unavailable"}
        complete = False
    print(json.dumps(payload, sort_keys=True))
    return 0 if complete else 1


def _load_paper_config() -> KisPaperMarketDataConfig:
    # Native invocation uses the existing byte-wise approved dotenv whitelist,
    # never ambient Docker credentials or unapproved account/live fields.
    return load_kis_paper_market_data_config(_REPO_ROOT / ".env", environment={})


if __name__ == "__main__":
    raise SystemExit(main())
