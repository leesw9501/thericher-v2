"""Offline CPU and CUDA plumbing for the frozen NAS volatility/trend campaign.

This module deliberately trains only against development labels and runs the
validation partition as a target-free forward pass.  It has no provider,
credential, broker, replay, PnL, ranking, or selection surface.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.data.kis_paper_daily_history_panel import KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
from thericher_v2.research.kis_nas_d1_volatility_trend_campaign import (
    KIS_NAS_D1_VOLATILITY_TREND_CPU_SMOKE_ID,
    KIS_NAS_D1_VOLATILITY_TREND_FEATURE_COUNT,
    KIS_NAS_D1_VOLATILITY_TREND_GPU_BREADTH_ID,
    KisNasD1VolatilityTrendCampaignInput,
    KisNasD1VolatilityTrendDevelopmentSample,
    KisNasD1VolatilityTrendValidationSample,
    calculate_kis_nas_d1_volatility_trend_campaign_precommit_hash,
    require_attested_kis_nas_d1_volatility_trend_campaign_input,
)
from thericher_v2.research.sequence_architecture_models import (
    SequenceArchitectureId,
    build_torch_sequence_model,
)

KIS_NAS_D1_VOLATILITY_TREND_BREADTH_ID = "kis-nas-d1-volatility-trend-breadth-v1"
KIS_NAS_D1_VOLATILITY_TREND_BREADTH_ARTIFACT_ROOT = Path(
    "D:/thericher-v2/model-artifacts/research"
)
KIS_NAS_D1_VOLATILITY_TREND_CPU_LOGISTIC_STEPS = 160
KIS_NAS_D1_VOLATILITY_TREND_CPU_LOGISTIC_LEARNING_RATE = 0.08
KIS_NAS_D1_VOLATILITY_TREND_CPU_LOGISTIC_L2 = 0.0001
KIS_NAS_D1_VOLATILITY_TREND_STANDARDIZER_SCALE_FLOOR = 1e-12
KIS_NAS_D1_VOLATILITY_TREND_CUDA_EPOCHS = 6
KIS_NAS_D1_VOLATILITY_TREND_CUDA_BATCH_SIZE = 128
KIS_NAS_D1_VOLATILITY_TREND_CUDA_MAX_SECONDS_PER_CANDIDATE = 120
KIS_NAS_D1_VOLATILITY_TREND_CUDA_HIDDEN_SIZE = 16
KIS_NAS_D1_VOLATILITY_TREND_CUDA_ATTENTION_HEADS = 4
KIS_NAS_D1_VOLATILITY_TREND_CUDA_TCN_KERNEL_SIZE = 3
KIS_NAS_D1_VOLATILITY_TREND_CUDA_LEARNING_RATE = 0.001

_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)
_MODULE_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_DOCKER_REPOSITORY_ROOT = Path("/app")
_DOCKER_ARTIFACT_ROOT = _DOCKER_REPOSITORY_ROOT / "model_artifacts"


@dataclass(frozen=True, slots=True)
class KisNasD1VolatilityTrendStandardizer:
    """A development-only per-channel standardizer for a single symbol."""

    symbol: str
    development_input_hash: str
    means: tuple[float, ...]
    scales: tuple[float, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "means", tuple(float(value) for value in self.means))
        object.__setattr__(self, "scales", tuple(float(value) for value in self.scales))
        if (
            self.symbol not in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            or not _is_sha256(self.development_input_hash)
            or len(self.means) != KIS_NAS_D1_VOLATILITY_TREND_FEATURE_COUNT
            or len(self.scales) != KIS_NAS_D1_VOLATILITY_TREND_FEATURE_COUNT
            or any(not math.isfinite(value) for value in self.means)
            or any(not math.isfinite(value) or value <= 0.0 for value in self.scales)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("NAS D1 volatility trend standardizer is invalid")

    @property
    def standardizer_hash(self) -> str:
        return _sha256_payload(
            {
                "symbol": self.symbol,
                "development_input_hash": self.development_input_hash,
                "means": [format(value, ".17g") for value in self.means],
                "scales": [format(value, ".17g") for value in self.scales],
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
            or any(len(row) != KIS_NAS_D1_VOLATILITY_TREND_FEATURE_COUNT for row in result)
            or any(not math.isfinite(value) for row in result for value in row)
        ):
            raise ValueError("NAS D1 volatility trend standardized sequence is invalid")
        return result


@dataclass(frozen=True, slots=True)
class KisNasD1VolatilityTrendL2LogisticSpec:
    """Fixed deterministic CPU fitting terms for one independent symbol."""

    symbol: str
    seed: int
    steps: int = KIS_NAS_D1_VOLATILITY_TREND_CPU_LOGISTIC_STEPS
    learning_rate: float = KIS_NAS_D1_VOLATILITY_TREND_CPU_LOGISTIC_LEARNING_RATE
    l2_penalty: float = KIS_NAS_D1_VOLATILITY_TREND_CPU_LOGISTIC_L2
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.symbol not in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            or self.seed < 0
            or self.steps != KIS_NAS_D1_VOLATILITY_TREND_CPU_LOGISTIC_STEPS
            or self.learning_rate != KIS_NAS_D1_VOLATILITY_TREND_CPU_LOGISTIC_LEARNING_RATE
            or self.l2_penalty != KIS_NAS_D1_VOLATILITY_TREND_CPU_LOGISTIC_L2
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("NAS D1 volatility trend CPU spec is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "seed": self.seed,
            "steps": self.steps,
            "learning_rate": self.learning_rate,
            "l2_penalty": self.l2_penalty,
        }


KIS_NAS_D1_VOLATILITY_TREND_CPU_LOGISTIC_SPECS = tuple(
    KisNasD1VolatilityTrendL2LogisticSpec(symbol=symbol, seed=2026072815 + index)
    for index, symbol in enumerate(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS)
)


@dataclass(frozen=True, slots=True)
class KisNasD1VolatilityTrendL2LogisticModel:
    """In-memory model parameters that never enter an artifact receipt."""

    spec: KisNasD1VolatilityTrendL2LogisticSpec
    development_input_hash: str
    standardizer_hash: str
    weights: tuple[float, ...]
    intercept: float
    initial_loss: float
    final_loss: float
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "weights", tuple(float(value) for value in self.weights))
        expected_weight_count = KIS_NAS_D1_VOLATILITY_TREND_FEATURE_COUNT * 20
        if (
            not _is_sha256(self.development_input_hash)
            or not _is_sha256(self.standardizer_hash)
            or len(self.weights) != expected_weight_count
            or any(not math.isfinite(value) for value in self.weights)
            or any(
                not math.isfinite(value)
                for value in (self.intercept, self.initial_loss, self.final_loss)
            )
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("NAS D1 volatility trend CPU model is invalid")

    @property
    def parameter_hash(self) -> str:
        return _sha256_payload(
            {
                "symbol": self.spec.symbol,
                "development_input_hash": self.development_input_hash,
                "standardizer_hash": self.standardizer_hash,
                "weights": [format(value, ".17g") for value in self.weights],
                "intercept": format(self.intercept, ".17g"),
            }
        )


@dataclass(frozen=True, slots=True)
class KisNasD1VolatilityTrendTargetFreeForward:
    """Shape-only evidence that validation labels were not materialized."""

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
            raise ValueError("NAS D1 volatility trend target-free forward is invalid")

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
class KisNasD1VolatilityTrendArchitectureSpec:
    """One bounded GPU candidate."""

    architecture_id: SequenceArchitectureId
    symbol: str
    seed: int
    hidden_size: int = KIS_NAS_D1_VOLATILITY_TREND_CUDA_HIDDEN_SIZE
    attention_heads: int = KIS_NAS_D1_VOLATILITY_TREND_CUDA_ATTENTION_HEADS
    tcn_kernel_size: int = KIS_NAS_D1_VOLATILITY_TREND_CUDA_TCN_KERNEL_SIZE
    learning_rate: float = KIS_NAS_D1_VOLATILITY_TREND_CUDA_LEARNING_RATE
    epochs: int = KIS_NAS_D1_VOLATILITY_TREND_CUDA_EPOCHS
    batch_size: int = KIS_NAS_D1_VOLATILITY_TREND_CUDA_BATCH_SIZE
    max_seconds: int = KIS_NAS_D1_VOLATILITY_TREND_CUDA_MAX_SECONDS_PER_CANDIDATE
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.architecture_id not in {"lstm", "causal_tcn", "compact_attention"}
            or self.symbol not in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            or self.seed < 0
            or self.hidden_size != KIS_NAS_D1_VOLATILITY_TREND_CUDA_HIDDEN_SIZE
            or self.attention_heads != KIS_NAS_D1_VOLATILITY_TREND_CUDA_ATTENTION_HEADS
            or self.tcn_kernel_size != KIS_NAS_D1_VOLATILITY_TREND_CUDA_TCN_KERNEL_SIZE
            or self.learning_rate != KIS_NAS_D1_VOLATILITY_TREND_CUDA_LEARNING_RATE
            or self.epochs != KIS_NAS_D1_VOLATILITY_TREND_CUDA_EPOCHS
            or self.batch_size != KIS_NAS_D1_VOLATILITY_TREND_CUDA_BATCH_SIZE
            or self.max_seconds != KIS_NAS_D1_VOLATILITY_TREND_CUDA_MAX_SECONDS_PER_CANDIDATE
            or self.hidden_size % self.attention_heads != 0
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("NAS D1 volatility trend CUDA spec is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "architecture_id": self.architecture_id,
            "symbol": self.symbol,
            "seed": self.seed,
            "hidden_size": self.hidden_size,
            "attention_heads": self.attention_heads,
            "tcn_kernel_size": self.tcn_kernel_size,
            "learning_rate": self.learning_rate,
            "epochs": self.epochs,
            "batch_size": self.batch_size,
            "max_seconds": self.max_seconds,
        }


KIS_NAS_D1_VOLATILITY_TREND_CUDA_ARCHITECTURE_SPECS = tuple(
    KisNasD1VolatilityTrendArchitectureSpec(
        architecture_id=architecture_id,
        symbol=symbol,
        seed=2026072905 + architecture_index * 10 + symbol_index,
    )
    for architecture_index, architecture_id in enumerate(
        ("lstm", "causal_tcn", "compact_attention")
    )
    for symbol_index, symbol in enumerate(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS)
)


@dataclass(frozen=True, slots=True, init=False)
class KisNasD1VolatilityTrendBreadthInput:
    """Attested campaign and development-only scaling boundary."""

    campaign_input: KisNasD1VolatilityTrendCampaignInput
    campaign_precommit_hash: str
    review_status: str
    standardizers_by_symbol: Mapping[str, KisNasD1VolatilityTrendStandardizer]
    integrity_hash: str
    schema_version: int
    _attestation: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("use the attested NAS D1 volatility trend breadth input builder")

    def standardizer(self, symbol: str) -> KisNasD1VolatilityTrendStandardizer:
        _require_attested_breadth_input(self)
        resolved = _resolve_symbol(symbol)
        return self.standardizers_by_symbol[resolved]


@dataclass(frozen=True, slots=True)
class KisNasD1VolatilityTrendCpuCandidateReceipt:
    model: KisNasD1VolatilityTrendL2LogisticModel
    validation_forward: KisNasD1VolatilityTrendTargetFreeForward
    development_sample_count: int

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
class KisNasD1VolatilityTrendCpuSmokeRun:
    breadth_input: KisNasD1VolatilityTrendBreadthInput
    run_label: str
    precommit_path: Path
    precommit_hash: str
    summary_path: Path
    summary_hash: str
    candidates: tuple[KisNasD1VolatilityTrendCpuCandidateReceipt, ...]


@dataclass(frozen=True, slots=True)
class KisNasD1VolatilityTrendGpuCandidateReceipt:
    spec: KisNasD1VolatilityTrendArchitectureSpec
    development_sample_count: int
    validation_forward: KisNasD1VolatilityTrendTargetFreeForward
    checkpoint_path: Path
    checkpoint_sha256: str
    backend: Literal["torch_cuda", "unit"]
    device: str
    torch_version: str
    cuda_version: str | None
    initial_loss: float
    final_loss: float
    cuda_peak_memory_bytes: int
    safe_weights_only_reload: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "checkpoint_path", Path(self.checkpoint_path).resolve())
        if (
            self.development_sample_count <= 0
            or self.validation_forward.symbol != self.spec.symbol
            or not self.checkpoint_path.is_file()
            or not _is_sha256(self.checkpoint_sha256)
            or _sha256_file(self.checkpoint_path) != self.checkpoint_sha256
            or not self.device
            or not self.torch_version
            or any(not math.isfinite(value) for value in (self.initial_loss, self.final_loss))
            or self.cuda_peak_memory_bytes < 0
            or not self.safe_weights_only_reload
        ):
            raise ValueError("NAS D1 volatility trend CUDA candidate receipt is invalid")

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
class KisNasD1VolatilityTrendCudaFailure:
    spec: KisNasD1VolatilityTrendArchitectureSpec
    category: Literal["timeout", "memory", "invalid", "runtime"]

    def safe_payload(self) -> dict[str, object]:
        return {"architecture": self.spec.safe_payload(), "category": self.category}


@dataclass(frozen=True, slots=True)
class KisNasD1VolatilityTrendCudaBreadthRun:
    breadth_input: KisNasD1VolatilityTrendBreadthInput
    run_label: str
    cpu_smoke_summary_hash: str
    precommit_path: Path
    precommit_hash: str
    summary_path: Path
    summary_hash: str
    status: Literal["completed", "cuda_unavailable", "candidate_failed"]
    reason: str
    candidates: tuple[KisNasD1VolatilityTrendGpuCandidateReceipt, ...]
    failure: KisNasD1VolatilityTrendCudaFailure | None


CudaCandidateTrainer = Callable[
    [
        KisNasD1VolatilityTrendBreadthInput,
        KisNasD1VolatilityTrendArchitectureSpec,
        Path,
    ],
    KisNasD1VolatilityTrendGpuCandidateReceipt,
]


def build_kis_nas_d1_volatility_trend_breadth_input(
    campaign_input: KisNasD1VolatilityTrendCampaignInput,
    *,
    campaign_precommit_hash: str,
    review_status: str,
) -> KisNasD1VolatilityTrendBreadthInput:
    """Freeze per-symbol, per-channel development standardization."""

    require_attested_kis_nas_d1_volatility_trend_campaign_input(campaign_input)
    expected_precommit_hash = calculate_kis_nas_d1_volatility_trend_campaign_precommit_hash(
        campaign_input,
        review_status=review_status,
    )
    if campaign_precommit_hash != expected_precommit_hash:
        raise ValueError("NAS D1 volatility trend breadth requires its campaign precommit")
    standardizers = {
        symbol: _fit_development_standardizer(
            symbol=symbol,
            samples=campaign_input.development_samples(symbol),
            development_input_hash=_symbol_development_input_hash(
                symbol,
                campaign_input.development_samples(symbol),
            ),
        )
        for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
    }
    result = object.__new__(KisNasD1VolatilityTrendBreadthInput)
    object.__setattr__(result, "campaign_input", campaign_input)
    object.__setattr__(result, "campaign_precommit_hash", campaign_precommit_hash)
    object.__setattr__(result, "review_status", review_status)
    object.__setattr__(result, "standardizers_by_symbol", MappingProxyType(standardizers))
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
    object.__setattr__(result, "schema_version", SCHEMA_VERSION)
    object.__setattr__(result, "_attestation", _BREADTH_INPUT_ATTESTATION)
    _require_attested_breadth_input(result)
    return result


def fit_kis_nas_d1_volatility_trend_l2_logistic_smoke(
    breadth_input: KisNasD1VolatilityTrendBreadthInput,
    spec: KisNasD1VolatilityTrendL2LogisticSpec,
) -> KisNasD1VolatilityTrendL2LogisticModel:
    """Fit a deterministic development-only CPU smoke candidate."""

    _require_attested_breadth_input(breadth_input)
    standardizer = breadth_input.standardizer(spec.symbol)
    samples = breadth_input.campaign_input.development_samples(spec.symbol)
    numpy = _numpy()
    features = _flatten_matrix_from_samples(samples, standardizer, numpy)
    labels = numpy.asarray([sample.label for sample in samples], dtype=numpy.float64)
    if (
        features.shape
        != (
            len(samples),
            breadth_input.campaign_input.contract.features.sequence_length
            * KIS_NAS_D1_VOLATILITY_TREND_FEATURE_COUNT,
        )
        or labels.shape != (len(samples),)
        or not numpy.isfinite(features).all()
        or not numpy.isfinite(labels).all()
    ):
        raise ValueError("NAS D1 volatility trend CPU development matrix is invalid")
    generator = numpy.random.default_rng(spec.seed)
    weights = generator.normal(loc=0.0, scale=0.01, size=features.shape[1]).astype(numpy.float64)
    intercept = 0.0
    initial_loss = _logistic_loss(features, labels, weights, intercept, numpy)
    for _ in range(spec.steps):
        logits = numpy.clip(features @ weights + intercept, -60.0, 60.0)
        probabilities = 1.0 / (1.0 + numpy.exp(-logits))
        residuals = probabilities - labels
        gradient_weights = features.T @ residuals / len(samples) + spec.l2_penalty * weights
        gradient_intercept = float(residuals.mean())
        weights -= spec.learning_rate * gradient_weights
        intercept -= spec.learning_rate * gradient_intercept
        if not numpy.isfinite(weights).all() or not math.isfinite(intercept):
            raise ValueError("NAS D1 volatility trend CPU training diverged")
    return KisNasD1VolatilityTrendL2LogisticModel(
        spec=spec,
        development_input_hash=standardizer.development_input_hash,
        standardizer_hash=standardizer.standardizer_hash,
        weights=tuple(float(value) for value in weights),
        intercept=intercept,
        initial_loss=initial_loss,
        final_loss=_logistic_loss(features, labels, weights, intercept, numpy),
    )


def forward_kis_nas_d1_volatility_trend_l2_logistic_target_free_validation(
    breadth_input: KisNasD1VolatilityTrendBreadthInput,
    model: KisNasD1VolatilityTrendL2LogisticModel,
) -> KisNasD1VolatilityTrendTargetFreeForward:
    """Exercise only the validation tensor shape, never its targets."""

    _require_attested_breadth_input(breadth_input)
    standardizer = breadth_input.standardizer(model.spec.symbol)
    if (
        model.development_input_hash != standardizer.development_input_hash
        or model.standardizer_hash != standardizer.standardizer_hash
    ):
        raise ValueError("NAS D1 volatility trend model does not match its development input")
    samples = breadth_input.campaign_input.validation_samples(model.spec.symbol)
    numpy = _numpy()
    features = _flatten_matrix_from_samples(samples, standardizer, numpy)
    weights = numpy.asarray(model.weights, dtype=numpy.float64)
    logits = features @ weights + model.intercept
    outputs = 1.0 / (1.0 + numpy.exp(-numpy.clip(logits, -60.0, 60.0)))
    if (
        logits.shape != (len(samples),)
        or outputs.shape != (len(samples),)
        or not numpy.isfinite(logits).all()
        or not numpy.isfinite(outputs).all()
        or not bool(((outputs >= 0.0) & (outputs <= 1.0)).all())
    ):
        raise ValueError("NAS D1 volatility trend target-free CPU forward is invalid")
    return KisNasD1VolatilityTrendTargetFreeForward(
        symbol=model.spec.symbol,
        sample_count=len(samples),
        output_shape=(len(samples), 1),
        all_finite=True,
        output_bounds_valid=True,
    )


def run_kis_nas_d1_volatility_trend_l2_logistic_smoke(
    breadth_input: KisNasD1VolatilityTrendBreadthInput,
    *,
    artifact_root: Path | str = KIS_NAS_D1_VOLATILITY_TREND_BREADTH_ARTIFACT_ROOT,
    run_label: str,
    repo_root: Path | str | None = None,
) -> KisNasD1VolatilityTrendCpuSmokeRun:
    """Write immutable source-safe CPU evidence for all six symbol fits."""

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
        for spec in KIS_NAS_D1_VOLATILITY_TREND_CPU_LOGISTIC_SPECS
    )
    summary_path = output_dir / "summary.json"
    summary_payload = _cpu_summary_payload(
        breadth_input=breadth_input,
        precommit_hash=precommit_hash,
        candidates=candidates,
    )
    _assert_source_safe(summary_payload)
    summary_hash = _write_json_new(summary_path, summary_payload)
    return KisNasD1VolatilityTrendCpuSmokeRun(
        breadth_input=breadth_input,
        run_label=run_label,
        precommit_path=precommit_path,
        precommit_hash=precommit_hash,
        summary_path=summary_path,
        summary_hash=summary_hash,
        candidates=candidates,
    )


def run_kis_nas_d1_volatility_trend_cuda_breadth(
    breadth_input: KisNasD1VolatilityTrendBreadthInput,
    *,
    cpu_smoke_summary_path: Path | str,
    artifact_root: Path | str = KIS_NAS_D1_VOLATILITY_TREND_BREADTH_ARTIFACT_ROOT,
    run_label: str,
    repo_root: Path | str | None = None,
    trainer: CudaCandidateTrainer | None = None,
) -> KisNasD1VolatilityTrendCudaBreadthRun:
    """Run the frozen sequential CUDA breadth or write one scoped failure fact."""

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
    candidates: list[KisNasD1VolatilityTrendGpuCandidateReceipt] = []
    for spec in KIS_NAS_D1_VOLATILITY_TREND_CUDA_ARCHITECTURE_SPECS:
        try:
            candidate = candidate_trainer(breadth_input, spec, checkpoint_dir)
            _require_external_file(candidate.checkpoint_path, repository)
            if candidate.spec != spec:
                raise ValueError("NAS D1 volatility trend CUDA trainer changed the frozen spec")
            candidates.append(candidate)
        except Exception as exc:  # The receipt retains only a categorical recovery class.
            _remove_incomplete_checkpoint(checkpoint_dir, spec)
            failure = KisNasD1VolatilityTrendCudaFailure(
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
        not isinstance(value, KisNasD1VolatilityTrendBreadthInput)
        or getattr(value, "_attestation", None) is not _BREADTH_INPUT_ATTESTATION
        or value.schema_version != SCHEMA_VERSION
        or not _is_sha256(value.campaign_precommit_hash)
        or not _is_sha256(value.integrity_hash)
        or not isinstance(value.review_status, str)
        or tuple(value.standardizers_by_symbol) != KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
    ):
        raise ValueError("NAS D1 volatility trend breadth input is invalid")
    campaign_input = value.campaign_input
    if (
        not isinstance(campaign_input, KisNasD1VolatilityTrendCampaignInput)
        or not _is_sha256(campaign_input.contract.contract_hash)
        or not _is_sha256(campaign_input.development_input_hash)
        or not _is_sha256(campaign_input.validation_input_hash)
        or value.integrity_hash
        != _breadth_input_integrity_hash(
            campaign_input=campaign_input,
            campaign_precommit_hash=value.campaign_precommit_hash,
            review_status=value.review_status,
            standardizers_by_symbol=value.standardizers_by_symbol,
        )
    ):
        raise ValueError("NAS D1 volatility trend breadth input integrity is invalid")


_BREADTH_INPUT_ATTESTATION = object()


def _breadth_input_integrity_hash(
    *,
    campaign_input: KisNasD1VolatilityTrendCampaignInput,
    campaign_precommit_hash: str,
    review_status: str,
    standardizers_by_symbol: Mapping[str, KisNasD1VolatilityTrendStandardizer],
) -> str:
    """Cheap repeat-read integrity check after a full build-time attestation."""

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
    samples: Sequence[KisNasD1VolatilityTrendDevelopmentSample],
    development_input_hash: str,
) -> KisNasD1VolatilityTrendStandardizer:
    numpy = _numpy()
    values = numpy.asarray(
        [row for sample in samples for row in sample.feature_sequence],
        dtype=numpy.float64,
    )
    if (
        values.shape
        != (
            len(samples) * 20,
            KIS_NAS_D1_VOLATILITY_TREND_FEATURE_COUNT,
        )
        or not numpy.isfinite(values).all()
    ):
        raise ValueError("NAS D1 volatility trend development standardizer input is invalid")
    means = tuple(float(value) for value in values.mean(axis=0))
    observed_scales = tuple(float(value) for value in values.std(axis=0))
    scales = tuple(
        value if value > KIS_NAS_D1_VOLATILITY_TREND_STANDARDIZER_SCALE_FLOOR else 1.0
        for value in observed_scales
    )
    return KisNasD1VolatilityTrendStandardizer(
        symbol=symbol,
        development_input_hash=development_input_hash,
        means=means,
        scales=scales,
    )


def _flatten_matrix_from_samples(
    samples: Sequence[
        KisNasD1VolatilityTrendDevelopmentSample | KisNasD1VolatilityTrendValidationSample
    ],
    standardizer: KisNasD1VolatilityTrendStandardizer,
    numpy: object,
) -> object:
    sequence_length = 20
    transformed = tuple(
        standardizer.transform(sample.feature_sequence, sequence_length=sequence_length)
        for sample in samples
    )
    matrix = numpy.asarray(transformed, dtype=numpy.float64)
    if matrix.shape != (
        len(samples),
        sequence_length,
        KIS_NAS_D1_VOLATILITY_TREND_FEATURE_COUNT,
    ):
        raise ValueError("NAS D1 volatility trend sequence matrix is invalid")
    return matrix.reshape(len(samples), -1)


def _sequence_matrix_from_samples(
    samples: Sequence[
        KisNasD1VolatilityTrendDevelopmentSample | KisNasD1VolatilityTrendValidationSample
    ],
    standardizer: KisNasD1VolatilityTrendStandardizer,
    numpy: object,
) -> object:
    transformed = tuple(
        standardizer.transform(sample.feature_sequence, sequence_length=20) for sample in samples
    )
    matrix = numpy.asarray(transformed, dtype=numpy.float32)
    if matrix.shape != (
        len(samples),
        20,
        KIS_NAS_D1_VOLATILITY_TREND_FEATURE_COUNT,
    ) or not numpy.isfinite(matrix).all():
        raise ValueError("NAS D1 volatility trend sequence tensor is invalid")
    return matrix


def _cpu_candidate_receipt(
    breadth_input: KisNasD1VolatilityTrendBreadthInput,
    spec: KisNasD1VolatilityTrendL2LogisticSpec,
) -> KisNasD1VolatilityTrendCpuCandidateReceipt:
    model = fit_kis_nas_d1_volatility_trend_l2_logistic_smoke(breadth_input, spec)
    return KisNasD1VolatilityTrendCpuCandidateReceipt(
        model=model,
        validation_forward=forward_kis_nas_d1_volatility_trend_l2_logistic_target_free_validation(
            breadth_input,
            model,
        ),
        development_sample_count=len(breadth_input.campaign_input.development_samples(spec.symbol)),
    )


def _train_torch_cuda_candidate(
    breadth_input: KisNasD1VolatilityTrendBreadthInput,
    spec: KisNasD1VolatilityTrendArchitectureSpec,
    checkpoint_dir: Path,
    *,
    torch: object,
) -> KisNasD1VolatilityTrendGpuCandidateReceipt:
    standardizer = breadth_input.standardizer(spec.symbol)
    development = breadth_input.campaign_input.development_samples(spec.symbol)
    validation = breadth_input.campaign_input.validation_samples(spec.symbol)
    numpy = _numpy()
    development_matrix = _sequence_matrix_from_samples(development, standardizer, numpy)
    validation_matrix = _sequence_matrix_from_samples(validation, standardizer, numpy)
    labels = numpy.asarray([sample.label for sample in development], dtype=numpy.float32)
    if labels.shape != (len(development),) or not numpy.isfinite(labels).all():
        raise ValueError("NAS D1 volatility trend CUDA labels are invalid")
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
            feature_count=KIS_NAS_D1_VOLATILITY_TREND_FEATURE_COUNT,
            hidden_size=spec.hidden_size,
            attention_heads=spec.attention_heads,
            tcn_kernel_size=spec.tcn_kernel_size,
        ).to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=spec.learning_rate)
        loss_fn = torch.nn.BCEWithLogitsLoss()
        model.train()
        initial_loss = float(loss_fn(model(development_tensor), labels_tensor).detach().item())
        if not math.isfinite(initial_loss):
            raise ValueError("NAS D1 volatility trend CUDA initial loss is nonfinite")
        started = time.monotonic()
        last_loss: float | None = None
        for _ in range(spec.epochs):
            for start in range(0, len(development_tensor), spec.batch_size):
                stop = min(start + spec.batch_size, len(development_tensor))
                optimizer.zero_grad(set_to_none=True)
                loss = loss_fn(model(development_tensor[start:stop]), labels_tensor[start:stop])
                loss_value = float(loss.detach().item())
                if not math.isfinite(loss_value):
                    raise ValueError("NAS D1 volatility trend CUDA loss is nonfinite")
                loss.backward()
                optimizer.step()
                last_loss = loss_value
                if time.monotonic() - started > spec.max_seconds:
                    raise TimeoutError("NAS D1 volatility trend CUDA candidate exceeded its cap")
        if last_loss is None:
            raise ValueError("NAS D1 volatility trend CUDA candidate had no batches")
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
            raise ValueError("NAS D1 volatility trend target-free CUDA forward is invalid")
        final_loss = float(loss_fn(model(development_tensor), labels_tensor).detach().item())
        if not math.isfinite(final_loss):
            raise ValueError("NAS D1 volatility trend CUDA final loss is nonfinite")
        checkpoint_path = checkpoint_dir / f"{spec.architecture_id}-{spec.symbol.lower()}.pt"
        checkpoint_payload = {
            "schema_version": SCHEMA_VERSION,
            "kind": "kis_nas_d1_volatility_trend_breadth_checkpoint",
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
        return KisNasD1VolatilityTrendGpuCandidateReceipt(
            spec=spec,
            development_sample_count=len(development),
            validation_forward=KisNasD1VolatilityTrendTargetFreeForward(
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
    breadth_input: KisNasD1VolatilityTrendBreadthInput,
    spec: KisNasD1VolatilityTrendArchitectureSpec,
    torch: object,
) -> None:
    try:
        payload = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    except Exception as exc:  # pragma: no cover - real Torch reload faults only.
        raise ValueError(
            "NAS D1 volatility trend CUDA checkpoint cannot be safely reloaded"
        ) from exc
    standardizer = breadth_input.standardizer(spec.symbol)
    if (
        not isinstance(payload, dict)
        or payload.get("kind") != "kis_nas_d1_volatility_trend_breadth_checkpoint"
        or payload.get("campaign_contract_hash")
        != breadth_input.campaign_input.contract.contract_hash
        or payload.get("development_input_hash") != standardizer.development_input_hash
        or payload.get("standardizer_hash") != standardizer.standardizer_hash
        or payload.get("architecture") != spec.safe_payload()
    ):
        raise ValueError("NAS D1 volatility trend CUDA checkpoint contract is invalid")
    model = build_torch_sequence_model(
        torch=torch,
        architecture_id=spec.architecture_id,
        feature_count=KIS_NAS_D1_VOLATILITY_TREND_FEATURE_COUNT,
        hidden_size=spec.hidden_size,
        attention_heads=spec.attention_heads,
        tcn_kernel_size=spec.tcn_kernel_size,
    )
    try:
        model.load_state_dict(payload["state_dict"], strict=True)
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        raise ValueError("NAS D1 volatility trend CUDA checkpoint state is invalid") from exc


def _cpu_precommit_payload(
    breadth_input: KisNasD1VolatilityTrendBreadthInput,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_nas_d1_volatility_trend_cpu_smoke_precommit",
        "campaign_contract_hash": breadth_input.campaign_input.contract.contract_hash,
        "campaign_precommit_hash": breadth_input.campaign_precommit_hash,
        "review_status": breadth_input.review_status,
        "package_id": KIS_NAS_D1_VOLATILITY_TREND_CPU_SMOKE_ID,
        "source": _source_payload(breadth_input),
        "specifications": [
            spec.safe_payload()
            for spec in KIS_NAS_D1_VOLATILITY_TREND_CPU_LOGISTIC_SPECS
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
    breadth_input: KisNasD1VolatilityTrendBreadthInput,
    precommit_hash: str,
    candidates: Sequence[KisNasD1VolatilityTrendCpuCandidateReceipt],
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_nas_d1_volatility_trend_cpu_smoke",
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


def _cuda_precommit_payload(
    breadth_input: KisNasD1VolatilityTrendBreadthInput,
    cpu_smoke_summary_hash: str,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_nas_d1_volatility_trend_cuda_breadth_precommit",
        "campaign_contract_hash": breadth_input.campaign_input.contract.contract_hash,
        "campaign_precommit_hash": breadth_input.campaign_precommit_hash,
        "cpu_smoke_summary_hash": cpu_smoke_summary_hash,
        "package_id": KIS_NAS_D1_VOLATILITY_TREND_GPU_BREADTH_ID,
        "source": _source_payload(breadth_input),
        "specifications": [
            spec.safe_payload() for spec in KIS_NAS_D1_VOLATILITY_TREND_CUDA_ARCHITECTURE_SPECS
        ],
        "validation": {"forward_only": True, "labels_materialized": False},
        "compute_cap": {
            "max_seconds_per_candidate": KIS_NAS_D1_VOLATILITY_TREND_CUDA_MAX_SECONDS_PER_CANDIDATE,
            "candidate_count": len(KIS_NAS_D1_VOLATILITY_TREND_CUDA_ARCHITECTURE_SPECS),
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
    breadth_input: KisNasD1VolatilityTrendBreadthInput,
    cpu_smoke_summary_hash: str,
    precommit_hash: str,
    status: str,
    reason: str,
    candidates: Sequence[KisNasD1VolatilityTrendGpuCandidateReceipt],
    failure: KisNasD1VolatilityTrendCudaFailure | None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_nas_d1_volatility_trend_cuda_breadth",
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
    breadth_input: KisNasD1VolatilityTrendBreadthInput,
    run_label: str,
    output_dir: Path,
    cpu_smoke_summary_hash: str,
    precommit_path: Path,
    precommit_hash: str,
    status: Literal["completed", "cuda_unavailable", "candidate_failed"],
    reason: str,
    candidates: tuple[KisNasD1VolatilityTrendGpuCandidateReceipt, ...],
    failure: KisNasD1VolatilityTrendCudaFailure | None,
) -> KisNasD1VolatilityTrendCudaBreadthRun:
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
    return KisNasD1VolatilityTrendCudaBreadthRun(
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


def _source_payload(breadth_input: KisNasD1VolatilityTrendBreadthInput) -> dict[str, object]:
    return {
        "campaign_contract_hash": breadth_input.campaign_input.contract.contract_hash,
        "campaign_precommit_hash": breadth_input.campaign_precommit_hash,
        "development_input_hash": breadth_input.campaign_input.development_input_hash,
        "validation_input_hash": breadth_input.campaign_input.validation_input_hash,
        "symbols": list(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS),
        "source_limitations": list(breadth_input.campaign_input.source_limitations),
        "standardizer_hashes": [
            breadth_input.standardizer(symbol).standardizer_hash
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
    breadth_input: KisNasD1VolatilityTrendBreadthInput,
    *,
    repository: Path,
) -> str:
    summary_path = _require_external_file(path, repository)
    precommit_path = _require_external_file(summary_path.with_name("precommit.json"), repository)
    try:
        summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
        precommit_payload = json.loads(precommit_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("NAS D1 volatility trend CPU smoke receipt is unreadable") from exc
    expected_precommit = _cpu_precommit_payload(breadth_input)
    _assert_source_safe(summary_payload)
    _assert_source_safe(precommit_payload)
    precommit_hash = _sha256_file(precommit_path)
    if precommit_payload != expected_precommit:
        raise ValueError("NAS D1 volatility trend CUDA breadth requires its CPU precommit")
    expected_symbols = list(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS)
    if (
        not isinstance(summary_payload, dict)
        or summary_payload.get("kind") != "kis_nas_d1_volatility_trend_cpu_smoke"
        or summary_payload.get("status") != "completed"
        or summary_payload.get("campaign_precommit_hash") != breadth_input.campaign_precommit_hash
        or summary_payload.get("precommit_hash") != precommit_hash
        or [candidate.get("symbol") for candidate in summary_payload.get("candidates", [])]
        != expected_symbols
        or summary_payload.get("validation") != {"forward_only": True, "labels_materialized": False}
    ):
        raise ValueError("NAS D1 volatility trend CPU smoke summary is invalid")
    return _sha256_file(summary_path)


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
    output_dir = root / KIS_NAS_D1_VOLATILITY_TREND_BREADTH_ID / mode / run_label
    _reject_link_or_junction_components(output_dir)
    _reject_repository_artifact_root(output_dir.resolve(), repository)
    _reject_repository_artifact_root(output_dir.resolve(), _MODULE_REPOSITORY_ROOT)
    if output_dir.exists():
        raise FileExistsError("NAS D1 volatility trend artifact run label already exists")
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
        raise ValueError("NAS D1 volatility trend external receipt is invalid")
    resolved = candidate.resolve()
    _reject_repository_artifact_root(resolved, repository)
    _reject_repository_artifact_root(resolved, _MODULE_REPOSITORY_ROOT)
    return resolved


def _reject_repository_artifact_root(path: Path, repository: Path) -> None:
    if not path.is_relative_to(repository):
        return
    docker_artifact_root = _DOCKER_ARTIFACT_ROOT.resolve()
    if (
        repository == _DOCKER_REPOSITORY_ROOT.resolve()
        and _DOCKER_ARTIFACT_ROOT.is_mount()
        and path.is_relative_to(docker_artifact_root)
    ):
        return
    raise ValueError("NAS D1 volatility trend artifacts must stay outside the Git workspace")


def _reject_link_or_junction_components(path: Path) -> None:
    candidate = path.absolute()
    current = Path(candidate.anchor)
    for part in candidate.parts:
        if part == candidate.anchor:
            continue
        current /= part
        if _is_link_or_junction(current):
            raise ValueError("NAS D1 volatility trend artifact path cannot contain a link")


def _is_link_or_junction(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or (callable(is_junction) and is_junction())


def _write_json_new(path: Path, payload: Mapping[str, object]) -> str:
    _reject_link_or_junction_components(path.parent)
    if _is_link_or_junction(path):
        raise ValueError("NAS D1 volatility trend receipt path is invalid")
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return _sha256_file(path)


def _remove_incomplete_checkpoint(
    checkpoint_dir: Path,
    spec: KisNasD1VolatilityTrendArchitectureSpec,
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
        raise ValueError("NAS D1 volatility trend CPU loss is nonfinite")
    return result


def _symbol_development_input_hash(
    symbol: str,
    samples: Sequence[KisNasD1VolatilityTrendDevelopmentSample],
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
        "threshold_value",
        "volume",
        "weights",
    }
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if str(key).lower() in forbidden:
                raise ValueError("NAS D1 volatility trend receipt contains a source value field")
            _assert_source_safe(nested)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for nested in value:
            _assert_source_safe(nested)


def _validate_run_label(run_label: str) -> None:
    if not isinstance(run_label, str) or _RUN_LABEL.fullmatch(run_label) is None:
        raise ValueError("NAS D1 volatility trend run label is invalid")


def _resolve_symbol(symbol: str) -> str:
    if not isinstance(symbol, str):
        raise ValueError("NAS D1 volatility trend symbol is invalid")
    resolved = symbol.strip().upper()
    if resolved not in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        raise ValueError("NAS D1 volatility trend symbol is unsupported")
    return resolved


def _numpy() -> object:
    try:
        import numpy
    except ImportError as exc:  # pragma: no cover - project runtime owns NumPy.
        raise RuntimeError("NAS D1 volatility trend research requires NumPy") from exc
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
