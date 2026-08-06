"""Pure causal session-reset EMA state decisions.

The 15/30 moving-average cross shape was independently checked against
QuantConnect LEAN's Apache-2.0 ``MovingAverageCrossAlgorithm`` example:
https://github.com/QuantConnect/Lean/blob/master/Algorithm.Python/MovingAverageCrossAlgorithm.py
This module is an independent, in-memory implementation. Callers declare the
current ``SessionWindow``; no prior or later session contributes to a decision.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Final, Literal

from thericher_v2.contracts import Bar, decimal_value, positive, require_utc
from thericher_v2.market.resample import SessionWindow

SESSION_RESET_EMA_STATE_RULE_ID: Final = "session-reset-ema-state-v1"
SESSION_RESET_EMA_STATE_SEED_POLICY: Final = "within_session_sma_seed_then_decimal_ema_v1"

EmaStateAction = Literal["enter", "exit", "hold"]
EmaStateInputStatus = Literal["missing", "ready"]
EmaStatePosition = Literal["flat", "long"]

_ACTIONS: Final = frozenset({"enter", "exit", "hold"})
_INPUT_STATUSES: Final = frozenset({"missing", "ready"})
_POSITIONS: Final = frozenset({"flat", "long"})
_ONE: Final = Decimal("1")
_ZERO: Final = Decimal("0")


@dataclass(frozen=True)
class SessionResetEmaStateDecision:
    """One long/flat decision from completed bars in one declared session."""

    action: EmaStateAction
    position_after: EmaStatePosition
    input_status: EmaStateInputStatus
    reason: str
    feature_window_end: datetime | None
    fast_ema: Decimal | None = None
    slow_ema: Decimal | None = None

    def __post_init__(self) -> None:
        if self.action not in _ACTIONS:
            raise ValueError("action is invalid")
        if self.position_after not in _POSITIONS:
            raise ValueError("position_after is invalid")
        if self.input_status not in _INPUT_STATUSES:
            raise ValueError("input_status is invalid")
        if not self.reason.strip():
            raise ValueError("reason must be nonempty")
        if self.action == "enter" and self.position_after != "long":
            raise ValueError("enter decisions must leave a long position")
        if self.action == "exit" and self.position_after != "flat":
            raise ValueError("exit decisions must leave a flat position")
        if self.action != "hold" and self.input_status != "ready":
            raise ValueError("unready inputs must hold")
        if (self.fast_ema is None) != (self.slow_ema is None):
            raise ValueError("EMA values must be present together")
        if self.input_status == "ready" and self.fast_ema is None:
            raise ValueError("ready inputs require EMA values")
        if self.input_status == "missing" and self.fast_ema is not None:
            raise ValueError("missing inputs cannot expose EMA values")
        if self.feature_window_end is not None:
            object.__setattr__(
                self,
                "feature_window_end",
                require_utc(self.feature_window_end, "feature_window_end"),
            )
        if self.input_status == "ready" and self.feature_window_end is None:
            raise ValueError("ready inputs require feature_window_end")
        if self.fast_ema is not None:
            object.__setattr__(self, "fast_ema", positive(self.fast_ema, "fast_ema"))
            object.__setattr__(self, "slow_ema", positive(self.slow_ema, "slow_ema"))


@dataclass(frozen=True)
class SessionResetEmaStateRule:
    """A stateless 15/30 EMA long/flat rule scoped to one declared session.

    Each EMA seeds from the simple average of its own first in-session completed
    closes. Later in-session closes update it with ``2 / (period + 1)`` using
    ``Decimal`` arithmetic. Inputs must be timestamp-ordered, complete, and
    contiguous within the selected session; missing bars are not inferred.
    """

    fast_period: int = 15
    slow_period: int = 30
    tolerance: Decimal | int | str = Decimal("0.00015")

    def __post_init__(self) -> None:
        if (
            not isinstance(self.fast_period, int)
            or isinstance(self.fast_period, bool)
            or self.fast_period < 1
        ):
            raise ValueError("fast_period must be a positive integer")
        if (
            not isinstance(self.slow_period, int)
            or isinstance(self.slow_period, bool)
            or self.slow_period < 1
        ):
            raise ValueError("slow_period must be a positive integer")
        if self.fast_period >= self.slow_period:
            raise ValueError("fast_period must be less than slow_period")
        tolerance = decimal_value(self.tolerance, "tolerance")
        if tolerance < _ZERO:
            raise ValueError("tolerance must be nonnegative")
        object.__setattr__(self, "tolerance", tolerance)

    def decide(
        self,
        bars: Sequence[Bar],
        *,
        position: EmaStatePosition,
        session: SessionWindow,
        as_of: datetime,
    ) -> SessionResetEmaStateDecision:
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
        if len(session_bars) < self.slow_period:
            feature_window_end = session_bars[-1].end_ts if session_bars else None
            return _hold(
                position,
                input_status="missing",
                reason="ema_warmup",
                feature_window_end=feature_window_end,
            )

        closes = tuple(bar.close for bar in session_bars)
        fast_ema = _ema(closes, period=self.fast_period)
        slow_ema = _ema(closes, period=self.slow_period)
        latest = session_bars[-1]

        if position == "flat":
            entry_threshold = slow_ema * (_ONE + self.tolerance)
            if fast_ema > entry_threshold:
                return SessionResetEmaStateDecision(
                    action="enter",
                    position_after="long",
                    input_status="ready",
                    reason="fast_above_entry_threshold",
                    feature_window_end=latest.end_ts,
                    fast_ema=fast_ema,
                    slow_ema=slow_ema,
                )
            return _hold(
                position,
                input_status="ready",
                reason="fast_not_above_entry_threshold",
                feature_window_end=latest.end_ts,
                fast_ema=fast_ema,
                slow_ema=slow_ema,
            )

        if fast_ema < slow_ema:
            return SessionResetEmaStateDecision(
                action="exit",
                position_after="flat",
                input_status="ready",
                reason="fast_below_slow",
                feature_window_end=latest.end_ts,
                fast_ema=fast_ema,
                slow_ema=slow_ema,
            )
        return _hold(
            position,
            input_status="ready",
            reason="fast_not_below_slow",
            feature_window_end=latest.end_ts,
            fast_ema=fast_ema,
            slow_ema=slow_ema,
        )


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


def _ema(closes: Sequence[Decimal], *, period: int) -> Decimal:
    """Seed from a period-specific SMA, then update recursively with Decimal."""

    if len(closes) < period:
        raise ValueError("EMA requires at least one full period")
    ema = sum(closes[:period], _ZERO) / Decimal(period)
    alpha = Decimal("2") / Decimal(period + 1)
    for close in closes[period:]:
        ema = ema + alpha * (close - ema)
    return ema


def _hold(
    position: EmaStatePosition,
    *,
    input_status: EmaStateInputStatus,
    reason: str,
    feature_window_end: datetime | None,
    fast_ema: Decimal | None = None,
    slow_ema: Decimal | None = None,
) -> SessionResetEmaStateDecision:
    return SessionResetEmaStateDecision(
        action="hold",
        position_after=position,
        input_status=input_status,
        reason=reason,
        feature_window_end=feature_window_end,
        fast_ema=fast_ema,
        slow_ema=slow_ema,
    )
