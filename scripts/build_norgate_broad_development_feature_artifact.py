"""Build the host-only Norgate broad development feature artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from thericher_v2.data.norgate_broad_development_artifact import (
    DEFAULT_MODEL_ARTIFACT_ROOT,
    build_norgate_broad_development_feature_artifact,
    default_norgate_broad_development_feature_artifact_dir,
)
from thericher_v2.data.norgate_trial_development_panel import DEFAULT_MARKET_DATA_ROOT

DEFAULT_PANEL_SNAPSHOT = (
    DEFAULT_MARKET_DATA_ROOT
    / "us_equities"
    / "norgate_trial_broad_development_panel"
    / "canonical"
    / "ohlcv_1d"
    / "snapshot=2026-07-18-norgate-trial-broad-d1-panel-r1"
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel-snapshot", type=Path, default=DEFAULT_PANEL_SNAPSHOT)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_MODEL_ARTIFACT_ROOT)
    parser.add_argument("--market-data-root", type=Path, default=DEFAULT_MARKET_DATA_ROOT)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = build_norgate_broad_development_feature_artifact(
        args.panel_snapshot,
        artifact_root=args.artifact_root,
        market_data_root=args.market_data_root,
        repo_root=args.repo_root,
    )
    print(
        json.dumps(
            {
                "artifact_dir": str(result.artifact_dir),
                "expected_artifact_dir": str(
                    default_norgate_broad_development_feature_artifact_dir(
                        args.panel_snapshot,
                        artifact_root=args.artifact_root,
                    )
                ),
                "artifact_hash": result.artifact_hash,
                "contract_hash": result.contract_hash,
                "manifest_hash": result.manifest_hash,
                "parent_dataset_hash": result.parent_dataset_hash,
                "parent_manifest_hash": result.parent_manifest_hash,
                "row_counts": result.contract["row_counts"],
                "scope": result.contract["scope"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
