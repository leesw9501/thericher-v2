"""One frozen, source-local D1 candle-structure discrimination preflight."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, time
from decimal import Decimal, localcontext
from math import ceil, isfinite
from typing import Literal

import numpy
from sklearn.ensemble import HistGradientBoostingClassifier

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe

NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_PREFLIGHT_ID = (
    "norgate-d1-trio-intraday-structure-gbt-preflight-v1"
)
NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_SYMBOLS = ("SPY", "QQQ", "IWM")
NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_SESSION_COUNT = 511
NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_WINDOWS = (1, 5, 10, 20)
NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_DEVELOPMENT_DECISION_START = 20
NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_DEVELOPMENT_TARGET_END_EXCLUSIVE = 350
NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_PURGE_SESSION_COUNT = 21
NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_VALIDATION_DECISION_START = 371
NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_VALIDATION_DECISION_END_EXCLUSIVE = 510
NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_MIN_VALIDATION_DATE_GROUPS = 120
NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_NULL_SHIFTS = tuple(range(1, 65))
NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_NULL_PERCENTILE = 0.95
NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_MIN_BALANCED_ACCURACY_ADVANTAGE = 0.08
NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_RANDOM_STATE = 731

_DEVELOPMENT_DECISION_END_EXCLUSIVE = (
    NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_DEVELOPMENT_TARGET_END_EXCLUSIVE - 1
)
_FEATURE_WIDTH = 3 * len(NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_WINDOWS)
_EXPECTED_DEVELOPMENT_DATE_GROUPS = (
    _DEVELOPMENT_DECISION_END_EXCLUSIVE
    - NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_DEVELOPMENT_DECISION_START
)
_EXPECTED_VALIDATION_DATE_GROUPS = (
    NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_VALIDATION_DECISION_END_EXCLUSIVE
    - NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_VALIDATION_DECISION_START
)

ResultStatus = Literal[
    "noise_not_separable",
    "review_required",
    "alignment_suspect",
    "input_unavailable",
]
ResultReason = Literal[
    "strong_discrimination_requires_review",
    "one_session_shift_control_exceeded_threshold",
    "effect_floor_not_met",
    "date_block_null_threshold_not_met",
    "effect_and_null_threshold_not_met",
    "development_target_single_class",
    "validation_target_single_class",
]


@dataclass(frozen=True, slots=True)
class NorgateD1TrioIntradayStructureGbtPreflightResult:
    """Aggregate-only outcome; it is never an execution or PnL signal."""

    status: ResultStatus
    reason: ResultReason
    development_row_count: int
    validation_row_count: int
    validation_date_group_count: int
    feature_count: int
    always_flat_decision_count: int
    actual_balanced_accuracy: float | None
    always_long_balanced_accuracy: float | None
    null_p95_balanced_accuracy: float | None
    one_session_shift_balanced_accuracy: float | None
    effect_floor_met: bool
    null_threshold_met: bool
    alignment_control_passed: bool
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        expected_development_rows = (
            _EXPECTED_DEVELOPMENT_DATE_GROUPS
            * len(NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_SYMBOLS)
        )
        expected_validation_rows = (
            _EXPECTED_VALIDATION_DATE_GROUPS
            * len(NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_SYMBOLS)
        )
        if (
            self.schema_version != SCHEMA_VERSION
            or self.status not in {
                "noise_not_separable",
                "review_required",
                "alignment_suspect",
                "input_unavailable",
            }
            or self.reason
            not in {
                "strong_discrimination_requires_review",
                "one_session_shift_control_exceeded_threshold",
                "effect_floor_not_met",
                "date_block_null_threshold_not_met",
                "effect_and_null_threshold_not_met",
                "development_target_single_class",
                "validation_target_single_class",
            }
            or self.development_row_count != expected_development_rows
            or self.validation_row_count != expected_validation_rows
            or self.validation_date_group_count != _EXPECTED_VALIDATION_DATE_GROUPS
            or self.validation_date_group_count
            < NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_MIN_VALIDATION_DATE_GROUPS
            or self.feature_count != _FEATURE_WIDTH
            or self.always_flat_decision_count != 0
        ):
            raise ValueError("Norgate D1 intraday-structure GBT result geometry is invalid")

        metrics = (
            self.actual_balanced_accuracy,
            self.always_long_balanced_accuracy,
            self.null_p95_balanced_accuracy,
            self.one_session_shift_balanced_accuracy,
        )
        if self.status == "input_unavailable":
            if (
                self.reason
                not in {"development_target_single_class", "validation_target_single_class"}
                or any(value is not None for value in metrics)
                or self.effect_floor_met
                or self.null_threshold_met
                or self.alignment_control_passed
            ):
                raise ValueError("Norgate D1 intraday-structure GBT unavailable result is invalid")
            return

        if any(value is None or not 0.0 <= value <= 1.0 for value in metrics):
            raise ValueError("Norgate D1 intraday-structure GBT metrics are invalid")
        assert self.actual_balanced_accuracy is not None
        assert self.null_p95_balanced_accuracy is not None
        assert self.one_session_shift_balanced_accuracy is not None
        effect_floor = 0.5 + NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_MIN_BALANCED_ACCURACY_ADVANTAGE
        strong_threshold = max(effect_floor, self.null_p95_balanced_accuracy)
        if self.effect_floor_met != (self.actual_balanced_accuracy >= effect_floor):
            raise ValueError("Norgate D1 intraday-structure GBT effect floor is invalid")
        if self.null_threshold_met != (
            self.actual_balanced_accuracy > self.null_p95_balanced_accuracy
        ):
            raise ValueError("Norgate D1 intraday-structure GBT null threshold is invalid")
        if self.alignment_control_passed != (
            self.one_session_shift_balanced_accuracy < strong_threshold
        ):
            raise ValueError("Norgate D1 intraday-structure GBT shift control is invalid")
        if self.status == "review_required":
            if (
                self.reason != "strong_discrimination_requires_review"
                or not self.effect_floor_met
                or not self.null_threshold_met
                or not self.alignment_control_passed
            ):
                raise ValueError("Norgate D1 intraday-structure GBT review result is invalid")
        elif self.status == "alignment_suspect":
            if (
                self.reason != "one_session_shift_control_exceeded_threshold"
                or not self.effect_floor_met
                or not self.null_threshold_met
                or self.alignment_control_passed
            ):
                raise ValueError("Norgate D1 intraday-structure GBT alignment result is invalid")
        elif self.status == "noise_not_separable":
            expected_reason = (
                "effect_and_null_threshold_not_met"
                if not self.effect_floor_met and not self.null_threshold_met
                else (
                    "effect_floor_not_met"
                    if not self.effect_floor_met
                    else "date_block_null_threshold_not_met"
                )
            )
            if self.reason != expected_reason:
                raise ValueError("Norgate D1 intraday-structure GBT noise result is invalid")

    def safe_payload(self) -> dict[str, object]:
        """Return categories and counts without bars, dates, labels, or predictions."""

        return {
            "campaign_id": NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_PREFLIGHT_ID,
            "status": self.status,
            "reason": self.reason,
            "development_row_count": self.development_row_count,
            "validation_row_count": self.validation_row_count,
            "validation_date_group_count": self.validation_date_group_count,
            "feature_count": self.feature_count,
            "always_flat_decision_count": self.always_flat_decision_count,
            "metrics": {
                "actual_balanced_accuracy": _metric_category(self.actual_balanced_accuracy),
                "always_long_balanced_accuracy": _metric_category(
                    self.always_long_balanced_accuracy
                ),
                "null_p95_balanced_accuracy": _metric_category(self.null_p95_balanced_accuracy),
                "one_session_shift_balanced_accuracy": _metric_category(
                    self.one_session_shift_balanced_accuracy
                ),
                "effect_floor_met": self.effect_floor_met,
                "null_threshold_met": self.null_threshold_met,
                "alignment_control_passed": self.alignment_control_passed,
            },
            "promotion_allowed": False,
            "paper_input_eligible": False,
            "gpu_eligible": False,
            "pnl_evaluated": False,
        }


def frozen_norgate_d1_trio_intraday_structure_gbt_contract() -> dict[str, object]:
    """Return the complete fixed contract for this one non-promoting preflight."""

    return {
        "campaign_id": NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_PREFLIGHT_ID,
        "symbols": list(NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_SYMBOLS),
        "session_count": NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_SESSION_COUNT,
        "decision": "completed_d1_bar_t",
        "features": {
            "same_session_ratio_features": ["body", "range", "close_location"],
            "windows": list(NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_WINDOWS),
            "cross_session_price_ratios_allowed": False,
            "price_levels_allowed": False,
            "calendar_features_allowed": False,
            "volume_allowed": False,
        },
        "target": "next_session_close_over_open_strictly_positive",
        "uniform_per_session_ohlcv_multiplier_invariant": True,
        "split": {
            "development_decision_indices": [
                NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_DEVELOPMENT_DECISION_START,
                _DEVELOPMENT_DECISION_END_EXCLUSIVE - 1,
            ],
            "purge_session_indices": [
                NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_DEVELOPMENT_TARGET_END_EXCLUSIVE,
                NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_VALIDATION_DECISION_START - 1,
            ],
            "validation_decision_indices": [
                NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_VALIDATION_DECISION_START,
                NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_VALIDATION_DECISION_END_EXCLUSIVE - 1,
            ],
            "development_date_groups": _EXPECTED_DEVELOPMENT_DATE_GROUPS,
            "purge_session_count": NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_PURGE_SESSION_COUNT,
            "validation_date_groups": _EXPECTED_VALIDATION_DATE_GROUPS,
            "development_validation_feature_overlap": False,
            "development_validation_target_overlap": False,
        },
        "model": {
            "kind": "sklearn_hist_gradient_boosting_classifier",
            "learning_rate": 0.05,
            "max_iter": 64,
            "max_leaf_nodes": 7,
            "min_samples_leaf": 20,
            "l2_regularization": 0.1,
            "early_stopping": False,
            "random_state": NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_RANDOM_STATE,
        },
        "evaluation": {
            "metric": "balanced_accuracy",
            "date_block_null": {
                "kind": "nonzero_circular_label_shifts",
                "shifts": list(NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_NULL_SHIFTS),
                "percentile": NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_NULL_PERCENTILE,
            },
            "minimum_validation_date_groups": (
                NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_MIN_VALIDATION_DATE_GROUPS
            ),
            "minimum_balanced_accuracy_advantage_over_half": (
                NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_MIN_BALANCED_ACCURACY_ADVANTAGE
            ),
            "one_session_label_shift_control": True,
            "always_flat_recorded": True,
            "always_long_recorded": True,
            "after_cost_pnl_evaluated": False,
        },
        "scope": {
            "promotion_allowed": False,
            "paper_input_allowed": False,
            "gpu_eligible": False,
            "sealed_holdout_allowed": False,
            "ensemble_allowed": False,
            "public_weights_allowed": False,
        },
    }


def run_norgate_d1_trio_intraday_structure_gbt_preflight(
    bars_by_symbol: Mapping[str, Sequence[Bar]],
) -> NorgateD1TrioIntradayStructureGbtPreflightResult:
    """Fit one fixed CPU model and compare it only with frozen null controls."""

    streams = _validated_panel(bars_by_symbol)
    development_features, development_labels = _sample_matrix(
        streams,
        range(
            NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_DEVELOPMENT_DECISION_START,
            _DEVELOPMENT_DECISION_END_EXCLUSIVE,
        ),
    )
    validation_features, validation_labels = _sample_matrix(
        streams,
        range(
            NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_VALIDATION_DECISION_START,
            NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_VALIDATION_DECISION_END_EXCLUSIVE,
        ),
    )
    common = {
        "development_row_count": int(development_features.shape[0]),
        "validation_row_count": int(validation_features.shape[0]),
        "validation_date_group_count": _EXPECTED_VALIDATION_DATE_GROUPS,
        "feature_count": int(development_features.shape[1]),
        "always_flat_decision_count": 0,
    }
    if numpy.unique(development_labels).size != 2:
        return NorgateD1TrioIntradayStructureGbtPreflightResult(
            status="input_unavailable",
            reason="development_target_single_class",
            actual_balanced_accuracy=None,
            always_long_balanced_accuracy=None,
            null_p95_balanced_accuracy=None,
            one_session_shift_balanced_accuracy=None,
            effect_floor_met=False,
            null_threshold_met=False,
            alignment_control_passed=False,
            **common,
        )
    if numpy.unique(validation_labels).size != 2:
        return NorgateD1TrioIntradayStructureGbtPreflightResult(
            status="input_unavailable",
            reason="validation_target_single_class",
            actual_balanced_accuracy=None,
            always_long_balanced_accuracy=None,
            null_p95_balanced_accuracy=None,
            one_session_shift_balanced_accuracy=None,
            effect_floor_met=False,
            null_threshold_met=False,
            alignment_control_passed=False,
            **common,
        )

    model = _new_model()
    model.fit(development_features, development_labels)
    predictions = numpy.asarray(model.predict(validation_features), dtype=numpy.int8)
    actual = _balanced_accuracy(validation_labels, predictions)
    always_long = _balanced_accuracy(
        validation_labels,
        numpy.ones(validation_labels.shape[0], dtype=numpy.int8),
    )
    labels_by_date = validation_labels.reshape(
        _EXPECTED_VALIDATION_DATE_GROUPS,
        len(NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_SYMBOLS),
    )
    null_scores = tuple(
        _balanced_accuracy(
            numpy.roll(labels_by_date, shift=shift, axis=0).reshape(-1),
            predictions,
        )
        for shift in NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_NULL_SHIFTS
    )
    null_p95 = _percentile(null_scores, NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_NULL_PERCENTILE)
    one_session_shift = null_scores[0]
    effect_floor = 0.5 + NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_MIN_BALANCED_ACCURACY_ADVANTAGE
    effect_floor_met = actual >= effect_floor
    null_threshold_met = actual > null_p95
    alignment_control_passed = one_session_shift < max(effect_floor, null_p95)
    if effect_floor_met and null_threshold_met:
        if alignment_control_passed:
            status: ResultStatus = "review_required"
            reason: ResultReason = "strong_discrimination_requires_review"
        else:
            status = "alignment_suspect"
            reason = "one_session_shift_control_exceeded_threshold"
    else:
        status = "noise_not_separable"
        if not effect_floor_met and not null_threshold_met:
            reason = "effect_and_null_threshold_not_met"
        elif not effect_floor_met:
            reason = "effect_floor_not_met"
        else:
            reason = "date_block_null_threshold_not_met"
    return NorgateD1TrioIntradayStructureGbtPreflightResult(
        status=status,
        reason=reason,
        actual_balanced_accuracy=actual,
        always_long_balanced_accuracy=always_long,
        null_p95_balanced_accuracy=null_p95,
        one_session_shift_balanced_accuracy=one_session_shift,
        effect_floor_met=effect_floor_met,
        null_threshold_met=null_threshold_met,
        alignment_control_passed=alignment_control_passed,
        **common,
    )


def _validated_panel(
    bars_by_symbol: Mapping[str, Sequence[Bar]],
) -> dict[str, tuple[Bar, ...]]:
    if not isinstance(bars_by_symbol, Mapping):
        raise TypeError("bars_by_symbol must be a mapping")
    if set(bars_by_symbol) != set(NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_SYMBOLS):
        raise ValueError("Norgate D1 intraday-structure panel symbols are invalid")
    result: dict[str, tuple[Bar, ...]] = {}
    reference_starts: tuple[object, ...] | None = None
    for symbol in NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_SYMBOLS:
        bars = tuple(bars_by_symbol[symbol])
        if len(bars) != NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_SESSION_COUNT or any(
            not isinstance(bar, Bar)
            or bar.symbol != symbol
            or bar.market != "US"
            or bar.timeframe is not Timeframe.D1
            or not bar.complete
            or bar.start_ts.tzinfo is not UTC
            or bar.start_ts.time() != time()
            or not _valid_ohlcv_geometry(bar)
            for bar in bars
        ):
            raise ValueError("Norgate D1 intraday-structure panel bars are invalid")
        starts = tuple(bar.start_ts for bar in bars)
        if any(later <= earlier for earlier, later in zip(starts, starts[1:], strict=False)):
            raise ValueError("Norgate D1 intraday-structure sessions must be chronological")
        if reference_starts is None:
            reference_starts = starts
        elif starts != reference_starts:
            raise ValueError("Norgate D1 intraday-structure panel sessions are misaligned")
        result[symbol] = bars
    return result


def _valid_ohlcv_geometry(bar: Bar) -> bool:
    return (
        bar.open > 0
        and bar.high > 0
        and bar.low > 0
        and bar.close > 0
        and bar.high >= max(bar.open, bar.close)
        and bar.low <= min(bar.open, bar.close)
    )


def _sample_matrix(
    streams: Mapping[str, tuple[Bar, ...]],
    decision_indices: range,
) -> tuple[numpy.ndarray, numpy.ndarray]:
    rows: list[list[float]] = []
    labels: list[int] = []
    for index in decision_indices:
        for symbol in NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_SYMBOLS:
            bars = streams[symbol]
            rows.append(_feature_vector(bars, index))
            labels.append(_next_session_label(bars, index))
    return (
        numpy.asarray(rows, dtype=numpy.float64),
        numpy.asarray(labels, dtype=numpy.int8),
    )


def _feature_vector(bars: Sequence[Bar], index: int) -> list[float]:
    if index < max(NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_WINDOWS) - 1:
        raise ValueError("Norgate D1 intraday-structure feature index is invalid")
    features: list[float] = []
    for window in NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_WINDOWS:
        values = [_candle_ratios(bar) for bar in bars[index - window + 1 : index + 1]]
        for column in range(3):
            features.append(float(sum(value[column] for value in values) / Decimal(window)))
    return features


def _candle_ratios(bar: Bar) -> tuple[Decimal, Decimal, Decimal]:
    with localcontext() as context:
        context.prec = 34
        body = bar.close / bar.open - Decimal("1")
        candle_range = bar.high / bar.low - Decimal("1")
        span = bar.high - bar.low
        close_location = Decimal("0.5") if span == 0 else (bar.close - bar.low) / span
    return body, candle_range, close_location


def _next_session_label(bars: Sequence[Bar], index: int) -> int:
    target_index = index + 1
    if target_index >= len(bars):
        raise ValueError("Norgate D1 intraday-structure target index is invalid")
    return int(bars[target_index].close > bars[target_index].open)


def _new_model() -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        learning_rate=0.05,
        max_iter=64,
        max_leaf_nodes=7,
        min_samples_leaf=20,
        l2_regularization=0.1,
        early_stopping=False,
        random_state=NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_RANDOM_STATE,
    )


def _balanced_accuracy(labels: numpy.ndarray, predictions: numpy.ndarray) -> float:
    if labels.shape != predictions.shape or labels.ndim != 1:
        raise ValueError("Norgate D1 intraday-structure metric geometry is invalid")
    positive = labels == 1
    negative = labels == 0
    if not positive.any() or not negative.any():
        raise ValueError("Norgate D1 intraday-structure metric requires both classes")
    value = 0.5 * (
        float((predictions[positive] == 1).mean())
        + float((predictions[negative] == 0).mean())
    )
    if not isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError("Norgate D1 intraday-structure metric is invalid")
    return value


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values or not 0.0 < percentile <= 1.0:
        raise ValueError("Norgate D1 intraday-structure null percentile is invalid")
    ordered = sorted(values)
    index = ceil(percentile * len(ordered)) - 1
    result = float(ordered[index])
    if not isfinite(result) or not 0.0 <= result <= 1.0:
        raise ValueError("Norgate D1 intraday-structure null scores are invalid")
    return result


def _metric_category(value: float | None) -> str:
    if value is None:
        return "not_evaluated"
    effect_floor = 0.5 + NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_MIN_BALANCED_ACCURACY_ADVANTAGE
    if value >= effect_floor:
        return "at_or_above_effect_floor"
    if value >= 0.5:
        return "at_or_above_chance_below_effect_floor"
    return "below_chance"
