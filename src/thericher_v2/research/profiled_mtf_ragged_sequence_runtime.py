"""Target-free ragged sequence runtime evidence for frozen profiled MTF controls.

The module deliberately preserves native timeframe sequences.  Its attention
tokens carry timeframe and within-timeframe position identities, not a claimed
row-wise or wall-clock alignment across timeframes.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Final, Literal

from thericher_v2.contracts import SCHEMA_VERSION, Timeframe
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
from .profiled_mtf_flat_mlp_runtime_smoke import (
    PROFILED_MTF_FLAT_MLP_RUNTIME_PROFILE_ID,
    ProfiledMtfFlatMlpRuntimeSource,
    build_profiled_mtf_flat_mlp_runtime_batch,
)
from .profiled_mtf_flattened_control import (
    PROFILED_MTF_FLATTENED_CONTROL_SCHEMA_ID,
    ProfiledMtfFlattenedControl,
)

PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_ID: Final = "profiled-mtf-ragged-sequence-runtime-v1"
PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_PROFILE_ID: Final = (
    PROFILED_MTF_FLAT_MLP_RUNTIME_PROFILE_ID
)
PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_SEED: Final = 307
PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_HIDDEN_WIDTH: Final = 4
PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_LEARNING_RATE: Final = 0.01
PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_CPU_STEPS_PER_FAMILY: Final = 4
PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_CUDA_STEPS_PER_FAMILY: Final = 8
PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_CUDA_MAX_SECONDS: Final = 60.0
PROFILED_MTF_RAGGED_SEQUENCE_FEATURE_WIDTH: Final = 2
PROFILED_MTF_RAGGED_SEQUENCE_FAMILIES: Final = (
    "per_timeframe_recurrent",
    "causal_tcn",
    "masked_cross_timeframe_attention",
)
PROFILED_MTF_RAGGED_SEQUENCE_MASK_POLICY: Final = {
    "native_timeframe_sequences_preserved": True,
    "cross_timeframe_row_alignment": "none",
    "per_timeframe_padding_mask": "explicit_validity_mask",
    "attention_mask": "availability_only_not_global_temporal_order",
    "within_timeframe_position": "oldest_to_newest_causal_rank",
}
_SHA256_PREFIX: Final = "sha256:"
_ATTEMPT_ID_PATTERN: Final = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)

RuntimePhase = Literal["cpu", "cuda"]
RuntimeDevice = Literal["cpu", "cuda", "unavailable"]
RuntimeRunStatus = Literal["completed", "runtime_unavailable"]


@dataclass(frozen=True, slots=True)
class ProfiledMtfRaggedSequenceFrame:
    """One native sequence segment; its token offset is not a time alignment."""

    timeframe: Timeframe
    source_feature_offset: int
    sequence_length: int
    token_offset: int
    feature_width: int = PROFILED_MTF_RAGGED_SEQUENCE_FEATURE_WIDTH

    def __post_init__(self) -> None:
        if (
            self.timeframe not in SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES
            or self.source_feature_offset < 0
            or self.sequence_length <= 0
            or self.token_offset < 0
            or self.feature_width != PROFILED_MTF_RAGGED_SEQUENCE_FEATURE_WIDTH
        ):
            raise ValueError("ragged sequence frame geometry is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "timeframe": self.timeframe.value,
            "source_feature_offset": self.source_feature_offset,
            "sequence_length": self.sequence_length,
            "token_offset": self.token_offset,
            "feature_width": self.feature_width,
        }


@dataclass(frozen=True, slots=True)
class ProfiledMtfRaggedSequenceBatch:
    """Validated target-free native sequences with an explicit availability mask."""

    source_inventory_sha256: str
    source_batch_sha256: str
    profile_id: str
    source_contract_sha256: str
    source_dataset_hashes: tuple[str, ...]
    catalog_sha256: str
    frames: tuple[ProfiledMtfRaggedSequenceFrame, ...]
    control_sha256s: tuple[str, ...]
    sequences: tuple[tuple[tuple[tuple[float, ...], ...], ...], ...] = field(repr=False)
    validity_masks: tuple[tuple[tuple[bool, ...], ...], ...] = field(repr=False)
    layout_sha256: str
    batch_sha256: str

    def __post_init__(self) -> None:
        frames = tuple(self.frames)
        controls = tuple(self.control_sha256s)
        sequences = tuple(
            tuple(tuple(tuple(float(value) for value in row) for row in frame) for frame in control)
            for control in self.sequences
        )
        masks = tuple(
            tuple(tuple(bool(value) for value in frame) for frame in control)
            for control in self.validity_masks
        )
        source_dataset_hashes = tuple(self.source_dataset_hashes)
        if (
            self.profile_id != PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_PROFILE_ID
            or not all(
                _is_sha256(value)
                for value in (
                    self.source_inventory_sha256,
                    self.source_batch_sha256,
                    self.source_contract_sha256,
                    self.catalog_sha256,
                    self.layout_sha256,
                    self.batch_sha256,
                )
            )
            or not source_dataset_hashes
            or source_dataset_hashes != tuple(sorted(set(source_dataset_hashes)))
            or any(not _is_sha256(value) for value in source_dataset_hashes)
            or len(frames) != len(SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES)
            or frames != _expected_frames(self.profile_id)
            or len(controls) < 2
            or len(controls) != len(sequences)
            or len(masks) != len(sequences)
            or len(set(controls)) != len(controls)
            or any(not _is_sha256(value) for value in controls)
        ):
            raise ValueError("ragged sequence batch identity is invalid")
        for control_frames, control_masks in zip(sequences, masks, strict=True):
            if len(control_frames) != len(frames) or len(control_masks) != len(frames):
                raise ValueError("ragged sequence batch frame count is invalid")
            for frame, rows, mask in zip(frames, control_frames, control_masks, strict=True):
                if (
                    len(rows) != frame.sequence_length
                    or len(mask) != frame.sequence_length
                    or any(len(row) != frame.feature_width for row in rows)
                    or any(not math.isfinite(value) for row in rows for value in row)
                    or not all(mask)
                ):
                    raise ValueError("ragged sequence batch values or mask are invalid")
        expected_layout = _sha256_json(
            {
                "frames": [frame.safe_payload() for frame in frames],
                "mask_policy": PROFILED_MTF_RAGGED_SEQUENCE_MASK_POLICY,
            }
        )
        if self.layout_sha256 != expected_layout:
            raise ValueError("ragged sequence layout identity is invalid")
        expected_batch = _ragged_batch_sha256(
            source_inventory_sha256=self.source_inventory_sha256,
            source_batch_sha256=self.source_batch_sha256,
            profile_id=self.profile_id,
            source_contract_sha256=self.source_contract_sha256,
            source_dataset_hashes=source_dataset_hashes,
            catalog_sha256=self.catalog_sha256,
            layout_sha256=self.layout_sha256,
            control_sha256s=controls,
        )
        if self.batch_sha256 != expected_batch:
            raise ValueError("ragged sequence batch hash is invalid")
        object.__setattr__(self, "frames", frames)
        object.__setattr__(self, "control_sha256s", controls)
        object.__setattr__(self, "sequences", sequences)
        object.__setattr__(self, "validity_masks", masks)
        object.__setattr__(self, "source_dataset_hashes", source_dataset_hashes)

    @property
    def control_count(self) -> int:
        return len(self.sequences)

    @property
    def token_count(self) -> int:
        return sum(frame.sequence_length for frame in self.frames)

    def safe_payload(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "source_inventory_sha256": self.source_inventory_sha256,
            "source_batch_sha256": self.source_batch_sha256,
            "source_contract_sha256": self.source_contract_sha256,
            "source_dataset_hashes": list(self.source_dataset_hashes),
            "catalog_sha256": self.catalog_sha256,
            "frames": [frame.safe_payload() for frame in self.frames],
            "control_count": self.control_count,
            "token_count": self.token_count,
            "feature_width": PROFILED_MTF_RAGGED_SEQUENCE_FEATURE_WIDTH,
            "mask_policy": PROFILED_MTF_RAGGED_SEQUENCE_MASK_POLICY,
            "layout_sha256": self.layout_sha256,
            "batch_sha256": self.batch_sha256,
        }


@dataclass(frozen=True, slots=True)
class ProfiledMtfRaggedSequenceRuntimeContract:
    """One source-safe target-free appointment over a frozen ragged batch."""

    source: ProfiledMtfFlatMlpRuntimeSource = field(repr=False)
    batch: ProfiledMtfRaggedSequenceBatch = field(repr=False)
    artifact_root: Path
    repo_root: Path
    attempt_id: str
    run_directory: Path
    contract_path: Path
    contract_sha256: str
    registry_entry: FrozenCampaignRegistryEntry

    def __post_init__(self) -> None:
        if (
            self.source.inventory.status != "runtime_input_ready"
            or self.source.inventory.batch is None
            or not _is_sha256(self.contract_sha256)
            or self.contract_path.parent != self.run_directory
            or self.run_directory.is_symlink()
            or not self.run_directory.is_relative_to(self.artifact_root.resolve())
        ):
            raise ValueError("ragged sequence runtime contract is invalid")


@dataclass(frozen=True, slots=True)
class ProfiledMtfRaggedSequenceRuntimeRun:
    """One source-safe CPU or CUDA structural runtime receipt."""

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
            or (
                self.status == "completed"
                and (self.device != self.phase or self.steps_completed <= 0)
            )
            or (
                self.status == "runtime_unavailable"
                and (self.device != "unavailable" or self.steps_completed != 0)
            )
        ):
            raise ValueError("ragged sequence runtime run is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "campaign_id": PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_ID,
            "campaign_contract_sha256": self.contract_sha256,
            "phase": self.phase,
            "status": self.status,
            "device": self.device,
            "steps_completed": self.steps_completed,
            "summary_sha256": self.summary_sha256,
            "runtime_metrics": dict(self.runtime_metrics),
            "runtime_evidence_only": True,
        }


def build_profiled_mtf_ragged_sequence_batch(
    source: ProfiledMtfFlatMlpRuntimeSource,
) -> ProfiledMtfRaggedSequenceBatch:
    """Revalidate controls before converting them into native ragged sequences."""

    if source.inventory.status != "runtime_input_ready" or source.inventory.batch is None:
        raise ValueError("ragged sequence batch requires a ready runtime source")
    controls = tuple(source.controls)
    source_batch = build_profiled_mtf_flat_mlp_runtime_batch(controls)
    if source_batch != source.inventory.batch:
        raise ValueError("ragged sequence source no longer matches its inventory")
    first = controls[0]
    if (
        first.schema_id != PROFILED_MTF_FLATTENED_CONTROL_SCHEMA_ID
        or first.profile_id != PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_PROFILE_ID
    ):
        raise ValueError("ragged sequence source profile is invalid")
    frames = _frames_from_control(first)
    if any(
        control.schema_id != first.schema_id
        or control.profile_id != first.profile_id
        or control.source_contract_sha256 != first.source_contract_sha256
        or control.catalog_sha256 != first.catalog_sha256
        or _frames_from_control(control) != frames
        for control in controls
    ):
        raise ValueError("ragged sequence controls have incompatible native layouts")
    sequences = tuple(_sequences_from_control(control, frames) for control in controls)
    masks = tuple(
        tuple(tuple(True for _ in frame_rows) for frame_rows in control_frames)
        for control_frames in sequences
    )
    layout_sha256 = _sha256_json(
        {
            "frames": [frame.safe_payload() for frame in frames],
            "mask_policy": PROFILED_MTF_RAGGED_SEQUENCE_MASK_POLICY,
        }
    )
    control_sha256s = tuple(control.control_sha256 for control in controls)
    source_dataset_hashes = tuple(sorted({control.source_dataset_hash for control in controls}))
    return ProfiledMtfRaggedSequenceBatch(
        source_inventory_sha256=source.inventory.inventory_sha256,
        source_batch_sha256=source_batch.batch_sha256,
        profile_id=first.profile_id,
        source_contract_sha256=first.source_contract_sha256,
        source_dataset_hashes=source_dataset_hashes,
        catalog_sha256=first.catalog_sha256,
        frames=frames,
        control_sha256s=control_sha256s,
        sequences=sequences,
        validity_masks=masks,
        layout_sha256=layout_sha256,
        batch_sha256=_ragged_batch_sha256(
            source_inventory_sha256=source.inventory.inventory_sha256,
            source_batch_sha256=source_batch.batch_sha256,
            profile_id=first.profile_id,
            source_contract_sha256=first.source_contract_sha256,
            source_dataset_hashes=source_dataset_hashes,
            catalog_sha256=first.catalog_sha256,
            layout_sha256=layout_sha256,
            control_sha256s=control_sha256s,
        ),
    )


def freeze_profiled_mtf_ragged_sequence_runtime(
    source: ProfiledMtfFlatMlpRuntimeSource,
    *,
    artifact_root: Path,
    repo_root: Path,
    code_revision_sha256: str,
    attempt_id: str,
) -> ProfiledMtfRaggedSequenceRuntimeContract:
    """Freeze one non-predictive three-family runtime appointment."""

    _require_attempt_id(attempt_id)
    _require_sha256(code_revision_sha256, "code_revision_sha256")
    batch = build_profiled_mtf_ragged_sequence_batch(source)
    reject_repo_artifact_path(artifact_root, repo_root)
    run_directory = ensure_external_artifact_directory(
        artifact_root,
        repo_root,
        "research",
        PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_ID,
        attempt_id,
    )
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_ID,
        "attempt_id": attempt_id,
        "code_revision_sha256": code_revision_sha256,
        "source_inventory_sha256": source.inventory.inventory_sha256,
        "input": batch.safe_payload(),
        "runtime": {
            "families": list(PROFILED_MTF_RAGGED_SEQUENCE_FAMILIES),
            "task": "target_free_structural_autoencoding",
            "seed": PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_SEED,
            "hidden_width": PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_HIDDEN_WIDTH,
            "learning_rate": PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_LEARNING_RATE,
            "cpu_steps_per_family": PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_CPU_STEPS_PER_FAMILY,
            "cuda_steps_per_family": PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_CUDA_STEPS_PER_FAMILY,
            "cuda_max_seconds": int(PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_CUDA_MAX_SECONDS),
            "mask_policy": PROFILED_MTF_RAGGED_SEQUENCE_MASK_POLICY,
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
    }
    payload = _signed_payload(unsigned, field_name="campaign_contract_sha256")
    contract_path = run_directory / "campaign-contract.json"
    recorded = _write_or_verify_json(contract_path, payload)
    contract_sha256 = _required_payload_sha256(recorded, "campaign_contract_sha256")
    registry_entry = register_frozen_campaign(
        contract_hash=contract_sha256,
        dataset_hash=batch.batch_sha256,
        split_hash=_sha256_json(
            {
                "structure": "all_available_fixed_profile_native_sequences",
                "layout_sha256": batch.layout_sha256,
                "control_count": batch.control_count,
            }
        ),
        cost_model_hash=_sha256_json({"cost_model": "not_applicable_target_free"}),
        trial_family=PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_ID,
        holdout_access="none",
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    return ProfiledMtfRaggedSequenceRuntimeContract(
        source=source,
        batch=batch,
        artifact_root=artifact_root.resolve(),
        repo_root=repo_root.resolve(),
        attempt_id=attempt_id,
        run_directory=run_directory,
        contract_path=contract_path,
        contract_sha256=contract_sha256,
        registry_entry=registry_entry,
    )


def run_profiled_mtf_ragged_sequence_runtime_cpu(
    contract: ProfiledMtfRaggedSequenceRuntimeContract,
) -> ProfiledMtfRaggedSequenceRuntimeRun:
    """Run the required CPU structural receipt before a CUDA appointment."""

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
    return _write_completed_run(
        contract,
        phase="cpu",
        device="cpu",
        metrics=_runtime_metrics(
            torch,
            contract.batch,
            device_name="cpu",
            steps_per_family=PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_CPU_STEPS_PER_FAMILY,
            max_seconds=None,
        ),
    )


def run_profiled_mtf_ragged_sequence_runtime_cuda(
    contract: ProfiledMtfRaggedSequenceRuntimeContract,
) -> ProfiledMtfRaggedSequenceRuntimeRun:
    """Run one bounded CUDA receipt only after its matching CPU receipt."""

    _require_completed_cpu_run(contract)
    existing = _load_existing_run(contract, phase="cuda")
    if existing is not None:
        return _with_cuda_outcome(contract, existing)
    try:
        torch = _torch()
    except ModuleNotFoundError:
        return _with_cuda_outcome(
            contract,
            _write_unavailable_run(
                contract,
                phase="cuda",
                reason="torch_runtime_unavailable",
            ),
        )
    if not torch.cuda.is_available():
        return _with_cuda_outcome(
            contract,
            _write_unavailable_run(
                contract,
                phase="cuda",
                reason="cuda_runtime_unavailable",
            ),
        )
    return _with_cuda_outcome(
        contract,
        _write_completed_run(
            contract,
            phase="cuda",
            device="cuda",
            metrics=_runtime_metrics(
                torch,
                contract.batch,
                device_name="cuda",
                steps_per_family=PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_CUDA_STEPS_PER_FAMILY,
                max_seconds=PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_CUDA_MAX_SECONDS,
            ),
        ),
    )


def _runtime_metrics(
    torch: Any,
    batch: ProfiledMtfRaggedSequenceBatch,
    *,
    device_name: Literal["cpu", "cuda"],
    steps_per_family: int,
    max_seconds: float | None,
) -> dict[str, object]:
    if steps_per_family <= 0:
        raise ValueError("ragged sequence runtime steps must be positive")
    _configure_torch_determinism(torch, device_name=device_name)
    device = torch.device(device_name)
    frames, masks = _frame_tensors(torch, batch, device=device)
    started = time.monotonic()
    family_metrics: list[dict[str, object]] = []
    for family_index, family_id in enumerate(PROFILED_MTF_RAGGED_SEQUENCE_FAMILIES):
        if max_seconds is not None and time.monotonic() - started >= max_seconds:
            raise ValueError("ragged sequence CUDA budget elapsed before a family started")
        _configure_torch_determinism(
            torch,
            device_name=device_name,
            seed=PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_SEED + family_index,
        )
        model, mode = _family_model(torch, family_id, batch, device=device)
        optimizer = torch.optim.SGD(
            model.parameters(),
            lr=PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_LEARNING_RATE,
        )
        initial_loss = _family_loss(torch, model, mode, frames, masks)
        if not bool(torch.isfinite(initial_loss).item()):
            raise ValueError("ragged sequence runtime initial loss is not finite")
        steps_completed = 0
        for _ in range(steps_per_family):
            if max_seconds is not None and time.monotonic() - started >= max_seconds:
                break
            optimizer.zero_grad()
            loss = _family_loss(torch, model, mode, frames, masks)
            if not bool(torch.isfinite(loss).item()):
                raise ValueError("ragged sequence runtime loss is not finite")
            loss.backward()
            optimizer.step()
            steps_completed += 1
        if steps_completed != steps_per_family:
            raise ValueError("ragged sequence runtime did not complete its fixed family steps")
        final_loss = _family_loss(torch, model, mode, frames, masks)
        if not bool(torch.isfinite(final_loss).item()):
            raise ValueError("ragged sequence runtime final loss is not finite")
        family_metrics.append(
            {
                "family_id": family_id,
                "steps_completed": steps_completed,
                "initial_reconstruction_mse": _finite_scalar(initial_loss),
                "final_reconstruction_mse": _finite_scalar(final_loss),
            }
        )
    if device_name == "cuda":
        torch.cuda.synchronize()
    return {
        "control_count": batch.control_count,
        "native_sequence_lengths": [frame.sequence_length for frame in batch.frames],
        "feature_width": PROFILED_MTF_RAGGED_SEQUENCE_FEATURE_WIDTH,
        "token_count": batch.token_count,
        "mask_policy": PROFILED_MTF_RAGGED_SEQUENCE_MASK_POLICY,
        "families": family_metrics,
        "steps_completed": sum(
            int(metrics["steps_completed"]) for metrics in family_metrics
        ),
        "elapsed_milliseconds": int(round((time.monotonic() - started) * 1000)),
        "structure_conclusion": "not_assessed_low_sample",
    }


def _frame_tensors(
    torch: Any,
    batch: ProfiledMtfRaggedSequenceBatch,
    *,
    device: Any,
) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
    frames: list[Any] = []
    masks: list[Any] = []
    for frame_index, frame in enumerate(batch.frames):
        values = [
            [list(row) for row in control[frame_index]]
            for control in batch.sequences
        ]
        mask_values = [list(control[frame_index]) for control in batch.validity_masks]
        tensor = torch.tensor(values, dtype=torch.float32, device=device)
        mask = torch.tensor(mask_values, dtype=torch.bool, device=device)
        expected_shape = (
            batch.control_count,
            frame.sequence_length,
            PROFILED_MTF_RAGGED_SEQUENCE_FEATURE_WIDTH,
        )
        if tuple(tensor.shape) != expected_shape or tuple(mask.shape) != expected_shape[:2]:
            raise ValueError("ragged sequence tensor geometry is invalid")
        if not bool(torch.isfinite(tensor).all().item()) or not bool(mask.all().item()):
            raise ValueError("ragged sequence tensor availability is invalid")
        frames.append(tensor)
        masks.append(mask)
    return tuple(frames), tuple(masks)


def _family_model(
    torch: Any,
    family_id: str,
    batch: ProfiledMtfRaggedSequenceBatch,
    *,
    device: Any,
) -> tuple[Any, Literal["frames", "attention"]]:
    if family_id == "per_timeframe_recurrent":
        return _recurrent_model(torch, batch).to(device), "frames"
    if family_id == "causal_tcn":
        return _causal_tcn_model(torch, batch).to(device), "frames"
    if family_id == "masked_cross_timeframe_attention":
        return _attention_model(torch, batch).to(device), "attention"
    raise ValueError("ragged sequence runtime family is invalid")


def _recurrent_model(torch: Any, batch: ProfiledMtfRaggedSequenceBatch) -> Any:
    class RecurrentAutoencoder(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.encoders = torch.nn.ModuleList(
                [
                    torch.nn.GRU(
                        input_size=PROFILED_MTF_RAGGED_SEQUENCE_FEATURE_WIDTH,
                        hidden_size=PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_HIDDEN_WIDTH,
                        batch_first=True,
                    )
                    for _ in batch.frames
                ]
            )
            self.decoders = torch.nn.ModuleList(
                [
                    torch.nn.Linear(
                        PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_HIDDEN_WIDTH,
                        PROFILED_MTF_RAGGED_SEQUENCE_FEATURE_WIDTH,
                    )
                    for _ in batch.frames
                ]
            )

        def forward(self, frames: Sequence[Any]) -> tuple[Any, ...]:
            return tuple(
                decoder(encoder(frame)[0])
                for encoder, decoder, frame in zip(
                    self.encoders,
                    self.decoders,
                    frames,
                    strict=True,
                )
            )

    return RecurrentAutoencoder()


def _causal_tcn_model(torch: Any, batch: ProfiledMtfRaggedSequenceBatch) -> Any:
    class CausalTcnAutoencoder(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.encoders = torch.nn.ModuleList(
                [
                    torch.nn.Conv1d(
                        PROFILED_MTF_RAGGED_SEQUENCE_FEATURE_WIDTH,
                        PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_HIDDEN_WIDTH,
                        kernel_size=3,
                    )
                    for _ in batch.frames
                ]
            )
            self.decoders = torch.nn.ModuleList(
                [
                    torch.nn.Conv1d(
                        PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_HIDDEN_WIDTH,
                        PROFILED_MTF_RAGGED_SEQUENCE_FEATURE_WIDTH,
                        kernel_size=1,
                    )
                    for _ in batch.frames
                ]
            )

        def forward(self, frames: Sequence[Any]) -> tuple[Any, ...]:
            return tuple(
                decoder(
                    torch.relu(
                        encoder(torch.nn.functional.pad(frame.transpose(1, 2), (2, 0)))
                    )
                ).transpose(1, 2)
                for encoder, decoder, frame in zip(
                    self.encoders,
                    self.decoders,
                    frames,
                    strict=True,
                )
            )

    return CausalTcnAutoencoder()


def _attention_model(torch: Any, batch: ProfiledMtfRaggedSequenceBatch) -> Any:
    class MaskedAttentionAutoencoder(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            hidden_width = PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_HIDDEN_WIDTH
            self.input_projection = torch.nn.Linear(
                PROFILED_MTF_RAGGED_SEQUENCE_FEATURE_WIDTH,
                hidden_width,
            )
            self.timeframe_embedding = torch.nn.Embedding(len(batch.frames), hidden_width)
            self.position_embedding = torch.nn.Embedding(
                max(frame.sequence_length for frame in batch.frames),
                hidden_width,
            )
            self.attention = torch.nn.MultiheadAttention(
                hidden_width,
                num_heads=1,
                batch_first=True,
            )
            self.output_projection = torch.nn.Linear(
                hidden_width,
                PROFILED_MTF_RAGGED_SEQUENCE_FEATURE_WIDTH,
            )
            timeframe_ids: list[int] = []
            position_ids: list[int] = []
            for frame_index, frame in enumerate(batch.frames):
                timeframe_ids.extend([frame_index] * frame.sequence_length)
                position_ids.extend(range(frame.sequence_length))
            self.register_buffer(
                "timeframe_ids",
                torch.tensor(timeframe_ids, dtype=torch.long),
                persistent=False,
            )
            self.register_buffer(
                "position_ids",
                torch.tensor(position_ids, dtype=torch.long),
                persistent=False,
            )

        def forward(self, frames: Sequence[Any], masks: Sequence[Any]) -> tuple[Any, Any, Any]:
            tokens = torch.cat(tuple(frames), dim=1)
            validity = torch.cat(tuple(masks), dim=1)
            features = self.input_projection(tokens)
            features = features + self.timeframe_embedding(self.timeframe_ids).unsqueeze(0)
            features = features + self.position_embedding(self.position_ids).unsqueeze(0)
            attended, _ = self.attention(
                features,
                features,
                features,
                key_padding_mask=~validity,
                need_weights=False,
            )
            return self.output_projection(attended), tokens, validity

    return MaskedAttentionAutoencoder()


def _family_loss(
    torch: Any,
    model: Any,
    mode: Literal["frames", "attention"],
    frames: Sequence[Any],
    masks: Sequence[Any],
) -> Any:
    if mode == "attention":
        reconstruction, target, mask = model(frames, masks)
        return _masked_mse(torch, reconstruction, target, mask)
    reconstructions = model(frames)
    losses = tuple(
        _masked_mse(torch, reconstruction, target, mask)
        for reconstruction, target, mask in zip(reconstructions, frames, masks, strict=True)
    )
    return torch.stack(losses).mean()


def _masked_mse(torch: Any, reconstruction: Any, target: Any, mask: Any) -> Any:
    if (
        tuple(reconstruction.shape) != tuple(target.shape)
        or tuple(mask.shape) != tuple(target.shape[:2])
    ):
        raise ValueError("ragged sequence masked reconstruction geometry is invalid")
    weights = mask.unsqueeze(-1).to(dtype=target.dtype)
    denominator = weights.sum() * target.shape[-1]
    if not bool(torch.isfinite(denominator).item()) or float(denominator.item()) <= 0:
        raise ValueError("ragged sequence mask has no available values")
    return ((reconstruction - target) ** 2 * weights).sum() / denominator


def _write_completed_run(
    contract: ProfiledMtfRaggedSequenceRuntimeContract,
    *,
    phase: RuntimePhase,
    device: Literal["cpu", "cuda"],
    metrics: Mapping[str, object],
) -> ProfiledMtfRaggedSequenceRuntimeRun:
    return _write_run(
        contract,
        phase=phase,
        status="completed",
        device=device,
        steps_completed=_required_metric_steps(metrics),
        runtime_metrics=metrics,
    )


def _write_unavailable_run(
    contract: ProfiledMtfRaggedSequenceRuntimeContract,
    *,
    phase: RuntimePhase,
    reason: str,
) -> ProfiledMtfRaggedSequenceRuntimeRun:
    return _write_run(
        contract,
        phase=phase,
        status="runtime_unavailable",
        device="unavailable",
        steps_completed=0,
        runtime_metrics={
            "control_count": contract.batch.control_count,
            "native_sequence_lengths": [frame.sequence_length for frame in contract.batch.frames],
            "feature_width": PROFILED_MTF_RAGGED_SEQUENCE_FEATURE_WIDTH,
            "token_count": contract.batch.token_count,
            "reason": reason,
            "structure_conclusion": "not_assessed_low_sample",
        },
    )


def _write_run(
    contract: ProfiledMtfRaggedSequenceRuntimeContract,
    *,
    phase: RuntimePhase,
    status: RuntimeRunStatus,
    device: RuntimeDevice,
    steps_completed: int,
    runtime_metrics: Mapping[str, object],
) -> ProfiledMtfRaggedSequenceRuntimeRun:
    path = _summary_path(contract, phase=phase)
    payload = _signed_payload(
        {
            "schema_version": SCHEMA_VERSION,
            "campaign_id": PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_ID,
            "campaign_contract_sha256": contract.contract_sha256,
            "source_inventory_sha256": contract.source.inventory.inventory_sha256,
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
    contract: ProfiledMtfRaggedSequenceRuntimeContract,
    *,
    phase: RuntimePhase,
) -> ProfiledMtfRaggedSequenceRuntimeRun | None:
    path = _summary_path(contract, phase=phase)
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise ValueError("ragged sequence runtime summary is invalid")
    payload = _read_json_object(path)
    _verify_signed_payload(payload, field_name="summary_sha256")
    if (
        payload.get("campaign_id") != PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_ID
        or payload.get("campaign_contract_sha256") != contract.contract_sha256
        or payload.get("source_inventory_sha256") != contract.source.inventory.inventory_sha256
        or payload.get("batch_sha256") != contract.batch.batch_sha256
        or payload.get("phase") != phase
    ):
        raise ValueError("ragged sequence runtime summary is malformed for its contract")
    return _run_from_payload(payload, path=path)


def _run_from_payload(
    payload: Mapping[str, object],
    *,
    path: Path,
) -> ProfiledMtfRaggedSequenceRuntimeRun:
    status = payload.get("status")
    device = payload.get("device")
    phase = payload.get("phase")
    metrics = payload.get("runtime_metrics")
    steps_completed = payload.get("steps_completed")
    if (
        status not in {"completed", "runtime_unavailable"}
        or device not in {"cpu", "cuda", "unavailable"}
        or phase not in {"cpu", "cuda"}
        or not isinstance(metrics, dict)
        or type(steps_completed) is not int
    ):
        raise ValueError("ragged sequence runtime summary is malformed")
    return ProfiledMtfRaggedSequenceRuntimeRun(
        contract_sha256=_required_payload_sha256(payload, "campaign_contract_sha256"),
        phase=phase,
        status=status,
        device=device,
        steps_completed=steps_completed,
        summary_path=path,
        summary_sha256=_required_payload_sha256(payload, "summary_sha256"),
        runtime_metrics=metrics,
    )


def _require_completed_cpu_run(contract: ProfiledMtfRaggedSequenceRuntimeContract) -> None:
    cpu_run = _load_existing_run(contract, phase="cpu")
    if (
        cpu_run is None
        or cpu_run.status != "completed"
        or cpu_run.device != "cpu"
        or cpu_run.steps_completed
        != _total_steps(PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_CPU_STEPS_PER_FAMILY)
    ):
        raise ValueError("a completed matching CPU runtime receipt is required before CUDA")


def _with_cuda_outcome(
    contract: ProfiledMtfRaggedSequenceRuntimeContract,
    run: ProfiledMtfRaggedSequenceRuntimeRun,
) -> ProfiledMtfRaggedSequenceRuntimeRun:
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


def _frames_from_control(
    control: ProfiledMtfFlattenedControl,
) -> tuple[ProfiledMtfRaggedSequenceFrame, ...]:
    expected = _expected_frames(control.profile_id)
    if len(control.blocks) != len(expected):
        raise ValueError("ragged sequence control frame count is invalid")
    for block, frame in zip(control.blocks, expected, strict=True):
        if (
            block.timeframe != frame.timeframe
            or block.feature_offset != frame.source_feature_offset
            or block.bar_count != frame.sequence_length
            or block.feature_width != frame.sequence_length * frame.feature_width
            or block.window_end > control.cutoff
        ):
            raise ValueError("ragged sequence control frame geometry is invalid")
    return expected


def _expected_frames(profile_id: str) -> tuple[ProfiledMtfRaggedSequenceFrame, ...]:
    if profile_id != PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_PROFILE_ID:
        raise ValueError("ragged sequence profile is invalid")
    profile = CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG.profile(profile_id)
    feature_offset = 0
    token_offset = 0
    frames: list[ProfiledMtfRaggedSequenceFrame] = []
    for timeframe in SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES:
        sequence_length = profile.lookbacks[timeframe]
        frame = ProfiledMtfRaggedSequenceFrame(
            timeframe=timeframe,
            source_feature_offset=feature_offset,
            sequence_length=sequence_length,
            token_offset=token_offset,
        )
        frames.append(frame)
        feature_offset += frame.sequence_length * frame.feature_width
        token_offset += frame.sequence_length
    return tuple(frames)


def _sequences_from_control(
    control: ProfiledMtfFlattenedControl,
    frames: Sequence[ProfiledMtfRaggedSequenceFrame],
) -> tuple[tuple[tuple[float, ...], ...], ...]:
    values = tuple(control.flattened_values)
    sequences: list[tuple[tuple[float, ...], ...]] = []
    for frame in frames:
        end = frame.source_feature_offset + frame.sequence_length * frame.feature_width
        segment = values[frame.source_feature_offset : end]
        if len(segment) != frame.sequence_length * frame.feature_width:
            raise ValueError("ragged sequence control values are incomplete")
        rows = tuple(
            tuple(float(value) for value in segment[index : index + frame.feature_width])
            for index in range(0, len(segment), frame.feature_width)
        )
        if any(not math.isfinite(value) for row in rows for value in row):
            raise ValueError("ragged sequence control values are not finite")
        sequences.append(rows)
    return tuple(sequences)


def _summary_path(
    contract: ProfiledMtfRaggedSequenceRuntimeContract,
    *,
    phase: RuntimePhase,
) -> Path:
    return contract.run_directory / f"{phase}-summary.json"


def _configure_torch_determinism(
    torch: Any,
    *,
    device_name: Literal["cpu", "cuda"],
    seed: int = PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_SEED,
) -> None:
    torch.manual_seed(seed)
    if device_name == "cuda":
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True
    torch.use_deterministic_algorithms(True)


def _finite_scalar(value: Any) -> float:
    scalar = float(value.detach().cpu().item())
    if not math.isfinite(scalar):
        raise ValueError("ragged sequence runtime scalar is not finite")
    return round(scalar, 10)


def _required_metric_steps(metrics: Mapping[str, object]) -> int:
    value = metrics.get("steps_completed")
    if type(value) is not int or value <= 0:
        raise ValueError("ragged sequence runtime completed metrics are invalid")
    return value


def _total_steps(steps_per_family: int) -> int:
    return steps_per_family * len(PROFILED_MTF_RAGGED_SEQUENCE_FAMILIES)


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


def _ragged_batch_sha256(
    *,
    source_inventory_sha256: str,
    source_batch_sha256: str,
    profile_id: str,
    source_contract_sha256: str,
    source_dataset_hashes: Sequence[str],
    catalog_sha256: str,
    layout_sha256: str,
    control_sha256s: Sequence[str],
) -> str:
    return _sha256_json(
        {
            "source_inventory_sha256": source_inventory_sha256,
            "source_batch_sha256": source_batch_sha256,
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
        raise ValueError("ragged sequence signed payload already has its checksum")
    completed = dict(payload)
    completed[field_name] = _sha256_json(completed)
    return completed


def _verify_signed_payload(payload: Mapping[str, object], *, field_name: str) -> str:
    digest = payload.get(field_name)
    unsigned = dict(payload)
    unsigned.pop(field_name, None)
    if not isinstance(digest, str) or digest != _sha256_json(unsigned):
        raise ValueError("ragged sequence artifact checksum is invalid")
    return digest


def _write_or_verify_json(path: Path, payload: Mapping[str, object]) -> dict[str, object]:
    if path.is_symlink():
        raise ValueError("ragged sequence artifact path must not be a link")
    encoded = _canonical_json(payload)
    if path.exists():
        existing = _read_json_object(path)
        if _canonical_json(existing) != encoded:
            raise ValueError("ragged sequence artifact conflicts with the frozen contract")
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
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("ragged sequence artifact is malformed") from error
    if not isinstance(payload, dict):
        raise ValueError("ragged sequence artifact must be an object")
    return payload


def _required_payload_sha256(payload: Mapping[str, object], field_name: str) -> str:
    value = payload.get(field_name)
    if not _is_sha256(value):
        raise ValueError("ragged sequence artifact hash is invalid")
    return value


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
        raise ValueError(f"{field_name} must be a SHA-256 identity")


def _require_attempt_id(value: str) -> None:
    if _ATTEMPT_ID_PATTERN.fullmatch(value) is None:
        raise ValueError("ragged sequence runtime attempt_id is invalid")


def _torch() -> Any:
    import torch

    return torch
