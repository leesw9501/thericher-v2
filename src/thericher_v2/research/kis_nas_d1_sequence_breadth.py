"""Bounded per-symbol NAS D1 CPU and CUDA architecture breadth runners.

This module consumes only the already attested NAS sequence campaign.  It is
deliberately a model-plumbing surface: validation has no labels, output receipts
contain aggregate shape and finite-loss evidence only, and no replay, PnL,
ranking, broker, or provider path is reachable from here.
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
from thericher_v2.research.kis_nas_d1_sequence_campaign import (
    KIS_NAS_D1_SEQUENCE_CPU_SMOKE_ID,
    KIS_NAS_D1_SEQUENCE_FEATURE_NAMES,
    KIS_NAS_D1_SEQUENCE_GPU_BREADTH_ID,
    KIS_NAS_D1_SEQUENCE_LENGTH,
    KisNasD1DevelopmentSample,
    KisNasD1SequenceCampaignInput,
    KisNasD1ValidationSample,
    calculate_kis_nas_d1_sequence_campaign_precommit_hash,
    require_attested_kis_nas_d1_sequence_campaign_input,
)
from thericher_v2.research.sequence_architecture_models import (
    SequenceArchitectureId,
    build_torch_sequence_model,
)

KIS_NAS_D1_SEQUENCE_BREADTH_ID = "kis-nas-d1-sequence-breadth-v1"
KIS_NAS_D1_SEQUENCE_BREADTH_ARTIFACT_ROOT = Path("D:/thericher-v2/model-artifacts/research")
KIS_NAS_D1_SEQUENCE_BREADTH_EXPECTED_CAMPAIGN_CONTRACT_HASH = (
    "sha256:5a9ceb6df7b6c1909ef452b8851fbd7bd23ec03660e9fc75bb278377079aaea5"
)
KIS_NAS_D1_SEQUENCE_BREADTH_EXPECTED_CAMPAIGN_PRECOMMIT_HASH = (
    "sha256:c54e795b3fb2caa76c9367a72aadc1c0ac685241bd5c59e2e12bdb0af603d37e"
)
KIS_NAS_D1_SEQUENCE_CPU_LOGISTIC_STEPS = 160
KIS_NAS_D1_SEQUENCE_CPU_LOGISTIC_LEARNING_RATE = 0.08
KIS_NAS_D1_SEQUENCE_CPU_LOGISTIC_L2 = 0.0001
KIS_NAS_D1_SEQUENCE_STANDARDIZER_SCALE_FLOOR = 1e-12
KIS_NAS_D1_SEQUENCE_CUDA_EPOCHS = 6
KIS_NAS_D1_SEQUENCE_CUDA_BATCH_SIZE = 128
KIS_NAS_D1_SEQUENCE_CUDA_MAX_SECONDS_PER_CANDIDATE = 120
KIS_NAS_D1_SEQUENCE_CUDA_HIDDEN_SIZE = 16
KIS_NAS_D1_SEQUENCE_CUDA_ATTENTION_HEADS = 4
KIS_NAS_D1_SEQUENCE_CUDA_TCN_KERNEL_SIZE = 3
KIS_NAS_D1_SEQUENCE_CUDA_LEARNING_RATE = 0.001
_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)
_MODULE_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_DOCKER_REPOSITORY_ROOT = Path("/app")
_DOCKER_ARTIFACT_ROOT = _DOCKER_REPOSITORY_ROOT / "model_artifacts"


@dataclass(frozen=True, slots=True)
class KisNasD1SequenceStandardizer:
    """One development-only scalar standardizer for one symbol's close returns."""

    symbol: str
    development_input_hash: str
    mean: float
    scale: float
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.symbol not in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            or not _is_sha256(self.development_input_hash)
            or not math.isfinite(self.mean)
            or not math.isfinite(self.scale)
            or self.scale <= 0
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("NAS D1 sequence standardizer is invalid")

    @property
    def standardizer_hash(self) -> str:
        return _sha256_payload(
            {
                "symbol": self.symbol,
                "development_input_hash": self.development_input_hash,
                "mean": format(self.mean, ".17g"),
                "scale": format(self.scale, ".17g"),
            }
        )

    def transform(self, values: Sequence[float]) -> tuple[float, ...]:
        transformed = tuple((float(value) - self.mean) / self.scale for value in values)
        if len(transformed) != KIS_NAS_D1_SEQUENCE_LENGTH or any(
            not math.isfinite(value) for value in transformed
        ):
            raise ValueError("NAS D1 sequence standardized feature vector is invalid")
        return transformed


@dataclass(frozen=True, slots=True)
class KisNasD1L2LogisticSpec:
    """Fixed per-symbol CPU logistic fitting terms."""

    symbol: str
    seed: int
    steps: int = KIS_NAS_D1_SEQUENCE_CPU_LOGISTIC_STEPS
    learning_rate: float = KIS_NAS_D1_SEQUENCE_CPU_LOGISTIC_LEARNING_RATE
    l2_penalty: float = KIS_NAS_D1_SEQUENCE_CPU_LOGISTIC_L2
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.symbol not in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            or self.seed < 0
            or self.steps != KIS_NAS_D1_SEQUENCE_CPU_LOGISTIC_STEPS
            or self.learning_rate != KIS_NAS_D1_SEQUENCE_CPU_LOGISTIC_LEARNING_RATE
            or self.l2_penalty != KIS_NAS_D1_SEQUENCE_CPU_LOGISTIC_L2
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("NAS D1 CPU logistic specification is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "seed": self.seed,
            "steps": self.steps,
            "learning_rate": self.learning_rate,
            "l2_penalty": self.l2_penalty,
        }


KIS_NAS_D1_SEQUENCE_CPU_LOGISTIC_SPECS = tuple(
    KisNasD1L2LogisticSpec(symbol=symbol, seed=2026072810 + index)
    for index, symbol in enumerate(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS)
)


