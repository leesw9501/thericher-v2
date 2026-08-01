"""Bounded, source-local Tiingo D1 sequence breadth research.

This module deliberately keeps the raw provider data in memory.  Its external
artifacts contain only identities, precommitted contracts, and aggregate
metrics.  It is not a KIS adapter, execution route, model-selection routine, or
Paper-trading input.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.data.tiingo_etf_daily import (
    TIINGO_ETF_D1_SYMBOLS,
    LoadedTiingoEtfDailySnapshot,
    TiingoEtfDailyRow,
)
from thericher_v2.research.sequence_architecture_models import (
    build_torch_sequence_model,
)

TIINGO_D1_SEQUENCE_BREADTH_ID = "tiingo-d1-sequence-breadth-v1"
TIINGO_D1_SEQUENCE_LENGTHS = (5, 20)
TIINGO_D1_SEQUENCE_FEATURE_NAMES = (
    "close_return",
    "intraday_return",
    "range_ratio",
    "volume_log_change",
)
TIINGO_D1_SEQUENCE_DEVELOPMENT_NUMERATOR = 7
TIINGO_D1_SEQUENCE_DEVELOPMENT_DENOMINATOR = 10
TIINGO_D1_SEQUENCE_TARGET_HORIZON = 1
TIINGO_D1_SEQUENCE_PURGE_SESSIONS = 22
TIINGO_D1_SEQUENCE_DISCONTINUITY_LIMIT = Decimal("0.20")
TIINGO_D1_SEQUENCE_COST_BAND = (Decimal("5"), Decimal("10"), Decimal("20"))
TIINGO_D1_SEQUENCE_MIN_DEVELOPMENT_SAMPLES = 500
TIINGO_D1_SEQUENCE_MIN_VALIDATION_SAMPLES = 100
TIINGO_D1_SEQUENCE_LOGISTIC_EPOCHS = 80
TIINGO_D1_SEQUENCE_LOGISTIC_LEARNING_RATE = 0.05
TIINGO_D1_SEQUENCE_LOGISTIC_L2 = 0.0001
TIINGO_D1_SEQUENCE_GPU_EPOCHS = 4
TIINGO_D1_SEQUENCE_GPU_BATCH_SIZE = 512
TIINGO_D1_SEQUENCE_GPU_MAX_SECONDS_PER_MODEL = 90
TIINGO_D1_SEQUENCE_GPU_HIDDEN_SIZE = 16
TIINGO_D1_SEQUENCE_GPU_ATTENTION_HEADS = 4
TIINGO_D1_SEQUENCE_GPU_TCN_KERNEL_SIZE = 3
TIINGO_D1_SEQUENCE_GPU_LEARNING_RATE = 0.001
TIINGO_D1_SEQUENCE_GPU_ARCHITECTURES = ("gru", "causal_tcn", "compact_attention")
_MODULE_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)

SampleExclusion = Literal["event", "feature_discontinuity"]
Mode = Literal["cpu", "cuda"]


@dataclass(frozen=True, slots=True)
class TiingoD1SequenceConfig:
    """Frozen causal geometry and compute limits for this one campaign family."""

    lengths: tuple[int, ...] = TIINGO_D1_SEQUENCE_LENGTHS
    development_numerator: int = TIINGO_D1_SEQUENCE_DEVELOPMENT_NUMERATOR
    development_denominator: int = TIINGO_D1_SEQUENCE_DEVELOPMENT_DENOMINATOR
    target_horizon: int = TIINGO_D1_SEQUENCE_TARGET_HORIZON
    purge_sessions: int = TIINGO_D1_SEQUENCE_PURGE_SESSIONS
    discontinuity_limit: Decimal = TIINGO_D1_SEQUENCE_DISCONTINUITY_LIMIT
    cost_band: tuple[Decimal, ...] = TIINGO_D1_SEQUENCE_COST_BAND
    min_development_samples: int = TIINGO_D1_SEQUENCE_MIN_DEVELOPMENT_SAMPLES
    min_validation_samples: int = TIINGO_D1_SEQUENCE_MIN_VALIDATION_SAMPLES
    logistic_epochs: int = TIINGO_D1_SEQUENCE_LOGISTIC_EPOCHS
    logistic_learning_rate: float = TIINGO_D1_SEQUENCE_LOGISTIC_LEARNING_RATE
    logistic_l2: float = TIINGO_D1_SEQUENCE_LOGISTIC_L2
    gpu_epochs: int = TIINGO_D1_SEQUENCE_GPU_EPOCHS
    gpu_batch_size: int = TIINGO_D1_SEQUENCE_GPU_BATCH_SIZE
    gpu_max_seconds_per_model: int = TIINGO_D1_SEQUENCE_GPU_MAX_SECONDS_PER_MODEL
    seed: int = 811
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.lengths != TIINGO_D1_SEQUENCE_LENGTHS
            or self.development_numerator != TIINGO_D1_SEQUENCE_DEVELOPMENT_NUMERATOR
            or self.development_denominator != TIINGO_D1_SEQUENCE_DEVELOPMENT_DENOMINATOR
            or self.target_horizon != TIINGO_D1_SEQUENCE_TARGET_HORIZON
            or self.purge_sessions != TIINGO_D1_SEQUENCE_PURGE_SESSIONS
            or self.discontinuity_limit != TIINGO_D1_SEQUENCE_DISCONTINUITY_LIMIT
            or self.cost_band != TIINGO_D1_SEQUENCE_COST_BAND
            or self.min_development_samples != TIINGO_D1_SEQUENCE_MIN_DEVELOPMENT_SAMPLES
            or self.min_validation_samples != TIINGO_D1_SEQUENCE_MIN_VALIDATION_SAMPLES
            or self.logistic_epochs != TIINGO_D1_SEQUENCE_LOGISTIC_EPOCHS
            or self.logistic_learning_rate != TIINGO_D1_SEQUENCE_LOGISTIC_LEARNING_RATE
            or self.logistic_l2 != TIINGO_D1_SEQUENCE_LOGISTIC_L2
            or self.gpu_epochs != TIINGO_D1_SEQUENCE_GPU_EPOCHS
            or self.gpu_batch_size != TIINGO_D1_SEQUENCE_GPU_BATCH_SIZE
            or self.gpu_max_seconds_per_model
            != TIINGO_D1_SEQUENCE_GPU_MAX_SECONDS_PER_MODEL
            or self.seed != 811
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("Tiingo D1 sequence config is frozen")
        if self.purge_sessions < max(self.lengths) + 2:
            raise ValueError("Tiingo D1 sequence purge is insufficient")

    def safe_payload(self) -> dict[str, object]:
        return {
            "sequence_lengths": list(self.lengths),
            "feature_names": list(TIINGO_D1_SEQUENCE_FEATURE_NAMES),
            "feature_available_through": "completed_session_t_close",
            "target": "next_session_open_to_close_direction_non_up_is_zero",
            "target_horizon_sessions": self.target_horizon,
            "development_fraction": {
                "numerator": self.development_numerator,
                "denominator": self.development_denominator,
            },
            "purge_sessions": self.purge_sessions,
            "event_mask": "known_ex_dividend_or_split_t-L_through_t+1_descriptive_only",
            "feature_discontinuity_window": "t-L+1_through_t_only",
            "feature_discontinuity_limit": _decimal_text(self.discontinuity_limit),
            "cost_band_bps": [_decimal_text(cost) for cost in self.cost_band],
            "minimum_samples": {
                "development_per_symbol_window": self.min_development_samples,
                "validation_per_symbol_window": self.min_validation_samples,
            },
            "cpu_control": "pooled_summary_feature_logistic",
            "gpu_batch": {
                "architectures": list(TIINGO_D1_SEQUENCE_GPU_ARCHITECTURES),
                "epochs": self.gpu_epochs,
                "batch_size": self.gpu_batch_size,
                "max_seconds_per_model": self.gpu_max_seconds_per_model,
                "hidden_size": TIINGO_D1_SEQUENCE_GPU_HIDDEN_SIZE,
            },
            "seed": self.seed,
            "candidate_selection_allowed": False,
            "ensemble_allowed": False,
            "paper_input_allowed": False,
        }


@dataclass(frozen=True, slots=True)
class _SequenceSample:
    """An in-memory causal sample; numeric values never enter a safe artifact."""

    symbol: str
    length: int
    dependency_start_index: int
    dependency_end_index: int
    features: tuple[tuple[float, ...], ...] = field(repr=False)
    label: int = field(repr=False)
    target_return: float = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "features", tuple(tuple(row) for row in self.features))
        if (
            self.symbol not in TIINGO_ETF_D1_SYMBOLS
            or self.length not in TIINGO_D1_SEQUENCE_LENGTHS
            or self.label not in {0, 1}
            or self.dependency_start_index < 0
            or self.dependency_end_index <= self.dependency_start_index
            or len(self.features) != self.length
            or any(len(row) != len(TIINGO_D1_SEQUENCE_FEATURE_NAMES) for row in self.features)
            or any(not math.isfinite(value) for row in self.features for value in row)
            or not math.isfinite(self.target_return)
        ):
            raise ValueError("Tiingo D1 sequence sample is invalid")


@dataclass(frozen=True, slots=True)
class TiingoD1SequenceCellFacts:
    symbol: str
    length: int
    development_candidate_count: int
    development_accepted_count: int
    development_event_excluded_count: int
    development_discontinuity_excluded_count: int
    validation_candidate_count: int
    validation_accepted_count: int
    validation_event_excluded_count: int
    validation_discontinuity_excluded_count: int
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        values = (
            self.development_candidate_count,
            self.development_accepted_count,
            self.development_event_excluded_count,
            self.development_discontinuity_excluded_count,
            self.validation_candidate_count,
            self.validation_accepted_count,
            self.validation_event_excluded_count,
            self.validation_discontinuity_excluded_count,
        )
        if (
            self.symbol not in TIINGO_ETF_D1_SYMBOLS
            or self.length not in TIINGO_D1_SEQUENCE_LENGTHS
            or min(values) < 0
            or self.development_candidate_count
            != self.development_accepted_count
            + self.development_event_excluded_count
            + self.development_discontinuity_excluded_count
            or self.validation_candidate_count
            != self.validation_accepted_count
            + self.validation_event_excluded_count
            + self.validation_discontinuity_excluded_count
        ):
            raise ValueError("Tiingo D1 sequence cell facts are invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "sequence_length": self.length,
            "development": {
                "candidate_count": self.development_candidate_count,
                "accepted_count": self.development_accepted_count,
                "event_excluded_count": self.development_event_excluded_count,
                "feature_discontinuity_excluded_count": (
                    self.development_discontinuity_excluded_count
                ),
            },
            "validation": {
                "candidate_count": self.validation_candidate_count,
                "accepted_count": self.validation_accepted_count,
                "event_excluded_count": self.validation_event_excluded_count,
                "feature_discontinuity_excluded_count": (
                    self.validation_discontinuity_excluded_count
                ),
            },
        }


@dataclass(frozen=True, slots=True)
class TiingoD1SequenceInput:
    """Reattached source contract plus hidden normalized tensors for one fixed family."""

    dataset_id: str
    dataset_hash: str
    manifest_hash: str
    config: TiingoD1SequenceConfig
    cells: tuple[TiingoD1SequenceCellFacts, ...]
    development_samples: Mapping[tuple[str, int], tuple[_SequenceSample, ...]] = field(repr=False)
    validation_samples: Mapping[tuple[str, int], tuple[_SequenceSample, ...]] = field(repr=False)
    normalizer_hashes: Mapping[tuple[str, int], str]
    input_hash: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        development = {key: tuple(value) for key, value in self.development_samples.items()}
        validation = {key: tuple(value) for key, value in self.validation_samples.items()}
        normalizers = dict(self.normalizer_hashes)
        expected_keys = tuple(
            (symbol, length) for symbol in TIINGO_ETF_D1_SYMBOLS for length in self.config.lengths
        )
        if (
            not self.dataset_id.startswith("us_equities.tiingo_etf_daily.snapshot=")
            or not _is_sha256(self.dataset_hash)
            or not _is_sha256(self.manifest_hash)
            or not _is_sha256(self.input_hash)
            or tuple(development) != expected_keys
            or tuple(validation) != expected_keys
            or tuple(normalizers) != expected_keys
            or tuple((cell.symbol, cell.length) for cell in self.cells) != expected_keys
            or any(not samples for samples in development.values())
            or any(not samples for samples in validation.values())
            or any(not _is_sha256(value) for value in normalizers.values())
        ):
            raise ValueError("Tiingo D1 sequence input is invalid")
        object.__setattr__(self, "development_samples", MappingProxyType(development))
        object.__setattr__(self, "validation_samples", MappingProxyType(validation))
        object.__setattr__(self, "normalizer_hashes", MappingProxyType(normalizers))

    @property
    def gpu_eligible(self) -> bool:
        return all(
            len(self.development_samples[key]) >= self.config.min_development_samples
            and len(self.validation_samples[key]) >= self.config.min_validation_samples
            for key in self.development_samples
        )

    def safe_payload(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "dataset_hash": self.dataset_hash,
            "manifest_hash": self.manifest_hash,
            "source": {
                "provider": "Tiingo standard EOD API",
                "raw_ohlcv_only": True,
                "retrospective_research_only": True,
                "point_in_time_eligible": False,
                "paper_input_eligible": False,
            },
            "config": self.config.safe_payload(),
            "cell_facts": [cell.safe_payload() for cell in self.cells],
            "normalizer_hashes": {
                _cell_key(symbol, length): self.normalizer_hashes[(symbol, length)]
                for symbol, length in self.normalizer_hashes
            },
            "normalizer_hashes_scope": "runtime_numerical_diagnostic_not_input_identity",
            "input_identity_scope": "source_snapshot_contract_and_sample_structure",
            "input_hash": self.input_hash,
            "gpu_eligibility": {
                "eligible": self.gpu_eligible,
                "rule": "all_symbol_window_cells_meet_frozen_minimum_samples",
            },
        }


@dataclass(frozen=True, slots=True)
class TiingoD1SequenceRun:
    mode: Mode
    input: TiingoD1SequenceInput
    precommit_path: Path
    precommit_hash: str
    summary_path: Path
    schema_version: int = SCHEMA_VERSION


def build_tiingo_d1_sequence_input(
    snapshot: LoadedTiingoEtfDailySnapshot,
    *,
    config: TiingoD1SequenceConfig | None = None,
) -> TiingoD1SequenceInput:
    """Build hidden causal tensors and assert the development/validation dependency gap."""

    resolved_config = config or TiingoD1SequenceConfig()
    _validate_snapshot_rows(snapshot)
    cells: list[TiingoD1SequenceCellFacts] = []
    development: dict[tuple[str, int], tuple[_SequenceSample, ...]] = {}
    validation: dict[tuple[str, int], tuple[_SequenceSample, ...]] = {}
    normalizer_hashes: dict[tuple[str, int], str] = {}
    hash_material: list[object] = []
    for symbol in TIINGO_ETF_D1_SYMBOLS:
        rows = snapshot.rows_by_symbol[symbol]
        development_end, validation_start = _split_indices(len(rows), resolved_config)
        for length in resolved_config.lengths:
            development_raw, development_counts = _build_phase_samples(
                rows,
                symbol=symbol,
                length=length,
                start_index=length,
                end_index=development_end - 2,
                config=resolved_config,
            )
            validation_raw, validation_counts = _build_phase_samples(
                rows,
                symbol=symbol,
                length=length,
                start_index=validation_start,
                end_index=len(rows) - 2,
                config=resolved_config,
            )
            _assert_phase_dependency_separation(development_raw, validation_raw)
            means, scales = _fit_normalizer(development_raw)
            key = (symbol, length)
            development[key] = _normalize_samples(development_raw, means=means, scales=scales)
            validation[key] = _normalize_samples(validation_raw, means=means, scales=scales)
            normalizer_hashes[key] = _sha256_payload(
                {
                    "symbol": symbol,
                    "length": length,
                    "means": [_float_text(value) for value in means],
                    "scales": [_float_text(value) for value in scales],
                }
            )
            cells.append(
                TiingoD1SequenceCellFacts(
                    symbol=symbol,
                    length=length,
                    development_candidate_count=development_counts[0],
                    development_accepted_count=len(development_raw),
                    development_event_excluded_count=development_counts[1],
                    development_discontinuity_excluded_count=development_counts[2],
                    validation_candidate_count=validation_counts[0],
                    validation_accepted_count=len(validation_raw),
                    validation_event_excluded_count=validation_counts[1],
                    validation_discontinuity_excluded_count=validation_counts[2],
                )
            )
            hash_material.append(
                {
                    "symbol": symbol,
                    "length": length,
                    "development": _sample_identity_material(development[key]),
                    "validation": _sample_identity_material(validation[key]),
                }
            )
    input_hash = _sha256_payload(
        {
            "dataset_id": snapshot.snapshot.dataset_id,
            "dataset_hash": snapshot.snapshot.dataset_hash,
            "manifest_hash": snapshot.snapshot.manifest_hash,
            "campaign_id": TIINGO_D1_SEQUENCE_BREADTH_ID,
            "feature_contract": "raw_ohlcv_normalized_sequence_v1",
            "config": resolved_config.safe_payload(),
            "cell_facts": [cell.safe_payload() for cell in cells],
            "samples": hash_material,
        }
    )
    return TiingoD1SequenceInput(
        dataset_id=snapshot.snapshot.dataset_id,
        dataset_hash=snapshot.snapshot.dataset_hash,
        manifest_hash=snapshot.snapshot.manifest_hash,
        config=resolved_config,
        cells=tuple(cells),
        development_samples=development,
        validation_samples=validation,
        normalizer_hashes=normalizer_hashes,
        input_hash=input_hash,
    )


def run_tiingo_d1_sequence_cpu(
    snapshot: LoadedTiingoEtfDailySnapshot,
    *,
    artifact_root: Path,
    run_label: str,
    repo_root: Path | None = None,
    config: TiingoD1SequenceConfig | None = None,
) -> TiingoD1SequenceRun:
    """Precommit and run the deterministic CPU comparator without external access."""

    resolved_config = config or TiingoD1SequenceConfig()
    output_dir = _prepare_output_dir(
        artifact_root=artifact_root,
        run_label=run_label,
        mode="cpu",
        repo_root=repo_root,
    )
    precommit_path, precommit_hash = _write_precommit(
        output_dir=output_dir,
        snapshot=snapshot,
        config=resolved_config,
        mode="cpu",
        cpu_summary=None,
    )
    try:
        sequence_input = build_tiingo_d1_sequence_input(snapshot, config=resolved_config)
        summary = _cpu_summary(sequence_input)
    except Exception as error:
        _write_incomplete(output_dir, precommit_hash, mode="cpu", error=error)
        raise
    summary_path = output_dir / "summary.json"
    _write_json_new(
        summary_path,
        {
            "schema_version": SCHEMA_VERSION,
            "campaign_id": TIINGO_D1_SEQUENCE_BREADTH_ID,
            "mode": "cpu",
            "status": "completed_descriptive_only",
            "precommit_hash": precommit_hash,
            "input_hash": sequence_input.input_hash,
            "gpu_eligibility": summary["gpu_eligibility"],
            "input": sequence_input.safe_payload(),
            "cpu": summary,
            "candidate_selection_allowed": False,
            "ensemble_allowed": False,
            "gpu_appointment_created": False,
            "paper_input_allowed": False,
            "promotion_allowed": False,
            "raw_market_data_written": False,
        },
    )
    return TiingoD1SequenceRun(
        mode="cpu",
        input=sequence_input,
        precommit_path=precommit_path,
        precommit_hash=precommit_hash,
        summary_path=summary_path,
    )


def run_tiingo_d1_sequence_cuda(
    snapshot: LoadedTiingoEtfDailySnapshot,
    *,
    cpu_summary_path: Path,
    artifact_root: Path,
    run_label: str,
    repo_root: Path | None = None,
    config: TiingoD1SequenceConfig | None = None,
    trainer: Callable[[TiingoD1SequenceInput], Mapping[str, object]] | None = None,
) -> TiingoD1SequenceRun:
    """Run the fixed CUDA breadth only after the matching CPU eligibility evidence."""

    resolved_config = config or TiingoD1SequenceConfig()
    cpu_summary = _load_cpu_summary(cpu_summary_path)
    output_dir = _prepare_output_dir(
        artifact_root=artifact_root,
        run_label=run_label,
        mode="cuda",
        repo_root=repo_root,
    )
    precommit_path, precommit_hash = _write_precommit(
        output_dir=output_dir,
        snapshot=snapshot,
        config=resolved_config,
        mode="cuda",
        cpu_summary=cpu_summary,
    )
    try:
        sequence_input = build_tiingo_d1_sequence_input(snapshot, config=resolved_config)
        _verify_cpu_eligibility(cpu_summary, sequence_input)
        breadth = dict((trainer or _run_torch_cuda_breadth)(sequence_input))
        _validate_cuda_breadth(breadth)
    except Exception as error:
        _write_incomplete(output_dir, precommit_hash, mode="cuda", error=error)
        raise
    summary_path = output_dir / "summary.json"
    _write_json_new(
        summary_path,
        {
            "schema_version": SCHEMA_VERSION,
            "campaign_id": TIINGO_D1_SEQUENCE_BREADTH_ID,
            "mode": "cuda",
            "status": "completed_descriptive_only",
            "precommit_hash": precommit_hash,
            "cpu_precommit_hash": cpu_summary["precommit_hash"],
            "input_hash": sequence_input.input_hash,
            "gpu_eligibility": {
                "eligible": sequence_input.gpu_eligible,
                "reason": "all_symbol_window_cells_meet_frozen_minimum_samples",
            },
            "input": sequence_input.safe_payload(),
            "cuda": breadth,
            "candidate_selection_allowed": False,
            "ensemble_allowed": False,
            "gpu_appointment_created": True,
            "paper_input_allowed": False,
            "promotion_allowed": False,
            "checkpoint_written": False,
            "raw_market_data_written": False,
        },
    )
    return TiingoD1SequenceRun(
        mode="cuda",
        input=sequence_input,
        precommit_path=precommit_path,
        precommit_hash=precommit_hash,
        summary_path=summary_path,
    )


def _build_phase_samples(
    rows: tuple[TiingoEtfDailyRow, ...],
    *,
    symbol: str,
    length: int,
    start_index: int,
    end_index: int,
    config: TiingoD1SequenceConfig,
) -> tuple[tuple[_SequenceSample, ...], tuple[int, int, int]]:
    samples: list[_SequenceSample] = []
    candidates = max(0, end_index - start_index + 1)
    event_excluded = 0
    discontinuity_excluded = 0
    for decision_index in range(start_index, end_index + 1):
        exclusion = _sample_exclusion(
            rows,
            decision_index=decision_index,
            length=length,
            discontinuity_limit=config.discontinuity_limit,
        )
        if exclusion == "event":
            event_excluded += 1
            continue
        if exclusion == "feature_discontinuity":
            discontinuity_excluded += 1
            continue
        features = tuple(
            _feature_row(rows, index)
            for index in range(decision_index - length + 1, decision_index + 1)
        )
        next_row = rows[decision_index + 1]
        target_return = float(next_row.close / next_row.open - Decimal("1"))
        samples.append(
            _SequenceSample(
                symbol=symbol,
                length=length,
                dependency_start_index=decision_index - length,
                dependency_end_index=decision_index + 1,
                features=features,
                label=1 if target_return > 0 else 0,
                target_return=target_return,
            )
        )
    return tuple(samples), (candidates, event_excluded, discontinuity_excluded)


def _feature_row(rows: tuple[TiingoEtfDailyRow, ...], index: int) -> tuple[float, ...]:
    previous = rows[index - 1]
    current = rows[index]
    return (
        float(current.close / previous.close - Decimal("1")),
        float(current.close / current.open - Decimal("1")),
        float((current.high - current.low) / current.open),
        math.log1p(float(current.volume)) - math.log1p(float(previous.volume)),
    )


def _sample_exclusion(
    rows: tuple[TiingoEtfDailyRow, ...],
    *,
    decision_index: int,
    length: int,
    discontinuity_limit: Decimal,
) -> SampleExclusion | None:
    if decision_index - length < 0 or decision_index + 1 >= len(rows):
        raise ValueError("Tiingo D1 sequence sample index is invalid")
    if any(
        row.div_cash != 0 or row.split_factor != 1
        for row in rows[decision_index - length : decision_index + 2]
    ):
        return "event"
    for index in range(decision_index - length + 1, decision_index + 1):
        close_return = rows[index].close / rows[index - 1].close - Decimal("1")
        if abs(close_return) > discontinuity_limit:
            return "feature_discontinuity"
    return None


def _split_indices(session_count: int, config: TiingoD1SequenceConfig) -> tuple[int, int]:
    development_end = (
        session_count * config.development_numerator // config.development_denominator
    )
    validation_start = development_end + config.purge_sessions
    if development_end <= max(config.lengths) + 1 or validation_start >= session_count - 1:
        raise ValueError("Tiingo D1 sequence source has insufficient sessions")
    return development_end, validation_start


def _assert_phase_dependency_separation(
    development: Sequence[_SequenceSample],
    validation: Sequence[_SequenceSample],
) -> None:
    if not development or not validation:
        raise ValueError("Tiingo D1 sequence phase input is unavailable")
    development_end = max(sample.dependency_end_index for sample in development)
    validation_start = min(sample.dependency_start_index for sample in validation)
    if validation_start <= development_end:
        raise ValueError("Tiingo D1 sequence development and validation dependencies overlap")


def _fit_normalizer(
    samples: Sequence[_SequenceSample],
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    flattened = [row for sample in samples for row in sample.features]
    feature_count = len(TIINGO_D1_SEQUENCE_FEATURE_NAMES)
    means = tuple(
        math.fsum(row[index] for row in flattened) / len(flattened)
        for index in range(feature_count)
    )
    scales = tuple(
        math.sqrt(math.fsum((row[index] - means[index]) ** 2 for row in flattened) / len(flattened))
        for index in range(feature_count)
    )
    if any(not math.isfinite(value) for value in means) or any(
        not math.isfinite(value) or value <= 0 for value in scales
    ):
        raise ValueError("Tiingo D1 sequence development normalizer is invalid")
    return means, scales


def _normalize_samples(
    samples: Sequence[_SequenceSample],
    *,
    means: tuple[float, ...],
    scales: tuple[float, ...],
) -> tuple[_SequenceSample, ...]:
    return tuple(
        _SequenceSample(
            symbol=sample.symbol,
            length=sample.length,
            dependency_start_index=sample.dependency_start_index,
            dependency_end_index=sample.dependency_end_index,
            features=tuple(
                tuple((value - means[index]) / scales[index] for index, value in enumerate(row))
                for row in sample.features
            ),
            label=sample.label,
            target_return=sample.target_return,
        )
        for sample in samples
    )


def _cpu_summary(sequence_input: TiingoD1SequenceInput) -> dict[str, object]:
    cells: list[dict[str, object]] = []
    training_hashes: dict[str, str] = {}
    for length in sequence_input.config.lengths:
        development = tuple(
            sample
            for symbol in TIINGO_ETF_D1_SYMBOLS
            for sample in sequence_input.development_samples[(symbol, length)]
        )
        weights, bias = _fit_logistic(development, config=sequence_input.config)
        training_hashes[f"L{length}"] = _sha256_payload(
            {
                "length": length,
                "weights": [_float_text(value) for value in weights],
                "bias": _float_text(bias),
            }
        )
        for symbol in TIINGO_ETF_D1_SYMBOLS:
            validation = sequence_input.validation_samples[(symbol, length)]
            logistic_probabilities = tuple(
                _sigmoid(_dot(weights, _summary_features(sample)) + bias)
                for sample in validation
            )
            naive_probabilities = tuple(
                0.75 if sample.features[-1][1] > 0 else 0.25 for sample in validation
            )
            cells.append(
                {
                    "symbol": symbol,
                    "sequence_length": length,
                    "validation_sample_count": len(validation),
                    "always_flat": _flat_metrics(len(validation)),
                    "previous_intraday_direction": _score_probabilities(
                        naive_probabilities,
                        validation,
                        cost_band=sequence_input.config.cost_band,
                    ),
                    "summary_feature_logistic": _score_probabilities(
                        logistic_probabilities,
                        validation,
                        cost_band=sequence_input.config.cost_band,
                    ),
                }
            )
    return {
        "status": "completed",
        "training_hashes": training_hashes,
        "cells": cells,
        "gpu_eligibility": {
            "eligible": sequence_input.gpu_eligible,
            "reason": (
                "all_symbol_window_cells_meet_frozen_minimum_samples"
                if sequence_input.gpu_eligible
                else "one_or_more_symbol_window_cells_below_frozen_minimum_samples"
            ),
        },
        "candidate_selection_allowed": False,
        "ensemble_allowed": False,
        "promotion_allowed": False,
    }


def _fit_logistic(
    samples: Sequence[_SequenceSample],
    *,
    config: TiingoD1SequenceConfig,
) -> tuple[tuple[float, ...], float]:
    if not samples:
        raise ValueError("Tiingo D1 sequence CPU training input is unavailable")
    feature_count = len(_summary_features(samples[0]))
    weights = [0.0] * feature_count
    bias = 0.0
    for _ in range(config.logistic_epochs):
        gradient = [0.0] * feature_count
        bias_gradient = 0.0
        for sample in samples:
            values = _summary_features(sample)
            error = _sigmoid(_dot(weights, values) + bias) - sample.label
            for index, value in enumerate(values):
                gradient[index] += error * value
            bias_gradient += error
        sample_count = len(samples)
        for index in range(feature_count):
            gradient[index] = gradient[index] / sample_count + config.logistic_l2 * weights[index]
            weights[index] -= config.logistic_learning_rate * gradient[index]
        bias -= config.logistic_learning_rate * bias_gradient / sample_count
    return tuple(weights), bias


def _summary_features(sample: _SequenceSample) -> tuple[float, ...]:
    return tuple(
        value
        for feature_index in range(len(TIINGO_D1_SEQUENCE_FEATURE_NAMES))
        for value in (
            math.fsum(row[feature_index] for row in sample.features) / len(sample.features),
            sample.features[-1][feature_index],
        )
    )


def _score_probabilities(
    probabilities: Sequence[float],
    samples: Sequence[_SequenceSample],
    *,
    cost_band: Sequence[Decimal],
) -> dict[str, object]:
    if len(probabilities) != len(samples):
        raise ValueError("Tiingo D1 sequence probability geometry is invalid")
    decisions = tuple(probability >= 0.5 for probability in probabilities)
    long_count = sum(decisions)
    correct = sum(
        int((probability >= 0.5) == bool(sample.label))
        for probability, sample in zip(probabilities, samples, strict=True)
    )
    brier = math.fsum(
        (probability - sample.label) ** 2
        for probability, sample in zip(probabilities, samples, strict=True)
    ) / len(samples)
    gross_bps = math.fsum(
        sample.target_return * 10000
        for decision, sample in zip(decisions, samples, strict=True)
        if decision
    )
    return {
        "direction_accuracy": _float_text(correct / len(samples)),
        "brier": _float_text(brier),
        "long_trade_count": long_count,
        "gross_total_bps": _float_text(gross_bps),
        "net_total_bps_by_round_trip_cost": {
            _decimal_text(cost): _float_text(gross_bps - long_count * float(cost))
            for cost in cost_band
        },
        "prediction_hash": _sha256_payload(
            ["1" if decision else "0" for decision in decisions]
        ),
    }


def _flat_metrics(sample_count: int) -> dict[str, object]:
    return {
        "direction_accuracy": None,
        "brier": None,
        "long_trade_count": 0,
        "gross_total_bps": "0",
        "net_total_bps_by_round_trip_cost": {
            _decimal_text(cost): "0" for cost in TIINGO_D1_SEQUENCE_COST_BAND
        },
        "sample_count": sample_count,
    }


def _run_torch_cuda_breadth(sequence_input: TiingoD1SequenceInput) -> Mapping[str, object]:
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("PyTorch CUDA is unavailable")
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    device = torch.device("cuda")
    models: list[dict[str, object]] = []
    for length_index, length in enumerate(sequence_input.config.lengths):
        development = tuple(
            sample
            for symbol in TIINGO_ETF_D1_SYMBOLS
            for sample in sequence_input.development_samples[(symbol, length)]
        )
        for architecture_index, architecture_id in enumerate(TIINGO_D1_SEQUENCE_GPU_ARCHITECTURES):
            seed = sequence_input.config.seed + length_index * 100 + architecture_index
            torch.manual_seed(seed)
            torch.cuda.manual_seed_all(seed)
            model = _build_cuda_model(torch, architecture_id=architecture_id).to(device)
            optimizer = torch.optim.AdamW(
                model.parameters(),
                lr=TIINGO_D1_SEQUENCE_GPU_LEARNING_RATE,
            )
            loss_fn = torch.nn.BCEWithLogitsLoss()
            features = torch.tensor(
                [sample.features for sample in development], dtype=torch.float32, device=device
            )
            labels = torch.tensor(
                [sample.label for sample in development], dtype=torch.float32, device=device
            ).unsqueeze(1)
            started = time.monotonic()
            initial_loss = _torch_loss(model, features, labels, loss_fn)
            for _ in range(sequence_input.config.gpu_epochs):
                for start in range(0, len(development), sequence_input.config.gpu_batch_size):
                    end = start + sequence_input.config.gpu_batch_size
                    optimizer.zero_grad(set_to_none=True)
                    loss = loss_fn(model(features[start:end]), labels[start:end])
                    loss.backward()
                    optimizer.step()
                if time.monotonic() - started > sequence_input.config.gpu_max_seconds_per_model:
                    raise RuntimeError("Tiingo D1 sequence CUDA compute stop reached")
            torch.cuda.synchronize()
            elapsed = time.monotonic() - started
            final_loss = _torch_loss(model, features, labels, loss_fn)
            validation_cells = []
            for symbol in TIINGO_ETF_D1_SYMBOLS:
                validation = sequence_input.validation_samples[(symbol, length)]
                tensor = torch.tensor(
                    [sample.features for sample in validation], dtype=torch.float32, device=device
                )
                with torch.no_grad():
                    probabilities = tuple(torch.sigmoid(model(tensor)).flatten().cpu().tolist())
                validation_cells.append(
                    {
                        "symbol": symbol,
                        "validation_sample_count": len(validation),
                        "metrics": _score_probabilities(
                            probabilities,
                            validation,
                            cost_band=sequence_input.config.cost_band,
                        ),
                    }
                )
            models.append(
                {
                    "architecture_id": architecture_id,
                    "sequence_length": length,
                    "seed": seed,
                    "development_sample_count": len(development),
                    "epochs": sequence_input.config.gpu_epochs,
                    "elapsed_seconds": _float_text(elapsed),
                    "initial_loss": _float_text(initial_loss),
                    "final_loss": _float_text(final_loss),
                    "validation_cells": validation_cells,
                    "checkpoint_written": False,
                }
            )
            del features, labels, model, optimizer
            torch.cuda.empty_cache()
    return {
        "backend": "torch_cuda",
        "device_count": torch.cuda.device_count(),
        "cuda_version": torch.version.cuda,
        "models": models,
        "candidate_selection_allowed": False,
        "ensemble_allowed": False,
        "promotion_allowed": False,
    }


def _build_cuda_model(torch: object, *, architecture_id: str) -> object:
    if architecture_id == "gru":
        nn = torch.nn

        class GruModel(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.encoder = nn.GRU(
                    input_size=len(TIINGO_D1_SEQUENCE_FEATURE_NAMES),
                    hidden_size=TIINGO_D1_SEQUENCE_GPU_HIDDEN_SIZE,
                    batch_first=True,
                )
                self.head = nn.Linear(TIINGO_D1_SEQUENCE_GPU_HIDDEN_SIZE, 1)

            def forward(self, values: object) -> object:
                encoded, _ = self.encoder(values)
                return self.head(encoded[:, -1, :])

        return GruModel()
    return build_torch_sequence_model(
        torch=torch,
        architecture_id=architecture_id,
        feature_count=len(TIINGO_D1_SEQUENCE_FEATURE_NAMES),
        hidden_size=TIINGO_D1_SEQUENCE_GPU_HIDDEN_SIZE,
        attention_heads=TIINGO_D1_SEQUENCE_GPU_ATTENTION_HEADS,
        tcn_kernel_size=TIINGO_D1_SEQUENCE_GPU_TCN_KERNEL_SIZE,
    )


def _torch_loss(model: object, features: object, labels: object, loss_fn: object) -> float:
    import torch

    with torch.no_grad():
        return float(loss_fn(model(features), labels).item())


def _prepare_output_dir(
    *,
    artifact_root: Path,
    run_label: str,
    mode: Mode,
    repo_root: Path | None,
) -> Path:
    if _SAFE_RUN_LABEL.fullmatch(run_label) is None:
        raise ValueError("Tiingo D1 sequence run label is invalid")
    resolved_root = Path(artifact_root).resolve(strict=False)
    for candidate in (repo_root, _MODULE_REPOSITORY_ROOT):
        if candidate is None:
            continue
        repository = Path(candidate).resolve(strict=True)
        if (
            resolved_root == repository or resolved_root.is_relative_to(repository)
        ) and not _is_container_external_artifact_root(resolved_root, repository):
            raise ValueError("Tiingo D1 sequence artifacts must stay outside the Git workspace")
    output_dir = (
        resolved_root / "research" / TIINGO_D1_SEQUENCE_BREADTH_ID / mode / run_label
    ).resolve(strict=False)
    if not output_dir.is_relative_to(resolved_root):
        raise ValueError("Tiingo D1 sequence artifact path is invalid")
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError("Tiingo D1 sequence artifact already exists")
    output_dir.mkdir(parents=True, exist_ok=False)
    return output_dir


def _is_container_external_artifact_root(path: Path, repo_root: Path) -> bool:
    """Allow the named model-artifact bind mount used by the Docker Research profile."""

    container_repo = Path("/app").resolve()
    mount_root = container_repo / "model_artifacts"
    return repo_root == container_repo and (
        path == mount_root or path.is_relative_to(mount_root)
    )


def _write_precommit(
    *,
    output_dir: Path,
    snapshot: LoadedTiingoEtfDailySnapshot,
    config: TiingoD1SequenceConfig,
    mode: Mode,
    cpu_summary: Mapping[str, object] | None,
) -> tuple[Path, str]:
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": TIINGO_D1_SEQUENCE_BREADTH_ID,
        "mode": mode,
        "status": "precommitted",
        "source": {
            "dataset_id": snapshot.snapshot.dataset_id,
            "dataset_hash": snapshot.snapshot.dataset_hash,
            "manifest_hash": snapshot.snapshot.manifest_hash,
            "provider": "Tiingo standard EOD API",
            "retrospective_research_only": True,
            "point_in_time_eligible": False,
            "paper_input_eligible": False,
        },
        "config": config.safe_payload(),
        "candidate_selection_allowed": False,
        "ensemble_allowed": False,
        "paper_input_allowed": False,
        "promotion_allowed": False,
        "raw_market_data_written": False,
    }
    if cpu_summary is not None:
        payload["cpu_precommit_hash"] = cpu_summary["precommit_hash"]
        payload["cpu_input_hash"] = _required_text(cpu_summary.get("input_hash"), "cpu input hash")
    precommit_hash = _sha256_payload(payload)
    path = output_dir / "precommit.json"
    _write_json_new(path, {**payload, "precommit_hash": precommit_hash})
    return path, precommit_hash


def _load_cpu_summary(path: Path) -> Mapping[str, object]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("Tiingo D1 sequence CPU summary is unavailable") from error
    if not isinstance(payload, dict):
        raise ValueError("Tiingo D1 sequence CPU summary is invalid")
    if (
        payload.get("campaign_id") != TIINGO_D1_SEQUENCE_BREADTH_ID
        or payload.get("mode") != "cpu"
        or payload.get("status") != "completed_descriptive_only"
        or not _is_sha256(_required_text(payload.get("precommit_hash"), "cpu precommit hash"))
        or not _is_sha256(_required_text(payload.get("input_hash"), "cpu input hash"))
    ):
        raise ValueError("Tiingo D1 sequence CPU summary is invalid")
    return MappingProxyType(dict(payload))


def _verify_cpu_eligibility(
    cpu_summary: Mapping[str, object],
    sequence_input: TiingoD1SequenceInput,
) -> None:
    if cpu_summary["input_hash"] != sequence_input.input_hash:
        raise ValueError("Tiingo D1 sequence CPU input identity does not match")
    eligibility = cpu_summary.get("gpu_eligibility")
    if not isinstance(eligibility, dict) or eligibility.get("eligible") is not True:
        raise ValueError("Tiingo D1 sequence GPU eligibility is not satisfied")


def _validate_cuda_breadth(breadth: Mapping[str, object]) -> None:
    models = breadth.get("models")
    expected_pairs = {
        (architecture_id, length)
        for architecture_id in TIINGO_D1_SEQUENCE_GPU_ARCHITECTURES
        for length in TIINGO_D1_SEQUENCE_LENGTHS
    }
    if (
        breadth.get("backend") != "torch_cuda"
        or not isinstance(models, list)
        or breadth.get("candidate_selection_allowed") is not False
        or breadth.get("ensemble_allowed") is not False
        or breadth.get("promotion_allowed") is not False
    ):
        raise ValueError("Tiingo D1 sequence CUDA breadth result is invalid")
    actual_pairs: set[tuple[object, object]] = set()
    for model in models:
        if not isinstance(model, Mapping):
            raise ValueError("Tiingo D1 sequence CUDA breadth model is invalid")
        validation_cells = model.get("validation_cells")
        if (
            model.get("checkpoint_written") is not False
            or not isinstance(validation_cells, list)
            or tuple(
                cell.get("symbol") if isinstance(cell, Mapping) else None
                for cell in validation_cells
            )
            != TIINGO_ETF_D1_SYMBOLS
        ):
            raise ValueError("Tiingo D1 sequence CUDA breadth model is invalid")
        actual_pairs.add((model.get("architecture_id"), model.get("sequence_length")))
    if actual_pairs != expected_pairs or len(models) != len(expected_pairs):
        raise ValueError("Tiingo D1 sequence CUDA breadth result is invalid")


def _write_incomplete(
    output_dir: Path,
    precommit_hash: str,
    *,
    mode: Mode,
    error: Exception,
) -> None:
    _write_json_new(
        output_dir / "incomplete.json",
        {
            "schema_version": SCHEMA_VERSION,
            "campaign_id": TIINGO_D1_SEQUENCE_BREADTH_ID,
            "mode": mode,
            "status": "incomplete",
            "precommit_hash": precommit_hash,
            "failure_class": type(error).__name__,
            "candidate_selection_allowed": False,
            "ensemble_allowed": False,
            "promotion_allowed": False,
            "raw_market_data_written": False,
        },
    )


def _validate_snapshot_rows(snapshot: LoadedTiingoEtfDailySnapshot) -> None:
    if tuple(snapshot.rows_by_symbol) != TIINGO_ETF_D1_SYMBOLS:
        raise ValueError("Tiingo D1 sequence snapshot symbols are invalid")
    for symbol in TIINGO_ETF_D1_SYMBOLS:
        previous = None
        for row in snapshot.rows_by_symbol[symbol]:
            if row.symbol != symbol or (previous is not None and row.session_date <= previous):
                raise ValueError("Tiingo D1 sequence snapshot chronology is invalid")
            previous = row.session_date


def _sample_identity_material(samples: Sequence[_SequenceSample]) -> list[object]:
    return [
        {
            "dependency": [sample.dependency_start_index, sample.dependency_end_index],
        }
        for sample in samples
    ]


def _write_json_new(path: Path, payload: Mapping[str, object]) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except OSError as error:
        raise RuntimeError("Tiingo D1 sequence artifact write failed") from error


def _is_sha256(value: str) -> bool:
    return (
        len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _sha256_payload(payload: object) -> str:
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _cell_key(symbol: str, length: int) -> str:
    return f"{symbol}-L{length}"


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _float_text(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError("Tiingo D1 sequence value is not finite")
    return format(value, ".12g")


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"Tiingo D1 sequence {label} is invalid")
    return value


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return math.fsum(value * other for value, other in zip(left, right, strict=True))


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1 / (1 + math.exp(-value))
    exp_value = math.exp(value)
    return exp_value / (1 + exp_value)
