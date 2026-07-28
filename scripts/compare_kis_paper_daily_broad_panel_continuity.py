"""Compare two frozen broad KIS D1 panels without opening a provider route."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.data.kis_paper_daily_broad_panel import (
    KIS_PAPER_DAILY_BROAD_CACHE_ROOT,
    KIS_PAPER_DAILY_BROAD_PANEL_CONTINUITY_EVIDENCE_ROOT,
    KIS_PAPER_DAILY_BROAD_PANEL_ROOT,
    materialize_kis_paper_daily_broad_panel_continuity,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-manifest", type=Path, required=True)
    parser.add_argument("--candidate-manifest", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, default=KIS_PAPER_DAILY_BROAD_CACHE_ROOT)
    parser.add_argument("--panel-root", type=Path, default=KIS_PAPER_DAILY_BROAD_PANEL_ROOT)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=KIS_PAPER_DAILY_BROAD_PANEL_CONTINUITY_EVIDENCE_ROOT,
    )
    parser.add_argument("--repository-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)

    try:
        result = materialize_kis_paper_daily_broad_panel_continuity(
            baseline_manifest_path=args.baseline_manifest,
            candidate_manifest_path=args.candidate_manifest,
            cache_root=args.cache_root,
            panel_root=args.panel_root,
            artifact_root=args.artifact_root,
            repo_root=args.repository_root,
        )
    except (OSError, ValueError):
        _emit({"status": "unavailable"})
        return 2

    comparison = result.comparison
    _emit(
        {
            "status": comparison.status,
            "baseline_dataset_hash": comparison.baseline_dataset_hash,
            "candidate_dataset_hash": comparison.candidate_dataset_hash,
            "shared_target_count": comparison.shared_target_count,
            "shared_row_count": comparison.shared_row_count,
            "mismatched_target_count": comparison.mismatched_target_count,
            "mismatched_row_count": comparison.mismatched_row_count,
            "receipt_sha256": result.receipt_hash,
            "route_isolation": {
                "network_accessed": False,
                "kis_accessed": False,
                "account_endpoints_used": False,
                "order_endpoints_used": False,
                "live_endpoints_used": False,
            },
        }
    )
    return 0 if comparison.status == "equal" else 3


def _emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
