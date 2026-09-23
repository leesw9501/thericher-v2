"""Pure descriptive forecast diagnostics; no fitting decisions or inference claims."""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray


def summarize_forecast(
    predicted_bps: ArrayLike,
    actual_bps: ArrayLike,
    session_keys: ArrayLike,
    *,
    train_mean_bps: float,
) -> dict[str, Any]:
    """Summarize aligned observations without changing inputs or doing I/O.

    Counts are integers; metrics are finite floats or None when undefined.
    Means, standard deviations (ddof=0), MAE and the calibration intercept
    use bps; MSE fields use bps squared. Both MSE skill fields are
    ``1 - mse / baseline_mse`` (None for a zero baseline). The TRAIN baseline
    uses only the supplied scalar, never an estimated evaluation mean.

    Pearson/Spearman are None for fewer than two rows or either constant
    vector. Spearman uses average tied ranks. Directional accuracy excludes
    actual zeros but counts predicted zeros as misses. Session Pearson is an
    unweighted mean over defined sessions, with its own valid_session_count.

    predicted_bins maps the fixed interval labels to n, pred_mean, actual_mean,
    and positive_actual_fraction. Empty-bin metrics are None. selected_gt_6bps
    contains n, share and actual_mean_bps (None if empty). These are fixed
    descriptive subsets, not trading decisions. Calibration is OLS of actual
    on predicted with an intercept; both fields are None for constant predicted.

    Numeric inputs must be finite, real, nonempty 1-D vectors of equal length.
    Keys must be equally long, nonblank strings. Invalid inputs raise ValueError
    with a fixed category; unrepresentable arithmetic raises
    forecast_numeric_overflow rather than emitting nonfinite JSON numbers.
    """
    predicted = _vector(predicted_bps)
    actual = _vector(actual_bps)
    if predicted.size == 0 or actual.size == 0:
        raise ValueError("forecast_empty")
    if predicted.size != actual.size:
        raise ValueError("forecast_length_mismatch")
    try:
        keys = np.asarray(session_keys, dtype=object)
    except (TypeError, ValueError):
        raise ValueError("session_keys_invalid") from None
    if keys.ndim != 1 or any(not isinstance(key, str) or not key.strip() for key in keys):
        raise ValueError("session_keys_invalid")
    if keys.size != predicted.size:
        raise ValueError("forecast_length_mismatch")
    try:
        train_mean = np.asarray(train_mean_bps)
        if train_mean.ndim != 0 or train_mean.dtype.kind not in "iuf":
            raise ValueError
        train_mean = float(train_mean)
        if not np.isfinite(train_mean):
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        raise ValueError("train_mean_invalid") from None

    try:
        with np.errstate(over="raise", invalid="raise", divide="raise", under="ignore"):
            return _summarize(predicted, actual, keys, train_mean)
    except (FloatingPointError, OverflowError):
        raise ValueError("forecast_numeric_overflow") from None


def _vector(values: ArrayLike) -> NDArray[np.float64]:
    try:
        array = np.asarray(values)
        if array.dtype.kind not in "iuf":
            raise ValueError
        array = array.astype(np.float64, copy=False)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("forecast_values_invalid") from None
    if array.ndim != 1:
        raise ValueError("forecast_shape_invalid")
    if not np.isfinite(array).all():
        raise ValueError("forecast_nonfinite")
    return array


