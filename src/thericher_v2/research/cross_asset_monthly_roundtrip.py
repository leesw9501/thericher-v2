"""Pure monthly OPEN/CLOSE roundtrips on one continuous daily-marked cash NAV.

Caller-frozen calendar dates/boundaries select every required mark, never price
support. Calendar completeness, price grade, corporate actions, availability
and ideal fractional fills remain caller assumptions. Positional prices follow
SPY/TLT/GLD order; legacy SYMBOLS and adjusted-source records are not relabeled.
No IO, model, strategy, fit, monthly capital reset or observed-date inference.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from thericher_v2.research import three_asset_nav as nav
from thericher_v2.research.cross_asset_etf_input import INSTRUMENT_ORDER


def _require(condition, code):
    if not condition:
        raise nav.ThreeAssetNavError(code)


def _month(day):
    return day.year * 12 + day.month - 1


@dataclass(frozen=True, slots=True)
class MonthlyBoundary:
    entry_session_date: date
    exit_session_date: date

    def __post_init__(self):
        first, last = self.entry_session_date, self.exit_session_date
        _require(type(first) is date and type(last) is date
                 and first <= last and _month(first) == _month(last), "month_boundary_invalid")


def _boundaries(scheduled_dates, month_boundaries):
    _require(type(scheduled_dates) is tuple and bool(scheduled_dates)
             and all(type(day) is date for day in scheduled_dates)
             and all(a < b for a, b in zip(scheduled_dates, scheduled_dates[1:], strict=False)),
             "calendar_invalid")
    _require(type(month_boundaries) is tuple and bool(month_boundaries), "month_boundaries_invalid")
    for boundary in month_boundaries:
        _require(type(boundary) is MonthlyBoundary, "month_boundary_type_invalid")
        boundary.__post_init__()
    expected = []
    first = last = scheduled_dates[0]
    for day in scheduled_dates[1:]:
        if _month(day) != _month(last):
            _require(_month(day) == _month(last) + 1, "calendar_month_gap")
            expected.append(MonthlyBoundary(first, last))
            first = day
        last = day
    expected.append(MonthlyBoundary(first, last))
    _require(month_boundaries == tuple(expected), "month_boundary_schedule_mismatch")
    return {boundary.entry_session_date for boundary in month_boundaries}, {
        boundary.exit_session_date for boundary in month_boundaries}


def _targets(targets, expected_entries):
    if isinstance(targets, Mapping):
        pairs = tuple(targets.items())
    else:
        _require(isinstance(targets, Sequence) and not isinstance(targets, (str, bytes)),
                 "targets_invalid")
        pairs = tuple(targets)
    result = {}
    for pair in pairs:
        _require(type(pair) is tuple and len(pair) == 2, "target_pair_invalid")
        day, target = pair
        _require(type(day) is date, "target_date_invalid")
        _require(day not in result, "target_date_duplicate")
        _require(type(target) is nav.ThreeAssetTarget, "target_invalid")
        target.__post_init__()
        result[day] = target
    _require(set(result) == expected_entries, "target_entries_missing_or_extra")
    return result


@nav._decimal
def replay_monthly_roundtrips(
    days: Sequence[nav.ThreeAssetDay],
    targets: Mapping[date, nav.ThreeAssetTarget] | Sequence[tuple[date, nav.ThreeAssetTarget]],
    *,
    scheduled_dates: tuple[date, ...],
    month_boundaries: tuple[MonthlyBoundary, ...],
    cost_bps: Decimal,
    instrument_order: tuple[str, ...] = INSTRUMENT_ORDER,
) -> nav.ThreeAssetReplay:
    """Initial NAV1 once, monthly OPEN actions, daily CLOSE marks, monthly exit.

    Every frozen calendar mark is required, including cash-only days. Missing
    signals are not absent ledger actions: exactly one supplied target per
    month is mandatory. Month-end liquidation carries net cash and the daily
    return denominator forward. Future daily utility must use this complete
    trace, not the target helper's two-endpoint synthetic marks.
    """
    _require(type(instrument_order) is tuple and instrument_order == INSTRUMENT_ORDER,
             "instrument_order_invalid")
    entries, exits = _boundaries(scheduled_dates, month_boundaries)
    actions = _targets(targets, entries)
    _require(isinstance(days, Sequence) and not isinstance(days, (str, bytes)), "days_invalid")
    records = tuple(days)
    _require(all(type(day) is nav.ThreeAssetDay for day in records), "day_invalid")
    _require(tuple(day.date for day in records) == scheduled_dates, "daily_mark_schedule_mismatch")
    for day in records:
        day.__post_init__()
    fee = nav._fee(cost_bps)
    state, previous = nav.ThreeAssetState(Decimal(1)), Decimal(1)
    daily = []
    total_fees = total_notional = Decimal(0)
    for day in records:
        paid = traded = Decimal(0)
        if day.date in entries:
            target = actions[day.date]
            entry = nav._rebalance(state, nav.ThreeAssetPrices(day.adj_open3),
                                   target.weights3, target.cash_weight, fee)
            state, paid, traded = entry.state, entry.fees, entry.turnover
        close = nav.ThreeAssetPrices(day.adj_close3)
        if day.date in exits:
            exit_trade = nav.liquidate_close(state, close, cost_bps)
            state = exit_trade.state
            paid, traded = paid + exit_trade.fees, traded + exit_trade.turnover
        marked = nav.mark_close(state, close)
        _require(marked.nav > 0, "nonpositive_nav")
        growth = marked.nav / previous
        daily.append(nav.ThreeAssetDaily(day.date, marked.nav, paid, traded, state.cash,
                                        all(q == 0 for q in state.quantities),
                                        growth - 1, growth.ln()))
        total_fees += paid
        total_notional += traded
        previous = marked.nav
    _require(all(q == 0 for q in state.quantities) and daily[-1].flat, "final_not_flat")
    return nav.ThreeAssetReplay(tuple(daily), state, total_fees, total_notional)
