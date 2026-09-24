"""Pure fixed completed-window features and TRAIN-only Ridge comparator."""

from __future__ import annotations

import math
import time

import numpy as np
from sklearn.linear_model import Ridge

from thericher_v2.research.policy_graph_models import _array, _hash, _require

WINDOWS = (3, 12, 36)
FEATURES = tuple(
    f"{name}_{window}"
    for window in WINDOWS
    for name in (
        "window_return",
        "close_return_std",
        "mean_range",
        "mean_body",
        "logvolume_contrast",
    )
)


def _deadline(deadline):
    if time.monotonic() >= deadline:
        raise TimeoutError("causal_feature_ridge_deadline_exceeded")


def feature_matrix(x, closes) -> np.ndarray:
    """Return 15 features from each row's completed 36 bars, ordered by WINDOWS.

    The four x channels are close/open-1, high/open-1, low/open-1 and
    log1p(volume). Closes are actual completed prices, used only as ratios.
    Each window contributes return from its first open, population standard
    deviation of its w-1 close returns, mean range, mean body and recent-minus-
    full-window mean log volume. Rows and windows never borrow outside bars.
    """
    _require(isinstance(x, np.ndarray) and x.ndim == 3, "x_shape")
    n = len(x)
    _require(n > 0, "empty_input")
    _array(x, (n, 36, 4), "x")
    _array(closes, (n, 36), "closes")
    _require((closes > 0).all(), "closes_positive_required")
    body, high, low, logvolume = (x[:, :, i] for i in range(4))
    _require(
        (x[:, :, :3] > -1).all()
        and (high >= 0).all()
        and (high >= body).all()
        and (low <= 0).all()
        and (low <= body).all(),
        "invalid_normalized_ohlc",
    )
    _require((logvolume >= 0).all(), "logvolume_nonnegative_required")
    features = np.empty((n, len(FEATURES)), dtype="float64")
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        try:
            for index, window in enumerate(WINDOWS):
                prices = closes[:, -window:]
                first_open = prices[:, 0] / (1 + body[:, -window])
                returns = prices[:, 1:] / prices[:, :-1] - 1
                recent = max(1, window // 3)
                features[:, 5 * index : 5 * (index + 1)] = np.column_stack(
                    (
                        prices[:, -1] / first_open - 1,
                        returns.std(axis=1, ddof=0),
                        (high[:, -window:] - low[:, -window:]).mean(axis=1),
                        body[:, -window:].mean(axis=1),
                        logvolume[:, -recent:].mean(axis=1) - logvolume[:, -window:].mean(axis=1),
                    )
                )
        except (FloatingPointError, OverflowError):
            raise ValueError("nonfinite_features") from None
    _require(np.isfinite(features).all(), "nonfinite_features")
    return features


def fit_predict(
    *, train_x, train_closes, train_y, eval_x, eval_closes, deadline
) -> tuple[np.ndarray, dict[str, str]]:
    """Fit one fixed Ridge; caller attests completed bars and the temporal split.

    Deadline is an absolute time.monotonic() value. Only TRAIN fits the
    per-feature population mean/std; a zero std becomes one. No evaluation
    targets, timestamps, fitted weights or raw features leave this function.
    """
    _require(
        type(deadline) in (int, float) and -math.inf < deadline < math.inf,
        "deadline_finite_required",
    )
    _deadline(deadline)
    train_features = feature_matrix(train_x, train_closes)
    eval_features = feature_matrix(eval_x, eval_closes)
    _array(train_y, (len(train_features),), "train_y")
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        try:
            mean = train_features.mean(axis=0)
            scale = train_features.std(axis=0, ddof=0)
            scale = np.where(scale == 0, 1.0, scale)
            train = (train_features - mean) / scale
            evaluation = (eval_features - mean) / scale
        except (FloatingPointError, OverflowError):
            raise ValueError("nonfinite_scaler") from None
    _require(
        all(np.isfinite(value).all() for value in (mean, scale, train, evaluation)),
        "nonfinite_scaler",
    )
    _deadline(deadline)
    model = Ridge(alpha=1.0, solver="svd", fit_intercept=True)
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        try:
            model.fit(train, train_y)
        except (FloatingPointError, OverflowError, ValueError, np.linalg.LinAlgError):
            raise ValueError("ridge_numerical_failure") from None
    _deadline(deadline)
    _require(
        np.isfinite(model.coef_).all() and np.isfinite(model.intercept_).all(),
        "nonfinite_ridge",
    )
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        try:
            forecast = model.predict(evaluation)
        except (FloatingPointError, OverflowError, ValueError, np.linalg.LinAlgError):
            raise ValueError("ridge_numerical_failure") from None
    _array(forecast, (len(eval_features),), "forecast")
    forecast.setflags(write=False)
    identity = dict(
        scaler_sha256=_hash(mean, scale),
        model_sha256=_hash(model.coef_, np.asarray(model.intercept_)),
    )
    _deadline(deadline)
    return forecast, identity
