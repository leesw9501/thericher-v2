"""Offline CPU and CUDA plumbing for the frozen NAS candle-state campaign.

All fitting uses development labels only.  Validation runs only target-free
forwards.  This candidate screen has no provider, credential, broker, replay,
PnL, ranking, selection, or promotion surface.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.data.kis_paper_daily_history_panel import KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
from thericher_v2.research.kis_nas_d1_candle_state_campaign import (
    KIS_NAS_D1_CANDLE_STATE_ALLOWED_REVIEW_STATUSES,
    KIS_NAS_D1_CANDLE_STATE_CPU_SMOKE_ID,
    KIS_NAS_D1_CANDLE_STATE_FEATURE_COUNT,
    KIS_NAS_D1_CANDLE_STATE_GPU_BREADTH_ID,
    KisNasD1CandleStateCampaignInput,
    KisNasD1CandleStateDevelopmentSample,
    KisNasD1CandleStateValidationSample,
    calculate_kis_nas_d1_candle_state_campaign_precommit_hash,
    require_attested_kis_nas_d1_candle_state_campaign_input,
)
from thericher_v2.research.sequence_architecture_models import (
    SequenceArchitectureId,
    build_torch_sequence_model,
)

KIS_NAS_D1_CANDLE_STATE_BREADTH_ID = "kis-nas-d1-candle-state-breadth-v3"
KIS_NAS_D1_CANDLE_STATE_BREADTH_ARTIFACT_ROOT = Path(
    "D:/thericher-v2/model-artifacts/research"
)
KIS_NAS_D1_CANDLE_STATE_CPU_LOGISTIC_STEPS = 32
KIS_NAS_D1_CANDLE_STATE_CPU_LOGISTIC_LEARNING_RATE = 0.08
KIS_NAS_D1_CANDLE_STATE_CPU_LOGISTIC_L2 = 0.0001
KIS_NAS_D1_CANDLE_STATE_STANDARDIZER_SCALE_FLOOR = 1e-12
KIS_NAS_D1_CANDLE_STATE_CUDA_EPOCHS = 6
KIS_NAS_D1_CANDLE_STATE_CUDA_BATCH_SIZE = 128
KIS_NAS_D1_CANDLE_STATE_CUDA_MAX_SECONDS_PER_CANDIDATE = 120
KIS_NAS_D1_CANDLE_STATE_CUDA_HIDDEN_SIZE = 16
KIS_NAS_D1_CANDLE_STATE_CUDA_ATTENTION_HEADS = 4
KIS_NAS_D1_CANDLE_STATE_CUDA_TCN_KERNEL_SIZE = 3
KIS_NAS_D1_CANDLE_STATE_CUDA_LEARNING_RATE = 0.001

_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)
_BREADTH_INPUT_ATTESTATION = object()
_MODULE_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_DOCKER_REPOSITORY_ROOT = Path("/app")
_DOCKER_ARTIFACT_ROOT = _DOCKER_REPOSITORY_ROOT / "model_artifacts"
_STANDARDIZER_DECIMAL_PRECISION = 36
_STANDARDIZER_QUANTUM = Decimal("0.000000000001")
_CPU_SUMMARY_ATTESTATION_FILENAME = "summary-attestation.json"


@dataclass(frozen=True, slots=True)
class KisNasD1CandleStateStandardizer:
    """A development-only per-channel standardizer for one symbol."""

    symbol: str
    development_input_hash: str
    means: tuple[float, ...]
    scales: tuple[float, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "means",
            tuple(_canonical_standardizer_number(value) for value in self.means),
        )
        object.__setattr__(
            self,
            "scales",
            tuple(_canonical_standardizer_number(value) for value in self.scales),
        )
        if (
            self.symbol not in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            or not _is_sha256(self.development_input_hash)
            or len(self.means) != KIS_NAS_D1_CANDLE_STATE_FEATURE_COUNT
            or len(self.scales) != KIS_NAS_D1_CANDLE_STATE_FEATURE_COUNT
            or any(not math.isfinite(value) for value in self.means)
            or any(not math.isfinite(value) or value <= 0.0 for value in self.scales)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("NAS D1 candle-state standardizer is invalid")

    @property
    def standardizer_hash(self) -> str:
        return _sha256_payload(
            {
                "symbol": self.symbol,
                "development_input_hash": self.development_input_hash,
                "means": [format(value, ".12f") for value in self.means],
                "scales": [format(value, ".12f") for value in self.scales],
            }
        )

    def transform(
        self,
        values: Sequence[Sequence[float]],
        *,
        sequence_length: int,
    ) -> tuple[tuple[float, ...], ...]:
        result = tuple(
            tuple(
                (float(value) - self.means[index]) / self.scales[index]
                for index, value in enumerate(row)
            )
            for row in values
        )
        if (
            len(result) != sequence_length
            or any(len(row) != KIS_NAS_D1_CANDLE_STATE_FEATURE_COUNT for row in result)
            or any(not math.isfinite(value) for row in result for value in row)
        ):
            raise ValueError("NAS D1 candle-state standardized sequence is invalid")
        return result


@dataclass(frozen=True, slots=True)
class KisNasD1CandleStateL2LogisticSpec:
    """Fixed deterministic CPU fitting terms for one independent symbol."""

    symbol: str
    seed: int
    steps: int = KIS_NAS_D1_CANDLE_STATE_CPU_LOGISTIC_STEPS
    learning_rate: float = KIS_NAS_D1_CANDLE_STATE_CPU_LOGISTIC_LEARNING_RATE
    l2: float = KIS_NAS_D1_CANDLE_STATE_CPU_LOGISTIC_L2
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.symbol not in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            or self.seed < 0
            or self.steps <= 0
            or not math.isfinite(self.learning_rate)
            or self.learning_rate <= 0.0
            or not math.isfinite(self.l2)
            or self.l2 < 0.0
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("NAS D1 candle-state CPU specification is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "seed": self.seed,
            "steps": self.steps,
            "learning_rate": format(self.learning_rate, ".17g"),
            "l2": format(self.l2, ".17g"),
        }


KIS_NAS_D1_CANDLE_STATE_CPU_LOGISTIC_SPECS = tuple(
    KisNasD1CandleStateL2LogisticSpec(symbol=symbol, seed=2026072800 + index)
    for index, symbol in enumerate(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS)
)


@dataclass(frozen=True, slots=True)
class KisNasD1CandleStateL2LogisticModel:
    """In-memory CPU model state; receipts contain only its digest and losses."""

    spec: KisNasD1CandleStateL2LogisticSpec
    standardizer_hash: str
    weights: tuple[float, ...]
    intercept: float
    initial_loss: float
    final_loss: float
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "weights", tuple(float(value) for value in self.weights))
        expected_width = 20 * KIS_NAS_D1_CANDLE_STATE_FEATURE_COUNT
        if (
            not _is_sha256(self.standardizer_hash)
            or len(self.weights) != expected_width
            or any(not math.isfinite(value) for value in self.weights)
            or not math.isfinite(self.intercept)
            or not math.isfinite(self.initial_loss)
            or not math.isfinite(self.final_loss)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("NAS D1 candle-state CPU model is invalid")

    @property
    def parameter_hash(self) -> str:
        return _sha256_payload(
            {
                "spec": self.spec.safe_payload(),
                "standardizer_hash": self.standardizer_hash,
                "weights": [format(value, ".17g") for value in self.weights],
                "intercept": format(self.intercept, ".17g"),
            }
        )


@dataclass(frozen=True, slots=True)
class KisNasD1CandleStateTargetFreeForward:
    """Aggregate-only validation forward evidence."""

    symbol: str
    sample_count: int
    output_shape: tuple[int, int]
    all_finite: bool
    output_bounds_valid: bool
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.symbol not in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            or self.sample_count <= 0
            or self.output_shape != (self.sample_count, 1)
            or not self.all_finite
            or not self.output_bounds_valid
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("NAS D1 candle-state target-free forward is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "sample_count": self.sample_count,
            "output_shape": list(self.output_shape),
            "all_finite": self.all_finite,
            "output_bounds_valid": self.output_bounds_valid,
            "labels_materialized": False,
        }


@dataclass(frozen=True, slots=True)
class KisNasD1CandleStateArchitectureSpec:
    """One frozen GPU architecture/symbol breadth candidate."""

    architecture_id: SequenceArchitectureId
    symbol: str
    seed: int
    hidden_size: int = KIS_NAS_D1_CANDLE_STATE_CUDA_HIDDEN_SIZE
    attention_heads: int = KIS_NAS_D1_CANDLE_STATE_CUDA_ATTENTION_HEADS
    tcn_kernel_size: int = KIS_NAS_D1_CANDLE_STATE_CUDA_TCN_KERNEL_SIZE
    learning_rate: float = KIS_NAS_D1_CANDLE_STATE_CUDA_LEARNING_RATE
    epochs: int = KIS_NAS_D1_CANDLE_STATE_CUDA_EPOCHS
    batch_size: int = KIS_NAS_D1_CANDLE_STATE_CUDA_BATCH_SIZE
    max_seconds: int = KIS_NAS_D1_CANDLE_STATE_CUDA_MAX_SECONDS_PER_CANDIDATE
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.architecture_id not in {"lstm", "causal_tcn", "compact_attention"}
            or self.symbol not in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            or self.seed < 0
            or self.hidden_size <= 0
            or self.attention_heads <= 0
            or self.hidden_size % self.attention_heads != 0
            or self.tcn_kernel_size <= 0
            or not math.isfinite(self.learning_rate)
            or self.learning_rate <= 0.0
            or self.epochs <= 0
            or self.batch_size <= 0
            or self.max_seconds <= 0
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("NAS D1 candle-state CUDA architecture specification is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "architecture_id": self.architecture_id,
            "symbol": self.symbol,
            "seed": self.seed,
            "hidden_size": self.hidden_size,
            "attention_heads": self.attention_heads,
            "tcn_kernel_size": self.tcn_kernel_size,
            "learning_rate": format(self.learning_rate, ".17g"),
            "epochs": self.epochs,
            "batch_size": self.batch_size,
            "max_seconds": self.max_seconds,
        }


KIS_NAS_D1_CANDLE_STATE_CUDA_ARCHITECTURE_SPECS = tuple(
    KisNasD1CandleStateArchitectureSpec(
        architecture_id=architecture_id,
        symbol=symbol,
        seed=2026072900 + architecture_index * 10 + symbol_index,
    )
    for architecture_index, architecture_id in enumerate(
        ("lstm", "causal_tcn", "compact_attention")
    )
    for symbol_index, symbol in enumerate(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS)
)


@dataclass(frozen=True, slots=True, init=False)
class KisNasD1CandleStateBreadthInput:
    """Attested campaign plus development-only per-symbol standardizers."""

    campaign_input: KisNasD1CandleStateCampaignInput
    campaign_precommit_hash: str
    review_status: str
    standardizers_by_symbol: Mapping[str, KisNasD1CandleStateStandardizer]
    integrity_hash: str
    schema_version: int
    _attestation: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("use the attested NAS D1 candle-state breadth input builder")

    def standardizer(self, symbol: str) -> KisNasD1CandleStateStandardizer:
        _require_attested_breadth_input(self)
        return self.standardizers_by_symbol[_resolve_symbol(symbol)]


@dataclass(frozen=True, slots=True)
class KisNasD1CandleStateCpuCandidateReceipt:
    """Source-safe evidence for one independent CPU smoke fit."""

    model: KisNasD1CandleStateL2LogisticModel
    validation_forward: KisNasD1CandleStateTargetFreeForward
    development_sample_count: int
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.development_sample_count <= 0
            or self.model.spec.symbol != self.validation_forward.symbol
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("NAS D1 candle-state CPU candidate receipt is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "symbol": self.model.spec.symbol,
            "model_id": "l2_logistic",
            "model_parameter_hash": self.model.parameter_hash,
            "standardizer_hash": self.model.standardizer_hash,
            "development_sample_count": self.development_sample_count,
            "steps": self.model.spec.steps,
            "seed": self.model.spec.seed,
            "initial_loss": format(self.model.initial_loss, ".8f"),
            "final_loss": format(self.model.final_loss, ".8f"),
            "validation_forward": self.validation_forward.safe_payload(),
        }


@dataclass(frozen=True, slots=True)
class KisNasD1CandleStateCpuSmokeRun:
    """One complete six-symbol CPU smoke receipt."""

    breadth_input: KisNasD1CandleStateBreadthInput
    run_label: str
    precommit_path: Path
    precommit_hash: str
    summary_path: Path
    summary_hash: str
    summary_attestation_path: Path
    summary_attestation_hash: str
    candidates: tuple[KisNasD1CandleStateCpuCandidateReceipt, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidates", tuple(self.candidates))
        if (
            tuple(candidate.model.spec.symbol for candidate in self.candidates)
            != KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            or not _is_sha256(self.precommit_hash)
            or not _is_sha256(self.summary_hash)
            or not _is_sha256(self.summary_attestation_hash)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("NAS D1 candle-state CPU smoke did not complete every symbol")


@dataclass(frozen=True, slots=True)
class KisNasD1CandleStateGpuCandidateReceipt:
    """Aggregate-only receipt for one external CUDA checkpoint and forward pass."""

    spec: KisNasD1CandleStateArchitectureSpec
    development_sample_count: int
    validation_forward: KisNasD1CandleStateTargetFreeForward
    checkpoint_path: Path
    checkpoint_sha256: str
    backend: str
    device: str
    torch_version: str
    cuda_version: str | None
    initial_loss: float
    final_loss: float
    cuda_peak_memory_bytes: int
    safe_weights_only_reload: bool
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.development_sample_count <= 0
            or not self.checkpoint_path.is_file()
            or not _is_sha256(self.checkpoint_sha256)
            or _sha256_file(self.checkpoint_path) != self.checkpoint_sha256
            or self.validation_forward.symbol != self.spec.symbol
            or not self.backend
            or not self.device
            or not self.torch_version
            or not math.isfinite(self.initial_loss)
            or not math.isfinite(self.final_loss)
            or self.cuda_peak_memory_bytes < 0
            or not self.safe_weights_only_reload
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("NAS D1 candle-state CUDA candidate receipt is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "architecture": self.spec.safe_payload(),
            "development_sample_count": self.development_sample_count,
            "validation_forward": self.validation_forward.safe_payload(),
            "checkpoint_sha256": self.checkpoint_sha256,
            "backend": self.backend,
            "device": self.device,
            "torch_version": self.torch_version,
            "cuda_version": self.cuda_version,
            "initial_loss": format(self.initial_loss, ".8f"),
            "final_loss": format(self.final_loss, ".8f"),
            "cuda_peak_memory_bytes": self.cuda_peak_memory_bytes,
            "safe_weights_only_reload": self.safe_weights_only_reload,
        }


@dataclass(frozen=True, slots=True)
class KisNasD1CandleStateCudaFailure:
    """Source-safe categorical recovery fact for one frozen CUDA candidate."""

    spec: KisNasD1CandleStateArchitectureSpec
    category: Literal["timeout", "memory", "invalid", "runtime"]

    def safe_payload(self) -> dict[str, object]:
        return {"architecture": self.spec.safe_payload(), "category": self.category}


@dataclass(frozen=True, slots=True)
class KisNasD1CandleStateCudaBreadthRun:
    """A completed or precisely scoped CUDA breadth receipt."""

    breadth_input: KisNasD1CandleStateBreadthInput
    run_label: str
    cpu_smoke_summary_hash: str
    precommit_path: Path
    precommit_hash: str
    summary_path: Path
    summary_hash: str
    status: Literal["completed", "cuda_unavailable", "candidate_failed"]
    reason: str
    candidates: tuple[KisNasD1CandleStateGpuCandidateReceipt, ...]
    failure: KisNasD1CandleStateCudaFailure | None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidates", tuple(self.candidates))
        if (
            not _is_sha256(self.cpu_smoke_summary_hash)
            or not _is_sha256(self.precommit_hash)
            or not _is_sha256(self.summary_hash)
            or self.status not in {"completed", "cuda_unavailable", "candidate_failed"}
            or not self.reason
            or self.schema_version != SCHEMA_VERSION
            or (
                self.status == "completed"
                and len(self.candidates) != len(KIS_NAS_D1_CANDLE_STATE_CUDA_ARCHITECTURE_SPECS)
            )
            or (self.status == "candidate_failed" and self.failure is None)
            or (self.status == "cuda_unavailable" and self.candidates)
        ):
            raise ValueError("NAS D1 candle-state CUDA breadth receipt is invalid")


CudaCandidateTrainer = Callable[
    [KisNasD1CandleStateBreadthInput, KisNasD1CandleStateArchitectureSpec, Path],
    KisNasD1CandleStateGpuCandidateReceipt,
]


def build_kis_nas_d1_candle_state_breadth_input(
    campaign_input: KisNasD1CandleStateCampaignInput,
    *,
    campaign_precommit_hash: str,
    review_status: str,
) -> KisNasD1CandleStateBreadthInput:
    """Fit per-symbol normalizers from development rows and bind the precommit."""

    require_attested_kis_nas_d1_candle_state_campaign_input(campaign_input)
    if (
        campaign_precommit_hash
        != calculate_kis_nas_d1_candle_state_campaign_precommit_hash(
            campaign_input,
            review_status=review_status,
        )
    ):
        raise ValueError("NAS D1 candle-state breadth requires the matching campaign precommit")
    if review_status not in KIS_NAS_D1_CANDLE_STATE_ALLOWED_REVIEW_STATUSES:
        raise ValueError("NAS D1 candle-state review status is invalid")
    standardizers = {
        symbol: _fit_development_standardizer(
            symbol=symbol,
            samples=campaign_input.development_samples_by_symbol[symbol],
            development_input_hash=_symbol_development_input_hash(
                symbol,
                campaign_input.development_samples_by_symbol[symbol],
            ),
        )
        for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
    }
    result = object.__new__(KisNasD1CandleStateBreadthInput)
    object.__setattr__(result, "campaign_input", campaign_input)
    object.__setattr__(result, "campaign_precommit_hash", campaign_precommit_hash)
    object.__setattr__(result, "review_status", review_status)
    object.__setattr__(result, "standardizers_by_symbol", MappingProxyType(standardizers))
    object.__setattr__(result, "schema_version", SCHEMA_VERSION)
    object.__setattr__(result, "_attestation", _BREADTH_INPUT_ATTESTATION)
    object.__setattr__(
        result,
        "integrity_hash",
        _breadth_input_integrity_hash(
            campaign_input=campaign_input,
            campaign_precommit_hash=campaign_precommit_hash,
            review_status=review_status,
            standardizers_by_symbol=standardizers,
        ),
    )
    _require_attested_breadth_input(result)
    return result


def fit_kis_nas_d1_candle_state_l2_logistic_smoke(
    breadth_input: KisNasD1CandleStateBreadthInput,
    spec: KisNasD1CandleStateL2LogisticSpec,
) -> KisNasD1CandleStateL2LogisticModel:
    """Fit one deterministic CPU baseline against development labels only."""

    _require_attested_breadth_input(breadth_input)
    return _fit_kis_nas_d1_candle_state_l2_logistic_smoke_validated(breadth_input, spec)


def _fit_kis_nas_d1_candle_state_l2_logistic_smoke_validated(
    breadth_input: KisNasD1CandleStateBreadthInput,
    spec: KisNasD1CandleStateL2LogisticSpec,
) -> KisNasD1CandleStateL2LogisticModel:
    """Fit one model after the caller has attested its immutable input."""

    standardizer = breadth_input.standardizers_by_symbol[spec.symbol]
    samples = breadth_input.campaign_input.development_samples_by_symbol[spec.symbol]
    numpy = _numpy()
    features = _flatten_matrix_from_samples(samples, standardizer, numpy)
    labels = numpy.asarray([sample.label for sample in samples], dtype=numpy.float64)
    if labels.shape != (len(samples),) or not numpy.isfinite(labels).all():
        raise ValueError("NAS D1 candle-state CPU labels are invalid")
    generator = numpy.random.default_rng(spec.seed)
    weights = generator.normal(0.0, 0.001, size=features.shape[1])
    intercept = 0.0
    initial_loss = _logistic_loss(features, labels, weights, intercept, numpy)
    for _ in range(spec.steps):
        logits = numpy.clip(features @ weights + intercept, -60.0, 60.0)
        probabilities = 1.0 / (1.0 + numpy.exp(-logits))
        residual = probabilities - labels
        gradient = (features.T @ residual) / len(samples) + spec.l2 * weights
        intercept_gradient = float(residual.mean())
        weights -= spec.learning_rate * gradient
        intercept -= spec.learning_rate * intercept_gradient
    final_loss = _logistic_loss(features, labels, weights, intercept, numpy)
    return KisNasD1CandleStateL2LogisticModel(
        spec=spec,
        standardizer_hash=standardizer.standardizer_hash,
        weights=tuple(float(value) for value in weights),
        intercept=float(intercept),
        initial_loss=initial_loss,
        final_loss=final_loss,
    )


def forward_kis_nas_d1_candle_state_l2_logistic_target_free_validation(
    breadth_input: KisNasD1CandleStateBreadthInput,
    model: KisNasD1CandleStateL2LogisticModel,
) -> KisNasD1CandleStateTargetFreeForward:
    """Check a validation forward without exposing targets or predictions."""

    _require_attested_breadth_input(breadth_input)
    return _forward_kis_nas_d1_candle_state_l2_logistic_target_free_validation_validated(
        breadth_input,
        model,
    )


def _forward_kis_nas_d1_candle_state_l2_logistic_target_free_validation_validated(
    breadth_input: KisNasD1CandleStateBreadthInput,
    model: KisNasD1CandleStateL2LogisticModel,
) -> KisNasD1CandleStateTargetFreeForward:
    """Validate one CPU forward after its immutable input was attested."""

    standardizer = breadth_input.standardizers_by_symbol[model.spec.symbol]
    if model.standardizer_hash != standardizer.standardizer_hash:
        raise ValueError("NAS D1 candle-state CPU model standardizer does not match input")
    samples = breadth_input.campaign_input.validation_samples_by_symbol[model.spec.symbol]
    numpy = _numpy()
    features = _flatten_matrix_from_samples(
        samples,
        standardizer,
        numpy,
    )
    logits = numpy.clip(features @ model.weights + model.intercept, -60, 60)
    outputs = 1.0 / (1.0 + numpy.exp(-logits))
    if outputs.shape != (len(samples),) or not numpy.isfinite(outputs).all():
        raise ValueError("NAS D1 candle-state target-free CPU forward is invalid")
    return KisNasD1CandleStateTargetFreeForward(
        symbol=model.spec.symbol,
        sample_count=len(samples),
        output_shape=(len(samples), 1),
        all_finite=True,
        output_bounds_valid=bool(((outputs >= 0.0) & (outputs <= 1.0)).all()),
    )


def run_kis_nas_d1_candle_state_l2_logistic_smoke(
    breadth_input: KisNasD1CandleStateBreadthInput,
    *,
    artifact_root: Path | str = KIS_NAS_D1_CANDLE_STATE_BREADTH_ARTIFACT_ROOT,
    run_label: str,
    repo_root: Path | str | None = None,
) -> KisNasD1CandleStateCpuSmokeRun:
    """Run the fixed CPU baseline and write only aggregate external receipts."""

    _require_attested_breadth_input(breadth_input)
    output_dir = _prepare_output_dir(
        artifact_root=artifact_root,
        repo_root=repo_root,
        mode="cpu-smoke",
        run_label=run_label,
    )
    precommit_path = output_dir / "precommit.json"
    precommit_payload = _cpu_precommit_payload(breadth_input)
    _assert_source_safe(precommit_payload)
    precommit_hash = _write_json_new(precommit_path, precommit_payload)
    candidates = tuple(
        _cpu_candidate_receipt(breadth_input, spec)
        for spec in KIS_NAS_D1_CANDLE_STATE_CPU_LOGISTIC_SPECS
    )
    summary_path = output_dir / "summary.json"
    summary_payload = _cpu_summary_payload(
        breadth_input=breadth_input,
        precommit_hash=precommit_hash,
        candidates=candidates,
    )
    _assert_source_safe(summary_payload)
    summary_hash = _write_json_new(summary_path, summary_payload)
    summary_attestation_path = output_dir / _CPU_SUMMARY_ATTESTATION_FILENAME
    summary_attestation_payload = _cpu_summary_attestation_payload(
        breadth_input=breadth_input,
        precommit_hash=precommit_hash,
        summary_hash=summary_hash,
    )
    _assert_source_safe(summary_attestation_payload)
    summary_attestation_hash = _write_json_new(
        summary_attestation_path,
        summary_attestation_payload,
    )
    return KisNasD1CandleStateCpuSmokeRun(
        breadth_input=breadth_input,
        run_label=run_label,
        precommit_path=precommit_path,
        precommit_hash=precommit_hash,
        summary_path=summary_path,
        summary_hash=summary_hash,
        summary_attestation_path=summary_attestation_path,
        summary_attestation_hash=summary_attestation_hash,
        candidates=candidates,
    )


def run_kis_nas_d1_candle_state_cuda_breadth(
    breadth_input: KisNasD1CandleStateBreadthInput,
    *,
    cpu_smoke_summary_path: Path | str,
    artifact_root: Path | str = KIS_NAS_D1_CANDLE_STATE_BREADTH_ARTIFACT_ROOT,
    run_label: str,
    repo_root: Path | str | None = None,
    trainer: CudaCandidateTrainer | None = None,
) -> KisNasD1CandleStateCudaBreadthRun:
    """Run frozen sequential CUDA breadth or record one scoped runtime fact."""

    _require_attested_breadth_input(breadth_input)
    repository = _repository_root(repo_root)
    cpu_summary_hash = _validate_cpu_smoke_summary(
        Path(cpu_smoke_summary_path),
        breadth_input,
        repository=repository,
    )
    output_dir = _prepare_output_dir(
        artifact_root=artifact_root,
        repo_root=repository,
        mode="cuda-breadth",
        run_label=run_label,
    )
    precommit_path = output_dir / "precommit.json"
    precommit_payload = _cuda_precommit_payload(breadth_input, cpu_summary_hash)
    _assert_source_safe(precommit_payload)
    precommit_hash = _write_json_new(precommit_path, precommit_payload)
    torch = _torch_or_none()
    if torch is None or not bool(torch.cuda.is_available()):
        return _write_cuda_summary(
            breadth_input=breadth_input,
            run_label=run_label,
            output_dir=output_dir,
            cpu_smoke_summary_hash=cpu_summary_hash,
            precommit_path=precommit_path,
            precommit_hash=precommit_hash,
            status="cuda_unavailable",
            reason="PyTorch CUDA is unavailable in the research runtime",
            candidates=(),
            failure=None,
        )
    candidate_trainer = trainer or (
        lambda value, spec, checkpoint_dir: _train_torch_cuda_candidate(
            value,
            spec,
            checkpoint_dir,
            torch=torch,
        )
    )
    checkpoint_dir = output_dir / "checkpoints"
    checkpoint_dir.mkdir(exist_ok=False)
    _reject_link_or_junction_components(checkpoint_dir)
    _reject_repository_artifact_root(checkpoint_dir.resolve(), repository)
    _reject_repository_artifact_root(checkpoint_dir.resolve(), _MODULE_REPOSITORY_ROOT)
    candidates: list[KisNasD1CandleStateGpuCandidateReceipt] = []
    for spec in KIS_NAS_D1_CANDLE_STATE_CUDA_ARCHITECTURE_SPECS:
        try:
            candidate = candidate_trainer(breadth_input, spec, checkpoint_dir)
            _require_bound_cuda_candidate_receipt(
                candidate,
                breadth_input=breadth_input,
                spec=spec,
                checkpoint_dir=checkpoint_dir,
                repository=repository,
                require_torch_backend=trainer is None,
            )
            candidates.append(candidate)
        except Exception as exc:
            _remove_incomplete_checkpoint(checkpoint_dir, spec)
            failure = KisNasD1CandleStateCudaFailure(
                spec=spec,
                category=_cuda_failure_category(exc),
            )
            return _write_cuda_summary(
                breadth_input=breadth_input,
                run_label=run_label,
                output_dir=output_dir,
                cpu_smoke_summary_hash=cpu_summary_hash,
                precommit_path=precommit_path,
                precommit_hash=precommit_hash,
                status="candidate_failed",
                reason="one frozen CUDA candidate stopped before completion",
                candidates=tuple(candidates),
                failure=failure,
            )
    return _write_cuda_summary(
        breadth_input=breadth_input,
        run_label=run_label,
        output_dir=output_dir,
        cpu_smoke_summary_hash=cpu_summary_hash,
        precommit_path=precommit_path,
        precommit_hash=precommit_hash,
        status="completed",
        reason="all frozen CUDA candidates completed target-free validation forwards",
        candidates=tuple(candidates),
        failure=None,
    )


def _require_attested_breadth_input(value: object) -> None:
    if (
        not isinstance(value, KisNasD1CandleStateBreadthInput)
        or getattr(value, "_attestation", None) is not _BREADTH_INPUT_ATTESTATION
        or value.schema_version != SCHEMA_VERSION
        or not _is_sha256(value.campaign_precommit_hash)
        or not _is_sha256(value.integrity_hash)
        or value.review_status not in KIS_NAS_D1_CANDLE_STATE_ALLOWED_REVIEW_STATUSES
        or tuple(value.standardizers_by_symbol) != KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
    ):
        raise ValueError("NAS D1 candle-state breadth input is invalid")
    require_attested_kis_nas_d1_candle_state_campaign_input(value.campaign_input)
    expected_precommit_hash = calculate_kis_nas_d1_candle_state_campaign_precommit_hash(
        value.campaign_input,
        review_status=value.review_status,
    )
    if value.campaign_precommit_hash != expected_precommit_hash:
        raise ValueError("NAS D1 candle-state breadth precommit is invalid")
    for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        standardizer = value.standardizers_by_symbol[symbol]
        if (
            not isinstance(standardizer, KisNasD1CandleStateStandardizer)
            or standardizer.symbol != symbol
            or standardizer.development_input_hash
            != _symbol_development_input_hash(
                symbol,
                value.campaign_input.development_samples_by_symbol[symbol],
            )
        ):
            raise ValueError("NAS D1 candle-state breadth standardizer is invalid")
    if value.integrity_hash != _breadth_input_integrity_hash(
        campaign_input=value.campaign_input,
        campaign_precommit_hash=value.campaign_precommit_hash,
        review_status=value.review_status,
        standardizers_by_symbol=value.standardizers_by_symbol,
    ):
        raise ValueError("NAS D1 candle-state breadth input integrity is invalid")


def _breadth_input_integrity_hash(
    *,
    campaign_input: KisNasD1CandleStateCampaignInput,
    campaign_precommit_hash: str,
    review_status: str,
    standardizers_by_symbol: Mapping[str, KisNasD1CandleStateStandardizer],
) -> str:
    return _sha256_payload(
        {
            "campaign_contract_hash": campaign_input.contract.contract_hash,
            "development_input_hash": campaign_input.development_input_hash,
            "validation_input_hash": campaign_input.validation_input_hash,
            "campaign_precommit_hash": campaign_precommit_hash,
            "review_status": review_status,
            "standardizer_hashes": [
                standardizers_by_symbol[symbol].standardizer_hash
                for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            ],
        }
    )


def _fit_development_standardizer(
    *,
    symbol: str,
    samples: Sequence[KisNasD1CandleStateDevelopmentSample],
    development_input_hash: str,
) -> KisNasD1CandleStateStandardizer:
    numpy = _numpy()
    values = numpy.asarray(
        [row for sample in samples for row in sample.feature_sequence],
        dtype=numpy.float64,
    )
    if (
        values.shape != (len(samples) * 20, KIS_NAS_D1_CANDLE_STATE_FEATURE_COUNT)
        or not numpy.isfinite(values).all()
    ):
        raise ValueError("NAS D1 candle-state development standardizer input is invalid")
    feature_rows = tuple(
        tuple(float(value) for value in row)
        for sample in samples
        for row in sample.feature_sequence
    )
    means = tuple(
        _canonical_standardizer_number(
            math.fsum(row[feature_index] for row in feature_rows) / len(feature_rows)
        )
        for feature_index in range(KIS_NAS_D1_CANDLE_STATE_FEATURE_COUNT)
    )
    observed_scales = tuple(
        _canonical_standardizer_number(
            math.sqrt(
                math.fsum(
                    (row[feature_index] - means[feature_index]) ** 2
                    for row in feature_rows
                )
                / len(feature_rows)
            )
        )
        for feature_index in range(KIS_NAS_D1_CANDLE_STATE_FEATURE_COUNT)
    )
    scales = tuple(
        value if value > KIS_NAS_D1_CANDLE_STATE_STANDARDIZER_SCALE_FLOOR else 1.0
        for value in observed_scales
    )
    return KisNasD1CandleStateStandardizer(
        symbol=symbol,
        development_input_hash=development_input_hash,
        means=means,
        scales=scales,
    )


def _canonical_standardizer_number(value: object) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("NAS D1 candle-state standardizer value is invalid") from exc
    if not math.isfinite(numeric):
        raise ValueError("NAS D1 candle-state standardizer value is invalid")
    with localcontext() as context:
        context.prec = _STANDARDIZER_DECIMAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        canonical = Decimal(format(numeric, ".17g")).quantize(
            _STANDARDIZER_QUANTUM,
            rounding=ROUND_HALF_EVEN,
        )
    result = float(canonical)
    if not math.isfinite(result):
        raise ValueError("NAS D1 candle-state standardizer value is invalid")
    return result


def _flatten_matrix_from_samples(
    samples: Sequence[KisNasD1CandleStateDevelopmentSample | KisNasD1CandleStateValidationSample],
    standardizer: KisNasD1CandleStateStandardizer,
    numpy: object,
) -> object:
    transformed = tuple(
        standardizer.transform(sample.feature_sequence, sequence_length=20) for sample in samples
    )
    matrix = numpy.asarray(transformed, dtype=numpy.float64)
    if matrix.shape != (len(samples), 20, KIS_NAS_D1_CANDLE_STATE_FEATURE_COUNT):
        raise ValueError("NAS D1 candle-state sequence matrix is invalid")
    return matrix.reshape(len(samples), -1)


def _sequence_matrix_from_samples(
    samples: Sequence[KisNasD1CandleStateDevelopmentSample | KisNasD1CandleStateValidationSample],
    standardizer: KisNasD1CandleStateStandardizer,
    numpy: object,
) -> object:
    transformed = tuple(
        standardizer.transform(sample.feature_sequence, sequence_length=20) for sample in samples
    )
    matrix = numpy.asarray(transformed, dtype=numpy.float32)
    if (
        matrix.shape != (len(samples), 20, KIS_NAS_D1_CANDLE_STATE_FEATURE_COUNT)
        or not numpy.isfinite(matrix).all()
    ):
        raise ValueError("NAS D1 candle-state sequence tensor is invalid")
    return matrix


def _cpu_candidate_receipt(
    breadth_input: KisNasD1CandleStateBreadthInput,
    spec: KisNasD1CandleStateL2LogisticSpec,
) -> KisNasD1CandleStateCpuCandidateReceipt:
    model = _fit_kis_nas_d1_candle_state_l2_logistic_smoke_validated(breadth_input, spec)
    return KisNasD1CandleStateCpuCandidateReceipt(
        model=model,
        validation_forward=_forward_kis_nas_d1_candle_state_l2_logistic_target_free_validation_validated(
            breadth_input,
            model,
        ),
        development_sample_count=len(
            breadth_input.campaign_input.development_samples_by_symbol[spec.symbol]
        ),
    )


def _train_torch_cuda_candidate(
    breadth_input: KisNasD1CandleStateBreadthInput,
    spec: KisNasD1CandleStateArchitectureSpec,
    checkpoint_dir: Path,
    *,
    torch: object,
) -> KisNasD1CandleStateGpuCandidateReceipt:
    standardizer = breadth_input.standardizers_by_symbol[spec.symbol]
    development = breadth_input.campaign_input.development_samples_by_symbol[spec.symbol]
    validation = breadth_input.campaign_input.validation_samples_by_symbol[spec.symbol]
    numpy = _numpy()
    development_matrix = _sequence_matrix_from_samples(development, standardizer, numpy)
    validation_matrix = _sequence_matrix_from_samples(validation, standardizer, numpy)
    labels = numpy.asarray([sample.label for sample in development], dtype=numpy.float32)
    if labels.shape != (len(development),) or not numpy.isfinite(labels).all():
        raise ValueError("NAS D1 candle-state CUDA labels are invalid")
    device = torch.device("cuda")
    previous_threads = torch.get_num_threads()
    was_deterministic = torch.are_deterministic_algorithms_enabled()
    previous_benchmark = torch.backends.cudnn.benchmark
    previous_cudnn_deterministic = torch.backends.cudnn.deterministic
    try:
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)
        torch.manual_seed(spec.seed)
        torch.cuda.manual_seed_all(spec.seed)
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True
        torch.cuda.reset_peak_memory_stats(device)
        development_tensor = torch.tensor(development_matrix, dtype=torch.float32, device=device)
        labels_tensor = torch.tensor(labels, dtype=torch.float32, device=device).unsqueeze(1)
        validation_tensor = torch.tensor(validation_matrix, dtype=torch.float32, device=device)
        model = build_torch_sequence_model(
            torch=torch,
            architecture_id=spec.architecture_id,
            feature_count=KIS_NAS_D1_CANDLE_STATE_FEATURE_COUNT,
            hidden_size=spec.hidden_size,
            attention_heads=spec.attention_heads,
            tcn_kernel_size=spec.tcn_kernel_size,
        ).to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=spec.learning_rate)
        loss_fn = torch.nn.BCEWithLogitsLoss()
        model.train()
        initial_loss = float(loss_fn(model(development_tensor), labels_tensor).detach().item())
        if not math.isfinite(initial_loss):
            raise ValueError("NAS D1 candle-state CUDA initial loss is nonfinite")
        started = time.monotonic()
        last_loss: float | None = None
        for _ in range(spec.epochs):
            for start in range(0, len(development_tensor), spec.batch_size):
                stop = min(start + spec.batch_size, len(development_tensor))
                optimizer.zero_grad(set_to_none=True)
                loss = loss_fn(model(development_tensor[start:stop]), labels_tensor[start:stop])
                loss_value = float(loss.detach().item())
                if not math.isfinite(loss_value):
                    raise ValueError("NAS D1 candle-state CUDA loss is nonfinite")
                loss.backward()
                optimizer.step()
                last_loss = loss_value
                if time.monotonic() - started > spec.max_seconds:
                    raise TimeoutError("NAS D1 candle-state CUDA candidate exceeded its cap")
        if last_loss is None:
            raise ValueError("NAS D1 candle-state CUDA candidate had no batches")
        torch.cuda.synchronize(device)
        model.eval()
        with torch.no_grad():
            validation_logits = model(validation_tensor)
            validation_outputs = torch.sigmoid(validation_logits)
        if (
            tuple(validation_logits.shape) != (len(validation), 1)
            or not bool(torch.isfinite(validation_logits).all().item())
            or not bool(torch.isfinite(validation_outputs).all().item())
            or not bool(((validation_outputs >= 0.0) & (validation_outputs <= 1.0)).all().item())
        ):
            raise ValueError("NAS D1 candle-state target-free CUDA forward is invalid")
        final_loss = float(loss_fn(model(development_tensor), labels_tensor).detach().item())
        if not math.isfinite(final_loss):
            raise ValueError("NAS D1 candle-state CUDA final loss is nonfinite")
        checkpoint_path = checkpoint_dir / f"{spec.architecture_id}-{spec.symbol.lower()}.pt"
        checkpoint_payload = {
            "schema_version": SCHEMA_VERSION,
            "kind": "kis_nas_d1_candle_state_breadth_checkpoint",
            "campaign_contract_hash": breadth_input.campaign_input.contract.contract_hash,
            "development_input_hash": standardizer.development_input_hash,
            "standardizer_hash": standardizer.standardizer_hash,
            "architecture": spec.safe_payload(),
            "state_dict": model.state_dict(),
        }
        with checkpoint_path.open("xb") as handle:
            torch.save(checkpoint_payload, handle)
        _verify_torch_checkpoint(
            checkpoint_path,
            breadth_input=breadth_input,
            spec=spec,
            torch=torch,
        )
        return KisNasD1CandleStateGpuCandidateReceipt(
            spec=spec,
            development_sample_count=len(development),
            validation_forward=KisNasD1CandleStateTargetFreeForward(
                symbol=spec.symbol,
                sample_count=len(validation),
                output_shape=(len(validation), 1),
                all_finite=True,
                output_bounds_valid=True,
            ),
            checkpoint_path=checkpoint_path,
            checkpoint_sha256=_sha256_file(checkpoint_path),
            backend="torch_cuda",
            device=str(torch.cuda.get_device_name(device)),
            torch_version=str(torch.__version__),
            cuda_version=None if torch.version.cuda is None else str(torch.version.cuda),
            initial_loss=initial_loss,
            final_loss=final_loss,
            cuda_peak_memory_bytes=int(torch.cuda.max_memory_allocated(device)),
            safe_weights_only_reload=True,
        )
    finally:
        torch.set_num_threads(previous_threads)
        torch.use_deterministic_algorithms(was_deterministic)
        torch.backends.cudnn.benchmark = previous_benchmark
        torch.backends.cudnn.deterministic = previous_cudnn_deterministic


def _verify_torch_checkpoint(
    checkpoint_path: Path,
    *,
    breadth_input: KisNasD1CandleStateBreadthInput,
    spec: KisNasD1CandleStateArchitectureSpec,
    torch: object,
) -> None:
    try:
        payload = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    except Exception as exc:  # pragma: no cover - real Torch reload faults only.
        raise ValueError("NAS D1 candle-state CUDA checkpoint cannot be safely reloaded") from exc
    standardizer = breadth_input.standardizers_by_symbol[spec.symbol]
    if (
        not isinstance(payload, dict)
        or payload.get("kind") != "kis_nas_d1_candle_state_breadth_checkpoint"
        or payload.get("campaign_contract_hash")
        != breadth_input.campaign_input.contract.contract_hash
        or payload.get("development_input_hash") != standardizer.development_input_hash
        or payload.get("standardizer_hash") != standardizer.standardizer_hash
        or payload.get("architecture") != spec.safe_payload()
    ):
        raise ValueError("NAS D1 candle-state CUDA checkpoint contract is invalid")
    model = build_torch_sequence_model(
        torch=torch,
        architecture_id=spec.architecture_id,
        feature_count=KIS_NAS_D1_CANDLE_STATE_FEATURE_COUNT,
        hidden_size=spec.hidden_size,
        attention_heads=spec.attention_heads,
        tcn_kernel_size=spec.tcn_kernel_size,
    )
    try:
        model.load_state_dict(payload["state_dict"], strict=True)
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        raise ValueError("NAS D1 candle-state CUDA checkpoint state is invalid") from exc


def _require_bound_cuda_candidate_receipt(
    candidate: KisNasD1CandleStateGpuCandidateReceipt,
    *,
    breadth_input: KisNasD1CandleStateBreadthInput,
    spec: KisNasD1CandleStateArchitectureSpec,
    checkpoint_dir: Path,
    repository: Path,
    require_torch_backend: bool,
) -> None:
    expected_checkpoint = (
        checkpoint_dir / f"{spec.architecture_id}-{spec.symbol.lower()}.pt"
    ).resolve()
    checkpoint_path = _require_external_file(candidate.checkpoint_path, repository)
    validation_count = len(breadth_input.campaign_input.validation_samples_by_symbol[spec.symbol])
    development_count = len(
        breadth_input.campaign_input.development_samples_by_symbol[spec.symbol]
    )
    if (
        candidate.spec != spec
        or checkpoint_path != expected_checkpoint
        or not checkpoint_path.is_relative_to(checkpoint_dir.resolve())
        or candidate.checkpoint_sha256 != _sha256_file(checkpoint_path)
        or candidate.development_sample_count != development_count
        or candidate.validation_forward.symbol != spec.symbol
        or candidate.validation_forward.sample_count != validation_count
        or candidate.validation_forward.output_shape != (validation_count, 1)
        or (require_torch_backend and candidate.backend != "torch_cuda")
    ):
        raise ValueError("NAS D1 candle-state CUDA candidate receipt is not bound to its run")


def _cpu_precommit_payload(breadth_input: KisNasD1CandleStateBreadthInput) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_nas_d1_candle_state_cpu_smoke_precommit",
        "campaign_contract_hash": breadth_input.campaign_input.contract.contract_hash,
        "campaign_precommit_hash": breadth_input.campaign_precommit_hash,
        "review_status": breadth_input.review_status,
        "package_id": KIS_NAS_D1_CANDLE_STATE_CPU_SMOKE_ID,
        "source": _source_payload(breadth_input),
        "specifications": [
            spec.safe_payload() for spec in KIS_NAS_D1_CANDLE_STATE_CPU_LOGISTIC_SPECS
        ],
        "validation": {"forward_only": True, "labels_materialized": False},
        "artifact_policy": {
            "checkpoints_written": False,
            "raw_rows_persisted": False,
            "feature_values_persisted": False,
            "prediction_values_persisted": False,
        },
        "reporting": _reporting_payload(),
    }


def _cpu_summary_payload(
    *,
    breadth_input: KisNasD1CandleStateBreadthInput,
    precommit_hash: str,
    candidates: Sequence[KisNasD1CandleStateCpuCandidateReceipt],
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_nas_d1_candle_state_cpu_smoke",
        "status": "completed",
        "campaign_contract_hash": breadth_input.campaign_input.contract.contract_hash,
        "campaign_precommit_hash": breadth_input.campaign_precommit_hash,
        "precommit_hash": precommit_hash,
        "source": _source_payload(breadth_input),
        "candidates": [candidate.safe_payload() for candidate in candidates],
        "validation": {"forward_only": True, "labels_materialized": False},
        "artifact_policy": {
            "checkpoints_written": False,
            "raw_rows_persisted": False,
            "feature_values_persisted": False,
            "prediction_values_persisted": False,
        },
        "reporting": _reporting_payload(),
    }


def _cpu_summary_attestation_payload(
    *,
    breadth_input: KisNasD1CandleStateBreadthInput,
    precommit_hash: str,
    summary_hash: str,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_nas_d1_candle_state_cpu_smoke_summary_attestation",
        "summary_filename": "summary.json",
        "summary_hash": summary_hash,
        "precommit_hash": precommit_hash,
        "campaign_contract_hash": breadth_input.campaign_input.contract.contract_hash,
        "campaign_precommit_hash": breadth_input.campaign_precommit_hash,
        "source": _source_payload(breadth_input),
        "artifact_policy": {
            "raw_rows_persisted": False,
            "feature_values_persisted": False,
            "prediction_values_persisted": False,
        },
    }


def _cuda_precommit_payload(
    breadth_input: KisNasD1CandleStateBreadthInput,
    cpu_smoke_summary_hash: str,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_nas_d1_candle_state_cuda_breadth_precommit",
        "campaign_contract_hash": breadth_input.campaign_input.contract.contract_hash,
        "campaign_precommit_hash": breadth_input.campaign_precommit_hash,
        "cpu_smoke_summary_hash": cpu_smoke_summary_hash,
        "package_id": KIS_NAS_D1_CANDLE_STATE_GPU_BREADTH_ID,
        "source": _source_payload(breadth_input),
        "specifications": [
            spec.safe_payload() for spec in KIS_NAS_D1_CANDLE_STATE_CUDA_ARCHITECTURE_SPECS
        ],
        "validation": {"forward_only": True, "labels_materialized": False},
        "compute_cap": {
            "max_seconds_per_candidate": KIS_NAS_D1_CANDLE_STATE_CUDA_MAX_SECONDS_PER_CANDIDATE,
            "candidate_count": len(KIS_NAS_D1_CANDLE_STATE_CUDA_ARCHITECTURE_SPECS),
        },
        "artifact_policy": {
            "checkpoints_written": True,
            "safe_weights_only_reload_required": True,
            "raw_rows_persisted": False,
            "feature_values_persisted": False,
            "prediction_values_persisted": False,
        },
        "reporting": _reporting_payload(),
    }


def _cuda_summary_payload(
    *,
    breadth_input: KisNasD1CandleStateBreadthInput,
    cpu_smoke_summary_hash: str,
    precommit_hash: str,
    status: str,
    reason: str,
    candidates: Sequence[KisNasD1CandleStateGpuCandidateReceipt],
    failure: KisNasD1CandleStateCudaFailure | None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_nas_d1_candle_state_cuda_breadth",
        "status": status,
        "reason": reason,
        "campaign_contract_hash": breadth_input.campaign_input.contract.contract_hash,
        "campaign_precommit_hash": breadth_input.campaign_precommit_hash,
        "cpu_smoke_summary_hash": cpu_smoke_summary_hash,
        "precommit_hash": precommit_hash,
        "source": _source_payload(breadth_input),
        "candidates": [candidate.safe_payload() for candidate in candidates],
        "validation": {"forward_only": True, "labels_materialized": False},
        "artifact_policy": {
            "checkpoints_written": bool(candidates),
            "safe_weights_only_reload_required": True,
            "raw_rows_persisted": False,
            "feature_values_persisted": False,
            "prediction_values_persisted": False,
        },
        "reporting": _reporting_payload(),
    }
    if failure is not None:
        payload["failure"] = failure.safe_payload()
    return payload


def _write_cuda_summary(
    *,
    breadth_input: KisNasD1CandleStateBreadthInput,
    run_label: str,
    output_dir: Path,
    cpu_smoke_summary_hash: str,
    precommit_path: Path,
    precommit_hash: str,
    status: Literal["completed", "cuda_unavailable", "candidate_failed"],
    reason: str,
    candidates: tuple[KisNasD1CandleStateGpuCandidateReceipt, ...],
    failure: KisNasD1CandleStateCudaFailure | None,
) -> KisNasD1CandleStateCudaBreadthRun:
    summary_path = output_dir / "summary.json"
    payload = _cuda_summary_payload(
        breadth_input=breadth_input,
        cpu_smoke_summary_hash=cpu_smoke_summary_hash,
        precommit_hash=precommit_hash,
        status=status,
        reason=reason,
        candidates=candidates,
        failure=failure,
    )
    _assert_source_safe(payload)
    summary_hash = _write_json_new(summary_path, payload)
    return KisNasD1CandleStateCudaBreadthRun(
        breadth_input=breadth_input,
        run_label=run_label,
        cpu_smoke_summary_hash=cpu_smoke_summary_hash,
        precommit_path=precommit_path,
        precommit_hash=precommit_hash,
        summary_path=summary_path,
        summary_hash=summary_hash,
        status=status,
        reason=reason,
        candidates=candidates,
        failure=failure,
    )


def _source_payload(breadth_input: KisNasD1CandleStateBreadthInput) -> dict[str, object]:
    return {
        "campaign_contract_hash": breadth_input.campaign_input.contract.contract_hash,
        "campaign_precommit_hash": breadth_input.campaign_precommit_hash,
        "development_input_hash": breadth_input.campaign_input.development_input_hash,
        "validation_input_hash": breadth_input.campaign_input.validation_input_hash,
        "symbols": list(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS),
        "source_limitations": list(breadth_input.campaign_input.source_limitations),
        "standardizer_hashes": [
            breadth_input.standardizers_by_symbol[symbol].standardizer_hash
            for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
        ],
    }


def _reporting_payload() -> dict[str, object]:
    return {
        "selection_allowed": False,
        "ensemble_allowed": False,
        "promotion_allowed": False,
        "replay_allowed": False,
        "pnl_materialized": False,
        "paper_trading_eligible": False,
    }


def _validate_cpu_smoke_summary(
    path: Path,
    breadth_input: KisNasD1CandleStateBreadthInput,
    *,
    repository: Path,
) -> str:
    summary_path = _require_external_file(path, repository)
    precommit_path = _require_external_file(summary_path.with_name("precommit.json"), repository)
    summary_attestation_path = _require_external_file(
        summary_path.with_name(_CPU_SUMMARY_ATTESTATION_FILENAME),
        repository,
    )
    try:
        summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
        precommit_payload = json.loads(precommit_path.read_text(encoding="utf-8"))
        summary_attestation_payload = json.loads(
            summary_attestation_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("NAS D1 candle-state CPU smoke receipt is unreadable") from exc
    expected_precommit = _cpu_precommit_payload(breadth_input)
    _assert_source_safe(summary_payload)
    _assert_source_safe(precommit_payload)
    _assert_source_safe(summary_attestation_payload)
    precommit_hash = _sha256_file(precommit_path)
    summary_hash = _sha256_file(summary_path)
    expected_summary_attestation = _cpu_summary_attestation_payload(
        breadth_input=breadth_input,
        precommit_hash=precommit_hash,
        summary_hash=summary_hash,
    )
    candidates = summary_payload.get("candidates", []) if isinstance(summary_payload, dict) else []
    if (
        precommit_payload != expected_precommit
        or summary_attestation_payload != expected_summary_attestation
        or not isinstance(summary_payload, dict)
        or summary_payload.get("kind") != "kis_nas_d1_candle_state_cpu_smoke"
        or summary_payload.get("status") != "completed"
        or summary_payload.get("campaign_contract_hash")
        != breadth_input.campaign_input.contract.contract_hash
        or summary_payload.get("campaign_precommit_hash") != breadth_input.campaign_precommit_hash
        or summary_payload.get("precommit_hash") != precommit_hash
        or summary_payload.get("source") != _source_payload(breadth_input)
        or summary_payload.get("artifact_policy")
        != {
            "checkpoints_written": False,
            "raw_rows_persisted": False,
            "feature_values_persisted": False,
            "prediction_values_persisted": False,
        }
        or summary_payload.get("reporting") != _reporting_payload()
        or summary_payload.get("validation") != {"forward_only": True, "labels_materialized": False}
        or not isinstance(candidates, list)
        or len(candidates) != len(KIS_NAS_D1_CANDLE_STATE_CPU_LOGISTIC_SPECS)
        or any(
            not _is_valid_cpu_candidate_payload(candidate, breadth_input, spec)
            for candidate, spec in zip(
                candidates,
                KIS_NAS_D1_CANDLE_STATE_CPU_LOGISTIC_SPECS,
                strict=True,
            )
        )
    ):
        raise ValueError("NAS D1 candle-state CPU smoke summary is invalid")
    return summary_hash


def _is_valid_cpu_candidate_payload(
    value: object,
    breadth_input: KisNasD1CandleStateBreadthInput,
    spec: KisNasD1CandleStateL2LogisticSpec,
) -> bool:
    if not isinstance(value, Mapping) or set(value) != {
        "symbol",
        "model_id",
        "model_parameter_hash",
        "standardizer_hash",
        "development_sample_count",
        "steps",
        "seed",
        "initial_loss",
        "final_loss",
        "validation_forward",
    }:
        return False
    validation = value.get("validation_forward")
    expected_validation_count = len(
        breadth_input.campaign_input.validation_samples_by_symbol[spec.symbol]
    )
    expected_development_count = len(
        breadth_input.campaign_input.development_samples_by_symbol[spec.symbol]
    )
    expected_standardizer_hash = breadth_input.standardizers_by_symbol[
        spec.symbol
    ].standardizer_hash
    return (
        value.get("symbol") == spec.symbol
        and value.get("model_id") == "l2_logistic"
        and _is_sha256(value.get("model_parameter_hash"))
        and value.get("standardizer_hash") == expected_standardizer_hash
        and value.get("development_sample_count") == expected_development_count
        and value.get("steps") == spec.steps
        and value.get("seed") == spec.seed
        and _is_finite_loss_text(value.get("initial_loss"))
        and _is_finite_loss_text(value.get("final_loss"))
        and isinstance(validation, Mapping)
        and set(validation)
        == {
            "symbol",
            "sample_count",
            "output_shape",
            "all_finite",
            "output_bounds_valid",
            "labels_materialized",
        }
        and validation.get("symbol") == spec.symbol
        and validation.get("sample_count") == expected_validation_count
        and validation.get("output_shape") == [expected_validation_count, 1]
        and validation.get("all_finite") is True
        and validation.get("output_bounds_valid") is True
        and validation.get("labels_materialized") is False
    )


def _is_finite_loss_text(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return math.isfinite(float(value))
    except ValueError:
        return False


def _prepare_output_dir(
    *,
    artifact_root: Path | str,
    repo_root: Path | str | None,
    mode: Literal["cpu-smoke", "cuda-breadth"],
    run_label: str,
) -> Path:
    _validate_run_label(run_label)
    repository = _repository_root(repo_root)
    requested_root = Path(artifact_root).absolute()
    _reject_link_or_junction_components(requested_root)
    root = requested_root.resolve()
    _reject_repository_artifact_root(root, repository)
    _reject_repository_artifact_root(root, _MODULE_REPOSITORY_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    _reject_link_or_junction_components(root)
    root = root.resolve()
    _reject_repository_artifact_root(root, repository)
    _reject_repository_artifact_root(root, _MODULE_REPOSITORY_ROOT)
    output_dir = root / KIS_NAS_D1_CANDLE_STATE_BREADTH_ID / mode / run_label
    _reject_link_or_junction_components(output_dir)
    _reject_repository_artifact_root(output_dir.resolve(), repository)
    _reject_repository_artifact_root(output_dir.resolve(), _MODULE_REPOSITORY_ROOT)
    if output_dir.exists():
        raise FileExistsError("NAS D1 candle-state artifact run label already exists")
    output_dir.mkdir(parents=True, exist_ok=False)
    _reject_link_or_junction_components(output_dir)
    _reject_repository_artifact_root(output_dir.resolve(), repository)
    _reject_repository_artifact_root(output_dir.resolve(), _MODULE_REPOSITORY_ROOT)
    return output_dir


def _repository_root(repo_root: Path | str | None) -> Path:
    return Path(repo_root or Path.cwd()).resolve()


def _require_external_file(path: Path | str, repository: Path) -> Path:
    candidate = Path(path)
    _reject_link_or_junction_components(candidate)
    if not candidate.is_file():
        raise ValueError("NAS D1 candle-state external receipt is invalid")
    resolved = candidate.resolve()
    _reject_repository_artifact_root(resolved, repository)
    _reject_repository_artifact_root(resolved, _MODULE_REPOSITORY_ROOT)
    return resolved


def _reject_repository_artifact_root(path: Path, repository: Path) -> None:
    docker_artifact_root = _DOCKER_ARTIFACT_ROOT.resolve()
    if (
        repository == _DOCKER_REPOSITORY_ROOT.resolve()
        and _DOCKER_ARTIFACT_ROOT.is_mount()
        and path.is_relative_to(docker_artifact_root)
    ):
        return
    if repository == _DOCKER_REPOSITORY_ROOT.resolve():
        raise ValueError("NAS D1 candle-state Docker artifacts must use /app/model_artifacts")
    if not path.is_relative_to(repository):
        return
    raise ValueError("NAS D1 candle-state artifacts must stay outside the Git workspace")


def _reject_link_or_junction_components(path: Path) -> None:
    candidate = path.absolute()
    current = Path(candidate.anchor)
    for part in candidate.parts:
        if part == candidate.anchor:
            continue
        current /= part
        if _is_link_or_junction(current):
            raise ValueError("NAS D1 candle-state artifact path cannot contain a link")


def _is_link_or_junction(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or (callable(is_junction) and is_junction())


def _write_json_new(path: Path, payload: Mapping[str, object]) -> str:
    _reject_link_or_junction_components(path.parent)
    if _is_link_or_junction(path):
        raise ValueError("NAS D1 candle-state receipt path is invalid")
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return _sha256_file(path)


def _remove_incomplete_checkpoint(
    checkpoint_dir: Path,
    spec: KisNasD1CandleStateArchitectureSpec,
) -> None:
    path = checkpoint_dir / f"{spec.architecture_id}-{spec.symbol.lower()}.pt"
    if path.exists():
        path.unlink()


def _cuda_failure_category(error: Exception) -> Literal["timeout", "memory", "invalid", "runtime"]:
    if isinstance(error, TimeoutError):
        return "timeout"
    if isinstance(error, ValueError):
        return "invalid"
    if "out of memory" in str(error).lower():
        return "memory"
    return "runtime"


def _logistic_loss(
    features: object,
    labels: object,
    weights: object,
    intercept: float,
    numpy: object,
) -> float:
    logits = numpy.clip(features @ weights + intercept, -60.0, 60.0)
    probabilities = 1.0 / (1.0 + numpy.exp(-logits))
    loss = -numpy.mean(
        labels * numpy.log(numpy.clip(probabilities, 1e-12, 1.0 - 1e-12))
        + (1.0 - labels) * numpy.log(numpy.clip(1.0 - probabilities, 1e-12, 1.0))
    )
    result = float(loss)
    if not math.isfinite(result):
        raise ValueError("NAS D1 candle-state CPU loss is nonfinite")
    return result


def _symbol_development_input_hash(
    symbol: str,
    samples: Sequence[KisNasD1CandleStateDevelopmentSample],
) -> str:
    return _sha256_payload(
        {
            "symbol": symbol,
            "samples": [
                {
                    "decision_start": sample.decision_start.isoformat(),
                    "feature_hash": _feature_hash(sample.feature_sequence),
                    "label": sample.label,
                }
                for sample in samples
            ],
        }
    )


def _feature_hash(sequence: Sequence[Sequence[float]]) -> str:
    return _sha256_payload(
        {"features": [[format(float(value), ".17g") for value in row] for row in sequence]}
    )


def _assert_source_safe(value: object) -> None:
    forbidden = {
        "account",
        "account_number",
        "bar",
        "bars",
        "broker",
        "close",
        "credential",
        "credentials",
        "entry",
        "event",
        "event_rows",
        "exit",
        "feature_rows",
        "feature_sequence",
        "high",
        "label",
        "labels",
        "low",
        "open",
        "order",
        "orders",
        "pnl",
        "prediction",
        "predictions",
        "price",
        "prices",
        "probability",
        "probabilities",
        "raw_bars",
        "secret",
        "target",
        "targets",
        "volume",
        "weights",
    }
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if str(key).lower() in forbidden:
                raise ValueError("NAS D1 candle-state receipt contains a source value field")
            _assert_source_safe(nested)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for nested in value:
            _assert_source_safe(nested)


def _validate_run_label(run_label: str) -> None:
    if not isinstance(run_label, str) or _RUN_LABEL.fullmatch(run_label) is None:
        raise ValueError("NAS D1 candle-state run label is invalid")


def _resolve_symbol(symbol: str) -> str:
    if not isinstance(symbol, str):
        raise ValueError("NAS D1 candle-state symbol is invalid")
    resolved = symbol.strip().upper()
    if resolved not in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        raise ValueError("NAS D1 candle-state symbol is unsupported")
    return resolved


def _numpy() -> object:
    try:
        import numpy
    except ImportError as exc:  # pragma: no cover - project runtime owns NumPy.
        raise RuntimeError("NAS D1 candle-state research requires NumPy") from exc
    return numpy


def _torch_or_none() -> object | None:
    try:
        import torch
    except ImportError:
        return None
    return torch


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        return False
    try:
        int(value.removeprefix("sha256:"), 16)
    except ValueError:
        return False
    return True


def _sha256_payload(payload: Mapping[str, object]) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()
