"""Pure causal session-reset Donchian breakout decisions.

The channel definition was independently checked against QuantConnect LEAN's
``DonchianChannel`` source under Apache-2.0:
https://github.com/QuantConnect/Lean/blob/master/Indicators/DonchianChannel.cs
This module is an independent, in-memory implementation. It infers no market
calendar: callers declare the current ``SessionWindow`` and prior sessions are
excluded from the decision window.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal

from thericher_v2.contracts import Bar, require_utc
from thericher_v2.market.resample import SessionWindow

DonchianAction = Literal["enter", "exit", "hold"]
DonchianPosition = Literal["flat", "long"]

_ACTIONS: Final = frozenset({"enter", "exit", "hold"})
_POSITIONS: Final = frozenset({"flat", "long"})


@dataclass(frozen=True)
class SessionResetDonchianDecision:
    """One long/flat decision from only completed bars at or before ``as_of``."""

    action: DonchianAction
    position_after: DonchianPosition
    reason: str
    feature_window_end: datetime | None

    def __post_init__(self) -> None:
        if self.action not in _ACTIONS:
            raise ValueError("action is invalid")
        if self.position_after not in _POSITIONS:
            raise ValueError("position_after is invalid")
        if not self.reason.strip():
            raise ValueError("reason must be nonempty")
        if self.action == "enter" and self.position_after != "long":
            raise ValueError("enter decisions must leave a long position")
        if self.action == "exit" and self.position_after != "flat":
            raise ValueError("exit decisions must leave a flat position")
        if self.feature_window_end is not None:
            object.__setattr__(
                self,
                "feature_window_end",
                require_utc(self.feature_window_end, "feature_window_end"),
            )


@dataclass(frozen=True)
class SessionResetDonchianRule:
    """A stateless 20/10-bar Donchian long/flat rule for one declared session.

    ``bars`` may include prior or later sessions, but the rule uses only bars
    fully inside ``session`` whose end timestamp is at or before ``as_of``.
    Inputs must be strictly timestamp-ordered, unique, complete, and have one
    symbol, market, and timeframe inside the declared session. Missing bars are
    not inferred or filled; the supplied completed bars are the only history.
    """

    entry_lookback: int = 20
    exit_lookback: int = 10

    def __post_init__(self) -> None:
        if not isinstance(self.entry_lookback, int) or self.entry_lookback < 1:
            raise ValueError("entry_lookback must be a positive integer")
        if not isinstance(self.exit_lookback, int) or self.exit_lookback < 1:
            raise ValueError("exit_lookback must be a positive integer")

    def decide(
        self,
        bars: Sequence[Bar],
        *,
        position: DonchianPosition,
        session: SessionWindow,
        as_of: datetime,
    ) -> SessionResetDonchianDecision:
        """Return a causal decision without mutating state or performing I/O."""

        if position not in _POSITIONS:
            raise ValueError("position must be flat or long")
        if not isinstance(session, SessionWindow):
            raise TypeError("session must be a SessionWindow")
        now = require_utc(as_of, "as_of")
        if now < session.open_ts or now > session.close_ts:
            raise ValueError("as_of must remain inside the declared session")

        source = tuple(bars)
        _validate_source_bars(source)
        session_bars = _session_bars_before_as_of(source, session=session, as_of=now)
        if not session_bars:
            return _hold(position, "insufficient_history", None)

        latest = session_bars[-1]
        if position == "flat":
            if len(session_bars) <= self.entry_lookback:
                return _hold(position, "insufficient_entry_history", latest.end_ts)
            prior_high = max(bar.high for bar in session_bars[-1 - self.entry_lookback : -1])
            if latest.close > prior_high:
                return SessionResetDonchianDecision(
                    action="enter",
                    position_after="long",
                    reason="entry_breakout",
                    feature_window_end=latest.end_ts,
                )
            return _hold(position, "inside_entry_channel", latest.end_ts)

        if len(session_bars) <= self.exit_lookback:
            return _hold(position, "insufficient_exit_history", latest.end_ts)
        prior_low = min(bar.low for bar in session_bars[-1 - self.exit_lookback : -1])
        if latest.close < prior_low:
            return SessionResetDonchianDecision(
                action="exit",
                position_after="flat",
                reason="exit_breakdown",
                feature_window_end=latest.end_ts,
            )
        return _hold(position, "inside_exit_channel", latest.end_ts)


def _validate_source_bars(bars: Sequence[Bar]) -> None:
    if any(not isinstance(bar, Bar) for bar in bars):
        raise TypeError("bars must contain Bar values")
    if any(not bar.complete for bar in bars):
        raise ValueError("bars must all be complete")
    if any(
        current.start_ts <= prior.start_ts
        for prior, current in zip(bars, bars[1:], strict=False)
    ):
        raise ValueError("bars must be strictly timestamp-ordered without duplicates")


def _session_bars_before_as_of(
    bars: Sequence[Bar],
    *,
    session: SessionWindow,
    as_of: datetime,
) -> tuple[Bar, ...]:
    session_bars: list[Bar] = []
    for bar in bars:
        if bar.end_ts > as_of:
            continue
        overlaps_session = bar.start_ts < session.close_ts and bar.end_ts > session.open_ts
        inside_session = session.open_ts <= bar.start_ts and bar.end_ts <= session.close_ts
        if overlaps_session and not inside_session:
            raise ValueError("bars overlapping the session must remain fully inside it")
        if inside_session:
            session_bars.append(bar)

    if not session_bars:
        return ()
    first = session_bars[0]
    if any(
        bar.symbol != first.symbol
        or bar.market != first.market
        or bar.timeframe != first.timeframe
        for bar in session_bars
    ):
        raise ValueError("session bars must share symbol, market, and timeframe")
    if any(
        current.start_ts != prior.end_ts
        for prior, current in zip(session_bars, session_bars[1:], strict=False)
    ):
        raise ValueError("session bars must be contiguous")
    return tuple(session_bars)


def _hold(
    position: DonchianPosition,
    reason: str,
    feature_window_end: datetime | None,
) -> SessionResetDonchianDecision:
    return SessionResetDonchianDecision(
        action="hold",
        position_after=position,
        reason=reason,
        feature_window_end=feature_window_end,
    )
