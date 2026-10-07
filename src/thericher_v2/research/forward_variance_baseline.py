"""Pure CPU development controls for caller-owned causal session records.

One symbol/horizon, one fixed L2=1 log-variance fit, no selection or refitting.
Complete positive-target TRAIN rows alone set population scalers and coefficients.
QLIKE is y/f - log(y/f) - 1 on a common positive-target comparison cohort.
Zero targets are retained as explicit log-domain exclusions, not floored labels.
All outputs are non-promoting risk predictions, never returns or orders.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from math import exp, expm1, isfinite, log
from numbers import Real

import numpy as np

from thericher_v2.research.intraday_variance_targets import IntradayVarianceTarget

FORECAST_FLOOR = 1e-12
FORECAST_CEILING = 1e12
SCALE_FLOOR = 1e-12
RIDGE_PENALTY = 1.0
MINUTE = timedelta(minutes=1)


@dataclass(frozen=True, slots=True, repr=False)
class ForwardVarianceBaselineConfig:
    symbol: str
    feature_names: tuple[str, ...]
    train_through: date
    comparison_from: date
    horizon_minutes: int
    past_return_count: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.symbol, str)
            or not self.symbol
            or self.symbol != self.symbol.strip().upper()
        ):
            raise ValueError("symbol must be canonical")
        if (
            not isinstance(self.feature_names, tuple)
            or not self.feature_names
            or any(not isinstance(name, str) or not name.strip() for name in self.feature_names)
            or len(set(self.feature_names)) != len(self.feature_names)
        ):
            raise ValueError("feature_names must be distinct nonempty names in a frozen tuple")
        if (
            type(self.train_through) is not date
            or type(self.comparison_from) is not date
            or self.train_through >= self.comparison_from
        ):
            raise ValueError("TRAIN must precede comparison dates")
        if any(
            type(value) is not int or value <= 0
            for value in (self.horizon_minutes, self.past_return_count)
        ):
            raise ValueError("horizon_minutes and past_return_count must be positive integers")


@dataclass(frozen=True, slots=True, repr=False)
class ForwardVarianceRecord:
    """One scheduled session; input availability covers features AND past variance.

    The caller owns session-date mapping, causal construction and the declared
    past-return count. This helper validates their contract, not source finality.
    """

    session_date: date
    symbol: str
    decision_at: datetime
    features_available_at: datetime | None
    features: tuple[float, ...] | None
    past_realized_variance: float | None
    target: IntradayVarianceTarget | None
    input_status: str = "available"
    target_status: str = "available"


@dataclass(frozen=True, slots=True, repr=False)
class ForwardVarianceBaseline:
    config: ForwardVarianceBaselineConfig
    feature_mean: tuple[float, ...]
    feature_scale: tuple[float, ...]
    coefficients: tuple[float, ...]
    intercept: float
    train_mean_variance: float
    train_available_through: datetime
    training_rows: tuple[tuple[date, tuple[str, ...]], ...]
    scope: str = field(default="non_promoting_forward_risk", init=False)


@dataclass(frozen=True, slots=True, repr=False)
class VariancePrediction:
    session_date: date
    decision_at: datetime
    exclusions: tuple[str, ...]
    log_ridge: float | None
    past_variance: float | None
    train_mean: float | None
    ridge_clipped: bool = False
    past_floored: bool = False


@dataclass(frozen=True, slots=True, repr=False)
class VarianceScore:
    prediction: VariancePrediction
    exclusions: tuple[str, ...]
    qlike: tuple[float, float, float] | None


@dataclass(frozen=True, slots=True, repr=False)
class VarianceComparison:
    rows: tuple[VarianceScore, ...]
    scored_count: int
    mean_qlike: tuple[float, float, float] | None
    scope: str = field(default="non_promoting_forward_risk", init=False)


def _utc_minute(value: datetime, name: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
        or value.second != 0
        or value.microsecond != 0
    ):
        raise ValueError(f"{name} must be UTC and minute-aligned")


def _finite(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be finite numeric data")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} must be finite numeric data") from exc
    if not isfinite(result):
        raise ValueError(f"{name} must be finite numeric data")
    return result


def _records(
    records: Sequence[ForwardVarianceRecord], config: ForwardVarianceBaselineConfig
) -> tuple[ForwardVarianceRecord, ...]:
    rows = tuple(records)
    for index, row in enumerate(rows):
        if (
            not isinstance(row, ForwardVarianceRecord)
            or type(row.session_date) is not date
            or row.symbol != config.symbol
        ):
            raise ValueError("records must have the declared symbol and session identity")
        _utc_minute(row.decision_at, "decision_at")
        if index and (
            rows[index - 1].session_date >= row.session_date
            or rows[index - 1].decision_at >= row.decision_at
        ):
            raise ValueError("records must be chronological with one record per session")
    return rows


def _status(value: str, name: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{name} must be an explicit nonempty status")


def _inputs(row: ForwardVarianceRecord, config: ForwardVarianceBaselineConfig) -> tuple[str, ...]:
    _status(row.input_status, "input_status")
    if row.input_status != "available":
        if any(
            value is not None
            for value in (row.features, row.features_available_at, row.past_realized_variance)
        ):
            raise ValueError("unavailable inputs must have no payload")
        return (f"input:{row.input_status}",)
    _utc_minute(row.features_available_at, "features_available_at")
    if row.features_available_at > row.decision_at:
        raise ValueError("features must be available by decision_at")
    if not isinstance(row.features, tuple) or len(row.features) != len(config.feature_names):
        raise ValueError("available features must match the frozen feature schema")
    for value in row.features:
        _finite(value, "feature")
    if _finite(row.past_realized_variance, "past_realized_variance") < 0:
        raise ValueError("past_realized_variance must be nonnegative")
    return ()


def _target(
    row: ForwardVarianceRecord, config: ForwardVarianceBaselineConfig
) -> tuple[float | None, tuple[str, ...]]:
    _status(row.target_status, "target_status")
    if row.target_status != "available":
        if row.target is not None:
            raise ValueError("unavailable target must have no payload")
        return None, (f"target:{row.target_status}",)
    target = row.target
    if not isinstance(target, IntradayVarianceTarget):
        raise ValueError("available target must be an IntradayVarianceTarget")
    for name in ("decision_at", "target_start", "target_end", "available_at"):
        _utc_minute(getattr(target, name), f"target.{name}")
    if (
        target.symbol != row.symbol
        or target.decision_at != row.decision_at
        or type(target.horizon_minutes) is not int
        or target.horizon_minutes != config.horizon_minutes
        or target.target_start != row.decision_at + MINUTE
        or target.target_end != target.target_start + config.horizon_minutes * MINUTE
        or target.available_at != target.target_end + MINUTE
    ):
        raise ValueError("target must match the declared forward OPEN variance geometry")
    value = _finite(target.realized_variance, "target variance")
    if value < 0:
        raise ValueError("target variance must be nonnegative")
    return value, ("target:zero_log_domain",) if value == 0 else ()


def fit_forward_variance_baseline(
    records: Sequence[ForwardVarianceRecord], *, config: ForwardVarianceBaselineConfig
) -> ForwardVarianceBaseline:
    """Fit once; later/embargo payloads are never inspected, even for validation.

    Cuts use scheduled session dates BEFORE exclusions; missing rows cannot move
    a later observation into TRAIN. The TRAIN mean uses the same complete cohort.
    """
    train = tuple(
        row for row in _records(records, config) if row.session_date <= config.train_through
    )
    audit, eligible = [], []
    for row in train:
        input_exclusions = _inputs(row, config)
        value, target_exclusions = _target(row, config)
        exclusions = input_exclusions + target_exclusions
        audit.append((row.session_date, exclusions))
        if not exclusions:
            eligible.append((row, value))
    if len(eligible) < 2:
        raise ValueError("at least two complete positive-target TRAIN sessions are required")
    x = np.asarray([row.features for row, _ in eligible], dtype=np.float64)
    y = np.asarray([value for _, value in eligible], dtype=np.float64)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            mean = x.mean(axis=0)
            scale = np.maximum(x.std(axis=0), SCALE_FLOOR)
            z = (x - mean) / scale
            log_y = np.log(y)
            intercept = float(log_y.mean())
            coefficients = np.linalg.solve(
                z.T @ z + RIDGE_PENALTY * np.eye(x.shape[1]), z.T @ (log_y - intercept)
            )
            train_mean = float(y.mean())
    except (FloatingPointError, np.linalg.LinAlgError) as exc:
        raise ValueError("TRAIN numerical fit failed") from exc
    if (
        not all(np.isfinite(values).all() for values in (mean, scale, coefficients))
        or not isfinite(intercept)
        or not isfinite(train_mean)
        or train_mean <= 0
    ):
        raise ValueError("TRAIN numerical fit must be finite with a positive mean")
    return ForwardVarianceBaseline(
        config,
        tuple(mean),
        tuple(scale),
        tuple(coefficients),
        intercept,
        train_mean,
        max(row.target.available_at for row, _ in eligible),
        tuple(audit),
    )


def predict_forward_variance_baseline(
    model: ForwardVarianceBaseline, records: Sequence[ForwardVarianceRecord]
) -> tuple[VariancePrediction, ...]:
    """Predict later inputs without reading their target values or support status.

    Ridge log forecasts have fixed [1e-12, 1e12] variance bounds. Past summed
    variance is horizon-scaled by its declared adjacent-return count and floored
    at 1e-12, including legitimate flat past windows. Both changes are flagged.
    """
    predictions = []
    for row in _records(records, model.config):
        if (
            row.session_date < model.config.comparison_from
            or row.decision_at <= model.train_available_through
        ):
            raise ValueError("comparison must follow the cut and TRAIN target availability")
        exclusions = _inputs(row, model.config)
        if exclusions:
            predictions.append(
                VariancePrediction(row.session_date, row.decision_at, exclusions, None, None, None)
            )
            continue
        try:
            with np.errstate(over="raise", invalid="raise", divide="raise"):
                z = (
                    np.asarray(row.features, dtype=np.float64) - model.feature_mean
                ) / model.feature_scale
                log_forecast = float(z @ model.coefficients + model.intercept)
            past = float(row.past_realized_variance) * (
                model.config.horizon_minutes / model.config.past_return_count
            )
        except (FloatingPointError, OverflowError) as exc:
            raise ValueError("forecast numerical transform failed") from exc
        if not isfinite(log_forecast) or not isfinite(past):
            raise ValueError("forecasts must be finite")
        lower, upper = log(FORECAST_FLOOR), log(FORECAST_CEILING)
        ridge = (
            FORECAST_FLOOR
            if log_forecast <= lower
            else FORECAST_CEILING
            if log_forecast >= upper
            else exp(log_forecast)
        )
        predictions.append(
            VariancePrediction(
                row.session_date,
                row.decision_at,
                (),
                ridge,
                max(past, FORECAST_FLOOR),
                model.train_mean_variance,
                log_forecast < lower or log_forecast > upper,
                past < FORECAST_FLOOR,
            )
        )
    return tuple(predictions)


def qlike(target: float, forecast: float) -> float:
    """Normalized QLIKE y/f - log(y/f) - 1; both arguments strictly positive."""
    target, forecast = _finite(target, "QLIKE target"), _finite(forecast, "QLIKE forecast")
    if target <= 0 or forecast <= 0:
        raise ValueError("QLIKE requires strictly positive target and forecast")
    difference = log(target) - log(forecast)
    try:
        loss = expm1(difference) - difference
    except OverflowError as exc:
        raise ValueError("QLIKE loss must be finite") from exc
    if not isfinite(loss):
        raise ValueError("QLIKE loss must be finite")
    return max(0.0, loss)


def compare_forward_variance_baseline(
    model: ForwardVarianceBaseline, records: Sequence[ForwardVarianceRecord]
) -> VarianceComparison:
    """Retain every row; score all three controls on exactly the same cohort.

    Loss tuple order: log_ridge, past_variance, train_mean. This is descriptive
    development evidence, not independent performance, selection or promotion.
    """
    rows = tuple(records)
    predictions = predict_forward_variance_baseline(model, rows)
    scores, losses = [], []
    for row, prediction in zip(rows, predictions, strict=True):
        value, target_exclusions = _target(row, model.config)
        exclusions = prediction.exclusions + target_exclusions
        loss = (
            None
            if exclusions
            else tuple(
                qlike(value, forecast)
                for forecast in (
                    prediction.log_ridge,
                    prediction.past_variance,
                    prediction.train_mean,
                )
            )
        )
        scores.append(VarianceScore(prediction, exclusions, loss))
        if loss is not None:
            losses.append(loss)
    # Dividing first avoids an overflowing sum of individually finite losses.
    means = (
        tuple(sum(loss[index] / len(losses) for loss in losses) for index in range(3))
        if losses
        else None
    )
    if means is not None and not all(isfinite(value) for value in means):
        raise ValueError("mean QLIKE must be finite")
    return VarianceComparison(tuple(scores), len(losses), means)
