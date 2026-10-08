from __future__ import annotations

import builtins
import socket
from dataclasses import replace
from datetime import date
from decimal import ROUND_DOWN, Decimal, localcontext

import pytest

from thericher_v2.research import cross_asset_monthly_roundtrip as monthly
from thericher_v2.research import three_asset_nav as nav
from thericher_v2.research.cross_asset_etf_input import CrossAssetSession
from thericher_v2.research.cross_asset_hedge_failure_input import (
    RawD1Price,
    build_monthly_target,
)
from thericher_v2.research.cross_asset_monthly_momentum import THIRD

D = Decimal
DEFAULT_COST = D(5)
DATES = (date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 31),
         date(2024, 2, 1), date(2024, 2, 2), date(2024, 2, 29))
BOUNDS = (monthly.MonthlyBoundary(DATES[0], DATES[2]),
          monthly.MonthlyBoundary(DATES[3], DATES[5]))
ORDER = ("SPY", "TLT", "GLD")


def allocation(weights=None):
    weights = (THIRD,) * 3 if weights is None else weights
    with localcontext() as context:
        context.prec = 50
        return nav.ThreeAssetTarget(weights, 1 - sum(weights, D(0)))


def days():
    return (
        nav.ThreeAssetDay(DATES[0], (D(100),) * 3, (D(110), D(105), D(100))),
        nav.ThreeAssetDay(DATES[1], (D(120), D(105), D(100)), (D(125), D(100), D(95))),
        nav.ThreeAssetDay(DATES[2], (D(125), D(100), D(95)), (D(130), D(110), D(90))),
        nav.ThreeAssetDay(DATES[3], (D(100),) * 3, (D(105), D(100), D(100))),
        nav.ThreeAssetDay(DATES[4], (D(105), D(100), D(100)), (D(110), D(95), D(90))),
        nav.ThreeAssetDay(DATES[5], (D(110), D(95), D(90)), (D(90), D(100), D(110))),
    )


def replay(records=None, targets=None, dates=DATES, bounds=BOUNDS, cost=DEFAULT_COST, order=ORDER):
    records = days() if records is None else records
    targets = {DATES[0]: allocation(), DATES[3]: allocation()} if targets is None else targets
    return monthly.replay_monthly_roundtrips(records, targets, scheduled_dates=dates,
                                            month_boundaries=bounds, cost_bps=cost,
                                            instrument_order=order)


@pytest.mark.parametrize("cost", [D(0), D("2.5"), D(5), D(10)])
def test_one_month_exact_canonical_ledger_parity_no_double_final_exit(cost):
    records = days()[:3]
    targets = {DATES[0]: allocation()}
    result = replay(records, targets, DATES[:3], BOUNDS[:1], cost)
    assert result == nav.replay(records, targets, cost)
    assert result.daily[-1].flat and result.final_state.quantities == (D(0),) * 3


def test_unit_target_agrees_but_policy_cash_and_capital_are_not_reset_each_month():
    from datetime import UTC, datetime, time

    records, result = days(), replay()
    factors = []
    for boundary, block in zip(BOUNDS, (records[:3], records[3:]), strict=True):
        schedule = tuple(
            CrossAssetSession(day.date, datetime.combine(day.date, time(14, 30), UTC),
                              datetime.combine(day.date, time(21), UTC)) for day in block)
        rows = {symbol: (RawD1Price(symbol, boundary.entry_session_date, "synthetic-raw",
                                    open=block[0].adj_open3[i]),
                         RawD1Price(symbol, boundary.exit_session_date, "synthetic-raw",
                                    close=block[-1].adj_close3[i]))
                for i, symbol in enumerate(ORDER)}
        factors.append(build_monthly_target(rows, scheduled_month=schedule,
                                             vintage_ref="synthetic-raw").net_factor)
    assert result.daily[2].nav == factors[0]
    assert result.daily[2].cash == result.daily[2].nav
    second_unit = nav.replay(records[3:], {DATES[3]: allocation()}, D(5))
    with localcontext() as context:
        context.prec = 50
        assert abs(result.final_nav - factors[0] * factors[1]) < D("1e-45")
        assert abs(result.daily[3].nav - factors[0] * second_unit.daily[0].nav) < D("1e-45")
        assert abs(result.daily[3].fees - factors[0] * second_unit.daily[0].fees) < D("1e-45")
    assert result.final_nav != factors[1]


