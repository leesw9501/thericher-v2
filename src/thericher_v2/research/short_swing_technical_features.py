"""Pure prior-window features for future H123 raw-plus-technical consumers.

This preserves the established 60-bar indicator definitions without importing
artifact runtimes or extracting executable code from another source file.
Existing frozen campaigns keep their original feature implementations.
"""

from __future__ import annotations

import numpy as np

WINDOW = 60
FEATURE_NAMES = (
    "BB20_RELATIVE_WIDTH",
    "MACD12_26_RELATIVE_LEVEL",
    "MACD9_RELATIVE_SIGNAL",
    "MACD_RELATIVE_HISTOGRAM",
    "ADX14_FRACTION",
    "PLUS_DI14_FRACTION",
    "MINUS_DI14_FRACTION",
    "STOCHASTIC14_K_FRACTION",
    "STOCHASTIC14_D3_FRACTION",
    "CANDLE_RANGE_ATR14",
    "CANDLE_SIGNED_BODY_ATR14",
)


def _divide(numerator, denominator):
    return np.divide(
        numerator,
        denominator,
        out=np.full_like(numerator, np.nan),
        where=denominator != 0,
    )


def _ema(values, period):
    result = np.full_like(values, np.nan)
    result[:, period - 1] = values[:, :period].mean(1)
    alpha = 2 / (period + 1)
    for index in range(period, values.shape[1]):
        result[:, index] = result[:, index - 1] + alpha * (values[:, index] - result[:, index - 1])
    return result


def _wilder(values, period=14):
    result = np.full_like(values, np.nan)
    result[:, period - 1] = values[:, :period].mean(1)
    for index in range(period, values.shape[1]):
        result[:, index] = ((period - 1) * result[:, index - 1] + values[:, index]) / period
    return result


def short_swing_technical_features(prior_ohlc):
    """Return N x 11 dimensionless features from N x 60 x 4 completed OHLC.

    Inputs must be known, finite and positive. Degenerate ratios remain NaN;
    the caller must preserve that missingness rather than turn it into cash.
    This function neither establishes bar availability nor consumes targets.
    """
    prices = np.asarray(prior_ohlc, dtype=np.float64)
    if prices.ndim != 3 or prices.shape[1:] != (WINDOW, 4):
        raise ValueError("short_swing_requires_60_ohlc")
    if not np.isfinite(prices).all() or not (prices > 0).all():
        raise ValueError("short_swing_requires_known_positive_ohlc")
    op, hi, lo, cl = (prices[:, :, column] for column in range(4))
    if not (
        (hi >= np.maximum(op, cl)).all() and (lo <= np.minimum(op, cl)).all() and (hi >= lo).all()
    ):
        raise ValueError("short_swing_inconsistent_ohlc")

    macd = _ema(cl, 12)[:, 25:] - _ema(cl, 26)[:, 25:]
    level = macd[:, -1] / cl[:, -1]
    signal = _ema(macd, 9)[:, -1] / cl[:, -1]
    true_range = np.maximum(
        hi[:, 1:] - lo[:, 1:],
        np.maximum(abs(hi[:, 1:] - cl[:, :-1]), abs(lo[:, 1:] - cl[:, :-1])),
    )
    up, down = np.diff(hi, axis=1), -np.diff(lo, axis=1)
    plus = np.where((up > down) & (up > 0), up, 0)
    minus = np.where((down > up) & (down > 0), down, 0)
    atr = _wilder(true_range)
    plus_di, minus_di = _divide(_wilder(plus), atr), _divide(_wilder(minus), atr)
    flat = atr == 0
    plus_di[flat] = minus_di[flat] = 0
    dx = _divide(abs(plus_di - minus_di), plus_di + minus_di)
    dx[(plus_di + minus_di) == 0] = 0
    adx = _wilder(dx[:, 13:])[:, -1]
    stochastic = []
    for end in (58, 59, 60):
        lowest = lo[:, end - 14 : end].min(1)
        highest = hi[:, end - 14 : end].max(1)
        stochastic.append(_divide(cl[:, end - 1] - lowest, highest - lowest))
    k = np.stack(stochastic, axis=1)
    return np.column_stack(
        (
            4 * cl[:, -20:].std(1, ddof=0) / cl[:, -20:].mean(1),
            level,
            signal,
            level - signal,
            adx,
            plus_di[:, -1],
            minus_di[:, -1],
            k[:, -1],
            k.mean(1),
            _divide(hi[:, -1] - lo[:, -1], atr[:, -1]),
            _divide(cl[:, -1] - op[:, -1], atr[:, -1]),
        )
    )


def short_swing_technical_features_at(ohlc, entry_index):
    """Read only the 60 bars preceding the exclusive entry index."""
    if (
        isinstance(entry_index, bool)
        or not isinstance(entry_index, int)
        or not WINDOW <= entry_index <= len(ohlc)
    ):
        raise ValueError("short_swing_invalid_entry_index")
    prior = np.asarray(ohlc[entry_index - WINDOW : entry_index], dtype=np.float64)
    return short_swing_technical_features(prior[None])[0]
