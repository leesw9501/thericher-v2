"""One bounded causal-TCN representation feasibility campaign for KIS D1 bars.

The module deliberately keeps the campaign source-local and non-promoting.  It
does not produce an alpha score, a trade label, a backtest, or an execution
surface.  PyTorch is imported only when a CPU or CUDA run is explicitly
requested so the data/contract helpers remain import-pure.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from thericher_v2.contracts import SCHEMA_VERSION, Timeframe

from .campaign_registry import (
    CampaignOutcomeRegistryEntry,
    FrozenCampaignRegistryEntry,
    register_campaign_outcome,
    register_frozen_campaign,
)
from .validation import _reject_repo_artifact_path

KIS_D1_CAUSAL_REPRESENTATION_ID = "kis-d1-causal-representation-feasibility-v1"
KIS_D1_CAUSAL_REPRESENTATION_DATASET_ID = "kis.paper.private.daily.nas.history.panel-v1"
KIS_D1_CAUSAL_REPRESENTATION_DATASET_HASH = (
    "sha256:7e8d6fe54dd5252fc4b9548b70e3bb31aefcd282922a50c1ca7c58a94d57dc8e"
)
KIS_D1_CAUSAL_REPRESENTATION_SYMBOLS = (
    "AAPL",
    "AMZN",
    "GOOGL",
    "META",
    "MSFT",
    "NVDA",
)
KIS_D1_CAUSAL_REPRESENTATION_DEVELOPMENT_SESSIONS = 1510
KIS_D1_CAUSAL_REPRESENTATION_TRAINING_SESSIONS = 1000
KIS_D1_CAUSAL_REPRESENTATION_PURGE_SESSIONS = 32
KIS_D1_CAUSAL_REPRESENTATION_WINDOW_LENGTH = 32
KIS_D1_CAUSAL_REPRESENTATION_MASK_ROWS = 4
KIS_D1_CAUSAL_REPRESENTATION_FEATURE_NAMES = (
    "close_to_prior_close_log_return",
    "high_to_open_log_ratio",
    "low_to_open_log_ratio",
    "close_to_open_log_ratio",
    "log_volume_change",
)
KIS_D1_CAUSAL_REPRESENTATION_SEED = 20_260_802
KIS_D1_CAUSAL_REPRESENTATION_HIDDEN_CHANNELS = 32
KIS_D1_CAUSAL_REPRESENTATION_KERNEL_SIZE = 3
KIS_D1_CAUSAL_REPRESENTATION_DILATIONS = (1, 2, 4)
KIS_D1_CAUSAL_REPRESENTATION_LEARNING_RATE = 0.001
KIS_D1_CAUSAL_REPRESENTATION_WEIGHT_DECAY = 0.0001
KIS_D1_CAUSAL_REPRESENTATION_BATCH_SIZE = 256
KIS_D1_CAUSAL_REPRESENTATION_CPU_STEPS = 4
KIS_D1_CAUSAL_REPRESENTATION_CUDA_STEPS = 192
KIS_D1_CAUSAL_REPRESENTATION_CUDA_MAX_SECONDS = 300.0
KIS_D1_CAUSAL_REPRESENTATION_DEFAULT_ATTEMPT_ID = "implementation-r2"

RepresentationRunStatus = Literal["completed", "runtime_unavailable", "time_bounded"]
RepresentationDevice = Literal["cpu", "cuda", "unavailable"]


@dataclass(frozen=True, slots=True)
class KisD1CausalRepresentationDataset:
    """In-memory normalized causal windows from the frozen development phase."""

    input_id: str
    dataset_id: str
    dataset_hash: str
    index_hash: str
    training_windows: Any
    diagnostic_windows: Any
    training_window_sha256: str
    diagnostic_window_sha256: str
    symbol_count: int

    def __post_init__(self) -> None:
        if (
            self.input_id != "kis.paper.private.daily.nas.sequence.input-v1"
            or self.dataset_id != KIS_D1_CAUSAL_REPRESENTATION_DATASET_ID
            or self.dataset_hash != KIS_D1_CAUSAL_REPRESENTATION_DATASET_HASH
            or not _is_sha256(self.index_hash)
            or not _is_sha256(self.training_window_sha256)
            or not _is_sha256(self.diagnostic_window_sha256)
            or self.symbol_count != len(KIS_D1_CAUSAL_REPRESENTATION_SYMBOLS)
        ):
            raise ValueError("KIS D1 representation dataset identity is invalid")


@dataclass(frozen=True, slots=True)
class KisD1CausalRepresentationContract:
    """Immutable external contract and its single Research Steward custody entry."""

    dataset: KisD1CausalRepresentationDataset
    artifact_root: Path
    repo_root: Path
    attempt_id: str
    run_directory: Path
    contract_path: Path
    contract_sha256: str
    registry_entry: FrozenCampaignRegistryEntry


@dataclass(frozen=True, slots=True)
class KisD1CausalRepresentationRun:
    """A source-safe result for a CPU smoke or the only CUDA appointment."""

    phase: Literal["cpu_smoke", "cuda"]
    status: RepresentationRunStatus
    device: RepresentationDevice
    steps_completed: int
    training_loss_finite: bool
    training_loss_decreased: bool
    diagnostic_loss_finite: bool
    summary_path: Path
    summary_sha256: str
    weights_path: Path | None
    weights_sha256: str | None
    registry_outcome: CampaignOutcomeRegistryEntry | None = None


def load_kis_d1_causal_representation_dataset(
    *,
    manifest_path: Path,
    cache_root: Path,
    panel_root: Path,
    repo_root: Path | None = None,
) -> KisD1CausalRepresentationDataset:
    """Load only through the existing attested KIS daily sequence input adapter."""

    from thericher_v2.data.kis_paper_daily_history_sequence_input import (
        load_kis_paper_daily_history_sequence_input,
    )

    source = load_kis_paper_daily_history_sequence_input(
        manifest_path=manifest_path,
        cache_root=cache_root,
        panel_root=panel_root,
        repo_root=repo_root,
    )
    return build_kis_d1_causal_representation_dataset(source.development, input_id=source.input_id)


def build_kis_d1_causal_representation_dataset(
    development_phase: object,
    *,
    input_id: str,
) -> KisD1CausalRepresentationDataset:
    """Derive training and diagnostic windows without materializing later phases."""

    numpy = _numpy()
    _require_development_phase(development_phase, input_id=input_id)
    phase = cast(Any, development_phase)
    bars_by_symbol = phase.bars_by_symbol
    training_by_symbol: list[Any] = []
    diagnostic_by_symbol: list[Any] = []
    for symbol in KIS_D1_CAUSAL_REPRESENTATION_SYMBOLS:
        stream = bars_by_symbol[symbol]
        feature_rows = _feature_rows(tuple(stream.bars), symbol=symbol)
        training_values = feature_rows[: KIS_D1_CAUSAL_REPRESENTATION_TRAINING_SESSIONS - 1]
        diagnostic_start = (
            KIS_D1_CAUSAL_REPRESENTATION_TRAINING_SESSIONS
            + KIS_D1_CAUSAL_REPRESENTATION_PURGE_SESSIONS
        )
        # The prior-bar return for the diagnostic segment also stays beyond the
        # purge boundary so no diagnostic example reaches back into training.
        diagnostic_values = feature_rows[diagnostic_start:]
        training_by_symbol.append(training_values)
        diagnostic_by_symbol.append(diagnostic_values)

    training_values = numpy.concatenate(training_by_symbol, axis=0)
    mean = training_values.mean(axis=0, keepdims=True)
    standard_deviation = training_values.std(axis=0, keepdims=True)
    if (
        not numpy.isfinite(mean).all()
        or not numpy.isfinite(standard_deviation).all()
        or numpy.any(standard_deviation <= 0.0)
    ):
        raise ValueError("KIS D1 representation normalization is invalid")

    training_windows: list[Any] = []
    diagnostic_windows: list[Any] = []
    for training_values, diagnostic_values in zip(
        training_by_symbol,
        diagnostic_by_symbol,
        strict=True,
    ):
        training_windows.append(
            _windows((training_values - mean) / standard_deviation)
        )
        diagnostic_windows.append(
            _windows((diagnostic_values - mean) / standard_deviation)
        )
    training = numpy.concatenate(training_windows, axis=0).astype(numpy.float32, copy=False)
    diagnostic = numpy.concatenate(diagnostic_windows, axis=0).astype(numpy.float32, copy=False)
    _require_windows(training, field_name="training windows")
    _require_windows(diagnostic, field_name="diagnostic windows")

    return KisD1CausalRepresentationDataset(
        input_id=input_id,
        dataset_id=str(phase.parent_dataset_id),
        dataset_hash=str(phase.parent_dataset_hash),
        index_hash=str(phase.index_hash),
        training_windows=training,
        diagnostic_windows=diagnostic,
        training_window_sha256=_sha256_array(training),
        diagnostic_window_sha256=_sha256_array(diagnostic),
        symbol_count=len(KIS_D1_CAUSAL_REPRESENTATION_SYMBOLS),
    )


def mask_causal_representation_windows(windows: Any) -> tuple[Any, Any]:
    """Hide the terminal rows and return model input plus in-memory targets."""

    numpy = _numpy()
    values = numpy.asarray(windows, dtype=numpy.float32)
    _require_windows(values, field_name="representation windows")
    visible = values.copy()
    visible[:, -KIS_D1_CAUSAL_REPRESENTATION_MASK_ROWS :, :] = 0.0
    mask = numpy.zeros((values.shape[0], values.shape[1], 1), dtype=numpy.float32)
    mask[:, -KIS_D1_CAUSAL_REPRESENTATION_MASK_ROWS :, 0] = 1.0
    inputs = numpy.concatenate((visible, mask), axis=2)
    targets = values[:, -KIS_D1_CAUSAL_REPRESENTATION_MASK_ROWS :, :].copy()
    if not numpy.isfinite(inputs).all() or not numpy.isfinite(targets).all():
        raise ValueError("causal representation masking is invalid")
    return inputs, targets


def freeze_kis_d1_causal_representation_campaign(
    dataset: KisD1CausalRepresentationDataset,
    *,
    artifact_root: Path,
    repo_root: Path,
    code_revision: str,
    attempt_id: str = KIS_D1_CAUSAL_REPRESENTATION_DEFAULT_ATTEMPT_ID,
) -> KisD1CausalRepresentationContract:
    """Freeze the one architecture contract before the optional CUDA appointment."""

    if not code_revision or not code_revision.strip():
        raise ValueError("code revision is required")
    _require_attempt_id(attempt_id)
    output_directory = _external_run_directory(artifact_root, repo_root, attempt_id=attempt_id)
    payload = _signed_payload(
        {
            "schema_version": SCHEMA_VERSION,
            "campaign_id": KIS_D1_CAUSAL_REPRESENTATION_ID,
            "attempt_id": attempt_id,
            "code_revision": code_revision,
            "source": {
                "input_id": dataset.input_id,
                "dataset_id": dataset.dataset_id,
                "dataset_hash": dataset.dataset_hash,
                "index_hash": dataset.index_hash,
                "phase": "development_only",
                "symbol_count": dataset.symbol_count,
                "raw_price_limitations": [
                    "MODP=0_unadjusted",
                    "corporate_action_semantics_not_qualified",
                    "current_listing_registry_not_point_in_time_universe",
                    "source_local_only_no_cross_source_blend",
                ],
            },
            "geometry": {
                "window_length": KIS_D1_CAUSAL_REPRESENTATION_WINDOW_LENGTH,
                "mask_rows": KIS_D1_CAUSAL_REPRESENTATION_MASK_ROWS,
                "training_session_count": KIS_D1_CAUSAL_REPRESENTATION_TRAINING_SESSIONS,
                "purge_session_count": KIS_D1_CAUSAL_REPRESENTATION_PURGE_SESSIONS,
                "diagnostic_phase": "remaining_development_only",
                "feature_names": list(KIS_D1_CAUSAL_REPRESENTATION_FEATURE_NAMES),
                "training_window_sha256": dataset.training_window_sha256,
                "diagnostic_window_sha256": dataset.diagnostic_window_sha256,
            },
            "architecture": {
                "family": "causal_tcn",
                "dilations": list(KIS_D1_CAUSAL_REPRESENTATION_DILATIONS),
                "hidden_channels": KIS_D1_CAUSAL_REPRESENTATION_HIDDEN_CHANNELS,
                "kernel_size": KIS_D1_CAUSAL_REPRESENTATION_KERNEL_SIZE,
                "seed": KIS_D1_CAUSAL_REPRESENTATION_SEED,
            },
            "training": {
                "optimizer": "adamw",
                "learning_rate": KIS_D1_CAUSAL_REPRESENTATION_LEARNING_RATE,
                "weight_decay": KIS_D1_CAUSAL_REPRESENTATION_WEIGHT_DECAY,
                "batch_size": KIS_D1_CAUSAL_REPRESENTATION_BATCH_SIZE,
                "cpu_smoke_steps": KIS_D1_CAUSAL_REPRESENTATION_CPU_STEPS,
                "cuda_steps": KIS_D1_CAUSAL_REPRESENTATION_CUDA_STEPS,
                "cuda_max_seconds": int(KIS_D1_CAUSAL_REPRESENTATION_CUDA_MAX_SECONDS),
            },
            "scope": _non_promoting_scope(),
            "artifact_policy": {
                "repository_storage_allowed": False,
                "raw_rows_persisted": False,
                "feature_values_persisted": False,
                "target_values_persisted": False,
                "predictions_persisted": False,
                "numeric_losses_persisted": False,
                "weight_format": "numpy_npz_no_pickle",
            },
        },
        field_name="campaign_contract_sha256",
    )
    contract_path = output_directory / "campaign-contract.json"
    recorded_contract = _write_or_reattach_contract(contract_path, payload)
    contract_sha256 = str(recorded_contract["campaign_contract_sha256"])
    registry_entry = register_frozen_campaign(
        contract_hash=contract_sha256,
        dataset_hash=dataset.dataset_hash,
        split_hash=_sha256_json(payload["geometry"]),
        cost_model_hash=_sha256_json({"cost_model": "not_applicable_target_free"}),
        trial_family=KIS_D1_CAUSAL_REPRESENTATION_ID,
        holdout_access="none",
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    return KisD1CausalRepresentationContract(
        dataset=dataset,
        artifact_root=artifact_root.resolve(),
        repo_root=repo_root.resolve(),
        attempt_id=attempt_id,
        run_directory=output_directory,
        contract_path=contract_path,
        contract_sha256=contract_sha256,
        registry_entry=registry_entry,
    )


def run_kis_d1_causal_representation_cpu_smoke(
    contract: KisD1CausalRepresentationContract,
) -> KisD1CausalRepresentationRun:
    """Run the predeclared four-step CPU smoke before CUDA is considered."""

    return _run_training(
        contract,
        phase="cpu_smoke",
        device_name="cpu",
        max_steps=KIS_D1_CAUSAL_REPRESENTATION_CPU_STEPS,
        max_seconds=None,
    )


def run_kis_d1_causal_representation_cuda(
    contract: KisD1CausalRepresentationContract,
) -> KisD1CausalRepresentationRun:
    """Run the one bounded CUDA appointment or record that it is unavailable."""

    existing = _load_existing_run(contract, phase="cuda")
    if existing is not None:
        return _with_outcome(existing, _register_cuda_outcome(contract, existing))
    _require_completed_cpu_smoke(contract)
    torch = _torch()
    if not torch.cuda.is_available():
        result = _unavailable_cuda_result(contract)
        return _with_outcome(result, _register_cuda_outcome(contract, result))
    result = _run_training(
        contract,
        phase="cuda",
        device_name="cuda",
        max_steps=KIS_D1_CAUSAL_REPRESENTATION_CUDA_STEPS,
        max_seconds=KIS_D1_CAUSAL_REPRESENTATION_CUDA_MAX_SECONDS,
    )
    return _with_outcome(result, _register_cuda_outcome(contract, result))


def _run_training(
    contract: KisD1CausalRepresentationContract,
    *,
    phase: Literal["cpu_smoke", "cuda"],
    device_name: Literal["cpu", "cuda"],
    max_steps: int,
    max_seconds: float | None,
) -> KisD1CausalRepresentationRun:
    existing = _load_existing_run(contract, phase=phase)
    if existing is not None:
        return existing
    if max_steps <= 0:
        raise ValueError("representation training steps must be positive")
    torch = _torch()
    numpy = _numpy()
    _configure_torch_determinism(torch, device_name=device_name)
    model = _build_causal_tcn(torch).to(torch.device(device_name))
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=KIS_D1_CAUSAL_REPRESENTATION_LEARNING_RATE,
        weight_decay=KIS_D1_CAUSAL_REPRESENTATION_WEIGHT_DECAY,
    )
    train_inputs, train_targets = mask_causal_representation_windows(
        contract.dataset.training_windows
    )
    diagnostic_inputs, diagnostic_targets = mask_causal_representation_windows(
        contract.dataset.diagnostic_windows
    )
    device = torch.device(device_name)
    train_input_tensor = torch.tensor(train_inputs, dtype=torch.float32, device=device)
    train_target_tensor = torch.tensor(train_targets, dtype=torch.float32, device=device)
    diagnostic_input_tensor = torch.tensor(diagnostic_inputs, dtype=torch.float32, device=device)
    diagnostic_target_tensor = torch.tensor(
        diagnostic_targets,
        dtype=torch.float32,
        device=device,
    )
    row_count = int(train_input_tensor.shape[0])
    if row_count <= 0:
        raise ValueError("representation training has no rows")

    started = time.monotonic()
    first_loss: float | None = None
    last_loss: float | None = None
    steps_completed = 0
    status: RepresentationRunStatus = "completed"
    for step in range(max_steps):
        if max_seconds is not None and time.monotonic() - started >= max_seconds:
            status = "time_bounded"
            break
        start = (step * KIS_D1_CAUSAL_REPRESENTATION_BATCH_SIZE) % row_count
        stop = min(start + KIS_D1_CAUSAL_REPRESENTATION_BATCH_SIZE, row_count)
        batch_inputs = train_input_tensor[start:stop]
        batch_targets = train_target_tensor[start:stop]
        optimizer.zero_grad(set_to_none=True)
        prediction = model(batch_inputs)
        residual = (
            prediction[:, -KIS_D1_CAUSAL_REPRESENTATION_MASK_ROWS :, :]
            - batch_targets
        )
        loss = torch.mean(residual**2)
        if not bool(torch.isfinite(loss).item()):
            raise RuntimeError("representation training loss is not finite")
        loss.backward()
        optimizer.step()
        value = float(loss.detach().cpu().item())
        if first_loss is None:
            first_loss = value
        last_loss = value
        steps_completed += 1
    if first_loss is None or last_loss is None:
        raise RuntimeError("representation training completed no optimizer steps")
    model.eval()
    with torch.no_grad():
        diagnostic_prediction = model(diagnostic_input_tensor)
        diagnostic_loss = torch.mean(
            (
                diagnostic_prediction[:, -KIS_D1_CAUSAL_REPRESENTATION_MASK_ROWS :, :]
                - diagnostic_target_tensor
            )
            ** 2
        )
    diagnostic_value = float(diagnostic_loss.detach().cpu().item())
    if not math.isfinite(diagnostic_value):
        raise RuntimeError("representation diagnostic loss is not finite")
    weights_path = contract.run_directory / f"{phase}-weights.npz"
    weights_sha256 = _write_or_verify_safe_weights(
        path=weights_path,
        model=model,
        numpy=numpy,
    )
    summary = _signed_payload(
        {
            "schema_version": SCHEMA_VERSION,
            "campaign_id": KIS_D1_CAUSAL_REPRESENTATION_ID,
            "campaign_contract_sha256": contract.contract_sha256,
            "phase": phase,
            "status": status,
            "device": device_name,
            "steps_completed": steps_completed,
            "training_loss_finite": math.isfinite(last_loss),
            "training_loss_decreased": last_loss < first_loss,
            "diagnostic_loss_finite": math.isfinite(diagnostic_value),
            "weights_sha256": weights_sha256,
            "scope": _non_promoting_scope(),
        },
        field_name="summary_sha256",
    )
    summary_path = contract.run_directory / f"{phase}-summary.json"
    _write_or_verify_json(summary_path, summary)
    return _run_from_summary(contract, summary_path, weights_path=weights_path)


def _unavailable_cuda_result(
    contract: KisD1CausalRepresentationContract,
) -> KisD1CausalRepresentationRun:
    summary = _signed_payload(
        {
            "schema_version": SCHEMA_VERSION,
            "campaign_id": KIS_D1_CAUSAL_REPRESENTATION_ID,
            "campaign_contract_sha256": contract.contract_sha256,
            "phase": "cuda",
            "status": "runtime_unavailable",
            "device": "unavailable",
            "steps_completed": 0,
            "training_loss_finite": False,
            "training_loss_decreased": False,
            "diagnostic_loss_finite": False,
            "scope": _non_promoting_scope(),
        },
        field_name="summary_sha256",
    )
    summary_path = contract.run_directory / "cuda-summary.json"
    _write_or_verify_json(summary_path, summary)
    return _run_from_summary(contract, summary_path, weights_path=None)


def _load_existing_run(
    contract: KisD1CausalRepresentationContract,
    *,
    phase: Literal["cpu_smoke", "cuda"],
) -> KisD1CausalRepresentationRun | None:
    summary_path = contract.run_directory / f"{phase}-summary.json"
    if not summary_path.exists():
        return None
    weights_path = contract.run_directory / f"{phase}-weights.npz"
    return _run_from_summary(
        contract,
        summary_path,
        weights_path=weights_path if weights_path.exists() else None,
    )


def _run_from_summary(
    contract: KisD1CausalRepresentationContract,
    summary_path: Path,
    *,
    weights_path: Path | None,
) -> KisD1CausalRepresentationRun:
    summary = _read_json_object(summary_path)
    summary_sha256 = _verify_signed_payload(summary, field_name="summary_sha256")
    phase = summary.get("phase")
    status = summary.get("status")
    device = summary.get("device")
    if (
        summary.get("campaign_id") != KIS_D1_CAUSAL_REPRESENTATION_ID
        or summary.get("campaign_contract_sha256") != contract.contract_sha256
        or phase not in {"cpu_smoke", "cuda"}
        or status not in {"completed", "runtime_unavailable", "time_bounded"}
        or device not in {"cpu", "cuda", "unavailable"}
        or not isinstance(summary.get("steps_completed"), int)
        or not isinstance(summary.get("training_loss_finite"), bool)
        or not isinstance(summary.get("training_loss_decreased"), bool)
        or not isinstance(summary.get("diagnostic_loss_finite"), bool)
        or summary.get("scope") != _non_promoting_scope()
    ):
        raise ValueError("representation summary is malformed")
    if phase != summary_path.name.removesuffix("-summary.json"):
        raise ValueError("representation summary phase does not match its artifact path")
    expected_weights_hash = summary.get("weights_sha256")
    if weights_path is None:
        if expected_weights_hash is not None:
            raise ValueError("representation summary requires a missing weights artifact")
        weights_sha256 = None
    else:
        if (
            not _is_sha256(expected_weights_hash)
            or not weights_path.is_file()
            or weights_path.is_symlink()
        ):
            raise ValueError("representation weights artifact is invalid")
        weights_sha256 = _sha256_file(weights_path)
        if weights_sha256 != expected_weights_hash:
            raise ValueError("representation weights artifact conflicts with its summary")
        _verify_safe_weight_archive(weights_path)
    return KisD1CausalRepresentationRun(
        phase=phase,
        status=status,
        device=device,
        steps_completed=summary["steps_completed"],
        training_loss_finite=summary["training_loss_finite"],
        training_loss_decreased=summary["training_loss_decreased"],
        diagnostic_loss_finite=summary["diagnostic_loss_finite"],
        summary_path=summary_path,
        summary_sha256=summary_sha256,
        weights_path=weights_path,
        weights_sha256=weights_sha256,
    )


def _with_outcome(
    result: KisD1CausalRepresentationRun,
    outcome: CampaignOutcomeRegistryEntry,
) -> KisD1CausalRepresentationRun:
    return KisD1CausalRepresentationRun(
        phase=result.phase,
        status=result.status,
        device=result.device,
        steps_completed=result.steps_completed,
        training_loss_finite=result.training_loss_finite,
        training_loss_decreased=result.training_loss_decreased,
        diagnostic_loss_finite=result.diagnostic_loss_finite,
        summary_path=result.summary_path,
        summary_sha256=result.summary_sha256,
        weights_path=result.weights_path,
        weights_sha256=result.weights_sha256,
        registry_outcome=outcome,
    )


def _register_cuda_outcome(
    contract: KisD1CausalRepresentationContract,
    result: KisD1CausalRepresentationRun,
) -> CampaignOutcomeRegistryEntry:
    return register_campaign_outcome(
        contract_hash=contract.contract_sha256,
        outcome_class=(
            "non_promoting_completed"
            if result.status == "completed"
            else "non_promoting_failed"
        ),
        outcome_reference_sha256=result.summary_sha256,
        artifact_root=contract.artifact_root,
        repo_root=contract.repo_root,
    )


def _require_completed_cpu_smoke(contract: KisD1CausalRepresentationContract) -> None:
    run = _load_existing_run(contract, phase="cpu_smoke")
    if (
        run is None
        or run.status != "completed"
        or run.device != "cpu"
        or run.steps_completed != KIS_D1_CAUSAL_REPRESENTATION_CPU_STEPS
        or not run.training_loss_finite
        or not run.diagnostic_loss_finite
    ):
        raise ValueError("a completed CPU smoke is required before CUDA")


def _build_causal_tcn(torch: Any) -> Any:
    """Create the one fixed architecture with left-only receptive fields."""

    nn = torch.nn
    functional = torch.nn.functional

    class CausalTCN(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            channels = len(KIS_D1_CAUSAL_REPRESENTATION_FEATURE_NAMES) + 1
            layers: list[Any] = []
            for dilation in KIS_D1_CAUSAL_REPRESENTATION_DILATIONS:
                layers.append(
                    nn.Conv1d(
                        channels,
                        KIS_D1_CAUSAL_REPRESENTATION_HIDDEN_CHANNELS,
                        kernel_size=KIS_D1_CAUSAL_REPRESENTATION_KERNEL_SIZE,
                        dilation=dilation,
                    )
                )
                channels = KIS_D1_CAUSAL_REPRESENTATION_HIDDEN_CHANNELS
            self.layers = nn.ModuleList(layers)
            self.head = nn.Conv1d(
                channels,
                len(KIS_D1_CAUSAL_REPRESENTATION_FEATURE_NAMES),
                kernel_size=1,
            )

        def forward(self, values: Any) -> Any:
            encoded = values.transpose(1, 2)
            for convolution, dilation in zip(
                self.layers,
                KIS_D1_CAUSAL_REPRESENTATION_DILATIONS,
                strict=True,
            ):
                left_padding = dilation * (KIS_D1_CAUSAL_REPRESENTATION_KERNEL_SIZE - 1)
                encoded = functional.pad(encoded, (left_padding, 0))
                encoded = torch.relu(convolution(encoded))
            return self.head(encoded).transpose(1, 2)

    return CausalTCN()


def _feature_rows(bars: Sequence[object], *, symbol: str) -> Any:
    numpy = _numpy()
    if len(bars) != KIS_D1_CAUSAL_REPRESENTATION_DEVELOPMENT_SESSIONS:
        raise ValueError("representation development session count is invalid")
    values: list[tuple[float, float, float, float, float]] = []
    previous_volume: float | None = None
    previous_close: float | None = None
    for bar in bars:
        if (
            getattr(bar, "symbol", None) != symbol
            or getattr(bar, "market", None) != "US"
            or getattr(bar, "timeframe", None) is not Timeframe.D1
            or not getattr(bar, "complete", False)
        ):
            raise ValueError("representation bar identity is invalid")
        typed_bar = cast(Any, bar)
        opening = float(typed_bar.open)
        high = float(typed_bar.high)
        low = float(typed_bar.low)
        close = float(typed_bar.close)
        volume = float(typed_bar.volume)
        if (
            not all(
                math.isfinite(value) and value > 0.0
                for value in (opening, high, low, close, volume)
            )
            or high < low
        ):
            raise ValueError("representation bar values are invalid")
        if previous_close is not None and previous_volume is not None:
            values.append(
                (
                    math.log(close / previous_close),
                    math.log(high / opening),
                    math.log(low / opening),
                    math.log(close / opening),
                    math.log(volume / previous_volume),
                )
            )
        previous_close = close
        previous_volume = volume
    result = numpy.asarray(values, dtype=numpy.float64)
    if result.shape != (
        KIS_D1_CAUSAL_REPRESENTATION_DEVELOPMENT_SESSIONS - 1,
        len(KIS_D1_CAUSAL_REPRESENTATION_FEATURE_NAMES),
    ) or not numpy.isfinite(result).all():
        raise ValueError("representation feature rows are invalid")
    return result


def _windows(values: Any) -> Any:
    numpy = _numpy()
    if values.ndim != 2 or values.shape[0] < KIS_D1_CAUSAL_REPRESENTATION_WINDOW_LENGTH:
        raise ValueError("representation window source is too short")
    windows = numpy.asarray(
        [
            values[start : start + KIS_D1_CAUSAL_REPRESENTATION_WINDOW_LENGTH]
            for start in range(values.shape[0] - KIS_D1_CAUSAL_REPRESENTATION_WINDOW_LENGTH + 1)
        ],
        dtype=numpy.float32,
    )
    _require_windows(windows, field_name="derived representation windows")
    return windows


def _require_development_phase(development_phase: object, *, input_id: str) -> None:
    if (
        input_id != "kis.paper.private.daily.nas.sequence.input-v1"
        or getattr(development_phase, "phase", None) != "development"
        or getattr(development_phase, "parent_dataset_id", None)
        != KIS_D1_CAUSAL_REPRESENTATION_DATASET_ID
        or getattr(development_phase, "parent_dataset_hash", None)
        != KIS_D1_CAUSAL_REPRESENTATION_DATASET_HASH
        or not _is_sha256(getattr(development_phase, "index_hash", None))
        or tuple(getattr(development_phase, "bars_by_symbol", ()))
        != KIS_D1_CAUSAL_REPRESENTATION_SYMBOLS
        or len(getattr(development_phase, "common_sessions", ()))
        != KIS_D1_CAUSAL_REPRESENTATION_DEVELOPMENT_SESSIONS
    ):
        raise ValueError("representation requires the exact KIS D1 development phase")


def _require_windows(values: Any, *, field_name: str) -> None:
    numpy = _numpy()
    if (
        values.ndim != 3
        or values.shape[0] <= 0
        or values.shape[1] != KIS_D1_CAUSAL_REPRESENTATION_WINDOW_LENGTH
        or values.shape[2] != len(KIS_D1_CAUSAL_REPRESENTATION_FEATURE_NAMES)
        or not numpy.isfinite(values).all()
    ):
        raise ValueError(f"{field_name} are invalid")


def _configure_torch_determinism(torch: Any, *, device_name: Literal["cpu", "cuda"]) -> None:
    torch.manual_seed(KIS_D1_CAUSAL_REPRESENTATION_SEED)
    torch.use_deterministic_algorithms(True)
    if device_name == "cuda":
        torch.cuda.manual_seed_all(KIS_D1_CAUSAL_REPRESENTATION_SEED)
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.allow_tf32 = False
        torch.backends.cuda.matmul.allow_tf32 = False
        if hasattr(torch, "set_float32_matmul_precision"):
            torch.set_float32_matmul_precision("highest")


def _write_or_verify_safe_weights(*, path: Path, model: Any, numpy: Any) -> str:
    arrays: dict[str, Any] = {}
    for name, tensor in sorted(model.state_dict().items()):
        array = tensor.detach().cpu().contiguous().numpy()
        if array.dtype.hasobject:
            raise ValueError("representation weights cannot contain object values")
        arrays[name] = array
    if path.exists():
        _verify_safe_weight_archive(path)
        raise FileExistsError("orphaned representation weights require recovery")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        numpy.savez_compressed(handle, **arrays)
    _verify_safe_weight_archive(path)
    return _sha256_file(path)


def _verify_safe_weight_archive(path: Path) -> None:
    numpy = _numpy()
    if not path.is_file() or path.is_symlink():
        raise ValueError("representation weights cannot be a link or missing")
    try:
        with numpy.load(path, allow_pickle=False) as archive:
            names = tuple(archive.files)
            if not names:
                raise ValueError("representation weights archive is empty")
            for name in names:
                value = archive[name]
                if (
                    not name
                    or value.dtype.hasobject
                    or value.size <= 0
                    or not numpy.isfinite(value).all()
                ):
                    raise ValueError("representation weights archive is unsafe")
    except (OSError, ValueError) as exc:
        raise ValueError("representation weights archive is invalid") from exc


def _external_run_directory(artifact_root: Path, repo_root: Path, *, attempt_id: str) -> Path:
    requested_root = Path(artifact_root)
    repository = Path(repo_root).resolve()
    _reject_repo_artifact_path(requested_root, repository)
    requested_root.mkdir(parents=True, exist_ok=True)
    _reject_repo_artifact_path(requested_root, repository)
    output = (
        requested_root
        / "research"
        / KIS_D1_CAUSAL_REPRESENTATION_ID
        / f"attempt={attempt_id}"
    )
    _reject_link_components(output)
    output.mkdir(parents=True, exist_ok=True)
    _reject_link_components(output)
    _reject_repo_artifact_path(output, repository)
    return output.resolve()


def _reject_link_components(path: Path) -> None:
    current = Path(path)
    while True:
        if current.is_symlink():
            raise ValueError("representation artifact path cannot contain a link")
        if current == current.parent:
            return
        current = current.parent


def _write_or_verify_json(path: Path, payload: Mapping[str, object]) -> None:
    if path.exists():
        if path.is_symlink() or _read_json_object(path) != dict(payload):
            raise ValueError("representation artifact conflicts with the frozen contract")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _write_or_reattach_contract(
    path: Path,
    payload: Mapping[str, object],
) -> dict[str, object]:
    if not path.exists():
        _write_or_verify_json(path, payload)
        return dict(payload)
    existing = _read_json_object(path)
    _verify_signed_payload(existing, field_name="campaign_contract_sha256")
    if existing == dict(payload):
        return existing
    expected_without_provenance = _contract_without_code_provenance(payload)
    existing_without_provenance = _contract_without_code_provenance(existing)
    if existing_without_provenance != expected_without_provenance:
        raise ValueError("representation artifact conflicts with the frozen contract")
    return existing


def _contract_without_code_provenance(payload: Mapping[str, object]) -> dict[str, object]:
    result = dict(payload)
    result.pop("code_revision", None)
    result.pop("campaign_contract_sha256", None)
    return result


def _read_json_object(path: Path) -> dict[str, object]:
    if not path.is_file() or path.is_symlink():
        raise ValueError("representation artifact is missing or invalid")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("representation artifact is malformed") from exc
    if not isinstance(payload, dict):
        raise ValueError("representation artifact must be a JSON object")
    return payload


def _signed_payload(payload: Mapping[str, object], *, field_name: str) -> dict[str, object]:
    result = dict(payload)
    result[field_name] = _sha256_json(result)
    return result


def _verify_signed_payload(payload: Mapping[str, object], *, field_name: str) -> str:
    recorded = payload.get(field_name)
    unsigned = dict(payload)
    unsigned.pop(field_name, None)
    if not _is_sha256(recorded) or recorded != _sha256_json(unsigned):
        raise ValueError("representation artifact checksum is invalid")
    return recorded


def _non_promoting_scope() -> dict[str, bool]:
    return {
        "source_local_only": True,
        "point_in_time_qualified": False,
        "trade_label_used": False,
        "forecast_eligible": False,
        "ranking_eligible": False,
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
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _sha256_json(value: Mapping[str, object]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _require_attempt_id(value: str) -> None:
    if re.fullmatch(r"[a-z][a-z0-9-]{1,63}", value) is None:
        raise ValueError("representation attempt id is invalid")
