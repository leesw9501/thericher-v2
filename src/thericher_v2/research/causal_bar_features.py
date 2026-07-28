"""Pure completed-bar features for phase-local Research inputs.

The functions in this module have no provider, filesystem, credential, model,
or target dependency.  They only transform an already-qualified sequence of
completed daily bars into causal feature rows.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from decimal import ROUND_HALF_EVEN, Decimal, localcontext

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

KIS_NAS_D1_CANDLE_STATE_SEQUENCE_LENGTH = 20
KIS_NAS_D1_CANDLE_STATE_VOLUME_WINDOW = 20
KIS_NAS_D1_CANDLE_STATE_REQUIRED_BARS = 40
KIS_NAS_D1_CANDLE_STATE_FEATURE_SCHEMA_ID = "per-symbol-completed-d1-candle-state-r3"
KIS_NAS_D1_CANDLE_STATE_FEATURE_NAMES = (
    "log_open_gap",
    "signed_body_to_range",
    "close_location",
    "range_to_prior_close",
    "log_relative_volume_20",
)

_FEATURE_COUNT = len(KIS_NAS_D1_VOLATILITY_TREND_FEATURE_NAMES)
_CANDLE_STATE_FEATURE_COUNT = len(KIS_NAS_D1_CANDLE_STATE_FEATURE_NAMES)
_DENOMINATOR_FLOOR = 1e-12
_CANDLE_STATE_DECIMAL_PRECISION = 36
_CANDLE_STATE_QUANTUM = Decimal("0.000000000001")


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


def build_kis_nas_d1_candle_state_feature_sequence(
    bars: Sequence[Bar],
    *,
    symbol: str,
    decision_index: int,
) -> tuple[tuple[float, ...], ...]:
    """Build one causal 20x5 OHLCV candle-state sequence.

    Each row represents one completed daily candle.  Its relative-volume
    feature compares that candle's ``log1p(volume)`` with the preceding 20
    completed candles, so the full sequence reads only indexes
    ``decision_index - 39`` through ``decision_index``.
    """

    resolved_symbol = _resolve_symbol(symbol)
    if (
        isinstance(decision_index, bool)
        or not isinstance(decision_index, int)
        or decision_index < KIS_NAS_D1_CANDLE_STATE_REQUIRED_BARS - 1
        or decision_index >= len(bars)
    ):
        raise ValueError("NAS D1 candle-state decision index is invalid")

    anchor_index = decision_index - KIS_NAS_D1_CANDLE_STATE_REQUIRED_BARS + 1
    chain = tuple(bars[anchor_index : decision_index + 1])
    if len(chain) != KIS_NAS_D1_CANDLE_STATE_REQUIRED_BARS:
        raise ValueError("NAS D1 candle-state bar chain is too short")
    _validate_completed_d1_ohlcv_chain(chain, symbol=resolved_symbol)

    feature_start_index = decision_index - KIS_NAS_D1_CANDLE_STATE_SEQUENCE_LENGTH + 1
    rows: list[tuple[float, ...]] = []
    for terminal_index in range(feature_start_index, decision_index + 1):
        current = bars[terminal_index]
        prior = bars[terminal_index - 1]
        volume_window = tuple(
            _log1p_volume(bars[index])
            for index in range(
                terminal_index - KIS_NAS_D1_CANDLE_STATE_VOLUME_WINDOW,
                terminal_index,
            )
        )
        if len(volume_window) != KIS_NAS_D1_CANDLE_STATE_VOLUME_WINDOW:
            raise ValueError("NAS D1 candle-state volume window is invalid")
        rows.append(
            _candle_state_feature_row(
                current=current,
                prior=prior,
                volume_window=volume_window,
            )
        )

    result = tuple(rows)
    _require_candle_state_feature_sequence(result)
    return result


def build_kis_nas_d1_candle_state_feature_sequences(
    bars: Sequence[Bar],
    *,
    symbol: str,
) -> tuple[tuple[tuple[float, ...], ...], ...]:
    """Build every phase-local candle-state sequence with shared causal rows.

    This bulk helper is for an already qualified phase.  It validates the full
    phase once, computes each completed candle row once, then returns sequences
    in ascending decision-index order from ``required_bars - 1`` onward.  Each
    returned sequence retains the same no-future dependency as the single
    sequence builder above.
    """

    resolved_symbol = _resolve_symbol(symbol)
    if len(bars) < KIS_NAS_D1_CANDLE_STATE_REQUIRED_BARS:
        raise ValueError("NAS D1 candle-state phase is too short")
    _validate_completed_d1_ohlcv_chain(bars, symbol=resolved_symbol)
    log_volumes = tuple(_log1p_volume(bar) for bar in bars)
    rows_by_terminal: dict[int, tuple[float, ...]] = {}
    for terminal_index in range(KIS_NAS_D1_CANDLE_STATE_VOLUME_WINDOW, len(bars)):
        rows_by_terminal[terminal_index] = _candle_state_feature_row(
            current=bars[terminal_index],
            prior=bars[terminal_index - 1],
            volume_window=log_volumes[
                terminal_index - KIS_NAS_D1_CANDLE_STATE_VOLUME_WINDOW : terminal_index
            ],
        )
    sequences: list[tuple[tuple[float, ...], ...]] = []
    for decision_index in range(KIS_NAS_D1_CANDLE_STATE_REQUIRED_BARS - 1, len(bars)):
        sequence = tuple(
            rows_by_terminal[index]
            for index in range(
                decision_index - KIS_NAS_D1_CANDLE_STATE_SEQUENCE_LENGTH + 1,
                decision_index + 1,
            )
        )
        _require_candle_state_feature_sequence(sequence)
        sequences.append(sequence)
    return tuple(sequences)


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


def _validate_completed_d1_ohlcv_chain(chain: Sequence[Bar], *, symbol: str) -> None:
    _validate_completed_d1_chain(chain, symbol=symbol)
    for bar in chain:
        if (
            not isinstance(bar.volume, Decimal)
            or not bar.volume.is_finite()
            or bar.volume < 0
        ):
            raise ValueError("NAS D1 candle-state volume is invalid")


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


def _log1p_volume(bar: Bar) -> Decimal:
    value = bar.volume
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise ValueError("NAS D1 candle-state volume is invalid")
    with localcontext() as context:
        context.prec = _CANDLE_STATE_DECIMAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        result = (value + Decimal("1")).ln()
    if not result.is_finite():
        raise ValueError("NAS D1 candle-state log volume is invalid")
    return result


def _candle_state_feature_row(
    *,
    current: Bar,
    prior: Bar,
    volume_window: Sequence[Decimal],
) -> tuple[float, ...]:
    if len(volume_window) != KIS_NAS_D1_CANDLE_STATE_VOLUME_WINDOW:
        raise ValueError("NAS D1 candle-state volume window is invalid")
    candle_range = current.high - current.low
    with localcontext() as context:
        context.prec = _CANDLE_STATE_DECIMAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        if candle_range == 0:
            signed_body_to_range = Decimal("0")
            close_location = Decimal("0")
        else:
            signed_body_to_range = (current.close - current.open) / candle_range
            close_location = (
                Decimal("2") * (current.close - current.low) / candle_range - Decimal("1")
            )
        log_open_gap = (current.open / prior.close).ln()
        range_to_prior_close = candle_range / prior.close
        log_relative_volume = _log1p_volume(current) - (
            sum(volume_window, Decimal("0"))
            / Decimal(KIS_NAS_D1_CANDLE_STATE_VOLUME_WINDOW)
        )
    row = (
        _canonical_candle_state_number(log_open_gap),
        _canonical_candle_state_number(signed_body_to_range),
        _canonical_candle_state_number(close_location),
        _canonical_candle_state_number(range_to_prior_close),
        _canonical_candle_state_number(log_relative_volume),
    )
    if (
        len(row) != _CANDLE_STATE_FEATURE_COUNT
        or any(not math.isfinite(value) for value in row)
        or not -1.0 <= signed_body_to_range <= 1.0
        or not -1.0 <= close_location <= 1.0
        or range_to_prior_close < 0.0
    ):
        raise ValueError("NAS D1 candle-state feature row is invalid")
    return row


def _canonical_candle_state_number(value: Decimal) -> float:
    """Round feature values before float conversion for host/Docker parity."""

    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("NAS D1 candle-state feature value is invalid")
    with localcontext() as context:
        context.prec = _CANDLE_STATE_DECIMAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        quantized = value.quantize(_CANDLE_STATE_QUANTUM, rounding=ROUND_HALF_EVEN)
    result = float(quantized)
    if not math.isfinite(result):
        raise ValueError("NAS D1 candle-state feature value is invalid")
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


def _require_candle_state_feature_sequence(
    feature_sequence: Sequence[Sequence[float]],
) -> tuple[tuple[float, ...], ...]:
    try:
        rows = tuple(tuple(float(value) for value in row) for row in feature_sequence)
    except (TypeError, ValueError) as error:
        raise ValueError("NAS D1 candle-state feature sequence is invalid") from error
    if (
        len(rows) != KIS_NAS_D1_CANDLE_STATE_SEQUENCE_LENGTH
        or any(len(row) != _CANDLE_STATE_FEATURE_COUNT for row in rows)
        or any(not math.isfinite(value) for row in rows for value in row)
    ):
        raise ValueError("NAS D1 candle-state feature sequence is invalid")
    return rows


def _resolve_symbol(symbol: str) -> str:
    if not isinstance(symbol, str):
        raise ValueError("NAS D1 volatility trend symbol is invalid")
    resolved = symbol.strip().upper()
    if not resolved:
        raise ValueError("NAS D1 volatility trend symbol is invalid")
    return resolved
