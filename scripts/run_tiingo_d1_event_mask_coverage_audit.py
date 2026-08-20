"""Run the Tiingo D1 aggregate event-mask audit without external routes."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.data.tiingo_etf_daily import (
    DEFAULT_MARKET_DATA_ROOT,
    load_verified_tiingo_etf_d1_snapshot,
)
from thericher_v2.research.tiingo_d1_event_mask_coverage_audit import (
    run_tiingo_d1_event_mask_coverage_audit,
    validate_tiingo_d1_event_mask_coverage_audit,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")
_SNAPSHOT = Path(
    r"D:\market_data\us_equities\tiingo_etf_daily\canonical\snapshot=20260801T173121Z-tiingo-etf-d1-r1"
)
_DATASET_ID = "us_equities.tiingo_etf_daily.snapshot=20260801T173121Z-tiingo-etf-d1-r1"
_DATASET_HASH = "sha256:b47539a373bf2d625ad2380376808cf412219f6c5d932b66631bb3aa553683cf"
_ROTATION_RUN_LABEL = "20260820-r1"


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--rotation-run-label", default=_ROTATION_RUN_LABEL)
    parser.add_argument("--snapshot", type=Path, default=_SNAPSHOT)
    parser.add_argument("--market-data-root", type=Path, default=DEFAULT_MARKET_DATA_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--verify-only", action="store_true")
    arguments = parser.parse_args(argv)
    snapshot = load_verified_tiingo_etf_d1_snapshot(
        arguments.snapshot,
        dataset_id=_DATASET_ID,
        expected_dataset_hash=_DATASET_HASH,
        expected_manifest_hash=_manifest_hash(),
        market_data_root=arguments.market_data_root,
        repo_root=_REPOSITORY_ROOT,
    )
    if arguments.verify_only:
        receipt = validate_tiingo_d1_event_mask_coverage_audit(
            snapshot,
            artifact_root=arguments.artifact_root,
            rotation_artifact_root=arguments.artifact_root,
            rotation_run_label=arguments.rotation_run_label,
            run_label=arguments.run_label,
            repo_root=_REPOSITORY_ROOT,
        )
        print(
            json.dumps(
                {
                    "precommit_hash": receipt.precommit_hash,
                    "rotation_precommit_hash": receipt.rotation_precommit_hash,
                    "status": receipt.status,
                },
                ensure_ascii=True,
                sort_keys=True,
            )
        )
        return
    run = run_tiingo_d1_event_mask_coverage_audit(
        snapshot,
        artifact_root=arguments.artifact_root,
        rotation_artifact_root=arguments.artifact_root,
        rotation_run_label=arguments.rotation_run_label,
        run_label=arguments.run_label,
        repo_root=_REPOSITORY_ROOT,
    )
    print(run.summary_path.read_text(encoding="utf-8"), end="")


def _manifest_hash() -> str:
    """Pin the supplied immutable manifest identity; never derive it at runtime."""

    return "sha256:8b2e375a027e645ea2065ec61b252b7097da5e743155eb819129391125c072de"


if __name__ == "__main__":
    main()
