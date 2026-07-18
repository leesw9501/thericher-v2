"""Build one host-only, development-source Norgate trial raw-D1 snapshot."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime, time, timedelta
from importlib.metadata import version
from pathlib import Path

from thericher_v2.contracts import Timeframe
from thericher_v2.data.norgate_daily import NorgateRawDailyBarProvider
from thericher_v2.data.norgate_trial_raw_d1 import (
    build_norgate_trial_raw_d1_snapshot,
    default_norgate_trial_raw_d1_snapshot_dir,
    load_norgate_capital_event_evidence,
)
from thericher_v2.data.provider import BarQuery

REQUESTED_START = date(2024, 7, 18)
REQUESTED_END = date(2026, 6, 22)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    retrieved_at = datetime.now(UTC)
    provider = NorgateRawDailyBarProvider()

    def load_bars(symbol: str, start: date, end: date):
        return provider.get_bars(
            BarQuery(
                symbol=symbol,
                market="US",
                timeframe=Timeframe.D1,
                start_ts=datetime.combine(start, time(), UTC),
                end_ts=datetime.combine(end + timedelta(days=1), time(), UTC),
            )
        )

    result = build_norgate_trial_raw_d1_snapshot(
        destination=args.destination or default_norgate_trial_raw_d1_snapshot_dir(
            retrieved_at.date()
        ),
        requested_start=REQUESTED_START,
        requested_end=REQUESTED_END,
        retrieved_at_utc=retrieved_at,
        norgate_bars=load_bars,
        capital_event_evidence=load_norgate_capital_event_evidence,
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
                "common_session_count": result.common_session_count,
                "observed_event_marker_count": result.event_marker_count,
                "event_marker_count_interpretation": (
                    "not_established_from_clipped_or_padded_query"
                ),
                "excluded_session_count": result.excluded_session_count,
                "actual_start": result.actual_start.isoformat(),
                "actual_end": result.actual_end.isoformat(),
                "norgate_package_version": result.norgate_package_version,
                "free_percent": result.free_percent,
                "development_training_eligible": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
