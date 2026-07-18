"""Build one fixed host-only Norgate/Tiingo raw-D1 alignment snapshot."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime, time, timedelta
from importlib.metadata import version
from pathlib import Path

from thericher_v2.contracts import Timeframe
from thericher_v2.data.norgate_daily import NorgateRawDailyBarProvider
from thericher_v2.data.norgate_raw_alignment import (
    TiingoRawD1Reference,
    build_norgate_raw_d1_alignment_snapshot,
    default_norgate_raw_alignment_snapshot_dir,
)
from thericher_v2.data.provider import BarQuery
from thericher_v2.data.tiingo_eod import (
    load_cataloged_tiingo_raw_d1_bars,
    load_fixed_r2_corporate_action_lineage,
)

REQUESTED_START = date(2022, 11, 22)
REQUESTED_END = date(2026, 6, 22)
TIINGO_RAW_D1_SNAPSHOT = Path(
    "D:/market_data/us_equities/fixed_etf_daily/canonical/tiingo_raw_d1/"
    "snapshot=2026-07-18-tiingo-raw-d1-r1"
)
TIINGO_RAW_D1_DATASET_ID = (
    "us_equities.fixed_etf_tiingo_raw_d1.snapshot=2026-07-18-tiingo-raw-d1-r1"
)
TIINGO_RAW_D1_DATASET_HASH = (
    "sha256:9056112167ab920335cb8a5f3c2f45d540a04e1132ee6eb231bac16ee11d7a3d"
)
TIINGO_RAW_D1_MANIFEST_HASH = (
    "sha256:44a6316e9821694886fa3f791ddb19ec56a435dbaf765417a9568b4a3e57f421"
)
TIINGO_CORPORATE_ACTION_SNAPSHOT = Path(
    "D:/market_data/us_equities/fixed_etf_corporate_actions/canonical/"
    "tiingo_standard_eod/snapshot=2026-07-18-tiingo-eod-corporate-actions-r1"
)
R2_SNAPSHOT = Path(
    "D:/market_data/us_equities/fixed_etf_daily/canonical/ohlcv_1d/"
    "snapshot=2026-07-18-r2"
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    retrieved_at = datetime.now(UTC)
    destination = args.destination or default_norgate_raw_alignment_snapshot_dir(
        retrieved_at.date()
    )
    provider = NorgateRawDailyBarProvider()
    r2_lineage = load_fixed_r2_corporate_action_lineage(R2_SNAPSHOT)

    def read_norgate(symbol: str, start: date, end: date):
        return provider.get_bars(
            BarQuery(
                symbol=symbol,
                market="US",
                timeframe=Timeframe.D1,
                start_ts=datetime.combine(start, time(), UTC),
                end_ts=datetime.combine(end + timedelta(days=1), time(), UTC),
            )
        )

    def read_tiingo(symbol: str, _start: date, _end: date):
        return load_cataloged_tiingo_raw_d1_bars(
            TIINGO_RAW_D1_SNAPSHOT,
            dataset_id=TIINGO_RAW_D1_DATASET_ID,
            expected_dataset_hash=TIINGO_RAW_D1_DATASET_HASH,
            expected_manifest_hash=TIINGO_RAW_D1_MANIFEST_HASH,
            source_snapshot_dir=TIINGO_CORPORATE_ACTION_SNAPSHOT,
            r2_lineage=r2_lineage,
            symbol=symbol,
            repo_root=Path.cwd(),
        ).bars

    result = build_norgate_raw_d1_alignment_snapshot(
        destination=destination,
        requested_start=REQUESTED_START,
        requested_end=REQUESTED_END,
        retrieved_at_utc=retrieved_at,
        tiingo_reference=TiingoRawD1Reference(
            snapshot_dir=TIINGO_RAW_D1_SNAPSHOT,
            dataset_id=TIINGO_RAW_D1_DATASET_ID,
            dataset_hash=TIINGO_RAW_D1_DATASET_HASH,
            manifest_hash=TIINGO_RAW_D1_MANIFEST_HASH,
        ),
        norgate_bars=read_norgate,
        tiingo_bars=read_tiingo,
        norgate_package_version=version("norgatedata"),
        repo_root=Path.cwd(),
    )
    print(
        json.dumps(
            {
            "snapshot_dir": str(result.snapshot_dir),
            "dataset_id": result.dataset_id,
            "dataset_hash": result.dataset_hash,
            "manifest_hash": result.manifest_hash,
            "row_count": result.row_count,
            "comparison_status": result.comparison_status,
            "requested_start": result.requested_start.isoformat(),
            "requested_end": result.requested_end.isoformat(),
            "norgate_package_version": result.norgate_package_version,
            "free_percent": result.free_percent,
            "validation": "passed",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