@pytest.mark.parametrize("cost", [D(0), D(5), D(10)])
def test_constant_prices_monthly_actual_roundtrip_fees_carry_cash(cost):
    records = tuple(nav.ThreeAssetDay(day, (D(100),) * 3, (D(100),) * 3) for day in DATES)
    result = replay(records, cost=cost)
    with localcontext() as context:
        context.prec = 50
        invested, f = 3 * THIRD, cost / 10000
        factor = (1 - f * invested) / (1 + f * invested)
        assert abs(result.daily[2].nav - factor) < D("1e-45")
        assert abs(result.final_nav - factor * factor) < D("1e-45")
        assert abs(result.total_fees - f * result.total_traded_notional) < D("1e-45")
    assert result.daily[1].fees == result.daily[4].fees == 0
    assert result.daily[2].flat and result.daily[-1].flat


def test_every_daily_return_uses_previous_continuous_nav_and_telescope():
    result = replay()
    with localcontext() as context:
        context.prec = 50
        previous = D(1)
        for day in result.daily:
            assert day.simple_return == day.nav / previous - 1
            assert day.log_return == (day.nav / previous).ln()
            previous = day.nav
        assert abs(sum(result.log_returns, D(0)) - result.final_nav.ln()) < D("1e-45")
    assert len(result.daily) == len(DATES)


def test_inside_month_overnight_positions_carry_no_daily_rebalance():
    targets = {DATES[0]: allocation((THIRD, D(0), D(0))),
               DATES[3]: allocation((D(0), D(0), D(0)))}
    result = replay(targets=targets)
    assert result.daily[1].cash == result.daily[0].cash
    assert result.daily[1].nav > result.daily[0].nav
    assert result.daily[1].fees == result.daily[1].traded_notional == 0
    changed = list(days())
    changed[1] = replace(changed[1], adj_open3=(D("9000"), D("8000"), D("7000")))
    assert replay(tuple(changed), targets) == result


def test_intermediate_close_changes_daily_utility_not_endpoint_factor():
    original = replay()
    changed = list(days())
    changed[1] = replace(changed[1], adj_close3=(D(50), D(50), D(50)))
    result = replay(tuple(changed))
    assert result.final_nav == original.final_nav
    assert result.total_fees == original.total_fees
    assert result.log_returns != original.log_returns


def test_explicit_cash_month_preserves_previous_net_capital_and_all_flat_marks():
    result = replay(targets={DATES[0]: allocation(), DATES[3]: allocation((D(0),) * 3)})
    assert result.final_nav == result.daily[2].nav != 1
    for day in result.daily[3:]:
        assert day.flat and day.fees == day.traded_notional == day.log_return == 0
        assert day.nav == result.daily[2].nav


def test_independent_asset_price_scale_invariance_and_legacy_symbols_unchanged():
    original = replay()
    records = tuple(nav.ThreeAssetDay(day.date,
                                    tuple(p * s for p, s in zip(day.adj_open3, (2, 3, 5),
                                                                strict=True)),
                                    tuple(p * s for p, s in zip(day.adj_close3, (2, 3, 5),
                                                                strict=True))) for day in days())
    scaled = replay(records)
    with localcontext() as context:
        context.prec = 50
        assert all(abs(a - b) < D("1e-45")
                   for a, b in zip(original.navs, scaled.navs, strict=True))
        assert abs(original.total_fees - scaled.total_fees) < D("1e-45")
    assert nav.SYMBOLS == ("SPY", "QQQ", "IWM")


def test_hostile_decimal_context_cannot_change_precision_rounding_or_results():
    original = replay()
    targets = {DATES[0]: allocation(), DATES[3]: allocation()}
    with localcontext() as context:
        context.prec, context.rounding = 6, ROUND_DOWN
        assert replay(targets=targets) == original
        assert context.prec == 6 and context.rounding == ROUND_DOWN


@pytest.mark.parametrize("case,code", [
    ("empty", "calendar_invalid"),
    ("duplicate_date", "calendar_invalid"),
    ("month_gap", "calendar_month_gap"),
    ("extra_boundary", "month_boundary_schedule_mismatch"),
    ("wrong_start", "month_boundary_schedule_mismatch"),
    ("duplicate_boundary", "month_boundary_schedule_mismatch"),
])
def test_calendar_contract_not_inferred_from_observed_source(case, code):
    dates, bounds = DATES, BOUNDS
    if case == "empty":
        dates = ()
    elif case == "duplicate_date":
        dates = (DATES[0], *DATES)
    elif case == "month_gap":
        dates = (date(2024, 1, 2), date(2024, 3, 1))
        bounds = (monthly.MonthlyBoundary(dates[0], dates[0]),
                  monthly.MonthlyBoundary(dates[1], dates[1]))
    elif case == "extra_boundary":
        bounds = (*bounds, monthly.MonthlyBoundary(date(2024, 3, 1), date(2024, 3, 28)))
    elif case == "wrong_start":
        bounds = (monthly.MonthlyBoundary(DATES[1], DATES[2]), BOUNDS[1])
    else:
        bounds = (BOUNDS[0], *BOUNDS)
    with pytest.raises(nav.ThreeAssetNavError, match=code):
        replay(dates=dates, bounds=bounds)