@dataclass(frozen=True, slots=True)
class KisNasD1L2LogisticModel:
    """In-memory CPU smoke model whose parameters never enter a receipt."""

    spec: KisNasD1L2LogisticSpec
    development_input_hash: str
    standardizer_hash: str
    weights: tuple[float, ...]
    intercept: float
    initial_loss: float
    final_loss: float
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "weights", tuple(float(value) for value in self.weights))
        if (
            not _is_sha256(self.development_input_hash)
            or not _is_sha256(self.standardizer_hash)
            or len(self.weights) != KIS_NAS_D1_SEQUENCE_LENGTH
            or any(not math.isfinite(value) for value in self.weights)
            or any(
                not math.isfinite(value)
                for value in (self.intercept, self.initial_loss, self.final_loss)
            )
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("NAS D1 CPU logistic model is invalid")

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
class KisNasD1TargetFreeForward:
    """Validation forward-shape evidence without scores, probabilities, or labels."""

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
            raise ValueError("NAS D1 target-free forward evidence is invalid")

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
class KisNasD1SequenceArchitectureSpec:
    """One frozen GPU architecture/symbol breadth candidate."""

    architecture_id: SequenceArchitectureId
    symbol: str
    seed: int
    hidden_size: int = KIS_NAS_D1_SEQUENCE_CUDA_HIDDEN_SIZE
    attention_heads: int = KIS_NAS_D1_SEQUENCE_CUDA_ATTENTION_HEADS
    tcn_kernel_size: int = KIS_NAS_D1_SEQUENCE_CUDA_TCN_KERNEL_SIZE
    learning_rate: float = KIS_NAS_D1_SEQUENCE_CUDA_LEARNING_RATE
    epochs: int = KIS_NAS_D1_SEQUENCE_CUDA_EPOCHS
    batch_size: int = KIS_NAS_D1_SEQUENCE_CUDA_BATCH_SIZE
    max_seconds: int = KIS_NAS_D1_SEQUENCE_CUDA_MAX_SECONDS_PER_CANDIDATE
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.architecture_id not in {"lstm", "causal_tcn", "compact_attention"}
            or self.symbol not in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            or self.seed < 0
            or self.hidden_size != KIS_NAS_D1_SEQUENCE_CUDA_HIDDEN_SIZE
            or self.attention_heads != KIS_NAS_D1_SEQUENCE_CUDA_ATTENTION_HEADS
            or self.tcn_kernel_size != KIS_NAS_D1_SEQUENCE_CUDA_TCN_KERNEL_SIZE
            or self.learning_rate != KIS_NAS_D1_SEQUENCE_CUDA_LEARNING_RATE
            or self.epochs != KIS_NAS_D1_SEQUENCE_CUDA_EPOCHS
            or self.batch_size != KIS_NAS_D1_SEQUENCE_CUDA_BATCH_SIZE
            or self.max_seconds != KIS_NAS_D1_SEQUENCE_CUDA_MAX_SECONDS_PER_CANDIDATE
            or self.hidden_size % self.attention_heads != 0
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("NAS D1 CUDA architecture specification is invalid")

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


KIS_NAS_D1_SEQUENCE_CUDA_ARCHITECTURE_SPECS = tuple(
    KisNasD1SequenceArchitectureSpec(
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
class KisNasD1SequenceBreadthInput:
    """Attested campaign plus per-symbol development-only standardizers."""

    campaign_input: KisNasD1SequenceCampaignInput
    campaign_precommit_hash: str
    standardizers_by_symbol: Mapping[str, KisNasD1SequenceStandardizer]
    schema_version: int

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("use the attested NAS D1 sequence breadth input builder")

    def standardizer(self, symbol: str) -> KisNasD1SequenceStandardizer:
        _require_attested_breadth_input(self)
        resolved = symbol.strip().upper()
        if resolved not in self.standardizers_by_symbol:
            raise ValueError("NAS D1 breadth symbol is unsupported")
        return self.standardizers_by_symbol[resolved]


@dataclass(frozen=True, slots=True)
class KisNasD1CpuCandidateReceipt:
    """Source-safe evidence for one independent CPU smoke fit."""

    model: KisNasD1L2LogisticModel
    validation_forward: KisNasD1TargetFreeForward
    development_sample_count: int
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.development_sample_count <= 0
            or self.model.spec.symbol != self.validation_forward.symbol
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("NAS D1 CPU candidate receipt is invalid")

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
class KisNasD1CpuSmokeRun:
    """One complete six-symbol, source-safe CPU smoke receipt."""

    breadth_input: KisNasD1SequenceBreadthInput
    run_label: str
    precommit_path: Path
    precommit_hash: str
    summary_path: Path
    summary_hash: str
    candidates: tuple[KisNasD1CpuCandidateReceipt, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidates", tuple(self.candidates))
        if (
            tuple(candidate.model.spec.symbol for candidate in self.candidates)
            != KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            or not _is_sha256(self.precommit_hash)
            or not _is_sha256(self.summary_hash)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("NAS D1 CPU smoke did not complete every symbol")


@dataclass(frozen=True, slots=True)
class KisNasD1GpuCandidateReceipt:
    """Aggregate-only receipt for one external CUDA checkpoint and forward pass."""

    spec: KisNasD1SequenceArchitectureSpec
    development_sample_count: int
    validation_forward: KisNasD1TargetFreeForward
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
        object.__setattr__(self, "checkpoint_path", Path(self.checkpoint_path).resolve())
        if (
            self.development_sample_count <= 0
            or self.validation_forward.symbol != self.spec.symbol
            or self.backend not in {"torch_cuda", "unit"}
            or not self.device
            or not self.torch_version
            or not _is_sha256(self.checkpoint_sha256)
            or not self.checkpoint_path.is_file()
            or _sha256_file(self.checkpoint_path) != self.checkpoint_sha256
            or any(not math.isfinite(value) for value in (self.initial_loss, self.final_loss))
            or self.cuda_peak_memory_bytes < 0
            or not self.safe_weights_only_reload
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("NAS D1 CUDA candidate receipt is invalid")

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
class KisNasD1CudaCandidateFailure:
    """Source-safe recovery evidence for one stopped frozen CUDA candidate."""

    spec: KisNasD1SequenceArchitectureSpec
    category: Literal["timeout", "memory", "invalid", "runtime"]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.category not in {"timeout", "memory", "invalid", "runtime"}
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("NAS D1 CUDA candidate failure is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "architecture": self.spec.safe_payload(),
            "category": self.category,
        }


@dataclass(frozen=True, slots=True)
class KisNasD1CudaBreadthRun:
    """One sequential GPU breadth attempt, completed or truthfully unavailable."""

    breadth_input: KisNasD1SequenceBreadthInput
    run_label: str
    cpu_smoke_summary_hash: str
    precommit_path: Path
    precommit_hash: str
    summary_path: Path
    summary_hash: str
    status: Literal["completed", "cuda_unavailable", "candidate_failed"]
    reason: str
    candidates: tuple[KisNasD1GpuCandidateReceipt, ...]
    failure: KisNasD1CudaCandidateFailure | None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidates", tuple(self.candidates))
        if (
            self.status not in {"completed", "cuda_unavailable", "candidate_failed"}
            or not self.reason
            or not _is_sha256(self.cpu_smoke_summary_hash)
            or not _is_sha256(self.precommit_hash)
            or not _is_sha256(self.summary_hash)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("NAS D1 CUDA breadth receipt is invalid")
        expected_specs = KIS_NAS_D1_SEQUENCE_CUDA_ARCHITECTURE_SPECS
        completed_specs = tuple(candidate.spec for candidate in self.candidates)
        if self.status == "completed" and completed_specs != expected_specs:
            raise ValueError("NAS D1 CUDA breadth did not complete its frozen candidates")
        if self.status == "cuda_unavailable" and (self.candidates or self.failure is not None):
            raise ValueError("CUDA-unavailable breadth cannot contain trained candidates")
        if self.status == "completed" and self.failure is not None:
            raise ValueError("completed CUDA breadth cannot contain a failure")
        if self.status == "candidate_failed" and (
            self.failure is None
            or len(completed_specs) >= len(expected_specs)
            or completed_specs != expected_specs[: len(completed_specs)]
            or self.failure.spec != expected_specs[len(completed_specs)]
        ):
            raise ValueError("NAS D1 CUDA failure does not match its frozen candidate")


CudaCandidateTrainer = Callable[
    [KisNasD1SequenceBreadthInput, KisNasD1SequenceArchitectureSpec, Path],
    KisNasD1GpuCandidateReceipt,
]


def build_kis_nas_d1_sequence_breadth_input(
    campaign_input: KisNasD1SequenceCampaignInput,
    *,
    campaign_precommit_hash: str,
) -> KisNasD1SequenceBreadthInput:
    """Build one per-symbol standardization boundary from development data only."""

    require_attested_kis_nas_d1_sequence_campaign_input(campaign_input)
    if not _is_sha256(campaign_precommit_hash):
        raise ValueError("NAS D1 breadth requires the campaign precommit hash")
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
    result = object.__new__(KisNasD1SequenceBreadthInput)
    object.__setattr__(result, "campaign_input", campaign_input)
    object.__setattr__(result, "campaign_precommit_hash", campaign_precommit_hash)
    object.__setattr__(result, "standardizers_by_symbol", MappingProxyType(standardizers))
    object.__setattr__(result, "schema_version", SCHEMA_VERSION)
    _require_attested_breadth_input(result)
    return result


def require_frozen_kis_nas_d1_sequence_breadth_campaign(
    campaign_input: KisNasD1SequenceCampaignInput,
) -> None:
    """Reject source drift before this fixed breadth package writes an artifact."""

    require_attested_kis_nas_d1_sequence_campaign_input(campaign_input)
    if (
        campaign_input.contract.contract_hash
        != KIS_NAS_D1_SEQUENCE_BREADTH_EXPECTED_CAMPAIGN_CONTRACT_HASH
        or calculate_kis_nas_d1_sequence_campaign_precommit_hash(campaign_input)
        != KIS_NAS_D1_SEQUENCE_BREADTH_EXPECTED_CAMPAIGN_PRECOMMIT_HASH
    ):
        raise ValueError("NAS D1 breadth campaign does not match its frozen precommit")


def fit_kis_nas_d1_l2_logistic_smoke(
    breadth_input: KisNasD1SequenceBreadthInput,
    spec: KisNasD1L2LogisticSpec,
) -> KisNasD1L2LogisticModel:
    """Fit one deterministic, independent logistic model from development labels only."""

    _require_attested_breadth_input(breadth_input)
    standardizer = breadth_input.standardizer(spec.symbol)
    samples = breadth_input.campaign_input.development_samples(spec.symbol)
    numpy = _numpy()
    features = _matrix_from_development_samples(samples, standardizer, numpy)
    labels = numpy.asarray([sample.label for sample in samples], dtype=numpy.float64)
    if (
        features.shape != (len(samples), KIS_NAS_D1_SEQUENCE_LENGTH)
        or labels.shape != (len(samples),)
        or not numpy.isfinite(features).all()
        or not numpy.isfinite(labels).all()
    ):
        raise ValueError("NAS D1 CPU logistic development matrix is invalid")
    generator = numpy.random.default_rng(spec.seed)
    weights = generator.normal(
        loc=0.0,
        scale=0.01,
        size=KIS_NAS_D1_SEQUENCE_LENGTH,
    ).astype(numpy.float64)
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
            raise ValueError("NAS D1 CPU logistic training diverged")
    final_loss = _logistic_loss(features, labels, weights, intercept, numpy)
    return KisNasD1L2LogisticModel(
        spec=spec,
        development_input_hash=standardizer.development_input_hash,
        standardizer_hash=standardizer.standardizer_hash,
        weights=tuple(float(value) for value in weights),
        intercept=intercept,
        initial_loss=initial_loss,
        final_loss=final_loss,
    )


def forward_kis_nas_d1_l2_logistic_target_free_validation(
    breadth_input: KisNasD1SequenceBreadthInput,
    model: KisNasD1L2LogisticModel,
) -> KisNasD1TargetFreeForward:
    """Prove validation tensor shape and finite forward values without a target read."""

    _require_attested_breadth_input(breadth_input)
    standardizer = breadth_input.standardizer(model.spec.symbol)
    if (
        model.development_input_hash != standardizer.development_input_hash
        or model.standardizer_hash != standardizer.standardizer_hash
    ):
        raise ValueError("NAS D1 CPU model does not match its development input")
    samples = breadth_input.campaign_input.validation_samples(model.spec.symbol)
    numpy = _numpy()
    features = _matrix_from_validation_samples(samples, standardizer, numpy)
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
        raise ValueError("NAS D1 target-free CPU validation forward is invalid")
    return KisNasD1TargetFreeForward(
        symbol=model.spec.symbol,
        sample_count=len(samples),
        output_shape=(len(samples), 1),
        all_finite=True,
        output_bounds_valid=True,
    )


def run_kis_nas_d1_l2_logistic_smoke(
    breadth_input: KisNasD1SequenceBreadthInput,
    *,
    artifact_root: Path | str = KIS_NAS_D1_SEQUENCE_BREADTH_ARTIFACT_ROOT,
    run_label: str,
    repo_root: Path | str | None = None,
) -> KisNasD1CpuSmokeRun:
    """Write a precommit then complete all six deterministic CPU smoke fits."""

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
        for spec in KIS_NAS_D1_SEQUENCE_CPU_LOGISTIC_SPECS
    )
    summary_path = output_dir / "summary.json"
    summary_payload = _cpu_summary_payload(
        breadth_input=breadth_input,
        precommit_hash=precommit_hash,
        candidates=candidates,
    )
    _assert_source_safe(summary_payload)
    summary_hash = _write_json_new(summary_path, summary_payload)
    return KisNasD1CpuSmokeRun(
        breadth_input=breadth_input,
        run_label=run_label,
        precommit_path=precommit_path,
        precommit_hash=precommit_hash,
        summary_path=summary_path,
        summary_hash=summary_hash,
        candidates=candidates,
    )


def run_kis_nas_d1_cuda_sequence_breadth(
    breadth_input: KisNasD1SequenceBreadthInput,
    *,
    cpu_smoke_summary_path: Path | str,
    artifact_root: Path | str = KIS_NAS_D1_SEQUENCE_BREADTH_ARTIFACT_ROOT,
    run_label: str,
    repo_root: Path | str | None = None,
    trainer: CudaCandidateTrainer | None = None,
) -> KisNasD1CudaBreadthRun:
    """Run the fixed sequential CUDA breadth or record one exact unavailable fact."""

    _require_attested_breadth_input(breadth_input)
    repository = Path(repo_root or Path.cwd()).resolve()
    cpu_smoke_summary_hash = _validate_cpu_smoke_summary(
        Path(cpu_smoke_summary_path),
        breadth_input,
        repository=repository,
    )
    output_dir = _prepare_output_dir(
        artifact_root=artifact_root,
        repo_root=repo_root,
        mode="cuda-breadth",
        run_label=run_label,
    )
    precommit_path = output_dir / "precommit.json"
    precommit_payload = _cuda_precommit_payload(breadth_input, cpu_smoke_summary_hash)
    _assert_source_safe(precommit_payload)
    precommit_hash = _write_json_new(precommit_path, precommit_payload)
    failure: KisNasD1CudaCandidateFailure | None = None
    if trainer is not None:
        checkpoint_dir = output_dir / "checkpoints"
        checkpoint_dir.mkdir()
        candidates, failure = _run_cuda_candidates(
            breadth_input,
            checkpoint_dir,
            trainer,
        )
        status: Literal["completed", "cuda_unavailable", "candidate_failed"] = (
            "candidate_failed" if failure is not None else "completed"
        )
        reason = (
            "injected CUDA breadth stopped at one frozen candidate"
            if failure is not None
            else "injected CUDA breadth trainer completed every frozen candidate"
        )
    else:
        try:
            import torch
        except ImportError:
            candidates = ()
            status = "cuda_unavailable"
            reason = "PyTorch is unavailable in the research runtime"
        else:
            if not torch.cuda.is_available():
                candidates = ()
                status = "cuda_unavailable"
                reason = "PyTorch CUDA is unavailable in the research runtime"
            else:
                checkpoint_dir = output_dir / "checkpoints"
                checkpoint_dir.mkdir()
                candidates, failure = _run_cuda_candidates(
                    breadth_input,
                    checkpoint_dir,
                    lambda input_value, spec, directory: _train_torch_cuda_candidate(
                        input_value,
                        spec,
                        directory,
                        torch=torch,
                    ),
                )
                status = "candidate_failed" if failure is not None else "completed"
                reason = (
                    "sequential CUDA breadth stopped at one frozen candidate"
                    if failure is not None
                    else "sequential CUDA breadth completed every frozen candidate"
                )
    summary_path = output_dir / "summary.json"
    summary_payload = _cuda_summary_payload(
        breadth_input=breadth_input,
        cpu_smoke_summary_hash=cpu_smoke_summary_hash,
        precommit_hash=precommit_hash,
        status=status,
        reason=reason,
        candidates=candidates,
        failure=failure,
    )
    _assert_source_safe(summary_payload)
    summary_hash = _write_json_new(summary_path, summary_payload)
    return KisNasD1CudaBreadthRun(
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


def _run_cuda_candidates(
    breadth_input: KisNasD1SequenceBreadthInput,
    checkpoint_dir: Path,
    trainer: CudaCandidateTrainer,
) -> tuple[tuple[KisNasD1GpuCandidateReceipt, ...], KisNasD1CudaCandidateFailure | None]:
    candidates: list[KisNasD1GpuCandidateReceipt] = []
    resolved_checkpoint_dir = checkpoint_dir.resolve()
    for spec in KIS_NAS_D1_SEQUENCE_CUDA_ARCHITECTURE_SPECS:
        try:
            candidate = trainer(breadth_input, spec, checkpoint_dir)
            if candidate.spec != spec or not candidate.checkpoint_path.is_relative_to(
                resolved_checkpoint_dir
            ):
                raise ValueError("NAS D1 CUDA candidate receipt does not match its output scope")
        except Exception as exc:
            _remove_incomplete_checkpoint(checkpoint_dir, spec)
            return tuple(candidates), KisNasD1CudaCandidateFailure(
                spec=spec,
                category=_cuda_failure_category(exc),
            )
        candidates.append(candidate)
    return tuple(candidates), None


def _remove_incomplete_checkpoint(
    checkpoint_dir: Path,
    spec: KisNasD1SequenceArchitectureSpec,
) -> None:
    checkpoint_path = _checkpoint_path(checkpoint_dir, spec)
    try:
        checkpoint_path.unlink()
    except FileNotFoundError:
        pass


def _checkpoint_path(
    checkpoint_dir: Path,
    spec: KisNasD1SequenceArchitectureSpec,
) -> Path:
    return checkpoint_dir / f"{spec.architecture_id}-{spec.symbol}.pt"


def _cuda_failure_category(exc: Exception) -> Literal["timeout", "memory", "invalid", "runtime"]:
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, MemoryError):
        return "memory"
    if isinstance(exc, ValueError):
        return "invalid"
    return "runtime"


def _require_attested_breadth_input(value: object) -> None:
    if (
        not isinstance(value, KisNasD1SequenceBreadthInput)
        or value.schema_version != SCHEMA_VERSION
        or not _is_sha256(value.campaign_precommit_hash)
        or tuple(value.standardizers_by_symbol) != KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
    ):
        raise ValueError("NAS D1 sequence breadth requires an attested input")
    require_attested_kis_nas_d1_sequence_campaign_input(value.campaign_input)
    for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        standardizer = value.standardizers_by_symbol[symbol]
        if (
            not isinstance(standardizer, KisNasD1SequenceStandardizer)
            or standardizer.symbol != symbol
            or standardizer.development_input_hash
            != _symbol_development_input_hash(
                symbol,
                value.campaign_input.development_samples(symbol),
            )
        ):
            raise ValueError("NAS D1 sequence breadth standardizer is invalid")


def _fit_development_standardizer(
    *,
    symbol: str,
    samples: Sequence[KisNasD1DevelopmentSample],
    development_input_hash: str,
) -> KisNasD1SequenceStandardizer:
    numpy = _numpy()
    values = numpy.asarray(
        [value for sample in samples for value in sample.close_returns],
        dtype=numpy.float64,
    )
    if (
        values.shape != (len(samples) * KIS_NAS_D1_SEQUENCE_LENGTH,)
        or not numpy.isfinite(values).all()
    ):
        raise ValueError("NAS D1 development standardizer values are invalid")
    mean = float(values.mean())
    observed_scale = float(values.std())
    scale = observed_scale if observed_scale > KIS_NAS_D1_SEQUENCE_STANDARDIZER_SCALE_FLOOR else 1.0
    return KisNasD1SequenceStandardizer(
        symbol=symbol,
        development_input_hash=development_input_hash,
        mean=mean,
        scale=scale,
    )


def _symbol_development_input_hash(
    symbol: str,
    samples: Sequence[KisNasD1DevelopmentSample],
) -> str:
    if not samples or any(sample.symbol != symbol for sample in samples):
        raise ValueError("NAS D1 per-symbol development input is invalid")
    return _sha256_payload(
        {
            "symbol": symbol,
            "samples": [
                {
                    "return_anchor_start": sample.return_anchor_start.isoformat(),
                    "feature_start": sample.feature_start.isoformat(),
                    "decision_start": sample.decision_start.isoformat(),
                    "entry_start": sample.entry_start.isoformat(),
                    "exit_start": sample.exit_start.isoformat(),
                    "close_returns": [format(value, ".17g") for value in sample.close_returns],
                    "label": sample.label,
                }
                for sample in samples
            ],
        }
    )


def _matrix_from_development_samples(
    samples: Sequence[KisNasD1DevelopmentSample],
    standardizer: KisNasD1SequenceStandardizer,
    numpy: object,
) -> object:
    return _matrix_from_close_return_rows(
        (sample.close_returns for sample in samples),
        standardizer,
        numpy,
    )


def _matrix_from_validation_samples(
    samples: Sequence[KisNasD1ValidationSample],
    standardizer: KisNasD1SequenceStandardizer,
    numpy: object,
) -> object:
    return _matrix_from_close_return_rows(
        (sample.close_returns for sample in samples),
        standardizer,
        numpy,
    )


def _matrix_from_close_return_rows(
    rows: Sequence[Sequence[float]] | object,
    standardizer: KisNasD1SequenceStandardizer,
    numpy: object,
) -> object:
    transformed = tuple(standardizer.transform(tuple(row)) for row in rows)
    matrix = numpy.asarray(transformed, dtype=numpy.float64)
    if (
        matrix.ndim != 2
        or matrix.shape[1] != KIS_NAS_D1_SEQUENCE_LENGTH
        or not numpy.isfinite(matrix).all()
    ):
        raise ValueError("NAS D1 standardized feature matrix is invalid")
    return matrix


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
        raise ValueError("NAS D1 CPU logistic loss is nonfinite")
    return result


def _cpu_candidate_receipt(
    breadth_input: KisNasD1SequenceBreadthInput,
    spec: KisNasD1L2LogisticSpec,
) -> KisNasD1CpuCandidateReceipt:
    model = fit_kis_nas_d1_l2_logistic_smoke(breadth_input, spec)
    return KisNasD1CpuCandidateReceipt(
        model=model,
        validation_forward=forward_kis_nas_d1_l2_logistic_target_free_validation(
            breadth_input,
            model,
        ),
        development_sample_count=len(breadth_input.campaign_input.development_samples(spec.symbol)),
    )


def _train_torch_cuda_candidate(
    breadth_input: KisNasD1SequenceBreadthInput,
    spec: KisNasD1SequenceArchitectureSpec,
    checkpoint_dir: Path,
    *,
    torch: object,
) -> KisNasD1GpuCandidateReceipt:
    standardizer = breadth_input.standardizer(spec.symbol)
    development = breadth_input.campaign_input.development_samples(spec.symbol)
    validation = breadth_input.campaign_input.validation_samples(spec.symbol)
    numpy = _numpy()
    development_matrix = _matrix_from_development_samples(development, standardizer, numpy)
    validation_matrix = _matrix_from_validation_samples(validation, standardizer, numpy)
    labels = numpy.asarray([sample.label for sample in development], dtype=numpy.float32)
    if labels.shape != (len(development),) or not numpy.isfinite(labels).all():
        raise ValueError("NAS D1 CUDA development labels are invalid")
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
        development_tensor = torch.tensor(
            development_matrix[:, :, None],
            dtype=torch.float32,
            device=device,
        )
        labels_tensor = torch.tensor(labels, dtype=torch.float32, device=device).unsqueeze(1)
        validation_tensor = torch.tensor(
            validation_matrix[:, :, None],
            dtype=torch.float32,
            device=device,
        )
        model = build_torch_sequence_model(
            torch=torch,
            architecture_id=spec.architecture_id,
            feature_count=len(KIS_NAS_D1_SEQUENCE_FEATURE_NAMES),
            hidden_size=spec.hidden_size,
            attention_heads=spec.attention_heads,
            tcn_kernel_size=spec.tcn_kernel_size,
        ).to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=spec.learning_rate)
        loss_fn = torch.nn.BCEWithLogitsLoss()
        model.train()
        initial_loss = float(loss_fn(model(development_tensor), labels_tensor).detach().item())
        if not math.isfinite(initial_loss):
            raise ValueError("NAS D1 CUDA initial loss is nonfinite")
        started = time.monotonic()
        last_loss: float | None = None
        for _ in range(spec.epochs):
            for start in range(0, len(development_tensor), spec.batch_size):
                stop = min(start + spec.batch_size, len(development_tensor))
                optimizer.zero_grad(set_to_none=True)
                loss = loss_fn(model(development_tensor[start:stop]), labels_tensor[start:stop])
                loss_value = float(loss.detach().item())
                if not math.isfinite(loss_value):
                    raise ValueError("NAS D1 CUDA training loss is nonfinite")
                loss.backward()
                optimizer.step()
                last_loss = loss_value
                if time.monotonic() - started > spec.max_seconds:
                    raise TimeoutError("NAS D1 CUDA candidate exceeded its fixed compute budget")
        if last_loss is None:
            raise ValueError("NAS D1 CUDA candidate received no development batches")
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
            raise ValueError("NAS D1 target-free CUDA validation forward is invalid")
        final_loss = float(loss_fn(model(development_tensor), labels_tensor).detach().item())
        if not math.isfinite(final_loss):
            raise ValueError("NAS D1 CUDA final loss is nonfinite")
        checkpoint_path = _checkpoint_path(checkpoint_dir, spec)
        checkpoint_payload = {
            "schema_version": SCHEMA_VERSION,
            "kind": "kis_nas_d1_sequence_breadth_checkpoint",
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
        return KisNasD1GpuCandidateReceipt(
            spec=spec,
            development_sample_count=len(development),
            validation_forward=KisNasD1TargetFreeForward(
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
    breadth_input: KisNasD1SequenceBreadthInput,
    spec: KisNasD1SequenceArchitectureSpec,
    torch: object,
) -> None:
    try:
        payload = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    except Exception as exc:  # pragma: no cover - requires an actual torch runtime fault.
        raise ValueError("NAS D1 CUDA checkpoint cannot be safely reloaded") from exc
    standardizer = breadth_input.standardizer(spec.symbol)
    if (
        not isinstance(payload, dict)
        or payload.get("kind") != "kis_nas_d1_sequence_breadth_checkpoint"
        or payload.get("campaign_contract_hash")
        != breadth_input.campaign_input.contract.contract_hash
        or payload.get("development_input_hash") != standardizer.development_input_hash
        or payload.get("standardizer_hash") != standardizer.standardizer_hash
        or payload.get("architecture") != spec.safe_payload()
    ):
        raise ValueError("NAS D1 CUDA checkpoint contract is invalid")
    model = build_torch_sequence_model(
        torch=torch,
        architecture_id=spec.architecture_id,
        feature_count=len(KIS_NAS_D1_SEQUENCE_FEATURE_NAMES),
        hidden_size=spec.hidden_size,
        attention_heads=spec.attention_heads,
        tcn_kernel_size=spec.tcn_kernel_size,
    )
    try:
        model.load_state_dict(payload["state_dict"], strict=True)
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        raise ValueError("NAS D1 CUDA checkpoint state is incompatible") from exc


def _validate_cpu_smoke_summary(
    path: Path,
    breadth_input: KisNasD1SequenceBreadthInput,
    *,
    repository: Path,
) -> str:
    precommit_path = path.with_name("precommit.json")
    if (
        path.is_symlink()
        or path.parent.is_symlink()
        or not path.is_file()
        or precommit_path.is_symlink()
        or not precommit_path.is_file()
    ):
        raise ValueError("NAS D1 CUDA breadth requires a CPU smoke summary")
    resolved_path = path.resolve()
    resolved_precommit_path = precommit_path.resolve()
    _reject_repository_artifact_root(resolved_path, repository)
    _reject_repository_artifact_root(resolved_precommit_path, repository)
    _reject_repository_artifact_root(resolved_path, _MODULE_REPOSITORY_ROOT)
    _reject_repository_artifact_root(resolved_precommit_path, _MODULE_REPOSITORY_ROOT)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        precommit_payload = json.loads(precommit_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("NAS D1 CPU smoke summary is unreadable") from exc
    expected_precommit_payload = _cpu_precommit_payload(breadth_input)
    _assert_source_safe(expected_precommit_payload)
    _assert_source_safe(precommit_payload)
    _assert_source_safe(payload)
    if precommit_payload != expected_precommit_payload:
        raise ValueError("NAS D1 CPU smoke precommit does not satisfy CUDA breadth input")
    precommit_hash = _sha256_file(precommit_path)
    if (
        not isinstance(payload, dict)
        or set(payload)
        != {
            "schema_version",
            "kind",
            "status",
            "precommit_hash",
            "source",
            "candidates",
            "validation",
            "artifact_policy",
            "reporting",
        }
        or payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("kind") != "kis_nas_d1_sequence_cpu_smoke"
        or payload.get("status") != "completed"
        or payload.get("precommit_hash") != precommit_hash
        or payload.get("source") != _source_payload(breadth_input)
        or payload.get("validation")
        != {"labels_materialized": False, "forward_only": True}
        or payload.get("artifact_policy")
        != {
            "repo_storage_allowed": False,
            "checkpoints_written": False,
            "raw_rows_persisted": False,
            "predictions_persisted": False,
        }
        or payload.get("reporting") != _reporting_payload()
        or not _matches_cpu_smoke_candidates(payload.get("candidates"), breadth_input)
    ):
        raise ValueError("NAS D1 CPU smoke summary does not satisfy CUDA breadth input")
    return _sha256_file(path)


def _matches_cpu_smoke_candidates(
    value: object,
    breadth_input: KisNasD1SequenceBreadthInput,
) -> bool:
    if not isinstance(value, list) or len(value) != len(KIS_NAS_D1_SEQUENCE_CPU_LOGISTIC_SPECS):
        return False
    for item, spec in zip(value, KIS_NAS_D1_SEQUENCE_CPU_LOGISTIC_SPECS, strict=True):
        standardizer = breadth_input.standardizer(spec.symbol)
        validation_count = len(breadth_input.campaign_input.validation_samples(spec.symbol))
        if (
            not isinstance(item, dict)
            or set(item)
            != {
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
            }
            or item.get("symbol") != spec.symbol
            or item.get("model_id") != "l2_logistic"
            or not _is_sha256(item.get("model_parameter_hash"))
            or item.get("standardizer_hash") != standardizer.standardizer_hash
            or item.get("development_sample_count")
            != len(breadth_input.campaign_input.development_samples(spec.symbol))
            or item.get("steps") != spec.steps
            or item.get("seed") != spec.seed
            or not _is_finite_loss_text(item.get("initial_loss"))
            or not _is_finite_loss_text(item.get("final_loss"))
            or item.get("validation_forward")
            != {
                "symbol": spec.symbol,
                "sample_count": validation_count,
                "output_shape": [validation_count, 1],
                "all_finite": True,
                "output_bounds_valid": True,
                "labels_materialized": False,
            }
        ):
            return False
    return True


def _is_finite_loss_text(value: object) -> bool:
    try:
        return isinstance(value, str) and math.isfinite(float(value))
    except ValueError:
        return False


def _cpu_precommit_payload(breadth_input: KisNasD1SequenceBreadthInput) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_nas_d1_sequence_cpu_smoke_precommit",
        "package_id": KIS_NAS_D1_SEQUENCE_CPU_SMOKE_ID,
        "source": _source_payload(breadth_input),
        "models": [spec.safe_payload() for spec in KIS_NAS_D1_SEQUENCE_CPU_LOGISTIC_SPECS],
        "features": {
            "sequence_length": KIS_NAS_D1_SEQUENCE_LENGTH,
            "feature_shape": [KIS_NAS_D1_SEQUENCE_LENGTH, 1],
            "per_symbol_only": True,
            "standardization": "per_symbol_development_only",
        },
        "validation": {
            "labels_materialized": False,
            "operation": "target_free_forward_shape_only",
        },
        "artifact_policy": {
            "repo_storage_allowed": False,
            "checkpoints_written": False,
            "raw_rows_persisted": False,
            "predictions_persisted": False,
        },
        "reporting": _reporting_payload(),
    }


def _cuda_precommit_payload(
    breadth_input: KisNasD1SequenceBreadthInput,
    cpu_smoke_summary_hash: str,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_nas_d1_sequence_cuda_breadth_precommit",
        "package_id": KIS_NAS_D1_SEQUENCE_GPU_BREADTH_ID,
        "source": _source_payload(breadth_input),
        "cpu_smoke_summary_hash": cpu_smoke_summary_hash,
        "candidates": [spec.safe_payload() for spec in KIS_NAS_D1_SEQUENCE_CUDA_ARCHITECTURE_SPECS],
        "features": {
            "sequence_length": KIS_NAS_D1_SEQUENCE_LENGTH,
            "feature_shape": [KIS_NAS_D1_SEQUENCE_LENGTH, 1],
            "per_symbol_only": True,
            "standardization": "per_symbol_development_only",
        },
        "validation": {
            "labels_materialized": False,
            "operation": "target_free_forward_shape_only",
        },
        "checkpoint_policy": {
            "repo_storage_allowed": False,
            "format": "torch_state_dict_only",
            "safe_weights_only_reload_required": True,
        },
        "reporting": _reporting_payload(),
    }


def _cpu_summary_payload(
    *,
    breadth_input: KisNasD1SequenceBreadthInput,
    precommit_hash: str,
    candidates: Sequence[KisNasD1CpuCandidateReceipt],
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_nas_d1_sequence_cpu_smoke",
        "status": "completed",
        "precommit_hash": precommit_hash,
        "source": _source_payload(breadth_input),
        "candidates": [candidate.safe_payload() for candidate in candidates],
        "validation": {
            "labels_materialized": False,
            "forward_only": True,
        },
        "artifact_policy": {
            "repo_storage_allowed": False,
            "checkpoints_written": False,
            "raw_rows_persisted": False,
            "predictions_persisted": False,
        },
        "reporting": _reporting_payload(),
    }


def _cuda_summary_payload(
    *,
    breadth_input: KisNasD1SequenceBreadthInput,
    cpu_smoke_summary_hash: str,
    precommit_hash: str,
    status: Literal["completed", "cuda_unavailable", "candidate_failed"],
    reason: str,
    candidates: Sequence[KisNasD1GpuCandidateReceipt],
    failure: KisNasD1CudaCandidateFailure | None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_nas_d1_sequence_cuda_breadth",
        "status": status,
        "reason": reason,
        "precommit_hash": precommit_hash,
        "cpu_smoke_summary_hash": cpu_smoke_summary_hash,
        "source": _source_payload(breadth_input),
        "candidates": [candidate.safe_payload() for candidate in candidates],
        "validation": {
            "labels_materialized": False,
            "forward_only": True,
        },
        "artifact_policy": {
            "repo_storage_allowed": False,
            "checkpoints_written": bool(candidates),
            "raw_rows_persisted": False,
            "predictions_persisted": False,
        },
        "reporting": _reporting_payload(),
    }
    if failure is not None:
        payload["failure"] = failure.safe_payload()
    return payload


def _source_payload(breadth_input: KisNasD1SequenceBreadthInput) -> dict[str, object]:
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


def _prepare_output_dir(
    *,
    artifact_root: Path | str,
    repo_root: Path | str | None,
    mode: Literal["cpu-smoke", "cuda-breadth"],
    run_label: str,
) -> Path:
    _validate_run_label(run_label)
    repository = Path(repo_root or Path.cwd()).resolve()
    requested_root = Path(artifact_root)
    if requested_root.is_symlink():
        raise ValueError("NAS D1 breadth artifact root cannot be a symlink")
    root = requested_root.resolve()
    _reject_repository_artifact_root(root, repository)
    _reject_repository_artifact_root(root, _MODULE_REPOSITORY_ROOT)
    package_root = root / KIS_NAS_D1_SEQUENCE_BREADTH_ID / mode
    _require_non_symlink_artifact_components(
        root,
        (KIS_NAS_D1_SEQUENCE_BREADTH_ID, mode, run_label),
    )
    output_dir = package_root / run_label
    _reject_repository_artifact_root(output_dir, repository)
    _reject_repository_artifact_root(output_dir, _MODULE_REPOSITORY_ROOT)
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError("NAS D1 breadth artifact run label already exists")
    output_dir.mkdir(parents=True, exist_ok=False)
    return output_dir


def _reject_repository_artifact_root(path: Path, repository: Path) -> None:
    if not path.is_relative_to(repository):
        return
    docker_artifact_root = _DOCKER_ARTIFACT_ROOT.resolve()
    if (
        repository == _DOCKER_REPOSITORY_ROOT.resolve()
        and docker_artifact_root.is_mount()
        and path.is_relative_to(docker_artifact_root)
    ):
        return
    raise ValueError("NAS D1 breadth artifacts must stay outside the Git workspace")


def _require_non_symlink_artifact_components(root: Path, parts: Sequence[str]) -> None:
    current = root
    for part in parts:
        current /= part
        if current.is_symlink():
            raise ValueError("NAS D1 breadth artifact path cannot contain a symlink")


def _write_json_new(path: Path, payload: Mapping[str, object]) -> str:
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError("NAS D1 breadth receipt path cannot contain a symlink")
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return _sha256_file(path)


def _assert_source_safe(payload: object) -> None:
    forbidden_keys = {
        "account",
        "account_number",
        "broker",
        "close_returns",
        "credentials",
        "feature_rows",
        "labels",
        "pnl",
        "predictions",
        "probabilities",
        "raw_bars",
        "secret",
    }
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if str(key).lower() in forbidden_keys:
                raise ValueError("NAS D1 breadth receipt contains a prohibited value-level field")
            _assert_source_safe(value)
    elif isinstance(payload, Sequence) and not isinstance(payload, str | bytes):
        for value in payload:
            _assert_source_safe(value)


def _validate_run_label(run_label: str) -> None:
    if not isinstance(run_label, str) or _RUN_LABEL.fullmatch(run_label) is None:
        raise ValueError("NAS D1 breadth run_label is invalid")


def _sha256_payload(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    digest = value.removeprefix("sha256:")
    if len(digest) != 64:
        return False
    try:
        int(digest, 16)
    except ValueError:
        return False
    return True


def _numpy():
    import numpy

    return numpy
