"""Materialize one offline, source-safe broad KIS D1 panel snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from thericher_v2.data.kis_paper_daily_broad_panel import (
    KIS_PAPER_DAILY_BROAD_CACHE_ROOT,
    KIS_PAPER_DAILY_BROAD_PANEL_EVIDENCE_ROOT,
    KIS_PAPER_DAILY_BROAD_PANEL_ROOT,
    materialize_kis_paper_daily_broad_panel,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-root", type=Path, default=KIS_PAPER_DAILY_BROAD_CACHE_ROOT)
    parser.add_argument("--panel-root", type=Path, default=KIS_PAPER_DAILY_BROAD_PANEL_ROOT)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=KIS_PAPER_DAILY_BROAD_PANEL_EVIDENCE_ROOT,
    )
    parser.add_argument("--repository-root", type=Path, default=Path(__file__).resolve().parents[1])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = materialize_kis_paper_daily_broad_panel(
        cache_root=args.cache_root,
        panel_root=args.panel_root,
        artifact_root=args.artifact_root,
        repo_root=args.repository_root,
    )
    print(
        json.dumps(
            {
                "status": "complete",
                "dataset_hash": result.panel.dataset_hash,
                "manifest_sha256": result.manifest_hash,
                "receipt_sha256": result.receipt_hash,
                "target_count": len(result.panel.target_keys),
                "covered_target_count": result.panel.covered_target_count,
                "zero_coverage_target_count": result.panel.zero_coverage_target_count,
                "quarantined_target_count": result.panel.quarantined_target_count,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