@pytest.mark.parametrize("case", ["missing_flat_day", "duplicate_day", "extra_month", "order"])
def test_every_mandatory_daily_mark_even_cash_only_is_required(case):
    records = days()
    if case == "missing_flat_day":
        records = (*records[:4], records[5])
    elif case == "duplicate_day":
        records = (*records[:2], records[1], *records[2:])
    elif case == "extra_month":
        records = (*records, nav.ThreeAssetDay(date(2024, 3, 1), (D(100),) * 3, (D(100),) * 3))
    else:
        records = tuple(reversed(records))
    with pytest.raises(nav.ThreeAssetNavError, match="daily_mark_schedule_mismatch"):
        replay(records, {DATES[0]: allocation((D(0),) * 3),
                         DATES[3]: allocation((D(0),) * 3)})


@pytest.mark.parametrize("case,code", [
    ("duplicate", "target_date_duplicate"),
    ("missing", "target_entries_missing_or_extra"),
    ("extra", "target_entries_missing_or_extra"),
    ("daily_repeat", "target_entries_missing_or_extra"),
])
def test_target_keys_are_exact_month_entries_no_silent_carry_or_duplicates(case, code):
    pairs = [(DATES[0], allocation()), (DATES[3], allocation())]
    if case == "duplicate":
        pairs.append(pairs[0])
    elif case == "missing":
        pairs.pop()
    elif case == "extra":
        pairs.append((date(2024, 3, 1), allocation()))
    else:
        pairs.append((DATES[1], allocation()))
    with pytest.raises(nav.ThreeAssetNavError, match=code):
        replay(targets=pairs)


@pytest.mark.parametrize("cost", [D(-1), 5.0])
def test_bad_cost_is_categorical(cost):
    with pytest.raises(nav.ThreeAssetNavError, match="cost_bps_invalid"):
        replay(cost=cost)


def test_wrong_instrument_order_cannot_route_legacy_symbols():
    with pytest.raises(nav.ThreeAssetNavError, match="instrument_order_invalid"):
        replay(order=nav.SYMBOLS)
    pairs = [(DATES[3], allocation()), (DATES[0], allocation())]
    assert replay(targets=pairs) == replay()


def test_december_january_and_leap_month_boundaries_preserve_cash():
    dates = (date(2023, 12, 1), date(2023, 12, 29), date(2024, 1, 2),
             date(2024, 1, 31), date(2024, 2, 1), date(2024, 2, 29))
    bounds = tuple(monthly.MonthlyBoundary(a, b) for a, b in zip(dates[::2], dates[1::2],
                                                               strict=True))
    records = tuple(nav.ThreeAssetDay(day, (D(100),) * 3, (D(100),) * 3) for day in dates)
    result = replay(records, {day: allocation() for day in dates[::2]}, dates, bounds)
    assert len(result.daily) == 6 and all(result.daily[i].flat for i in (1, 3, 5))
    assert result.daily[1].nav > result.daily[3].nav > result.daily[5].nav


def test_single_session_months_sum_entry_and_exit_fees_without_reset():
    dates = (date(2024, 1, 2), date(2024, 2, 1))
    bounds = tuple(monthly.MonthlyBoundary(day, day) for day in dates)
    records = tuple(nav.ThreeAssetDay(day, (D(100),) * 3, (D(100),) * 3) for day in dates)
    result = replay(records, {day: allocation() for day in dates}, dates, bounds)
    assert all(day.flat for day in result.daily)
    assert result.daily[0].fees > 0 and result.daily[1].fees > 0
    assert result.daily[1].nav < result.daily[0].nav < 1
    assert result.daily[1].fees < result.daily[0].fees


def test_source_io_isolation_inputs_unchanged_and_numeric_repr_hidden(monkeypatch):
    records, targets = days(), {DATES[0]: allocation(), DATES[3]: allocation()}
    original_targets = dict(targets)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("unexpected IO")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    result = replay(records, targets)
    assert replay(records, targets) == result
    assert targets == original_targets and records == days()
    assert repr(result) == "ThreeAssetReplay()"


def test_nonfinite_required_mark_is_revalidated_without_raw_error_values():
    records = list(days())
    poisoned = replace(records[1])
    object.__setattr__(poisoned, "adj_close3", (D("NaN"), D(100), D(100)))
    records[1] = poisoned
    with pytest.raises(nav.ThreeAssetNavError, match="prices_invalid") as caught:
        replay(tuple(records))
    assert str(caught.value) == "prices_invalid"
