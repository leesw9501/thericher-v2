"""Pure completed-bar features for phase-local Research inputs.

The functions in this module have no provider, filesystem, credential, model,
or target dependency.  They only transform an already-qualified sequence of
completed daily bars into causal feature rows.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from decimal import Decimal

from thericher_v2.contracts import Bar, Timeframe

KIS_NAS_D1_VOLATILITY_TREND_SEQUENCE_LENGTH = 20
KIS_NAS_D1_VOLATILITY_TREND_CONDITIONING_WINDOW = 10
KIS_NAS_D1_VOLATILITY_TREND_REQUIRED_BARS = 30
KIS_NAS_D1_VOLATILITY_TREND_FEATURE_SCHEMA_ID = (
    "per-symbol-completed-d1-volatility-range-conditioned-trend-r1"
)
KIS_NAS_D1_VOLATILITY_TREND_FEATURE_NAMES = (
    "completed_log_return",
    "trend_10",
    "realized_volatility_10",
    "normalized_true_range_10",
    "range_conditioned_trend_10",
)

_FEATURE_COUNT = len(KIS_NAS_D1_VOLATILITY_TREND_FEATURE_NAMES)
_DENOMINATOR_FLOOR = 1e-12


def build_kis_nas_d1_volatility_trend_feature_sequence(
    bars: Sequence[Bar],
    *,
    symbol: str,
    decision_index: int,
) -> tuple[tuple[float, ...], ...]:
    """Build one causal 20x5 feature sequence from phase-local completed bars.

    Only indexes ``decision_index - 29`` through ``decision_index`` are read.
    The decision bar itself is complete, so this function intentionally has no
    entry, exit, label, provider, or artifact surface.
    """

    resolved_symbol = _resolve_symbol(symbol)
    if (
        isinstance(decision_index, bool)
        or not isinstance(decision_index, int)
        or decision_index < KIS_NAS_D1_VOLATILITY_TREND_REQUIRED_BARS - 1
        or decision_index >= len(bars)
    ):
        raise ValueError("NAS D1 volatility trend decision index is invalid")

    anchor_index = decision_index - KIS_NAS_D1_VOLATILITY_TREND_REQUIRED_BARS + 1
    chain = tuple(bars[anchor_index : decision_index + 1])
    if len(chain) != KIS_NAS_D1_VOLATILITY_TREND_REQUIRED_BARS:
        raise ValueError("NAS D1 volatility trend bar chain is too short")
    _validate_completed_d1_chain(chain, symbol=resolved_symbol)

    log_returns: dict[int, float] = {}
    normalized_true_ranges: dict[int, float] = {}
    for index in range(anchor_index + 1, decision_index + 1):
        prior = bars[index - 1]
        current = bars[index]
        log_returns[index] = _completed_log_return(current=current, prior=prior)
        normalized_true_ranges[index] = _normalized_true_range(current=current, prior=prior)

    feature_start_index = decision_index - KIS_NAS_D1_VOLATILITY_TREND_SEQUENCE_LENGTH + 1
    rows: list[tuple[float, ...]] = []
    for terminal_index in range(feature_start_index, decision_index + 1):
        start_index = terminal_index - KIS_NAS_D1_VOLATILITY_TREND_CONDITIONING_WINDOW + 1
        returns = tuple(log_returns[index] for index in range(start_index, terminal_index + 1))
        ranges = tuple(
            normalized_true_ranges[index] for index in range(start_index, terminal_index + 1)
        )
        trend = sum(returns)
        realized_volatility = math.sqrt(
            sum(value * value for value in returns)
            / KIS_NAS_D1_VOLATILITY_TREND_CONDITIONING_WINDOW
        )
        mean_normalized_true_range = (
            sum(ranges) / KIS_NAS_D1_VOLATILITY_TREND_CONDITIONING_WINDOW
        )
        denominator = max(
            math.sqrt(KIS_NAS_D1_VOLATILITY_TREND_CONDITIONING_WINDOW)
            * max(realized_volatility, mean_normalized_true_range),
            _DENOMINATOR_FLOOR,
        )
        row = (
            log_returns[terminal_index],
            trend,
            realized_volatility,
            mean_normalized_true_range,
            trend / denominator,
        )
        if len(row) != _FEATURE_COUNT or any(not math.isfinite(value) for value in row):
            raise ValueError("NAS D1 volatility trend feature row is invalid")
        rows.append(row)

    result = tuple(rows)
    _require_feature_sequence(result)
    return result


def terminal_realized_volatility_20(feature_sequence: Sequence[Sequence[float]]) -> float:
    """Return the causal 20-bar RMS volatility from an already-built sequence."""

    rows = _require_feature_sequence(feature_sequence)
    result = math.sqrt(
        sum(row[0] * row[0] for row in rows)
        / KIS_NAS_D1_VOLATILITY_TREND_SEQUENCE_LENGTH
    )
    if not math.isfinite(result):
        raise ValueError("NAS D1 terminal realized volatility is invalid")
    return result


def terminal_trend_5(feature_sequence: Sequence[Sequence[float]]) -> float:
    """Return the causal five-bar trend from an already-built sequence."""

    rows = _require_feature_sequence(feature_sequence)
    result = sum(row[0] for row in rows[-5:])
    if not math.isfinite(result):
        raise ValueError("NAS D1 terminal trend is invalid")
    return result


def _validate_completed_d1_chain(chain: Sequence[Bar], *, symbol: str) -> None:
    prior: Bar | None = None
    for bar in chain:
        if not isinstance(bar, Bar) or bar.symbol != symbol or bar.timeframe is not Timeframe.D1:
            raise ValueError("NAS D1 volatility trend bar identity is invalid")
        if not bar.complete:
            raise ValueError("NAS D1 volatility trend requires completed bars")
        _validate_ohlc(bar)
        if prior is not None:
            try:
                non_monotonic = (
                    bar.start_ts <= prior.start_ts or bar.end_ts <= prior.end_ts
                )
            except TypeError as error:
                raise ValueError("NAS D1 volatility trend bar time is invalid") from error
            if non_monotonic:
                raise ValueError("NAS D1 volatility trend bars are non-monotonic")
        prior = bar


def _validate_ohlc(bar: Bar) -> None:
    values = (bar.open, bar.high, bar.low, bar.close)
    if (
        not all(isinstance(value, Decimal) and value.is_finite() and value > 0 for value in values)
        or bar.high < bar.low
        or bar.high < max(bar.open, bar.close)
        or bar.low > min(bar.open, bar.close)
    ):
        raise ValueError("NAS D1 volatility trend OHLC is invalid")


def _completed_log_return(*, current: Bar, prior: Bar) -> float:
    ratio = float(current.close / prior.close)
    if not math.isfinite(ratio) or ratio <= 0:
        raise ValueError("NAS D1 completed log return is invalid")
    result = math.log(ratio)
    if not math.isfinite(result):
        raise ValueError("NAS D1 completed log return is non-finite")
    return result


def _normalized_true_range(*, current: Bar, prior: Bar) -> float:
    true_range = max(
        current.high - current.low,
        abs(current.high - prior.close),
        abs(current.low - prior.close),
    )
    result = float(true_range / prior.close)
    if not math.isfinite(result) or result < 0:
        raise ValueError("NAS D1 normalized true range is invalid")
    return result


def _require_feature_sequence(
    feature_sequence: Sequence[Sequence[float]],
) -> tuple[tuple[float, ...], ...]:
    try:
        rows = tuple(tuple(float(value) for value in row) for row in feature_sequence)
    except (TypeError, ValueError) as error:
        raise ValueError("NAS D1 volatility trend feature sequence is invalid") from error
    if (
        len(rows) != KIS_NAS_D1_VOLATILITY_TREND_SEQUENCE_LENGTH
        or any(len(row) != _FEATURE_COUNT for row in rows)
        or any(not math.isfinite(value) for row in rows for value in row)
    ):
        raise ValueError("NAS D1 volatility trend feature sequence is invalid")
    return rows


def _resolve_symbol(symbol: str) -> str:
    if not isinstance(symbol, str):
        raise ValueError("NAS D1 volatility trend symbol is invalid")
    resolved = symbol.strip().upper()
    if not resolved:
        raise ValueError("NAS D1 volatility trend symbol is invalid")
    return resolved
