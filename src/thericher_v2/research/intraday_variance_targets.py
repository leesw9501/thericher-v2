"""Pure forward M1 variance labels; no feature, eligibility or trading decisions."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import MAX_EMAX, MIN_EMIN, ROUND_HALF_EVEN, Context, Decimal, localcontext
from math import fsum, isfinite

from thericher_v2.contracts import Bar, Timeframe, require_utc
from thericher_v2.market.resample import SessionWindow


@dataclass(frozen=True, slots=True, repr=False)
class IntradayVarianceTarget:
    symbol: str
    decision_at: datetime
    horizon_minutes: int
    target_start: datetime
    target_end: datetime
    available_at: datetime
    realized_variance: float


def _aligned_utc(value: datetime, name: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
        or value.second != 0
        or value.microsecond != 0
    ):
        raise ValueError(f"{name} must be UTC and minute-aligned")
    return require_utc(value, name)


def build_intraday_variance_target(
    bars: Sequence[Bar],
    *,
    symbol: str,
    session: SessionWindow,
    decision_at: datetime,
    observed_at: datetime,
    horizon_minutes: int = 60,
) -> IntradayVarianceTarget:
    """Sum squared adjacent log OPEN differences from the next-minute entry.

    The H-minute target needs H+1 completed M1 bars, including the end OPEN's
    entire bar. Availability is that last bar's end, not the caller's later
    observation. Only starts in the required interval are inspected further.
    """
    if not isinstance(symbol, str) or not symbol or symbol != symbol.strip().upper():
        raise ValueError("symbol must be a nonempty canonical symbol")
    if not isinstance(session, SessionWindow):
        raise ValueError("session must be a SessionWindow")
    opening = _aligned_utc(session.open_ts, "session.open_ts")
    closing = _aligned_utc(session.close_ts, "session.close_ts")
    decision_at = _aligned_utc(decision_at, "decision_at")
    observed_at = _aligned_utc(observed_at, "observed_at")
    if not opening <= decision_at < closing:
        raise ValueError("decision_at must be inside the session")
    minute = Timeframe.M1.duration
    if (
        type(horizon_minutes) is not int
        or horizon_minutes <= 0
        or horizon_minutes > (closing - decision_at) // minute - 2
    ):
        raise ValueError("horizon_minutes must be a positive integer bounded by the session")
    target_start = decision_at + minute
    target_end = target_start + horizon_minutes * minute
    available_at = target_end + minute
    if observed_at < available_at:
        raise ValueError("required bars must be completed by observed_at")

    required = []
    for bar in bars:
        start = getattr(bar, "start_ts", None)
        if (
            isinstance(start, datetime)
            and start.tzinfo is not None
            and start.utcoffset() is not None
            and target_start <= start < available_at
        ):
            required.append(bar)
    if len(required) != horizon_minutes + 1:
        raise ValueError("required M1 bars must be exact, ordered, unique and contiguous")
    for index, bar in enumerate(required):
        if (
            not isinstance(bar, Bar)
            or bar.symbol != symbol
            or bar.market != "US"
            or bar.timeframe is not Timeframe.M1
        ):
            raise ValueError("required bars must match symbol, US market and M1 identity")
        start = _aligned_utc(bar.start_ts, "required bar.start_ts")
        if start != target_start + index * minute:
            raise ValueError("required M1 bars must be exact, ordered, unique and contiguous")
        if bar.complete is not True or bar.end_ts > observed_at:
            raise ValueError("required bars must be explicitly complete by observed_at")
        if any(
            not isinstance(value, Decimal) or not value.is_finite()
            for value in (bar.open, bar.high, bar.low, bar.close, bar.volume)
        ):
            raise ValueError("required bar values must be finite Decimals")
        replace(bar)

    # Decimal logs avoid converting extreme prices or their ratios to floats.
    with localcontext(
        Context(prec=50, rounding=ROUND_HALF_EVEN, Emax=MAX_EMAX, Emin=MIN_EMIN)
    ):
        logs = [bar.open.ln() for bar in required]
        differences = [float(right - left) for left, right in zip(logs, logs[1:], strict=False)]
    realized_variance = fsum(value * value for value in differences)
    if not isfinite(realized_variance):
        raise ValueError("realized variance must be finite")
    return IntradayVarianceTarget(
        symbol=symbol,
        decision_at=decision_at,
        horizon_minutes=horizon_minutes,
        target_start=target_start,
        target_end=target_end,
        available_at=available_at,
        realized_variance=realized_variance,
    )
