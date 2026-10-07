"""Pure ordered past-context for one same-vintage three-ETF D1 policy.

The caller supplies the exact prior NYSE schedule and decision OPEN timestamp.
UTC D1 completeness is representation geometry, not historical availability or
adjustment provenance. No source, calendar, target, scaler or model lives here.
"""

from __future__ import annotations

import math
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import MAX_EMAX, MIN_EMIN, ROUND_HALF_EVEN, Context, Decimal, localcontext

from thericher_v2.contracts import Bar, Timeframe, require_utc

SYMBOLS = ("SPY", "QQQ", "IWM")
CONTEXT_CLOSES = 32
CONTEXT_OBSERVATIONS = CONTEXT_CLOSES - 1
FEATURE_NAMES = ("close_log_return", "intraday_log_return", "range_log")
CHANNELS = tuple(f"{symbol}.{feature}" for symbol in SYMBOLS for feature in FEATURE_NAMES)
LOG_MEMO_MAX_ENTRIES = 1024


class JointD1PolicyInputUnavailable(ValueError):
    """A categorical failure of only this requested past-context window."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)

    def safe_facts(self) -> dict[str, str]:
        return {"status": "input_unavailable", "reason_code": self.reason_code}


@dataclass(frozen=True, slots=True, repr=False)
class JointD1PolicyContext:
    symbols: tuple[str, ...]
    channels: tuple[str, ...]
    scheduled_dates: tuple[date, ...]
    decision_at: datetime
    completed_through: datetime
    source_vintage_ref: str
    # Asset-major channels, each ordered over scheduled_dates[1:].
    features: tuple[tuple[float, ...], ...]

    @property
    def observation_dates(self) -> tuple[date, ...]:
        return self.scheduled_dates[1:]

    def safe_facts(self) -> dict[str, str | int]:
        return {
            "status": "ready",
            "symbol_count": len(self.symbols),
            "close_count_per_symbol": len(self.scheduled_dates),
            "channel_count": len(self.features),
            "observation_count_per_channel": len(self.observation_dates),
            "history_start": self.scheduled_dates[0].isoformat(),
            "history_last_session": self.scheduled_dates[-1].isoformat(),
            "completed_through": self.completed_through.isoformat(),
            "decision_at": self.decision_at.isoformat(),
        }


def _contract(condition: bool, reason_code: str) -> None:
    if not condition:
        raise ValueError(reason_code)


def _required_bars(
    bars: Sequence[Bar], *, symbol: str, dates: tuple[date, ...], decision_at: datetime
) -> tuple[Bar, ...]:
    _contract(isinstance(bars, Sequence) and not isinstance(bars, (str, bytes)), "source_sequence")
    date_set = frozenset(dates)
    required = []
    # Select past keys first: future values/support/completeness cannot mask inputs.
    for bar in bars:
        start = getattr(bar, "start_ts", None)
        if (
            isinstance(start, datetime)
            and start.tzinfo is not None
            and start.utcoffset() is not None
            and start.astimezone(UTC).date() in date_set
        ):
            required.append(bar)
    starts = [bar.start_ts for bar in required]
    if len(set(starts)) != len(starts):
        raise JointD1PolicyInputUnavailable("required_session_duplicate")
    if len(required) != CONTEXT_CLOSES:
        raise JointD1PolicyInputUnavailable("required_session_missing")
    expected = tuple(datetime.combine(day, time(), UTC) for day in dates)
    if tuple(starts) != expected:
        raise JointD1PolicyInputUnavailable("required_session_alignment_or_order")
    for bar in required:
        if (
            not isinstance(bar, Bar)
            or bar.symbol != symbol
            or bar.market != "US"
            or bar.timeframe is not Timeframe.D1
            or bar.start_ts.utcoffset() != timedelta(0)
        ):
            raise JointD1PolicyInputUnavailable("required_bar_identity")
        if bar.complete is not True or bar.end_ts > decision_at:
            raise JointD1PolicyInputUnavailable("required_bar_incomplete")
        values = (bar.open, bar.high, bar.low, bar.close, bar.volume)
        if any(type(value) is not Decimal or not value.is_finite() for value in values):
            raise JointD1PolicyInputUnavailable("required_bar_values_invalid")
        try:
            replace(bar)
        except (ValueError, TypeError, ArithmeticError):
            raise JointD1PolicyInputUnavailable("required_bar_values_invalid") from None
    return tuple(required)


def _log_ratio(numerator: Decimal, denominator: Decimal) -> float:
    try:
        with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN, Emax=MAX_EMAX, Emin=MIN_EMIN)):
            # Independent positive-price logs avoid forming an overflowing ratio.
            result = float(numerator.ln() - denominator.ln())
    except (ValueError, OverflowError, ArithmeticError):
        raise JointD1PolicyInputUnavailable("features_not_representable") from None
    if not math.isfinite(result) or (numerator != denominator and result == 0):
        raise JointD1PolicyInputUnavailable("features_not_representable")
    return result


class JointD1PolicyLogMemo:
    """One preparation-local bounded cache, cleared even when its caller fails.

    Only successful results of the unchanged fixed-precision ratio function are
    memoized. Exact Decimal representations are keys, not dates or availability.
    No window, source validation or failure is cached. Do not share across jobs.
    """

    __slots__ = ("_cache", "_active", "_closed", "_hits", "_misses")

    def __init__(self) -> None:
        self._cache: OrderedDict[tuple, float] = OrderedDict()
        self._active = self._closed = False
        self._hits = self._misses = 0

    def __enter__(self) -> JointD1PolicyLogMemo:
        _contract(not self._active and not self._closed, "log_memo_scope")
        self._active = True
        return self

    def __exit__(self, *_exc) -> None:
        self._cache.clear()
        self._active, self._closed = False, True

    def ratio(self, numerator: Decimal, denominator: Decimal) -> float:
        _contract(self._active, "log_memo_scope")
        _contract(
            all(type(v) is Decimal and v.is_finite() and v > 0 for v in (numerator, denominator)),
            "log_memo_prices",
        )
        key = (numerator.as_tuple(), denominator.as_tuple())
        if key in self._cache:
            self._hits += 1
            self._cache.move_to_end(key)
            return self._cache[key]
        self._misses += 1
        result = _log_ratio(numerator, denominator)
        if len(self._cache) == LOG_MEMO_MAX_ENTRIES:
            self._cache.popitem(last=False)
        self._cache[key] = result
        return result

    def safe_facts(self) -> dict[str, str | int]:
        return dict(
            status="active" if self._active else "closed" if self._closed else "unused",
            capacity=LOG_MEMO_MAX_ENTRIES,
            entries=len(self._cache),
            hits=self._hits,
            misses=self._misses,
        )


def build_joint_d1_policy_context(
    bars_by_symbol: Mapping[str, Sequence[Bar]],
    *,
    vintage_ref_by_symbol: Mapping[str, str],
    scheduled_dates: tuple[date, ...],
    decision_at: datetime,
    log_memo: JointD1PolicyLogMemo | None = None,
) -> JointD1PolicyContext:
    """Build immutable, finite 9x31 features from exactly 32 scheduled past Bars.

    For each asset in SYMBOLS, channels are log(C[t]/C[t-1]), log(C[t]/O[t])
    and log(H[t]/L[t]), using only the last 31 Bars plus the first prior close.
    The caller binds NYSE dates, adjusted values, a common source vintage and
    the actual decision OPEN; this helper neither infers nor verifies those
    source/calendar attestations. Selected Bars must be complete UTC-midnight
    US D1 records ending at or before the cutoff. Current/future support and
    current OPEN values are irrelevant. No whole-period availability mask,
    imputation, normalization or source replacement is performed.
    An optional active preparation-local log_memo reuses only ratio arithmetic;
    every window's required Bars are still independently selected and validated.
    """
    _contract(isinstance(bars_by_symbol, Mapping), "source_columns")
    sources = dict(bars_by_symbol)
    _contract(set(sources) == set(SYMBOLS), "source_columns")
    _contract(isinstance(vintage_ref_by_symbol, Mapping), "source_vintage_columns")
    vintages = dict(vintage_ref_by_symbol)
    _contract(set(vintages) == set(SYMBOLS), "source_vintage_columns")
    _contract(
        all(isinstance(value, str) and bool(value.strip()) for value in vintages.values()),
        "source_vintage_ref",
    )
    if len(set(vintages.values())) != 1:
        raise JointD1PolicyInputUnavailable("source_vintage_mismatch")
    _contract(
        type(scheduled_dates) is tuple
        and len(scheduled_dates) == CONTEXT_CLOSES
        and all(type(day) is date for day in scheduled_dates)
        and all(
            left < right for left, right in zip(scheduled_dates, scheduled_dates[1:], strict=False)
        ),
        "scheduled_dates",
    )
    _contract(isinstance(decision_at, datetime), "decision_at")
    decision_at = require_utc(decision_at, "decision_at")
    _contract(scheduled_dates[-1] < decision_at.date(), "scheduled_dates_not_past")
    selected = tuple(
        _required_bars(
            sources[symbol], symbol=symbol, dates=scheduled_dates, decision_at=decision_at
        )
        for symbol in SYMBOLS
    )
    _contract(log_memo is None or isinstance(log_memo, JointD1PolicyLogMemo), "log_memo_type")
    ratio = _log_ratio if log_memo is None else log_memo.ratio
    features = tuple(
        channel
        for bars in selected
        for channel in (
            tuple(
                ratio(right.close, left.close) for left, right in zip(bars, bars[1:], strict=False)
            ),
            tuple(ratio(bar.close, bar.open) for bar in bars[1:]),
            tuple(ratio(bar.high, bar.low) for bar in bars[1:]),
        )
    )
    return JointD1PolicyContext(
        symbols=SYMBOLS,
        channels=CHANNELS,
        scheduled_dates=scheduled_dates,
        decision_at=decision_at,
        completed_through=selected[0][-1].end_ts,
        source_vintage_ref=vintages[SYMBOLS[0]],
        features=features,
    )
