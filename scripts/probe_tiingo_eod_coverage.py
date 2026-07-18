"""Run the one bounded Tiingo standard-EOD coverage probe."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime
from pathlib import Path

from thericher_v2.data.tiingo_coverage_probe import (
    default_tiingo_coverage_probe_dir,
    run_tiingo_eod_coverage_probe,
)

CANDIDATE_UNION_SNAPSHOT = Path(
    "D:/market_data/us_equities/norgate_membership/canonical/"
    "sp500_current_past/snapshot=2026-07-18-norgate-sp500-membership-r1"
)
CANDIDATE_UNION_PATH = CANDIDATE_UNION_SNAPSHOT / "candidate_union.csv"
CANDIDATE_UNION_MANIFEST_PATH = CANDIDATE_UNION_SNAPSHOT / "manifest.json"
CANDIDATE_UNION_HASH = "sha256:bb116ebce77cbff16c92636566a5f4e0c64a63e4281bd777974bbd38b2ca6b58"
REQUESTED_START = date(2024, 7, 18)
REQUESTED_END = date(2026, 7, 17)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    retrieved_at = datetime.now(UTC)
    result = run_tiingo_eod_coverage_probe(
        candidate_union_path=CANDIDATE_UNION_PATH,
        candidate_union_manifest_path=CANDIDATE_UNION_MANIFEST_PATH,
        expected_candidate_union_hash=CANDIDATE_UNION_HASH,
        env_path=Path(".env"),
        destination=args.destination or default_tiingo_coverage_probe_dir(retrieved_at.date()),
        requested_start=REQUESTED_START,
        requested_end=REQUESTED_END,
        retrieved_at_utc=retrieved_at,
        repo_root=Path.cwd(),
    )
    print(
        json.dumps(
            {
                "summary_path": str(result.summary_path),
                "summary_hash": result.summary_hash,
                "completed": result.completed,
                "stop_reason": result.stop_reason,
                "request_count": result.request_count,
                "available_count": result.available_count,
                "empty_count": result.empty_count,
                "unavailable_count": result.unavailable_count,
                "free_percent": result.free_percent,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