def _summarize(
    predicted: NDArray[np.float64],
    actual: NDArray[np.float64],
    keys: NDArray[np.object_],
    train_mean: float,
) -> dict[str, Any]:
    pred_mean = np.mean(predicted)
    actual_mean = np.mean(actual)
    error = predicted - actual
    mse = np.mean(np.square(error))
    zero_mse = np.mean(np.square(actual))
    train_mse = np.mean(np.square(actual - train_mean))
    nonzero_actual = actual != 0

    bins = {}
    for label, mask in (
        ("[-inf,-6)", predicted < -6),
        ("[-6,0)", (predicted >= -6) & (predicted < 0)),
        ("[0,6]", (predicted >= 0) & (predicted <= 6)),
        ("(6,inf)", predicted > 6),
    ):
        count = int(np.count_nonzero(mask))
        bins[label] = {
            "n": count,
            "pred_mean": float(np.mean(predicted[mask])) if count else None,
            "actual_mean": float(np.mean(actual[mask])) if count else None,
            "positive_actual_fraction": float(np.mean(actual[mask] > 0)) if count else None,
        }

    sessions: dict[str, list[int]] = {}
    for index, key in enumerate(keys):
        sessions.setdefault(key, []).append(index)
    session_correlations = []
    for indices in sessions.values():
        correlation = _pearson(predicted[indices], actual[indices])
        if correlation is not None:
            session_correlations.append(correlation)

    slope = intercept = None
    if not np.all(predicted == predicted[0]):
        centered = predicted - pred_mean
        scale = np.max(np.abs(centered))
        scaled = centered / scale
        slope = np.mean(scaled * (actual - actual_mean)) / np.mean(np.square(scaled)) / scale
        intercept = float(actual_mean - slope * pred_mean)
        slope = float(slope)

    selected = bins["(6,inf)"]
    return {
        "n": int(predicted.size),
        "session_count": len(sessions),
        "predicted_mean_bps": float(pred_mean),
        "predicted_std_bps": float(np.std(predicted, ddof=0)),
        "actual_mean_bps": float(actual_mean),
        "actual_std_bps": float(np.std(actual, ddof=0)),
        "mae_bps": float(np.mean(np.abs(error))),
        "mse_bps2": float(mse),
        "zero_forecast_mse_bps2": float(zero_mse),
        "train_mean_forecast_mse_bps2": float(train_mse),
        "mse_skill_vs_zero": float(1 - mse / zero_mse) if zero_mse != 0 else None,
        "mse_skill_vs_train_mean": float(1 - mse / train_mse) if train_mse != 0 else None,
        "pearson": _pearson(predicted, actual),
        "spearman": _pearson(_average_ranks(predicted), _average_ranks(actual)),
        "directional_accuracy": (
            float(np.mean(np.sign(predicted[nonzero_actual]) == np.sign(actual[nonzero_actual])))
            if np.any(nonzero_actual)
            else None
        ),
        "predicted_bins": bins,
        "selected_gt_6bps": {
            "n": selected["n"],
            "share": selected["n"] / int(predicted.size),
            "actual_mean_bps": selected["actual_mean"],
        },
        "mean_session_pearson": (
            float(np.mean(session_correlations)) if session_correlations else None
        ),
        "valid_session_count": len(session_correlations),
        "calibration_slope": slope,
        "calibration_intercept_bps": intercept,
    }


def _pearson(x: NDArray[np.float64], y: NDArray[np.float64]) -> float | None:
    if x.size < 2 or np.all(x == x[0]) or np.all(y == y[0]):
        return None
    x = x - np.mean(x)
    y = y - np.mean(y)
    # Normalize before squaring to keep correlation independent of magnitude.
    x = x / np.max(np.abs(x))
    y = y / np.max(np.abs(y))
    value = np.dot(x, y) / (np.sqrt(np.dot(x, x)) * np.sqrt(np.dot(y, y)))
    return float(np.clip(value, -1.0, 1.0))


def _average_ranks(values: NDArray[np.float64]) -> NDArray[np.float64]:
    order = np.argsort(values, kind="stable")
    sorted_values = values[order]
    starts = np.r_[0, np.flatnonzero(sorted_values[1:] != sorted_values[:-1]) + 1]
    ends = np.r_[starts[1:], values.size]
    ranks = np.empty(values.size, dtype=np.float64)
    ranks[order] = np.repeat((starts + ends + 1) / 2, ends - starts)
    return ranks
