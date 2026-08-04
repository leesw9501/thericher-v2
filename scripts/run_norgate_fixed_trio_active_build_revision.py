"""Compare one active local build to an explicitly supplied fixed-trio D1 snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from thericher_v2.data.norgate_active_build_revision import (  # noqa: E402
    DEFAULT_NORGATE_ACTIVE_BUILD_REVISION_ARTIFACT_ROOT,
    NORGATE_ACTIVE_BUILD_REVISION_PROBE_ID,
    build_norgate_active_build_revision_receipt,
    norgate_fixed_trio_d1_reference_from_verified_snapshot,
)
from thericher_v2.data.norgate_trial_raw_d1 import (  # noqa: E402
    DEFAULT_MARKET_DATA_ROOT,
    verify_norgate_trial_raw_d1_snapshot,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Write one aggregate-only receipt for the supplied immutable snapshot."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    parser.add_argument("--run-label", required=True)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=DEFAULT_NORGATE_ACTIVE_BUILD_REVISION_ARTIFACT_ROOT,
    )
    parser.add_argument("--market-data-root", type=Path, default=DEFAULT_MARKET_DATA_ROOT)
    arguments = parser.parse_args(argv)

    source = verify_norgate_trial_raw_d1_snapshot(
        arguments.snapshot_dir,
        market_data_root=arguments.market_data_root,
        repo_root=REPOSITORY_ROOT,
    )
    result = build_norgate_active_build_revision_receipt(
        destination=arguments.artifact_root / f"revision-{arguments.run_label}",
        artifact_root=arguments.artifact_root,
        repo_root=REPOSITORY_ROOT,
        reference=norgate_fixed_trio_d1_reference_from_verified_snapshot(source),
    )
    payload = result.safe_payload()
    print(
        json.dumps(
            {
                "probe_id": NORGATE_ACTIVE_BUILD_REVISION_PROBE_ID,
                "receipt_sha256": result.receipt_sha256,
                "status": payload["status"],
                "reason": payload["reason"],
                "reference_dataset_hash": payload["reference_dataset_hash"],
                "reference_manifest_hash": payload["reference_manifest_hash"],
                "reference_bar_count": payload["reference_bar_count"],
                "active_bar_count": payload["active_bar_count"],
                "divergent_bar_count": payload["divergent_bar_count"],
                "active_response_sha256": payload["active_response_sha256"],
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
