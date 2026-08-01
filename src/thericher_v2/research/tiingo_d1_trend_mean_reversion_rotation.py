"""CPU-only, repeat-source falsification for one Tiingo ETF rotation rule.

This module keeps source values, scores, and individual returns in memory.  Its
external artifacts contain only immutable source identities, frozen geometry,
counts, aggregate cost outcomes, and a non-promoting classification.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, localcontext
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.data.tiingo_etf_daily import (
    TIINGO_ETF_D1_SYMBOLS,
    LoadedTiingoEtfDailySnapshot,
    TiingoEtfDailyRow,
)

TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_ID = "tiingo-d1-trend-mean-reversion-rotation-v1"
TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_TREND_LOOKBACK = 60
TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_PULLBACK_LOOKBACK = 5
TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_VOLATILITY_LOOKBACK = 20
TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_DEVELOPMENT_NUMERATOR = 7
TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_DEVELOPMENT_DENOMINATOR = 10
TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_PURGE_SESSIONS = 61
TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_MIN_VALIDATION_ACTIVE_DECISIONS = 100
TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_DISCONTINUITY_LIMIT = Decimal("0.20")
TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_COST_BAND = (
    Decimal("5"),
    Decimal("10"),
    Decimal("20"),
)
TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_PRIMARY_COST = Decimal("10")
TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_KILL_COST = Decimal("20")
TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_SOURCE_REUSE_FAMILIES = (
    "tiingo-etf-d1-cpu-baseline-v1",
    "tiingo-d1-sequence-breadth-v1",
)
_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)

InputStatus = Literal["ready", "input_unavailable"]
ResultStatus = Literal["input_unavailable", "falsified", "non_promoting_validation"]
MaskReason = Literal["event", "feature_discontinuity"]


@dataclass(frozen=True, slots=True)
class TiingoD1TrendMeanReversionRotationConfig:
    """Frozen causal, economic, and falsification geometry for this family."""

    trend_lookback: int = TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_TREND_LOOKBACK
    pullback_lookback: int = TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_PULLBACK_LOOKBACK
    volatility_lookback: int = TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_VOLATILITY_LOOKBACK
    development_numerator: int = TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_DEVELOPMENT_NUMERATOR
    development_denominator: int = TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_DEVELOPMENT_DENOMINATOR
    purge_sessions: int = TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_PURGE_SESSIONS
    minimum_validation_active_decisions: int = (
        TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_MIN_VALIDATION_ACTIVE_DECISIONS
    )
    discontinuity_limit: Decimal = TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_DISCONTINUITY_LIMIT
    cost_band: tuple[Decimal, ...] = TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_COST_BAND
    primary_cost: Decimal = TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_PRIMARY_COST
    kill_cost: Decimal = TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_KILL_COST
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.trend_lookback != TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_TREND_LOOKBACK
            or self.pullback_lookback
            != TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_PULLBACK_LOOKBACK
            or self.volatility_lookback
            != TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_VOLATILITY_LOOKBACK
            or self.development_numerator
            != TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_DEVELOPMENT_NUMERATOR
            or self.development_denominator
            != TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_DEVELOPMENT_DENOMINATOR
            or self.purge_sessions != TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_PURGE_SESSIONS
            or self.minimum_validation_active_decisions
            != TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_MIN_VALIDATION_ACTIVE_DECISIONS
            or self.discontinuity_limit
            != TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_DISCONTINUITY_LIMIT
            or self.cost_band != TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_COST_BAND
            or self.primary_cost != TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_PRIMARY_COST
            or self.kill_cost != TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_KILL_COST
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("Tiingo D1 mean-reversion rotation config is frozen")
        if self.purge_sessions <= self.trend_lookback:
            raise ValueError("Tiingo D1 mean-reversion rotation purge is insufficient")

    def safe_payload(self) -> dict[str, object]:
        return {
            "rule_id": TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_ID,
            "decision_time": "completed_session_t_close",
            "feature_windows": {
                "trend_sessions": self.trend_lookback,
                "pullback_sessions": self.pullback_lookback,
                "volatility_sessions": self.volatility_lookback,
            },
            "candidate_rule": (
                "positive_60_session_close_return_and_negative_5_session_close_return"
            ),
            "score": "negative_5_session_return_divided_by_prior_20_session_population_volatility",
            "target": "next_session_open_to_close_return",
            "position_limit": "at_most_one_etf_or_flat",
            "symbol_tie_order": list(TIINGO_ETF_D1_SYMBOLS),
            "event_mask": "any_fixed_universe_dividend_or_split_t_minus_60_through_t",
            "discontinuity_mask": (
                "any_fixed_universe_absolute_close_return_over_20pct_t_minus_60_through_t"
            ),
            "target_day_masking": "prohibited",
            "split": {
                "development_fraction": {
                    "numerator": self.development_numerator,
                    "denominator": self.development_denominator,
                },
                "purge_sessions": self.purge_sessions,
                "validation": "remainder_after_purge",
                "source_reuse_grade": "repeat_source_non_promoting_falsification",
            },
            "minimum_validation_active_decisions": self.minimum_validation_active_decisions,
            "cost": {
                "all_in_round_trip_bps": [_decimal_text(cost) for cost in self.cost_band],
                "primary_all_in_round_trip_bps": _decimal_text(self.primary_cost),
                "kill_all_in_round_trip_bps": _decimal_text(self.kill_cost),
            },
            "comparators": [
                "always_flat",
                "equal_weight_spy_qqq_iwm_on_candidate_active_dates",
                "positive_60_session_trend_rotation_on_candidate_active_dates",
            ],
            "kill_rule": (
                "candidate_net_flat_or_worse_at_20bp_or_no_better_than_both_active_comparators"
                "_across_cost_band"
            ),
            "gpu_eligible": False,
            "paper_input_eligible": False,
            "promotion_allowed": False,
        }


@dataclass(frozen=True, slots=True)
class TiingoD1TrendMeanReversionRotationSource:
    """Identity and source-reuse facts without rows or prices."""

    dataset_id: str
    dataset_hash: str
    manifest_hash: str
    source_reuse_families: tuple[str, ...] = (
        TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_SOURCE_REUSE_FAMILIES
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_reuse_families", tuple(self.source_reuse_families))
        if (
            not self.dataset_id.startswith("us_equities.tiingo_etf_daily.snapshot=")
            or not _is_sha256(self.dataset_hash)
            or not _is_sha256(self.manifest_hash)
            or self.source_reuse_families
            != TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_SOURCE_REUSE_FAMILIES
        ):
            raise ValueError("Tiingo D1 mean-reversion rotation source is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "provider": "Tiingo standard EOD API",
            "dataset_id": self.dataset_id,
            "dataset_hash": self.dataset_hash,
            "manifest_hash": self.manifest_hash,
            "symbols": list(TIINGO_ETF_D1_SYMBOLS),
            "raw_ohlcv_only": True,
            "source_reuse_families": list(self.source_reuse_families),
            "independent_holdout_claim_allowed": False,
            "sealed_tail_claim_allowed": False,
            "paper_input_eligible": False,
        }


@dataclass(frozen=True, slots=True)
class TiingoD1TrendMeanReversionRotationPhaseFacts:
    """Aggregate decision-shape facts for one chronological phase."""

    phase: Literal["development", "validation"]
    scheduled_decision_count: int
    accepted_decision_count: int
    event_excluded_count: int
    discontinuity_excluded_count: int
    no_signal_count: int
    active_decision_count: int

    def __post_init__(self) -> None:
        values = (
            self.scheduled_decision_count,
            self.accepted_decision_count,
            self.event_excluded_count,
            self.discontinuity_excluded_count,
            self.no_signal_count,
            self.active_decision_count,
        )
        if (
            self.phase not in {"development", "validation"}
            or min(values) < 0
            or self.scheduled_decision_count
            != self.accepted_decision_count
            + self.event_excluded_count
            + self.discontinuity_excluded_count
            or self.accepted_decision_count != self.no_signal_count + self.active_decision_count
        ):
            raise ValueError("Tiingo D1 mean-reversion rotation phase facts are invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "phase": self.phase,
            "scheduled_decision_count": self.scheduled_decision_count,
            "accepted_decision_count": self.accepted_decision_count,
            "event_excluded_count": self.event_excluded_count,
            "discontinuity_excluded_count": self.discontinuity_excluded_count,
            "no_signal_count": self.no_signal_count,
            "active_decision_count": self.active_decision_count,
        }


@dataclass(frozen=True, slots=True)
class _RotationDecision:
    index: int
    candidate_symbol: str | None
    trend_symbol: str | None

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("Tiingo D1 mean-reversion rotation decision index is invalid")
        if self.candidate_symbol is not None and self.candidate_symbol not in TIINGO_ETF_D1_SYMBOLS:
            raise ValueError("Tiingo D1 mean-reversion rotation candidate is invalid")
        if self.trend_symbol is not None and self.trend_symbol not in TIINGO_ETF_D1_SYMBOLS:
            raise ValueError("Tiingo D1 mean-reversion rotation trend candidate is invalid")


@dataclass(frozen=True, slots=True)
class TiingoD1TrendMeanReversionRotationInput:
    """Prepared source identity and decision shape; source values stay in memory."""

    source: TiingoD1TrendMeanReversionRotationSource
    config: TiingoD1TrendMeanReversionRotationConfig
    status: InputStatus
    reason: str | None
    common_session_count: int
    development: TiingoD1TrendMeanReversionRotationPhaseFacts
    validation: TiingoD1TrendMeanReversionRotationPhaseFacts
    input_hash: str
    _rows_by_symbol: Mapping[str, tuple[TiingoEtfDailyRow, ...]] = field(repr=False)
    _validation_decisions: tuple[_RotationDecision, ...] = field(repr=False)
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        rows = {symbol: tuple(value) for symbol, value in self._rows_by_symbol.items()}
        decisions = tuple(self._validation_decisions)
        if (
            set(rows) != set(TIINGO_ETF_D1_SYMBOLS)
            or self.status not in {"ready", "input_unavailable"}
            or self.common_session_count < 0
            or not _is_sha256(self.input_hash)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("Tiingo D1 mean-reversion rotation input is invalid")
        if any(len(value) != self.common_session_count for value in rows.values()):
            raise ValueError("Tiingo D1 mean-reversion rotation rows are misaligned")
        if self.status == "ready":
            if self.reason is not None or len(decisions) != self.validation.active_decision_count:
                raise ValueError("ready Tiingo D1 mean-reversion rotation input is invalid")
        elif (
            self.reason
            not in {"insufficient_common_sessions", "insufficient_validation_active_decisions"}
            or decisions
        ):
            raise ValueError("unavailable Tiingo D1 mean-reversion rotation input is invalid")
        expected_hash = _input_hash(
            source=self.source,
            config=self.config,
            status=self.status,
            reason=self.reason,
            common_session_count=self.common_session_count,
            development=self.development,
            validation=self.validation,
        )
        if self.input_hash != expected_hash:
            raise ValueError("Tiingo D1 mean-reversion rotation input identity is invalid")
        object.__setattr__(self, "_rows_by_symbol", MappingProxyType(rows))
        object.__setattr__(self, "_validation_decisions", decisions)

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "campaign_id": TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_ID,
            "source": self.source.safe_payload(),
            "contract": self.config.safe_payload(),
            "status": self.status,
            "reason": self.reason,
            "common_session_count": self.common_session_count,
            "phases": [self.development.safe_payload(), self.validation.safe_payload()],
            "input_hash": self.input_hash,
            "raw_market_data_written": False,
        }


@dataclass(frozen=True, slots=True)
class TiingoD1TrendMeanReversionRotationValidation:
    """Aggregate validation outcomes with all source values withheld."""

    active_decision_count: int
    candidate_net_total_bps_by_cost: Mapping[str, Decimal]
    equal_weight_net_total_bps_by_cost: Mapping[str, Decimal]
    trend_rotation_net_total_bps_by_cost: Mapping[str, Decimal]
    kill_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "kill_reasons", tuple(self.kill_reasons))
        mappings = (
            self.candidate_net_total_bps_by_cost,
            self.equal_weight_net_total_bps_by_cost,
            self.trend_rotation_net_total_bps_by_cost,
        )
        expected_costs = tuple(
            _decimal_text(cost)
            for cost in TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_COST_BAND
        )
        if (
            self.active_decision_count
            < TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_MIN_VALIDATION_ACTIVE_DECISIONS
            or any(tuple(mapping) != expected_costs for mapping in mappings)
            or any(not value.is_finite() for mapping in mappings for value in mapping.values())
            or any(
                reason
                not in {
                    "candidate_net_flat_or_worse_at_20bp",
                    "candidate_no_better_than_both_active_comparators_across_cost_band",
                }
                for reason in self.kill_reasons
            )
        ):
            raise ValueError("Tiingo D1 mean-reversion rotation validation is invalid")
        object.__setattr__(
            self,
            "candidate_net_total_bps_by_cost",
            MappingProxyType(dict(self.candidate_net_total_bps_by_cost)),
        )
        object.__setattr__(
            self,
            "equal_weight_net_total_bps_by_cost",
            MappingProxyType(dict(self.equal_weight_net_total_bps_by_cost)),
        )
        object.__setattr__(
            self,
            "trend_rotation_net_total_bps_by_cost",
            MappingProxyType(dict(self.trend_rotation_net_total_bps_by_cost)),
        )

    def safe_payload(self) -> dict[str, object]:
        return {
            "active_decision_count": self.active_decision_count,
            "candidate_net_total_bps_by_all_in_round_trip_cost": _safe_cost_mapping(
                self.candidate_net_total_bps_by_cost
            ),
            "equal_weight_net_total_bps_by_all_in_round_trip_cost": _safe_cost_mapping(
                self.equal_weight_net_total_bps_by_cost
            ),
            "trend_rotation_net_total_bps_by_all_in_round_trip_cost": _safe_cost_mapping(
                self.trend_rotation_net_total_bps_by_cost
            ),
            "active_comparator_scope": "candidate_active_decision_dates_only",
            "kill_reasons": list(self.kill_reasons),
        }


@dataclass(frozen=True, slots=True)
class TiingoD1TrendMeanReversionRotationResult:
    """One non-promoting validation classification for the frozen family."""

    campaign_input: TiingoD1TrendMeanReversionRotationInput
    status: ResultStatus
    validation: TiingoD1TrendMeanReversionRotationValidation | None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.status not in {"input_unavailable", "falsified", "non_promoting_validation"}:
            raise ValueError("Tiingo D1 mean-reversion rotation result status is invalid")
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("Tiingo D1 mean-reversion rotation result schema is invalid")
        if self.status == "input_unavailable":
            if self.campaign_input.status != "input_unavailable" or self.validation is not None:
                raise ValueError("unavailable Tiingo D1 mean-reversion rotation result is invalid")
        elif (
            self.campaign_input.status != "ready"
            or self.validation is None
            or (self.status == "falsified") != bool(self.validation.kill_reasons)
        ):
            raise ValueError("evaluated Tiingo D1 mean-reversion rotation result is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "campaign_id": TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_ID,
            "status": self.status,
            "input": self.campaign_input.safe_payload(),
            "validation": None if self.validation is None else self.validation.safe_payload(),
            "candidate_selection_allowed": False,
            "ensemble_allowed": False,
            "gpu_eligible": False,
            "paper_input_allowed": False,
            "promotion_allowed": False,
            "profitability_claim_allowed": False,
            "raw_market_data_written": False,
        }


@dataclass(frozen=True, slots=True)
class TiingoD1TrendMeanReversionRotationRun:
    """External-only precommit and summary paths for one deterministic run label."""

    result: TiingoD1TrendMeanReversionRotationResult
    precommit_path: Path
    precommit_hash: str
    summary_path: Path

    def __post_init__(self) -> None:
        if not _is_sha256(self.precommit_hash):
            raise ValueError("Tiingo D1 mean-reversion rotation precommit hash is invalid")


def prepare_tiingo_d1_trend_mean_reversion_rotation(
    snapshot: LoadedTiingoEtfDailySnapshot,
    *,
    config: TiingoD1TrendMeanReversionRotationConfig | None = None,
) -> TiingoD1TrendMeanReversionRotationInput:
    """Freeze only causal decision shape before any target-day return is read."""

    if not isinstance(snapshot, LoadedTiingoEtfDailySnapshot):
        raise TypeError("Tiingo D1 mean-reversion rotation requires a verified snapshot")
    resolved_config = config or TiingoD1TrendMeanReversionRotationConfig()
    source = TiingoD1TrendMeanReversionRotationSource(
        dataset_id=snapshot.snapshot.dataset_id,
        dataset_hash=snapshot.snapshot.dataset_hash,
        manifest_hash=snapshot.snapshot.manifest_hash,
    )
    rows_by_symbol = _aligned_rows(snapshot)
    common_session_count = len(rows_by_symbol[TIINGO_ETF_D1_SYMBOLS[0]])
    decision_indices = _decision_indices(common_session_count, resolved_config)
    if decision_indices is None:
        empty = TiingoD1TrendMeanReversionRotationPhaseFacts(
            phase="development",
            scheduled_decision_count=0,
            accepted_decision_count=0,
            event_excluded_count=0,
            discontinuity_excluded_count=0,
            no_signal_count=0,
            active_decision_count=0,
        )
        validation = TiingoD1TrendMeanReversionRotationPhaseFacts(
            phase="validation",
            scheduled_decision_count=0,
            accepted_decision_count=0,
            event_excluded_count=0,
            discontinuity_excluded_count=0,
            no_signal_count=0,
            active_decision_count=0,
        )
        return _campaign_input(
            source=source,
            config=resolved_config,
            status="input_unavailable",
            reason="insufficient_common_sessions",
            common_session_count=common_session_count,
            development=empty,
            validation=validation,
            rows_by_symbol=rows_by_symbol,
            validation_decisions=(),
        )

    development_indices, validation_indices = decision_indices
    development, _ = _phase_decisions(
        phase="development",
        indices=development_indices,
        rows_by_symbol=rows_by_symbol,
        config=resolved_config,
    )
    validation, validation_decisions = _phase_decisions(
        phase="validation",
        indices=validation_indices,
        rows_by_symbol=rows_by_symbol,
        config=resolved_config,
    )
    if validation.active_decision_count < resolved_config.minimum_validation_active_decisions:
        return _campaign_input(
            source=source,
            config=resolved_config,
            status="input_unavailable",
            reason="insufficient_validation_active_decisions",
            common_session_count=common_session_count,
            development=development,
            validation=validation,
            rows_by_symbol=rows_by_symbol,
            validation_decisions=(),
        )
    return _campaign_input(
        source=source,
        config=resolved_config,
        status="ready",
        reason=None,
        common_session_count=common_session_count,
        development=development,
        validation=validation,
        rows_by_symbol=rows_by_symbol,
        validation_decisions=validation_decisions,
    )


def evaluate_tiingo_d1_trend_mean_reversion_rotation(
    campaign_input: TiingoD1TrendMeanReversionRotationInput,
) -> TiingoD1TrendMeanReversionRotationResult:
    """Evaluate only the already-qualified validation decision contexts."""

    if not isinstance(campaign_input, TiingoD1TrendMeanReversionRotationInput):
        raise TypeError("Tiingo D1 mean-reversion rotation requires a prepared input")
    if campaign_input.status == "input_unavailable":
        return TiingoD1TrendMeanReversionRotationResult(
            campaign_input=campaign_input,
            status="input_unavailable",
            validation=None,
        )

    validation = _validation_outcomes(campaign_input)
    return TiingoD1TrendMeanReversionRotationResult(
        campaign_input=campaign_input,
        status="falsified" if validation.kill_reasons else "non_promoting_validation",
        validation=validation,
    )


def run_tiingo_d1_trend_mean_reversion_rotation(
    snapshot: LoadedTiingoEtfDailySnapshot,
    *,
    artifact_root: Path | str,
    run_label: str,
    repo_root: Path | str,
) -> TiingoD1TrendMeanReversionRotationRun:
    """Prepare, evaluate, and write idempotent safe evidence outside Git."""

    resolved_label = _validated_run_label(run_label)
    root = _external_artifact_root(Path(artifact_root), Path(repo_root))
    campaign_input = prepare_tiingo_d1_trend_mean_reversion_rotation(snapshot)
    precommit_payload = campaign_input.safe_payload()
    precommit_hash = _sha256_json(precommit_payload)
    result = evaluate_tiingo_d1_trend_mean_reversion_rotation(campaign_input)
    summary_payload = {
        "precommit_hash": precommit_hash,
        "result": result.safe_payload(),
    }
    artifact_dir = root / "research" / TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_ID / resolved_label
    _ensure_artifact_directory(root, artifact_dir)
    precommit_path = artifact_dir / "precommit.json"
    summary_path = artifact_dir / "summary.json"
    _write_or_verify(precommit_path, _canonical_json(precommit_payload))
    _write_or_verify(summary_path, _canonical_json(summary_payload))
    return TiingoD1TrendMeanReversionRotationRun(
        result=result,
        precommit_path=precommit_path,
        precommit_hash=precommit_hash,
        summary_path=summary_path,
    )


def _campaign_input(
    *,
    source: TiingoD1TrendMeanReversionRotationSource,
    config: TiingoD1TrendMeanReversionRotationConfig,
    status: InputStatus,
    reason: str | None,
    common_session_count: int,
    development: TiingoD1TrendMeanReversionRotationPhaseFacts,
    validation: TiingoD1TrendMeanReversionRotationPhaseFacts,
    rows_by_symbol: Mapping[str, tuple[TiingoEtfDailyRow, ...]],
    validation_decisions: tuple[_RotationDecision, ...],
) -> TiingoD1TrendMeanReversionRotationInput:
    return TiingoD1TrendMeanReversionRotationInput(
        source=source,
        config=config,
        status=status,
        reason=reason,
        common_session_count=common_session_count,
        development=development,
        validation=validation,
        input_hash=_input_hash(
            source=source,
            config=config,
            status=status,
            reason=reason,
            common_session_count=common_session_count,
            development=development,
            validation=validation,
        ),
        _rows_by_symbol=rows_by_symbol,
        _validation_decisions=validation_decisions,
    )


def _aligned_rows(
    snapshot: LoadedTiingoEtfDailySnapshot,
) -> Mapping[str, tuple[TiingoEtfDailyRow, ...]]:
    rows_by_symbol = {
        symbol: tuple(snapshot.rows_by_symbol[symbol]) for symbol in TIINGO_ETF_D1_SYMBOLS
    }
    date_maps = {
        symbol: {row.session_date: row for row in rows}
        for symbol, rows in rows_by_symbol.items()
    }
    if any(
        len(date_maps[symbol]) != len(rows_by_symbol[symbol])
        for symbol in TIINGO_ETF_D1_SYMBOLS
    ):
        raise ValueError("Tiingo D1 mean-reversion rotation source dates are invalid")
    common_dates = tuple(sorted(set.intersection(*(set(values) for values in date_maps.values()))))
    if not common_dates:
        raise ValueError("Tiingo D1 mean-reversion rotation source has no common sessions")
    return MappingProxyType(
        {
            symbol: tuple(date_maps[symbol][session_date] for session_date in common_dates)
            for symbol in TIINGO_ETF_D1_SYMBOLS
        }
    )


def _decision_indices(
    common_session_count: int,
    config: TiingoD1TrendMeanReversionRotationConfig,
) -> tuple[tuple[int, ...], tuple[int, ...]] | None:
    minimum_index = config.trend_lookback + 1
    all_indices = tuple(range(minimum_index, common_session_count - 1))
    development_count = (
        len(all_indices) * config.development_numerator // config.development_denominator
    )
    validation_start = development_count + config.purge_sessions
    if development_count == 0 or validation_start >= len(all_indices):
        return None
    return all_indices[:development_count], all_indices[validation_start:]


def _phase_decisions(
    *,
    phase: Literal["development", "validation"],
    indices: tuple[int, ...],
    rows_by_symbol: Mapping[str, tuple[TiingoEtfDailyRow, ...]],
    config: TiingoD1TrendMeanReversionRotationConfig,
) -> tuple[TiingoD1TrendMeanReversionRotationPhaseFacts, tuple[_RotationDecision, ...]]:
    accepted = 0
    events = 0
    discontinuities = 0
    no_signal = 0
    active: list[_RotationDecision] = []
    for index in indices:
        exclusion = _mask_reason(index=index, rows_by_symbol=rows_by_symbol, config=config)
        if exclusion == "event":
            events += 1
            continue
        if exclusion == "feature_discontinuity":
            discontinuities += 1
            continue
        accepted += 1
        decision = _decision(index=index, rows_by_symbol=rows_by_symbol, config=config)
        if decision.candidate_symbol is None:
            no_signal += 1
        else:
            active.append(decision)
    facts = TiingoD1TrendMeanReversionRotationPhaseFacts(
        phase=phase,
        scheduled_decision_count=len(indices),
        accepted_decision_count=accepted,
        event_excluded_count=events,
        discontinuity_excluded_count=discontinuities,
        no_signal_count=no_signal,
        active_decision_count=len(active),
    )
    return facts, tuple(active)


def _mask_reason(
    *,
    index: int,
    rows_by_symbol: Mapping[str, tuple[TiingoEtfDailyRow, ...]],
    config: TiingoD1TrendMeanReversionRotationConfig,
) -> MaskReason | None:
    start = index - config.trend_lookback
    if start <= 0:
        raise ValueError("Tiingo D1 mean-reversion rotation decision index is invalid")
    for symbol in TIINGO_ETF_D1_SYMBOLS:
        rows = rows_by_symbol[symbol]
        if any(row.div_cash != 0 or row.split_factor != 1 for row in rows[start : index + 1]):
            return "event"
        for transition_index in range(start, index + 1):
            close_return = (
                rows[transition_index].close / rows[transition_index - 1].close - Decimal("1")
            )
            if abs(close_return) > config.discontinuity_limit:
                return "feature_discontinuity"
    return None


def _decision(
    *,
    index: int,
    rows_by_symbol: Mapping[str, tuple[TiingoEtfDailyRow, ...]],
    config: TiingoD1TrendMeanReversionRotationConfig,
) -> _RotationDecision:
    best_candidate: tuple[Decimal, str] | None = None
    best_trend: tuple[Decimal, str] | None = None
    for symbol in TIINGO_ETF_D1_SYMBOLS:
        rows = rows_by_symbol[symbol]
        trend_return = rows[index].close / rows[index - config.trend_lookback].close - Decimal("1")
        if trend_return > 0 and (best_trend is None or trend_return > best_trend[0]):
            best_trend = (trend_return, symbol)
        pullback_return = (
            rows[index].close / rows[index - config.pullback_lookback].close - Decimal("1")
        )
        if trend_return <= 0 or pullback_return >= 0:
            continue
        volatility = _prior_volatility(rows, index=index, config=config)
        if volatility == 0:
            continue
        score = -pullback_return / volatility
        if best_candidate is None or score > best_candidate[0]:
            best_candidate = (score, symbol)
    return _RotationDecision(
        index=index,
        candidate_symbol=None if best_candidate is None else best_candidate[1],
        trend_symbol=None if best_trend is None else best_trend[1],
    )


def _prior_volatility(
    rows: tuple[TiingoEtfDailyRow, ...],
    *,
    index: int,
    config: TiingoD1TrendMeanReversionRotationConfig,
) -> Decimal:
    returns = tuple(
        rows[position].close / rows[position - 1].close - Decimal("1")
        for position in range(index - config.volatility_lookback, index)
    )
    if len(returns) != config.volatility_lookback:
        raise ValueError("Tiingo D1 mean-reversion rotation volatility window is invalid")
    mean = sum(returns, Decimal("0")) / Decimal(len(returns))
    variance = sum((value - mean) ** 2 for value in returns) / Decimal(len(returns))
    with localcontext() as context:
        context.prec = 34
        return variance.sqrt()


def _validation_outcomes(
    campaign_input: TiingoD1TrendMeanReversionRotationInput,
) -> TiingoD1TrendMeanReversionRotationValidation:
    costs = tuple(_decimal_text(cost) for cost in campaign_input.config.cost_band)
    candidate = {cost: Decimal("0") for cost in costs}
    equal_weight = {cost: Decimal("0") for cost in costs}
    trend_rotation = {cost: Decimal("0") for cost in costs}
    for decision in campaign_input._validation_decisions:
        if decision.candidate_symbol is None or decision.trend_symbol is None:
            raise ValueError("Tiingo D1 mean-reversion rotation validation decision is invalid")
        candidate_return = _target_return(
            campaign_input._rows_by_symbol[decision.candidate_symbol], decision.index
        )
        equal_weight_return = sum(
            (
                _target_return(campaign_input._rows_by_symbol[symbol], decision.index)
                for symbol in TIINGO_ETF_D1_SYMBOLS
            ),
            Decimal("0"),
        ) / Decimal(len(TIINGO_ETF_D1_SYMBOLS))
        trend_return = _target_return(
            campaign_input._rows_by_symbol[decision.trend_symbol], decision.index
        )
        for cost in campaign_input.config.cost_band:
            key = _decimal_text(cost)
            candidate[key] += candidate_return * Decimal("10000") - cost
            equal_weight[key] += equal_weight_return * Decimal("10000") - cost
            trend_rotation[key] += trend_return * Decimal("10000") - cost
    kill_reasons: list[str] = []
    kill_key = _decimal_text(campaign_input.config.kill_cost)
    if candidate[kill_key] <= 0:
        kill_reasons.append("candidate_net_flat_or_worse_at_20bp")
    if all(
        candidate[key] <= equal_weight[key] and candidate[key] <= trend_rotation[key]
        for key in costs
    ):
        kill_reasons.append(
            "candidate_no_better_than_both_active_comparators_across_cost_band"
        )
    return TiingoD1TrendMeanReversionRotationValidation(
        active_decision_count=len(campaign_input._validation_decisions),
        candidate_net_total_bps_by_cost=candidate,
        equal_weight_net_total_bps_by_cost=equal_weight,
        trend_rotation_net_total_bps_by_cost=trend_rotation,
        kill_reasons=tuple(kill_reasons),
    )


def _target_return(rows: tuple[TiingoEtfDailyRow, ...], index: int) -> Decimal:
    target = rows[index + 1]
    if target.open <= 0:
        raise ValueError("Tiingo D1 mean-reversion rotation target open is invalid")
    return target.close / target.open - Decimal("1")


def _input_hash(
    *,
    source: TiingoD1TrendMeanReversionRotationSource,
    config: TiingoD1TrendMeanReversionRotationConfig,
    status: InputStatus,
    reason: str | None,
    common_session_count: int,
    development: TiingoD1TrendMeanReversionRotationPhaseFacts,
    validation: TiingoD1TrendMeanReversionRotationPhaseFacts,
) -> str:
    return _sha256_json(
        {
            "source": source.safe_payload(),
            "contract": config.safe_payload(),
            "status": status,
            "reason": reason,
            "common_session_count": common_session_count,
            "phases": [development.safe_payload(), validation.safe_payload()],
        }
    )


def _validated_run_label(run_label: str) -> str:
    if not isinstance(run_label, str) or not _SAFE_RUN_LABEL.fullmatch(run_label):
        raise ValueError("Tiingo D1 mean-reversion rotation run label is invalid")
    return run_label


def _external_artifact_root(artifact_root: Path, repo_root: Path) -> Path:
    root = artifact_root.resolve(strict=False)
    repository = repo_root.resolve(strict=False)
    docker_repository = Path("/app").resolve(strict=False)
    docker_artifacts = (docker_repository / "model_artifacts").resolve(strict=False)
    if root.is_relative_to(repository) and not (
        repository == docker_repository and root.is_relative_to(docker_artifacts)
    ):
        raise ValueError("Tiingo D1 mean-reversion rotation artifacts must stay outside Git")
    if root.exists() and (root.is_symlink() or not root.is_dir()):
        raise ValueError("Tiingo D1 mean-reversion rotation artifact root is invalid")
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve(strict=False)


def _ensure_artifact_directory(root: Path, artifact_dir: Path) -> None:
    if artifact_dir.exists() and (artifact_dir.is_symlink() or not artifact_dir.is_dir()):
        raise ValueError("Tiingo D1 mean-reversion rotation artifact directory is invalid")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    if not artifact_dir.resolve(strict=False).is_relative_to(root):
        raise ValueError("Tiingo D1 mean-reversion rotation artifact directory is invalid")


def _write_or_verify(path: Path, encoded: bytes) -> None:
    if path.exists():
        if path.is_symlink() or path.read_bytes() != encoded:
            raise ValueError("Tiingo D1 mean-reversion rotation artifact conflicts with evidence")
        return
    staging = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.stage")
    try:
        staging.write_bytes(encoded)
        os.replace(staging, path)
    finally:
        staging.unlink(missing_ok=True)


def _canonical_json(payload: Mapping[str, object]) -> bytes:
    return (json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _safe_cost_mapping(values: Mapping[str, Decimal]) -> dict[str, str]:
    return {cost: _decimal_text(values[cost]) for cost in values}


def _sha256_json(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _is_sha256(value: str) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")
