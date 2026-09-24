"""Collect one bounded, prior-session-only KIS Paper SPY daily head snapshot."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataClient,
    KisPaperMarketDataError,
    UrllibKisPaperMarketDataTransport,
    load_kis_paper_market_data_config,
)
from thericher_v2.execution.kis_market_data_rate_gate import (
    KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY,
    KIS_PAPER_MARKET_DATA_TOKEN_REQUEST_NOT_DUE_REASON,
    KisPaperMarketDataRateGate,
    KisPaperMarketDataTokenStartGate,
)
from thericher_v2.execution.kis_paper_daily_spy_head import (
    KIS_PAPER_DAILY_SPY_HEAD_ROOT,
    KisPaperDailySpyHeadError,
    collect_kis_paper_daily_spy_head_once,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_RECOVERY_EXIT = 20
_MARKET_DATA_FAILURE_CATEGORIES = frozenset(
    {
        "config_missing",
        "paper_host_required",
        "request_not_allowlisted",
        "redirect_rejected",
        "transport_failure",
        "response_invalid",
        "daily_response_invalid",
        "daily_page_limit_exceeded",
        "rate_limited",
        "auth_rejected",
        "auth_response_invalid",
        KIS_PAPER_MARKET_DATA_TOKEN_REQUEST_NOT_DUE_REASON,
    }
)


def main(
    argv: Sequence[str] | None = None,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    dotenv_path: Path = _REPOSITORY_ROOT / ".env",
) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--cache-root", type=Path, default=KIS_PAPER_DAILY_SPY_HEAD_ROOT)
    parser.add_argument("--repository-root", type=Path, default=_REPOSITORY_ROOT)
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status": "not_executed", "reason": "execute_flag_required"}))
        return 0
    failure_stage = "environment"
    try:
        config = load_kis_paper_market_data_config(dotenv_path)
        failure_stage = "control_gate"
        request_gate = KisPaperMarketDataRateGate(
            control_root=_shared_control_root(Path(args.cache_root))
        )
        token_start_gate = KisPaperMarketDataTokenStartGate(
            control_root=_shared_control_root(Path(args.cache_root))
        )
        failure_stage = "client_setup"
        client = KisPaperMarketDataClient(
            config=config,
            transport=UrllibKisPaperMarketDataTransport(
                request_gate=request_gate,
                token_start_gate=token_start_gate,
            ),
        )
        failure_stage = "collection"
        result = collect_kis_paper_daily_spy_head_once(
            client,
            cache_root=args.cache_root,
            repository_root=args.repository_root,
            observed_at=clock(),
        )
        payload = result.safe_payload()
    except Exception as error:
        # Exception messages can contain provider bodies or private paths.
        reason = "daily_head_unavailable"
        if isinstance(error, KisPaperMarketDataError):
            reason = "market_data_unavailable"
            category = "market_data_error"
            if (
                len(error.args) == 1
                and type(error.args[0]) is str
                and error.args[0] in _MARKET_DATA_FAILURE_CATEGORIES
            ):
                category = error.args[0]
        elif isinstance(error, KisPaperDailySpyHeadError):
            category = "head_contract"
        elif isinstance(error, OSError):
            category = "io_error"
        elif isinstance(error, ValueError):
            category = "invalid_input"
        else:
            category = "unexpected_error"
        print(
            json.dumps(
                {
                    "status": "unavailable",
                    "reason": reason,
                    "failure_stage": failure_stage,
                    "failure_category": category,
                },
                sort_keys=True,
            )
        )
        return _RECOVERY_EXIT
    if result.status == "unavailable":
        payload.update(
            failure_stage="collection",
            failure_category="insufficient_completed_rows",
        )
        print(json.dumps(payload, sort_keys=True))
        return _RECOVERY_EXIT
    print(json.dumps(payload, sort_keys=True))
    return 0


def _shared_control_root(cache_root: Path) -> Path:
    """Locate the common gate beside every private KIS Paper cache lane."""

    if cache_root.name == "v1" and cache_root.parent.name == "daily-head":
        return cache_root.parent.parent / KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY
    return cache_root.parent / KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY


if __name__ == "__main__":
    raise SystemExit(main())
