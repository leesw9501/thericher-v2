"""Fixed, descriptive evaluation of frozen development variance losses.

Scheduled halves never move after exclusions. Shared-date deletion only removes
frozen losses; it cannot refit, tune, promote a model or create a Paper input.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from math import fsum, isclose, isfinite
from numbers import Real

from thericher_v2.research.forward_variance_baseline import (
    VarianceComparison,
    VariancePrediction,
    VarianceScore,
)

SYMBOLS = ("QQQ", "SPY")
GROUPS = (("all90", 0, 90), ("first45", 0, 45), ("last45", 45, 90))
MODEL_ORDER = ("log_ridge", "past_variance", "train_mean")
PAIRED_DIFFERENCE_ORDER = ("ridge_minus_past_variance", "ridge_minus_train_mean")
SCOPE = "non_promoting_forward_risk"
REASON = re.compile(r"(?:input|target):[a-z][a-z0-9_]*\Z")


def _triple(value: object, *, positive: bool = False) -> tuple[float, float, float]:
    if not isinstance(value, tuple) or len(value) != 3:
        raise ValueError("values must be a common three-model tuple")
    result = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, Real):
            raise ValueError("values must be finite nonnegative numeric data")
        try:
            number = float(item)
        except (ValueError, OverflowError) as exc:
            raise ValueError("values must be finite nonnegative numeric data") from exc
        if not isfinite(number) or number < 0 or (positive and number == 0):
            raise ValueError("values must be finite nonnegative data; forecasts must be positive")
        result.append(number)
    return tuple(result)


def _reasons(value: object) -> tuple[str, ...]:
    if (
        not isinstance(value, tuple)
        or any(not isinstance(reason, str) or not REASON.fullmatch(reason) for reason in value)
        or len(set(value)) != len(value)
    ):
        raise ValueError("exclusions must be distinct, source-safe input/target categories")
    return value


def _means(losses: tuple[tuple[float, float, float], ...]) -> tuple[float, ...] | None:
    return (
        tuple(fsum(loss[index] / len(losses) for loss in losses) for index in range(3))
        if losses
        else None
    )


def _paired(losses: tuple[tuple[float, float, float], ...]) -> tuple[float, ...] | None:
    return (
        tuple(fsum((loss[0] - loss[index]) / len(losses) for loss in losses) for index in (1, 2))
        if losses
        else None
    )


def _beats_both(differences: tuple[float, ...] | None) -> bool:
    return differences is not None and all(value < 0 for value in differences)


def _validated_rows(
    comparison: VarianceComparison, dates: tuple[date, ...]
) -> tuple[VarianceScore, ...]:
    if (
        not isinstance(comparison, VarianceComparison)
        or comparison.scope != SCOPE
        or not isinstance(comparison.rows, tuple)
        or len(comparison.rows) != len(dates)
    ):
        raise ValueError("comparison must retain exactly the scheduled rows and scope")
    previous = None
    losses = []
    for row, day in zip(comparison.rows, dates, strict=True):
        if not isinstance(row, VarianceScore) or not isinstance(row.prediction, VariancePrediction):
            raise ValueError("rows must be VarianceScore with VariancePrediction")
        prediction = row.prediction
        at = prediction.decision_at
        if (
            type(prediction.session_date) is not date
            or prediction.session_date != day
            or not isinstance(at, datetime)
            or at.tzinfo is None
            or at.utcoffset() != timedelta(0)
            or at.second != 0
            or at.microsecond != 0
            or (previous is not None and at <= previous)
        ):
            raise ValueError("rows must match ordered scheduled dates and UTC minute decisions")
        previous = at
        inputs, exclusions = _reasons(prediction.exclusions), _reasons(row.exclusions)
        if (
            any(not reason.startswith("input:") for reason in inputs)
            or exclusions[: len(inputs)] != inputs
            or any(not reason.startswith("target:") for reason in exclusions[len(inputs) :])
        ):
            raise ValueError("score exclusions must preserve input and target cohort reasons")
        if type(prediction.ridge_clipped) is not bool or type(prediction.past_floored) is not bool:
            raise ValueError("forecast flags must be boolean")
        forecasts = (prediction.log_ridge, prediction.past_variance, prediction.train_mean)
        if inputs:
            if any(value is not None for value in forecasts) or (
                prediction.ridge_clipped or prediction.past_floored
            ):
                raise ValueError("excluded inputs must have no forecasts or flags")
        else:
            _triple(forecasts, positive=True)
        if exclusions:
            if row.qlike is not None:
                raise ValueError("excluded scores must be absent")
        else:
            losses.append(_triple(row.qlike))
    if type(comparison.scored_count) is not int or comparison.scored_count != len(losses):
        raise ValueError("scored_count must match the common cohort")
    means = _means(tuple(losses))
    if means is None:
        if comparison.mean_qlike is not None:
            raise ValueError("empty cohort must have no mean scores")
    elif comparison.mean_qlike is None or any(
        not isclose(actual, expected, rel_tol=1e-12, abs_tol=0)
        for actual, expected in zip(_triple(comparison.mean_qlike), means, strict=True)
    ):
        raise ValueError("mean_qlike must match the frozen common-cohort losses")
    return comparison.rows


def _group(rows: tuple[VarianceScore, ...], dates: tuple[date, ...]) -> dict[str, object]:
    eligible = tuple(
        (row.prediction.session_date, _triple(row.qlike)) for row in rows if not row.exclusions
    )
    losses = tuple(loss for _, loss in eligible)
    paired = _paired(losses)
    # Every deletion uses the same shared date, including excluded or out-of-half dates.
    deletions = tuple(
        _paired(tuple(loss for row_date, loss in eligible if row_date != day)) for day in dates
    )
    defined = tuple(value for value in deletions if value is not None)
    reasons = Counter(reason for row in rows for reason in row.exclusions)
    return {
        "scheduled_count": len(rows),
        "eligible_count": len(eligible),
        "excluded_count": len(rows) - len(eligible),
        "exclusion_reasons": dict(sorted(reasons.items())),
        "scheduled_ridge_clipped_count": sum(row.prediction.ridge_clipped for row in rows),
        "scheduled_past_floored_count": sum(row.prediction.past_floored for row in rows),
        "mean_qlike": _means(losses),
        "paired_differences": paired,
        "incremental_premise": _beats_both(paired),
        "leave_one_shared_date_out": {
            "checked_date_count": len(dates),
            "undefined_count": len(deletions) - len(defined),
            "failed_date_count": sum(not _beats_both(value) for value in deletions),
            "worst_paired_differences": (
                tuple(max(value[index] for value in defined) for index in (0, 1))
                if defined
                else None
            ),
            "incremental_premise": all(_beats_both(value) for value in deletions),
        },
    }


def evaluate_variance_baselines(
    comparisons: Mapping[str, VarianceComparison], *, comparison_dates: tuple[date, ...]
) -> dict[str, object]:
    """Evaluate QQQ/SPY on 90 scheduled dates, never filtering before splitting.

    Means and paired differences use each ETF's common positive-target cohort.
    Negative ridge-minus-control differences must hold in all three groups and
    all 90 shared-date deletions for every group. Empty/undefined or equal scores
    reject only this incremental development premise, not an independent lane.
    Comparison metadata is cross-checked with 1e-12 relative rounding tolerance;
    the incremental rule has no tolerance. Symbol provenance remains caller-owned
    because VarianceComparison contains no instrument field.
    """
    if (
        not isinstance(comparison_dates, tuple)
        or len(comparison_dates) != 90
        or any(type(day) is not date for day in comparison_dates)
        or any(
            left >= right
            for left, right in zip(comparison_dates, comparison_dates[1:], strict=False)
        )
    ):
        raise ValueError("comparison_dates must be exactly 90 ordered unique date keys")
    if not isinstance(comparisons, Mapping) or set(comparisons) != set(SYMBOLS):
        raise ValueError("comparisons must have exactly QQQ and SPY symbol scope")
    rows = {symbol: _validated_rows(comparisons[symbol], comparison_dates) for symbol in SYMBOLS}
    if any(
        qqq.prediction.decision_at != spy.prediction.decision_at
        for qqq, spy in zip(rows["QQQ"], rows["SPY"], strict=True)
    ):
        raise ValueError("QQQ and SPY decisions must align on each shared scheduled date")
    etfs = {
        symbol: {
            name: _group(rows[symbol][start:stop], comparison_dates) for name, start, stop in GROUPS
        }
        for symbol in SYMBOLS
    }
    supported = all(
        group["incremental_premise"] and group["leave_one_shared_date_out"]["incremental_premise"]
        for groups in etfs.values()
        for group in groups.values()
    )
    return {
        "scope": SCOPE,
        "status": "supported-development-premise" if supported else "rejected",
        "loss": "normalized_qlike",
        "model_order": MODEL_ORDER,
        "paired_difference_order": PAIRED_DIFFERENCE_ORDER,
        "scheduled_date_count": len(comparison_dates),
        "group_order": tuple(name for name, _, _ in GROUPS),
        "etfs": etfs,
        "limitations": (
            "complete_positive_target_cohort_only",
            "zero_targets_excluded_not_floored",
            "missingness_not_imputed",
            "seen_source_development_not_promotion",
            "symbol_and_source_provenance_caller_owned",
        ),
    }
