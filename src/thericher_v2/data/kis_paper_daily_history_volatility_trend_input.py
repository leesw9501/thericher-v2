"""Attested, phase-local NAS D1 volatility and trend feature inputs.

This Data-to-Research adapter consumes the already reattested daily-history
sequence input.  It materializes only causal completed-bar features in memory;
it has no provider, filesystem output, credential, target, or broker path.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, Timeframe
from thericher_v2.data.kis_paper_daily_history_panel import (
    KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE,
    KIS_PAPER_DAILY_HISTORY_PANEL_ID,
    KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS,
    KIS_PAPER_DAILY_HISTORY_PANEL_TARGET_KEYS,
    KisPaperDailyHistoryPanelTarget,
)
from thericher_v2.data.kis_paper_daily_history_sequence_input import (
    KIS_PAPER_DAILY_HISTORY_SEQUENCE_DEVELOPMENT_SESSION_COUNT,
    KIS_PAPER_DAILY_HISTORY_SEQUENCE_EXPECTED_DATASET_HASH,
    KIS_PAPER_DAILY_HISTORY_SEQUENCE_INPUT_ID,
    KIS_PAPER_DAILY_HISTORY_SEQUENCE_SOURCE_LIMITATIONS,
    KIS_PAPER_DAILY_HISTORY_SEQUENCE_VALIDATION_SESSION_COUNT,
    KisPaperDailyHistorySequenceInput,
    KisPaperDailyHistorySequencePhaseInput,
    require_attested_kis_paper_daily_history_sequence_input,
    require_attested_kis_paper_daily_history_sequence_phase_input,
)
from thericher_v2.research.causal_bar_features import (
    KIS_NAS_D1_VOLATILITY_TREND_CONDITIONING_WINDOW,
    KIS_NAS_D1_VOLATILITY_TREND_FEATURE_NAMES,
    KIS_NAS_D1_VOLATILITY_TREND_FEATURE_SCHEMA_ID,
    KIS_NAS_D1_VOLATILITY_TREND_REQUIRED_BARS,
    KIS_NAS_D1_VOLATILITY_TREND_SEQUENCE_LENGTH,
    build_kis_nas_d1_volatility_trend_feature_sequence,
    terminal_realized_volatility_20,
    terminal_trend_5,
)

KIS_PAPER_DAILY_HISTORY_VOLATILITY_TREND_INPUT_VERSION = (
    "kis-paper-daily-nas-volatility-trend-input-v1"
)
KIS_PAPER_DAILY_HISTORY_VOLATILITY_TREND_INPUT_ID = (
    "kis.paper.private.daily.nas.volatility-trend.input-v1"
)

KisPaperDailyHistoryVolatilityTrendPhase = Literal["development", "validation"]
_PHASES: tuple[KisPaperDailyHistoryVolatilityTrendPhase, ...] = (
    "development",
    "validation",
)
_INPUT_ATTESTATION = object()
_SOURCE_SAFE_FORBIDDEN_FIELDS = frozenset(
    {
        "bars",
        "close",
        "entry",
        "exit",
        "feature_sequence",
        "high",
        "label",
        "low",
        "open",
        "prices",
        "volume",
    }
)


@dataclass(frozen=True, slots=True)
class KisPaperDailyHistoryVolatilityTrendFeatureSample:
    """One target-free, completed-bar-only feature sample for one symbol."""

    symbol: str
    lookback_anchor_start: datetime
    feature_start: datetime
    decision_start: datetime
    decision_end: datetime
    feature_sequence: tuple[tuple[float, ...], ...]
    terminal_realized_volatility_20: float
    terminal_trend_5: float
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        try:
            sequence = tuple(
                tuple(float(value) for value in row) for row in self.feature_sequence
            )
        except (TypeError, ValueError) as error:
            raise ValueError("NAS D1 volatility trend feature sample is invalid") from error
        object.__setattr__(self, "feature_sequence", sequence)
        expected_volatility = terminal_realized_volatility_20(sequence)
        expected_trend = terminal_trend_5(sequence)
        if (
            self.symbol not in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            or self.schema_version != SCHEMA_VERSION
            or not math.isfinite(self.terminal_realized_volatility_20)
            or not math.isfinite(self.terminal_trend_5)
            or not math.isclose(
                self.terminal_realized_volatility_20,
                expected_volatility,
                rel_tol=1e-12,
                abs_tol=1e-15,
            )
            or not math.isclose(
                self.terminal_trend_5,
                expected_trend,
                rel_tol=1e-12,
                abs_tol=1e-15,
            )
            or not (
                self.lookback_anchor_start
                < self.feature_start
                <= self.decision_start
                < self.decision_end
            )
            or self.decision_end - self.decision_start != Timeframe.D1.duration
        ):
            raise ValueError("NAS D1 volatility trend feature sample is invalid")


@dataclass(frozen=True, slots=True, init=False)
class KisPaperDailyHistoryVolatilityTrendPhaseInput:
    """One reattested phase and its per-symbol target-free feature samples."""

    phase: KisPaperDailyHistoryVolatilityTrendPhase
    parent_dataset_id: str
    parent_dataset_hash: str
    index_hash: str
    source_phase_dataset_id: str
    source_phase_dataset_hash: str
    source_index_path: Path
    source_sessions: tuple[date, ...]
    source_targets_by_key: Mapping[str, KisPaperDailyHistoryPanelTarget]
    raw_price_limitations: tuple[str, ...]
    samples_by_symbol: Mapping[str, tuple[KisPaperDailyHistoryVolatilityTrendFeatureSample, ...]]
    feature_input_hash: str
    schema_version: int
    _attestation: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("use the verified NAS D1 volatility trend input builder")

    def samples(self, symbol: str) -> tuple[KisPaperDailyHistoryVolatilityTrendFeatureSample, ...]:
        require_attested_kis_paper_daily_history_volatility_trend_phase_input(self)
        return self.samples_by_symbol[_resolve_symbol(symbol)]

    def safe_payload(self) -> dict[str, object]:
        """Return identity and geometry only, never feature or price values."""

        require_attested_kis_paper_daily_history_volatility_trend_phase_input(self)
        payload = {
            "schema_version": self.schema_version,
            "kind": "kis_paper_daily_history_volatility_trend_phase_input",
            "phase": self.phase,
            "source": {
                "parent_dataset_id": self.parent_dataset_id,
                "parent_dataset_hash": self.parent_dataset_hash,
                "index_hash": self.index_hash,
                "phase_dataset_id": self.source_phase_dataset_id,
                "phase_dataset_hash": self.source_phase_dataset_hash,
                "source_target_states": [
                    _target_state_payload(target)
                    for target in self.source_targets_by_key.values()
                ],
            },
            "sessions": {
                "count": len(self.source_sessions),
                "start": self.source_sessions[0].isoformat(),
                "end": self.source_sessions[-1].isoformat(),
            },
            "features": _feature_contract_payload(),
            "sample_counts": {
                symbol: len(self.samples_by_symbol[symbol])
                for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            },
            "feature_input_hash": self.feature_input_hash,
            "source_local_only": True,
            "raw_rows_persisted": False,
        }
        _assert_source_safe(payload)
        return payload


@dataclass(frozen=True, slots=True, init=False)
class KisPaperDailyHistoryVolatilityTrendInput:
    """Attested development and validation feature inputs for Research."""

    input_id: str
    source_input_id: str
    panel_dataset_id: str
    panel_dataset_hash: str
    index_hash: str
    adjustment_mode: str
    source_index_path: Path
    source_targets_by_key: Mapping[str, KisPaperDailyHistoryPanelTarget]
    raw_price_limitations: tuple[str, ...]
    development: KisPaperDailyHistoryVolatilityTrendPhaseInput
    validation: KisPaperDailyHistoryVolatilityTrendPhaseInput
    development_input_hash: str
    validation_input_hash: str
    input_hash: str
    schema_version: int
    _attestation: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("use the verified NAS D1 volatility trend input builder")

    def development_samples(
        self,
        symbol: str,
    ) -> tuple[KisPaperDailyHistoryVolatilityTrendFeatureSample, ...]:
        require_attested_kis_paper_daily_history_volatility_trend_input(self)
        return self.development.samples(symbol)

    def validation_samples(
        self,
        symbol: str,
    ) -> tuple[KisPaperDailyHistoryVolatilityTrendFeatureSample, ...]:
        require_attested_kis_paper_daily_history_volatility_trend_input(self)
        return self.validation.samples(symbol)

    def safe_payload(self) -> dict[str, object]:
        """Return a source-safe handoff suitable for a future research precommit."""

        require_attested_kis_paper_daily_history_volatility_trend_input(self)
        payload = {
            "schema_version": self.schema_version,
            "kind": KIS_PAPER_DAILY_HISTORY_VOLATILITY_TREND_INPUT_ID,
            "version": KIS_PAPER_DAILY_HISTORY_VOLATILITY_TREND_INPUT_VERSION,
            "source_input_id": self.source_input_id,
            "panel": {
                "dataset_id": self.panel_dataset_id,
                "dataset_hash": self.panel_dataset_hash,
                "index_hash": self.index_hash,
                "adjustment_mode": self.adjustment_mode,
            },
            "features": _feature_contract_payload(),
            "limitations": list(self.raw_price_limitations),
            "phases": {
                "development": self.development.safe_payload(),
                "validation": self.validation.safe_payload(),
            },
            "input_hash": self.input_hash,
            "source_local_only": True,
            "raw_rows_persisted": False,
        }
        _assert_source_safe(payload)
        return payload


def build_kis_paper_daily_history_volatility_trend_input(
    source_input: KisPaperDailyHistorySequenceInput,
) -> KisPaperDailyHistoryVolatilityTrendInput:
    """Reattest and convert development and validation phases independently."""

    require_attested_kis_paper_daily_history_sequence_input(source_input)
    development = _build_phase_input(source_input.development)
    validation = _build_phase_input(source_input.validation)
    result = object.__new__(KisPaperDailyHistoryVolatilityTrendInput)
    object.__setattr__(result, "input_id", KIS_PAPER_DAILY_HISTORY_VOLATILITY_TREND_INPUT_ID)
    object.__setattr__(result, "source_input_id", source_input.input_id)
    object.__setattr__(result, "panel_dataset_id", source_input.panel_dataset_id)
    object.__setattr__(result, "panel_dataset_hash", source_input.panel_dataset_hash)
    object.__setattr__(result, "index_hash", source_input.index_hash)
    object.__setattr__(result, "adjustment_mode", source_input.adjustment_mode)
    object.__setattr__(result, "source_index_path", source_input.source_index_path)
    object.__setattr__(
        result,
        "source_targets_by_key",
        MappingProxyType(dict(source_input.source_targets_by_key)),
    )
    object.__setattr__(result, "raw_price_limitations", source_input.raw_price_limitations)
    object.__setattr__(result, "development", development)
    object.__setattr__(result, "validation", validation)
    object.__setattr__(result, "development_input_hash", development.feature_input_hash)
    object.__setattr__(result, "validation_input_hash", validation.feature_input_hash)
    object.__setattr__(
        result,
        "input_hash",
        _input_hash(
            source_input_id=source_input.input_id,
            panel_dataset_id=source_input.panel_dataset_id,
            panel_dataset_hash=source_input.panel_dataset_hash,
            index_hash=source_input.index_hash,
            adjustment_mode=source_input.adjustment_mode,
            development_input_hash=development.feature_input_hash,
            validation_input_hash=validation.feature_input_hash,
        ),
    )
    object.__setattr__(result, "schema_version", SCHEMA_VERSION)
    object.__setattr__(result, "_attestation", _INPUT_ATTESTATION)
    require_attested_kis_paper_daily_history_volatility_trend_input(result)
    return result


def require_attested_kis_paper_daily_history_volatility_trend_input(value: object) -> None:
    """Fail closed before Research consumes a volatility-trend input."""

    if (
        not isinstance(value, KisPaperDailyHistoryVolatilityTrendInput)
        or getattr(value, "_attestation", None) is not _INPUT_ATTESTATION
        or value.input_id != KIS_PAPER_DAILY_HISTORY_VOLATILITY_TREND_INPUT_ID
        or value.source_input_id != KIS_PAPER_DAILY_HISTORY_SEQUENCE_INPUT_ID
        or value.panel_dataset_id != KIS_PAPER_DAILY_HISTORY_PANEL_ID
        or value.panel_dataset_hash != KIS_PAPER_DAILY_HISTORY_SEQUENCE_EXPECTED_DATASET_HASH
        or value.adjustment_mode != KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE
        or value.raw_price_limitations != KIS_PAPER_DAILY_HISTORY_SEQUENCE_SOURCE_LIMITATIONS
        or value.schema_version != SCHEMA_VERSION
        or tuple(value.source_targets_by_key) != KIS_PAPER_DAILY_HISTORY_PANEL_TARGET_KEYS
        or value.source_index_path.is_symlink()
        or not value.source_index_path.is_file()
        or not _is_sha256(value.development_input_hash)
        or not _is_sha256(value.validation_input_hash)
        or not _is_sha256(value.input_hash)
    ):
        raise ValueError("NAS D1 volatility trend input requires an attested source")
    require_attested_kis_paper_daily_history_volatility_trend_phase_input(value.development)
    require_attested_kis_paper_daily_history_volatility_trend_phase_input(value.validation)
    if (
        value.development.phase != "development"
        or value.validation.phase != "validation"
        or value.development.parent_dataset_id != value.panel_dataset_id
        or value.validation.parent_dataset_id != value.panel_dataset_id
        or value.development.parent_dataset_hash != value.panel_dataset_hash
        or value.validation.parent_dataset_hash != value.panel_dataset_hash
        or value.development.index_hash != value.index_hash
        or value.validation.index_hash != value.index_hash
        or value.development.source_index_path != value.source_index_path
        or value.validation.source_index_path != value.source_index_path
        or value.development.source_targets_by_key != value.source_targets_by_key
        or value.validation.source_targets_by_key != value.source_targets_by_key
        or value.development.raw_price_limitations != value.raw_price_limitations
        or value.validation.raw_price_limitations != value.raw_price_limitations
        or value.development.feature_input_hash != value.development_input_hash
        or value.validation.feature_input_hash != value.validation_input_hash
        or value.development.source_sessions[-1] >= value.validation.source_sessions[0]
        or value.input_hash
        != _input_hash(
            source_input_id=value.source_input_id,
            panel_dataset_id=value.panel_dataset_id,
            panel_dataset_hash=value.panel_dataset_hash,
            index_hash=value.index_hash,
            adjustment_mode=value.adjustment_mode,
            development_input_hash=value.development_input_hash,
            validation_input_hash=value.validation_input_hash,
        )
    ):
        raise ValueError("NAS D1 volatility trend input provenance is invalid")


def require_attested_kis_paper_daily_history_volatility_trend_phase_input(
    value: object,
) -> None:
    """Fail closed unless one feature phase remains local, causal, and immutable."""

    if (
        not isinstance(value, KisPaperDailyHistoryVolatilityTrendPhaseInput)
        or getattr(value, "_attestation", None) is not _INPUT_ATTESTATION
        or value.phase not in _PHASES
        or value.parent_dataset_id != KIS_PAPER_DAILY_HISTORY_PANEL_ID
        or value.parent_dataset_hash != KIS_PAPER_DAILY_HISTORY_SEQUENCE_EXPECTED_DATASET_HASH
        or value.raw_price_limitations != KIS_PAPER_DAILY_HISTORY_SEQUENCE_SOURCE_LIMITATIONS
        or value.schema_version != SCHEMA_VERSION
        or tuple(value.source_targets_by_key) != KIS_PAPER_DAILY_HISTORY_PANEL_TARGET_KEYS
        or tuple(value.samples_by_symbol) != KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
        or value.source_index_path.is_symlink()
        or not value.source_index_path.is_file()
        or not _is_sha256(value.index_hash)
        or not _is_sha256(value.source_phase_dataset_hash)
        or not _is_sha256(value.feature_input_hash)
        or not value.source_phase_dataset_id
        or len(value.source_sessions) != _expected_session_count(value.phase)
        or tuple(sorted(value.source_sessions)) != value.source_sessions
        or len(set(value.source_sessions)) != len(value.source_sessions)
    ):
        raise ValueError("NAS D1 volatility trend phase input is invalid")
    expected_count = len(value.source_sessions) - KIS_NAS_D1_VOLATILITY_TREND_REQUIRED_BARS + 1
    if expected_count <= 0:
        raise ValueError("NAS D1 volatility trend phase input is too short")
    for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        samples = value.samples_by_symbol[symbol]
        if (
            len(samples) != expected_count
            or any(
                not isinstance(sample, KisPaperDailyHistoryVolatilityTrendFeatureSample)
                for sample in samples
            )
        ):
            raise ValueError("NAS D1 volatility trend phase sample count is invalid")
        for offset, sample in enumerate(samples):
            _require_phase_local_sample(
                sample,
                expected_symbol=symbol,
                decision_index=KIS_NAS_D1_VOLATILITY_TREND_REQUIRED_BARS - 1 + offset,
                sessions=value.source_sessions,
            )
    if value.feature_input_hash != _phase_input_hash(value):
        raise ValueError("NAS D1 volatility trend phase input hash is invalid")


def _build_phase_input(
    source_phase: KisPaperDailyHistorySequencePhaseInput,
) -> KisPaperDailyHistoryVolatilityTrendPhaseInput:
    require_attested_kis_paper_daily_history_sequence_phase_input(source_phase)
    if source_phase.phase not in _PHASES:
        raise ValueError("NAS D1 volatility trend phase is unsupported")
    streams = {
        symbol: source_phase.stream(symbol) for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
    }
    first_stream = streams[KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS[0]]
    if any(
        stream.dataset_id != first_stream.dataset_id
        or stream.dataset_hash != first_stream.dataset_hash
        or stream.source_path != source_phase.source_index_path
        for stream in streams.values()
    ):
        raise ValueError("NAS D1 volatility trend phase source is inconsistent")
    samples_by_symbol = {
        symbol: _samples_from_phase_bars(symbol=symbol, bars=streams[symbol].bars)
        for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
    }
    result = object.__new__(KisPaperDailyHistoryVolatilityTrendPhaseInput)
    object.__setattr__(result, "phase", source_phase.phase)
    object.__setattr__(result, "parent_dataset_id", source_phase.parent_dataset_id)
    object.__setattr__(result, "parent_dataset_hash", source_phase.parent_dataset_hash)
    object.__setattr__(result, "index_hash", source_phase.index_hash)
    object.__setattr__(result, "source_phase_dataset_id", first_stream.dataset_id)
    object.__setattr__(result, "source_phase_dataset_hash", first_stream.dataset_hash)
    object.__setattr__(result, "source_index_path", source_phase.source_index_path)
    object.__setattr__(result, "source_sessions", source_phase.common_sessions)
    object.__setattr__(
        result,
        "source_targets_by_key",
        MappingProxyType(dict(source_phase.targets_by_key)),
    )
    object.__setattr__(result, "raw_price_limitations", source_phase.raw_price_limitations)
    object.__setattr__(result, "samples_by_symbol", MappingProxyType(samples_by_symbol))
    object.__setattr__(result, "schema_version", SCHEMA_VERSION)
    object.__setattr__(result, "_attestation", _INPUT_ATTESTATION)
    object.__setattr__(result, "feature_input_hash", _phase_input_hash(result))
    require_attested_kis_paper_daily_history_volatility_trend_phase_input(result)
    return result


def _samples_from_phase_bars(
    *,
    symbol: str,
    bars: Sequence[object],
) -> tuple[KisPaperDailyHistoryVolatilityTrendFeatureSample, ...]:
    if len(bars) < KIS_NAS_D1_VOLATILITY_TREND_REQUIRED_BARS:
        raise ValueError("NAS D1 volatility trend phase is too short")
    samples: list[KisPaperDailyHistoryVolatilityTrendFeatureSample] = []
    for decision_index in range(KIS_NAS_D1_VOLATILITY_TREND_REQUIRED_BARS - 1, len(bars)):
        feature_sequence = build_kis_nas_d1_volatility_trend_feature_sequence(
            bars,  # type: ignore[arg-type]
            symbol=symbol,
            decision_index=decision_index,
        )
        decision_bar = bars[decision_index]
        anchor_bar = bars[
            decision_index - KIS_NAS_D1_VOLATILITY_TREND_REQUIRED_BARS + 1
        ]
        feature_start_bar = bars[
            decision_index - KIS_NAS_D1_VOLATILITY_TREND_SEQUENCE_LENGTH + 1
        ]
        if not all(
            hasattr(bar, "start_ts") and hasattr(bar, "end_ts")
            for bar in (decision_bar, anchor_bar, feature_start_bar)
        ):
            raise ValueError("NAS D1 volatility trend phase bar is invalid")
        samples.append(
            KisPaperDailyHistoryVolatilityTrendFeatureSample(
                symbol=symbol,
                lookback_anchor_start=anchor_bar.start_ts,  # type: ignore[union-attr]
                feature_start=feature_start_bar.start_ts,  # type: ignore[union-attr]
                decision_start=decision_bar.start_ts,  # type: ignore[union-attr]
                decision_end=decision_bar.end_ts,  # type: ignore[union-attr]
                feature_sequence=feature_sequence,
                terminal_realized_volatility_20=terminal_realized_volatility_20(
                    feature_sequence
                ),
                terminal_trend_5=terminal_trend_5(feature_sequence),
            )
        )
    return tuple(samples)


def _require_phase_local_sample(
    sample: KisPaperDailyHistoryVolatilityTrendFeatureSample,
    *,
    expected_symbol: str,
    decision_index: int,
    sessions: tuple[date, ...],
) -> None:
    if (
        sample.symbol != expected_symbol
        or sample.lookback_anchor_start.date()
        != sessions[decision_index - KIS_NAS_D1_VOLATILITY_TREND_REQUIRED_BARS + 1]
        or sample.feature_start.date()
        != sessions[decision_index - KIS_NAS_D1_VOLATILITY_TREND_SEQUENCE_LENGTH + 1]
        or sample.decision_start.date() != sessions[decision_index]
    ):
        raise ValueError("NAS D1 volatility trend sample crosses its phase boundary")


def _expected_session_count(phase: KisPaperDailyHistoryVolatilityTrendPhase) -> int:
    return {
        "development": KIS_PAPER_DAILY_HISTORY_SEQUENCE_DEVELOPMENT_SESSION_COUNT,
        "validation": KIS_PAPER_DAILY_HISTORY_SEQUENCE_VALIDATION_SESSION_COUNT,
    }[phase]


def _phase_input_hash(value: KisPaperDailyHistoryVolatilityTrendPhaseInput) -> str:
    return _sha256_json(
        {
            "kind": "kis_paper_daily_history_volatility_trend_phase_features",
            "schema_version": value.schema_version,
            "phase": value.phase,
            "parent_dataset_id": value.parent_dataset_id,
            "parent_dataset_hash": value.parent_dataset_hash,
            "index_hash": value.index_hash,
            "source_phase_dataset_id": value.source_phase_dataset_id,
            "source_phase_dataset_hash": value.source_phase_dataset_hash,
            "source_sessions": [session.isoformat() for session in value.source_sessions],
            "features": _feature_contract_payload(),
            "samples": {
                symbol: [
                    {
                        "lookback_anchor_start": sample.lookback_anchor_start.isoformat(),
                        "feature_start": sample.feature_start.isoformat(),
                        "decision_start": sample.decision_start.isoformat(),
                        "decision_end": sample.decision_end.isoformat(),
                        "feature_sequence": [
                            [format(number, ".17g") for number in row]
                            for row in sample.feature_sequence
                        ],
                        "terminal_realized_volatility_20": format(
                            sample.terminal_realized_volatility_20,
                            ".17g",
                        ),
                        "terminal_trend_5": format(sample.terminal_trend_5, ".17g"),
                    }
                    for sample in value.samples_by_symbol[symbol]
                ]
                for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            },
        }
    )


def _input_hash(
    *,
    source_input_id: str,
    panel_dataset_id: str,
    panel_dataset_hash: str,
    index_hash: str,
    adjustment_mode: str,
    development_input_hash: str,
    validation_input_hash: str,
) -> str:
    return _sha256_json(
        {
            "kind": KIS_PAPER_DAILY_HISTORY_VOLATILITY_TREND_INPUT_ID,
            "source_input_id": source_input_id,
            "panel_dataset_id": panel_dataset_id,
            "panel_dataset_hash": panel_dataset_hash,
            "index_hash": index_hash,
            "adjustment_mode": adjustment_mode,
            "features": _feature_contract_payload(),
            "development_input_hash": development_input_hash,
            "validation_input_hash": validation_input_hash,
        }
    )


def _feature_contract_payload() -> dict[str, object]:
    return {
        "schema_id": KIS_NAS_D1_VOLATILITY_TREND_FEATURE_SCHEMA_ID,
        "names": list(KIS_NAS_D1_VOLATILITY_TREND_FEATURE_NAMES),
        "sequence_length": KIS_NAS_D1_VOLATILITY_TREND_SEQUENCE_LENGTH,
        "conditioning_window": KIS_NAS_D1_VOLATILITY_TREND_CONDITIONING_WINDOW,
        "required_completed_bars": KIS_NAS_D1_VOLATILITY_TREND_REQUIRED_BARS,
        "per_symbol_only": True,
        "completed_bars_only": True,
        "future_bars_read": False,
    }


def _target_state_payload(target: KisPaperDailyHistoryPanelTarget) -> dict[str, object]:
    return {
        "target_key": target.target_key,
        "state": target.state,
        "last_reason": target.last_reason,
        "coverage_start_bucket": target.coverage_start_bucket,
        "coverage_end_bucket": target.coverage_end_bucket,
    }


def _assert_source_safe(value: object) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if str(key).lower() in _SOURCE_SAFE_FORBIDDEN_FIELDS:
                raise ValueError("NAS D1 volatility trend payload contains source values")
            _assert_source_safe(nested)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for nested in value:
            _assert_source_safe(nested)


def _sha256_json(value: Mapping[str, object]) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        return False
    try:
        int(value.removeprefix("sha256:"), 16)
    except ValueError:
        return False
    return True


def _resolve_symbol(symbol: str) -> str:
    if not isinstance(symbol, str):
        raise ValueError("NAS D1 volatility trend symbol is invalid")
    resolved = symbol.strip().upper()
    if resolved not in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        raise ValueError("NAS D1 volatility trend symbol is unsupported")
    return resolved
