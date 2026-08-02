"""Run one source-safe active-build conformance taxonomy for the Norgate broad D1 panel."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.data.norgate_broad_active_build_conformance import (
    DEFAULT_NORGATE_BROAD_ACTIVE_BUILD_CONFORMANCE_ARTIFACT_ROOT,
    NORGATE_BROAD_ACTIVE_BUILD_CONFORMANCE_ID,
    build_norgate_broad_active_build_conformance_receipt,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def main(argv: Sequence[str] | None = None) -> None:
    """Run one host-only Data conformance probe and print only safe aggregates."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-label", required=True)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=DEFAULT_NORGATE_BROAD_ACTIVE_BUILD_CONFORMANCE_ARTIFACT_ROOT,
    )
    arguments = parser.parse_args(argv)
    result = build_norgate_broad_active_build_conformance_receipt(
        destination=arguments.artifact_root / arguments.run_label,
        artifact_root=arguments.artifact_root,
        repo_root=_REPOSITORY_ROOT,
    )
    payload = result.safe_payload()
    print(
        json.dumps(
            {
                "probe_id": NORGATE_BROAD_ACTIVE_BUILD_CONFORMANCE_ID,
                "receipt_sha256": result.receipt_sha256,
                "status": payload["status"],
                "reason": payload["reason"],
                "selected_symbol_count": payload["selected_symbol_count"],
                "common_session_count": payload["common_session_count"],
                "reference_bar_count": payload["reference_bar_count"],
                "observed_active_bar_count": payload["observed_active_bar_count"],
                "compared_symbol_count": payload["compared_symbol_count"],
                "exact_match_symbol_count": payload["exact_match_symbol_count"],
                "value_mismatch_symbol_count": payload["value_mismatch_symbol_count"],
                "symbol_absent_count": payload["symbol_absent_count"],
                "session_coverage_mismatch_count": payload["session_coverage_mismatch_count"],
                "nonrepeatable_symbol_count": payload["nonrepeatable_symbol_count"],
                "malformed_symbol_count": payload["malformed_symbol_count"],
                "source_unavailable_symbol_count": payload[
                    "source_unavailable_symbol_count"
                ],
                "active_response_sha256": payload["active_response_sha256"],
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
