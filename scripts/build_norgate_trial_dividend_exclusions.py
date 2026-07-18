"""Build one host-only Norgate dividend-marker exclusion sidecar."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from thericher_v2.data.norgate_trial_raw_d1 import (
    build_norgate_trial_dividend_exclusion_snapshot,
    default_norgate_trial_dividend_exclusion_snapshot_dir,
    load_norgate_dividend_marker_evidence,
)

DEFAULT_PARENT = Path(
    "D:/market_data/us_equities/fixed_etf_daily/canonical/norgate_trial_raw_d1/"
    "snapshot=2026-07-18-norgate-trial-raw-d1-r2"
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--parent", type=Path, default=DEFAULT_PARENT)
    args = parser.parse_args()
    retrieved_at = datetime.now(UTC)
    result = build_norgate_trial_dividend_exclusion_snapshot(
        destination=args.destination
        or default_norgate_trial_dividend_exclusion_snapshot_dir(retrieved_at.date()),
        parent_snapshot=args.parent,
        retrieved_at_utc=retrieved_at,
        dividend_evidence=load_norgate_dividend_marker_evidence,
        norgate_package_version=version("norgatedata"),
        repo_root=Path.cwd(),
    )
    print(
        json.dumps(
            {
                "snapshot_dir": str(result.snapshot_dir),
                "parent_snapshot_dir": str(result.parent_snapshot_dir),
                "parent_dataset_hash": result.parent_dataset_hash,
                "parent_manifest_hash": result.parent_manifest_hash,
                "manifest_hash": result.manifest_hash,
                "observed_nonzero_marker_count": result.marker_count,
                "excluded_session_count": result.excluded_session_count,
                "common_session_count": result.common_session_count,
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
