"""Build one bounded host-only Norgate broad daily development panel."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime, time, timedelta
from importlib.metadata import version
from pathlib import Path

from thericher_v2.contracts import Timeframe
from thericher_v2.data.norgate_daily import NorgateRawDailyBarProvider
from thericher_v2.data.norgate_trial_development_panel import (
    build_norgate_trial_development_panel_snapshot,
    default_norgate_trial_development_panel_snapshot_dir,
)
from thericher_v2.data.provider import BarQuery

DEFAULT_MEMBERSHIP = Path(
    "D:/market_data/us_equities/norgate_membership/canonical/sp500_current_past/"
    "snapshot=2026-07-18-norgate-sp500-membership-r1"
)
DEFAULT_CALENDAR = Path(
    "D:/market_data/us_equities/fixed_etf_daily/canonical/norgate_trial_raw_d1/"
    "snapshot=2026-07-18-norgate-trial-raw-d1-r2"
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--membership", type=Path, default=DEFAULT_MEMBERSHIP)
    parser.add_argument("--calendar", type=Path, default=DEFAULT_CALENDAR)
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

    result = build_norgate_trial_development_panel_snapshot(
        destination=args.destination
        or default_norgate_trial_development_panel_snapshot_dir(retrieved_at.date()),
        membership_snapshot=args.membership,
        calendar_snapshot=args.calendar,
        retrieved_at_utc=retrieved_at,
        load_bars=load_bars,
        norgate_package_version=version("norgatedata"),
        repo_root=Path.cwd(),
    )
    print(
        json.dumps(
            {
                "snapshot_dir": str(result.snapshot_dir),
                "membership_snapshot_dir": str(result.membership_snapshot_dir),
                "calendar_snapshot_dir": str(result.calendar_snapshot_dir),
                "dataset_hash": result.dataset_hash,
                "manifest_hash": result.manifest_hash,
                "candidate_count": result.candidate_count,
                "selected_symbol_count": result.selected_symbol_count,
                "unavailable_count": result.unavailable_count,
                "session_mismatch_count": result.session_mismatch_count,
                "invalid_count": result.invalid_count,
                "common_session_count": result.common_session_count,
                "actual_start": result.actual_start.isoformat(),
                "actual_end": result.actual_end.isoformat(),
                "development_training_eligible": result.development_training_eligible,
                "norgate_package_version": result.norgate_package_version,
                "free_percent": result.free_percent,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
