"""Create the offline QQQ/SPY joint event-window campaign contract."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.kis_daily_joint_event_window_contract import (
    DEFAULT_MODEL_ARTIFACT_ROOT,
    KIS_DAILY_JOINT_EVENT_MODEL_EXECUTION_REVIEW_PENDING,
    KIS_DAILY_JOINT_EVENT_MODEL_EXECUTION_REVIEW_UNAVAILABLE,
    build_kis_daily_joint_event_window_contract,
    write_kis_daily_joint_event_window_contract,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SIDECAR_DIR = Path(
    "D:/market_data/us_equities/kis_paper_private/daily-corporate-actions/"
    "snapshot=2026-07-24-qqq-spy-tiingo-events-v1"
)
_SIDECAR_DATASET_HASH = "sha256:9a3e3b22c4a6045c4f26e6e77439cb3322cb61f8f6c04b422bb31412631d0de3"
_SIDECAR_MANIFEST_HASH = "sha256:c6f4b7113507d27577fb7ee66328db53d274e08d2470d3854b6f4e9aa46d171d"
_CATALOG_DATASET_HASH = "sha256:78b00556ddbc8bcfb0c4d1bb67e004e4a4c4ff035a8c348b2516b842fa397718"
_CATALOG_INDEX_HASH = "sha256:e0bb847994a97b1df1181b0013fabcb784d979c7c366f686940e563cb01ac660"
_SESSION_DATES_HASH = "sha256:a8743b8af3b9df84f9a68d51cd6b74a882809995d142b82602746af5329044cd"
_AUDIT_PATH = Path(
    "D:/thericher-v2/model-artifacts/research-contracts/"
    "snapshot=2026-07-24-qqq-spy-tiingo-events-v1-event-boundary-audit.json"
)
_AUDIT_HASH = "sha256:3d97b26b5e8e422cb2b4bcf262fbd1be887e44d7e43afdd9e2b5d689f805a46c"
_AUDIT_MASK_IDENTITY = "sha256:921c61b8abf822b0aee71b66b43c37875cb581e95bf7a1563b053880c087d429"
_AUDIT_PARTITION_IDENTITY = (
    "sha256:b82ed4022237929febde187651cb31e74740b311faa85c850967c617ac8dcfdb"
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_MODEL_ARTIFACT_ROOT)
    parser.add_argument("--destination", type=Path)
    parser.add_argument(
        "--model-execution-review",
        choices=(
            KIS_DAILY_JOINT_EVENT_MODEL_EXECUTION_REVIEW_PENDING,
            KIS_DAILY_JOINT_EVENT_MODEL_EXECUTION_REVIEW_UNAVAILABLE,
        ),
        default=KIS_DAILY_JOINT_EVENT_MODEL_EXECUTION_REVIEW_PENDING,
    )
    args = parser.parse_args(argv)

    # Keep imports free of Data-package side effects for metadata-only CLI paths.
    from thericher_v2.data.kis_daily_corporate_actions import (
        load_kis_daily_corporate_action_snapshot,
    )
    from thericher_v2.data.kis_daily_event_boundary_audit import (
        load_kis_daily_event_boundary_audit,
    )
    from thericher_v2.data.kis_paper_daily import load_kis_paper_private_daily_catalog

    artifact_root = Path(args.artifact_root)
    destination = args.destination or (
        artifact_root
        / "research-contracts"
        / "snapshot=2026-07-24-qqq-spy-tiingo-events-v1-joint-event-window-contract-v2.json"
    )
    catalog = load_kis_paper_private_daily_catalog(
        target_keys=("QQQ/NAS/MODP=0", "SPY/AMS/MODP=0"),
        expected_index_hash=_CATALOG_INDEX_HASH,
        expected_full_dataset_hash=_CATALOG_DATASET_HASH,
        repo_root=_REPO_ROOT,
    )
    sidecar = load_kis_daily_corporate_action_snapshot(
        _SIDECAR_DIR,
        catalog=catalog,
        expected_dataset_hash=_SIDECAR_DATASET_HASH,
        expected_manifest_hash=_SIDECAR_MANIFEST_HASH,
        repo_root=_REPO_ROOT,
    )
    audit = load_kis_daily_event_boundary_audit(
        _AUDIT_PATH,
        expected_artifact_sha256=_AUDIT_HASH,
        expected_catalog_dataset_hash=_CATALOG_DATASET_HASH,
        expected_catalog_index_hash=_CATALOG_INDEX_HASH,
        expected_sidecar_dataset_hash=_SIDECAR_DATASET_HASH,
        expected_sidecar_manifest_hash=_SIDECAR_MANIFEST_HASH,
        expected_session_dates_sha256=_SESSION_DATES_HASH,
        expected_mask_identity=_AUDIT_MASK_IDENTITY,
        expected_partition_identity=_AUDIT_PARTITION_IDENTITY,
    )
    contract = build_kis_daily_joint_event_window_contract(
        catalog=catalog,
        sidecar=sidecar,
        event_boundary_audit=audit,
        created_at_utc=datetime.now(UTC),
        repo_root=_REPO_ROOT,
        model_execution_review=args.model_execution_review,
    )
    artifact = write_kis_daily_joint_event_window_contract(
        destination=Path(destination),
        contract=contract,
        artifact_root=artifact_root,
        repo_root=_REPO_ROOT,
    )
    print(
        json.dumps(
            {
                "status": "candidate",
                "contract_identity": contract.contract_identity,
                "artifact_sha256": artifact.content_hash,
                "joint_event_session_count": len(contract.joint_event_sessions),
                "folds": [
                    {
                        "fold_id": fold.fold_id,
                        "development_eligible_decision_count": len(
                            fold.development_eligible_decision_indices
                        ),
                        "validation_eligible_decision_count": len(
                            fold.validation_eligible_decision_indices
                        ),
                    }
                    for fold in contract.folds
                ],
                "final_unused_tail_session_count": len(contract.sessions)
                - contract.final_unused_tail_start_index,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
