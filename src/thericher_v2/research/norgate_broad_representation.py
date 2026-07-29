"""Target-free sequence-representation plumbing over the frozen Norgate D1 panel.

This module deliberately uses no forward return label, score ranking, replay,
or broker surface. It is an offline engineering study that proves a safe CUDA
training path before a KIS-reconstructible predictive campaign exists.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal

from thericher_v2.contracts import SCHEMA_VERSION, Bar
from thericher_v2.data.norgate_trial_development_panel import (
    DEFAULT_MARKET_DATA_ROOT,
    FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_HASH,
    FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_ID,
    FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_SNAPSHOT_DIR,
    NorgateTrialDevelopmentPanelCatalog,
    load_verified_norgate_trial_development_panel_catalog,
)

from .campaign_registry import (
    CampaignOutcomeRegistryEntry,
    FrozenCampaignRegistryEntry,
    register_campaign_outcome,
    register_frozen_campaign,
)
from .validation import _reject_repo_artifact_path, resolve_model_artifact_root

NORGATE_BROAD_REPRESENTATION_ID = "norgate-broad-target-free-representation-v1"
DEFAULT_WINDOW_LENGTH = 40
DEFAULT_MASK_SPAN = 4
DEVELOPMENT_END_RETURN_INDEX = 297
DIAGNOSTIC_START_RETURN_INDEX = 320
DEFAULT_TRAINING_STEPS = 192
DEFAULT_CPU_SMOKE_STEPS = 3
DEFAULT_BATCH_SIZE = 4096
DEFAULT_HIDDEN_SIZE = 96
DEFAULT_ATTENTION_HEADS = 4
DEFAULT_TCN_KERNEL_SIZE = 3
DEFAULT_LEARNING_RATE = 0.0008
DEFAULT_WEIGHT_DECAY = 0.0001
RepresentationArchitectureId = Literal["gru", "lstm", "causal_tcn", "compact_attention"]
REPRESENTATION_ARCHITECTURE_IDS = (
    "gru",
    "lstm",
    "causal_tcn",
    "compact_attention",
)


@dataclass(frozen=True, slots=True)
class RepresentationGeometry:
    """Observed-window-only temporal geometry for a non-predictive study."""

    window_length: int = DEFAULT_WINDOW_LENGTH
    mask_span: int = DEFAULT_MASK_SPAN
    development_end_return_index: int = DEVELOPMENT_END_RETURN_INDEX
    diagnostic_start_return_index: int = DIAGNOSTIC_START_RETURN_INDEX

    def __post_init__(self) -> None:
        if self.window_length < 4:
            raise ValueError("representation window length must be at least four")
        if not 1 <= self.mask_span < self.window_length:
            raise ValueError("representation mask span must fit inside the observed window")
        if self.development_end_return_index < self.window_length - 1:
            raise ValueError("development return end must include one complete window")
        if self.diagnostic_start_return_index <= self.development_end_return_index:
            raise ValueError("diagnostic return range must follow development")

    @property
    def development_start_return_index(self) -> int:
        return self.window_length - 1

    @property
    def purge_start_return_index(self) -> int:
        return self.development_end_return_index + 1

    @property
    def purge_end_return_index(self) -> int:
        return self.diagnostic_start_return_index - 1


DEFAULT_REPRESENTATION_GEOMETRY = RepresentationGeometry()


@dataclass(frozen=True, slots=True)
class RepresentationArchitectureSpec:
    """One fixed non-selectable architecture and deterministic training budget."""

    architecture_id: RepresentationArchitectureId
    seed: int
    training_steps: int = DEFAULT_TRAINING_STEPS
    batch_size: int = DEFAULT_BATCH_SIZE
    hidden_size: int = DEFAULT_HIDDEN_SIZE
    attention_heads: int = DEFAULT_ATTENTION_HEADS
    tcn_kernel_size: int = DEFAULT_TCN_KERNEL_SIZE
    learning_rate: float = DEFAULT_LEARNING_RATE
    weight_decay: float = DEFAULT_WEIGHT_DECAY

    def __post_init__(self) -> None:
        if self.architecture_id not in REPRESENTATION_ARCHITECTURE_IDS:
            raise ValueError("representation architecture is not allowlisted")
        if (
            self.seed < 0
            or self.training_steps <= 0
            or self.batch_size <= 0
            or self.hidden_size <= 0
            or self.hidden_size % 2 != 0
            or self.attention_heads <= 0
            or self.hidden_size % self.attention_heads != 0
            or self.tcn_kernel_size <= 0
            or self.learning_rate <= 0
            or self.weight_decay < 0
        ):
            raise ValueError("representation architecture geometry is invalid")

    def payload(self) -> dict[str, Any]:
        return {
            "architecture_id": self.architecture_id,
            "seed": self.seed,
            "training_steps": self.training_steps,
            "batch_size": self.batch_size,
            "hidden_size": self.hidden_size,
            "attention_heads": self.attention_heads,
            "tcn_kernel_size": self.tcn_kernel_size,
            "learning_rate": self.learning_rate,
            "weight_decay": self.weight_decay,
        }


DEFAULT_ARCHITECTURE_SPECS = (
    RepresentationArchitectureSpec("gru", seed=4103),
    RepresentationArchitectureSpec("lstm", seed=4109),
    RepresentationArchitectureSpec("causal_tcn", seed=4111),
    RepresentationArchitectureSpec("compact_attention", seed=4117),
)


@dataclass(frozen=True, slots=True)
class ObservedReturnDataset:
    """In-memory windows made entirely from already observed close-to-close returns."""

    dataset_id: str
    dataset_hash: str
    manifest_hash: str
    common_sessions: tuple[date, ...]
    development_windows: Any
    diagnostic_windows: Any
    geometry: RepresentationGeometry
    selected_symbol_count: int
    development_window_sha256: str
    diagnostic_window_sha256: str

    def __post_init__(self) -> None:
        if not self.dataset_id or self.selected_symbol_count <= 0:
            raise ValueError("observed return dataset identity is invalid")
        _require_sha256(self.dataset_hash, "dataset hash")
        _require_sha256(self.manifest_hash, "manifest hash")
        _require_sha256(self.development_window_sha256, "development window hash")
        _require_sha256(self.diagnostic_window_sha256, "diagnostic window hash")


@dataclass(frozen=True, slots=True)
class RepresentationCampaignContract:
    """External non-promoting contract for one fixed target-free study."""

    contract_path: Path
    contract_sha256: str
    run_directory: Path
    dataset: ObservedReturnDataset
    registry_entry: FrozenCampaignRegistryEntry


@dataclass(frozen=True, slots=True)
class RepresentationRunResult:
    """One source-safe completed architecture result without a selection claim."""

    architecture_id: RepresentationArchitectureId
    summary_path: Path
    summary_sha256: str
    weights_path: Path
    weights_sha256: str
    final_training_masked_mse: float
    diagnostic_masked_mse: float
    device: str


@dataclass(frozen=True, slots=True)
class RepresentationBatchResult:
    """A fixed batch outcome and its registry outcome reference."""

    contract: RepresentationCampaignContract
    results: tuple[RepresentationRunResult, ...]
    batch_summary_path: Path
    batch_summary_sha256: str
    registry_outcome: CampaignOutcomeRegistryEntry


def load_frozen_observed_return_dataset(
    *,
    geometry: RepresentationGeometry = DEFAULT_REPRESENTATION_GEOMETRY,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
) -> ObservedReturnDataset:
    """Reattest the static panel and derive only past-and-present return windows."""

    catalog = load_verified_norgate_trial_development_panel_catalog(
        FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_SNAPSHOT_DIR,
        expected_dataset_id=FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_ID,
        expected_dataset_hash=FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_HASH,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    return build_observed_return_dataset(catalog, geometry=geometry)


def build_observed_return_dataset(
    catalog: NorgateTrialDevelopmentPanelCatalog,
    *,
    geometry: RepresentationGeometry = DEFAULT_REPRESENTATION_GEOMETRY,
) -> ObservedReturnDataset:
    """Build causal return windows without future labels or future-quality filters."""

    numpy = _numpy()
    common_sessions = tuple(catalog.common_sessions)
    if len(common_sessions) < geometry.diagnostic_start_return_index + 2:
        raise ValueError("Norgate panel is too short for the fixed representation geometry")
    ordered_symbols = tuple(sorted(catalog.bars_by_symbol))
    if not ordered_symbols:
        raise ValueError("Norgate panel has no selected symbols")
    development_rows: list[Any] = []
    diagnostic_rows: list[Any] = []
    final_return_index = len(common_sessions) - 2
    for symbol in ordered_symbols:
        bars = tuple(catalog.bars_by_symbol[symbol].bars)
        returns = observed_close_to_close_returns(bars, common_sessions=common_sessions)
        if len(returns) != final_return_index + 1:
            raise ValueError("Norgate observed return length is invalid")
        development_rows.extend(
            _windows_for_return_range(
                returns,
                start_return_index=geometry.development_start_return_index,
                end_return_index=geometry.development_end_return_index,
                window_length=geometry.window_length,
            )
        )
        diagnostic_rows.extend(
            _windows_for_return_range(
                returns,
                start_return_index=geometry.diagnostic_start_return_index,
                end_return_index=final_return_index,
                window_length=geometry.window_length,
            )
        )
    development = numpy.asarray(development_rows, dtype=numpy.float32)
    diagnostic = numpy.asarray(diagnostic_rows, dtype=numpy.float32)
    _validate_window_matrix(development, geometry=geometry, field_name="development windows")
    _validate_window_matrix(diagnostic, geometry=geometry, field_name="diagnostic windows")
    return ObservedReturnDataset(
        dataset_id=catalog.source.dataset_id,
        dataset_hash=catalog.source.dataset_hash,
        manifest_hash=catalog.source.manifest_hash,
        common_sessions=common_sessions,
        development_windows=development,
        diagnostic_windows=diagnostic,
        geometry=geometry,
        selected_symbol_count=len(ordered_symbols),
        development_window_sha256=_sha256_array(development),
        diagnostic_window_sha256=_sha256_array(diagnostic),
    )


def observed_close_to_close_returns(
    bars: Sequence[Bar],
    *,
    common_sessions: Sequence[date],
) -> Any:
    """Return values indexed only by their later already observed session."""

    numpy = _numpy()
    if len(bars) != len(common_sessions) or len(bars) < 2:
        raise ValueError("observed return source bars do not match the common session calendar")
    closes: list[float] = []
    for bar, session in zip(bars, common_sessions, strict=True):
        if not bar.complete or bar.start_ts.date() != session:
            raise ValueError("observed return source bar is incomplete or misaligned")
        closes.append(float(bar.close))
    values = numpy.asarray(closes, dtype=numpy.float64)
    if not numpy.isfinite(values).all() or numpy.any(values <= 0):
        raise ValueError("observed return source close is invalid")
    returns = (values[1:] / values[:-1]) - 1.0
    if not numpy.isfinite(returns).all():
        raise ValueError("observed return values are invalid")
    return returns.astype(numpy.float32, copy=False)


def mask_observed_windows(
    windows: Any,
    *,
    mask_span: int,
    seed: int,
) -> tuple[Any, Any, Any]:
    """Mask one deterministic span within each already observed sequence window."""

    numpy = _numpy()
    values = numpy.asarray(windows, dtype=numpy.float32)
    if values.ndim != 2 or values.shape[0] == 0 or values.shape[1] <= mask_span:
        raise ValueError("observed window masking geometry is invalid")
    if not numpy.isfinite(values).all() or mask_span <= 0 or seed < 0:
        raise ValueError("observed window masking inputs are invalid")
    row_indexes = numpy.arange(values.shape[0], dtype=numpy.int64)
    starts = ((row_indexes * 1_103_515_245) + seed) % (values.shape[1] - mask_span + 1)
    mask = numpy.zeros(values.shape, dtype=numpy.float32)
    offsets = numpy.arange(mask_span, dtype=numpy.int64)
    mask[row_indexes[:, None], starts[:, None] + offsets[None, :]] = 1.0
    masked = values.copy()
    masked[mask.astype(bool)] = 0.0
    features = numpy.stack((masked, mask), axis=-1)
    return features, values[..., None], mask[..., None]


def freeze_representation_campaign(
    dataset: ObservedReturnDataset,
    *,
    artifact_root: Path | None = None,
    repo_root: Path | None = None,
    run_id: str = NORGATE_BROAD_REPRESENTATION_ID,
    code_revision: str = "unrecorded",
    architecture_specs: Sequence[RepresentationArchitectureSpec] = DEFAULT_ARCHITECTURE_SPECS,
) -> RepresentationCampaignContract:
    """Write or reattach one immutable target-free external contract."""

    output_directory = _representation_output_directory(
        artifact_root=artifact_root,
        repo_root=repo_root,
        run_id=run_id,
    )
    specs = _validated_architecture_specs(architecture_specs)
    payload = _contract_payload(dataset, run_id=run_id, code_revision=code_revision, specs=specs)
    contract_path = output_directory / "campaign-contract.json"
    if contract_path.exists():
        _verify_existing_contract(contract_path, expected=payload)
    else:
        _write_json_new(
            contract_path,
            _signed_payload(payload, field_name="campaign_contract_sha256"),
        )
    contract_payload = _read_json_object(contract_path)
    contract_hash = contract_payload["campaign_contract_sha256"]
    registry_entry = register_frozen_campaign(
        contract_hash=contract_hash,
        dataset_hash=dataset.dataset_hash,
        split_hash=contract_payload["split_sha256"],
        cost_model_hash=contract_payload["cost_model_sha256"],
        trial_family=NORGATE_BROAD_REPRESENTATION_ID,
        holdout_access="none",
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    return RepresentationCampaignContract(
        contract_path=contract_path,
        contract_sha256=contract_hash,
        run_directory=output_directory,
        dataset=dataset,
        registry_entry=registry_entry,
    )


def run_representation_cpu_smoke(
    contract: RepresentationCampaignContract,
    *,
    architecture_id: RepresentationArchitectureId = "gru",
    steps: int = DEFAULT_CPU_SMOKE_STEPS,
) -> RepresentationRunResult:
    """Run one small deterministic CPU smoke before dispatching the CUDA batch."""

    spec = _architecture_spec(contract, architecture_id, steps=steps)
    return _run_architecture(contract, spec=spec, device_name="cpu", phase="cpu_smoke")


def run_representation_cuda_batch(
    contract: RepresentationCampaignContract,
    *,
    architecture_specs: Sequence[RepresentationArchitectureSpec] = DEFAULT_ARCHITECTURE_SPECS,
) -> RepresentationBatchResult:
    """Run fixed CUDA architecture studies without scoring or selecting their members."""

    torch = _torch()
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable for the bounded representation batch")
    specs = _validated_architecture_specs(architecture_specs)
    _verify_cpu_smoke(contract)
    results = tuple(
        _run_architecture(contract, spec=spec, device_name="cuda", phase="cuda_batch")
        for spec in specs
    )
    summary_payload = {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": NORGATE_BROAD_REPRESENTATION_ID,
        "campaign_contract_sha256": contract.contract_sha256,
        "phase": "cuda_batch",
        "scope": _non_promoting_scope(),
        "architecture_count": len(results),
        "architecture_ids": [result.architecture_id for result in results],
        "architecture_summary_sha256": [result.summary_sha256 for result in results],
        "architecture_weights_sha256": [result.weights_sha256 for result in results],
        "selection": "disabled",
    }
    batch_path = contract.run_directory / "cuda-batch-summary.json"
    _write_or_verify_json(
        batch_path,
        _signed_payload(summary_payload, field_name="batch_summary_sha256"),
    )
    batch_payload = _read_json_object(batch_path)
    batch_hash = batch_payload["batch_summary_sha256"]
    outcome = register_campaign_outcome(
        contract_hash=contract.contract_sha256,
        outcome_class="non_promoting_completed",
        outcome_reference_sha256=batch_hash,
        artifact_root=contract.run_directory.parents[2],
        repo_root=Path.cwd(),
    )
    return RepresentationBatchResult(
        contract=contract,
        results=results,
        batch_summary_path=batch_path,
        batch_summary_sha256=batch_hash,
        registry_outcome=outcome,
    )


def _run_architecture(
    contract: RepresentationCampaignContract,
    *,
    spec: RepresentationArchitectureSpec,
    device_name: Literal["cpu", "cuda"],
    phase: Literal["cpu_smoke", "cuda_batch"],
) -> RepresentationRunResult:
    torch = _torch()
    numpy = _numpy()
    device = torch.device(device_name)
    torch.manual_seed(spec.seed)
    if device_name == "cuda":
        torch.cuda.manual_seed_all(spec.seed)
    train_features, train_targets, train_mask = mask_observed_windows(
        contract.dataset.development_windows,
        mask_span=contract.dataset.geometry.mask_span,
        seed=spec.seed,
    )
    diagnostic_features, diagnostic_targets, diagnostic_mask = mask_observed_windows(
        contract.dataset.diagnostic_windows,
        mask_span=contract.dataset.geometry.mask_span,
        seed=spec.seed + 1,
    )
    train_feature_tensor = torch.tensor(train_features, dtype=torch.float32, device=device)
    train_target_tensor = torch.tensor(train_targets, dtype=torch.float32, device=device)
    train_mask_tensor = torch.tensor(train_mask, dtype=torch.float32, device=device)
    diagnostic_feature_tensor = torch.tensor(
        diagnostic_features, dtype=torch.float32, device=device
    )
    diagnostic_target_tensor = torch.tensor(
        diagnostic_targets, dtype=torch.float32, device=device
    )
    diagnostic_mask_tensor = torch.tensor(diagnostic_mask, dtype=torch.float32, device=device)
    model = _build_reconstruction_model(torch=torch, spec=spec).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=spec.learning_rate,
        weight_decay=spec.weight_decay,
    )
    last_loss = math.nan
    row_count = int(train_feature_tensor.shape[0])
    for step in range(spec.training_steps):
        start = (step * spec.batch_size) % row_count
        indexes = torch.arange(
            start,
            start + spec.batch_size,
            device=device,
            dtype=torch.long,
        ) % row_count
        prediction = model(train_feature_tensor.index_select(0, indexes))
        loss = _masked_mse(
            prediction,
            train_target_tensor.index_select(0, indexes),
            train_mask_tensor.index_select(0, indexes),
        )
        if not torch.isfinite(loss):
            raise RuntimeError("target-free representation loss became non-finite")
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        last_loss = float(loss.detach().cpu())
    with torch.no_grad():
        diagnostic_prediction = model(diagnostic_feature_tensor)
        diagnostic_loss = _masked_mse(
            diagnostic_prediction,
            diagnostic_target_tensor,
            diagnostic_mask_tensor,
        )
    diagnostic_value = float(diagnostic_loss.detach().cpu())
    if not math.isfinite(last_loss) or not math.isfinite(diagnostic_value):
        raise RuntimeError("target-free representation metrics are non-finite")
    output_dir = contract.run_directory / f"{phase}-{spec.architecture_id}"
    weights_path = output_dir / "weights.npz"
    weights_hash = _write_or_verify_safe_weights(weights_path, model=model, numpy=numpy)
    summary_payload = {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": NORGATE_BROAD_REPRESENTATION_ID,
        "campaign_contract_sha256": contract.contract_sha256,
        "phase": phase,
        "scope": _non_promoting_scope(),
        "objective": "masked_span_reconstruction_of_observed_returns",
        "architecture": spec.payload(),
        "device": device_name,
        "training_masked_mse_final": last_loss,
        "diagnostic_masked_mse": diagnostic_value,
        "weights_format": "npz_numpy_arrays_no_pickle",
        "weights_sha256": weights_hash,
        "selection": "disabled",
    }
    summary_path = output_dir / "summary.json"
    _write_or_verify_json(
        summary_path,
        _signed_payload(summary_payload, field_name="summary_sha256"),
    )
    summary = _read_json_object(summary_path)
    if device_name == "cuda":
        torch.cuda.empty_cache()
    return RepresentationRunResult(
        architecture_id=spec.architecture_id,
        summary_path=summary_path,
        summary_sha256=summary["summary_sha256"],
        weights_path=weights_path,
        weights_sha256=weights_hash,
        final_training_masked_mse=last_loss,
        diagnostic_masked_mse=diagnostic_value,
        device=device_name,
    )


def _build_reconstruction_model(*, torch: Any, spec: RepresentationArchitectureSpec) -> Any:
    nn = torch.nn
    if spec.architecture_id == "gru":

        class GruReconstructionModel(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.encoder = nn.GRU(2, spec.hidden_size, batch_first=True)
                self.head = nn.Linear(spec.hidden_size, 1)

            def forward(self, values: Any) -> Any:
                encoded, _ = self.encoder(values)
                return self.head(encoded)

        return GruReconstructionModel()
    if spec.architecture_id == "lstm":

        class LstmReconstructionModel(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.encoder = nn.LSTM(2, spec.hidden_size, batch_first=True)
                self.head = nn.Linear(spec.hidden_size, 1)

            def forward(self, values: Any) -> Any:
                encoded, _ = self.encoder(values)
                return self.head(encoded)

        return LstmReconstructionModel()
    if spec.architecture_id == "causal_tcn":

        class CausalTcnReconstructionModel(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.convolution = nn.Conv1d(
                    2,
                    spec.hidden_size,
                    kernel_size=spec.tcn_kernel_size,
                    padding=spec.tcn_kernel_size - 1,
                )
                self.head = nn.Linear(spec.hidden_size, 1)

            def forward(self, values: Any) -> Any:
                length = values.shape[1]
                encoded = self.convolution(values.transpose(1, 2))[:, :, :length]
                return self.head(torch.relu(encoded).transpose(1, 2))

        return CausalTcnReconstructionModel()

    class CompactAttentionReconstructionModel(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.input_projection = nn.Linear(2, spec.hidden_size)
            layer = nn.TransformerEncoderLayer(
                d_model=spec.hidden_size,
                nhead=spec.attention_heads,
                dim_feedforward=spec.hidden_size * 2,
                dropout=0.0,
                batch_first=True,
            )
            self.encoder = nn.TransformerEncoder(layer, num_layers=1)
            self.head = nn.Linear(spec.hidden_size, 1)

        def forward(self, values: Any) -> Any:
            length = values.shape[1]
            positions = torch.arange(length, dtype=values.dtype, device=values.device).unsqueeze(1)
            divisors = torch.exp(
                torch.arange(0, spec.hidden_size, 2, dtype=values.dtype, device=values.device)
                * (-math.log(10_000.0) / spec.hidden_size)
            )
            positional = torch.zeros(
                (length, spec.hidden_size),
                dtype=values.dtype,
                device=values.device,
            )
            positional[:, 0::2] = torch.sin(positions * divisors)
            positional[:, 1::2] = torch.cos(positions * divisors)
            causal_mask = torch.triu(
                torch.full(
                    (length, length),
                    float("-inf"),
                    dtype=values.dtype,
                    device=values.device,
                ),
                diagonal=1,
            )
            encoded = self.encoder(
                self.input_projection(values) + positional.unsqueeze(0),
                mask=causal_mask,
            )
            return self.head(encoded)

    return CompactAttentionReconstructionModel()


def _masked_mse(prediction: Any, target: Any, mask: Any) -> Any:
    squared_error = (prediction - target).square() * mask
    denominator = mask.sum()
    if denominator <= 0:
        raise RuntimeError("target-free representation mask is empty")
    return squared_error.sum() / denominator


def _architecture_spec(
    contract: RepresentationCampaignContract,
    architecture_id: RepresentationArchitectureId,
    *,
    steps: int,
) -> RepresentationArchitectureSpec:
    if steps <= 0:
        raise ValueError("CPU smoke steps must be positive")
    payload = _read_json_object(contract.contract_path)
    for candidate in payload["architectures"]:
        if candidate["architecture_id"] == architecture_id:
            return RepresentationArchitectureSpec(
                architecture_id=architecture_id,
                seed=candidate["seed"],
                training_steps=steps,
                batch_size=candidate["batch_size"],
                hidden_size=candidate["hidden_size"],
                attention_heads=candidate["attention_heads"],
                tcn_kernel_size=candidate["tcn_kernel_size"],
                learning_rate=candidate["learning_rate"],
                weight_decay=candidate["weight_decay"],
            )
    raise ValueError("CPU smoke architecture is not frozen in the campaign contract")


def _verify_cpu_smoke(contract: RepresentationCampaignContract) -> None:
    summary_path = contract.run_directory / "cpu_smoke-gru" / "summary.json"
    summary = _read_json_object(summary_path)
    if (
        summary.get("campaign_contract_sha256") != contract.contract_sha256
        or summary.get("phase") != "cpu_smoke"
        or summary.get("architecture", {}).get("architecture_id") != "gru"
        or summary.get("scope") != _non_promoting_scope()
        or summary.get("selection") != "disabled"
    ):
        raise ValueError("verified CPU smoke is required before the CUDA representation batch")


def _contract_payload(
    dataset: ObservedReturnDataset,
    *,
    run_id: str,
    code_revision: str,
    specs: tuple[RepresentationArchitectureSpec, ...],
) -> dict[str, Any]:
    _safe_path_component(run_id, "run_id")
    if not code_revision.strip():
        raise ValueError("code revision is required")
    split = {
        "window_length": dataset.geometry.window_length,
        "development_return_indices": [
            dataset.geometry.development_start_return_index,
            dataset.geometry.development_end_return_index,
        ],
        "purge_return_indices": [
            dataset.geometry.purge_start_return_index,
            dataset.geometry.purge_end_return_index,
        ],
        "diagnostic_return_indices": [
            dataset.geometry.diagnostic_start_return_index,
            len(dataset.common_sessions) - 2,
        ],
        "future_index_access": False,
    }
    cost_model = {"kind": "not_applicable_target_free_representation", "version": 1}
    return {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": NORGATE_BROAD_REPRESENTATION_ID,
        "run_id": run_id,
        "code_revision": code_revision.strip(),
        "objective": "masked_span_reconstruction_of_observed_returns",
        "scope": _non_promoting_scope(),
        "source": {
            "dataset_id": dataset.dataset_id,
            "dataset_hash": dataset.dataset_hash,
            "manifest_hash": dataset.manifest_hash,
            "selected_symbol_count": dataset.selected_symbol_count,
            "common_session_count": len(dataset.common_sessions),
            "source_scope_preserved": {
                "campaign_eligible": False,
                "model_eligible": False,
                "gpu_eligible": False,
                "paper_trading_eligible": False,
            },
        },
        "observed_windows": {
            "development_count": int(dataset.development_windows.shape[0]),
            "diagnostic_count": int(dataset.diagnostic_windows.shape[0]),
            "development_window_sha256": dataset.development_window_sha256,
            "diagnostic_window_sha256": dataset.diagnostic_window_sha256,
            "mask_span": dataset.geometry.mask_span,
            "forward_labels": False,
            "future_aware_quality_filter": False,
        },
        "split": split,
        "split_sha256": _sha256_json(split),
        "cost_model": cost_model,
        "cost_model_sha256": _sha256_json(cost_model),
        "architectures": [spec.payload() for spec in specs],
        "training_policy": {
            "fixed_steps": True,
            "early_stopping": False,
            "architecture_selection": False,
            "score_leaderboard": False,
            "weight_format": "npz_numpy_arrays_no_pickle",
        },
    }


def _representation_output_directory(
    *,
    artifact_root: Path | None,
    repo_root: Path | None,
    run_id: str,
) -> Path:
    _safe_path_component(run_id, "run_id")
    root = Path(artifact_root or resolve_model_artifact_root())
    if not root.is_dir() or root.is_symlink():
        raise ValueError("model artifact root must be an existing non-symlink directory")
    effective_repo_root = repo_root or Path.cwd()
    _reject_repo_artifact_path(root, effective_repo_root)
    resolved_root = root.resolve()
    output = resolved_root / "research" / NORGATE_BROAD_REPRESENTATION_ID / run_id
    if output.exists() and output.is_symlink():
        raise ValueError("representation artifact directory must not be a symlink")
    if not output.is_relative_to(resolved_root):
        raise ValueError("representation artifact path escapes the artifact root")
    output.mkdir(parents=True, exist_ok=True)
    return output


def _windows_for_return_range(
    returns: Any,
    *,
    start_return_index: int,
    end_return_index: int,
    window_length: int,
) -> list[Any]:
    if end_return_index >= len(returns) or start_return_index < window_length - 1:
        raise ValueError("observed return window range is invalid")
    return [
        returns[end_index - window_length + 1 : end_index + 1]
        for end_index in range(start_return_index, end_return_index + 1)
    ]


def _validate_window_matrix(
    value: Any,
    *,
    geometry: RepresentationGeometry,
    field_name: str,
) -> None:
    numpy = _numpy()
    if (
        value.ndim != 2
        or value.shape[0] <= 0
        or value.shape[1] != geometry.window_length
        or not numpy.isfinite(value).all()
    ):
        raise ValueError(f"{field_name} are invalid")


def _validated_architecture_specs(
    specs: Sequence[RepresentationArchitectureSpec],
) -> tuple[RepresentationArchitectureSpec, ...]:
    frozen = tuple(specs)
    if not frozen or len({spec.architecture_id for spec in frozen}) != len(frozen):
        raise ValueError("representation architecture specs must be non-empty and unique")
    if any(not isinstance(spec, RepresentationArchitectureSpec) for spec in frozen):
        raise TypeError("representation architecture specs are invalid")
    return frozen


def _verify_existing_contract(path: Path, *, expected: Mapping[str, Any]) -> None:
    existing = _read_json_object(path)
    signed_expected = _signed_payload(dict(expected), field_name="campaign_contract_sha256")
    if existing != signed_expected:
        raise ValueError("existing representation campaign contract conflicts with frozen inputs")


def _write_or_verify_json(path: Path, payload: Mapping[str, Any]) -> None:
    if path.exists():
        if _read_json_object(path) != dict(payload):
            raise ValueError("existing representation artifact conflicts with the fixed contract")
        return
    _write_json_new(path, payload)


def _write_or_verify_safe_weights(*, path: Path, model: Any, numpy: Any) -> str:
    arrays: dict[str, Any] = {}
    for name, tensor in sorted(model.state_dict().items()):
        value = tensor.detach().cpu().contiguous().numpy()
        if value.dtype.hasobject:
            raise ValueError("safe representation weights cannot contain object values")
        arrays[name] = value
    if path.exists():
        return _sha256_file(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        numpy.savez_compressed(handle, **arrays)
    return _sha256_file(path)


def _signed_payload(payload: Mapping[str, Any], *, field_name: str) -> dict[str, Any]:
    result = dict(payload)
    result[field_name] = _sha256_json(result)
    return result


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ValueError("representation artifact is missing or invalid")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("representation artifact is malformed") from exc
    if not isinstance(payload, dict):
        raise ValueError("representation artifact must be a JSON object")
    return payload


def _write_json_new(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _non_promoting_scope() -> dict[str, bool]:
    return {
        "target_free": True,
        "point_in_time_eligible": False,
        "ranking_eligible": False,
        "forecast_eligible": False,
        "model_promotion_eligible": False,
        "ensemble_eligible": False,
        "paper_trading_eligible": False,
        "pnl_or_profitability_claim": False,
    }


def _numpy() -> Any:
    import numpy

    return numpy


def _torch() -> Any:
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("PyTorch is required in the Docker research image") from exc
    return torch


def _sha256_array(value: Any) -> str:
    return "sha256:" + hashlib.sha256(value.tobytes()).hexdigest()


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_json(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _require_sha256(value: object, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith("sha256:")
        or len(value) != 71
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError(f"{field_name} must use sha256:<64 lowercase hex> format")
    return value


def _safe_path_component(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or value in {".", ".."}
        or any(character in value for character in ("/", "\\", ":"))
    ):
        raise ValueError(f"{field_name} must be a safe path component")
