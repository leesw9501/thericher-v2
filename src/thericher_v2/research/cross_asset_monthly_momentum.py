"""Pure fixed calendar-year price momentum; no source IO or performance claim.

PriceClose explicitly carries raw KIS MODP0 prices, never adjusted-source rows.
A caller-owned vintage/calendar binds inputs, not
historical publication, corporate actions, total return or next-OPEN fills.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Context, Decimal, DecimalException, Underflow, localcontext
from types import MappingProxyType

from thericher_v2.research.cross_asset_etf_input import (
    INSTRUMENT_ORDER,
    CrossAssetInputUnavailable,
    CrossAssetSession,
)
from thericher_v2.research.three_asset_nav import ThreeAssetNavError, ThreeAssetTarget

DECIMAL_CONTEXT = Context(prec=50, rounding=ROUND_HALF_EVEN)
DECIMAL_CONTEXT.traps[Underflow] = True
THIRD = Decimal("0." + "3" * 45)
BASE_WEIGHTS = (THIRD,) * 3
PRICE_BASIS = "kis_modp0_raw"


def _require(condition, code):
    if not condition:
        raise CrossAssetInputUnavailable(code)


def _vintage(value):
    _require(type(value) is str and bool(value) and value == value.strip(), "vintage_invalid")


def previous_year_cutoff(day: date) -> date:
    """Exact previous calendar year; only February29 clamps to February28."""
    _require(type(day) is date and day.year > 1, "cutoff_date_invalid")
    return day.replace(year=day.year - 1, day=28 if day.month == 2 and day.day == 29 else day.day)


def _month_index(day):
    return day.year * 12 + day.month - 1


def _calendar(sessions):
    _require(type(sessions) is tuple and len(sessions) >= 2, "calendar_required")
    for session in sessions:
        _require(type(session) is CrossAssetSession, "calendar_type_invalid")
        session.__post_init__()
    _require(all(a.session_date < b.session_date and a.close_at < b.open_at
                 for a, b in zip(sessions, sessions[1:], strict=False)), "calendar_order_invalid")


@dataclass(frozen=True, slots=True)
class MonthlyMomentumPlan:
    entry_session_date: date
    entry_at: datetime
    decision_session_date: date
    decision_at: datetime
    previous_year_cutoff: date
    anchor_session_date: date
    anchor_close_at: datetime

    def __post_init__(self):
        _require(all(type(d) is date for d in (self.entry_session_date, self.decision_session_date,
                                             self.previous_year_cutoff, self.anchor_session_date)),
                 "plan_dates_invalid")
        _require(all(type(t) is datetime and t.utcoffset() == timedelta(0)
                     for t in (self.entry_at, self.decision_at, self.anchor_close_at)),
                 "plan_not_utc")
        _require(self.previous_year_cutoff == previous_year_cutoff(self.decision_session_date)
                 and self.anchor_session_date <= self.previous_year_cutoff
                 and self.anchor_close_at < self.decision_at < self.entry_at
                 and self.anchor_close_at.date() == self.anchor_session_date
                 and self.decision_at.date() == self.decision_session_date
                 and self.entry_at.date() == self.entry_session_date
                 and _month_index(self.entry_session_date)
                 == _month_index(self.decision_session_date) + 1, "plan_geometry_invalid")


def plan_monthly_momentum(
    scheduled_sessions: tuple[CrossAssetSession, ...],
    *,
    entry_session_date: date,
    decision_at: datetime,
) -> MonthlyMomentumPlan:
    """Next month's first declared session, using its immediately prior CLOSE.

    The anchor is selected from the frozen calendar before source values/support
    are inspected. A missing selected observation never moves it backward.
    Calendar completeness and observed availability remain caller responsibilities.
    """
    _calendar(scheduled_sessions)
    dates = tuple(s.session_date for s in scheduled_sessions)
    _require(type(entry_session_date) is date and entry_session_date in dates,
             "entry_session_missing")
    index = dates.index(entry_session_date)
    _require(index > 0, "previous_close_missing")
    previous, entry = scheduled_sessions[index - 1], scheduled_sessions[index]
    _require(type(decision_at) is datetime and decision_at.utcoffset() == timedelta(0)
             and decision_at == previous.close_at, "decision_not_previous_close")
    _require(_month_index(entry_session_date) == _month_index(previous.session_date) + 1,
             "entry_not_next_month_first_session")
    cutoff = previous_year_cutoff(previous.session_date)
    anchors = tuple(s for s in scheduled_sessions[:index] if s.session_date <= cutoff)
    _require(bool(anchors), "scheduled_year_history_missing")
    anchor = anchors[-1]
    return MonthlyMomentumPlan(entry_session_date, entry.open_at, previous.session_date,
                               previous.close_at, cutoff, anchor.session_date, anchor.close_at)


@dataclass(frozen=True, slots=True)
class PriceClose:
    symbol: str
    session_date: date
    vintage_ref: str = field(repr=False)
    close: Decimal = field(repr=False)
    price_basis: str = PRICE_BASIS

    def __post_init__(self):
        _require(type(self.symbol) is str and self.symbol in INSTRUMENT_ORDER, "row_symbol_invalid")
        _require(type(self.session_date) is date, "row_date_invalid")
        _vintage(self.vintage_ref)
        _require(type(self.price_basis) is str and self.price_basis == PRICE_BASIS,
                 "price_basis_invalid")
        _require(type(self.close) is Decimal and self.close.is_finite() and self.close > 0,
                 "price_close_invalid")


@dataclass(frozen=True, slots=True)
class MonthlyMomentumSignal:
    plan: MonthlyMomentumPlan
    price_momentum: tuple[Decimal, Decimal, Decimal] = field(repr=False)
    target: ThreeAssetTarget = field(repr=False)
    vintage_ref: str = field(repr=False)

    def __post_init__(self):
        _require(type(self.plan) is MonthlyMomentumPlan, "signal_plan_invalid")
        self.plan.__post_init__()
        _vintage(self.vintage_ref)
        _require(type(self.price_momentum) is tuple and len(self.price_momentum) == 3
                 and all(type(v) is Decimal and v.is_finite() for v in self.price_momentum),
                 "signal_momentum_invalid")
        _require(type(self.target) is ThreeAssetTarget, "signal_target_invalid")
        try:
            self.target.__post_init__()
        except ThreeAssetNavError:
            raise CrossAssetInputUnavailable("signal_target_invalid") from None
        with localcontext(DECIMAL_CONTEXT):
            expected = tuple(THIRD if value > 0 else Decimal(0) for value in self.price_momentum)
            _require(self.target.weights3 == expected
                     and self.target.cash_weight == Decimal(1) - sum(expected, Decimal(0)),
                     "signal_target_mismatch")

    def safe_facts(self):
        return dict(status="ready", instrument_order=INSTRUMENT_ORDER,
                    anchor_session=self.plan.anchor_session_date.isoformat(),
                    cutoff=self.plan.previous_year_cutoff.isoformat(),
                    decision_at=self.plan.decision_at.isoformat(),
                    entry_session=self.plan.entry_session_date.isoformat(),
                    entry_at=self.plan.entry_at.isoformat(), required_close_count=6,
                    price_basis=PRICE_BASIS, splits_and_dividends="not_applied",
                    publication_availability="not_observed", paper_input=False)


def build_monthly_momentum(
    rows_by_symbol: Mapping[str, Sequence[PriceClose]],
    *,
    scheduled_sessions: tuple[CrossAssetSession, ...],
    entry_session_date: date,
    decision_at: datetime,
    vintage_ref: str,
) -> MonthlyMomentumSignal:
    """Positive price return activates only its fixed third; unused thirds stay cash.

    Exactly the three anchor and three decision CLOSEs are required. Other rows,
    including entry/payoff marks, cannot change features or input availability.
    No corporate-action correction, distribution reinvestment or scaling is inferred.
    """
    plan = plan_monthly_momentum(scheduled_sessions, entry_session_date=entry_session_date,
                                decision_at=decision_at)
    _vintage(vintage_ref)
    _require(isinstance(rows_by_symbol, Mapping)
             and set(rows_by_symbol) == set(INSTRUMENT_ORDER), "source_symbols_invalid")
    required = {plan.anchor_session_date, plan.decision_session_date}
    momentum = []
    try:
        with localcontext(DECIMAL_CONTEXT):
            for symbol in INSTRUMENT_ORDER:
                source = rows_by_symbol[symbol]
                _require(isinstance(source, Sequence) and not isinstance(source, (str, bytes)),
                         "source_sequence_invalid")
                selected = {}
                for row in source:
                    day = getattr(row, "session_date", None)
                    if type(day) is date and day in required:
                        _require(day not in selected, "required_session_duplicate")
                        _require(type(row) is PriceClose, "required_row_type_invalid")
                        row.__post_init__()
                        _require(row.symbol == symbol, "required_row_symbol_mismatch")
                        _require(row.vintage_ref == vintage_ref, "required_vintage_mismatch")
                        selected[day] = row.close
                _require(set(selected) == required, "required_session_missing")
                anchor = selected[plan.anchor_session_date]
                current = selected[plan.decision_session_date]
                momentum.append((current - anchor) / anchor)
            weights = tuple(weight if value > 0 else Decimal(0)
                            for weight, value in zip(BASE_WEIGHTS, momentum, strict=True))
            cash = Decimal(1) - sum(weights, Decimal(0))
            target = ThreeAssetTarget(weights, cash)
    except DecimalException:
        raise CrossAssetInputUnavailable("numeric_range") from None
    return MonthlyMomentumSignal(plan, tuple(momentum), target, vintage_ref)


def monthly_targets(
    signals: Sequence[MonthlyMomentumSignal],
    *,
    expected_entry_dates: tuple[date, ...],
) -> Mapping[date, ThreeAssetTarget]:
    """Exact monthly keys only; absent daily keys mean carry, not missing signals.

    The caller supplies every frozen monthly rebalance key. A failed monthly
    signal cannot silently become a missing ledger action or a cash decision.
    """
    _require(type(expected_entry_dates) is tuple and bool(expected_entry_dates)
             and all(type(day) is date for day in expected_entry_dates)
             and all(a < b and _month_index(a) < _month_index(b)
                     for a, b in zip(expected_entry_dates, expected_entry_dates[1:], strict=False)),
             "monthly_keys_invalid")
    _require(isinstance(signals, Sequence) and not isinstance(signals, (str, bytes)),
             "signals_invalid")
    targets = {}
    vintage = None
    for signal in signals:
        _require(type(signal) is MonthlyMomentumSignal, "signal_type_invalid")
        signal.__post_init__()
        if vintage is None:
            vintage = signal.vintage_ref
        _require(signal.vintage_ref == vintage, "monthly_vintage_mismatch")
        day = signal.plan.entry_session_date
        _require(day not in targets, "monthly_signal_duplicate")
        targets[day] = signal.target
    _require(set(targets) == set(expected_entry_dates), "monthly_signal_missing_or_extra")
    return MappingProxyType({day: targets[day] for day in expected_entry_dates})
