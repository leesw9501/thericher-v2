"""Run one hash-bound, disjoint Tiingo standard-EOD raw-daily shard."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime
from pathlib import Path

from thericher_v2.data.tiingo_daily_pilot import (
    acquire_tiingo_daily_shard,
    default_tiingo_daily_shard_dir,
)

CANDIDATE_UNION_SNAPSHOT = Path(
    "D:/market_data/us_equities/norgate_membership/canonical/"
    "sp500_current_past/snapshot=2026-07-18-norgate-sp500-membership-r1"
)
CANDIDATE_UNION_PATH = CANDIDATE_UNION_SNAPSHOT / "candidate_union.csv"
CANDIDATE_UNION_MANIFEST_PATH = CANDIDATE_UNION_SNAPSHOT / "manifest.json"
CANDIDATE_UNION_HASH = "sha256:bb116ebce77cbff16c92636566a5f4e0c64a63e4281bd777974bbd38b2ca6b58"
PREDECESSOR_SNAPSHOT = Path(
    "D:/market_data/us_equities/tiingo_standard_eod_pilot/canonical/"
    "snapshot=2026-07-18-tiingo-standard-eod-pilot-r1"
)
PREDECESSOR_DATASET_HASH = (
    "sha256:ecc5bf5c34ea1606fcea80ade658d4b95964033387149a7c273de7858652af56"
)
PREDECESSOR_MANIFEST_HASH = (
    "sha256:69493180e553af940810d3a07afe248d77febd2aee5105304dc777985ea7901f"
)
REQUESTED_START = date(2024, 7, 18)
REQUESTED_END = date(2026, 7, 17)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    retrieved_at = datetime.now(UTC)
    result = acquire_tiingo_daily_shard(
        candidate_union_path=CANDIDATE_UNION_PATH,
        candidate_union_manifest_path=CANDIDATE_UNION_MANIFEST_PATH,
        expected_candidate_union_hash=CANDIDATE_UNION_HASH,
        predecessor_snapshot_dir=PREDECESSOR_SNAPSHOT,
        expected_predecessor_dataset_hash=PREDECESSOR_DATASET_HASH,
        expected_predecessor_manifest_hash=PREDECESSOR_MANIFEST_HASH,
        env_path=Path(".env"),
        destination=args.destination or default_tiingo_daily_shard_dir(retrieved_at.date()),
        requested_start=REQUESTED_START,
        requested_end=REQUESTED_END,
        retrieved_at_utc=retrieved_at,
        repo_root=Path.cwd(),
    )
    print(
        json.dumps(
            {
                "snapshot_dir": str(result.snapshot_dir),
                "dataset_hash": result.dataset_hash,
                "manifest_hash": result.manifest_hash,
                "completed": result.completed,
                "stop_reason": result.stop_reason,
                "request_count": result.request_count,
                "available_count": result.available_count,
                "empty_count": result.empty_count,
                "unavailable_count": result.unavailable_count,
                "row_count": result.row_count,
                "free_percent": result.free_percent,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
