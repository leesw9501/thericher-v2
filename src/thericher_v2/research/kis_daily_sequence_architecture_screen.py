"""Bounded offline daily sequence breadth screen for the KIS QQQ/SPY panel.

The module deliberately owns only a development-only architecture comparison.
It does not rank candidates, form an ensemble, submit a broker order, or read
credentials. The actual Data loader remains responsible for re-attesting the
private cache before this screen receives it.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, Bar, ModelPrediction, Signal, Timeframe
from thericher_v2.data.kis_paper_daily import (
    KIS_PAPER_PRIVATE_DAILY_ADJUSTMENT_MODE,
    KIS_PAPER_PRIVATE_DAILY_CATALOG_ID,
    KisPaperPrivateDailyCatalog,
    slice_kis_paper_private_daily_catalog,
)
from thericher_v2.execution import LOCAL_PAPER_SOURCE

from .campaign import (
    CampaignContract,
    CampaignCosts,
    CampaignFold,
    CampaignWindow,
    CatalogDatasetRef,
    ExecutableTarget,
)
from .historical_kis_campaign import HISTORICAL_KIS_DAILY_TARGET_KEYS
from .sequence_architecture_models import SequenceArchitectureId, build_torch_sequence_model
from .validation import CampaignReplayRun, run_campaign_model_replay

KIS_DAILY_SEQUENCE_ARCHITECTURE_SCREEN_ID = "kis-daily-sequence-architecture-screen-v1"
KIS_DAILY_SEQUENCE_SYMBOLS = ("QQQ", "SPY")
KIS_DAILY_SEQUENCE_FEATURE_NAMES = (
    "qqq_completed_close_return",
    "spy_completed_close_return",
    "qqq_minus_spy_completed_close_return",
)
KIS_DAILY_SEQUENCE_LENGTH = 20
KIS_DAILY_SEQUENCE_PURGE_SESSIONS = KIS_DAILY_SEQUENCE_LENGTH + 2
KIS_DAILY_SEQUENCE_VALIDATION_DIVISOR = 5
KIS_DAILY_SEQUENCE_MIN_DEVELOPMENT_SESSIONS = 60
KIS_DAILY_SEQUENCE_MIN_VALIDATION_SESSIONS = 60
KIS_DAILY_SEQUENCE_DECISION_STRIDE = 2
KIS_DAILY_SEQUENCE_HIDDEN_SIZE = 16
KIS_DAILY_SEQUENCE_ATTENTION_HEADS = 4
KIS_DAILY_SEQUENCE_TCN_KERNEL_SIZE = 3
KIS_DAILY_SEQUENCE_LEARNING_RATE = 0.001
KIS_DAILY_SEQUENCE_DECISION_THRESHOLD = 0.5
KIS_DAILY_SEQUENCE_CPU_EPOCHS = 1
KIS_DAILY_SEQUENCE_CUDA_EPOCHS = 8
KIS_DAILY_SEQUENCE_CPU_MAX_SECONDS = 90
KIS_DAILY_SEQUENCE_CUDA_MAX_SECONDS = 180
KIS_DAILY_SEQUENCE_FOLD_ID = "chronological-validation"
KIS_DAILY_SEQUENCE_EXPECTED_INDEX_HASH = (
    "sha256:e0bb847994a97b1df1181b0013fabcb784d979c7c366f686940e563cb01ac660"
)
KIS_DAILY_SEQUENCE_EXPECTED_FULL_DATASET_HASH = (
    "sha256:78b00556ddbc8bcfb0c4d1bb67e004e4a4c4ff035a8c348b2516b842fa397718"
)
KIS_DAILY_SEQUENCE_ARCHITECTURES: tuple[SequenceArchitectureId, ...] = (
    "lstm",
    "causal_tcn",
    "compact_attention",
)

DailySequenceMode = Literal["cpu-smoke", "cuda-screen"]
SequenceRow = tuple[float, float, float]
SequenceFeatures = tuple[SequenceRow, ...]
SequenceBatch = tuple[SequenceFeatures, ...]


@dataclass(frozen=True)
class KisDailySequenceArchitectureSpec:
    """A fixed, compact architecture chosen before validation materializes."""

    architecture_id: SequenceArchitectureId
    seed: int
    hidden_size: int = KIS_DAILY_SEQUENCE_HIDDEN_SIZE
    attention_heads: int = KIS_DAILY_SEQUENCE_ATTENTION_HEADS
    tcn_kernel_size: int = KIS_DAILY_SEQUENCE_TCN_KERNEL_SIZE
    learning_rate: float = KIS_DAILY_SEQUENCE_LEARNING_RATE
    decision_threshold: float = KIS_DAILY_SEQUENCE_DECISION_THRESHOLD
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.architecture_id not in KIS_DAILY_SEQUENCE_ARCHITECTURES:
            raise ValueError("KIS daily sequence architecture is invalid")
        if (
            self.hidden_size != KIS_DAILY_SEQUENCE_HIDDEN_SIZE
            or self.attention_heads != KIS_DAILY_SEQUENCE_ATTENTION_HEADS
            or self.tcn_kernel_size != KIS_DAILY_SEQUENCE_TCN_KERNEL_SIZE
            or self.learning_rate != KIS_DAILY_SEQUENCE_LEARNING_RATE
            or self.decision_threshold != KIS_DAILY_SEQUENCE_DECISION_THRESHOLD
            or self.hidden_size % self.attention_heads != 0
            or self.seed < 0
        ):
            raise ValueError("KIS daily sequence architecture hyperparameters are frozen")

    def to_payload(self) -> dict[str, object]:
        return {
            "architecture_id": self.architecture_id,
            "seed": self.seed,
            "hidden_size": self.hidden_size,
            "attention_heads": self.attention_heads,
            "tcn_kernel_size": self.tcn_kernel_size,
            "learning_rate": self.learning_rate,
            "decision_threshold": self.decision_threshold,
            "training_scope": "pooled_qqq_spy_development_only",
        }


KIS_DAILY_SEQUENCE_ARCHITECTURE_SPECS = (
    KisDailySequenceArchitectureSpec(architecture_id="lstm", seed=211),
    KisDailySequenceArchitectureSpec(architecture_id="causal_tcn", seed=223),
    KisDailySequenceArchitectureSpec(architecture_id="compact_attention", seed=227),
)


@dataclass(frozen=True)
class KisDailySequenceSample:
    """One completed-bar-only model input and optional development label."""

    symbol: str
    history_start: datetime
    decision_start: datetime
    decision_end: datetime
    entry_start: datetime
    exit_start: datetime
    features: SequenceFeatures
    label: int | None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "features", tuple(tuple(row) for row in self.features))
        if self.symbol not in KIS_DAILY_SEQUENCE_SYMBOLS:
            raise ValueError("KIS daily sequence sample symbol is invalid")
        if self.label not in {None, 0, 1}:
            raise ValueError("KIS daily sequence sample label is invalid")
        if (
            len(self.features) != KIS_DAILY_SEQUENCE_LENGTH
            or any(len(row) != len(KIS_DAILY_SEQUENCE_FEATURE_NAMES) for row in self.features)
            or any(not math.isfinite(value) for row in self.features for value in row)
            or not (
                self.history_start <= self.decision_start
                and self.decision_start < self.decision_end
                and self.decision_end <= self.entry_start < self.exit_start
            )
        ):
            raise ValueError("KIS daily sequence sample timing or geometry is invalid")


@dataclass(frozen=True)
class KisDailySequenceStandardizer:
    """Development-only per-feature standardization for one frozen fold."""

    means: SequenceRow
    scales: SequenceRow
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "means", tuple(self.means))
        object.__setattr__(self, "scales", tuple(self.scales))
        if (
            len(self.means) != len(KIS_DAILY_SEQUENCE_FEATURE_NAMES)
            or len(self.scales) != len(KIS_DAILY_SEQUENCE_FEATURE_NAMES)
            or any(not math.isfinite(value) for value in (*self.means, *self.scales))
            or any(value <= 0 for value in self.scales)
        ):
            raise ValueError("KIS daily sequence standardizer is invalid")

    @property
    def standardizer_hash(self) -> str:
        return _sha256_payload(
            {
                "feature_names": list(KIS_DAILY_SEQUENCE_FEATURE_NAMES),
                "means": [format(value, ".17g") for value in self.means],
                "scales": [format(value, ".17g") for value in self.scales],
            }
        )

    def transform(self, features: SequenceFeatures) -> SequenceFeatures:
        return tuple(
            tuple(
                (value - self.means[index]) / self.scales[index]
                for index, value in enumerate(row)
            )
            for row in features
        )


@dataclass(frozen=True)
class KisDailySequenceSplit:
    development: CampaignWindow
    purge: CampaignWindow
    validation: CampaignWindow
    development_session_count: int
    purge_session_count: int
    validation_session_count: int
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            min(
                self.development_session_count,
                self.purge_session_count,
                self.validation_session_count,
            )
            <= 0
            or self.development.end_utc > self.purge.start_utc
            or self.purge.end_utc > self.validation.start_utc
            or self.purge_session_count != KIS_DAILY_SEQUENCE_PURGE_SESSIONS
        ):
            raise ValueError("KIS daily sequence chronological split is invalid")

    def to_payload(self) -> dict[str, object]:
        return {
            "development": _window_payload(self.development),
            "purge": _window_payload(self.purge),
            "validation": _window_payload(self.validation),
            "development_session_count": self.development_session_count,
            "purge_session_count": self.purge_session_count,
            "validation_session_count": self.validation_session_count,
            "validation_feature_window_rule": "entire_20_session_window_inside_validation",
        }


@dataclass(frozen=True)
class KisDailySequenceScreenInput:
    """Source-separated, phase-bounded tensors and replay contract."""

    catalog: KisPaperPrivateDailyCatalog
    campaign: CampaignContract
    split: KisDailySequenceSplit
    development_catalog: KisPaperPrivateDailyCatalog
    validation_catalog: KisPaperPrivateDailyCatalog
    development_samples: tuple[KisDailySequenceSample, ...]
    validation_samples_by_symbol: Mapping[str, tuple[KisDailySequenceSample, ...]]
    standardizer: KisDailySequenceStandardizer
    development_input_hash: str
    validation_input_hash: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "development_samples", tuple(self.development_samples))
        normalized_validation = {
            symbol: tuple(samples)
            for symbol, samples in self.validation_samples_by_symbol.items()
        }
        object.__setattr__(
            self,
            "validation_samples_by_symbol",
            MappingProxyType(normalized_validation),
        )
        if (
            tuple(self.catalog.bars_by_symbol) != KIS_DAILY_SEQUENCE_SYMBOLS
            or tuple(self.validation_samples_by_symbol) != KIS_DAILY_SEQUENCE_SYMBOLS
            or not self.development_samples
            or any(not samples for samples in self.validation_samples_by_symbol.values())
            or any(sample.label is None for sample in self.development_samples)
            or any(
                sample.label is not None
                for samples in self.validation_samples_by_symbol.values()
                for sample in samples
            )
        ):
            raise ValueError("KIS daily sequence screen input is incomplete")
        self.campaign.verify_cataloged_dataset(
            dataset_id=self.catalog.dataset_id,
            dataset_hash=self.catalog.dataset_hash,
        )


@dataclass(frozen=True)
class KisDailyTrainedSequenceArchitecture:
    spec: KisDailySequenceArchitectureSpec
    training: Mapping[str, object]
    probabilities_by_symbol: Mapping[str, tuple[float, ...]]
    checkpoint_path: Path
    checkpoint_sha256: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "probabilities_by_symbol",
            MappingProxyType(
                {
                    symbol: tuple(values)
                    for symbol, values in self.probabilities_by_symbol.items()
                }
            ),
        )
        object.__setattr__(self, "checkpoint_path", Path(self.checkpoint_path).resolve())
        if (
            tuple(self.probabilities_by_symbol) != KIS_DAILY_SEQUENCE_SYMBOLS
            or not self.checkpoint_sha256.startswith("sha256:")
            or len(self.checkpoint_sha256) != 71
        ):
            raise ValueError("KIS daily trained sequence architecture is invalid")


@dataclass(frozen=True)
class KisDailySequenceArchitectureReplayCell:
    architecture_id: SequenceArchitectureId
    symbol: str
    prediction_hash: str
    replay: CampaignReplayRun
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.architecture_id not in KIS_DAILY_SEQUENCE_ARCHITECTURES
            or self.symbol not in KIS_DAILY_SEQUENCE_SYMBOLS
            or self.replay.fill_source != LOCAL_PAPER_SOURCE
            or self.replay.replay_evidence.fill_source != LOCAL_PAPER_SOURCE
        ):
            raise ValueError("KIS daily sequence replay cell requires local-paper evidence")


@dataclass(frozen=True)
class KisDailySequenceArchitectureScreenRun:
    screen_input: KisDailySequenceScreenInput
    mode: DailySequenceMode
    precommit_path: Path
    precommit_hash: str
    trained_architectures: tuple[KisDailyTrainedSequenceArchitecture, ...]
    replay_cells: tuple[KisDailySequenceArchitectureReplayCell, ...]
    summary_path: Path
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "trained_architectures", tuple(self.trained_architectures))
        object.__setattr__(self, "replay_cells", tuple(self.replay_cells))
        expected_cells = tuple(
            (spec.architecture_id, symbol)
            for spec in KIS_DAILY_SEQUENCE_ARCHITECTURE_SPECS
            for symbol in KIS_DAILY_SEQUENCE_SYMBOLS
        )
        if (
            self.mode not in {"cpu-smoke", "cuda-screen"}
            or tuple(item.spec for item in self.trained_architectures)
            != KIS_DAILY_SEQUENCE_ARCHITECTURE_SPECS
            or tuple((cell.architecture_id, cell.symbol) for cell in self.replay_cells)
            != expected_cells
        ):
            raise ValueError("KIS daily sequence screen did not complete the fixed breadth plan")


DailySequenceArchitectureTrainer = Callable[
    [
        KisDailySequenceScreenInput,
        KisDailySequenceArchitectureSpec,
        DailySequenceMode,
        Path,
    ],
    KisDailyTrainedSequenceArchitecture,
]


def build_kis_daily_sequence_screen_input(
    catalog: KisPaperPrivateDailyCatalog,
) -> KisDailySequenceScreenInput:
    """Freeze causal QQQ/SPY daily tensors without reading a later holdout."""

    _validate_daily_catalog(catalog)
    split = _build_daily_split(catalog)
    development_catalog = slice_kis_paper_private_daily_catalog(
        catalog,
        start_index=0,
        stop_index=split.development_session_count,
    )
    validation_start = split.development_session_count + split.purge_session_count
    validation_catalog = slice_kis_paper_private_daily_catalog(
        catalog,
        start_index=validation_start,
        stop_index=len(catalog.common_sessions),
    )
    campaign = _build_campaign(catalog, split=split)
    development_raw = _build_phase_samples(
        development_catalog,
        include_labels=True,
        decision_stride=1,
        costs=campaign.costs,
    )
    standardizer = _fit_development_standardizer(development_raw)
    development_samples = tuple(
        _standardize_sample(sample, standardizer) for sample in development_raw
    )
    validation_raw = _build_phase_samples(
        validation_catalog,
        include_labels=False,
        decision_stride=KIS_DAILY_SEQUENCE_DECISION_STRIDE,
        costs=campaign.costs,
    )
    validation_samples_by_symbol = {
        symbol: tuple(
            _standardize_sample(sample, standardizer)
            for sample in validation_raw
            if sample.symbol == symbol
        )
        for symbol in KIS_DAILY_SEQUENCE_SYMBOLS
    }
    return KisDailySequenceScreenInput(
        catalog=catalog,
        campaign=campaign,
        split=split,
        development_catalog=development_catalog,
        validation_catalog=validation_catalog,
        development_samples=development_samples,
        validation_samples_by_symbol=validation_samples_by_symbol,
        standardizer=standardizer,
        development_input_hash=_sample_input_hash(development_samples, include_labels=True),
        validation_input_hash=_validation_input_hash(validation_samples_by_symbol),
    )


def _validate_daily_catalog(catalog: KisPaperPrivateDailyCatalog) -> None:
    if not isinstance(catalog, KisPaperPrivateDailyCatalog):
        raise TypeError("KIS daily sequence screen requires the Data-owned daily catalog")
    if (
        catalog.dataset_id != KIS_PAPER_PRIVATE_DAILY_CATALOG_ID
        or tuple(catalog.bars_by_symbol) != KIS_DAILY_SEQUENCE_SYMBOLS
        or catalog.adjustment_mode != KIS_PAPER_PRIVATE_DAILY_ADJUSTMENT_MODE
        or len(catalog.common_sessions) < (
            KIS_DAILY_SEQUENCE_MIN_DEVELOPMENT_SESSIONS
            + KIS_DAILY_SEQUENCE_PURGE_SESSIONS
            + KIS_DAILY_SEQUENCE_MIN_VALIDATION_SESSIONS
        )
        or not catalog.raw_price_limitations
    ):
        raise ValueError("KIS daily sequence screen source contract is invalid")
    for symbol in KIS_DAILY_SEQUENCE_SYMBOLS:
        stream = catalog.bars_by_symbol[symbol]
        if (
            stream.dataset_id != catalog.dataset_id
            or stream.dataset_hash != catalog.dataset_hash
            or len(stream.bars) != len(catalog.common_sessions)
            or any(
                bar.symbol != symbol
                or bar.market != "US"
                or bar.timeframe != Timeframe.D1
                or not bar.complete
                for bar in stream.bars
            )
            or tuple(bar.start_ts.date() for bar in stream.bars) != catalog.common_sessions
        ):
            raise ValueError("KIS daily sequence source streams are incompatible")


def _build_daily_split(catalog: KisPaperPrivateDailyCatalog) -> KisDailySequenceSplit:
    total = len(catalog.common_sessions)
    validation_count = max(
        KIS_DAILY_SEQUENCE_MIN_VALIDATION_SESSIONS,
        total // KIS_DAILY_SEQUENCE_VALIDATION_DIVISOR,
    )
    development_count = total - KIS_DAILY_SEQUENCE_PURGE_SESSIONS - validation_count
    if development_count < KIS_DAILY_SEQUENCE_MIN_DEVELOPMENT_SESSIONS:
        raise ValueError("KIS daily sequence source leaves too little development history")
    bars = catalog.bars_by_symbol["QQQ"].bars
    validation_start = development_count + KIS_DAILY_SEQUENCE_PURGE_SESSIONS
    return KisDailySequenceSplit(
        development=CampaignWindow(bars[0].start_ts, bars[development_count - 1].end_ts),
        purge=CampaignWindow(
            bars[development_count].start_ts,
            bars[validation_start - 1].end_ts,
        ),
        validation=CampaignWindow(bars[validation_start].start_ts, bars[-1].end_ts),
        development_session_count=development_count,
        purge_session_count=KIS_DAILY_SEQUENCE_PURGE_SESSIONS,
        validation_session_count=validation_count,
    )


def _build_campaign(
    catalog: KisPaperPrivateDailyCatalog,
    *,
    split: KisDailySequenceSplit,
) -> CampaignContract:
    gap = split.validation.start_utc - split.development.end_utc
    return CampaignContract(
        campaign_id=KIS_DAILY_SEQUENCE_ARCHITECTURE_SCREEN_ID,
        catalog=CatalogDatasetRef(
            catalog_id="kis-private-daily-qqq-spy-sequence-v1",
            dataset_id=catalog.dataset_id,
            dataset_hash=catalog.dataset_hash,
            constructed_as_of_utc=catalog.bars_by_symbol["QQQ"].bars[-1].end_ts,
            ranking_eligible=False,
            sealed_holdout_eligible=False,
        ),
        timeframe=Timeframe.D1,
        folds=(CampaignFold(KIS_DAILY_SEQUENCE_FOLD_ID, split.development, split.validation),),
        target=ExecutableTarget(),
        costs=CampaignCosts(
            fee_bps=Decimal("1"),
            slippage_bps=Decimal("2"),
            slippage_source_id="kis-daily-sequence-fixed-local-paper-cost-v1",
        ),
        purge=gap,
        embargo=gap,
        evidence_use="development",
        sealed_holdout=None,
        metrics=(
            "after_cost_pnl",
            "gross_pnl",
            "fee_cost",
            "slippage_cost",
            "trade_count",
            "decision_count",
        ),
        deterministic_seed=211,
    )


def _build_phase_samples(
    catalog: KisPaperPrivateDailyCatalog,
    *,
    include_labels: bool,
    decision_stride: int,
    costs: CampaignCosts,
) -> tuple[KisDailySequenceSample, ...]:
    if decision_stride < 1:
        raise ValueError("KIS daily sequence decision stride is invalid")
    qqq_bars = catalog.bars_by_symbol["QQQ"].bars
    spy_bars = catalog.bars_by_symbol["SPY"].bars
    final_decision_index = len(qqq_bars) - ExecutableTarget().exit_bar_offset
    samples: list[KisDailySequenceSample] = []
    for decision_index in range(
        KIS_DAILY_SEQUENCE_LENGTH,
        final_decision_index,
        decision_stride,
    ):
        rows = _feature_rows(
            qqq_bars=qqq_bars,
            spy_bars=spy_bars,
            decision_index=decision_index,
        )
        for symbol, bars in (("QQQ", qqq_bars), ("SPY", spy_bars)):
            decision_bar = bars[decision_index]
            entry_bar = bars[decision_index + 1]
            exit_bar = bars[decision_index + 2]
            samples.append(
                KisDailySequenceSample(
                    symbol=symbol,
                    history_start=bars[decision_index - KIS_DAILY_SEQUENCE_LENGTH + 1].start_ts,
                    decision_start=decision_bar.start_ts,
                    decision_end=decision_bar.end_ts,
                    entry_start=entry_bar.start_ts,
                    exit_start=exit_bar.start_ts,
                    features=rows,
                    label=(
                        _after_cost_label(entry_bar=entry_bar, exit_bar=exit_bar, costs=costs)
                        if include_labels
                        else None
                    ),
                )
            )
    if not samples:
        raise ValueError("KIS daily sequence phase has no eligible completed-bar samples")
    return tuple(samples)


def _feature_rows(
    *,
    qqq_bars: Sequence[Bar],
    spy_bars: Sequence[Bar],
    decision_index: int,
) -> SequenceFeatures:
    start_index = decision_index - KIS_DAILY_SEQUENCE_LENGTH + 1
    if start_index < 1:
        raise ValueError("KIS daily sequence feature window requires a prior completed close")
    rows: list[SequenceRow] = []
    for index in range(start_index, decision_index + 1):
        qqq_return = _completed_close_return(qqq_bars[index], qqq_bars[index - 1])
        spy_return = _completed_close_return(spy_bars[index], spy_bars[index - 1])
        row = (qqq_return, spy_return, qqq_return - spy_return)
        if any(not math.isfinite(value) for value in row):
            raise ValueError("KIS daily sequence feature values are invalid")
        rows.append(row)
    return tuple(rows)


def _completed_close_return(current: Bar, prior: Bar) -> float:
    if (
        current.end_ts <= prior.end_ts
        or current.close <= 0
        or prior.close <= 0
        or not current.complete
        or not prior.complete
    ):
        raise ValueError("KIS daily sequence completed close return is invalid")
    return float(current.close / prior.close - 1)


def _after_cost_label(
    *,
    entry_bar: Bar,
    exit_bar: Bar,
    costs: CampaignCosts,
) -> int:
    """Mirror the local-paper next-open fill arithmetic without broker side effects."""

    if (
        entry_bar.start_ts.date() >= exit_bar.start_ts.date()
        or entry_bar.open <= 0
        or exit_bar.open <= 0
    ):
        raise ValueError("KIS daily sequence target requires later observed daily opens")
    scale = Decimal("10000")
    quantum = Decimal("0.0001")
    entry_price = (entry_bar.open * (Decimal("1") + costs.slippage_bps / scale)).quantize(
        quantum
    )
    exit_price = (exit_bar.open * (Decimal("1") - costs.slippage_bps / scale)).quantize(
        quantum
    )
    entry_fee = (entry_price * costs.fee_bps / scale).quantize(quantum)
    exit_fee = (exit_price * costs.fee_bps / scale).quantize(quantum)
    return int(exit_price - exit_fee > entry_price + entry_fee)


def _fit_development_standardizer(
    samples: Sequence[KisDailySequenceSample],
) -> KisDailySequenceStandardizer:
    if not samples or any(sample.label is None for sample in samples):
        raise ValueError("KIS daily standardizer requires development-only labeled samples")
    rows = [row for sample in samples for row in sample.features]
    count = len(rows)
    means = tuple(sum(row[index] for row in rows) / count for index in range(len(rows[0])))
    scales: list[float] = []
    for index, mean in enumerate(means):
        variance = sum((row[index] - mean) ** 2 for row in rows) / count
        scales.append(max(math.sqrt(variance), 1e-12))
    return KisDailySequenceStandardizer(means=means, scales=tuple(scales))


def _standardize_sample(
    sample: KisDailySequenceSample,
    standardizer: KisDailySequenceStandardizer,
) -> KisDailySequenceSample:
    return KisDailySequenceSample(
        symbol=sample.symbol,
        history_start=sample.history_start,
        decision_start=sample.decision_start,
        decision_end=sample.decision_end,
        entry_start=sample.entry_start,
        exit_start=sample.exit_start,
        features=standardizer.transform(sample.features),
        label=sample.label,
    )


def _sample_input_hash(
    samples: Sequence[KisDailySequenceSample],
    *,
    include_labels: bool,
) -> str:
    return _sha256_payload(
        {
            "feature_names": list(KIS_DAILY_SEQUENCE_FEATURE_NAMES),
            "sequence_length": KIS_DAILY_SEQUENCE_LENGTH,
            "samples": [
                {
                    "symbol": sample.symbol,
                    "history_start": sample.history_start.isoformat(),
                    "decision_end": sample.decision_end.isoformat(),
                    "entry_start": sample.entry_start.isoformat(),
                    "exit_start": sample.exit_start.isoformat(),
                    "features": [
                        [format(value, ".17g") for value in row] for row in sample.features
                    ],
                    "label": sample.label if include_labels else None,
                }
                for sample in samples
            ],
        }
    )


def _validation_input_hash(
    samples_by_symbol: Mapping[str, Sequence[KisDailySequenceSample]],
) -> str:
    return _sha256_payload(
        {
            "symbols": list(KIS_DAILY_SEQUENCE_SYMBOLS),
            "inputs": {
                symbol: _sample_input_hash(samples, include_labels=False)
                for symbol, samples in samples_by_symbol.items()
            },
        }
    )


def _window_payload(window: CampaignWindow) -> dict[str, str]:
    return {"start_utc": window.start_utc.isoformat(), "end_utc": window.end_utc.isoformat()}


def _sha256_payload(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def run_kis_daily_sequence_architecture_screen(
    catalog: KisPaperPrivateDailyCatalog,
    *,
    artifact_root: Path,
    run_label: str,
    mode: DailySequenceMode,
    repo_root: Path | None = None,
    trainer: DailySequenceArchitectureTrainer | None = None,
) -> KisDailySequenceArchitectureScreenRun:
    """Run one precommitted CPU smoke or CUDA breadth screen offline.

    The validation phase is evaluated only after all architecture specifications
    and the development input are written to the immutable precommit artifact.
    No result is interpreted as a winner or fed into a later promotion path.
    """

    _validate_run_label(run_label)
    if mode not in {"cpu-smoke", "cuda-screen"}:
        raise ValueError("KIS daily sequence screen mode is invalid")
    resolved_repo_root = (repo_root or Path.cwd()).resolve()
    resolved_artifact_root = Path(artifact_root).resolve()
    _reject_repo_path(resolved_artifact_root, repo_root=resolved_repo_root)
    output_dir = (
        resolved_artifact_root / KIS_DAILY_SEQUENCE_ARCHITECTURE_SCREEN_ID / run_label
    )
    if output_dir.exists():
        raise FileExistsError("KIS daily sequence screen artifact already exists")

    screen_input = build_kis_daily_sequence_screen_input(catalog)
    output_dir.mkdir(parents=True, exist_ok=False)
    checkpoint_dir = output_dir / "checkpoints"
    checkpoint_dir.mkdir()
    precommit_payload = _precommit_payload(screen_input=screen_input, mode=mode)
    precommit_hash = _sha256_payload(precommit_payload)
    precommit_payload["precommit_hash"] = precommit_hash
    precommit_path = output_dir / "precommit.json"
    _write_json_new(precommit_path, precommit_payload)

    try:
        selected_trainer = trainer or _train_torch_sequence_architecture
        trained = tuple(
            selected_trainer(screen_input, spec, mode, checkpoint_dir)
            for spec in KIS_DAILY_SEQUENCE_ARCHITECTURE_SPECS
        )
        _validate_trained_architectures(
            trained,
            screen_input=screen_input,
            mode=mode,
            checkpoint_dir=checkpoint_dir,
        )
        replay_cells = _run_validation_replays(
            screen_input=screen_input,
            trained=trained,
            precommit_hash=precommit_hash,
            artifact_root=resolved_artifact_root,
            output_dir=output_dir,
            repo_root=resolved_repo_root,
            run_label=run_label,
        )
    except Exception as error:
        _write_json_new(
            output_dir / "incomplete.json",
            {
                "schema_version": SCHEMA_VERSION,
                "status": "incomplete",
                "mode": mode,
                "screen_id": KIS_DAILY_SEQUENCE_ARCHITECTURE_SCREEN_ID,
                "precommit_hash": precommit_hash,
                "failure_class": type(error).__name__,
                "selection_allowed": False,
                "ensemble_allowed": False,
                "raw_market_data_written": False,
            },
        )
        raise

    summary_path = output_dir / "summary.json"
    _write_json_new(
        summary_path,
        _summary_payload(
            screen_input=screen_input,
            mode=mode,
            precommit_hash=precommit_hash,
            trained=trained,
            replay_cells=replay_cells,
        ),
    )
    return KisDailySequenceArchitectureScreenRun(
        screen_input=screen_input,
        mode=mode,
        precommit_path=precommit_path,
        precommit_hash=precommit_hash,
        trained_architectures=trained,
        replay_cells=replay_cells,
        summary_path=summary_path,
    )


def _precommit_payload(
    *,
    screen_input: KisDailySequenceScreenInput,
    mode: DailySequenceMode,
) -> dict[str, object]:
    epochs, max_seconds = _mode_budget(mode)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "precommitted",
        "screen_id": KIS_DAILY_SEQUENCE_ARCHITECTURE_SCREEN_ID,
        "mode": mode,
        "claim": (
            "fixed multi-architecture descriptive development-only comparison; no winner, "
            "selection, ensemble, promotion, profitability claim, or paper-order decision"
        ),
        "source": {
            "loader": "load_kis_paper_private_daily_catalog",
            "dataset_id": screen_input.catalog.dataset_id,
            "dataset_hash": screen_input.catalog.dataset_hash,
            "index_hash": screen_input.catalog.index_hash,
            "target_keys": list(HISTORICAL_KIS_DAILY_TARGET_KEYS),
            "symbols": list(KIS_DAILY_SEQUENCE_SYMBOLS),
            "adjustment_mode": screen_input.catalog.adjustment_mode,
            "limitations": list(screen_input.catalog.raw_price_limitations),
            "source_mixing_allowed": False,
        },
        "campaign_contract_hash": screen_input.campaign.contract_hash,
        "chronological_split": screen_input.split.to_payload(),
        "features": {
            "names": list(KIS_DAILY_SEQUENCE_FEATURE_NAMES),
            "available_at": "completed_daily_bar_end",
            "sequence_length": KIS_DAILY_SEQUENCE_LENGTH,
            "validation_window_crosses_purge": False,
            "standardizer_fit": "pooled_qqq_spy_development_only",
            "standardizer_hash": screen_input.standardizer.standardizer_hash,
        },
        "target": {
            "decision": "completed_daily_bar_close",
            "entry": "next_observed_daily_open",
            "exit": "following_observed_daily_open",
            "position_side": "long_only",
            "cost_model": screen_input.campaign.to_payload()["costs"],
            "replay_fill_source": LOCAL_PAPER_SOURCE,
            "non_overlapping_decision_stride_sessions": KIS_DAILY_SEQUENCE_DECISION_STRIDE,
        },
        "training": {
            "development_input_hash": screen_input.development_input_hash,
            "development_sample_count": len(screen_input.development_samples),
            "epochs_per_architecture": epochs,
            "max_seconds_per_architecture": max_seconds,
            "stop_rule": "timeout_or_nonfinite_loss_or_nonlocal_paper_replay",
        },
        "validation": {
            "validation_input_hash": screen_input.validation_input_hash,
            "sample_counts": {
                symbol: len(samples)
                for symbol, samples in screen_input.validation_samples_by_symbol.items()
            },
            "labels_materialized": False,
            "tuning_allowed": False,
        },
        "architectures": [
            spec.to_payload() for spec in KIS_DAILY_SEQUENCE_ARCHITECTURE_SPECS
        ],
        "reporting": {
            "all_architectures_and_symbols_reported_jointly": True,
            "winner": None,
            "selection_allowed": False,
            "ensemble_allowed": False,
            "promotion_allowed": False,
        },
        "comparison_materialized": False,
        "sealed_holdout_materialized": False,
        "artifact_policy": {
            "repo_storage_allowed": False,
            "raw_market_data_written": False,
            "checkpoint_root": "external_artifact_root_only",
        },
    }


def _mode_budget(mode: DailySequenceMode) -> tuple[int, int]:
    if mode == "cpu-smoke":
        return KIS_DAILY_SEQUENCE_CPU_EPOCHS, KIS_DAILY_SEQUENCE_CPU_MAX_SECONDS
    if mode == "cuda-screen":
        return KIS_DAILY_SEQUENCE_CUDA_EPOCHS, KIS_DAILY_SEQUENCE_CUDA_MAX_SECONDS
    raise ValueError("KIS daily sequence screen mode is invalid")


def _validate_trained_architectures(
    trained: tuple[KisDailyTrainedSequenceArchitecture, ...],
    *,
    screen_input: KisDailySequenceScreenInput,
    mode: DailySequenceMode,
    checkpoint_dir: Path,
) -> None:
    if len(trained) != len(KIS_DAILY_SEQUENCE_ARCHITECTURE_SPECS):
        raise ValueError("KIS daily sequence screen requires every fixed architecture")
    expected_epochs, _ = _mode_budget(mode)
    for actual, expected in zip(trained, KIS_DAILY_SEQUENCE_ARCHITECTURE_SPECS, strict=True):
        training = actual.training
        if (
            actual.spec != expected
            or training.get("architecture") != expected.architecture_id
            or training.get("mode") != mode
            or training.get("sample_count") != len(screen_input.development_samples)
            or training.get("sequence_length") != KIS_DAILY_SEQUENCE_LENGTH
            or training.get("feature_count") != len(KIS_DAILY_SEQUENCE_FEATURE_NAMES)
            or training.get("epochs") != expected_epochs
            or not actual.checkpoint_path.is_relative_to(checkpoint_dir)
            or not actual.checkpoint_path.is_file()
            or _sha256_file(actual.checkpoint_path) != actual.checkpoint_sha256
        ):
            raise ValueError("KIS daily sequence trainer changed the frozen screen contract")
        for symbol in KIS_DAILY_SEQUENCE_SYMBOLS:
            probabilities = actual.probabilities_by_symbol[symbol]
            if (
                len(probabilities) != len(screen_input.validation_samples_by_symbol[symbol])
                or any(not math.isfinite(value) or not 0 <= value <= 1 for value in probabilities)
            ):
                raise ValueError("KIS daily sequence validation probabilities are invalid")


def _run_validation_replays(
    *,
    screen_input: KisDailySequenceScreenInput,
    trained: tuple[KisDailyTrainedSequenceArchitecture, ...],
    precommit_hash: str,
    artifact_root: Path,
    output_dir: Path,
    repo_root: Path,
    run_label: str,
) -> tuple[KisDailySequenceArchitectureReplayCell, ...]:
    cells: list[KisDailySequenceArchitectureReplayCell] = []
    for trained_architecture in trained:
        for symbol in KIS_DAILY_SEQUENCE_SYMBOLS:
            samples = screen_input.validation_samples_by_symbol[symbol]
            probabilities = trained_architecture.probabilities_by_symbol[symbol]
            probabilities_by_decision_end = dict(
                zip(
                    (sample.decision_end for sample in samples),
                    probabilities,
                    strict=True,
                )
            )
            if len(probabilities_by_decision_end) != len(samples):
                raise ValueError("KIS daily sequence validation decisions must be unique")
            prediction_hash = _sha256_payload(
                {
                    "precommit_hash": precommit_hash,
                    "architecture_id": trained_architecture.spec.architecture_id,
                    "symbol": symbol,
                    "validation_input_hash": screen_input.validation_input_hash,
                    "probabilities": [format(value, ".17g") for value in probabilities],
                }
            )
            model = _KisDailySequenceDecisionModel(
                architecture_id=trained_architecture.spec.architecture_id,
                symbol=symbol,
                samples_by_decision_end={sample.decision_end: sample for sample in samples},
                probabilities_by_decision_end=probabilities_by_decision_end,
                precommit_hash=precommit_hash,
                prediction_hash=prediction_hash,
                threshold=trained_architecture.spec.decision_threshold,
            )
            replay = run_campaign_model_replay(
                screen_input.catalog.bars_by_symbol[symbol],
                campaign=screen_input.campaign,
                model=model,
                run_id=(
                    f"{KIS_DAILY_SEQUENCE_ARCHITECTURE_SCREEN_ID}-"
                    f"{trained_architecture.spec.architecture_id}-{symbol}-{run_label}"
                ),
                artifact_root=artifact_root,
                work_dir=(
                    output_dir
                    / "work"
                    / trained_architecture.spec.architecture_id
                    / symbol
                ),
                phase="validation",
                fold_id=KIS_DAILY_SEQUENCE_FOLD_ID,
                repo_root=repo_root,
                starting_cash=Decimal("10000"),
                quantity=Decimal("1"),
                eligible_signal_starts=frozenset(sample.decision_start for sample in samples),
                emergency_reason="kis_daily_sequence_architecture_screen_validation_only",
            )
            if (
                replay.fill_source != LOCAL_PAPER_SOURCE
                or replay.replay_evidence.fill_source != LOCAL_PAPER_SOURCE
            ):
                raise RuntimeError("KIS daily sequence screen must use local-paper only")
            cells.append(
                KisDailySequenceArchitectureReplayCell(
                    architecture_id=trained_architecture.spec.architecture_id,
                    symbol=symbol,
                    prediction_hash=prediction_hash,
                    replay=replay,
                )
            )
    return tuple(cells)


@dataclass(frozen=True)
class _KisDailySequenceDecisionModel:
    architecture_id: SequenceArchitectureId
    symbol: str
    samples_by_decision_end: Mapping[datetime, KisDailySequenceSample]
    probabilities_by_decision_end: Mapping[datetime, float]
    precommit_hash: str
    prediction_hash: str
    threshold: float
    lookback: int = KIS_DAILY_SEQUENCE_LENGTH

    def __post_init__(self) -> None:
        if (
            self.architecture_id not in KIS_DAILY_SEQUENCE_ARCHITECTURES
            or self.symbol not in KIS_DAILY_SEQUENCE_SYMBOLS
            or not 0 <= self.threshold <= 1
            or set(self.samples_by_decision_end) != set(self.probabilities_by_decision_end)
        ):
            raise ValueError("KIS daily sequence decision model is invalid")

    def predict(self, bars: list[Bar]) -> ModelPrediction:
        if len(bars) < self.lookback:
            raise ValueError("KIS daily sequence model requires 20 completed daily bars")
        latest = bars[-1]
        sample = self.samples_by_decision_end.get(latest.end_ts)
        probability = self.probabilities_by_decision_end.get(latest.end_ts)
        if sample is None or probability is None or latest.symbol != self.symbol:
            raise ValueError("KIS daily sequence model received a non-validation decision")
        tail = tuple(bars[-KIS_DAILY_SEQUENCE_LENGTH:])
        if (
            tail[0].start_ts != sample.history_start
            or tail[-1].start_ts != sample.decision_start
            or tail[-1].end_ts != sample.decision_end
            or any(not bar.complete for bar in tail)
        ):
            raise ValueError("KIS daily sequence replay cannot use future or cross-phase history")
        confidence = Decimal(str(probability))
        action: Literal["buy", "hold"] = "buy" if probability >= self.threshold else "hold"
        signal = Signal(
            symbol=latest.symbol,
            market=latest.market,
            action=action,
            strength=confidence,
            reason=f"kis_daily_sequence_{self.architecture_id}",
            timeframe=Timeframe.D1,
            generated_at=latest.end_ts,
        )
        return ModelPrediction(
            model_id=f"kis_daily_sequence_{self.architecture_id}",
            model_version="1.0.0",
            symbol=latest.symbol,
            market=latest.market,
            signal=signal,
            confidence=confidence,
            expected_edge_bps=Decimal("0"),
            feature_window_end=latest.end_ts,
            metadata={
                "architecture_id": self.architecture_id,
                "decision_rule": "fixed_probability_threshold",
                "threshold": self.threshold,
                "precommit_hash": self.precommit_hash,
                "prediction_hash": self.prediction_hash,
                "validation_only": True,
            },
        )


def _train_torch_sequence_architecture(
    screen_input: KisDailySequenceScreenInput,
    spec: KisDailySequenceArchitectureSpec,
    mode: DailySequenceMode,
    checkpoint_dir: Path,
) -> KisDailyTrainedSequenceArchitecture:
    """Train exactly one development-only architecture on CPU or CUDA."""

    import torch

    epochs, max_seconds = _mode_budget(mode)
    if mode == "cuda-screen" and not torch.cuda.is_available():
        raise RuntimeError("PyTorch CUDA is unavailable")
    device = torch.device("cuda" if mode == "cuda-screen" else "cpu")
    previous_threads = torch.get_num_threads()
    was_deterministic = torch.are_deterministic_algorithms_enabled()
    try:
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)
        torch.manual_seed(spec.seed)
        if mode == "cuda-screen":
            torch.cuda.manual_seed_all(spec.seed)
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False

        features = torch.tensor(
            tuple(sample.features for sample in screen_input.development_samples),
            dtype=torch.float32,
            device=device,
        )
        labels = torch.tensor(
            tuple(int(sample.label) for sample in screen_input.development_samples),
            dtype=torch.float32,
            device=device,
        ).unsqueeze(1)
        model = build_torch_sequence_model(
            torch=torch,
            architecture_id=spec.architecture_id,
            feature_count=len(KIS_DAILY_SEQUENCE_FEATURE_NAMES),
            hidden_size=spec.hidden_size,
            attention_heads=spec.attention_heads,
            tcn_kernel_size=spec.tcn_kernel_size,
        ).to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=spec.learning_rate)
        loss_fn = torch.nn.BCEWithLogitsLoss()

        def loss_value() -> object:
            return loss_fn(model(features), labels)

        initial_loss = float(loss_value().detach().item())
        if not math.isfinite(initial_loss):
            raise RuntimeError("KIS daily sequence initial loss is nonfinite")
        started = time.monotonic()
        model.train()
        for _ in range(epochs):
            optimizer.zero_grad(set_to_none=True)
            loss = loss_value()
            if not math.isfinite(float(loss.detach().item())):
                raise RuntimeError("KIS daily sequence training loss is nonfinite")
            loss.backward()
            optimizer.step()
            if time.monotonic() - started > max_seconds:
                raise TimeoutError(
                    "KIS daily sequence architecture exceeded its fixed compute budget"
                )
        if mode == "cuda-screen":
            torch.cuda.synchronize()
        model.eval()
        final_loss = float(loss_value().detach().item())
        if not math.isfinite(final_loss):
            raise RuntimeError("KIS daily sequence final loss is nonfinite")

        probabilities_by_symbol: dict[str, tuple[float, ...]] = {}
        with torch.no_grad():
            for symbol in KIS_DAILY_SEQUENCE_SYMBOLS:
                sequences = tuple(
                    sample.features for sample in screen_input.validation_samples_by_symbol[symbol]
                )
                tensor = torch.tensor(sequences, dtype=torch.float32, device=device)
                values = torch.sigmoid(model(tensor)).flatten().detach().cpu().tolist()
                probabilities_by_symbol[symbol] = tuple(float(value) for value in values)

        checkpoint_path = checkpoint_dir / f"{spec.architecture_id}.pt"
        torch.save(
            {
                "schema_version": SCHEMA_VERSION,
                "screen_id": KIS_DAILY_SEQUENCE_ARCHITECTURE_SCREEN_ID,
                "mode": mode,
                "architecture": spec.to_payload(),
                "development_input_hash": screen_input.development_input_hash,
                "state_dict": model.state_dict(),
            },
            checkpoint_path,
        )
        return KisDailyTrainedSequenceArchitecture(
            spec=spec,
            training={
                "backend": "torch_cuda" if mode == "cuda-screen" else "torch_cpu",
                "mode": mode,
                "architecture": spec.architecture_id,
                "device": torch.cuda.get_device_name(device) if mode == "cuda-screen" else "cpu",
                "cuda_version": torch.version.cuda if mode == "cuda-screen" else None,
                "sample_count": len(screen_input.development_samples),
                "sequence_length": KIS_DAILY_SEQUENCE_LENGTH,
                "feature_count": len(KIS_DAILY_SEQUENCE_FEATURE_NAMES),
                "hidden_size": spec.hidden_size,
                "attention_heads": spec.attention_heads,
                "tcn_kernel_size": spec.tcn_kernel_size,
                "epochs": epochs,
                "learning_rate": spec.learning_rate,
                "initial_loss": f"{initial_loss:.8f}",
                "final_loss": f"{final_loss:.8f}",
            },
            probabilities_by_symbol=probabilities_by_symbol,
            checkpoint_path=checkpoint_path,
            checkpoint_sha256=_sha256_file(checkpoint_path),
        )
    finally:
        torch.set_num_threads(previous_threads)
        torch.use_deterministic_algorithms(was_deterministic)


def _summary_payload(
    *,
    screen_input: KisDailySequenceScreenInput,
    mode: DailySequenceMode,
    precommit_hash: str,
    trained: tuple[KisDailyTrainedSequenceArchitecture, ...],
    replay_cells: tuple[KisDailySequenceArchitectureReplayCell, ...],
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "complete",
        "mode": "offline_cuda_local_paper" if mode == "cuda-screen" else "offline_cpu_local_paper",
        "claim": (
            "fixed multi-architecture descriptive development-only comparison; no winner, "
            "selection, ensemble, promotion, profitability claim, or paper-order decision"
        ),
        "source": {
            "dataset_id": screen_input.catalog.dataset_id,
            "dataset_hash": screen_input.catalog.dataset_hash,
            "index_hash": screen_input.catalog.index_hash,
            "symbols": list(KIS_DAILY_SEQUENCE_SYMBOLS),
            "adjustment_mode": screen_input.catalog.adjustment_mode,
            "limitations": list(screen_input.catalog.raw_price_limitations),
        },
        "campaign_contract_hash": screen_input.campaign.contract_hash,
        "development_input_hash": screen_input.development_input_hash,
        "validation_input_hash": screen_input.validation_input_hash,
        "chronological_split": screen_input.split.to_payload(),
        "precommit": {
            "hash": precommit_hash,
            "written_before_training": True,
            "written_before_validation_materialized": True,
        },
        "reporting": {
            "winner": None,
            "selection_allowed": False,
            "ensemble_allowed": False,
            "promotion_allowed": False,
            "sealed_holdout_materialized": False,
        },
        "architectures": [
            {
                "architecture_id": item.spec.architecture_id,
                "training": dict(item.training),
                "checkpoint_sha256": item.checkpoint_sha256,
                "validation_probability_hashes": {
                    symbol: _sha256_payload(
                        {
                            "architecture_id": item.spec.architecture_id,
                            "symbol": symbol,
                            "probabilities": [
                                format(value, ".17g")
                                for value in item.probabilities_by_symbol[symbol]
                            ],
                        }
                    )
                    for symbol in KIS_DAILY_SEQUENCE_SYMBOLS
                },
            }
            for item in trained
        ],
        "replay_cells": [
            {
                "architecture_id": cell.architecture_id,
                "symbol": cell.symbol,
                "prediction_hash": cell.prediction_hash,
                "fill_source": cell.replay.fill_source,
                "decisions_seen": cell.replay.result.decisions_seen,
                "trade_count": len(cell.replay.result.trades),
                "after_cost_pnl": str(cell.replay.result.after_cost_pnl),
                "gross_pnl": str(cell.replay.result.gross_pnl),
                "total_fees": str(cell.replay.result.total_fees),
                "total_slippage": str(cell.replay.result.total_slippage),
                "event_jsonl_sha256": cell.replay.replay_evidence.event_jsonl_sha256,
                "state_sqlite_sha256": cell.replay.replay_evidence.state_sqlite_sha256,
            }
            for cell in replay_cells
        ],
        "artifact_policy": {
            "repo_storage_allowed": False,
            "checkpoint_written": True,
            "raw_market_data_written": False,
        },
    }


def _write_json_new(path: Path, payload: Mapping[str, object]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _validate_run_label(run_label: str) -> None:
    if not run_label.strip() or any(character in run_label for character in ("/", "\\", ":")):
        raise ValueError(
            "KIS daily sequence run_label must be nonempty and contain no path separators"
        )


def _reject_repo_path(path: Path, *, repo_root: Path) -> None:
    if os.name != "nt":
        docker_repo_root = Path("/app").resolve()
        docker_artifact_root = docker_repo_root / "model_artifacts"
        if repo_root == docker_repo_root and (
            path == docker_artifact_root or docker_artifact_root in path.parents
        ):
            return
    if path == repo_root or repo_root in path.parents:
        raise ValueError("KIS daily sequence artifacts must stay outside the Git workspace")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"
