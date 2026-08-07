"""Run the bounded source-safe QQQ/SPY KIS Paper M1 reach probe."""

from __future__ import annotations

import argparse
import json
import math
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.data.kis_paper_m1_historical_reach_probe import (
    KIS_PAPER_M1_HISTORICAL_REACH_MIN_INTERVAL_SECONDS,
    probe_and_write_kis_paper_m1_historical_reach,
    validate_kis_paper_m1_historical_reach_artifact_root,
)
from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataClient,
    KisPaperMarketDataError,
    UrllibKisPaperMarketDataTransport,
    load_kis_paper_market_data_config,
)
from thericher_v2.execution.kis_market_data_rate_gate import (
    KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY,
    KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS,
    KisPaperMarketDataRateGate,
    KisPaperMarketDataTokenStartGate,
)
from thericher_v2.execution.kis_private_intraday_backfill import (
    KIS_PAPER_PRIVATE_INTRADAY_CACHE_ROOT,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")


def main(
    argv: Sequence[str] | None = None,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    monotonic_clock: Callable[[], float] = time.monotonic,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument(
        "--minimum-request-interval-seconds",
        type=float,
        default=KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS,
    )
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status": "not_executed", "reason": "execute_flag_required"}))
        return 0
    if not (
        math.isfinite(args.minimum_request_interval_seconds)
        and KIS_PAPER_M1_HISTORICAL_REACH_MIN_INTERVAL_SECONDS
        <= args.minimum_request_interval_seconds
        <= KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS
    ):
        parser.error("--minimum-request-interval-seconds must be between 1.0 and the current gate")

    request_start_times: list[datetime] = []
    try:
        validate_kis_paper_m1_historical_reach_artifact_root(
            artifact_root=args.artifact_root,
            repository_root=_REPOSITORY_ROOT,
        )
        control_root = (
            KIS_PAPER_PRIVATE_INTRADAY_CACHE_ROOT.parent / KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY
        )
        client = KisPaperMarketDataClient(
            config=load_kis_paper_market_data_config(_REPOSITORY_ROOT / ".env"),
            transport=UrllibKisPaperMarketDataTransport(
                request_gate=KisPaperMarketDataRateGate(
                    control_root=control_root,
                    minimum_request_interval_seconds=args.minimum_request_interval_seconds,
                    on_request_started=request_start_times.append,
                ),
                token_start_gate=KisPaperMarketDataTokenStartGate(
                    control_root=control_root,
                ),
            ),
            max_minute_page_attempts=4,
        )
        result = probe_and_write_kis_paper_m1_historical_reach(
            client=client,
            request_start_times=request_start_times,
            artifact_root=args.artifact_root,
            repository_root=_REPOSITORY_ROOT,
            observed_at=clock(),
            tested_request_interval_seconds=args.minimum_request_interval_seconds,
            monotonic_clock=monotonic_clock,
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

    print(
        json.dumps(
            {
                **result.safe_payload(),
                "evidence_paths": [str(path) for path in result.evidence_paths],
            },
            sort_keys=True,
        )
    )
    return 0 if result.status == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
