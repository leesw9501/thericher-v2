"""Create a source-safe, offline receipt for one Norgate membership snapshot."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.data.norgate_membership_reattest import (
    reattest_norgate_sp500_membership_snapshot,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    parser.add_argument("--market-data-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--repo-root", type=Path, default=_REPOSITORY_ROOT)
    args = parser.parse_args(argv)

    try:
        result = reattest_norgate_sp500_membership_snapshot(
            snapshot_dir=args.snapshot_dir,
            market_data_root=args.market_data_root,
            artifact_root=args.artifact_root,
            repo_root=args.repo_root,
            attempt_id=str(args.attempt_id),
            created_at_utc=datetime.now(UTC),
        )
    except (FileExistsError, ValueError, OSError):
        print(json.dumps({"status": "input_unavailable"}, sort_keys=True))
        return
    payload = {"status": result.status}
    if result.status == "reattested":
        payload["receipt_sha256"] = result.receipt_sha256
        payload["source_identity_sha256"] = result.source_identity_sha256
    print(
        json.dumps(payload, sort_keys=True)
    )


if __name__ == "__main__":
    main()
