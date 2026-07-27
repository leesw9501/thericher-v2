"""Materialize one verified QQQ/SPY D1 fold window without model execution."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.kis_daily_joint_event_d1_materializer import (
    KisDailyJointEventD1Materializer,
    build_kis_daily_joint_event_d1_materializer,
    write_kis_daily_joint_event_d1_materializer_receipt,
)
from thericher_v2.kis_daily_joint_event_window_contract import (
    DEFAULT_MODEL_ARTIFACT_ROOT,
    KIS_DAILY_JOINT_EVENT_MODEL_EXECUTION_REVIEW_UNAVAILABLE,
    build_kis_daily_joint_event_window_contract,
    load_verified_kis_daily_joint_event_fold_input,
    load_verified_kis_daily_joint_event_window_contract,
    select_kis_daily_joint_event_fold_input,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_RESEARCH_CONTRACTS_DIRECTORY = "research-contracts"
_PARENT_ARTIFACT_NAME = (
    "snapshot=2026-07-24-qqq-spy-tiingo-events-v1-joint-event-window-contract-v2.json"
)
_PARENT_ARTIFACT_HASH = (
    "sha256:f908dd5570c795e94e92f54b3a9e243ee0c6cef641a557561bfc4db4983bb814"
)
_PARENT_CONTRACT_IDENTITY = (
    "sha256:d8c1a382ca8a16b87288ede8f31df22797574940e50f0c208d4e28dc2677c2a6"
)


@dataclass(frozen=True, slots=True)
class _FoldPin:
    artifact_name: str
    artifact_sha256: str
    fold_input_identity: str
    development_eligible_decision_count: int
    validation_eligible_decision_count: int


_FOLD_PINS = {
    "expanding-1": _FoldPin(
        artifact_name=(
            "snapshot=2026-07-24-qqq-spy-tiingo-events-v1-"
            "joint-event-window-fold-input-expanding-1-v1.json"
        ),
        artifact_sha256=(
            "sha256:a15c26b6ce8f9c8c1e204cd8300b46241e2e7d894548666c73d32d030f790f0b"
        ),
        fold_input_identity=(
            "sha256:b019c7e9a10eb2add48bbaa815c046a9b216ca9069c4ca8e4f836bc91085a1db"
        ),
        development_eligible_decision_count=2345,
        validation_eligible_decision_count=146,
    ),
    "expanding-2": _FoldPin(
        artifact_name=(
            "snapshot=2026-07-24-qqq-spy-tiingo-events-v1-"
            "joint-event-window-fold-input-expanding-2-v1.json"
        ),
        artifact_sha256=(
            "sha256:79723a4713b5a4751b6a62ddcd700b67542012bf3ff17a44958b7bd3d67c9305"
        ),
        fold_input_identity=(
            "sha256:6507570e49022133ff1055d49d610a6c32e80b92c0f881115f67d9e68e899f4e"
        ),
        development_eligible_decision_count=2511,
        validation_eligible_decision_count=128,
    ),
    "expanding-3": _FoldPin(
        artifact_name=(
            "snapshot=2026-07-24-qqq-spy-tiingo-events-v1-"
            "joint-event-window-fold-input-expanding-3-v1.json"
        ),
        artifact_sha256=(
            "sha256:40d6c9920a0edec12249f4b429c503b085b2e908466093496da8e0b6717128fc"
        ),
        fold_input_identity=(
            "sha256:1cf334306f1e2cc0e907d688d697c850aaf6ca0ef7ed2c42ee807f2c9633d11e"
        ),
        development_eligible_decision_count=2671,
        validation_eligible_decision_count=145,
    ),
}
_SIDECAR_DATASET_HASH = "sha256:9a3e3b22c4a6045c4f26e6e77439cb3322cb61f8f6c04b422bb31412631d0de3"
_SIDECAR_MANIFEST_HASH = "sha256:c6f4b7113507d27577fb7ee66328db53d274e08d2470d3854b6f4e9aa46d171d"
_CATALOG_DATASET_HASH = "sha256:78b00556ddbc8bcfb0c4d1bb67e004e4a4c4ff035a8c348b2516b842fa397718"
_CATALOG_INDEX_HASH = "sha256:e0bb847994a97b1df1181b0013fabcb784d979c7c366f686940e563cb01ac660"
_SESSION_DATES_HASH = "sha256:a8743b8af3b9df84f9a68d51cd6b74a882809995d142b82602746af5329044cd"
_AUDIT_HASH = "sha256:3d97b26b5e8e422cb2b4bcf262fbd1be887e44d7e43afdd9e2b5d689f805a46c"
_AUDIT_MASK_IDENTITY = "sha256:921c61b8abf822b0aee71b66b43c37875cb581e95bf7a1563b053880c087d429"
_AUDIT_PARTITION_IDENTITY = (
    "sha256:b82ed4022237929febde187651cb31e74740b311faa85c850967c617ac8dcfdb"
)
_DEFAULT_MARKET_DATA_ROOT = Path("D:/market_data")


def _fold_pin(fold_id: str) -> _FoldPin:
    if not isinstance(fold_id, str) or fold_id not in _FOLD_PINS:
        raise ValueError("joint D1 materializer fold id is invalid")
    return _FOLD_PINS[fold_id]


def _default_parent_artifact(artifact_root: Path) -> Path:
    return Path(artifact_root) / _RESEARCH_CONTRACTS_DIRECTORY / _PARENT_ARTIFACT_NAME


def _default_fold_artifact(artifact_root: Path, fold_id: str) -> Path:
    return Path(artifact_root) / _RESEARCH_CONTRACTS_DIRECTORY / _fold_pin(fold_id).artifact_name


def _sidecar_directory(market_data_root: Path) -> Path:
    return (
        market_data_root
        / "us_equities"
        / "kis_paper_private"
        / "daily-corporate-actions"
        / "snapshot=2026-07-24-qqq-spy-tiingo-events-v1"
    )


def _audit_artifact(artifact_root: Path) -> Path:
    return (
        artifact_root
        / "research-contracts"
        / "snapshot=2026-07-24-qqq-spy-tiingo-events-v1-event-boundary-audit.json"
    )


def load_pinned_kis_daily_joint_event_d1_materializer(
    *,
    artifact_root: Path,
    fold_id: str = "expanding-1",
    parent_artifact: Path | None = None,
    fold_artifact: Path | None = None,
    market_data_root: Path = _DEFAULT_MARKET_DATA_ROOT,
) -> KisDailyJointEventD1Materializer:
    """Reattest one explicitly pinned local QQQ/SPY fold without a network call."""

    # Keep import/help paths free of Data-package side effects.
    from thericher_v2.data.kis_daily_corporate_actions import (
        load_kis_daily_corporate_action_snapshot,
    )
    from thericher_v2.data.kis_daily_event_boundary_audit import (
        load_kis_daily_event_boundary_audit,
    )
    from thericher_v2.data.kis_paper_daily import load_kis_paper_private_daily_catalog

    pin = _fold_pin(fold_id)
    resolved_artifact_root = Path(artifact_root)
    resolved_parent_artifact = (
        Path(parent_artifact)
        if parent_artifact is not None
        else _default_parent_artifact(resolved_artifact_root)
    )
    resolved_fold_artifact = (
        Path(fold_artifact)
        if fold_artifact is not None
        else _default_fold_artifact(resolved_artifact_root, fold_id)
    )
    resolved_market_data_root = Path(market_data_root)
    catalog = load_kis_paper_private_daily_catalog(
        cache_root=resolved_market_data_root / "us_equities" / "kis_paper_private" / "daily",
        target_keys=("QQQ/NAS/MODP=0", "SPY/AMS/MODP=0"),
        expected_index_hash=_CATALOG_INDEX_HASH,
        expected_full_dataset_hash=_CATALOG_DATASET_HASH,
        repo_root=_REPO_ROOT,
    )
    sidecar = load_kis_daily_corporate_action_snapshot(
        _sidecar_directory(resolved_market_data_root),
        catalog=catalog,
        expected_dataset_hash=_SIDECAR_DATASET_HASH,
        expected_manifest_hash=_SIDECAR_MANIFEST_HASH,
        repo_root=_REPO_ROOT,
    )
    audit = load_kis_daily_event_boundary_audit(
        _audit_artifact(Path(artifact_root)),
        expected_artifact_sha256=_AUDIT_HASH,
        expected_catalog_dataset_hash=_CATALOG_DATASET_HASH,
        expected_catalog_index_hash=_CATALOG_INDEX_HASH,
        expected_sidecar_dataset_hash=_SIDECAR_DATASET_HASH,
        expected_sidecar_manifest_hash=_SIDECAR_MANIFEST_HASH,
        expected_session_dates_sha256=_SESSION_DATES_HASH,
        expected_mask_identity=_AUDIT_MASK_IDENTITY,
        expected_partition_identity=_AUDIT_PARTITION_IDENTITY,
    )
    rebuilt_parent = build_kis_daily_joint_event_window_contract(
        catalog=catalog,
        sidecar=sidecar,
        event_boundary_audit=audit,
        created_at_utc=datetime.now(UTC),
        repo_root=_REPO_ROOT,
        model_execution_review=KIS_DAILY_JOINT_EVENT_MODEL_EXECUTION_REVIEW_UNAVAILABLE,
    )
    verified_parent = load_verified_kis_daily_joint_event_window_contract(
        path=resolved_parent_artifact,
        expected_artifact_sha256=_PARENT_ARTIFACT_HASH,
        expected_contract_identity=_PARENT_CONTRACT_IDENTITY,
        rebuilt_contract=rebuilt_parent,
        artifact_root=artifact_root,
        repo_root=_REPO_ROOT,
    )
    runtime_fold = select_kis_daily_joint_event_fold_input(
        verified_parent,
        fold_id=fold_id,
    )
    if (
        runtime_fold.fold_id != fold_id
        or len(runtime_fold.development_eligible_decision_indices)
        != pin.development_eligible_decision_count
        or len(runtime_fold.validation_eligible_decision_indices)
        != pin.validation_eligible_decision_count
    ):
        raise ValueError("joint D1 materializer pinned fold geometry is invalid")
    verified_fold = load_verified_kis_daily_joint_event_fold_input(
        path=resolved_fold_artifact,
        expected_artifact_sha256=pin.artifact_sha256,
        expected_fold_input_identity=pin.fold_input_identity,
        expected_fold_input=runtime_fold,
        artifact_root=artifact_root,
        repo_root=_REPO_ROOT,
    )
    return build_kis_daily_joint_event_d1_materializer(
        fold_input_artifact=verified_fold,
        catalog=catalog,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_MODEL_ARTIFACT_ROOT)
    parser.add_argument("--market-data-root", type=Path, default=_DEFAULT_MARKET_DATA_ROOT)
    parser.add_argument("--fold-id", choices=tuple(_FOLD_PINS), default="expanding-1")
    parser.add_argument("--parent-artifact", type=Path)
    parser.add_argument("--fold-artifact", type=Path)
    parser.add_argument("--phase", choices=("development", "validation"), default="validation")
    parser.add_argument("--decision-index", type=int)
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args(argv)

    artifact_root = Path(args.artifact_root)
    materializer = load_pinned_kis_daily_joint_event_d1_materializer(
        artifact_root=artifact_root,
        fold_id=args.fold_id,
        parent_artifact=Path(args.parent_artifact) if args.parent_artifact else None,
        fold_artifact=Path(args.fold_artifact) if args.fold_artifact else None,
        market_data_root=Path(args.market_data_root),
    )
    phase = args.phase
    eligible = materializer.eligible_decision_indices(phase)
    decision_index = args.decision_index if args.decision_index is not None else eligible[0]
    destination = args.destination or (
        artifact_root
        / "research-contracts"
        / (
            "snapshot=2026-07-24-qqq-spy-tiingo-events-v1-"
            f"d1-materializer-{args.fold_id}-{phase}-first-v1.json"
        )
    )
    receipt = write_kis_daily_joint_event_d1_materializer_receipt(
        destination=Path(destination),
        materializer=materializer,
        phase=phase,
        decision_index=decision_index,
        artifact_root=artifact_root,
        repo_root=_REPO_ROOT,
    )
    window = materializer.materialize(phase=phase, decision_index=decision_index)
    print(
        json.dumps(
            {
                "status": "candidate",
                "fold_artifact_sha256": materializer.fold_artifact_sha256,
                "fold_input_identity": materializer.fold_input.fold_input_identity,
                "materializer_identity": materializer.materializer_identity,
                "receipt_sha256": receipt.content_hash,
                "phase": phase,
                "decision_index": window.decision_index,
                "feature_row_count": len(window.feature_rows),
                "predecessor_index": window.predecessor_index,
                "entry_index": window.target_references.entry_index,
                "exit_index": window.target_references.exit_index,
                "model_execution_review": materializer.fold_input.model_execution_review,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
