"""Collect one isolated current-day IWM/AMS KIS Paper minute page."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.data.kis_paper_iwm_m1_current_head import (
    KIS_PAPER_IWM_M1_CURRENT_HEAD_CACHE_ROOT,
    collect_and_write_kis_paper_iwm_m1_current_head,
    validate_kis_paper_iwm_m1_current_head_cache_root,
)
from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataClient,
    KisPaperMarketDataError,
    UrllibKisPaperMarketDataTransport,
    load_kis_paper_market_data_config,
)
from thericher_v2.execution.kis_market_data_rate_gate import (
    KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY,
    KisPaperMarketDataRateGate,
    KisPaperMarketDataTokenStartGate,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")


def main(
    argv: Sequence[str] | None = None,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--cache-root", type=Path, default=KIS_PAPER_IWM_M1_CURRENT_HEAD_CACHE_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status": "not_executed", "reason": "execute_flag_required"}))
        return 0

    try:
        cache_root = validate_kis_paper_iwm_m1_current_head_cache_root(
            cache_root=args.cache_root,
            repository_root=_REPOSITORY_ROOT,
        )
        control_root = cache_root.parent / KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY
        client = KisPaperMarketDataClient(
            config=load_kis_paper_market_data_config(_REPOSITORY_ROOT / ".env"),
            transport=UrllibKisPaperMarketDataTransport(
                request_gate=KisPaperMarketDataRateGate(control_root=control_root),
                token_start_gate=KisPaperMarketDataTokenStartGate(control_root=control_root),
            ),
            max_minute_page_attempts=1,
        )
        receipt = collect_and_write_kis_paper_iwm_m1_current_head(
            client=client,
            cache_root=cache_root,
            artifact_root=args.artifact_root,
            repository_root=_REPOSITORY_ROOT,
            observed_at=clock(),
        )
    except (KisPaperMarketDataError, OSError, ValueError):
        print(
            json.dumps(
                {
                    "status": "unavailable",
                    "paper_only": True,
                    "route_class": "kis_paper_market_data",
                },
                sort_keys=True,
            )
        )
        return 2

    print(json.dumps(receipt.result.outcome.safe_payload(), sort_keys=True))
    return 0 if receipt.result.outcome.status == "collected" else 2


if __name__ == "__main__":
    raise SystemExit(main())
