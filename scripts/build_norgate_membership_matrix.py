"""Build one host-only external Norgate S&P 500 membership matrix snapshot."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime
from pathlib import Path

from thericher_v2.data.norgate_membership import (
    build_norgate_sp500_membership_snapshot,
    default_norgate_sp500_membership_snapshot_dir,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requested-start", type=date.fromisoformat, required=True)
    parser.add_argument("--requested-end", type=date.fromisoformat, required=True)
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    retrieved_at = datetime.now(UTC)
    destination = args.destination or default_norgate_sp500_membership_snapshot_dir(
        retrieved_at.date()
    )
    result = build_norgate_sp500_membership_snapshot(
        destination=destination,
        requested_start=args.requested_start,
        requested_end=args.requested_end,
        retrieved_at_utc=retrieved_at,
        repo_root=Path.cwd(),
    )
    print(
        json.dumps(
            {
                "snapshot_dir": str(result.snapshot_dir),
                "dataset_id": result.dataset_id,
                "dataset_hash": result.dataset_hash,
                "manifest_hash": result.manifest_hash,
                "candidate_count": result.candidate_count,
                "membership_row_count": result.membership_row_count,
                "actual_start": result.actual_start.isoformat(),
                "actual_end": result.actual_end.isoformat(),
                "package_version": result.package_version,
                "free_percent": result.free_percent,
                "validation": "passed",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
