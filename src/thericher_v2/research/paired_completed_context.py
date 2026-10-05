"""Source-independent paired completed-bar context; provenance belongs to callers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime

from thericher_v2.contracts import Bar, Timeframe, require_utc
from thericher_v2.market.resample import (
    SUPPORTED_RESAMPLE_TIMEFRAMES,
    SessionWindow,
    resample_session_bars,
)


@dataclass(frozen=True, slots=True, repr=False)
class PairedCompletedContext:
    own_symbol: str
    peer_symbol: str
    timeframe: Timeframe
    observed_at: datetime
    history_start: datetime
    completed_through: datetime
    own_bars: tuple[Bar, ...]
    peer_bars: tuple[Bar, ...]


def build_paired_completed_context(
    own_bars: Sequence[Bar],
    peer_bars: Sequence[Bar],
    *,
    own_symbol: str,
    peer_symbol: str,
    session: SessionWindow,
    observed_at: datetime,
    timeframe: Timeframe,
    context_bars: int,
) -> PairedCompletedContext:
    """Select the last N completed, session-open-anchored bars for each symbol.

    Only the required M1 interval is validated, never a whole-session mask.
    An observation between target boundaries retains the previous completed
    end, exposing its lag through ``observed_at - completed_through``.
    Calendar correctness and source provenance remain caller responsibilities.
    """
    if type(context_bars) is not int or context_bars <= 0:
        raise ValueError("context_bars must be a positive integer")
    if not isinstance(timeframe, Timeframe) or timeframe not in SUPPORTED_RESAMPLE_TIMEFRAMES:
        raise ValueError("timeframe must be a supported intraday Timeframe")
    if (
        any(
            not isinstance(symbol, str) or not symbol or symbol != symbol.strip().upper()
            for symbol in (own_symbol, peer_symbol)
        )
        or own_symbol == peer_symbol
    ):
        raise ValueError("own_symbol and peer_symbol must be distinct canonical symbols")
    if not isinstance(session, SessionWindow):
        raise ValueError("session must be a SessionWindow")
    if not isinstance(observed_at, datetime):
        raise ValueError("observed_at must be a timezone-aware datetime")
    observed_at = require_utc(observed_at, "observed_at")
    if not session.open_ts <= observed_at <= session.close_ts:
        raise ValueError("observed_at must remain inside the declared session")

    completed_count = (observed_at - session.open_ts) // timeframe.duration
    if context_bars > completed_count:
        raise ValueError("requested context must remain inside this session")
    completed_through = min(
        session.close_ts, session.open_ts + completed_count * timeframe.duration
    )
    history_start = completed_through - context_bars * timeframe.duration
    own_context, peer_context = (
        _completed_bars(
            bars,
            symbol=symbol,
            timeframe=timeframe,
            session=session,
            history_start=history_start,
            completed_through=completed_through,
            as_of=observed_at,
        )
        for bars, symbol in ((own_bars, own_symbol), (peer_bars, peer_symbol))
    )
    return PairedCompletedContext(
        own_symbol=own_symbol,
        peer_symbol=peer_symbol,
        timeframe=timeframe,
        observed_at=observed_at,
        history_start=history_start,
        completed_through=completed_through,
        own_bars=own_context,
        peer_bars=peer_context,
    )


def _completed_bars(
    bars: Sequence[Bar],
    *,
    symbol: str,
    timeframe: Timeframe,
    session: SessionWindow,
    history_start: datetime,
    completed_through: datetime,
    as_of: datetime,
) -> tuple[Bar, ...]:
    # Filter by starts before reading identity, completeness, order or values.
    required = tuple(bar for bar in bars if history_start <= bar.start_ts < completed_through)
    minute_count = (completed_through - history_start) // Timeframe.M1.duration
    if len(required) != minute_count:
        raise ValueError("required M1 starts must be exact, contiguous, unique and ordered")
    expected = tuple(history_start + index * Timeframe.M1.duration for index in range(minute_count))
    if tuple(bar.start_ts for bar in required) != expected:
        raise ValueError("required M1 starts must be exact, contiguous, unique and ordered")
    if any(
        not isinstance(bar, Bar)
        or bar.symbol != symbol
        or bar.market != "US"
        or bar.timeframe is not Timeframe.M1
        for bar in required
    ):
        raise ValueError("required bars must match the declared symbol, US market and M1")
    if any(bar.complete is not True or bar.end_ts > as_of for bar in required):
        raise ValueError("required M1 bars must be complete as of observed_at")
    # Reuse Bar's value validation; the existing resampler owns all aggregation.
    validated = tuple(replace(bar) for bar in required)
    result = resample_session_bars(validated, timeframe, session=session).bars
    target_starts = tuple(
        history_start + index * timeframe.duration
        for index in range((completed_through - history_start) // timeframe.duration)
    )
    if tuple(bar.start_ts for bar in result) != target_starts:
        raise ValueError("requested completed target bars are unavailable")
    return result
