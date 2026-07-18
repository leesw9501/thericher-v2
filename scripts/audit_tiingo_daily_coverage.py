"""Run one offline, aggregate-only Tiingo daily coverage audit."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.data.tiingo_coverage_audit import (
    TiingoDailyCoverageAuditInputs,
    default_tiingo_daily_coverage_audit_dir,
    run_tiingo_daily_coverage_audit,
)

R1_SNAPSHOT = Path(
    "D:/market_data/us_equities/tiingo_standard_eod_pilot/canonical/"
    "snapshot=2026-07-18-tiingo-standard-eod-pilot-r1"
)
R1_DATASET_HASH = "sha256:ecc5bf5c34ea1606fcea80ade658d4b95964033387149a7c273de7858652af56"
R1_MANIFEST_HASH = "sha256:69493180e553af940810d3a07afe248d77febd2aee5105304dc777985ea7901f"
R2_SNAPSHOT = Path(
    "D:/market_data/us_equities/tiingo_standard_eod_pilot/canonical/"
    "snapshot=2026-07-18-tiingo-standard-eod-pilot-r2"
)
R2_DATASET_HASH = "sha256:6decf91002aa0029d7cda1cb0b5131d1f440129624c84db2cca0d98579e4ccc1"
R2_MANIFEST_HASH = "sha256:76234da1951bccb54d74ab0f07358d138e861331914405cae6b91538f25ddb9e"
CANDIDATE_UNION_HASH = "sha256:bb116ebce77cbff16c92636566a5f4e0c64a63e4281bd777974bbd38b2ca6b58"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    audited_at = datetime.now(UTC)
    result = run_tiingo_daily_coverage_audit(
        inputs=TiingoDailyCoverageAuditInputs(
            r1_snapshot_dir=R1_SNAPSHOT,
            r1_dataset_hash=R1_DATASET_HASH,
            r1_manifest_hash=R1_MANIFEST_HASH,
            r2_snapshot_dir=R2_SNAPSHOT,
            r2_dataset_hash=R2_DATASET_HASH,
            r2_manifest_hash=R2_MANIFEST_HASH,
            candidate_union_hash=CANDIDATE_UNION_HASH,
        ),
        destination=args.destination or default_tiingo_daily_coverage_audit_dir(audited_at.date()),
        audited_at_utc=audited_at,
        repo_root=Path.cwd(),
    )
    print(
        json.dumps(
            {
                "summary_path": str(result.summary_path),
                "summary_hash": result.summary_hash,
                "r1_common_session_count": result.r1_common_session_count,
                "r2_common_session_count": result.r2_common_session_count,
                "combined_common_session_count": result.combined_common_session_count,
                "existing_reference_window_candidate_count": (
                    result.existing_reference_window_candidate_count
                ),
                "free_percent": result.free_percent,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
