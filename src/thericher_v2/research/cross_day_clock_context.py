"""Pure endpoint-OPEN history for one caller-attested prior NYSE schedule.

The caller owns the exact calendar, source vintage and actual decision clock.
This helper infers none of them and reads no source, target or current-day data.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import MAX_EMAX, MIN_EMIN, ROUND_HALF_EVEN, Context, Decimal, localcontext
from types import MappingProxyType
from zoneinfo import ZoneInfo

from thericher_v2.contracts import Bar, Timeframe

CONTEXT_SESSIONS = 20
CLOCKS = ("10:00", "12:00", "14:00")
_EASTERN = ZoneInfo("America/New_York")
_MINUTE = timedelta(minutes=1)
_HORIZON = timedelta(minutes=30)
_BPS = Decimal(10000)


class CrossDayClockInputUnavailable(ValueError):
    """One categorical failure of this exact symbol/history scope only."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)

    def safe_facts(self) -> dict[str, str]:
        return {"status": "input_unavailable", "reason_code": self.reason_code}


def _contract(condition: bool, reason_code: str) -> None:
    if not condition:
        raise ValueError(reason_code)


def _utc(value: datetime, reason_code: str) -> datetime:
    _contract(
        type(value) is datetime and value.tzinfo is not None and value.utcoffset() == timedelta(0),
        reason_code,
    )
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class ClockSession:
    """Caller-attested NYSE date and UTC regular-session boundaries, not a calendar."""

    session_date: date
    open_ts: datetime
    close_ts: datetime

    def __post_init__(self) -> None:
        _contract(type(self.session_date) is date, "session_date")
        object.__setattr__(self, "open_ts", _utc(self.open_ts, "session_open_utc"))
        object.__setattr__(self, "close_ts", _utc(self.close_ts, "session_close_utc"))
        _contract(self.open_ts < self.close_ts, "session_interval")
        _contract(
            self.open_ts.astimezone(_EASTERN).date() == self.session_date
            and self.close_ts.astimezone(_EASTERN).date() == self.session_date,
            "session_date_alignment",
        )


@dataclass(frozen=True, slots=True, repr=False)
class CrossDayClockContext:
    symbol: str
    scheduled_sessions: tuple[ClockSession, ...]
    decision_at: datetime
    completed_through: datetime
    mean_return_bps_by_clock: Mapping[str, Decimal] = field(repr=False)
    pooled_mean_return_bps: Decimal = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "scheduled_sessions", tuple(self.scheduled_sessions))
        means = dict(self.mean_return_bps_by_clock)
        _contract(tuple(means) == CLOCKS, "context_clock_order")
        _contract(
            all(type(value) is Decimal and value.is_finite() for value in means.values())
            and type(self.pooled_mean_return_bps) is Decimal
            and self.pooled_mean_return_bps.is_finite(),
            "context_values",
        )
        object.__setattr__(self, "mean_return_bps_by_clock", MappingProxyType(means))

    def safe_facts(self) -> dict[str, str | int | tuple[str, ...]]:
        return {
            "status": "ready",
            "session_count": len(self.scheduled_sessions),
            "clocks_et": CLOCKS,
            "clock_count": len(CLOCKS),
            "observation_count_per_clock": CONTEXT_SESSIONS,
            "pooled_observation_count": CONTEXT_SESSIONS * len(CLOCKS),
            "required_endpoint_count": CONTEXT_SESSIONS * len(CLOCKS) * 2,
            "entry_offset_minutes": 1,
            "exit_horizon_minutes": 30,
            "history_start": self.scheduled_sessions[0].session_date.isoformat(),
            "history_last_session": self.scheduled_sessions[-1].session_date.isoformat(),
            "completed_through": self.completed_through.isoformat(),
            "decision_at": self.decision_at.isoformat(),
        }


def _select_endpoints(
    bars: Sequence[Bar], *, keys: frozenset[datetime], symbol: str, decision_at: datetime
) -> dict[datetime, Bar]:
    selected = {}
    # Select exact past keys before touching identity, completeness or OPEN values.
    for bar in bars:
        start = getattr(bar, "start_ts", None)
        if type(start) is not datetime or start.tzinfo is None:
            continue
        try:
            key = start.astimezone(UTC) if start.utcoffset() is not None else None
        except (ValueError, TypeError, ArithmeticError):
            continue
        if key not in keys:
            continue
        if key in selected:
            raise CrossDayClockInputUnavailable("required_endpoint_duplicate")
        selected[key] = bar
    if set(selected) != keys:
        raise CrossDayClockInputUnavailable("required_endpoint_missing")
    for bar in selected.values():
        if (
            not isinstance(bar, Bar)
            or bar.symbol != symbol
            or bar.market != "US"
            or bar.timeframe is not Timeframe.M1
            or bar.start_ts.utcoffset() != timedelta(0)
        ):
            raise CrossDayClockInputUnavailable("required_endpoint_identity")
        if bar.complete is not True or bar.end_ts > decision_at:
            raise CrossDayClockInputUnavailable("required_endpoint_incomplete")
        if type(bar.open) is not Decimal or not bar.open.is_finite() or bar.open <= 0:
            raise CrossDayClockInputUnavailable("required_endpoint_open_invalid")
    return selected


