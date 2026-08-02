"""Offline causal multi-timeframe SPY logistic baseline.

The module keeps feature rows, labels, predictions, and coefficients in
process. Its external artifacts carry only frozen contract, source identity,
counts, model hash, and aggregate outcomes for this non-promoting campaign.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe
from thericher_v2.data.kis_paper_intraday import (
    require_complete_kis_paper_private_intraday_session,
)
from thericher_v2.data.local import CatalogedBars
from thericher_v2.data.resample import SessionWindow, resample_session_bars
from thericher_v2.data.us_equity_session import US_EQUITY_EASTERN, us_equity_2026_session

SPY_INTRADAY_MTF_LOGISTIC_10M_ID = "spy-intraday-mtf-logistic-10m-v1"
SPY_INTRADAY_MTF_LOGISTIC_10M_SYMBOL = "SPY"
SPY_INTRADAY_MTF_LOGISTIC_10M_MARKET = "US"
SPY_INTRADAY_MTF_LOGISTIC_10M_DEVELOPMENT_SESSIONS = 10
SPY_INTRADAY_MTF_LOGISTIC_10M_PURGE_SESSIONS = 1
SPY_INTRADAY_MTF_LOGISTIC_10M_VALIDATION_SESSIONS = 10
SPY_INTRADAY_MTF_LOGISTIC_10M_FIRST_ENTRY_INDEX = 180
SPY_INTRADAY_MTF_LOGISTIC_10M_LAST_ENTRY_INDEX = 360
SPY_INTRADAY_MTF_LOGISTIC_10M_STEP_BARS = 10
SPY_INTRADAY_MTF_LOGISTIC_10M_HOLD_BARS = 10
SPY_INTRADAY_MTF_LOGISTIC_10M_MIN_PHASE_ROWS = 150
SPY_INTRADAY_MTF_LOGISTIC_10M_MIN_VALIDATION_LONGS = 30
SPY_INTRADAY_MTF_LOGISTIC_10M_M1_LOOKBACK = 30
SPY_INTRADAY_MTF_LOGISTIC_10M_M5_RETURN_BARS = 6
SPY_INTRADAY_MTF_LOGISTIC_10M_M10_RETURN_BARS = 3
SPY_INTRADAY_MTF_LOGISTIC_10M_C = 0.1
SPY_INTRADAY_MTF_LOGISTIC_10M_THRESHOLD = 0.55
SPY_INTRADAY_MTF_LOGISTIC_10M_COST_BAND = (
    Decimal("5"),
    Decimal("10"),
    Decimal("20"),
)
SPY_INTRADAY_MTF_LOGISTIC_10M_KILL_COST = Decimal("20")
SPY_INTRADAY_MTF_LOGISTIC_10M_FEATURE_NAMES = (
    "m1_return_30m",
    "m1_realized_range_30m",
    "m5_return_6bar",
    "m10_return_3bar",
    "h1_latest_candle_return",
    "h3_latest_candle_return",
)
_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)

InputStatus = Literal["ready", "input_unavailable"]
ModelStatus = Literal["ready", "input_unavailable"]
ResultStatus = Literal["input_unavailable", "falsified", "non_promoting_validation"]
PhaseName = Literal["development", "validation"]


@dataclass(frozen=True, slots=True)
class SpyIntradayMtfLogistic10mConfig:
    """The frozen geometry, feature schema, and single CPU model setting."""

    development_sessions: int = SPY_INTRADAY_MTF_LOGISTIC_10M_DEVELOPMENT_SESSIONS
    purge_sessions: int = SPY_INTRADAY_MTF_LOGISTIC_10M_PURGE_SESSIONS
    validation_sessions: int = SPY_INTRADAY_MTF_LOGISTIC_10M_VALIDATION_SESSIONS
    first_entry_index: int = SPY_INTRADAY_MTF_LOGISTIC_10M_FIRST_ENTRY_INDEX
    last_entry_index: int = SPY_INTRADAY_MTF_LOGISTIC_10M_LAST_ENTRY_INDEX
    step_bars: int = SPY_INTRADAY_MTF_LOGISTIC_10M_STEP_BARS
    hold_bars: int = SPY_INTRADAY_MTF_LOGISTIC_10M_HOLD_BARS
    minimum_phase_rows: int = SPY_INTRADAY_MTF_LOGISTIC_10M_MIN_PHASE_ROWS
    minimum_validation_longs: int = SPY_INTRADAY_MTF_LOGISTIC_10M_MIN_VALIDATION_LONGS
    m1_lookback: int = SPY_INTRADAY_MTF_LOGISTIC_10M_M1_LOOKBACK
    m5_return_bars: int = SPY_INTRADAY_MTF_LOGISTIC_10M_M5_RETURN_BARS
    m10_return_bars: int = SPY_INTRADAY_MTF_LOGISTIC_10M_M10_RETURN_BARS
    logistic_c: float = SPY_INTRADAY_MTF_LOGISTIC_10M_C
    threshold: float = SPY_INTRADAY_MTF_LOGISTIC_10M_THRESHOLD
    cost_band: tuple[Decimal, ...] = SPY_INTRADAY_MTF_LOGISTIC_10M_COST_BAND
    kill_cost: Decimal = SPY_INTRADAY_MTF_LOGISTIC_10M_KILL_COST
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.development_sessions != SPY_INTRADAY_MTF_LOGISTIC_10M_DEVELOPMENT_SESSIONS
            or self.purge_sessions != SPY_INTRADAY_MTF_LOGISTIC_10M_PURGE_SESSIONS
            or self.validation_sessions != SPY_INTRADAY_MTF_LOGISTIC_10M_VALIDATION_SESSIONS
            or self.first_entry_index != SPY_INTRADAY_MTF_LOGISTIC_10M_FIRST_ENTRY_INDEX
            or self.last_entry_index != SPY_INTRADAY_MTF_LOGISTIC_10M_LAST_ENTRY_INDEX
            or self.step_bars != SPY_INTRADAY_MTF_LOGISTIC_10M_STEP_BARS
            or self.hold_bars != SPY_INTRADAY_MTF_LOGISTIC_10M_HOLD_BARS
            or self.minimum_phase_rows != SPY_INTRADAY_MTF_LOGISTIC_10M_MIN_PHASE_ROWS
            or self.minimum_validation_longs != SPY_INTRADAY_MTF_LOGISTIC_10M_MIN_VALIDATION_LONGS
            or self.m1_lookback != SPY_INTRADAY_MTF_LOGISTIC_10M_M1_LOOKBACK
            or self.m5_return_bars != SPY_INTRADAY_MTF_LOGISTIC_10M_M5_RETURN_BARS
            or self.m10_return_bars != SPY_INTRADAY_MTF_LOGISTIC_10M_M10_RETURN_BARS
            or self.logistic_c != SPY_INTRADAY_MTF_LOGISTIC_10M_C
            or self.threshold != SPY_INTRADAY_MTF_LOGISTIC_10M_THRESHOLD
            or self.cost_band != SPY_INTRADAY_MTF_LOGISTIC_10M_COST_BAND
            or self.kill_cost != SPY_INTRADAY_MTF_LOGISTIC_10M_KILL_COST
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("SPY intraday MTF logistic config is frozen")
        if (
            self.first_entry_index <= self.m1_lookback
            or self.last_entry_index <= self.first_entry_index
            or self.step_bars <= 0
            or self.hold_bars != self.step_bars
            or self.minimum_phase_rows <= 0
            or self.minimum_validation_longs <= 0
            or self.kill_cost not in self.cost_band
        ):
            raise ValueError("SPY intraday MTF logistic geometry is invalid")

    @property
    def complete_session_count(self) -> int:
        return self.development_sessions + self.purge_sessions + self.validation_sessions

    @property
    def decision_indices(self) -> tuple[int, ...]:
        return tuple(range(self.first_entry_index, self.last_entry_index + 1, self.step_bars))

    def safe_payload(self) -> dict[str, object]:
        return {
            "campaign_id": SPY_INTRADAY_MTF_LOGISTIC_10M_ID,
            "decision_schedule": {
                "first_offset_minutes": self.first_entry_index,
                "last_offset_minutes": self.last_entry_index,
                "step_minutes": self.step_bars,
                "timezone": "America/New_York",
            },
            "feature_cutoff": "completed_same_session_bar_boundary",
            "features": {
                "names": list(SPY_INTRADAY_MTF_LOGISTIC_10M_FEATURE_NAMES),
                "m1_return_minutes": self.m1_lookback,
                "m1_realized_range_minutes": self.m1_lookback,
                "m5_return_completed_bars": self.m5_return_bars,
                "m10_return_completed_bars": self.m10_return_bars,
                "h1_latest_completed_candle_return": True,
                "h3_latest_completed_candle_return": True,
            },
            "target": "next_10m_m1_open_to_open_sign",
            "split": {
                "development_sessions": self.development_sessions,
                "purge_sessions": self.purge_sessions,
                "validation_sessions": self.validation_sessions,
                "development_target_access": "after_target_free_preflight_only",
                "validation_target_access": "after_fit_and_policy_construction_only",
            },
            "model": {
                "family": "standardized_l2_logistic_regression",
                "c": _float_text(self.logistic_c),
                "class_weight": None,
                "fit_scope": "development_only",
                "refit_allowed": False,
                "long_only_probability_threshold": _float_text(self.threshold),
            },
            "preflight": {
                "minimum_rows_each_phase": self.minimum_phase_rows,
                "minimum_validation_long_decisions": self.minimum_validation_longs,
                "effective_validation_unit": "ten_session_blocks_not_independent_rows",
            },
            "cost": {
                "all_in_round_trip_bps": [_decimal_text(cost) for cost in self.cost_band],
                "kill_all_in_round_trip_bps": _decimal_text(self.kill_cost),
            },
            "comparators": {
                "flat": "always_flat",
                "always_long": "same_schedule_same_cost_net_mean_per_executed_event",
            },
            "kill_rule": (
                "positive_20bp_policy_total_and_strictly_higher_20bp_policy_mean_than_always_long"
            ),
            "gpu_eligible": False,
            "paper_input_eligible": False,
            "promotion_allowed": False,
        }


@dataclass(frozen=True, slots=True)
class SpyIntradayMtfLogistic10mSource:
    dataset_id: str
    dataset_hash: str

    def __post_init__(self) -> None:
        if not self.dataset_id.startswith(
            "kis.paper.private.intraday.spy.ams.m1."
        ) or not _is_sha256(self.dataset_hash):
            raise ValueError("SPY intraday MTF logistic source is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "dataset_hash": self.dataset_hash,
            "symbol": SPY_INTRADAY_MTF_LOGISTIC_10M_SYMBOL,
            "market": SPY_INTRADAY_MTF_LOGISTIC_10M_MARKET,
            "source_scope": "verified_local_private_kis_cache_offline_only",
            "point_in_time_claim_allowed": False,
            "paper_input_eligible": False,
        }


@dataclass(frozen=True, slots=True)
class SpyIntradayMtfLogistic10mPhaseFacts:
    phase: PhaseName
    session_count: int
    scheduled_row_count: int
    structural_unavailable_count: int
    feature_row_count: int

    def __post_init__(self) -> None:
        values = (
            self.session_count,
            self.scheduled_row_count,
            self.structural_unavailable_count,
            self.feature_row_count,
        )
        if (
            self.phase not in {"development", "validation"}
            or min(values) < 0
            or self.scheduled_row_count
            != self.structural_unavailable_count + self.feature_row_count
        ):
            raise ValueError("SPY intraday MTF logistic phase facts are invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "phase": self.phase,
            "session_count": self.session_count,
            "scheduled_row_count": self.scheduled_row_count,
            "structural_unavailable_count": self.structural_unavailable_count,
            "feature_row_count": self.feature_row_count,
        }


@dataclass(frozen=True, slots=True)
class _RowContext:
    session_index: int
    entry_index: int
    features: tuple[float, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "features", tuple(self.features))
        if (
            self.session_index < 0
            or self.entry_index < 0
            or len(self.features) != len(SPY_INTRADAY_MTF_LOGISTIC_10M_FEATURE_NAMES)
            or any(not math.isfinite(value) for value in self.features)
        ):
            raise ValueError("SPY intraday MTF logistic row context is invalid")


@dataclass(frozen=True, slots=True)
class SpyIntradayMtfLogistic10mInput:
    """Prepared features without validation labels or target returns."""

    source: SpyIntradayMtfLogistic10mSource
    config: SpyIntradayMtfLogistic10mConfig
    status: InputStatus
    reason: str | None
    complete_regular_session_count: int
    development: SpyIntradayMtfLogistic10mPhaseFacts
    validation: SpyIntradayMtfLogistic10mPhaseFacts
    input_hash: str
    _development_sessions: tuple[tuple[Bar, ...], ...] = field(repr=False)
    _development_rows: tuple[_RowContext, ...] = field(repr=False)
    _validation_sessions: tuple[tuple[Bar, ...], ...] = field(repr=False)
    _validation_rows: tuple[_RowContext, ...] = field(repr=False)
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        development_sessions = tuple(tuple(session) for session in self._development_sessions)
        development_rows = tuple(self._development_rows)
        validation_sessions = tuple(tuple(session) for session in self._validation_sessions)
        validation_rows = tuple(self._validation_rows)
        if (
            self.status not in {"ready", "input_unavailable"}
            or self.complete_regular_session_count < 0
            or self.schema_version != SCHEMA_VERSION
            or not _is_sha256(self.input_hash)
        ):
            raise ValueError("SPY intraday MTF logistic input is invalid")
        if self.status == "ready":
            if (
                self.reason is not None
                or len(development_sessions) != self.config.development_sessions
                or len(validation_sessions) != self.config.validation_sessions
                or len(development_rows) != self.development.feature_row_count
                or len(validation_rows) != self.validation.feature_row_count
                or len(development_rows) < self.config.minimum_phase_rows
                or len(validation_rows) < self.config.minimum_phase_rows
            ):
                raise ValueError("ready SPY intraday MTF logistic input is invalid")
            _validate_sessions(development_sessions, self.config)
            _validate_sessions(validation_sessions, self.config)
            _validate_rows(development_rows, development_sessions, self.config)
            _validate_rows(validation_rows, validation_sessions, self.config)
        elif (
            self.reason
            not in {"insufficient_complete_regular_sessions", "insufficient_feature_rows"}
            or development_sessions
            or development_rows
            or validation_sessions
            or validation_rows
        ):
            raise ValueError("unavailable SPY intraday MTF logistic input is invalid")
        expected_hash = _input_hash(
            source=self.source,
            config=self.config,
            status=self.status,
            reason=self.reason,
            complete_regular_session_count=self.complete_regular_session_count,
            development=self.development,
            validation=self.validation,
        )
        if self.input_hash != expected_hash:
            raise ValueError("SPY intraday MTF logistic input identity is invalid")
        object.__setattr__(self, "_development_sessions", development_sessions)
        object.__setattr__(self, "_development_rows", development_rows)
        object.__setattr__(self, "_validation_sessions", validation_sessions)
        object.__setattr__(self, "_validation_rows", validation_rows)

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "campaign_id": SPY_INTRADAY_MTF_LOGISTIC_10M_ID,
            "source": self.source.safe_payload(),
            "contract": self.config.safe_payload(),
            "status": self.status,
            "reason": self.reason,
            "complete_regular_session_count": self.complete_regular_session_count,
            "phases": [self.development.safe_payload(), self.validation.safe_payload()],
            "input_hash": self.input_hash,
            "raw_market_data_written": False,
        }


@dataclass(frozen=True, slots=True)
class SpyIntradayMtfLogistic10mModel:
    """Private in-process standardization/coefficients; artifacts expose only a hash."""

    input_hash: str
    status: ModelStatus
    reason: str | None
    model_hash: str | None
    _mean: tuple[float, ...] = field(repr=False)
    _scale: tuple[float, ...] = field(repr=False)
    _coefficients: tuple[float, ...] = field(repr=False)
    _intercept: float = field(repr=False)

    def __post_init__(self) -> None:
        for name in ("_mean", "_scale", "_coefficients"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        if not _is_sha256(self.input_hash) or self.status not in {"ready", "input_unavailable"}:
            raise ValueError("SPY intraday MTF logistic model is invalid")
        values = (*self._mean, *self._scale, *self._coefficients, self._intercept)
        if self.status == "ready":
            if (
                self.reason is not None
                or not self.model_hash
                or not _is_sha256(self.model_hash)
                or len(self._mean) != len(SPY_INTRADAY_MTF_LOGISTIC_10M_FEATURE_NAMES)
                or len(self._scale) != len(SPY_INTRADAY_MTF_LOGISTIC_10M_FEATURE_NAMES)
                or len(self._coefficients) != len(SPY_INTRADAY_MTF_LOGISTIC_10M_FEATURE_NAMES)
                or any(not math.isfinite(value) for value in values)
                or any(value <= 0 for value in self._scale)
            ):
                raise ValueError("ready SPY intraday MTF logistic model is invalid")
        elif (
            self.reason != "development_single_target_class"
            or self.model_hash is not None
            or self._mean
            or self._scale
            or self._coefficients
            or self._intercept != 0.0
        ):
            raise ValueError("unavailable SPY intraday MTF logistic model is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "status": self.status,
            "reason": self.reason,
            "model": None
            if self.status == "input_unavailable"
            else {
                "family": "standardized_l2_logistic_regression",
                "feature_schema": list(SPY_INTRADAY_MTF_LOGISTIC_10M_FEATURE_NAMES),
                "class_weight": None,
                "c": _float_text(SPY_INTRADAY_MTF_LOGISTIC_10M_C),
                "fit_scope": "development_only",
                "model_hash": self.model_hash,
            },
        }

    def probability(self, features: tuple[float, ...]) -> float:
        if self.status != "ready":
            raise ValueError("SPY intraday MTF logistic model is unavailable")
        if len(features) != len(self._coefficients) or any(
            not math.isfinite(value) for value in features
        ):
            raise ValueError("SPY intraday MTF logistic feature vector is invalid")
        logit = self._intercept + sum(
            coefficient * ((value - mean) / scale)
            for value, mean, scale, coefficient in zip(
                features,
                self._mean,
                self._scale,
                self._coefficients,
                strict=True,
            )
        )
        if logit >= 0:
            return 1.0 / (1.0 + math.exp(-logit))
        exponential = math.exp(logit)
        return exponential / (1.0 + exponential)


@dataclass(frozen=True, slots=True)
class SpyIntradayMtfLogistic10mValidation:
    policy_long_decision_count: int
    always_long_decision_count: int
    policy_net_total_bps_by_cost: Mapping[str, Decimal]
    policy_net_mean_bps_by_cost: Mapping[str, Decimal]
    always_long_net_total_bps_by_cost: Mapping[str, Decimal]
    always_long_net_mean_bps_by_cost: Mapping[str, Decimal]
    kill_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "kill_reasons", tuple(self.kill_reasons))
        mappings = (
            self.policy_net_total_bps_by_cost,
            self.policy_net_mean_bps_by_cost,
            self.always_long_net_total_bps_by_cost,
            self.always_long_net_mean_bps_by_cost,
        )
        expected_keys = tuple(
            _decimal_text(cost) for cost in SPY_INTRADAY_MTF_LOGISTIC_10M_COST_BAND
        )
        if (
            self.policy_long_decision_count <= 0
            or self.always_long_decision_count < self.policy_long_decision_count
            or any(tuple(mapping) != expected_keys for mapping in mappings)
            or any(
                not isinstance(value, Decimal) for mapping in mappings for value in mapping.values()
            )
            or any(
                reason
                not in {
                    "policy_net_total_flat_or_worse_at_20bp",
                    "policy_mean_no_better_than_always_long_at_20bp",
                }
                for reason in self.kill_reasons
            )
        ):
            raise ValueError("SPY intraday MTF logistic validation is invalid")
        for attribute in (
            "policy_net_total_bps_by_cost",
            "policy_net_mean_bps_by_cost",
            "always_long_net_total_bps_by_cost",
            "always_long_net_mean_bps_by_cost",
        ):
            object.__setattr__(self, attribute, MappingProxyType(dict(getattr(self, attribute))))

    def safe_payload(self) -> dict[str, object]:
        return {
            "policy_long_decision_count": self.policy_long_decision_count,
            "always_long_decision_count": self.always_long_decision_count,
            "policy_net_total_bps_by_all_in_round_trip_cost": _safe_cost_mapping(
                self.policy_net_total_bps_by_cost
            ),
            "policy_net_mean_bps_by_all_in_round_trip_cost": _safe_cost_mapping(
                self.policy_net_mean_bps_by_cost
            ),
            "always_long_net_total_bps_by_all_in_round_trip_cost": _safe_cost_mapping(
                self.always_long_net_total_bps_by_cost
            ),
            "always_long_net_mean_bps_by_all_in_round_trip_cost": _safe_cost_mapping(
                self.always_long_net_mean_bps_by_cost
            ),
            "kill_reasons": list(self.kill_reasons),
        }


@dataclass(frozen=True, slots=True)
class SpyIntradayMtfLogistic10mResult:
    campaign_input: SpyIntradayMtfLogistic10mInput
    model: SpyIntradayMtfLogistic10mModel | None
    status: ResultStatus
    reason: str | None
    validation: SpyIntradayMtfLogistic10mValidation | None

    def __post_init__(self) -> None:
        if self.status not in {"input_unavailable", "falsified", "non_promoting_validation"}:
            raise ValueError("SPY intraday MTF logistic result status is invalid")
        if self.status == "input_unavailable":
            if self.validation is not None or self.reason not in {
                "insufficient_complete_regular_sessions",
                "insufficient_feature_rows",
                "development_single_target_class",
                "insufficient_validation_long_decisions",
            }:
                raise ValueError("unavailable SPY intraday MTF logistic result is invalid")
        elif (
            self.model is None
            or self.model.status != "ready"
            or self.validation is None
            or self.reason
        ):
            raise ValueError("evaluated SPY intraday MTF logistic result is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "campaign_id": SPY_INTRADAY_MTF_LOGISTIC_10M_ID,
            "status": self.status,
            "reason": self.reason,
            "input": self.campaign_input.safe_payload(),
            "model": None if self.model is None else self.model.safe_payload(),
            "validation": None if self.validation is None else self.validation.safe_payload(),
            "promotion_allowed": False,
            "candidate_selection_allowed": False,
            "ensemble_allowed": False,
            "paper_input_allowed": False,
            "profitability_claim_allowed": False,
            "gpu_eligible": False,
            "raw_market_data_written": False,
        }


@dataclass(frozen=True, slots=True)
class SpyIntradayMtfLogistic10mRun:
    result: SpyIntradayMtfLogistic10mResult
    precommit_path: Path
    precommit_hash: str
    summary_path: Path


def prepare_spy_intraday_mtf_logistic_10m(
    catalog: CatalogedBars,
    config: SpyIntradayMtfLogistic10mConfig | None = None,
) -> SpyIntradayMtfLogistic10mInput:
    """Construct completed-bar features before reading any development or validation target."""

    if not isinstance(catalog, CatalogedBars):
        raise TypeError("SPY intraday MTF logistic requires CatalogedBars")
    resolved_config = config or SpyIntradayMtfLogistic10mConfig()
    source = SpyIntradayMtfLogistic10mSource(
        dataset_id=catalog.dataset_id,
        dataset_hash=catalog.dataset_hash,
    )
    sessions = _complete_regular_sessions(catalog)
    if len(sessions) != resolved_config.complete_session_count:
        return _campaign_input(
            source=source,
            config=resolved_config,
            status="input_unavailable",
            reason="insufficient_complete_regular_sessions",
            complete_regular_session_count=len(sessions),
            development=_empty_phase("development"),
            validation=_empty_phase("validation"),
            development_sessions=(),
            development_rows=(),
            validation_sessions=(),
            validation_rows=(),
        )
    development, development_rows = _phase_rows(
        phase="development",
        sessions=sessions,
        start_index=0,
        stop_index=resolved_config.development_sessions,
        context_index_offset=0,
        config=resolved_config,
    )
    validation_start = resolved_config.development_sessions + resolved_config.purge_sessions
    validation_stop = validation_start + resolved_config.validation_sessions
    validation, validation_rows = _phase_rows(
        phase="validation",
        sessions=sessions,
        start_index=validation_start,
        stop_index=validation_stop,
        context_index_offset=validation_start,
        config=resolved_config,
    )
    if (
        development.feature_row_count < resolved_config.minimum_phase_rows
        or validation.feature_row_count < resolved_config.minimum_phase_rows
    ):
        return _campaign_input(
            source=source,
            config=resolved_config,
            status="input_unavailable",
            reason="insufficient_feature_rows",
            complete_regular_session_count=len(sessions),
            development=development,
            validation=validation,
            development_sessions=(),
            development_rows=(),
            validation_sessions=(),
            validation_rows=(),
        )
    return _campaign_input(
        source=source,
        config=resolved_config,
        status="ready",
        reason=None,
        complete_regular_session_count=len(sessions),
        development=development,
        validation=validation,
        development_sessions=tuple(
            sessions[index][1] for index in range(resolved_config.development_sessions)
        ),
        development_rows=development_rows,
        validation_sessions=tuple(
            sessions[index][1] for index in range(validation_start, validation_stop)
        ),
        validation_rows=validation_rows,
    )


def fit_spy_intraday_mtf_logistic_10m(
    campaign_input: SpyIntradayMtfLogistic10mInput,
) -> SpyIntradayMtfLogistic10mModel:
    """Fit exactly one scaler and L2 logistic model from development targets only."""

    # Keep import-time research modules inert; these CPU-only dependencies are
    # needed only when a frozen campaign actually reaches its fitting step.
    import numpy
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    if not isinstance(campaign_input, SpyIntradayMtfLogistic10mInput):
        raise TypeError("SPY intraday MTF logistic requires prepared input")
    if campaign_input.status == "input_unavailable":
        return _unavailable_model(campaign_input.input_hash)
    labels = numpy.asarray(
        [
            int(
                _target_return_bps(
                    campaign_input._development_sessions[row.session_index],
                    entry_index=row.entry_index,
                    config=campaign_input.config,
                )
                > 0
            )
            for row in campaign_input._development_rows
        ],
        dtype=numpy.int64,
    )
    if numpy.unique(labels).size != 2:
        return _unavailable_model(campaign_input.input_hash)
    features = numpy.asarray(
        [row.features for row in campaign_input._development_rows],
        dtype=numpy.float64,
    )
    scaler = StandardScaler()
    standardized = scaler.fit_transform(features)
    classifier = LogisticRegression(
        C=campaign_input.config.logistic_c,
        class_weight=None,
        max_iter=500,
        random_state=0,
        solver="lbfgs",
    )
    classifier.fit(standardized, labels)
    mean = tuple(float(value) for value in scaler.mean_)
    scale = tuple(float(value) for value in scaler.scale_)
    coefficients = tuple(float(value) for value in classifier.coef_[0])
    intercept = float(classifier.intercept_[0])
    model_hash = _sha256_json(
        {
            "input_hash": campaign_input.input_hash,
            "mean": [_float_text(value) for value in mean],
            "scale": [_float_text(value) for value in scale],
            "coefficients": [_float_text(value) for value in coefficients],
            "intercept": _float_text(intercept),
        }
    )
    return SpyIntradayMtfLogistic10mModel(
        input_hash=campaign_input.input_hash,
        status="ready",
        reason=None,
        model_hash=model_hash,
        _mean=mean,
        _scale=scale,
        _coefficients=coefficients,
        _intercept=intercept,
    )


def evaluate_spy_intraday_mtf_logistic_10m(
    campaign_input: SpyIntradayMtfLogistic10mInput,
    model: SpyIntradayMtfLogistic10mModel,
) -> SpyIntradayMtfLogistic10mResult:
    """Freeze validation policy decisions before reading validation target fields."""

    if not isinstance(campaign_input, SpyIntradayMtfLogistic10mInput):
        raise TypeError("SPY intraday MTF logistic requires prepared input")
    if not isinstance(model, SpyIntradayMtfLogistic10mModel):
        raise TypeError("SPY intraday MTF logistic requires fitted model")
    if model.input_hash != campaign_input.input_hash:
        raise ValueError("SPY intraday MTF logistic model/input identity conflicts")
    if campaign_input.status == "input_unavailable":
        return _unavailable_result(campaign_input, model, campaign_input.reason)
    if model.status == "input_unavailable":
        return _unavailable_result(campaign_input, model, model.reason)
    policy_rows = tuple(
        row
        for row in campaign_input._validation_rows
        if model.probability(row.features) >= campaign_input.config.threshold
    )
    if len(policy_rows) < campaign_input.config.minimum_validation_longs:
        return _unavailable_result(campaign_input, model, "insufficient_validation_long_decisions")
    policy_gross = tuple(
        _target_return_bps(
            campaign_input._validation_sessions[row.session_index],
            entry_index=row.entry_index,
            config=campaign_input.config,
        )
        for row in policy_rows
    )
    always_long_gross = tuple(
        _target_return_bps(
            campaign_input._validation_sessions[row.session_index],
            entry_index=row.entry_index,
            config=campaign_input.config,
        )
        for row in campaign_input._validation_rows
    )
    policy = _aggregate_returns(policy_gross, campaign_input.config)
    always_long = _aggregate_returns(always_long_gross, campaign_input.config)
    kill_key = _decimal_text(campaign_input.config.kill_cost)
    kill_reasons: list[str] = []
    if policy["total"][kill_key] <= 0:
        kill_reasons.append("policy_net_total_flat_or_worse_at_20bp")
    if policy["mean"][kill_key] <= always_long["mean"][kill_key]:
        kill_reasons.append("policy_mean_no_better_than_always_long_at_20bp")
    validation = SpyIntradayMtfLogistic10mValidation(
        policy_long_decision_count=len(policy_rows),
        always_long_decision_count=len(always_long_gross),
        policy_net_total_bps_by_cost=policy["total"],
        policy_net_mean_bps_by_cost=policy["mean"],
        always_long_net_total_bps_by_cost=always_long["total"],
        always_long_net_mean_bps_by_cost=always_long["mean"],
        kill_reasons=tuple(kill_reasons),
    )
    return SpyIntradayMtfLogistic10mResult(
        campaign_input=campaign_input,
        model=model,
        status="falsified" if validation.kill_reasons else "non_promoting_validation",
        reason=None,
        validation=validation,
    )


def run_spy_intraday_mtf_logistic_10m(
    catalog: CatalogedBars,
    *,
    artifact_root: Path | str,
    run_label: str,
    repo_root: Path | str,
) -> SpyIntradayMtfLogistic10mRun:
    """Prepare, fit, evaluate, and write idempotent source-safe external evidence."""

    resolved_label = _validated_run_label(run_label)
    root = _external_artifact_root(Path(artifact_root), Path(repo_root))
    campaign_input = prepare_spy_intraday_mtf_logistic_10m(catalog)
    precommit_payload = campaign_input.safe_payload()
    precommit_hash = _sha256_json(precommit_payload)
    model = fit_spy_intraday_mtf_logistic_10m(campaign_input)
    result = evaluate_spy_intraday_mtf_logistic_10m(campaign_input, model)
    summary_payload = {
        "precommit_hash": precommit_hash,
        "result": result.safe_payload(),
    }
    artifact_dir = root / "research" / SPY_INTRADAY_MTF_LOGISTIC_10M_ID / resolved_label
    _ensure_artifact_directory(root, artifact_dir)
    precommit_path = artifact_dir / "precommit.json"
    summary_path = artifact_dir / "summary.json"
    _write_or_verify(precommit_path, _canonical_json(precommit_payload))
    _write_or_verify(summary_path, _canonical_json(summary_payload))
    return SpyIntradayMtfLogistic10mRun(
        result=result,
        precommit_path=precommit_path,
        precommit_hash=precommit_hash,
        summary_path=summary_path,
    )


def _complete_regular_sessions(
    catalog: CatalogedBars,
) -> tuple[tuple[SessionWindow, tuple[Bar, ...]], ...]:
    if not catalog.dataset_id.startswith("kis.paper.private.intraday.spy.ams.m1.") or any(
        bar.symbol != SPY_INTRADAY_MTF_LOGISTIC_10M_SYMBOL
        or bar.market != SPY_INTRADAY_MTF_LOGISTIC_10M_MARKET
        or bar.timeframe != Timeframe.M1
        for bar in catalog.bars
    ):
        raise ValueError("SPY intraday MTF logistic catalog scope is invalid")
    candidate_dates = tuple(
        sorted({bar.start_ts.astimezone(US_EQUITY_EASTERN).date() for bar in catalog.bars})
    )
    complete: list[tuple[SessionWindow, tuple[Bar, ...]]] = []
    for session_date in candidate_dates:
        session = us_equity_2026_session(session_date)
        if session is None or session.kind != "regular":
            continue
        try:
            selected = require_complete_kis_paper_private_intraday_session(
                catalog,
                session=session.window,
            )
        except ValueError:
            continue
        complete.append((session.window, selected.bars))
    return tuple(complete)


def _phase_rows(
    *,
    phase: PhaseName,
    sessions: tuple[tuple[SessionWindow, tuple[Bar, ...]], ...],
    start_index: int,
    stop_index: int,
    context_index_offset: int,
    config: SpyIntradayMtfLogistic10mConfig,
) -> tuple[SpyIntradayMtfLogistic10mPhaseFacts, tuple[_RowContext, ...]]:
    scheduled = 0
    structural_unavailable = 0
    rows: list[_RowContext] = []
    for absolute_index in range(start_index, stop_index):
        session, session_bars = sessions[absolute_index]
        for entry_index in config.decision_indices:
            scheduled += 1
            features = _feature_values(
                session=session,
                session_bars=session_bars,
                entry_index=entry_index,
                config=config,
            )
            if features is None:
                structural_unavailable += 1
                continue
            rows.append(
                _RowContext(
                    session_index=absolute_index - context_index_offset,
                    entry_index=entry_index,
                    features=features,
                )
            )
    facts = SpyIntradayMtfLogistic10mPhaseFacts(
        phase=phase,
        session_count=stop_index - start_index,
        scheduled_row_count=scheduled,
        structural_unavailable_count=structural_unavailable,
        feature_row_count=len(rows),
    )
    return facts, tuple(rows)


def _feature_values(
    *,
    session: SessionWindow,
    session_bars: tuple[Bar, ...],
    entry_index: int,
    config: SpyIntradayMtfLogistic10mConfig,
) -> tuple[float, ...] | None:
    if entry_index + config.hold_bars >= len(session_bars) or entry_index < config.m1_lookback:
        return None
    source_bars = session_bars[:entry_index]
    if not source_bars or source_bars[-1].end_ts != (
        session.open_ts + Timeframe.M1.duration * entry_index
    ):
        return None
    m1_window = source_bars[-config.m1_lookback :]
    if len(m1_window) != config.m1_lookback or m1_window[0].close <= 0:
        return None
    resampled = {
        timeframe: resample_session_bars(source_bars, timeframe, session=session).bars
        for timeframe in (Timeframe.M5, Timeframe.M10, Timeframe.H1, Timeframe.H3)
    }
    if (
        len(resampled[Timeframe.M5]) <= config.m5_return_bars
        or len(resampled[Timeframe.M10]) <= config.m10_return_bars
        or not resampled[Timeframe.H1]
        or not resampled[Timeframe.H3]
    ):
        return None
    latest = {timeframe: values[-1] for timeframe, values in resampled.items()}
    if any(bar.end_ts > source_bars[-1].end_ts for bar in latest.values()):
        return None
    m5 = resampled[Timeframe.M5]
    m10 = resampled[Timeframe.M10]
    if (
        m5[-config.m5_return_bars - 1].close <= 0
        or m10[-config.m10_return_bars - 1].close <= 0
        or latest[Timeframe.H1].open <= 0
        or latest[Timeframe.H3].open <= 0
    ):
        return None
    values = (
        float(source_bars[-1].close / m1_window[0].close - Decimal("1")),
        float(
            max(bar.high for bar in m1_window) / min(bar.low for bar in m1_window) - Decimal("1")
        ),
        float(m5[-1].close / m5[-config.m5_return_bars - 1].close - Decimal("1")),
        float(m10[-1].close / m10[-config.m10_return_bars - 1].close - Decimal("1")),
        float(latest[Timeframe.H1].close / latest[Timeframe.H1].open - Decimal("1")),
        float(latest[Timeframe.H3].close / latest[Timeframe.H3].open - Decimal("1")),
    )
    return values if all(math.isfinite(value) for value in values) else None


def _empty_phase(phase: PhaseName) -> SpyIntradayMtfLogistic10mPhaseFacts:
    return SpyIntradayMtfLogistic10mPhaseFacts(
        phase=phase,
        session_count=0,
        scheduled_row_count=0,
        structural_unavailable_count=0,
        feature_row_count=0,
    )


def _campaign_input(
    *,
    source: SpyIntradayMtfLogistic10mSource,
    config: SpyIntradayMtfLogistic10mConfig,
    status: InputStatus,
    reason: str | None,
    complete_regular_session_count: int,
    development: SpyIntradayMtfLogistic10mPhaseFacts,
    validation: SpyIntradayMtfLogistic10mPhaseFacts,
    development_sessions: tuple[tuple[Bar, ...], ...],
    development_rows: tuple[_RowContext, ...],
    validation_sessions: tuple[tuple[Bar, ...], ...],
    validation_rows: tuple[_RowContext, ...],
) -> SpyIntradayMtfLogistic10mInput:
    return SpyIntradayMtfLogistic10mInput(
        source=source,
        config=config,
        status=status,
        reason=reason,
        complete_regular_session_count=complete_regular_session_count,
        development=development,
        validation=validation,
        input_hash=_input_hash(
            source=source,
            config=config,
            status=status,
            reason=reason,
            complete_regular_session_count=complete_regular_session_count,
            development=development,
            validation=validation,
        ),
        _development_sessions=development_sessions,
        _development_rows=development_rows,
        _validation_sessions=validation_sessions,
        _validation_rows=validation_rows,
    )


def _validate_sessions(
    sessions: tuple[tuple[Bar, ...], ...],
    config: SpyIntradayMtfLogistic10mConfig,
) -> None:
    for session in sessions:
        if len(session) <= config.last_entry_index + config.hold_bars or any(
            bar.symbol != SPY_INTRADAY_MTF_LOGISTIC_10M_SYMBOL
            or bar.market != SPY_INTRADAY_MTF_LOGISTIC_10M_MARKET
            or bar.timeframe != Timeframe.M1
            or not bar.complete
            for bar in session
        ):
            raise ValueError("SPY intraday MTF logistic sessions are invalid")


def _validate_rows(
    rows: tuple[_RowContext, ...],
    sessions: tuple[tuple[Bar, ...], ...],
    config: SpyIntradayMtfLogistic10mConfig,
) -> None:
    for row in rows:
        if row.session_index >= len(sessions):
            raise ValueError("SPY intraday MTF logistic row session is invalid")
        bars = sessions[row.session_index]
        if (
            row.entry_index not in config.decision_indices
            or row.entry_index + config.hold_bars >= len(bars)
        ):
            raise ValueError("SPY intraday MTF logistic row target is invalid")
        entry = bars[row.entry_index]
        exit_bar = bars[row.entry_index + config.hold_bars]
        if (
            entry.start_ts + Timeframe.M1.duration * config.hold_bars != exit_bar.start_ts
            or entry.end_ts > exit_bar.start_ts
        ):
            raise ValueError("SPY intraday MTF logistic row timing is invalid")


def _unavailable_model(input_hash: str) -> SpyIntradayMtfLogistic10mModel:
    return SpyIntradayMtfLogistic10mModel(
        input_hash=input_hash,
        status="input_unavailable",
        reason="development_single_target_class",
        model_hash=None,
        _mean=(),
        _scale=(),
        _coefficients=(),
        _intercept=0.0,
    )


def _unavailable_result(
    campaign_input: SpyIntradayMtfLogistic10mInput,
    model: SpyIntradayMtfLogistic10mModel,
    reason: str | None,
) -> SpyIntradayMtfLogistic10mResult:
    if reason not in {
        "insufficient_complete_regular_sessions",
        "insufficient_feature_rows",
        "development_single_target_class",
        "insufficient_validation_long_decisions",
    }:
        raise ValueError("SPY intraday MTF logistic unavailable result reason is invalid")
    return SpyIntradayMtfLogistic10mResult(
        campaign_input=campaign_input,
        model=model,
        status="input_unavailable",
        reason=reason,
        validation=None,
    )


def _target_return_bps(
    bars: tuple[Bar, ...],
    *,
    entry_index: int,
    config: SpyIntradayMtfLogistic10mConfig,
) -> Decimal:
    exit_index = entry_index + config.hold_bars
    entry = bars[entry_index]
    exit_bar = bars[exit_index]
    if (
        entry.open <= 0
        or entry.start_ts + Timeframe.M1.duration * config.hold_bars != exit_bar.start_ts
        or entry.end_ts > exit_bar.start_ts
    ):
        raise ValueError("SPY intraday MTF logistic target is invalid")
    return (exit_bar.open / entry.open - Decimal("1")) * Decimal("10000")


def _aggregate_returns(
    gross_returns: tuple[Decimal, ...],
    config: SpyIntradayMtfLogistic10mConfig,
) -> dict[str, Mapping[str, Decimal]]:
    if not gross_returns:
        raise ValueError("SPY intraday MTF logistic aggregate requires returns")
    totals: dict[str, Decimal] = {}
    means: dict[str, Decimal] = {}
    count = Decimal(len(gross_returns))
    for cost in config.cost_band:
        key = _decimal_text(cost)
        total = sum((gross - cost for gross in gross_returns), Decimal("0"))
        totals[key] = total
        means[key] = total / count
    return {"total": MappingProxyType(totals), "mean": MappingProxyType(means)}


def _input_hash(
    *,
    source: SpyIntradayMtfLogistic10mSource,
    config: SpyIntradayMtfLogistic10mConfig,
    status: InputStatus,
    reason: str | None,
    complete_regular_session_count: int,
    development: SpyIntradayMtfLogistic10mPhaseFacts,
    validation: SpyIntradayMtfLogistic10mPhaseFacts,
) -> str:
    return _sha256_json(
        {
            "source": source.safe_payload(),
            "contract": config.safe_payload(),
            "status": status,
            "reason": reason,
            "complete_regular_session_count": complete_regular_session_count,
            "phases": [development.safe_payload(), validation.safe_payload()],
        }
    )


def _validated_run_label(run_label: str) -> str:
    if not isinstance(run_label, str) or not _SAFE_RUN_LABEL.fullmatch(run_label):
        raise ValueError("SPY intraday MTF logistic run label is invalid")
    return run_label


def _external_artifact_root(artifact_root: Path, repo_root: Path) -> Path:
    root = artifact_root.resolve(strict=False)
    repository = repo_root.resolve(strict=False)
    docker_repository = Path("/app").resolve(strict=False)
    docker_artifacts = (docker_repository / "model_artifacts").resolve(strict=False)
    if root.is_relative_to(repository) and not (
        repository == docker_repository and root.is_relative_to(docker_artifacts)
    ):
        raise ValueError("SPY intraday MTF logistic artifacts must stay outside Git")
    if root.exists() and (root.is_symlink() or not root.is_dir()):
        raise ValueError("SPY intraday MTF logistic artifact root is invalid")
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve(strict=False)


def _ensure_artifact_directory(root: Path, artifact_dir: Path) -> None:
    if artifact_dir.exists() and (artifact_dir.is_symlink() or not artifact_dir.is_dir()):
        raise ValueError("SPY intraday MTF logistic artifact directory is invalid")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    if not artifact_dir.resolve(strict=False).is_relative_to(root):
        raise ValueError("SPY intraday MTF logistic artifact directory is invalid")


def _write_or_verify(path: Path, encoded: bytes) -> None:
    if path.exists():
        if path.is_symlink() or path.read_bytes() != encoded:
            raise ValueError("SPY intraday MTF logistic artifact conflicts with evidence")
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


def _float_text(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError("SPY intraday MTF logistic float is invalid")
    return format(value, ".17g")
