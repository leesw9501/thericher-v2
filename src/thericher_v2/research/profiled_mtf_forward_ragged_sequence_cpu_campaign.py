"""Fixed CPU-only native-ragged sequence controls for profiled MTF forward data.

The module is deliberately a small predictive campaign rather than a general
deep-learning runtime.  It opens labels only after the immutable D:-only
dataset receipt and materialization have been reattested, keeps all sequence
values and model state in memory, and persists source-safe hashes and counts
only.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, Literal

from thericher_v2.contracts import SCHEMA_VERSION, Timeframe
from thericher_v2.data.us_equity_session import US_EQUITY_EASTERN, us_equity_2026_session
from thericher_v2.models.sequence_window import SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES

from .artifact_paths import ensure_external_artifact_directory
from .causal_mtf_window_profile_feasibility import (
    CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG,
)
from .kis_mtf_profiled_feature_input_preflight import (
    build_target_free_mtf_feature_projection,
    resample_completed_causal_prefix,
)
from .profiled_mtf_forward_supervised_dataset import (
    PROFILED_MTF_FORWARD_SUPERVISED_DATASET_PAIR_COUNT,
    PROFILED_MTF_FORWARD_SUPERVISED_DATASET_TEMPORAL_SPLIT,
    ProfiledMtfForwardSupervisedDatasetMaterialization,
    ProfiledMtfForwardSupervisedDatasetReceipt,
)

PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_CAMPAIGN_ID: Final = (
    "profiled-mtf-forward-ragged-sequence-cpu-campaign-v1"
)
PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_PROFILE_ID: Final = "short"
PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_FEATURE_WIDTH: Final = 2
PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_SEED: Final = 641
PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_EPOCH_COUNT: Final = 8
PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_LEARNING_RATE: Final = 0.01
PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_HIDDEN_WIDTH: Final = 4
PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_TCN_KERNEL_SIZE: Final = 3
PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_ATTENTION_HEADS: Final = 1
PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_FAMILY_IDS: Final = (
    "per_timeframe_recurrent",
    "causal_tcn",
    "masked_cross_timeframe_attention",
)
PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_CANDIDATE_IDS: Final = (
    "no_trade_zero",
    *PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_FAMILY_IDS,
)
PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_METRIC_NAMES: Final = (
    "validation_mse",
    "validation_directional_hit_rate",
    "permuted_validation_mse",
    "permuted_validation_directional_hit_rate",
)
PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_MASK_POLICY: Final = {
    "native_timeframe_sequences_preserved": True,
    "cross_timeframe_row_alignment": "none",
    "per_timeframe_padding_mask": "explicit_validity_mask",
    "attention_mask": "availability_only_not_global_temporal_order",
    "within_timeframe_position": "oldest_to_newest_causal_rank",
}
_ATTEMPT_ID_PATTERN: Final = re.compile(r"^[A-Za-z0-9._-]{1,80}$", re.ASCII)

CampaignStatus = Literal[
    "input_unavailable",
    "cpu_runtime_unavailable",
    "cpu_evaluated_not_promoting",
]


@dataclass(frozen=True, slots=True)
class ProfiledMtfForwardRaggedSequenceFrame:
    """One native timeframe sequence; token order is not cross-timeframe alignment."""

    timeframe: Timeframe
    sequence_length: int
    token_offset: int
    feature_width: int = PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_FEATURE_WIDTH

    def __post_init__(self) -> None:
        if (
            self.timeframe not in SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES
            or self.sequence_length <= 0
            or self.token_offset < 0
            or self.feature_width != PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_FEATURE_WIDTH
        ):
            raise ValueError("ragged sequence frame geometry is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "timeframe": self.timeframe.value,
            "sequence_length": self.sequence_length,
            "token_offset": self.token_offset,
            "feature_width": self.feature_width,
        }


@dataclass(frozen=True, slots=True)
class ProfiledMtfForwardRaggedSequenceInputBatch:
    """D:-backed causal sequences, retained in memory and represented safely by hashes."""

    dataset_contract_sha256: str
    row_keys: tuple[tuple[int, int, str, str], ...]
    frames: tuple[ProfiledMtfForwardRaggedSequenceFrame, ...]
    sequences: tuple[tuple[tuple[tuple[Decimal, ...], ...], ...], ...] = field(
        repr=False
    )
    validity_masks: tuple[tuple[tuple[bool, ...], ...], ...] = field(repr=False)
    projection_sha256s: tuple[str, ...]
    input_batch_sha256: str

    def __post_init__(self) -> None:
        keys = tuple(self.row_keys)
        frames = tuple(self.frames)
        sequences = tuple(
            tuple(tuple(tuple(row) for row in frame) for frame in control)
            for control in self.sequences
        )
        masks = tuple(
            tuple(tuple(tuple(bool(value) for value in frame) for frame in control))
            for control in self.validity_masks
        )
        projections = tuple(self.projection_sha256s)
        expected_rows = PROFILED_MTF_FORWARD_SUPERVISED_DATASET_PAIR_COUNT * 2
        if (
            not _is_sha256(self.dataset_contract_sha256)
            or len(keys) != expected_rows
            or len(sequences) != expected_rows
            or len(masks) != expected_rows
            or len(projections) != expected_rows
            or frames != _expected_frames()
            or any(not _valid_row_key(key) for key in keys)
            or any(not _is_sha256(value) for value in projections)
        ):
            raise ValueError("ragged sequence input batch identity is invalid")
        for control_frames, control_masks in zip(sequences, masks, strict=True):
            if len(control_frames) != len(frames) or len(control_masks) != len(frames):
                raise ValueError("ragged sequence input frame count is invalid")
            for frame, rows, mask in zip(frames, control_frames, control_masks, strict=True):
                if (
                    len(rows) != frame.sequence_length
                    or len(mask) != frame.sequence_length
                    or any(len(row) != frame.feature_width for row in rows)
                    or any(
                        not isinstance(value, Decimal) or not value.is_finite()
                        for row in rows
                        for value in row
                    )
                    or not all(mask)
                ):
                    raise ValueError("ragged sequence input values or mask are invalid")
        expected_hash = _input_batch_sha256(
            dataset_contract_sha256=self.dataset_contract_sha256,
            row_keys=keys,
            frames=frames,
            sequences=sequences,
            validity_masks=masks,
            projection_sha256s=projections,
        )
        if self.input_batch_sha256 != expected_hash:
            raise ValueError("ragged sequence input batch hash is invalid")
        object.__setattr__(self, "row_keys", keys)
        object.__setattr__(self, "frames", frames)
        object.__setattr__(self, "sequences", sequences)
        object.__setattr__(self, "validity_masks", masks)
        object.__setattr__(self, "projection_sha256s", projections)

    @property
    def control_count(self) -> int:
        return len(self.sequences)

    @property
    def token_count(self) -> int:
        return sum(frame.sequence_length for frame in self.frames)

    def safe_payload(self) -> dict[str, object]:
        return {
            "dataset_contract_sha256": self.dataset_contract_sha256,
            "control_count": self.control_count,
            "frames": [frame.safe_payload() for frame in self.frames],
            "token_count": self.token_count,
            "mask_policy": PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_MASK_POLICY,
            "input_batch_sha256": self.input_batch_sha256,
        }


@dataclass(frozen=True, slots=True)
class ProfiledMtfForwardRaggedSequenceCpuCampaignPolicy:
    """The immutable single-pass contract before the D:-only targets are opened."""

    dataset_receipt_sha256: str
    dataset_policy_sha256: str
    dataset_result_sha256: str
    dataset_contract_sha256: str | None
    code_revision_sha256: str
    policy_sha256: str

    def __post_init__(self) -> None:
        if (
            not all(
                _is_sha256(value)
                for value in (
                    self.dataset_receipt_sha256,
                    self.dataset_policy_sha256,
                    self.dataset_result_sha256,
                    self.code_revision_sha256,
                    self.policy_sha256,
                )
            )
            or (
                self.dataset_contract_sha256 is not None
                and not _is_sha256(self.dataset_contract_sha256)
            )
            or self.policy_sha256 != _sha256_json(_policy_unsigned_payload(self))
        ):
            raise ValueError("ragged sequence CPU campaign policy is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {**_policy_unsigned_payload(self), "policy_sha256": self.policy_sha256}


@dataclass(frozen=True, slots=True)
class ProfiledMtfForwardRaggedSequenceCpuCandidateMetric:
    """In-memory numerical evidence for one fixed family, never a selection result."""

    candidate_id: str
    validation_mse: float = field(repr=False)
    validation_directional_hit_rate: float = field(repr=False)
    permuted_validation_mse: float = field(repr=False)
    permuted_validation_directional_hit_rate: float = field(repr=False)
    evidence_sha256: str

    def __post_init__(self) -> None:
        values = (
            self.validation_mse,
            self.validation_directional_hit_rate,
            self.permuted_validation_mse,
            self.permuted_validation_directional_hit_rate,
        )
        if (
            self.candidate_id not in PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_CANDIDATE_IDS
            or any(not math.isfinite(value) for value in values)
            or self.validation_mse < 0
            or self.permuted_validation_mse < 0
            or not 0 <= self.validation_directional_hit_rate <= 1
            or not 0 <= self.permuted_validation_directional_hit_rate <= 1
            or self.evidence_sha256 != _candidate_evidence_sha256(self)
        ):
            raise ValueError("ragged sequence CPU candidate metric is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "metric_names": list(PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_METRIC_NAMES),
            "metric_evidence_sha256": self.evidence_sha256,
        }


@dataclass(frozen=True, slots=True)
class ProfiledMtfForwardRaggedSequenceCpuCampaignResult:
    """A source-safe outcome which intentionally leaves values and weights in memory."""

    policy_sha256: str
    dataset_receipt_sha256: str
    dataset_result_sha256: str
    status: CampaignStatus
    input_batch_sha256: str | None
    train_row_count: int
    purge_row_count: int
    validation_row_count: int
    candidate_metrics: tuple[ProfiledMtfForwardRaggedSequenceCpuCandidateMetric, ...] = field(
        repr=False
    )
    result_sha256: str = ""

    def __post_init__(self) -> None:
        metrics = tuple(self.candidate_metrics)
        evaluated = self.status == "cpu_evaluated_not_promoting"
        expected_counts = (40, 4, 16) if evaluated else (0, 0, 0)
        if (
            not all(
                _is_sha256(value)
                for value in (
                    self.policy_sha256,
                    self.dataset_receipt_sha256,
                    self.dataset_result_sha256,
                    self.result_sha256,
                )
            )
            or (self.input_batch_sha256 is not None) != evaluated
            or (self.input_batch_sha256 is not None and not _is_sha256(self.input_batch_sha256))
            or (self.train_row_count, self.purge_row_count, self.validation_row_count)
            != expected_counts
            or (
                tuple(metric.candidate_id for metric in metrics)
                != PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_CANDIDATE_IDS
                if evaluated
                else metrics != ()
            )
            or self.status
            not in {"input_unavailable", "cpu_runtime_unavailable", "cpu_evaluated_not_promoting"}
            or self.result_sha256 != _result_sha256(self)
        ):
            raise ValueError("ragged sequence CPU campaign result is invalid")
        object.__setattr__(self, "candidate_metrics", metrics)

    def safe_payload(self) -> dict[str, object]:
        return {
            "campaign_id": PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_CAMPAIGN_ID,
            "policy_sha256": self.policy_sha256,
            "dataset_receipt_sha256": self.dataset_receipt_sha256,
            "dataset_result_sha256": self.dataset_result_sha256,
            "status": self.status,
            "input_batch_sha256": self.input_batch_sha256,
            "pair_split": {
                "train_row_count": self.train_row_count,
                "purge_row_count": self.purge_row_count,
                "validation_row_count": self.validation_row_count,
            },
            "candidate_metrics": [metric.safe_payload() for metric in self.candidate_metrics],
            "scope": _result_scope(cpu_trained=self.status == "cpu_evaluated_not_promoting"),
            "result_sha256": self.result_sha256,
        }


@dataclass(frozen=True, slots=True)
class ProfiledMtfForwardRaggedSequenceCpuCampaignReceipt:
    """One external receipt whose body excludes data values and model state."""

    policy: ProfiledMtfForwardRaggedSequenceCpuCampaignPolicy = field(repr=False)
    result: ProfiledMtfForwardRaggedSequenceCpuCampaignResult = field(repr=False)
    receipt_path: Path
    receipt_sha256: str

    def __post_init__(self) -> None:
        if (
            self.receipt_path.name != "campaign-receipt.json"
            or self.receipt_path.is_symlink()
            or not _is_sha256(self.receipt_sha256)
            or self.result.policy_sha256 != self.policy.policy_sha256
        ):
            raise ValueError("ragged sequence CPU campaign receipt is invalid")


def freeze_profiled_mtf_forward_ragged_sequence_cpu_campaign_policy(
    dataset_receipt: ProfiledMtfForwardSupervisedDatasetReceipt,
    *,
    code_revision_sha256: str,
) -> ProfiledMtfForwardRaggedSequenceCpuCampaignPolicy:
    """Predeclare the three fixed CPU families before labels are opened."""

    _require_sha256(code_revision_sha256, "code_revision_sha256")
    result = dataset_receipt.result
    return ProfiledMtfForwardRaggedSequenceCpuCampaignPolicy(
        dataset_receipt_sha256=dataset_receipt.receipt_sha256,
        dataset_policy_sha256=dataset_receipt.policy.policy_sha256,
        dataset_result_sha256=result.result_sha256,
        dataset_contract_sha256=result.dataset_contract_sha256,
        code_revision_sha256=code_revision_sha256,
        policy_sha256=_sha256_json(
            _policy_unsigned_payload_from_fields(
                dataset_receipt_sha256=dataset_receipt.receipt_sha256,
                dataset_policy_sha256=dataset_receipt.policy.policy_sha256,
                dataset_result_sha256=result.result_sha256,
                dataset_contract_sha256=result.dataset_contract_sha256,
                code_revision_sha256=code_revision_sha256,
            )
        ),
    )


def build_profiled_mtf_forward_ragged_sequence_input_batch(
    materialization: ProfiledMtfForwardSupervisedDatasetMaterialization,
) -> ProfiledMtfForwardRaggedSequenceInputBatch:
    """Build native per-timeframe sequences from completed 15:30 inputs only."""

    dataset_result = materialization.receipt.result
    if dataset_result.dataset_contract_sha256 is None:
        raise ValueError("ragged sequence campaign dataset contract is unavailable")
    frames = _expected_frames()
    row_keys: list[tuple[int, int, str, str]] = []
    controls: list[tuple[tuple[tuple[Decimal, ...], ...], ...]] = []
    masks: list[tuple[tuple[bool, ...], ...]] = []
    projection_sha256s: list[str] = []
    for row in materialization.rows:
        snapshot = materialization.snapshots[row.pair_index]
        minute_bars = snapshot.input_prefixes[row.leg_index]
        cutoff = row.input_end
        session = _regular_session_for_cutoff(cutoff)
        projection = build_target_free_mtf_feature_projection(
            source_contract_sha256=dataset_result.dataset_contract_sha256,
            source_dataset_hash=row.raw_snapshot_sha256,
            catalog=CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG,
            profile_id=PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_PROFILE_ID,
            minute_bars=minute_bars,
            bars_by_timeframe=resample_completed_causal_prefix(
                minute_bars,
                session=session.window,
                cutoff=cutoff,
            ),
            cutoff=cutoff,
        )
        if projection.feature_timestamp > cutoff or not projection.completed_bar_status:
            raise ValueError("ragged sequence input uses noncausal bars")
        control_frames: list[tuple[tuple[Decimal, ...], ...]] = []
        control_masks: list[tuple[bool, ...]] = []
        for frame in frames:
            rows = tuple(tuple(values) for values in projection.feature_values[frame.timeframe])
            sequence = projection.window.windows[frame.timeframe]
            if (
                len(rows) != frame.sequence_length
                or len(sequence.bars) != frame.sequence_length
                or sequence.end_ts > cutoff
            ):
                raise ValueError("ragged sequence input geometry changed")
            control_frames.append(rows)
            control_masks.append(tuple(True for _ in rows))
        row_keys.append((row.pair_index, row.leg_index, row.split, row.raw_snapshot_sha256))
        controls.append(tuple(control_frames))
        masks.append(tuple(control_masks))
        projection_sha256s.append(projection.projection_sha256)
    control_tuple = tuple(controls)
    mask_tuple = tuple(masks)
    key_tuple = tuple(row_keys)
    projection_tuple = tuple(projection_sha256s)
    return ProfiledMtfForwardRaggedSequenceInputBatch(
        dataset_contract_sha256=dataset_result.dataset_contract_sha256,
        row_keys=key_tuple,
        frames=frames,
        sequences=control_tuple,
        validity_masks=mask_tuple,
        projection_sha256s=projection_tuple,
        input_batch_sha256=_input_batch_sha256(
            dataset_contract_sha256=dataset_result.dataset_contract_sha256,
            row_keys=key_tuple,
            frames=frames,
            sequences=control_tuple,
            validity_masks=mask_tuple,
            projection_sha256s=projection_tuple,
        ),
    )


def run_profiled_mtf_forward_ragged_sequence_cpu_campaign(
    policy: ProfiledMtfForwardRaggedSequenceCpuCampaignPolicy,
    *,
    dataset_receipt: ProfiledMtfForwardSupervisedDatasetReceipt,
    materialization: ProfiledMtfForwardSupervisedDatasetMaterialization | None,
) -> ProfiledMtfForwardRaggedSequenceCpuCampaignResult:
    """Run exactly one fixed CPU pass and one pair-block permutation counterpart."""

    _reattest_policy(
        policy=policy,
        dataset_receipt=dataset_receipt,
        materialization=materialization,
    )
    if materialization is None:
        return _unavailable_result(policy=policy, status="input_unavailable")
    batch = build_profiled_mtf_forward_ragged_sequence_input_batch(materialization)
    try:
        torch = _torch()
    except ModuleNotFoundError:
        return _unavailable_result(policy=policy, status="cpu_runtime_unavailable")
    metrics = _evaluate_fixed_cpu_families(torch, batch, materialization)
    return _evaluated_result(policy=policy, batch=batch, metrics=metrics)


def write_profiled_mtf_forward_ragged_sequence_cpu_campaign_receipt(
    result: ProfiledMtfForwardRaggedSequenceCpuCampaignResult,
    *,
    policy: ProfiledMtfForwardRaggedSequenceCpuCampaignPolicy,
    artifact_root: Path | str,
    repo_root: Path | str,
    attempt_id: str,
) -> ProfiledMtfForwardRaggedSequenceCpuCampaignReceipt:
    """Write source-safe evidence outside Git without checkpoints or values."""

    _require_attempt_id(attempt_id)
    if result.policy_sha256 != policy.policy_sha256:
        raise ValueError("ragged sequence CPU campaign result policy changed")
    directory = ensure_external_artifact_directory(
        Path(artifact_root),
        Path(repo_root),
        "research",
        PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_CAMPAIGN_ID,
        attempt_id,
    )
    unsigned_payload = {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_CAMPAIGN_ID,
        "attempt_id": attempt_id,
        "policy": policy.safe_payload(),
        "result": result.safe_payload(),
        "artifact_policy": _artifact_policy(),
    }
    payload = {**unsigned_payload, "receipt_sha256": _sha256_json(unsigned_payload)}
    receipt_path = directory / "campaign-receipt.json"
    _write_or_verify_json(receipt_path, payload)
    return ProfiledMtfForwardRaggedSequenceCpuCampaignReceipt(
        policy=policy,
        result=result,
        receipt_path=receipt_path,
        receipt_sha256=payload["receipt_sha256"],
    )


def _evaluate_fixed_cpu_families(
    torch: Any,
    batch: ProfiledMtfForwardRaggedSequenceInputBatch,
    materialization: ProfiledMtfForwardSupervisedDatasetMaterialization,
) -> tuple[ProfiledMtfForwardRaggedSequenceCpuCandidateMetric, ...]:
    rows = materialization.rows
    expected_keys = tuple(
        (row.pair_index, row.leg_index, row.split, row.raw_snapshot_sha256) for row in rows
    )
    if batch.row_keys != expected_keys:
        raise ValueError("ragged sequence input/target rows diverged")
    train_indices, purge_indices, validation_indices = _split_indices(batch.row_keys)
    if (len(train_indices), len(purge_indices), len(validation_indices)) != (40, 4, 16):
        raise ValueError("ragged sequence pair split changed")
    previous_threads = torch.get_num_threads()
    previous_determinism = bool(torch.are_deterministic_algorithms_enabled())
    try:
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)
        frames, masks = _input_tensors(torch, batch)
        targets = torch.tensor(
            [float(row.target_log_return) for row in rows],
            dtype=torch.float32,
            device=torch.device("cpu"),
        )
        train_frames = tuple(frame[train_indices] for frame in frames)
        train_masks = tuple(mask[train_indices] for mask in masks)
        validation_frames = tuple(frame[validation_indices] for frame in frames)
        validation_masks = tuple(mask[validation_indices] for mask in masks)
        train_targets = targets[train_indices]
        validation_targets = targets[validation_indices]
        reverse_indices = _pair_block_reversal_indices(len(train_indices) // 2)
        permuted_train_targets = train_targets[list(reverse_indices)]
        metrics: list[ProfiledMtfForwardRaggedSequenceCpuCandidateMetric] = []
        for family_index, candidate_id in enumerate(
            PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_CANDIDATE_IDS
        ):
            if candidate_id == "no_trade_zero":
                predictions = torch.zeros_like(validation_targets)
                permuted_predictions = torch.zeros_like(validation_targets)
            else:
                seed = PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_SEED + family_index
                predictions = _fit_and_predict(
                    torch,
                    family_id=candidate_id,
                    batch=batch,
                    train_frames=train_frames,
                    train_masks=train_masks,
                    train_targets=train_targets,
                    validation_frames=validation_frames,
                    validation_masks=validation_masks,
                    seed=seed,
                )
                permuted_predictions = _fit_and_predict(
                    torch,
                    family_id=candidate_id,
                    batch=batch,
                    train_frames=train_frames,
                    train_masks=train_masks,
                    train_targets=permuted_train_targets,
                    validation_frames=validation_frames,
                    validation_masks=validation_masks,
                    seed=seed,
                )
            metric_fields = {
                "candidate_id": candidate_id,
                "validation_mse": _mean_squared_error(torch, validation_targets, predictions),
                "validation_directional_hit_rate": _directional_hit_rate(
                    torch, validation_targets, predictions
                ),
                "permuted_validation_mse": _mean_squared_error(
                    torch, validation_targets, permuted_predictions
                ),
                "permuted_validation_directional_hit_rate": _directional_hit_rate(
                    torch, validation_targets, permuted_predictions
                ),
            }
            metrics.append(
                ProfiledMtfForwardRaggedSequenceCpuCandidateMetric(
                    **metric_fields,
                    evidence_sha256=_candidate_evidence_sha256_fields(metric_fields),
                )
            )
        return tuple(metrics)
    finally:
        torch.use_deterministic_algorithms(previous_determinism)
        torch.set_num_threads(previous_threads)


def _fit_and_predict(
    torch: Any,
    *,
    family_id: str,
    batch: ProfiledMtfForwardRaggedSequenceInputBatch,
    train_frames: Sequence[Any],
    train_masks: Sequence[Any],
    train_targets: Any,
    validation_frames: Sequence[Any],
    validation_masks: Sequence[Any],
    seed: int,
) -> Any:
    torch.manual_seed(seed)
    model = _family_model(torch, family_id=family_id, batch=batch)
    optimizer = torch.optim.SGD(
        model.parameters(),
        lr=PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_LEARNING_RATE,
    )
    for _ in range(PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_EPOCH_COUNT):
        optimizer.zero_grad()
        predictions = model(train_frames, train_masks)
        loss = torch.mean((predictions - train_targets) ** 2)
        if not bool(torch.isfinite(loss).item()):
            raise ValueError("ragged sequence CPU loss is not finite")
        loss.backward()
        optimizer.step()
    with torch.no_grad():
        predictions = model(validation_frames, validation_masks)
    if not bool(torch.isfinite(predictions).all().item()):
        raise ValueError("ragged sequence CPU predictions are not finite")
    return predictions.detach()


def _family_model(
    torch: Any,
    *,
    family_id: str,
    batch: ProfiledMtfForwardRaggedSequenceInputBatch,
) -> Any:
    if family_id == "per_timeframe_recurrent":
        return _recurrent_model(torch, batch)
    if family_id == "causal_tcn":
        return _causal_tcn_model(torch, batch)
    if family_id == "masked_cross_timeframe_attention":
        return _attention_model(torch, batch)
    raise ValueError("ragged sequence family is invalid")


def _recurrent_model(torch: Any, batch: ProfiledMtfForwardRaggedSequenceInputBatch) -> Any:
    class PerTimeframeRecurrent(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.encoders = torch.nn.ModuleList(
                [
                    torch.nn.GRU(
                        input_size=PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_FEATURE_WIDTH,
                        hidden_size=PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_HIDDEN_WIDTH,
                        batch_first=True,
                    )
                    for _ in batch.frames
                ]
            )
            self.head = torch.nn.Linear(
                len(batch.frames) * PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_HIDDEN_WIDTH,
                1,
            )

        def forward(self, frames: Sequence[Any], masks: Sequence[Any]) -> Any:
            encoded = tuple(
                _last_valid(torch, encoder(frame)[0], mask)
                for encoder, frame, mask in zip(self.encoders, frames, masks, strict=True)
            )
            return self.head(torch.cat(encoded, dim=1)).squeeze(-1)

    return PerTimeframeRecurrent()


def _causal_tcn_model(torch: Any, batch: ProfiledMtfForwardRaggedSequenceInputBatch) -> Any:
    class CausalTcn(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.encoders = torch.nn.ModuleList(
                [
                    torch.nn.Conv1d(
                        PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_FEATURE_WIDTH,
                        PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_HIDDEN_WIDTH,
                        kernel_size=PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_TCN_KERNEL_SIZE,
                    )
                    for _ in batch.frames
                ]
            )
            self.head = torch.nn.Linear(
                len(batch.frames) * PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_HIDDEN_WIDTH,
                1,
            )

        def forward(self, frames: Sequence[Any], masks: Sequence[Any]) -> Any:
            encoded = tuple(
                _last_valid(
                    torch,
                    torch.relu(
                        encoder(
                            torch.nn.functional.pad(
                                frame.transpose(1, 2),
                                (PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_TCN_KERNEL_SIZE - 1, 0),
                            )
                        )
                    ).transpose(1, 2),
                    mask,
                )
                for encoder, frame, mask in zip(self.encoders, frames, masks, strict=True)
            )
            return self.head(torch.cat(encoded, dim=1)).squeeze(-1)

    return CausalTcn()


def _attention_model(torch: Any, batch: ProfiledMtfForwardRaggedSequenceInputBatch) -> Any:
    class MaskedCrossTimeframeAttention(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            hidden_width = PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_HIDDEN_WIDTH
            self.input_projection = torch.nn.Linear(
                PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_FEATURE_WIDTH,
                hidden_width,
            )
            self.timeframe_embedding = torch.nn.Embedding(len(batch.frames), hidden_width)
            self.position_embedding = torch.nn.Embedding(
                max(frame.sequence_length for frame in batch.frames),
                hidden_width,
            )
            self.attention = torch.nn.MultiheadAttention(
                hidden_width,
                num_heads=PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_ATTENTION_HEADS,
                dropout=0.0,
                batch_first=True,
            )
            self.head = torch.nn.Linear(hidden_width, 1)
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

        def forward(self, frames: Sequence[Any], masks: Sequence[Any]) -> Any:
            tokens = torch.cat(tuple(frames), dim=1)
            validity = torch.cat(tuple(masks), dim=1)
            if not bool(validity.any(dim=1).all().item()):
                raise ValueError("ragged attention has no available tokens")
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
            weights = validity.unsqueeze(-1).to(dtype=attended.dtype)
            pooled = (attended * weights).sum(dim=1) / weights.sum(dim=1)
            return self.head(pooled).squeeze(-1)

    return MaskedCrossTimeframeAttention()


def _last_valid(torch: Any, encoded: Any, mask: Any) -> Any:
    if tuple(mask.shape) != tuple(encoded.shape[:2]):
        raise ValueError("ragged sequence mask geometry is invalid")
    lengths = mask.sum(dim=1)
    if not bool((lengths > 0).all().item()):
        raise ValueError("ragged sequence mask has no available values")
    indices = (lengths - 1).to(dtype=torch.long).view(-1, 1, 1)
    indices = indices.expand(-1, 1, encoded.shape[-1])
    return encoded.gather(1, indices).squeeze(1)


def _input_tensors(
    torch: Any,
    batch: ProfiledMtfForwardRaggedSequenceInputBatch,
) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
    device = torch.device("cpu")
    frames: list[Any] = []
    masks: list[Any] = []
    for frame_index, frame in enumerate(batch.frames):
        values = [
            [[float(value) for value in row] for row in control[frame_index]]
            for control in batch.sequences
        ]
        mask_values = [list(control[frame_index]) for control in batch.validity_masks]
        tensor = torch.tensor(values, dtype=torch.float32, device=device)
        mask = torch.tensor(mask_values, dtype=torch.bool, device=device)
        expected_shape = (
            batch.control_count,
            frame.sequence_length,
            PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_FEATURE_WIDTH,
        )
        if tuple(tensor.shape) != expected_shape or tuple(mask.shape) != expected_shape[:2]:
            raise ValueError("ragged sequence tensor geometry is invalid")
        if not bool(torch.isfinite(tensor).all().item()) or not bool(mask.all().item()):
            raise ValueError("ragged sequence tensor availability is invalid")
        frames.append(tensor)
        masks.append(mask)
    return tuple(frames), tuple(masks)


def _split_indices(
    row_keys: tuple[tuple[int, int, str, str], ...],
) -> tuple[list[int], list[int], list[int]]:
    train_indices = [index for index, key in enumerate(row_keys) if key[2] == "train"]
    purge_indices = [index for index, key in enumerate(row_keys) if key[2] == "purge"]
    validation_indices = [index for index, key in enumerate(row_keys) if key[2] == "validation"]
    expected_pairs = {
        "train": range(0, PROFILED_MTF_FORWARD_SUPERVISED_DATASET_TEMPORAL_SPLIT[0]),
        "purge": range(
            PROFILED_MTF_FORWARD_SUPERVISED_DATASET_TEMPORAL_SPLIT[0],
            sum(PROFILED_MTF_FORWARD_SUPERVISED_DATASET_TEMPORAL_SPLIT[:2]),
        ),
        "validation": range(
            sum(PROFILED_MTF_FORWARD_SUPERVISED_DATASET_TEMPORAL_SPLIT[:2]),
            PROFILED_MTF_FORWARD_SUPERVISED_DATASET_PAIR_COUNT,
        ),
    }
    for split, indices in (
        ("train", train_indices),
        ("purge", purge_indices),
        ("validation", validation_indices),
    ):
        if tuple((row_keys[index][0], row_keys[index][1]) for index in indices) != tuple(
            (pair_index, leg_index)
            for pair_index in expected_pairs[split]
            for leg_index in range(2)
        ):
            raise ValueError("ragged sequence pair split changed")
    return train_indices, purge_indices, validation_indices


def _pair_block_reversal_indices(pair_count: int) -> tuple[int, ...]:
    if pair_count != PROFILED_MTF_FORWARD_SUPERVISED_DATASET_TEMPORAL_SPLIT[0]:
        raise ValueError("ragged sequence target permutation pair count changed")
    return tuple(
        index
        for pair_index in reversed(range(pair_count))
        for index in (pair_index * 2, pair_index * 2 + 1)
    )


def _mean_squared_error(torch: Any, targets: Any, predictions: Any) -> float:
    return _finite_scalar(torch.mean((targets - predictions) ** 2))


def _directional_hit_rate(torch: Any, targets: Any, predictions: Any) -> float:
    values = ((predictions > 0.0) == (targets > 0.0)).to(dtype=torch.float32)
    return _finite_scalar(values.mean())


def _regular_session_for_cutoff(cutoff: datetime):
    eastern_date = cutoff.astimezone(US_EQUITY_EASTERN).date()
    session = us_equity_2026_session(eastern_date)
    if (
        session is None
        or session.kind != "regular"
        or cutoff.astimezone(US_EQUITY_EASTERN).time().replace(tzinfo=None) != time(15, 30)
    ):
        raise ValueError("ragged sequence causal session is invalid")
    return session


def _expected_frames() -> tuple[ProfiledMtfForwardRaggedSequenceFrame, ...]:
    profile = CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG.profile(
        PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_PROFILE_ID
    )
    token_offset = 0
    frames: list[ProfiledMtfForwardRaggedSequenceFrame] = []
    for timeframe in SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES:
        frame = ProfiledMtfForwardRaggedSequenceFrame(
            timeframe=timeframe,
            sequence_length=profile.lookbacks[timeframe],
            token_offset=token_offset,
        )
        frames.append(frame)
        token_offset += frame.sequence_length
    return tuple(frames)


def _reattest_policy(
    *,
    policy: ProfiledMtfForwardRaggedSequenceCpuCampaignPolicy,
    dataset_receipt: ProfiledMtfForwardSupervisedDatasetReceipt,
    materialization: ProfiledMtfForwardSupervisedDatasetMaterialization | None,
) -> None:
    result = dataset_receipt.result
    if (
        policy.dataset_receipt_sha256 != dataset_receipt.receipt_sha256
        or policy.dataset_policy_sha256 != dataset_receipt.policy.policy_sha256
        or policy.dataset_result_sha256 != result.result_sha256
        or policy.dataset_contract_sha256 != result.dataset_contract_sha256
    ):
        raise ValueError("ragged sequence campaign dataset receipt is stale or mismatched")
    if materialization is not None and materialization.receipt != dataset_receipt:
        raise ValueError("ragged sequence campaign materialization is stale or mismatched")
    if (materialization is not None) != (result.status == "materialized"):
        raise ValueError("ragged sequence campaign dataset availability is inconsistent")


def _unavailable_result(
    *,
    policy: ProfiledMtfForwardRaggedSequenceCpuCampaignPolicy,
    status: Literal["input_unavailable", "cpu_runtime_unavailable"],
) -> ProfiledMtfForwardRaggedSequenceCpuCampaignResult:
    fields = {
        "policy_sha256": policy.policy_sha256,
        "dataset_receipt_sha256": policy.dataset_receipt_sha256,
        "dataset_result_sha256": policy.dataset_result_sha256,
        "status": status,
        "input_batch_sha256": None,
        "train_row_count": 0,
        "purge_row_count": 0,
        "validation_row_count": 0,
        "candidate_metrics": (),
    }
    return ProfiledMtfForwardRaggedSequenceCpuCampaignResult(
        **fields,
        result_sha256=_result_sha256_fields(fields),
    )


def _evaluated_result(
    *,
    policy: ProfiledMtfForwardRaggedSequenceCpuCampaignPolicy,
    batch: ProfiledMtfForwardRaggedSequenceInputBatch,
    metrics: tuple[ProfiledMtfForwardRaggedSequenceCpuCandidateMetric, ...],
) -> ProfiledMtfForwardRaggedSequenceCpuCampaignResult:
    fields = {
        "policy_sha256": policy.policy_sha256,
        "dataset_receipt_sha256": policy.dataset_receipt_sha256,
        "dataset_result_sha256": policy.dataset_result_sha256,
        "status": "cpu_evaluated_not_promoting",
        "input_batch_sha256": batch.input_batch_sha256,
        "train_row_count": 40,
        "purge_row_count": 4,
        "validation_row_count": 16,
        "candidate_metrics": metrics,
    }
    return ProfiledMtfForwardRaggedSequenceCpuCampaignResult(
        **fields,
        result_sha256=_result_sha256_fields(fields),
    )


def _policy_unsigned_payload(
    policy: ProfiledMtfForwardRaggedSequenceCpuCampaignPolicy,
) -> dict[str, object]:
    return _policy_unsigned_payload_from_fields(
        dataset_receipt_sha256=policy.dataset_receipt_sha256,
        dataset_policy_sha256=policy.dataset_policy_sha256,
        dataset_result_sha256=policy.dataset_result_sha256,
        dataset_contract_sha256=policy.dataset_contract_sha256,
        code_revision_sha256=policy.code_revision_sha256,
    )


def _policy_unsigned_payload_from_fields(
    *,
    dataset_receipt_sha256: str,
    dataset_policy_sha256: str,
    dataset_result_sha256: str,
    dataset_contract_sha256: str | None,
    code_revision_sha256: str,
) -> dict[str, object]:
    return {
        "campaign_id": PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_CAMPAIGN_ID,
        "dataset_receipt_sha256": dataset_receipt_sha256,
        "dataset_policy_sha256": dataset_policy_sha256,
        "dataset_result_sha256": dataset_result_sha256,
        "dataset_contract_sha256": dataset_contract_sha256,
        "code_revision_sha256": code_revision_sha256,
        "ragged_input_contract": {
            "profile_id": PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_PROFILE_ID,
            "timeframes": [timeframe.value for timeframe in SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES],
            "native_sequence_lengths": [frame.sequence_length for frame in _expected_frames()],
            "per_bar_features": [
                "close_relative_to_first_completed_bar",
                "volume_relative_to_first_completed_bar_or_one",
            ],
            "input_cutoff": "15:30 America/New_York",
            "outcome_rows_used_as_features": False,
            "mask_policy": PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_MASK_POLICY,
        },
        "pair_level_temporal_split": {
            "train_pair_count": PROFILED_MTF_FORWARD_SUPERVISED_DATASET_TEMPORAL_SPLIT[0],
            "purge_pair_count": PROFILED_MTF_FORWARD_SUPERVISED_DATASET_TEMPORAL_SPLIT[1],
            "validation_pair_count": PROFILED_MTF_FORWARD_SUPERVISED_DATASET_TEMPORAL_SPLIT[2],
        },
        "baseline": "no_trade_zero_return",
        "fixed_cpu_families": [
            {
                "family_id": "per_timeframe_recurrent",
                "encoder": "per_timeframe_gru_last_valid_masked_state",
                "hidden_width": PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_HIDDEN_WIDTH,
            },
            {
                "family_id": "causal_tcn",
                "encoder": "per_timeframe_left_padded_causal_convolution_last_valid_masked_state",
                "hidden_width": PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_HIDDEN_WIDTH,
                "kernel_size": PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_TCN_KERNEL_SIZE,
            },
            {
                "family_id": "masked_cross_timeframe_attention",
                "encoder": "availability_masked_native_tokens_with_timeframe_and_rank_identity",
                "hidden_width": PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_HIDDEN_WIDTH,
                "attention_heads": PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_ATTENTION_HEADS,
            },
        ],
        "optimization": {
            "seed": PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_SEED,
            "optimizer": "sgd",
            "learning_rate": PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_LEARNING_RATE,
            "epochs_per_family": PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_EPOCH_COUNT,
            "loss": "mean_squared_error",
            "device": "cpu",
        },
        "metrics": list(PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_METRIC_NAMES),
        "strongest_kill_test": "train_pair_block_target_reversal",
        "stop_rule": "single_fixed_original_and_permuted_cpu_pass_no_tuning_or_promotion",
    }


def _input_batch_sha256(
    *,
    dataset_contract_sha256: str,
    row_keys: tuple[tuple[int, int, str, str], ...],
    frames: tuple[ProfiledMtfForwardRaggedSequenceFrame, ...],
    sequences: tuple[tuple[tuple[tuple[Decimal, ...], ...], ...], ...],
    validity_masks: tuple[tuple[tuple[bool, ...], ...], ...],
    projection_sha256s: tuple[str, ...],
) -> str:
    return _sha256_json(
        {
            "dataset_contract_sha256": dataset_contract_sha256,
            "frames": [frame.safe_payload() for frame in frames],
            "rows": [
                {
                    "row_key": list(row_key),
                    "projection_sha256": projection_sha256,
                    "sequences": [
                        [[str(value) for value in row] for row in frame]
                        for frame in control
                    ],
                    "validity_masks": [list(mask) for mask in control_masks],
                }
                for row_key, control, control_masks, projection_sha256 in zip(
                    row_keys,
                    sequences,
                    validity_masks,
                    projection_sha256s,
                    strict=True,
                )
            ],
        }
    )


def _candidate_evidence_sha256(
    metric: ProfiledMtfForwardRaggedSequenceCpuCandidateMetric,
) -> str:
    return _candidate_evidence_sha256_fields(
        {
            "candidate_id": metric.candidate_id,
            "validation_mse": metric.validation_mse,
            "validation_directional_hit_rate": metric.validation_directional_hit_rate,
            "permuted_validation_mse": metric.permuted_validation_mse,
            "permuted_validation_directional_hit_rate": (
                metric.permuted_validation_directional_hit_rate
            ),
        }
    )


def _candidate_evidence_sha256_fields(fields: dict[str, object]) -> str:
    return _sha256_json(fields)


def _result_sha256(result: ProfiledMtfForwardRaggedSequenceCpuCampaignResult) -> str:
    return _result_sha256_fields(
        {
            "policy_sha256": result.policy_sha256,
            "dataset_receipt_sha256": result.dataset_receipt_sha256,
            "dataset_result_sha256": result.dataset_result_sha256,
            "status": result.status,
            "input_batch_sha256": result.input_batch_sha256,
            "train_row_count": result.train_row_count,
            "purge_row_count": result.purge_row_count,
            "validation_row_count": result.validation_row_count,
            "candidate_metrics": result.candidate_metrics,
        }
    )


def _result_sha256_fields(fields: dict[str, object]) -> str:
    metrics = fields["candidate_metrics"]
    return _sha256_json(
        {
            **{key: value for key, value in fields.items() if key != "candidate_metrics"},
            "candidate_metrics": [metric.safe_payload() for metric in metrics],
        }
    )


def _result_scope(*, cpu_trained: bool) -> dict[str, bool]:
    return {
        "repository_storage_allowed": False,
        "feature_values_persisted": False,
        "target_values_persisted": False,
        "predictions_persisted": False,
        "model_weights_persisted": False,
        "model_trained_cpu_only_in_memory": cpu_trained,
        "gpu_allocated": False,
        "pnl_calculated": False,
        "paper_or_broker_action": False,
        "network_or_credentials_used": False,
        "promotion_or_winner_selected": False,
    }


def _artifact_policy() -> dict[str, bool]:
    return {
        "repository_storage_allowed": False,
        "raw_rows_persisted": False,
        "feature_values_persisted": False,
        "target_values_persisted": False,
        "predictions_persisted": False,
        "weights_persisted": False,
        "checkpoints_persisted": False,
    }


def _finite_scalar(value: Any) -> float:
    scalar = float(value.detach().item())
    if not math.isfinite(scalar):
        raise ValueError("ragged sequence CPU scalar is not finite")
    return round(scalar, 12)


def _valid_row_key(value: object) -> bool:
    if not isinstance(value, tuple) or len(value) != 4:
        return False
    pair_index, leg_index, split, raw_snapshot_sha256 = value
    return (
        type(pair_index) is int
        and pair_index in range(PROFILED_MTF_FORWARD_SUPERVISED_DATASET_PAIR_COUNT)
        and type(leg_index) is int
        and leg_index in {0, 1}
        and split in {"train", "purge", "validation"}
        and _is_sha256(raw_snapshot_sha256)
    )


def _write_or_verify_json(path: Path, payload: dict[str, object]) -> None:
    if path.is_symlink():
        raise ValueError("ragged sequence CPU receipt path must not be a symlink")
    encoded = _canonical_json(payload)
    if path.exists():
        try:
            existing = path.read_bytes()
        except OSError as error:
            raise ValueError("ragged sequence CPU receipt is unavailable") from error
        if existing != encoded:
            raise ValueError("ragged sequence CPU receipt conflicts")
        return
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded.decode("utf-8"))
    except FileExistsError:
        _write_or_verify_json(path, payload)


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
        raise ValueError("ragged sequence CPU campaign attempt_id is invalid")


def _torch() -> Any:
    import torch

    return torch