def build_cross_day_clock_context(
    bars: Sequence[Bar],
    *,
    symbol: str,
    scheduled_sessions: Sequence[ClockSession],
    decision_at: datetime,
) -> CrossDayClockContext:
    """Mean signed OPEN-to-OPEN bps over exactly 20 prior dates and three clocks.

    Keys are E=C+1 minute and X=E+30 minutes for 10:00/12:00/14:00 Eastern.
    Each required M1 endpoint must be complete and end by decision_at and its
    session close. No intermediate rows or endpoint H/L/C/volume are consumed.
    All three clocks share one past-only eligibility contract. Unsupported prior
    early-close geometry or a missing/duplicate/invalid endpoint is unavailable;
    never search for 20 available dates. The caller separately excludes current
    unsupported clocks and binds NYSE calendar, source and OPEN availability.

    Arithmetic uses a private 50-digit, half-even Decimal context, independent
    of the ambient context. Pooled mean uses all 60 signed observations, not
    rounded per-clock means. No imputation, scaling or future-support mask.
    """
    _contract(isinstance(bars, Sequence) and not isinstance(bars, (str, bytes)), "bars_sequence")
    _contract(type(symbol) is str and bool(symbol) and symbol == symbol.strip().upper(), "symbol")
    _contract(
        isinstance(scheduled_sessions, Sequence)
        and not isinstance(scheduled_sessions, (str, bytes)),
        "scheduled_sessions",
    )
    sessions = tuple(scheduled_sessions)
    _contract(
        len(sessions) == CONTEXT_SESSIONS
        and all(type(session) is ClockSession for session in sessions)
        and all(
            left.session_date < right.session_date
            for left, right in zip(sessions, sessions[1:], strict=False)
        ),
        "scheduled_sessions",
    )
    decision_at = _utc(decision_at, "decision_at_utc")
    _contract(
        sessions[-1].session_date < decision_at.astimezone(_EASTERN).date()
        and all(session.close_ts <= decision_at for session in sessions),
        "scheduled_sessions_not_past",
    )
    endpoints_by_clock = {}
    for label in CLOCKS:
        pairs = []
        for session in sessions:
            clock = datetime.combine(session.session_date, time.fromisoformat(label), _EASTERN)
            entry = clock.astimezone(UTC) + _MINUTE
            exit_at = entry + _HORIZON
            if entry < session.open_ts or exit_at + _MINUTE > session.close_ts:
                raise CrossDayClockInputUnavailable("required_clock_geometry_unsupported")
            pairs.append((entry, exit_at))
        endpoints_by_clock[label] = tuple(pairs)
    keys = frozenset(key for pairs in endpoints_by_clock.values() for pair in pairs for key in pair)
    selected = _select_endpoints(bars, keys=keys, symbol=symbol, decision_at=decision_at)
    try:
        with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN, Emax=MAX_EMAX, Emin=MIN_EMIN)):
            returns = {
                label: tuple(
                    (selected[exit_at].open - selected[entry].open) / selected[entry].open * _BPS
                    for entry, exit_at in pairs
                )
                for label, pairs in endpoints_by_clock.items()
            }
            means = {
                label: sum(values, Decimal(0)) / CONTEXT_SESSIONS
                for label, values in returns.items()
            }
            pooled = sum((value for values in returns.values() for value in values), Decimal(0)) / (
                CONTEXT_SESSIONS * len(CLOCKS)
            )
    except ArithmeticError:
        raise CrossDayClockInputUnavailable("returns_not_representable") from None
    if any(not value.is_finite() for value in (*means.values(), pooled)):
        raise CrossDayClockInputUnavailable("returns_not_representable")
    return CrossDayClockContext(
        symbol=symbol,
        scheduled_sessions=sessions,
        decision_at=decision_at,
        completed_through=max(key + _MINUTE for key in keys),
        mean_return_bps_by_clock=means,
        pooled_mean_return_bps=pooled,
    )
