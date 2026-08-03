"""Bounded target-free PyTorch runtime evidence for profiled MTF controls.

This module does not create a predictive model. It accepts already validated
``ProfiledMtfFlattenedControl`` values, freezes a small runtime-only contract,
and records a CPU-first optional CUDA smoke outside the repository. The source
projection remains responsible for raw-feature provenance and causal geometry.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Final, Literal

from thericher_v2.contracts import SCHEMA_VERSION, Timeframe
from thericher_v2.data.kis_intraday_mtf_availability import (
    freeze_kis_intraday_mtf_availability_contract,
    load_kis_intraday_mtf_availability_catalogs,
    materialize_kis_intraday_mtf_availability,
)
from thericher_v2.models.sequence_window import SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES

from .artifact_paths import ensure_external_artifact_directory, reject_repo_artifact_path
from .campaign_registry import (
    CampaignOutcomeRegistryEntry,
    FrozenCampaignRegistryEntry,
    register_campaign_outcome,
    register_frozen_campaign,
)
from .causal_mtf_window_profile_feasibility import (
    CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG,
)
from .kis_mtf_profiled_feature_input_preflight import (
    KisMtfProfiledFeatureInputMaterialization,
    freeze_kis_mtf_profiled_feature_input_contract,
    materialize_kis_mtf_profiled_feature_inputs,
)
from .profiled_mtf_flattened_control import (
    PROFILED_MTF_FLATTENED_CONTROL_ANCHOR_POLICY,
    PROFILED_MTF_FLATTENED_CONTROL_SCHEMA_ID,
    ProfiledMtfFlattenedControl,
    build_profiled_mtf_flattened_control,
)

PROFILED_MTF_FLAT_MLP_RUNTIME_SMOKE_ID: Final = "profiled-mtf-flat-mlp-runtime-smoke-v1"
PROFILED_MTF_FLAT_MLP_RUNTIME_INVENTORY_ID: Final = "profiled-mtf-runtime-inventory-v1"
PROFILED_MTF_FLAT_MLP_RUNTIME_PROFILE_ID: Final = "short"
PROFILED_MTF_FLAT_MLP_RUNTIME_SEED: Final = 211
PROFILED_MTF_FLAT_MLP_RUNTIME_HIDDEN_WIDTH: Final = 16
PROFILED_MTF_FLAT_MLP_RUNTIME_LEARNING_RATE: Final = 0.01
PROFILED_MTF_FLAT_MLP_RUNTIME_CPU_STEPS: Final = 8
PROFILED_MTF_FLAT_MLP_RUNTIME_CUDA_STEPS: Final = 16
PROFILED_MTF_FLAT_MLP_RUNTIME_CUDA_MAX_SECONDS: Final = 60.0
_SHA256_PREFIX: Final = "sha256:"
_ATTEMPT_ID_PATTERN: Final = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)

RuntimeInventoryStatus = Literal["runtime_input_ready", "input_unavailable"]
RuntimePhase = Literal["cpu", "cuda"]
RuntimeDevice = Literal["cpu", "cuda", "unavailable"]
RuntimeRunStatus = Literal["completed", "runtime_unavailable"]


@dataclass(frozen=True, slots=True)
class ProfiledMtfFlatMlpRuntimeLayoutBlock:
    """Static block geometry shared by every control in one runtime batch."""

    timeframe: Timeframe
    feature_offset: int
    bar_count: int
    anchor_policy: str

    def __post_init__(self) -> None:
        if self.feature_offset < 0 or self.bar_count <= 0:
            raise ValueError("runtime layout block geometry is invalid")
        if self.anchor_policy != PROFILED_MTF_FLATTENED_CONTROL_ANCHOR_POLICY:
            raise ValueError("runtime layout block anchor policy is invalid")

    @property
    def feature_width(self) -> int:
        return self.bar_count * 2

    def safe_payload(self) -> dict[str, object]:
        return {
            "timeframe": self.timeframe.value,
            "feature_offset": self.feature_offset,
            "bar_count": self.bar_count,
            "anchor_policy": self.anchor_policy,
        }


@dataclass(frozen=True, slots=True)
class ProfiledMtfFlatMlpRuntimeBatch:
    """One in-memory, target-free batch with a source-safe identity."""

    profile_id: str
    source_contract_sha256: str
    source_dataset_hashes: tuple[str, ...]
    catalog_sha256: str
    layout: tuple[ProfiledMtfFlatMlpRuntimeLayoutBlock, ...]
    control_sha256s: tuple[str, ...]
    matrix: tuple[tuple[float, ...], ...] = field(repr=False)
    layout_sha256: str
    batch_sha256: str

    def __post_init__(self) -> None:
        matrix = tuple(tuple(float(value) for value in row) for row in self.matrix)
        layout = tuple(self.layout)
        control_sha256s = tuple(self.control_sha256s)
        source_dataset_hashes = tuple(self.source_dataset_hashes)
        if self.profile_id != PROFILED_MTF_FLAT_MLP_RUNTIME_PROFILE_ID:
            raise ValueError("runtime batch profile is invalid")
        if not _is_sha256(self.source_contract_sha256) or not _is_sha256(self.catalog_sha256):
            raise ValueError("runtime batch source identity is invalid")
        if (
            not source_dataset_hashes
            or source_dataset_hashes != tuple(sorted(set(source_dataset_hashes)))
            or any(not _is_sha256(value) for value in source_dataset_hashes)
        ):
            raise ValueError("runtime batch dataset identities are invalid")
        if not layout or len(matrix) < 2 or len(control_sha256s) != len(matrix):
            raise ValueError("runtime batch has insufficient controls")
        if len(set(control_sha256s)) != len(control_sha256s) or any(
            not _is_sha256(value) for value in control_sha256s
        ):
            raise ValueError("runtime batch controls must be unique identities")
        expected_width = sum(block.feature_width for block in layout)
        if (
            expected_width <= 0
            or any(len(row) != expected_width for row in matrix)
            or any(not math.isfinite(value) for row in matrix for value in row)
        ):
            raise ValueError("runtime batch matrix geometry is invalid")
        if layout != _expected_runtime_layout(self.profile_id):
            raise ValueError("runtime batch layout is not the fixed canonical profile")
        expected_layout_sha256 = _sha256_json(
            {"layout": [block.safe_payload() for block in layout]}
        )
        if self.layout_sha256 != expected_layout_sha256:
            raise ValueError("runtime batch layout identity is invalid")
        expected_batch_sha256 = _batch_sha256(
            profile_id=self.profile_id,
            source_contract_sha256=self.source_contract_sha256,
            source_dataset_hashes=source_dataset_hashes,
            catalog_sha256=self.catalog_sha256,
            layout_sha256=self.layout_sha256,
            control_sha256s=control_sha256s,
        )
        if self.batch_sha256 != expected_batch_sha256:
            raise ValueError("runtime batch identity is invalid")
        object.__setattr__(self, "layout", layout)
        object.__setattr__(self, "control_sha256s", control_sha256s)
        object.__setattr__(self, "source_dataset_hashes", source_dataset_hashes)
        object.__setattr__(self, "matrix", matrix)

    @property
    def control_count(self) -> int:
        return len(self.matrix)

    @property
    def feature_width(self) -> int:
        return len(self.matrix[0])

    def safe_payload(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "source_contract_sha256": self.source_contract_sha256,
            "source_dataset_hashes": list(self.source_dataset_hashes),
            "catalog_sha256": self.catalog_sha256,
            "layout_sha256": self.layout_sha256,
            "batch_sha256": self.batch_sha256,
            "control_count": self.control_count,
            "feature_width": self.feature_width,
        }


@dataclass(frozen=True, slots=True)
class ProfiledMtfFlatMlpRuntimeInventory:
    """Source-safe local input inventory for the one fixed runtime smoke."""

    status: RuntimeInventoryStatus
    reason: str | None
    source_contract_sha256: str
    source_receipt_sha256: str
    feature_input_contract_sha256: str
    feature_input_receipt_sha256: str
    eligible_session_count: int
    batch: ProfiledMtfFlatMlpRuntimeBatch | None = field(repr=False)
    inventory_sha256: str

    def __post_init__(self) -> None:
        if self.status not in {"runtime_input_ready", "input_unavailable"}:
            raise ValueError("runtime inventory status is invalid")
        if any(
            not _is_sha256(value)
            for value in (
                self.source_contract_sha256,
                self.source_receipt_sha256,
                self.feature_input_contract_sha256,
                self.feature_input_receipt_sha256,
            )
        ) or self.eligible_session_count < 0:
            raise ValueError("runtime inventory identity is invalid")
        if self.status == "runtime_input_ready":
            if self.reason is not None or self.batch is None:
                raise ValueError("ready runtime inventory is invalid")
        elif self.reason is None or self.batch is not None:
            raise ValueError("unavailable runtime inventory is invalid")
        expected = _inventory_sha256(
            status=self.status,
            reason=self.reason,
            source_contract_sha256=self.source_contract_sha256,
            source_receipt_sha256=self.source_receipt_sha256,
            feature_input_contract_sha256=self.feature_input_contract_sha256,
            feature_input_receipt_sha256=self.feature_input_receipt_sha256,
            eligible_session_count=self.eligible_session_count,
            batch=self.batch,
        )
        if self.inventory_sha256 != expected:
            raise ValueError("runtime inventory identity is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "inventory_id": PROFILED_MTF_FLAT_MLP_RUNTIME_INVENTORY_ID,
            "status": self.status,
            "reason": self.reason,
            "source_contract_sha256": self.source_contract_sha256,
            "source_receipt_sha256": self.source_receipt_sha256,
            "feature_input_contract_sha256": self.feature_input_contract_sha256,
            "feature_input_receipt_sha256": self.feature_input_receipt_sha256,
            "eligible_session_count": self.eligible_session_count,
            "predictive_target_ready_pair_count": 0,
            "batch": None if self.batch is None else self.batch.safe_payload(),
            "inventory_sha256": self.inventory_sha256,
            "scope": _runtime_only_scope(),
        }


@dataclass(frozen=True, slots=True)
class ProfiledMtfFlatMlpRuntimeContract:
    """Frozen target-free runtime appointment with no predictive interpretation."""

    inventory: ProfiledMtfFlatMlpRuntimeInventory = field(repr=False)
    artifact_root: Path
    repo_root: Path
    attempt_id: str
    run_directory: Path
    contract_path: Path
    contract_sha256: str
    registry_entry: FrozenCampaignRegistryEntry

    def __post_init__(self) -> None:
        if self.inventory.status != "runtime_input_ready" or self.inventory.batch is None:
            raise ValueError("runtime contract requires a ready inventory")
        if not _is_sha256(self.contract_sha256) or self.contract_path.parent != self.run_directory:
            raise ValueError("runtime contract identity is invalid")
        if self.run_directory.is_symlink() or not self.run_directory.is_relative_to(
            self.artifact_root.resolve()
        ):
            raise ValueError("runtime contract artifact directory is invalid")

    @property
    def batch(self) -> ProfiledMtfFlatMlpRuntimeBatch:
        assert self.inventory.batch is not None
        return self.inventory.batch


@dataclass(frozen=True, slots=True)
class ProfiledMtfFlatMlpRuntimeRun:
    """One source-safe CPU or CUDA runtime receipt."""

    contract_sha256: str
    phase: RuntimePhase
    status: RuntimeRunStatus
    device: RuntimeDevice
    steps_completed: int
    summary_path: Path
    summary_sha256: str
    runtime_metrics: Mapping[str, object] = field(repr=False)
    registry_outcome: CampaignOutcomeRegistryEntry | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if (
            not _is_sha256(self.contract_sha256)
            or not _is_sha256(self.summary_sha256)
            or self.phase not in {"cpu", "cuda"}
            or self.status not in {"completed", "runtime_unavailable"}
            or self.device not in {"cpu", "cuda", "unavailable"}
            or self.steps_completed < 0
            or self.summary_path.is_symlink()
        ):
            raise ValueError("runtime run is invalid")
        if self.status == "completed" and (
            self.device != self.phase or self.steps_completed <= 0
        ):
            raise ValueError("completed runtime phase/device combination is invalid")
        if self.status == "runtime_unavailable" and (
            self.device != "unavailable" or self.steps_completed != 0
        ):
            raise ValueError("unavailable runtime phase/device combination is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "campaign_id": PROFILED_MTF_FLAT_MLP_RUNTIME_SMOKE_ID,
            "campaign_contract_sha256": self.contract_sha256,
            "phase": self.phase,
            "status": self.status,
            "device": self.device,
            "steps_completed": self.steps_completed,
            "summary_sha256": self.summary_sha256,
            "runtime_metrics": dict(self.runtime_metrics),
            "runtime_evidence_only": True,
        }


def build_profiled_mtf_flat_mlp_runtime_batch(
    controls: Sequence[ProfiledMtfFlattenedControl],
) -> ProfiledMtfFlatMlpRuntimeBatch:
    """Build one fixed-profile matrix without reopening source bars or caches."""

    selected = tuple(controls)
    if len(selected) < 2 or any(
        not isinstance(control, ProfiledMtfFlattenedControl) for control in selected
    ):
        raise ValueError("runtime batch requires at least two flattened controls")
    first = selected[0]
    if (
        first.schema_id != PROFILED_MTF_FLATTENED_CONTROL_SCHEMA_ID
        or first.profile_id != PROFILED_MTF_FLAT_MLP_RUNTIME_PROFILE_ID
    ):
        raise ValueError("runtime batch profile is not the fixed smoke profile")
    layout = _layout_from_control(first)
    source_contract_sha256 = first.source_contract_sha256
    catalog_sha256 = first.catalog_sha256
    if any(
        control.schema_id != PROFILED_MTF_FLATTENED_CONTROL_SCHEMA_ID
        or control.profile_id != first.profile_id
        or control.source_contract_sha256 != source_contract_sha256
        or control.catalog_sha256 != catalog_sha256
        or _layout_from_control(control) != layout
        for control in selected
    ):
        raise ValueError("runtime batch controls have incompatible full layout geometry")
    control_sha256s = tuple(control.control_sha256 for control in selected)
    if len(set(control_sha256s)) != len(control_sha256s):
        raise ValueError("runtime batch controls must not repeat an identity")
    matrix = tuple(
        tuple(float(value) for value in control.flattened_values)
        for control in selected
    )
    layout_sha256 = _sha256_json({"layout": [block.safe_payload() for block in layout]})
    source_dataset_hashes = tuple(sorted({control.source_dataset_hash for control in selected}))
    return ProfiledMtfFlatMlpRuntimeBatch(
        profile_id=first.profile_id,
        source_contract_sha256=source_contract_sha256,
        source_dataset_hashes=source_dataset_hashes,
        catalog_sha256=catalog_sha256,
        layout=layout,
        control_sha256s=control_sha256s,
        matrix=matrix,
        layout_sha256=layout_sha256,
        batch_sha256=_batch_sha256(
            profile_id=first.profile_id,
            source_contract_sha256=source_contract_sha256,
            source_dataset_hashes=source_dataset_hashes,
            catalog_sha256=catalog_sha256,
            layout_sha256=layout_sha256,
            control_sha256s=control_sha256s,
        ),
    )


def inspect_profiled_mtf_flat_mlp_runtime_inventory(
    *,
    cache_root: Path | str,
    repo_root: Path | str,
    code_revision_sha256: str,
) -> ProfiledMtfFlatMlpRuntimeInventory:
    """Read the existing KIS local cache into the fixed runtime-only input scope."""

    _require_sha256(code_revision_sha256, "code_revision_sha256")
    catalogs = load_kis_intraday_mtf_availability_catalogs(
        cache_root=Path(cache_root), repo_root=Path(repo_root)
    )
    source_contract = freeze_kis_intraday_mtf_availability_contract(
        catalogs, code_revision=code_revision_sha256
    )
    source_receipt = materialize_kis_intraday_mtf_availability(source_contract, catalogs)
    feature_contract = freeze_kis_mtf_profiled_feature_input_contract(
        source_contract=source_contract,
        source_receipt=source_receipt,
        catalog=CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG,
        code_revision=code_revision_sha256,
    )
    materialization = materialize_kis_mtf_profiled_feature_inputs(
        contract=feature_contract,
        source_contract=source_contract,
        source_receipt=source_receipt,
        catalogs=catalogs,
    )
    return _inventory_from_materialization(
        source_contract_sha256=source_contract.contract_sha256,
        source_receipt_sha256=source_receipt.receipt_sha256,
        feature_input_contract_sha256=feature_contract.contract_sha256,
        materialization=materialization,
    )


def write_profiled_mtf_flat_mlp_runtime_inventory(
    inventory: ProfiledMtfFlatMlpRuntimeInventory,
    *,
    artifact_root: Path,
    repo_root: Path,
    attempt_id: str,
) -> Path:
    """Persist one aggregate-only input inventory outside the repository."""

    _require_attempt_id(attempt_id)
    directory = ensure_external_artifact_directory(
        artifact_root,
        repo_root,
        "data",
        PROFILED_MTF_FLAT_MLP_RUNTIME_INVENTORY_ID,
        attempt_id,
    )
    payload = _signed_payload(
        {
            "schema_version": SCHEMA_VERSION,
            **inventory.safe_payload(),
            "artifact_policy": {
                "raw_rows_persisted": False,
                "feature_values_persisted": False,
                "target_values_persisted": False,
                "predictions_persisted": False,
                "repository_storage_allowed": False,
            },
        },
        field_name="summary_sha256",
    )
    _write_or_verify_json(directory / "summary.json", payload)
    return directory / "summary.json"


def freeze_profiled_mtf_flat_mlp_runtime_smoke(
    inventory: ProfiledMtfFlatMlpRuntimeInventory,
    *,
    artifact_root: Path,
    repo_root: Path,
    code_revision_sha256: str,
    attempt_id: str,
) -> ProfiledMtfFlatMlpRuntimeContract:
    """Freeze one non-predictive appointment before any CPU or CUDA operation."""

    _require_attempt_id(attempt_id)
    _require_sha256(code_revision_sha256, "code_revision_sha256")
    if inventory.status != "runtime_input_ready" or inventory.batch is None:
        raise ValueError("runtime smoke requires a ready source inventory")
    reject_repo_artifact_path(artifact_root, repo_root)
    run_directory = ensure_external_artifact_directory(
        artifact_root,
        repo_root,
        "research",
        PROFILED_MTF_FLAT_MLP_RUNTIME_SMOKE_ID,
        attempt_id,
    )
    batch = inventory.batch
    payload = _signed_payload(
        {
            "schema_version": SCHEMA_VERSION,
            "campaign_id": PROFILED_MTF_FLAT_MLP_RUNTIME_SMOKE_ID,
            "attempt_id": attempt_id,
            "code_revision_sha256": code_revision_sha256,
            "inventory_sha256": inventory.inventory_sha256,
            "input": batch.safe_payload(),
            "runtime": {
                "task": "target_free_vector_runtime",
                "model_family": "one_hidden_layer_mlp",
                "seed": PROFILED_MTF_FLAT_MLP_RUNTIME_SEED,
                "hidden_width": PROFILED_MTF_FLAT_MLP_RUNTIME_HIDDEN_WIDTH,
                "learning_rate": PROFILED_MTF_FLAT_MLP_RUNTIME_LEARNING_RATE,
                "cpu_steps": PROFILED_MTF_FLAT_MLP_RUNTIME_CPU_STEPS,
                "cuda_steps": PROFILED_MTF_FLAT_MLP_RUNTIME_CUDA_STEPS,
                "cuda_max_seconds": int(PROFILED_MTF_FLAT_MLP_RUNTIME_CUDA_MAX_SECONDS),
                "column_permutation_kill_test": True,
                "structure_conclusion": "not_assessed_low_sample",
            },
            "scope": _runtime_only_scope(),
            "artifact_policy": {
                "repository_storage_allowed": False,
                "raw_rows_persisted": False,
                "feature_values_persisted": False,
                "target_values_persisted": False,
                "predictions_persisted": False,
                "weights_persisted": False,
            },
        },
        field_name="campaign_contract_sha256",
    )
    contract_path = run_directory / "campaign-contract.json"
    recorded = _write_or_verify_json(contract_path, payload)
    contract_sha256 = str(recorded["campaign_contract_sha256"])
    registry_entry = register_frozen_campaign(
        contract_hash=contract_sha256,
        dataset_hash=batch.batch_sha256,
        split_hash=_sha256_json(
            {
                "batch_rule": "all_available_fixed_profile_controls",
                "layout_sha256": batch.layout_sha256,
                "control_count": batch.control_count,
            }
        ),
        cost_model_hash=_sha256_json({"cost_model": "not_applicable_target_free"}),
        trial_family=PROFILED_MTF_FLAT_MLP_RUNTIME_SMOKE_ID,
        holdout_access="none",
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    return ProfiledMtfFlatMlpRuntimeContract(
        inventory=inventory,
        artifact_root=artifact_root.resolve(),
        repo_root=repo_root.resolve(),
        attempt_id=attempt_id,
        run_directory=run_directory,
        contract_path=contract_path,
        contract_sha256=contract_sha256,
        registry_entry=registry_entry,
    )


def run_profiled_mtf_flat_mlp_runtime_cpu(
    contract: ProfiledMtfFlatMlpRuntimeContract,
) -> ProfiledMtfFlatMlpRuntimeRun:
    """Run the required CPU evidence before a CUDA appointment is eligible."""

    existing = _load_existing_run(contract, phase="cpu")
    if existing is not None:
        return existing
    try:
        torch = _torch()
    except ModuleNotFoundError:
        return _write_unavailable_run(
            contract,
            phase="cpu",
            reason="torch_runtime_unavailable",
        )
    metrics = _cpu_runtime_metrics(torch, contract.batch)
    return _write_completed_run(
        contract,
        phase="cpu",
        device="cpu",
        metrics=metrics,
    )


def run_profiled_mtf_flat_mlp_runtime_cuda(
    contract: ProfiledMtfFlatMlpRuntimeContract,
) -> ProfiledMtfFlatMlpRuntimeRun:
    """Run one bounded CUDA receipt only after its exact CPU receipt completed."""

    _require_completed_cpu_run(contract)
    existing = _load_existing_run(contract, phase="cuda")
    if existing is not None:
        return _with_cuda_outcome(contract, existing)
    try:
        torch = _torch()
    except ModuleNotFoundError:
        return _with_cuda_outcome(
            contract,
            _write_unavailable_run(contract, phase="cuda", reason="torch_runtime_unavailable"),
        )
    if not torch.cuda.is_available():
        return _with_cuda_outcome(
            contract,
            _write_unavailable_run(contract, phase="cuda", reason="cuda_runtime_unavailable"),
        )
    metrics = _matrix_runtime_metrics(
        torch,
        contract.batch.matrix,
        device_name="cuda",
        max_steps=PROFILED_MTF_FLAT_MLP_RUNTIME_CUDA_STEPS,
        max_seconds=PROFILED_MTF_FLAT_MLP_RUNTIME_CUDA_MAX_SECONDS,
    )
    return _with_cuda_outcome(
        contract,
        _write_completed_run(contract, phase="cuda", device="cuda", metrics=metrics),
    )


def _inventory_from_materialization(
    *,
    source_contract_sha256: str,
    source_receipt_sha256: str,
    feature_input_contract_sha256: str,
    materialization: KisMtfProfiledFeatureInputMaterialization,
) -> ProfiledMtfFlatMlpRuntimeInventory:
    selected_controls = tuple(
        build_profiled_mtf_flattened_control(leg)
        for pair in materialization.pairs
        if pair.profile_id == PROFILED_MTF_FLAT_MLP_RUNTIME_PROFILE_ID
        for leg in pair.legs
    )
    if materialization.receipt.status != "feature_inputs_ready" or len(selected_controls) < 2:
        return _build_inventory(
            status="input_unavailable",
            reason="fixed_profile_controls_unavailable",
            source_contract_sha256=source_contract_sha256,
            source_receipt_sha256=source_receipt_sha256,
            feature_input_contract_sha256=feature_input_contract_sha256,
            feature_input_receipt_sha256=materialization.receipt.receipt_sha256,
            eligible_session_count=materialization.receipt.eligible_session_count,
            batch=None,
        )
    return _build_inventory(
        status="runtime_input_ready",
        reason=None,
        source_contract_sha256=source_contract_sha256,
        source_receipt_sha256=source_receipt_sha256,
        feature_input_contract_sha256=feature_input_contract_sha256,
        feature_input_receipt_sha256=materialization.receipt.receipt_sha256,
        eligible_session_count=materialization.receipt.eligible_session_count,
        batch=build_profiled_mtf_flat_mlp_runtime_batch(selected_controls),
    )


def _build_inventory(
    *,
    status: RuntimeInventoryStatus,
    reason: str | None,
    source_contract_sha256: str,
    source_receipt_sha256: str,
    feature_input_contract_sha256: str,
    feature_input_receipt_sha256: str,
    eligible_session_count: int,
    batch: ProfiledMtfFlatMlpRuntimeBatch | None,
) -> ProfiledMtfFlatMlpRuntimeInventory:
    return ProfiledMtfFlatMlpRuntimeInventory(
        status=status,
        reason=reason,
        source_contract_sha256=source_contract_sha256,
        source_receipt_sha256=source_receipt_sha256,
        feature_input_contract_sha256=feature_input_contract_sha256,
        feature_input_receipt_sha256=feature_input_receipt_sha256,
        eligible_session_count=eligible_session_count,
        batch=batch,
        inventory_sha256=_inventory_sha256(
            status=status,
            reason=reason,
            source_contract_sha256=source_contract_sha256,
            source_receipt_sha256=source_receipt_sha256,
            feature_input_contract_sha256=feature_input_contract_sha256,
            feature_input_receipt_sha256=feature_input_receipt_sha256,
            eligible_session_count=eligible_session_count,
            batch=batch,
        ),
    )


def _layout_from_control(
    control: ProfiledMtfFlattenedControl,
) -> tuple[ProfiledMtfFlatMlpRuntimeLayoutBlock, ...]:
    return tuple(
        ProfiledMtfFlatMlpRuntimeLayoutBlock(
            timeframe=block.timeframe,
            feature_offset=block.feature_offset,
            bar_count=block.bar_count,
            anchor_policy=block.anchor_policy,
        )
        for block in control.blocks
    )


def _expected_runtime_layout(
    profile_id: str,
) -> tuple[ProfiledMtfFlatMlpRuntimeLayoutBlock, ...]:
    """Return the fixed static geometry; per-session ends live in control hashes."""

    profile = CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG.profile(profile_id)
    feature_offset = 0
    blocks: list[ProfiledMtfFlatMlpRuntimeLayoutBlock] = []
    for timeframe in SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES:
        block = ProfiledMtfFlatMlpRuntimeLayoutBlock(
            timeframe=timeframe,
            feature_offset=feature_offset,
            bar_count=profile.lookbacks[timeframe],
            anchor_policy=PROFILED_MTF_FLATTENED_CONTROL_ANCHOR_POLICY,
        )
        blocks.append(block)
        feature_offset += block.feature_width
    return tuple(blocks)


def _cpu_runtime_metrics(torch: Any, batch: ProfiledMtfFlatMlpRuntimeBatch) -> dict[str, object]:
    original = _matrix_runtime_metrics(
        torch,
        batch.matrix,
        device_name="cpu",
        max_steps=PROFILED_MTF_FLAT_MLP_RUNTIME_CPU_STEPS,
        max_seconds=None,
    )
    permuted = _matrix_runtime_metrics(
        torch,
        _column_permuted_matrix(batch.matrix, seed=PROFILED_MTF_FLAT_MLP_RUNTIME_SEED),
        device_name="cpu",
        max_steps=PROFILED_MTF_FLAT_MLP_RUNTIME_CPU_STEPS,
        max_seconds=None,
    )
    return {
        "control_count": batch.control_count,
        "feature_width": batch.feature_width,
        "steps_completed": PROFILED_MTF_FLAT_MLP_RUNTIME_CPU_STEPS,
        "original": original,
        "column_permuted": permuted,
        "structure_conclusion": "not_assessed_low_sample",
    }


def _matrix_runtime_metrics(
    torch: Any,
    matrix: Sequence[Sequence[float]],
    *,
    device_name: Literal["cpu", "cuda"],
    max_steps: int,
    max_seconds: float | None,
) -> dict[str, object]:
    if max_steps <= 0 or len(matrix) < 2 or not matrix[0]:
        raise ValueError("runtime matrix configuration is invalid")
    if any(len(row) != len(matrix[0]) for row in matrix):
        raise ValueError("runtime matrix rows are inconsistent")
    _configure_torch_determinism(torch, device_name=device_name)
    device = torch.device(device_name)
    values = torch.tensor(matrix, dtype=torch.float32, device=device)
    if not bool(torch.isfinite(values).all().item()):
        raise ValueError("runtime matrix values are not finite")
    model = torch.nn.Sequential(
        torch.nn.Linear(int(values.shape[1]), PROFILED_MTF_FLAT_MLP_RUNTIME_HIDDEN_WIDTH),
        torch.nn.ReLU(),
        torch.nn.Linear(PROFILED_MTF_FLAT_MLP_RUNTIME_HIDDEN_WIDTH, int(values.shape[1])),
    ).to(device)
    optimizer = torch.optim.SGD(model.parameters(), lr=PROFILED_MTF_FLAT_MLP_RUNTIME_LEARNING_RATE)
    loss_fn = torch.nn.MSELoss()
    with torch.no_grad():
        initial_loss = loss_fn(model(values), values)
        column_mean_mse = torch.mean((values - values.mean(dim=0, keepdim=True)) ** 2)
    initial_loss_finite = bool(torch.isfinite(initial_loss).item())
    column_mean_mse_finite = bool(torch.isfinite(column_mean_mse).item())
    if not initial_loss_finite or not column_mean_mse_finite:
        raise ValueError("runtime matrix initial metrics are not finite")
    started = time.monotonic()
    steps_completed = 0
    for _ in range(max_steps):
        if max_seconds is not None and time.monotonic() - started >= max_seconds:
            break
        optimizer.zero_grad()
        loss = loss_fn(model(values), values)
        if not bool(torch.isfinite(loss).item()):
            raise ValueError("runtime matrix loss is not finite")
        loss.backward()
        optimizer.step()
        steps_completed += 1
    if steps_completed <= 0:
        raise ValueError("runtime matrix did not execute a training step")
    if device_name == "cuda":
        torch.cuda.synchronize()
    with torch.no_grad():
        final_loss = loss_fn(model(values), values)
    if not bool(torch.isfinite(final_loss).item()):
        raise ValueError("runtime matrix final metric is not finite")
    return {
        "initial_mse": round(float(initial_loss.detach().cpu().item()), 10),
        "final_mse": round(float(final_loss.detach().cpu().item()), 10),
        "column_mean_mse": round(float(column_mean_mse.detach().cpu().item()), 10),
        "steps_completed": steps_completed,
        "elapsed_milliseconds": int(round((time.monotonic() - started) * 1000)),
    }


def _column_permuted_matrix(
    matrix: Sequence[Sequence[float]],
    *,
    seed: int,
) -> tuple[tuple[float, ...], ...]:
    """Permute every feature column independently without modifying marginals."""

    rows = tuple(tuple(float(value) for value in row) for row in matrix)
    if len(rows) < 2 or not rows[0] or any(len(row) != len(rows[0]) for row in rows):
        raise ValueError("runtime matrix is invalid for column permutation")
    permuted = [list(row) for row in rows]
    for column in range(len(rows[0])):
        order = list(range(len(rows)))
        random.Random(seed + column).shuffle(order)
        for row_index, source_index in enumerate(order):
            permuted[row_index][column] = rows[source_index][column]
    return tuple(tuple(row) for row in permuted)


def _write_completed_run(
    contract: ProfiledMtfFlatMlpRuntimeContract,
    *,
    phase: RuntimePhase,
    device: Literal["cpu", "cuda"],
    metrics: Mapping[str, object],
) -> ProfiledMtfFlatMlpRuntimeRun:
    completed_metrics = {
        "control_count": contract.batch.control_count,
        "feature_width": contract.batch.feature_width,
        **metrics,
    }
    return _write_run(
        contract,
        phase=phase,
        status="completed",
        device=device,
        steps_completed=int(completed_metrics["steps_completed"]),
        runtime_metrics=completed_metrics,
    )


def _write_unavailable_run(
    contract: ProfiledMtfFlatMlpRuntimeContract,
    *,
    phase: RuntimePhase,
    reason: str,
) -> ProfiledMtfFlatMlpRuntimeRun:
    return _write_run(
        contract,
        phase=phase,
        status="runtime_unavailable",
        device="unavailable",
        steps_completed=0,
        runtime_metrics={
            "control_count": contract.batch.control_count,
            "feature_width": contract.batch.feature_width,
            "reason": reason,
            "structure_conclusion": "not_assessed_low_sample",
        },
    )


def _write_run(
    contract: ProfiledMtfFlatMlpRuntimeContract,
    *,
    phase: RuntimePhase,
    status: RuntimeRunStatus,
    device: RuntimeDevice,
    steps_completed: int,
    runtime_metrics: Mapping[str, object],
) -> ProfiledMtfFlatMlpRuntimeRun:
    path = _summary_path(contract, phase=phase)
    payload = _signed_payload(
        {
            "schema_version": SCHEMA_VERSION,
            "campaign_id": PROFILED_MTF_FLAT_MLP_RUNTIME_SMOKE_ID,
            "campaign_contract_sha256": contract.contract_sha256,
            "inventory_sha256": contract.inventory.inventory_sha256,
            "batch_sha256": contract.batch.batch_sha256,
            "phase": phase,
            "status": status,
            "device": device,
            "steps_completed": steps_completed,
            "runtime_evidence_only": True,
            "runtime_metrics": dict(runtime_metrics),
            "scope": _runtime_only_scope(),
        },
        field_name="summary_sha256",
    )
    recorded = _write_or_verify_json(path, payload)
    return _run_from_payload(recorded, path=path)


def _load_existing_run(
    contract: ProfiledMtfFlatMlpRuntimeContract,
    *,
    phase: RuntimePhase,
) -> ProfiledMtfFlatMlpRuntimeRun | None:
    path = _summary_path(contract, phase=phase)
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise ValueError("runtime summary is invalid")
    payload = _read_json_object(path)
    _verify_signed_payload(payload, field_name="summary_sha256")
    if (
        payload.get("campaign_id") != PROFILED_MTF_FLAT_MLP_RUNTIME_SMOKE_ID
        or payload.get("campaign_contract_sha256") != contract.contract_sha256
        or payload.get("inventory_sha256") != contract.inventory.inventory_sha256
        or payload.get("batch_sha256") != contract.batch.batch_sha256
        or payload.get("phase") != phase
    ):
        raise ValueError("runtime summary is malformed for its current contract")
    return _run_from_payload(payload, path=path)


def _run_from_payload(
    payload: Mapping[str, object],
    *,
    path: Path,
) -> ProfiledMtfFlatMlpRuntimeRun:
    status = payload.get("status")
    device = payload.get("device")
    phase = payload.get("phase")
    metrics = payload.get("runtime_metrics")
    steps_completed = payload.get("steps_completed")
    contract_sha256 = payload.get("campaign_contract_sha256")
    summary_sha256 = payload.get("summary_sha256")
    if (
        status not in {"completed", "runtime_unavailable"}
        or device not in {"cpu", "cuda", "unavailable"}
        or phase not in {"cpu", "cuda"}
        or not isinstance(metrics, dict)
        or isinstance(steps_completed, bool)
        or not isinstance(steps_completed, int)
        or not isinstance(contract_sha256, str)
        or not isinstance(summary_sha256, str)
    ):
        raise ValueError("runtime summary is malformed")
    return ProfiledMtfFlatMlpRuntimeRun(
        contract_sha256=contract_sha256,
        phase=phase,
        status=status,
        device=device,
        steps_completed=steps_completed,
        summary_path=path,
        summary_sha256=summary_sha256,
        runtime_metrics=metrics,
    )


def _require_completed_cpu_run(contract: ProfiledMtfFlatMlpRuntimeContract) -> None:
    cpu_run = _load_existing_run(contract, phase="cpu")
    if (
        cpu_run is None
        or cpu_run.status != "completed"
        or cpu_run.device != "cpu"
        or cpu_run.steps_completed != PROFILED_MTF_FLAT_MLP_RUNTIME_CPU_STEPS
    ):
        raise ValueError("a completed matching CPU runtime receipt is required before CUDA")


def _with_cuda_outcome(
    contract: ProfiledMtfFlatMlpRuntimeContract,
    run: ProfiledMtfFlatMlpRuntimeRun,
) -> ProfiledMtfFlatMlpRuntimeRun:
    outcome = register_campaign_outcome(
        contract_hash=contract.contract_sha256,
        outcome_class=(
            "non_promoting_completed"
            if run.status == "completed"
            else "non_promoting_failed"
        ),
        outcome_reference_sha256=run.summary_sha256,
        artifact_root=contract.artifact_root,
        repo_root=contract.repo_root,
    )
    return replace(run, registry_outcome=outcome)


def _summary_path(
    contract: ProfiledMtfFlatMlpRuntimeContract,
    *,
    phase: RuntimePhase,
) -> Path:
    return contract.run_directory / f"{phase}-summary.json"


def _configure_torch_determinism(torch: Any, *, device_name: Literal["cpu", "cuda"]) -> None:
    torch.manual_seed(PROFILED_MTF_FLAT_MLP_RUNTIME_SEED)
    if device_name == "cuda":
        torch.cuda.manual_seed_all(PROFILED_MTF_FLAT_MLP_RUNTIME_SEED)
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True
    torch.use_deterministic_algorithms(True)


def _runtime_only_scope() -> dict[str, bool]:
    return {
        "runtime_evidence_only": True,
        "predictive_model": False,
        "return_or_target_labels": False,
        "model_selection": False,
        "ensemble_member": False,
        "paper_input": False,
        "pnl_or_profitability_claim": False,
        "live_behavior": False,
    }


def _inventory_sha256(
    *,
    status: RuntimeInventoryStatus,
    reason: str | None,
    source_contract_sha256: str,
    source_receipt_sha256: str,
    feature_input_contract_sha256: str,
    feature_input_receipt_sha256: str,
    eligible_session_count: int,
    batch: ProfiledMtfFlatMlpRuntimeBatch | None,
) -> str:
    return _sha256_json(
        {
            "inventory_id": PROFILED_MTF_FLAT_MLP_RUNTIME_INVENTORY_ID,
            "status": status,
            "reason": reason,
            "source_contract_sha256": source_contract_sha256,
            "source_receipt_sha256": source_receipt_sha256,
            "feature_input_contract_sha256": feature_input_contract_sha256,
            "feature_input_receipt_sha256": feature_input_receipt_sha256,
            "eligible_session_count": eligible_session_count,
            "batch_sha256": None if batch is None else batch.batch_sha256,
        }
    )


def _batch_sha256(
    *,
    profile_id: str,
    source_contract_sha256: str,
    source_dataset_hashes: Sequence[str],
    catalog_sha256: str,
    layout_sha256: str,
    control_sha256s: Sequence[str],
) -> str:
    return _sha256_json(
        {
            "profile_id": profile_id,
            "source_contract_sha256": source_contract_sha256,
            "source_dataset_hashes": list(source_dataset_hashes),
            "catalog_sha256": catalog_sha256,
            "layout_sha256": layout_sha256,
            "control_sha256s": list(control_sha256s),
        }
    )


def _signed_payload(payload: Mapping[str, object], *, field_name: str) -> dict[str, object]:
    if field_name in payload:
        raise ValueError("signed payload field already exists")
    completed = dict(payload)
    completed[field_name] = _sha256_json(completed)
    return completed


def _verify_signed_payload(payload: Mapping[str, object], *, field_name: str) -> str:
    digest = payload.get(field_name)
    unsigned = dict(payload)
    unsigned.pop(field_name, None)
    if not isinstance(digest, str) or digest != _sha256_json(unsigned):
        raise ValueError("runtime artifact checksum is invalid")
    return digest


def _write_or_verify_json(path: Path, payload: Mapping[str, object]) -> dict[str, object]:
    if path.is_symlink():
        raise ValueError("runtime artifact path must not be a link")
    encoded = _canonical_json(payload)
    if path.exists():
        existing = _read_json_object(path)
        if _canonical_json(existing) != encoded:
            raise ValueError("runtime artifact conflicts with the frozen contract")
        return existing
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded.decode("utf-8"))
    except FileExistsError:
        return _write_or_verify_json(path, payload)
    return dict(payload)


def _read_json_object(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("runtime artifact is malformed") from exc
    if not isinstance(payload, dict):
        raise ValueError("runtime artifact must be an object")
    return payload


def _canonical_json(payload: Mapping[str, object]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256_json(payload: Mapping[str, object]) -> str:
    return _SHA256_PREFIX + hashlib.sha256(_canonical_json(payload)).hexdigest()


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"sha256:[0-9a-f]{64}", value))


def _require_sha256(value: object, field_name: str) -> None:
    if not _is_sha256(value):
        raise ValueError(f"{field_name} must be a sha256 identity")


def _require_attempt_id(value: str) -> None:
    if _ATTEMPT_ID_PATTERN.fullmatch(value) is None:
        raise ValueError("runtime attempt_id is invalid")


def _torch() -> Any:
    import torch

    return torch
