"""Original research-only M5 variant of the fourteen-session intraday noise band.

Source mechanism: https://concretumgroup.com/wp-content/uploads/2026/02/Beat-the-Market.pdf
This is not a full paper reproduction or adopted public implementation. There
is no previous-close/gap adjustment, strategy, signal, or execution behavior.
Callers choose fourteen prior sessions and own calendar correctness, actual
source availability/finality, replay assumptions, and future-target isolation.
Distinct days mean distinct declared UTC session-open dates; no days are inferred.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from thericher_v2.contracts import Bar, Timeframe, require_utc
from thericher_v2.market.resample import SessionWindow


@dataclass(frozen=True)
class NoiseBandHistoryEntry:
    session: SessionWindow
    bars: Sequence[Bar]


@dataclass(frozen=True)
class IntradayNoiseBand:
    sigma: Decimal
    upper: Decimal
    lower: Decimal
    feature_window_end: datetime
    history_count: int
    current_bar_count: int


def build_intraday_noise_band(
    bars: Sequence[Bar],
    *,
    history: Sequence[NoiseBandHistoryEntry],
    session: SessionWindow,
    as_of: datetime,
) -> IntradayNoiseBand:
    """Mean absolute prior CLOSE/session-OPEN move at the same elapsed cutoff.

    Prefixes must start at OPEN and contain every completed M5 bar through the
    exact cutoff. Later bars' prices are never read. Supplied bar metadata must
    remain homogeneous and inside its session, including any ignored tail.
    """
    cutoff = _strict_utc(as_of)
    current = _prefix(bars, session, cutoff)
    elapsed = cutoff - session.open_ts
    entries = tuple(history)
    if len(entries) != 14:
        raise ValueError("history requires exactly fourteen chosen sessions")
    if any(not isinstance(entry, NoiseBandHistoryEntry) for entry in entries):
        raise TypeError("history must contain NoiseBandHistoryEntry values")

    moves = []
    previous = None
    for entry in entries:
        if not isinstance(entry.session, SessionWindow):
            raise TypeError("historical session must be a SessionWindow")
        prior_open = _strict_utc(entry.session.open_ts)
        prior_close = _strict_utc(entry.session.close_ts)
        if prior_close > session.open_ts or prior_open.date() >= session.open_ts.date():
            raise ValueError("history must contain fully prior session days")
        if previous is not None and (
            previous.open_ts.date() >= prior_open.date() or previous.close_ts > prior_open
        ):
            raise ValueError("historical days must be distinct, chronological, non-overlapping")
        prefix = _prefix(entry.bars, entry.session, prior_open + elapsed)
        if (prefix[0].symbol, prefix[0].market) != (current[0].symbol, current[0].market):
            raise ValueError("current and historical bars must be homogeneous")
        moves.append(abs(prefix[-1].close / prefix[0].open - Decimal(1)))
        previous = entry.session

    sigma = sum(moves, Decimal(0)) / Decimal(14)
    anchor = current[0].open
    return IntradayNoiseBand(
        sigma, anchor * (Decimal(1) + sigma), anchor * (Decimal(1) - sigma),
        cutoff, len(entries), len(current),
    )


def _strict_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("timestamps must be datetime values")
    if value.utcoffset() != timedelta(0):
        raise ValueError("timestamps must be timezone-aware UTC")
    return require_utc(value)


def _prefix(
    bars: Sequence[Bar], session: SessionWindow, cutoff: datetime,
) -> tuple[Bar, ...]:
    if not isinstance(session, SessionWindow):
        raise TypeError("session must be a SessionWindow")
    opening = _strict_utc(session.open_ts)
    closing = _strict_utc(session.close_ts)
    elapsed = cutoff - opening
    step = Timeframe.M5.duration
    if elapsed <= timedelta(0) or cutoff > closing or elapsed % step != timedelta(0):
        raise ValueError("cutoff must be an exact positive M5 elapsed boundary inside session")
    source = tuple(bars)
    if any(not isinstance(bar, Bar) for bar in source):
        raise TypeError("bars must contain Bar values")
    if not source:
        raise ValueError("prefix must not be empty")
    identity = (source[0].symbol, source[0].market)
    if any(not isinstance(value, str) or not value.strip() for value in identity):
        raise ValueError("symbol and market must be nonempty strings")
    for bar in source:
        if bar.timeframe is not Timeframe.M5 or (bar.symbol, bar.market) != identity:
            raise ValueError("bars must be homogeneous M5 values")
        start = _strict_utc(bar.start_ts)
        if start < opening or bar.end_ts > closing:
            raise ValueError("bars must remain inside their declared session")
    selected = tuple(bar for bar in source if bar.end_ts <= cutoff)
    if len(selected) != elapsed // step or any(
        bar.start_ts != opening + index * step for index, bar in enumerate(selected)
    ):
        raise ValueError("prefix must be contiguous from OPEN through the exact cutoff")
    for bar in selected:
        if bar.complete is not True:
            raise ValueError("prefix requires completed bars with boolean True finality")
        for value in (bar.open, bar.close):
            if not isinstance(value, Decimal):
                raise TypeError("prefix opens and closes must be Decimal values")
            if not value.is_finite() or value <= 0:
                raise ValueError("prefix opens and closes must be finite and positive")
    return selected
