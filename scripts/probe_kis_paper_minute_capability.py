"""Run a bounded metadata-only KIS Paper QQQ minute capability probe."""

from __future__ import annotations

import argparse
import json
import math
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.data.kis_paper_minute_capability_probe import (
    KIS_PAPER_MINUTE_CAPABILITY_PROBE_CANDIDATE_TARGET_KEYS,
    KIS_PAPER_MINUTE_CAPABILITY_PROBE_MAX_PAGES,
    KIS_PAPER_MINUTE_CAPABILITY_PROBE_MIN_INTERVAL_SECONDS,
    KIS_PAPER_MINUTE_CAPABILITY_PROBE_NATIVE_TARGET_KEYS,
    probe_and_write_kis_paper_minute_capability,
    probe_and_write_kis_paper_minute_fixed_key_capability,
    validate_kis_paper_minute_fixed_key_probe,
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
    key_mode = parser.add_mutually_exclusive_group()
    key_mode.add_argument(
        "--explicit-older-key-once",
        action="store_true",
        help="QQQ/NAS only: full no-M/F head, then one NEXT=1/PINC=1 older-key request",
    )
    key_mode.add_argument(
        "--fixed-historical-key-pair",
        action="store_true",
        help="QQQ/NAS only: two fixed independent historical KEYB requests, metadata only",
    )
    parser.add_argument("--include-previous-day", action="store_true")
    parser.add_argument(
        "--target",
        choices=tuple(
            target_key.removesuffix("/1m")
            for target_key in sorted(
                KIS_PAPER_MINUTE_CAPABILITY_PROBE_NATIVE_TARGET_KEYS
                | KIS_PAPER_MINUTE_CAPABILITY_PROBE_CANDIDATE_TARGET_KEYS
            )
        ),
        default="QQQ/NAS",
    )
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument(
        "--max-pages",
        type=int,
        default=KIS_PAPER_MINUTE_CAPABILITY_PROBE_MAX_PAGES,
    )
    parser.add_argument(
        "--minimum-request-interval-seconds",
        type=float,
        default=KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS,
    )
    args = parser.parse_args(argv)
    if args.fixed_historical_key_pair:
        if args.target != "QQQ/NAS" or args.include_previous_day or args.max_pages not in {2, 3}:
            parser.error("fixed historical keys require QQQ/NAS, two pages and no head-mode flags")
        validate_kis_paper_minute_fixed_key_probe()
    if not args.execute:
        print(json.dumps({"status": "not_executed", "reason": "execute_flag_required"}))
        return 0
    if not 1 <= args.max_pages <= KIS_PAPER_MINUTE_CAPABILITY_PROBE_MAX_PAGES:
        parser.error("--max-pages must be between 1 and 3")
    if not (
        math.isfinite(args.minimum_request_interval_seconds)
        and KIS_PAPER_MINUTE_CAPABILITY_PROBE_MIN_INTERVAL_SECONDS
        <= args.minimum_request_interval_seconds
        <= KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS
    ):
        parser.error("--minimum-request-interval-seconds must be between 1.0 and the current gate")
    target_key = f"{args.target}/1m"
    if args.explicit_older_key_once and (
        args.target != "QQQ/NAS" or args.include_previous_day or args.max_pages < 2
    ):
        parser.error("explicit older-key mode requires QQQ/NAS current head and at least two pages")
    max_pages = (
        2 if args.explicit_older_key_once or args.fixed_historical_key_pair else args.max_pages
    )
    if target_key in KIS_PAPER_MINUTE_CAPABILITY_PROBE_CANDIDATE_TARGET_KEYS and (
        args.max_pages != 1 or args.include_previous_day
    ):
        parser.error("candidate target requires --max-pages 1 without --include-previous-day")

    request_start_times: list[datetime] = []
    symbol, exchange = str(args.target).split("/", maxsplit=1)
    try:
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
            max_minute_page_attempts=max_pages,
        )
        if args.fixed_historical_key_pair:
            result = probe_and_write_kis_paper_minute_fixed_key_capability(
                client=client,
                artifact_root=args.artifact_root,
                repository_root=_REPOSITORY_ROOT,
                observed_at=clock(),
            )
        else:
            result = probe_and_write_kis_paper_minute_capability(
                client=client,
                request_start_times=request_start_times,
                artifact_root=args.artifact_root,
                repository_root=_REPOSITORY_ROOT,
                observed_at=clock(),
                max_pages=max_pages,
                explicit_older_key_once=args.explicit_older_key_once,
                include_previous_day=args.include_previous_day,
                target=(symbol, exchange),
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

    payload = {**result.outcome.safe_payload(), "evidence_path": str(result.evidence_path)}
    if args.fixed_historical_key_pair:
        payload["evidence_sha256"] = result.evidence_sha256
    print(
        json.dumps(
            payload,
            sort_keys=True,
        )
    )
    return 0 if result.outcome.status != "unavailable" else 2


if __name__ == "__main__":
    raise SystemExit(main())
