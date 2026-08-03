"""First bounded supervised target contract for the profiled QQQ/SPY MTF path.

The module deliberately owns only one fixed first-30-pair materialization.  It
opens retained D:-resident forward snapshots only after the existing readiness
receipt has been reattested, and never writes target-bearing values to model
artifacts or the repository.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Final, Literal

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.data.kis_mtf_profiled_prospective_observer import (
    KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_TARGET_KEYS,
    KisMtfProfiledForwardOutcomeSnapshotCatalog,
)

from .artifact_paths import ensure_external_artifact_directory, reject_repo_artifact_path
from .profiled_mtf_forward_campaign_readiness import (
    PROFILED_MTF_FORWARD_CAMPAIGN_REQUIRED_PAIR_COUNT,
    PROFILED_MTF_FORWARD_CAMPAIGN_TEMPORAL_SPLIT,
    ProfiledMtfForwardCampaignReadinessReceipt,
    profiled_mtf_forward_campaign_inventory_sha256,
    reattest_profiled_mtf_forward_campaign_readiness,
)

PROFILED_MTF_FORWARD_SUPERVISED_DATASET_ID: Final = (
    "profiled-mtf-forward-supervised-dataset-contract-v1"
)
PROFILED_MTF_FORWARD_SUPERVISED_DATASET_RAW_DIRECTORY: Final = (
    "profiled-mtf-forward-supervised-dataset-v1"
)
PROFILED_MTF_FORWARD_SUPERVISED_DATASET_PAIR_COUNT: Final = (
    PROFILED_MTF_FORWARD_CAMPAIGN_REQUIRED_PAIR_COUNT
)
PROFILED_MTF_FORWARD_SUPERVISED_DATASET_TEMPORAL_SPLIT: Final = (
    PROFILED_MTF_FORWARD_CAMPAIGN_TEMPORAL_SPLIT
)
_ATTEMPT_ID_PATTERN: Final = re.compile(r"^[A-Za-z0-9._-]{1,80}$", re.ASCII)

DatasetStatus = Literal["input_unavailable", "materialized"]
DatasetSplit = Literal["train", "purge", "validation"]


@dataclass(frozen=True, slots=True)
class ProfiledMtfForwardSupervisedDatasetPolicy:
    """Frozen target, ordering, and pair-level split semantics before opening targets."""

    readiness_receipt_sha256: str
    readiness_policy_sha256: str
    readiness_sha256: str
    forward_outcome_contract_sha256: str
    code_revision_sha256: str
    policy_sha256: str

    def __post_init__(self) -> None:
        if (
            not all(
                _is_sha256(value)
                for value in (
                    self.readiness_receipt_sha256,
                    self.readiness_policy_sha256,
                    self.readiness_sha256,
                    self.forward_outcome_contract_sha256,
                    self.code_revision_sha256,
                    self.policy_sha256,
                )
            )
            or self.policy_sha256 != _sha256_json(_policy_unsigned_payload(self))
        ):
            raise ValueError("profiled MTF supervised dataset policy is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            **_policy_unsigned_payload(self),
            "policy_sha256": self.policy_sha256,
        }


@dataclass(frozen=True, slots=True)
class ProfiledMtfForwardSupervisedTargetRow:
    """One D:-only target row linked to its immutable input snapshot."""

    pair_index: int
    leg_index: int
    split: DatasetSplit
    session_key_sha256: str
    witness_sha256: str
    raw_snapshot_sha256: str
    input_end: datetime
    outcome_end: datetime
    target_log_return: Decimal = field(repr=False)

    def __post_init__(self) -> None:
        if (
            self.pair_index not in range(PROFILED_MTF_FORWARD_SUPERVISED_DATASET_PAIR_COUNT)
            or self.leg_index not in range(len(KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_TARGET_KEYS))
            or self.split not in {"train", "purge", "validation"}
            or not all(
                _is_sha256(value)
                for value in (
                    self.session_key_sha256,
                    self.witness_sha256,
                    self.raw_snapshot_sha256,
                )
            )
            or self.input_end.tzinfo is None
            or self.outcome_end.tzinfo is None
            or self.input_end >= self.outcome_end
            or not self.target_log_return.is_finite()
        ):
            raise ValueError("profiled MTF supervised target row is invalid")

    def d_only_payload(self) -> dict[str, object]:
        return {
            "pair_index": self.pair_index,
            "leg_index": self.leg_index,
            "target_key": KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_TARGET_KEYS[self.leg_index],
            "split": self.split,
            "session_key_sha256": self.session_key_sha256,
            "witness_sha256": self.witness_sha256,
            "raw_snapshot_sha256": self.raw_snapshot_sha256,
            "input_end": self.input_end.isoformat(),
            "outcome_end": self.outcome_end.isoformat(),
            "target_log_return": str(self.target_log_return),
        }


@dataclass(frozen=True, slots=True)
class ProfiledMtfForwardSupervisedDatasetResult:
    """Source-safe result; the materialization path/value rows stay private to D:."""

    policy_sha256: str
    readiness_receipt_sha256: str
    source_inventory_sha256: str
    source_manifest_sha256: str
    status: DatasetStatus
    selected_pair_count: int
    selected_pair_manifest_sha256: str
    row_count: int
    dataset_contract_sha256: str | None
    dataset_materialization_sha256: str | None
    result_sha256: str
    dataset_path: Path | None = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        materialized = self.status == "materialized"
        expected_selected = (
            PROFILED_MTF_FORWARD_SUPERVISED_DATASET_PAIR_COUNT if materialized else 0
        )
        expected_rows = expected_selected * len(KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_TARGET_KEYS)
        if (
            not all(
                _is_sha256(value)
                for value in (
                    self.policy_sha256,
                    self.readiness_receipt_sha256,
                    self.source_inventory_sha256,
                    self.source_manifest_sha256,
                    self.selected_pair_manifest_sha256,
                    self.result_sha256,
                )
            )
            or self.status not in {"input_unavailable", "materialized"}
            or self.selected_pair_count != expected_selected
            or self.row_count != expected_rows
            or (self.dataset_contract_sha256 is not None) != materialized
            or (self.dataset_materialization_sha256 is not None) != materialized
            or (self.dataset_path is not None) != materialized
            or (
                materialized
                and not all(
                    _is_sha256(value)
                    for value in (
                        self.dataset_contract_sha256,
                        self.dataset_materialization_sha256,
                    )
                )
            )
            or self.result_sha256 != _result_sha256(self)
        ):
            raise ValueError("profiled MTF supervised dataset result is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "dataset_id": PROFILED_MTF_FORWARD_SUPERVISED_DATASET_ID,
            "policy_sha256": self.policy_sha256,
            "readiness_receipt_sha256": self.readiness_receipt_sha256,
            "source_inventory_sha256": self.source_inventory_sha256,
            "source_manifest_sha256": self.source_manifest_sha256,
            "status": self.status,
            "selected_pair_count": self.selected_pair_count,
            "selected_pair_manifest_sha256": self.selected_pair_manifest_sha256,
            "row_count": self.row_count,
            "dataset_contract_sha256": self.dataset_contract_sha256,
            "dataset_materialization_sha256": self.dataset_materialization_sha256,
            "scope": _result_scope(),
            "result_sha256": self.result_sha256,
        }


@dataclass(frozen=True, slots=True)
class ProfiledMtfForwardSupervisedDatasetReceipt:
    """One immutable external receipt containing hashes and counts only."""

    policy: ProfiledMtfForwardSupervisedDatasetPolicy = field(repr=False)
    result: ProfiledMtfForwardSupervisedDatasetResult = field(repr=False)
    receipt_path: Path
    receipt_sha256: str

    def __post_init__(self) -> None:
        if (
            self.receipt_path.name != "dataset-receipt.json"
            or self.receipt_path.is_symlink()
            or not _is_sha256(self.receipt_sha256)
            or self.result.policy_sha256 != self.policy.policy_sha256
        ):
            raise ValueError("profiled MTF supervised dataset receipt is invalid")


@dataclass(frozen=True, slots=True)
class ProfiledMtfForwardSupervisedDatasetMaterialization:
    """One verified in-memory view of the D:-only first-30-pair target rows."""

    receipt: ProfiledMtfForwardSupervisedDatasetReceipt = field(repr=False)
    catalog: KisMtfProfiledForwardOutcomeSnapshotCatalog = field(repr=False)
    snapshots: tuple[object, ...] = field(repr=False)
    rows: tuple[ProfiledMtfForwardSupervisedTargetRow, ...] = field(repr=False)
    dataset_path: Path

    def __post_init__(self) -> None:
        snapshots = tuple(_require_snapshot(snapshot) for snapshot in self.snapshots)
        rows = tuple(self.rows)
        result = self.receipt.result
        if (
            result.status != "materialized"
            or self.catalog.contract.contract_sha256
            != self.receipt.policy.forward_outcome_contract_sha256
            or len(snapshots) != PROFILED_MTF_FORWARD_SUPERVISED_DATASET_PAIR_COUNT
            or rows != _target_rows(snapshots)
            or self.dataset_path != result.dataset_path
            or self.dataset_path.is_symlink()
        ):
            raise ValueError("profiled MTF supervised dataset materialization is invalid")
        object.__setattr__(self, "snapshots", snapshots)
        object.__setattr__(self, "rows", rows)


def freeze_profiled_mtf_forward_supervised_dataset_policy(
    receipt: ProfiledMtfForwardCampaignReadinessReceipt,
    *,
    code_revision_sha256: str,
) -> ProfiledMtfForwardSupervisedDatasetPolicy:
    """Freeze target/split semantics against one verified readiness receipt."""

    _require_sha256(code_revision_sha256, "code_revision_sha256")
    return ProfiledMtfForwardSupervisedDatasetPolicy(
        readiness_receipt_sha256=receipt.receipt_sha256,
        readiness_policy_sha256=receipt.policy.policy_sha256,
        readiness_sha256=receipt.readiness.readiness_sha256,
        forward_outcome_contract_sha256=receipt.readiness.forward_outcome_contract_sha256,
        code_revision_sha256=code_revision_sha256,
        policy_sha256=_sha256_json(
            _policy_unsigned_payload_from_fields(
                readiness_receipt_sha256=receipt.receipt_sha256,
                readiness_policy_sha256=receipt.policy.policy_sha256,
                readiness_sha256=receipt.readiness.readiness_sha256,
                forward_outcome_contract_sha256=(
                    receipt.readiness.forward_outcome_contract_sha256
                ),
                code_revision_sha256=code_revision_sha256,
            )
        ),
    )


def materialize_profiled_mtf_forward_supervised_dataset(
    policy: ProfiledMtfForwardSupervisedDatasetPolicy,
    *,
    receipt: ProfiledMtfForwardCampaignReadinessReceipt,
    catalog: KisMtfProfiledForwardOutcomeSnapshotCatalog,
    market_data_root: Path | str,
    repo_root: Path | str,
) -> ProfiledMtfForwardSupervisedDatasetResult:
    """Reattest readiness, then write target rows only for the fixed first 30 pairs."""

    _reattest_receipt_and_catalog(policy=policy, receipt=receipt, catalog=catalog)
    if receipt.readiness.status != "ready_for_private_campaign_freeze":
        return _input_unavailable_result(policy=policy, receipt=receipt)
    selected = catalog.snapshots[:PROFILED_MTF_FORWARD_SUPERVISED_DATASET_PAIR_COUNT]
    if len(selected) != PROFILED_MTF_FORWARD_SUPERVISED_DATASET_PAIR_COUNT:
        raise ValueError("ready forward inventory has fewer snapshots than required")
    selected_manifest_sha256 = _selected_pair_manifest_sha256(selected)
    dataset_contract_sha256 = _dataset_contract_sha256(
        policy_sha256=policy.policy_sha256,
        selected_pair_manifest_sha256=selected_manifest_sha256,
        source_inventory_sha256=receipt.readiness.source_inventory_sha256,
    )
    rows = _target_rows(selected)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": PROFILED_MTF_FORWARD_SUPERVISED_DATASET_ID,
        "dataset_contract_sha256": dataset_contract_sha256,
        "policy_sha256": policy.policy_sha256,
        "readiness_receipt_sha256": receipt.receipt_sha256,
        "source_inventory_sha256": receipt.readiness.source_inventory_sha256,
        "source_manifest_sha256": receipt.readiness.target_ready_manifest_sha256,
        "selected_pair_manifest_sha256": selected_manifest_sha256,
        "pair_count": len(selected),
        "row_count": len(rows),
        "rows": [row.d_only_payload() for row in rows],
    }
    materialization_sha256 = _sha256_json(payload)
    directory = ensure_external_artifact_directory(
        Path(market_data_root),
        Path(repo_root),
        "us_equities",
        "kis_paper_private",
        PROFILED_MTF_FORWARD_SUPERVISED_DATASET_RAW_DIRECTORY,
        "c",
        _storage_key(dataset_contract_sha256),
    )
    destination = directory / "supervised-dataset.json"
    _write_or_verify_json(destination, payload)
    return _materialized_result(
        policy=policy,
        receipt=receipt,
        selected_pair_manifest_sha256=selected_manifest_sha256,
        dataset_contract_sha256=dataset_contract_sha256,
        dataset_materialization_sha256=materialization_sha256,
        dataset_path=destination,
        row_count=len(rows),
    )


def write_profiled_mtf_forward_supervised_dataset_receipt(
    result: ProfiledMtfForwardSupervisedDatasetResult,
    *,
    policy: ProfiledMtfForwardSupervisedDatasetPolicy,
    artifact_root: Path | str,
    repo_root: Path | str,
    attempt_id: str,
) -> ProfiledMtfForwardSupervisedDatasetReceipt:
    """Persist a source-safe result outside Git and outside D:-resident target data."""

    _require_attempt_id(attempt_id)
    if result.policy_sha256 != policy.policy_sha256:
        raise ValueError("supervised dataset result policy changed")
    directory = ensure_external_artifact_directory(
        Path(artifact_root),
        Path(repo_root),
        "research",
        PROFILED_MTF_FORWARD_SUPERVISED_DATASET_ID,
        attempt_id,
    )
    unsigned_payload = {
        "schema_version": SCHEMA_VERSION,
        "dataset_id": PROFILED_MTF_FORWARD_SUPERVISED_DATASET_ID,
        "attempt_id": attempt_id,
        "policy": policy.safe_payload(),
        "result": result.safe_payload(),
        "artifact_policy": _artifact_policy(),
    }
    payload = {**unsigned_payload, "receipt_sha256": _sha256_json(unsigned_payload)}
    receipt_path = directory / "dataset-receipt.json"
    recorded = _write_or_verify_json(receipt_path, payload)
    return ProfiledMtfForwardSupervisedDatasetReceipt(
        policy=policy,
        result=result,
        receipt_path=receipt_path,
        receipt_sha256=_required_sha256_payload(recorded, "receipt_sha256"),
    )


def load_profiled_mtf_forward_supervised_dataset_receipt(
    receipt_path: Path | str,
    *,
    market_data_root: Path | str,
    repo_root: Path | str,
) -> ProfiledMtfForwardSupervisedDatasetReceipt:
    """Load one external source-safe receipt without creating an artifact path."""

    path = Path(receipt_path)
    reject_repo_artifact_path(path, Path(repo_root))
    if path.is_symlink() or not path.is_file():
        raise ValueError("supervised dataset receipt is missing or invalid")
    try:
        encoded = path.read_bytes()
        payload = json.loads(encoded)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("supervised dataset receipt is malformed") from error
    if not isinstance(payload, dict) or encoded != _canonical_json(payload):
        raise ValueError("supervised dataset receipt is malformed")
    if (
        set(payload)
        != {
            "schema_version",
            "dataset_id",
            "attempt_id",
            "policy",
            "result",
            "artifact_policy",
            "receipt_sha256",
        }
        or payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("dataset_id") != PROFILED_MTF_FORWARD_SUPERVISED_DATASET_ID
        or not isinstance(payload.get("attempt_id"), str)
        or payload.get("artifact_policy") != _artifact_policy()
    ):
        raise ValueError("supervised dataset receipt is malformed")
    _require_attempt_id(payload["attempt_id"])
    receipt_sha256 = _required_sha256_payload(payload, "receipt_sha256")
    unsigned = dict(payload)
    unsigned.pop("receipt_sha256")
    if receipt_sha256 != _sha256_json(unsigned):
        raise ValueError("supervised dataset receipt checksum is invalid")
    policy = _policy_from_safe_payload(_required_mapping(payload, "policy"))
    result = _result_from_safe_payload(
        _required_mapping(payload, "result"),
        market_data_root=Path(market_data_root),
        repo_root=Path(repo_root),
    )
    return ProfiledMtfForwardSupervisedDatasetReceipt(
        policy=policy,
        result=result,
        receipt_path=path,
        receipt_sha256=receipt_sha256,
    )


def load_profiled_mtf_forward_supervised_dataset_materialization(
    receipt: ProfiledMtfForwardSupervisedDatasetReceipt,
    *,
    catalog: KisMtfProfiledForwardOutcomeSnapshotCatalog,
    repo_root: Path | str,
) -> ProfiledMtfForwardSupervisedDatasetMaterialization | None:
    """Reattest and open the exact D:-only rows without regenerating them."""

    result = receipt.result
    _reattest_dataset_receipt_and_catalog(receipt=receipt, catalog=catalog)
    if result.status == "input_unavailable":
        return None
    if result.dataset_path is None or result.dataset_contract_sha256 is None:
        raise ValueError("supervised dataset materialization is unavailable")
    reject_repo_artifact_path(result.dataset_path, Path(repo_root))
    if not result.dataset_path.exists() or result.dataset_path.is_symlink():
        raise ValueError("supervised dataset materialization is unavailable")
    try:
        encoded = result.dataset_path.read_bytes()
        payload = json.loads(encoded)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("supervised dataset materialization is malformed") from error
    selected = catalog.snapshots[:PROFILED_MTF_FORWARD_SUPERVISED_DATASET_PAIR_COUNT]
    expected_rows = _target_rows(selected)
    expected_payload = _dataset_payload(
        policy=receipt.policy,
        result=result,
        rows=expected_rows,
    )
    if (
        not isinstance(payload, dict)
        or encoded != _canonical_json(payload)
        or encoded != _canonical_json(expected_payload)
        or _sha256_json(payload) != result.dataset_materialization_sha256
    ):
        raise ValueError("supervised dataset materialization changed")
    return ProfiledMtfForwardSupervisedDatasetMaterialization(
        receipt=receipt,
        catalog=catalog,
        snapshots=selected,
        rows=expected_rows,
        dataset_path=result.dataset_path,
    )


def _reattest_receipt_and_catalog(
    *,
    policy: ProfiledMtfForwardSupervisedDatasetPolicy,
    receipt: ProfiledMtfForwardCampaignReadinessReceipt,
    catalog: KisMtfProfiledForwardOutcomeSnapshotCatalog,
) -> None:
    if (
        receipt.receipt_sha256 != policy.readiness_receipt_sha256
        or receipt.policy.policy_sha256 != policy.readiness_policy_sha256
        or receipt.readiness.readiness_sha256 != policy.readiness_sha256
        or receipt.readiness.forward_outcome_contract_sha256
        != policy.forward_outcome_contract_sha256
        or catalog.contract.contract_sha256 != policy.forward_outcome_contract_sha256
    ):
        raise ValueError("supervised dataset readiness receipt is stale or mismatched")
    reattest_profiled_mtf_forward_campaign_readiness(
        receipt.readiness,
        policy=receipt.policy,
        inventory=catalog.inventory,
    )


def _reattest_dataset_receipt_and_catalog(
    *,
    receipt: ProfiledMtfForwardSupervisedDatasetReceipt,
    catalog: KisMtfProfiledForwardOutcomeSnapshotCatalog,
) -> None:
    result = receipt.result
    policy = receipt.policy
    if (
        catalog.contract.contract_sha256 != policy.forward_outcome_contract_sha256
        or result.policy_sha256 != policy.policy_sha256
        or result.readiness_receipt_sha256 != policy.readiness_receipt_sha256
        or result.source_inventory_sha256 != _inventory_sha256(catalog)
        or result.source_manifest_sha256 != catalog.inventory.target_ready_manifest_sha256
    ):
        raise ValueError("supervised dataset receipt is stale or mismatched")
    if result.status == "materialized":
        selected = catalog.snapshots[:PROFILED_MTF_FORWARD_SUPERVISED_DATASET_PAIR_COUNT]
        if (
            len(selected) != PROFILED_MTF_FORWARD_SUPERVISED_DATASET_PAIR_COUNT
            or result.selected_pair_manifest_sha256 != _selected_pair_manifest_sha256(selected)
            or result.dataset_contract_sha256
            != _dataset_contract_sha256(
                policy_sha256=policy.policy_sha256,
                selected_pair_manifest_sha256=result.selected_pair_manifest_sha256,
                source_inventory_sha256=result.source_inventory_sha256,
            )
        ):
            raise ValueError("supervised dataset receipt is stale or mismatched")


def _dataset_payload(
    *,
    policy: ProfiledMtfForwardSupervisedDatasetPolicy,
    result: ProfiledMtfForwardSupervisedDatasetResult,
    rows: tuple[ProfiledMtfForwardSupervisedTargetRow, ...],
) -> dict[str, object]:
    if result.dataset_contract_sha256 is None:
        raise ValueError("supervised dataset contract is unavailable")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": PROFILED_MTF_FORWARD_SUPERVISED_DATASET_ID,
        "dataset_contract_sha256": result.dataset_contract_sha256,
        "policy_sha256": policy.policy_sha256,
        "readiness_receipt_sha256": result.readiness_receipt_sha256,
        "source_inventory_sha256": result.source_inventory_sha256,
        "source_manifest_sha256": result.source_manifest_sha256,
        "selected_pair_manifest_sha256": result.selected_pair_manifest_sha256,
        "pair_count": result.selected_pair_count,
        "row_count": len(rows),
        "rows": [row.d_only_payload() for row in rows],
    }


def _target_rows(
    snapshots: tuple[object, ...],
) -> tuple[ProfiledMtfForwardSupervisedTargetRow, ...]:
    rows: list[ProfiledMtfForwardSupervisedTargetRow] = []
    for pair_index, raw_snapshot in enumerate(snapshots):
        snapshot = _require_snapshot(raw_snapshot)
        split = _split_for_pair(pair_index)
        for leg_index, (inputs, outcomes) in enumerate(
            zip(snapshot.input_prefixes, snapshot.outcome_windows, strict=True)
        ):
            rows.append(
                ProfiledMtfForwardSupervisedTargetRow(
                    pair_index=pair_index,
                    leg_index=leg_index,
                    split=split,
                    session_key_sha256=snapshot.session_key_sha256,
                    witness_sha256=snapshot.witness_sha256,
                    raw_snapshot_sha256=snapshot.raw_snapshot_sha256,
                    input_end=inputs[-1].end_ts,
                    outcome_end=outcomes[-1].end_ts,
                    target_log_return=_log_return(inputs[-1].close, outcomes[-1].close),
                )
            )
    return tuple(rows)


def _require_snapshot(raw_snapshot: object):
    from thericher_v2.data.kis_mtf_profiled_prospective_observer import (
        KisMtfProfiledForwardOutcomeSnapshot,
    )

    if not isinstance(raw_snapshot, KisMtfProfiledForwardOutcomeSnapshot):
        raise ValueError("supervised dataset snapshot is invalid")
    return raw_snapshot


def _split_for_pair(pair_index: int) -> DatasetSplit:
    train_count, purge_count, _ = PROFILED_MTF_FORWARD_SUPERVISED_DATASET_TEMPORAL_SPLIT
    if pair_index < train_count:
        return "train"
    if pair_index < train_count + purge_count:
        return "purge"
    return "validation"


def _log_return(input_close: Decimal, outcome_close: Decimal) -> Decimal:
    if input_close <= 0 or outcome_close <= 0:
        raise ValueError("supervised target close must be positive")
    with localcontext() as context:
        context.prec = 34
        return (outcome_close / input_close).ln()


def _selected_pair_manifest_sha256(snapshots: tuple[object, ...]) -> str:
    selected = tuple(_require_snapshot(snapshot) for snapshot in snapshots)
    return _sha256_json(
        {
            "selected_pairs": [
                {
                    "pair_index": pair_index,
                    "session_key_sha256": snapshot.session_key_sha256,
                    "witness_sha256": snapshot.witness_sha256,
                    "raw_snapshot_sha256": snapshot.raw_snapshot_sha256,
                }
                for pair_index, snapshot in enumerate(selected)
            ]
        }
    )


def _input_unavailable_result(
    *,
    policy: ProfiledMtfForwardSupervisedDatasetPolicy,
    receipt: ProfiledMtfForwardCampaignReadinessReceipt,
) -> ProfiledMtfForwardSupervisedDatasetResult:
    fields = {
        "policy_sha256": policy.policy_sha256,
        "readiness_receipt_sha256": receipt.receipt_sha256,
        "source_inventory_sha256": receipt.readiness.source_inventory_sha256,
        "source_manifest_sha256": receipt.readiness.target_ready_manifest_sha256,
        "status": "input_unavailable",
        "selected_pair_count": 0,
        "selected_pair_manifest_sha256": _sha256_json({"selected_pairs": []}),
        "row_count": 0,
        "dataset_contract_sha256": None,
        "dataset_materialization_sha256": None,
        "dataset_path": None,
    }
    return ProfiledMtfForwardSupervisedDatasetResult(
        **fields,
        result_sha256=_result_sha256_fields(fields),
    )


def _materialized_result(
    *,
    policy: ProfiledMtfForwardSupervisedDatasetPolicy,
    receipt: ProfiledMtfForwardCampaignReadinessReceipt,
    selected_pair_manifest_sha256: str,
    dataset_contract_sha256: str,
    dataset_materialization_sha256: str,
    dataset_path: Path,
    row_count: int,
) -> ProfiledMtfForwardSupervisedDatasetResult:
    fields = {
        "policy_sha256": policy.policy_sha256,
        "readiness_receipt_sha256": receipt.receipt_sha256,
        "source_inventory_sha256": receipt.readiness.source_inventory_sha256,
        "source_manifest_sha256": receipt.readiness.target_ready_manifest_sha256,
        "status": "materialized",
        "selected_pair_count": PROFILED_MTF_FORWARD_SUPERVISED_DATASET_PAIR_COUNT,
        "selected_pair_manifest_sha256": selected_pair_manifest_sha256,
        "row_count": row_count,
        "dataset_contract_sha256": dataset_contract_sha256,
        "dataset_materialization_sha256": dataset_materialization_sha256,
        "dataset_path": dataset_path,
    }
    return ProfiledMtfForwardSupervisedDatasetResult(
        **fields,
        result_sha256=_result_sha256_fields(fields),
    )


def _policy_unsigned_payload(
    policy: ProfiledMtfForwardSupervisedDatasetPolicy,
) -> dict[str, object]:
    return _policy_unsigned_payload_from_fields(
        readiness_receipt_sha256=policy.readiness_receipt_sha256,
        readiness_policy_sha256=policy.readiness_policy_sha256,
        readiness_sha256=policy.readiness_sha256,
        forward_outcome_contract_sha256=policy.forward_outcome_contract_sha256,
        code_revision_sha256=policy.code_revision_sha256,
    )


def _policy_from_safe_payload(
    payload: dict[str, object],
) -> ProfiledMtfForwardSupervisedDatasetPolicy:
    expected_keys = {
        "dataset_id",
        "readiness_receipt_sha256",
        "readiness_policy_sha256",
        "readiness_sha256",
        "forward_outcome_contract_sha256",
        "code_revision_sha256",
        "selection",
        "target",
        "pair_level_temporal_split",
        "policy_sha256",
    }
    if set(payload) != expected_keys or payload.get("dataset_id") != (
        PROFILED_MTF_FORWARD_SUPERVISED_DATASET_ID
    ):
        raise ValueError("supervised dataset policy is malformed")
    required_fields = (
        "readiness_receipt_sha256",
        "readiness_policy_sha256",
        "readiness_sha256",
        "forward_outcome_contract_sha256",
        "code_revision_sha256",
        "policy_sha256",
    )
    policy = ProfiledMtfForwardSupervisedDatasetPolicy(
        **{
            field_name: _required_sha256_payload(payload, field_name)
            for field_name in required_fields
        }
    )
    if payload != policy.safe_payload():
        raise ValueError("supervised dataset policy is malformed")
    return policy


def _result_from_safe_payload(
    payload: dict[str, object],
    *,
    market_data_root: Path,
    repo_root: Path,
) -> ProfiledMtfForwardSupervisedDatasetResult:
    expected_keys = {
        "dataset_id",
        "policy_sha256",
        "readiness_receipt_sha256",
        "source_inventory_sha256",
        "source_manifest_sha256",
        "status",
        "selected_pair_count",
        "selected_pair_manifest_sha256",
        "row_count",
        "dataset_contract_sha256",
        "dataset_materialization_sha256",
        "scope",
        "result_sha256",
    }
    if (
        set(payload) != expected_keys
        or payload.get("dataset_id") != PROFILED_MTF_FORWARD_SUPERVISED_DATASET_ID
        or payload.get("scope") != _result_scope()
        or payload.get("status") not in {"input_unavailable", "materialized"}
    ):
        raise ValueError("supervised dataset result is malformed")
    dataset_contract_sha256 = _optional_sha256_payload(payload, "dataset_contract_sha256")
    status = payload["status"]
    dataset_path = (
        _dataset_destination(
            market_data_root=market_data_root,
            repo_root=repo_root,
            dataset_contract_sha256=dataset_contract_sha256,
        )
        if status == "materialized" and dataset_contract_sha256 is not None
        else None
    )
    result = ProfiledMtfForwardSupervisedDatasetResult(
        policy_sha256=_required_sha256_payload(payload, "policy_sha256"),
        readiness_receipt_sha256=_required_sha256_payload(
            payload, "readiness_receipt_sha256"
        ),
        source_inventory_sha256=_required_sha256_payload(payload, "source_inventory_sha256"),
        source_manifest_sha256=_required_sha256_payload(payload, "source_manifest_sha256"),
        status=status,
        selected_pair_count=_required_int_payload(payload, "selected_pair_count"),
        selected_pair_manifest_sha256=_required_sha256_payload(
            payload, "selected_pair_manifest_sha256"
        ),
        row_count=_required_int_payload(payload, "row_count"),
        dataset_contract_sha256=dataset_contract_sha256,
        dataset_materialization_sha256=_optional_sha256_payload(
            payload, "dataset_materialization_sha256"
        ),
        result_sha256=_required_sha256_payload(payload, "result_sha256"),
        dataset_path=dataset_path,
    )
    if payload != result.safe_payload():
        raise ValueError("supervised dataset result is malformed")
    return result


def _dataset_destination(
    *,
    market_data_root: Path,
    repo_root: Path,
    dataset_contract_sha256: str,
) -> Path:
    _require_sha256(dataset_contract_sha256, "dataset_contract_sha256")
    reject_repo_artifact_path(market_data_root, repo_root)
    root = market_data_root.absolute()
    if root.exists() and (root.is_symlink() or not root.is_dir()):
        raise ValueError("supervised dataset market-data root is invalid")
    current = root
    resolved_root = root.resolve(strict=True) if root.exists() else None
    for part in (
        "us_equities",
        "kis_paper_private",
        PROFILED_MTF_FORWARD_SUPERVISED_DATASET_RAW_DIRECTORY,
        "c",
        _storage_key(dataset_contract_sha256),
    ):
        current = current / part
        if current.exists():
            if current.is_symlink() or not current.is_dir():
                raise ValueError("supervised dataset path is invalid")
            if resolved_root is not None and not current.resolve(strict=True).is_relative_to(
                resolved_root
            ):
                raise ValueError("supervised dataset path escapes market data")
    return current / "supervised-dataset.json"


def _inventory_sha256(catalog: KisMtfProfiledForwardOutcomeSnapshotCatalog) -> str:
    return profiled_mtf_forward_campaign_inventory_sha256(catalog.inventory)


def _policy_unsigned_payload_from_fields(
    *,
    readiness_receipt_sha256: str,
    readiness_policy_sha256: str,
    readiness_sha256: str,
    forward_outcome_contract_sha256: str,
    code_revision_sha256: str,
) -> dict[str, object]:
    return {
        "dataset_id": PROFILED_MTF_FORWARD_SUPERVISED_DATASET_ID,
        "readiness_receipt_sha256": readiness_receipt_sha256,
        "readiness_policy_sha256": readiness_policy_sha256,
        "readiness_sha256": readiness_sha256,
        "forward_outcome_contract_sha256": forward_outcome_contract_sha256,
        "code_revision_sha256": code_revision_sha256,
        "selection": {
            "pair_count": PROFILED_MTF_FORWARD_SUPERVISED_DATASET_PAIR_COUNT,
            "order": "outcome_end_utc_ascending_then_session_key_sha256",
        },
        "target": {
            "kind": "log_return",
            "input": "last_completed_causal_m1_close",
            "input_end": "15:30 America/New_York",
            "outcome": "final_completed_outcome_m1_close",
            "outcome_end": "15:45 America/New_York",
            "cross_timeframe_row_alignment": False,
        },
        "pair_level_temporal_split": {
            "train_pair_count": PROFILED_MTF_FORWARD_SUPERVISED_DATASET_TEMPORAL_SPLIT[0],
            "purge_pair_count": PROFILED_MTF_FORWARD_SUPERVISED_DATASET_TEMPORAL_SPLIT[1],
            "validation_pair_count": PROFILED_MTF_FORWARD_SUPERVISED_DATASET_TEMPORAL_SPLIT[2],
        },
    }


def _dataset_contract_sha256(
    *,
    policy_sha256: str,
    selected_pair_manifest_sha256: str,
    source_inventory_sha256: str,
) -> str:
    return _sha256_json(
        {
            "dataset_id": PROFILED_MTF_FORWARD_SUPERVISED_DATASET_ID,
            "policy_sha256": policy_sha256,
            "selected_pair_manifest_sha256": selected_pair_manifest_sha256,
            "source_inventory_sha256": source_inventory_sha256,
        }
    )


def _result_sha256(result: ProfiledMtfForwardSupervisedDatasetResult) -> str:
    return _result_sha256_fields(
        {
            "policy_sha256": result.policy_sha256,
            "readiness_receipt_sha256": result.readiness_receipt_sha256,
            "source_inventory_sha256": result.source_inventory_sha256,
            "source_manifest_sha256": result.source_manifest_sha256,
            "status": result.status,
            "selected_pair_count": result.selected_pair_count,
            "selected_pair_manifest_sha256": result.selected_pair_manifest_sha256,
            "row_count": result.row_count,
            "dataset_contract_sha256": result.dataset_contract_sha256,
            "dataset_materialization_sha256": result.dataset_materialization_sha256,
            "dataset_path": result.dataset_path,
        }
    )


def _result_sha256_fields(fields: dict[str, object]) -> str:
    return _sha256_json(
        {
            key: value
            for key, value in fields.items()
            if key != "dataset_path"
        }
    )


def _result_scope() -> dict[str, bool]:
    return {
        "repository_storage_allowed": False,
        "target_values_persisted_only_under_market_data": True,
        "raw_snapshots_persisted_only_under_market_data": True,
        "model_trained": False,
        "gpu_allocated": False,
        "pnl_calculated": False,
        "paper_or_broker_action": False,
        "network_or_credentials_used": False,
    }


def _artifact_policy() -> dict[str, bool]:
    return {
        "repository_storage_allowed": False,
        "raw_rows_persisted": False,
        "feature_values_persisted": False,
        "target_values_persisted": False,
        "predictions_persisted": False,
        "weights_persisted": False,
    }


def _write_or_verify_json(path: Path, payload: dict[str, object]) -> dict[str, object]:
    reject_repo_artifact_path(path, None)
    if path.is_symlink():
        raise ValueError("supervised dataset path must not be a symlink")
    encoded = _canonical_json(payload)
    if path.exists():
        try:
            existing = path.read_bytes()
        except OSError as error:
            raise ValueError("supervised dataset materialization is unavailable") from error
        if existing != encoded:
            raise ValueError("supervised dataset materialization conflicts")
        return payload
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded.decode("utf-8"))
    except FileExistsError:
        return _write_or_verify_json(path, payload)
    return payload


def _storage_key(value: str) -> str:
    _require_sha256(value, "storage key")
    return value.removeprefix("sha256:")[:16]


def _required_sha256_payload(payload: dict[str, object], field_name: str) -> str:
    value = payload.get(field_name)
    _require_sha256(value, field_name)
    return value


def _optional_sha256_payload(payload: dict[str, object], field_name: str) -> str | None:
    value = payload.get(field_name)
    if value is not None:
        _require_sha256(value, field_name)
    return value


def _required_mapping(payload: dict[str, object], field_name: str) -> dict[str, object]:
    value = payload.get(field_name)
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    return value


def _required_int_payload(payload: dict[str, object], field_name: str) -> int:
    value = payload.get(field_name)
    if type(value) is not int:
        raise ValueError(f"{field_name} must be an integer")
    return value


def _canonical_json(payload: object) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def _sha256_json(payload: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(payload)).hexdigest()


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"sha256:[0-9a-f]{64}", value))


def _require_sha256(value: object, field_name: str) -> None:
    if not _is_sha256(value):
        raise ValueError(f"{field_name} must be a SHA-256 identity")


def _require_attempt_id(value: str) -> None:
    if _ATTEMPT_ID_PATTERN.fullmatch(value) is None:
        raise ValueError("supervised dataset attempt_id is invalid")
