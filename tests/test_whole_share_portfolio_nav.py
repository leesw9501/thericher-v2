from __future__ import annotations

import builtins
import copy
import os
import socket
import subprocess
import urllib.request
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta
from decimal import Context, Decimal, localcontext
from fractions import Fraction
from pathlib import Path

import pytest

from thericher_v2.research import whole_share_portfolio_nav as nav

D = Decimal
F = Fraction
ZERO = F(0)
START = date(2026, 1, 1)


def prices(spy="100", tlt="100", gld="100"):
    return tuple(map(D, (spy, tlt, gld)))


def weights(spy="0", tlt="0", gld="0"):
    return tuple(map(D, (spy, tlt, gld)))


def day(offset, opening=None, closing=None):
    return nav.WholeShareDay(
        START + timedelta(days=offset), opening or prices(), closing or prices()
    )


def conservation(before, quote, trade, bps):
    if trade.status == "no_intent":
        assert trade.state is before
        assert trade.fees == trade.traded_notional == 0
        assert trade.sold3 == trade.bought3 == (0, 0, 0)
        return
    after = trade.state
    sales = sum((q * F(p) for q, p in zip(trade.sold3, quote, strict=True)), ZERO)
    buys = sum((q * F(p) for q, p in zip(trade.bought3, quote, strict=True)), ZERO)
    fees = F(bps) / 10000 * (sales + buys)
    assert trade.traded_notional == sales + buys
    assert trade.fees == fees
    assert after.gross_cash == before.gross_cash + sales - buys
    assert after.analytical_cash == before.analytical_cash + sales - buys - fees
    assert after.fees_paid == before.fees_paid + fees
    assert after.basis_usd == before.basis_usd == 100000
    assert after.allocated_usd == before.allocated_usd == 10000
    assert all(type(q) is int and q >= 0 for q in after.quantities3)
    assert sum(after.entry_costs3, ZERO) <= after.allocated_usd
    assert after.analytical_cash >= 0
    before_mark = nav.mark_close(before, quote)
    after_mark = nav.mark_close(after, quote)
    assert after_mark.gross_nav == before_mark.gross_nav
    assert after_mark.net_nav == before_mark.net_nav - fees
    released = sum(
        (c * q / h if q else ZERO)
        for c, q, h in zip(before.entry_costs3, trade.sold3, before.quantities3, strict=True)
    )
    assert sum(after.entry_costs3, ZERO) == sum(before.entry_costs3, ZERO) - released + buys
    assert after.gross_realized_pnl - before.gross_realized_pnl == sales - released


def test_nominal_initial_state_and_mark_are_exact_and_immutable():
    state = nav.WholeShareState()
    assert nav.SYMBOLS == ("SPY", "TLT", "GLD")
    assert state.gross_cash == state.analytical_cash == state.allocated_usd == 10000
    assert state.basis_usd == 100000 and state.fees_paid == 0
    assert state.quantities3 == (0, 0, 0) and state.entry_costs3 == (ZERO, ZERO, ZERO)
    marked = nav.mark_close(state, prices())
    assert marked.state is state and marked.gross_nav == marked.net_nav == 10000
    with pytest.raises(FrozenInstanceError):
        state.gross_cash = ZERO


@pytest.mark.parametrize("price,quantity", [("99.99", 30), ("100", 30), ("100.01", 29)])
def test_floor_is_exact_not_nearest_rounding_or_fractional_rescaling(price, quantity):
    quote, target = prices(price), weights(".3")
    initial = nav.WholeShareState()
    trade = nav.rebalance_open(initial, quote, target, D(0))
    exact = F(3, 10) * initial.gross_cash / F(D(price))
    assert trade.target_quantities3 == (quantity, 0, 0)
    assert trade.state.quantities3 == (exact.numerator // exact.denominator, 0, 0)
    assert F(quantity) <= exact < quantity + 1
    conservation(initial, quote, trade, D(0))


@pytest.mark.parametrize("cost", ["0", "2.5", "5", "10"])
def test_gross_targets_and_unrounded_analytical_fee_cash_are_separate(cost):
    initial, quote = nav.WholeShareState(), prices("123.45", "200", "70.01")
    target = weights(".3", ".2", ".1")
    trade = nav.rebalance_open(initial, quote, target, D(cost))
    oracle = tuple((F(w) * F(10000)) // F(p) for w, p in zip(target, quote, strict=True))
    assert trade.target_quantities3 == trade.state.quantities3 == oracle == (24, 10, 14)
    assert trade.status == "executed" and trade.reason is nav.WholeShareTradeReason.EXECUTED
    notional = 24 * F(D("123.45")) + 10 * 200 + 14 * F(D("70.01"))
    assert trade.state.gross_cash == F(10000) - notional
    assert trade.state.analytical_cash == F(10000) - notional * (1 + F(D(cost)) / 10000)
    assert trade.state.entry_costs3 == (24 * F(D("123.45")), F(2000), 14 * F(D("70.01")))
    conservation(initial, quote, trade, D(cost))


@pytest.mark.parametrize("cost", ["2.5", "5", "10"])
def test_fee_unaffordable_full_bank_rejects_without_clipping_to_ninety_nine(cost):
    initial = nav.WholeShareState()
    trade = nav.rebalance_open(initial, prices(), weights("1"), D(cost))
    assert trade.target_quantities3 == (100, 0, 0)
    assert trade.reason is nav.WholeShareTradeReason.ANALYTICAL_CASH_NEGATIVE
    conservation(initial, prices(), trade, D(cost))
    zero_cost = nav.rebalance_open(initial, prices(), weights("1"), D(0))
    assert zero_cost.state.quantities3 == (100, 0, 0) and zero_cost.state.gross_cash == 0


def test_fee_affordability_uses_accumulated_fees_not_only_this_batch():
    state = nav.WholeShareState(gross_cash=F(10000), fees_paid=F(50))
    trade = nav.rebalance_open(state, prices(), weights(".999"), D(0))
    assert trade.target_quantities3 == (99, 0, 0) and trade.status == "executed"
    assert trade.state.gross_cash == 100 and trade.state.analytical_cash == 50
    rejected = nav.rebalance_open(state, prices(), weights("1"), D(0))
    assert rejected.reason is nav.WholeShareTradeReason.ANALYTICAL_CASH_NEGATIVE
    conservation(state, prices(), rejected, D(0))


@pytest.mark.parametrize("incumbent", [0, 1])
def test_all_sells_fund_buys_and_release_bank_before_any_symbol_buy(incumbent):
    initial = nav.WholeShareState()
    entry_weights = weights(".8") if incumbent == 0 else weights("0", ".8")
    entry = nav.rebalance_open(initial, prices(), entry_weights, D(5))
    target = weights(".1", ".8") if incumbent == 0 else weights(".8", ".1")
    trade = nav.rebalance_open(entry.state, prices(), target, D(5))
    assert trade.status == "executed"
    assert trade.state.quantities3 == ((10, 80, 0) if incumbent == 0 else (80, 10, 0))
    assert trade.sold3 == ((70, 0, 0) if incumbent == 0 else (0, 70, 0))
    assert trade.bought3 == ((0, 80, 0) if incumbent == 0 else (80, 0, 0))
    assert trade.state.gross_cash == 1000 and sum(trade.state.entry_costs3, ZERO) == 9000
    assert trade.traded_notional == 15000 and trade.fees == F(15, 2)
    assert trade.state.fees_paid == F(23, 2)
    conservation(entry.state, prices(), trade, D(5))


def test_fee_rejection_is_atomic_even_when_a_sale_would_have_succeeded():
    entry = nav.rebalance_open(nav.WholeShareState(), prices(), weights(".5"), D(0))
    trade = nav.rebalance_open(entry.state, prices(), weights("0", "1"), D(5))
    assert trade.reason is nav.WholeShareTradeReason.ANALYTICAL_CASH_NEGATIVE
    assert trade.target_quantities3 == (0, 100, 0)
    conservation(entry.state, prices(), trade, D(5))
    assert entry.state.quantities3 == (50, 0, 0) and entry.state.gross_cash == 5000


def test_bank_rejection_preserves_unsold_incumbent_and_charges_no_fees():
    entry = nav.rebalance_open(nav.WholeShareState(), prices(), weights(".5"), D(0))
    quote = prices("200")
    trade = nav.rebalance_open(entry.state, quote, weights("0", "1"), D(5))
    assert trade.reason is nav.WholeShareTradeReason.BANK_EXCEEDED
    assert trade.target_quantities3 == (0, 150, 0)
    conservation(entry.state, quote, trade, D(5))
    assert entry.state.entry_costs3 == (F(5000), ZERO, ZERO)


def test_gain_is_not_a_new_bank_and_repeated_rejection_is_idempotent():
    entry = nav.rebalance_open(nav.WholeShareState(), prices(), weights(".5"), D(5))
    exit_trade = nav.liquidate_close(entry.state, prices("200"), D(5))
    state = exit_trade.state
    assert state.gross_cash == 15000 and state.analytical_cash == F(29985, 2)
    assert state.gross_realized_pnl == 5000
    assert state.basis_usd == 100000 and state.allocated_usd == 10000
    for _ in range(3):
        rejected = nav.rebalance_open(state, prices(), weights("1"), D(0))
        assert rejected.reason is nav.WholeShareTradeReason.BANK_EXCEEDED
        assert rejected.target_quantities3 == (150, 0, 0)
        conservation(state, prices(), rejected, D(0))


def test_average_cost_combines_entries_and_partial_sale_releases_proportionally():
    first = nav.rebalance_open(nav.WholeShareState(), prices(), weights(".03"), D(5))
    second = nav.rebalance_open(first.state, prices("110"), weights(".055"), D(5))
    assert second.state.quantities3 == (5, 0, 0)
    assert second.state.entry_costs3 == (F(520), ZERO, ZERO)
    assert second.state.gross_realized_pnl == 0
    third = nav.rebalance_open(second.state, prices("111"), weights(".04"), D(5))
    assert third.sold3 == (2, 0, 0) and third.state.quantities3 == (3, 0, 0)
    assert third.state.entry_costs3 == (F(312), ZERO, ZERO)
    assert third.state.gross_realized_pnl == 222 - 208 == 14
    conservation(second.state, prices("111"), third, D(5))


def test_average_cost_does_not_round_a_nonterminating_rational_release():
    state = nav.WholeShareState(
        gross_cash=F(9800), quantities3=(2, 0, 0), entry_costs3=(F(200), ZERO, ZERO)
    )
    bought = nav.rebalance_open(state, prices("100.01"), weights(".031"), D(0))
    assert bought.state.quantities3 == (3, 0, 0)
    assert bought.state.entry_costs3[0] == F(30001, 100)
    sold = nav.rebalance_open(bought.state, prices("100.02"), weights(".021"), D(0))
    assert sold.state.quantities3 == (2, 0, 0)
    assert sold.state.entry_costs3[0] == F(30001, 150)
    conservation(bought.state, prices("100.02"), sold, D(0))


def test_price_marks_change_nav_not_cash_quantity_cost_or_basis():
    state = nav.rebalance_open(nav.WholeShareState(), prices(), weights(".5"), D(5)).state
    before = copy.deepcopy(state)
    high = nav.mark_close(state, prices("150"))
    low = nav.mark_close(state, prices("50"))
    assert high.state is low.state is state and state == before
    assert high.gross_nav == 12500 and low.gross_nav == 7500
    assert high.net_nav == F(24995, 2) and low.net_nav == F(14995, 2)


@pytest.mark.parametrize("cost", ["0", "2.5", "5", "10"])
def test_cash_target_liquidates_existing_inventory_but_flat_cash_is_fee_free(cost):
    initial = nav.WholeShareState()
    flat = nav.rebalance_open(initial, prices(), weights(), D(cost))
    assert flat.reason is nav.WholeShareTradeReason.NO_TARGET_DELTA
    conservation(initial, prices(), flat, D(cost))
    entry = nav.rebalance_open(initial, prices(), weights(".5"), D(cost))
    sale = nav.rebalance_open(entry.state, prices(), weights(), D(cost))
    assert sale.state.quantities3 == (0, 0, 0) and sale.traded_notional == 5000
    assert sale.fees == F(D(cost)) / 2
    conservation(entry.state, prices(), sale, D(cost))
    repeated = nav.liquidate_close(sale.state, prices(), D(cost))
    assert repeated.state is sale.state and repeated.fees == repeated.traded_notional == 0


def test_unaffordable_liquidation_is_not_falsely_reported_as_flat():
    state = nav.rebalance_open(nav.WholeShareState(), prices(), weights("1"), D(0)).state
    trade = nav.liquidate_close(state, prices(), D(10001))
    assert trade.reason is nav.WholeShareTradeReason.ANALYTICAL_CASH_NEGATIVE
    conservation(state, prices(), trade, D(10001))
    assert trade.state.quantities3 == (100, 0, 0)


def test_episode_charges_entry_and_final_close_fees_and_marks_gross_and_net():
    record = day(0, closing=prices("110"))
    result = nav.replay(
        [record],
        {record.date: weights(".5")},
        D(5),
        initial_state=nav.WholeShareState(),
        liquidate_last_close=True,
    )
    assert result.initial_mark.gross_nav == result.initial_mark.net_nav == 10000
    assert result.final_gross_nav == 10500 and result.final_net_nav == F(41979, 4)
    assert result.daily[0].nav == result.final_net_nav
    assert result.total_fees == F(21, 4) and result.total_traded_notional == 10500
    assert result.final_state.quantities3 == (0, 0, 0)
    assert result.final_state.entry_costs3 == (ZERO, ZERO, ZERO)
    assert result.final_state.gross_realized_pnl == 500


def test_twenty_one_supplied_sessions_mark_carry_and_explicitly_exit_last_close():
    days = tuple(day(index, closing=prices(str(100 + index))) for index in range(21))
    actions = {days[0].date: weights(".5")}
    initial = nav.WholeShareState()
    carried = nav.replay(days, actions, D(5), initial_state=initial, liquidate_last_close=False)
    closed = nav.replay(days, actions, D(5), initial_state=initial, liquidate_last_close=True)
    assert len(closed.daily) == 21 and closed.daily[:-1] == carried.daily[:-1]
    assert all(d.open_trade is None for d in closed.daily[1:])
    assert all(d.close_trade is None for d in closed.daily[:-1])
    assert carried.final_state.quantities3 == (50, 0, 0)
    assert closed.final_state.quantities3 == (0, 0, 0)
    assert carried.final_gross_nav == closed.final_gross_nav == 11000
    assert closed.total_fees == F(11, 2) and closed.final_net_nav == F(21989, 2)
    assert initial == nav.WholeShareState()


def test_continuous_replay_partition_preserves_profit_fees_bank_and_all_state():
    days = (
        day(0, closing=prices("110")),
        day(1, opening=prices("110"), closing=prices("120")),
        day(2, opening=prices("120"), closing=prices("130")),
        day(3, opening=prices("130"), closing=prices("140")),
    )
    actions = {days[0].date: weights(".5"), days[2].date: weights(".3", ".2")}
    initial = nav.WholeShareState()
    whole = nav.replay(days, actions, D(5), initial_state=initial, liquidate_last_close=True)
    first = nav.replay(
        days[:2],
        {days[0].date: actions[days[0].date]},
        D(5),
        initial_state=initial,
        liquidate_last_close=False,
    )
    second = nav.replay(
        days[2:],
        {days[2].date: actions[days[2].date]},
        D(5),
        initial_state=first.final_state,
        liquidate_last_close=True,
    )
    assert whole.daily == first.daily + second.daily
    assert whole.final_state == second.final_state
    assert whole.total_fees == first.total_fees + second.total_fees
    assert second.final_state.fees_paid == whole.total_fees
    assert second.final_state.basis_usd == 100000 and second.final_state.allocated_usd == 10000
    assert second.total_fees != second.final_state.fees_paid


def test_replay_does_not_reset_flat_profit_to_nominal_bank():
    state = nav.WholeShareState(gross_cash=F(10500), fees_paid=F(5))
    record = day(0)
    result = nav.replay(
        [record],
        {record.date: weights("1")},
        D(5),
        initial_state=state,
        liquidate_last_close=True,
    )
    assert result.daily[0].open_trade.reason is nav.WholeShareTradeReason.BANK_EXCEEDED
    assert result.final_state is state
    assert result.final_gross_nav == 10500 and result.final_net_nav == 10495
    assert result.total_fees == 0 and state.allocated_usd == 10000


def test_cash_action_utility_is_not_zero_for_a_nonflat_initial_episode():
    state = nav.WholeShareState(
        gross_cash=F(5000),
        fees_paid=F(5),
        quantities3=(50, 0, 0),
        entry_costs3=(F(5000), ZERO, ZERO),
    )
    record = day(0)
    result = nav.replay(
        [record],
        {record.date: weights()},
        D(5),
        initial_state=state,
        liquidate_last_close=True,
    )
    assert result.final_state.quantities3 == (0, 0, 0)
    assert result.final_net_nav - result.initial_mark.net_nav == -F(5, 2)
    assert result.total_fees == F(5, 2)


def test_flat_cash_episode_is_zero_growth_with_no_fees_or_implicit_targets():
    records = tuple(day(index) for index in range(21))
    state = nav.WholeShareState()
    result = nav.replay(
        records,
        {records[0].date: (ZERO, ZERO, ZERO)},
        D(10),
        initial_state=state,
        liquidate_last_close=True,
    )
    assert all(record.nav == result.initial_mark.net_nav == 10000 for record in result.daily)
    assert result.final_state is state
    assert result.total_fees == result.total_traded_notional == 0


def test_zero_wealth_cannot_manufacture_a_new_nominal_bank_or_inventory():
    state = nav.WholeShareState(gross_cash=ZERO)
    trade = nav.rebalance_open(state, prices(), (F(1, 3),) * 3, D(5))
    assert trade.reason is nav.WholeShareTradeReason.NO_TARGET_DELTA
    assert trade.target_quantities3 == (0, 0, 0) and trade.state is state
    mark = nav.mark_close(state, prices())
    assert mark.gross_nav == mark.net_nav == 0
    assert state.basis_usd == 100000 and state.allocated_usd == 10000


def test_future_close_and_open_perturbations_do_not_rewrite_prior_fills_or_state():
    days = (day(0), day(1), day(2))
    actions = {days[0].date: weights(".5"), days[2].date: weights(".2", ".3")}
    original = copy.deepcopy((days, actions))
    baseline = nav.replay(
        days,
        actions,
        D(5),
        initial_state=nav.WholeShareState(),
        liquidate_last_close=True,
    )
    same_day_close = (replace(days[0], close3=prices("199.99")), *days[1:])
    changed = nav.replay(
        same_day_close,
        actions,
        D(5),
        initial_state=nav.WholeShareState(),
        liquidate_last_close=True,
    )
    assert changed.daily[0].open_trade == baseline.daily[0].open_trade
    assert changed.daily[1:] == baseline.daily[1:]
    future = (*days[:2], replace(days[2], open3=prices("80"), close3=prices("400")))
    future_result = nav.replay(
        future,
        actions,
        D(5),
        initial_state=nav.WholeShareState(),
        liquidate_last_close=True,
    )
    assert future_result.daily[:2] == baseline.daily[:2]
    assert (days, actions) == original


def test_hostile_decimal_context_cannot_change_exact_floors_fees_or_cent_lattice():
    quote, target, cost = prices("123.45"), weights(".3", ".2", ".1"), D("2.5")
    baseline = nav.rebalance_open(nav.WholeShareState(), quote, target, cost)
    context = Context(prec=1, Emin=-1, Emax=1, clamp=1)
    for signal in context.traps:
        context.traps[signal] = True
    with localcontext(context):
        assert nav.rebalance_open(nav.WholeShareState(), quote, target, cost) == baseline
        with pytest.raises(nav.WholeShareNavError, match="^weights_invalid$"):
            nav.rebalance_open(nav.WholeShareState(), quote, (D(1), D("1e-50"), D(0)), cost)


def test_exact_fraction_thirds_and_mixed_decimal_weights_keep_their_exact_geometry():
    initial = nav.WholeShareState()
    thirds = (F(1, 3), F(1, 3), F(1, 3))
    trade = nav.rebalance_open(initial, prices(), thirds, D(5))
    assert trade.target_quantities3 == trade.state.quantities3 == (33, 33, 33)
    assert trade.state.gross_cash == 100 and trade.state.analytical_cash == F(1901, 20)
    conservation(initial, prices(), trade, D(5))
    mixed = (F(1, 3), D(".2"), F(1, 10))
    mixed_trade = nav.rebalance_open(initial, prices(), mixed, D(5))
    assert mixed_trade.target_quantities3 == (33, 20, 10)
    assert mixed_trade.state.quantities3 == mixed_trade.target_quantities3
    record = day(0)
    trace = nav.replay(
        [record],
        {record.date: thirds},
        D(5),
        initial_state=initial,
        liquidate_last_close=True,
    )
    assert trace.daily[0].open_trade.target_quantities3 == (33, 33, 33)
    assert trace.daily[0].nav == trace.final_net_nav == F(99901, 10)


@pytest.mark.parametrize("bad", [True, False, 0, 1, 0.1, "0.1", D("NaN"), D("Infinity")])
def test_mixed_fraction_weights_reject_bool_float_and_nonfinite_entries(bad):
    with pytest.raises(nav.WholeShareNavError, match="^weights_invalid$"):
        nav.rebalance_open(nav.WholeShareState(), prices(), (F(1, 3), bad, F(1, 3)), D(5))


def test_fraction_weight_support_does_not_widen_price_or_fee_types():
    with pytest.raises(nav.WholeShareNavError, match="^prices_invalid$"):
        nav.mark_close(nav.WholeShareState(), (F(100), D(100), D(100)))
    with pytest.raises(nav.WholeShareNavError, match="^cost_bps_invalid$"):
        nav.rebalance_open(nav.WholeShareState(), prices(), (F(1, 3), ZERO, ZERO), F(5))


@pytest.mark.parametrize("bad", [None, True, 1, 1.0, "100", D("NaN"), D("sNaN"), D("Infinity")])
def test_invalid_decimal_types_nonfinite_prices_weights_and_fees_are_categorical(bad):
    initial = nav.WholeShareState()
    with pytest.raises(nav.WholeShareNavError, match="^prices_invalid$"):
        nav.mark_close(initial, (bad, D(100), D(100)))
    with pytest.raises(nav.WholeShareNavError, match="^weights_invalid$"):
        nav.rebalance_open(initial, prices(), (bad, D(0), D(0)), D(5))
    with pytest.raises(nav.WholeShareNavError, match="^cost_bps_invalid$"):
        nav.liquidate_close(initial, prices(), bad)


@pytest.mark.parametrize("bad", ["0", "-1", "1.001", "0.0001"])
def test_nonpositive_and_noncent_prices_are_rejected_without_quantizing(bad):
    with pytest.raises(nav.WholeShareNavError, match="^prices_invalid$"):
        nav.mark_close(nav.WholeShareState(), prices(bad))


@pytest.mark.parametrize(
    "bad",
    [
        (D(-1), D(0), D(0)),
        (D(".6"), D(".5"), D(0)),
        (F(-1), ZERO, ZERO),
        (F(2, 3), F(2, 3), ZERO),
    ],
)
def test_negative_or_excess_weights_are_not_renormalized(bad):
    with pytest.raises(nav.WholeShareNavError, match="^weights_invalid$"):
        nav.rebalance_open(nav.WholeShareState(), prices(), bad, D(0))


@pytest.mark.parametrize("bad", [(), (D(1),), (D(1),) * 4, [D(1)] * 3, None])
def test_invalid_vector_shapes_fail_without_partial_processing(bad):
    with pytest.raises(nav.WholeShareNavError, match="^prices_invalid$"):
        nav.mark_close(nav.WholeShareState(), bad)
    with pytest.raises(nav.WholeShareNavError, match="^weights_invalid$"):
        nav.rebalance_open(nav.WholeShareState(), prices(), bad, D(0))


@pytest.mark.parametrize(
    "fields,category",
    [
        ({"gross_cash": 10000}, "state_amounts_invalid"),
        ({"gross_cash": F(-1)}, "state_amounts_invalid"),
        ({"fees_paid": F(10001)}, "state_cash_negative"),
        ({"allocated_usd": F(10001)}, "state_bank_invalid"),
        ({"basis_usd": ZERO}, "state_bank_invalid"),
        ({"quantities3": (True, 0, 0)}, "state_quantities_invalid"),
        ({"quantities3": (F(1, 2), 0, 0)}, "state_quantities_invalid"),
        ({"quantities3": (-1, 0, 0)}, "state_quantities_invalid"),
        ({"quantities3": (1, 0, 0)}, "state_entry_costs_invalid"),
        ({"entry_costs3": (F(1), ZERO, ZERO)}, "state_entry_costs_invalid"),
        ({"entry_costs3": (0, 0, 0)}, "state_entry_costs_invalid"),
        ({"quantities3": (1, 0, 0), "entry_costs3": (F(10001), ZERO, ZERO)}, "state_bank_exceeded"),
    ],
)
def test_invalid_state_does_not_adopt_fractional_inventory_or_borrow(fields, category):
    with pytest.raises(nav.WholeShareNavError, match="^" + category + "$"):
        nav.WholeShareState(**fields)


@pytest.mark.parametrize(
    "days,targets,category",
    [
        ([], {}, "days_invalid"),
        ([None], {}, "day_invalid"),
        ([day(0), day(0)], {}, "day_order_invalid"),
        ([day(1), day(0)], {}, "day_order_invalid"),
        ([day(0)], None, "target_dates_invalid"),
        ([day(0)], {START + timedelta(days=1): weights()}, "target_dates_invalid"),
        ([day(0)], {datetime(2026, 1, 1): weights()}, "target_dates_invalid"),
        ([day(0)], {START: (D(1), D(1), D(1))}, "weights_invalid"),
    ],
)
def test_replay_rejects_duplicate_unsorted_or_unbound_action_dates(days, targets, category):
    with pytest.raises(nav.WholeShareNavError, match="^" + category + "$"):
        nav.replay(
            days,
            targets,
            D(5),
            initial_state=nav.WholeShareState(),
            liquidate_last_close=True,
        )


def test_terminal_choice_is_explicit_boolean_and_invalid_date_is_not_coerced():
    with pytest.raises(nav.WholeShareNavError, match="^liquidation_choice_invalid$"):
        nav.replay([day(0)], {}, D(5), initial_state=nav.WholeShareState(), liquidate_last_close=1)
    with pytest.raises(nav.WholeShareNavError, match="^date_invalid$"):
        nav.WholeShareDay(datetime(2026, 1, 1), prices(), prices())
    with pytest.raises(nav.WholeShareNavError, match="^cost_bps_invalid$"):
        nav.rebalance_open(nav.WholeShareState(), prices(), weights(), D(-1))


def test_numeric_reprs_are_hidden_and_kernel_has_no_external_effects(monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("pure analytical kernel attempted an external effect")

    record = day(0, closing=prices("123.45"))
    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", deny)
        patch.setattr(Path, "read_bytes", deny)
        patch.setattr(Path, "read_text", deny)
        patch.setattr(Path, "write_bytes", deny)
        patch.setattr(Path, "write_text", deny)
        patch.setattr(os, "getenv", deny)
        patch.setattr(socket, "create_connection", deny)
        patch.setattr(urllib.request, "urlopen", deny)
        patch.setattr(subprocess, "run", deny)
        result = nav.replay(
            [record],
            {record.date: weights(".5")},
            D(5),
            initial_state=nav.WholeShareState(),
            liquidate_last_close=True,
        )
    values = (
        result,
        result.final_state,
        result.daily[0],
        result.daily[0].mark,
        result.daily[0].open_trade,
        result.daily[0].close_trade,
    )
    for value in values:
        assert "123.45" not in repr(value) and "100000" not in repr(value)
        assert "Fraction(" not in repr(value) and "Decimal(" not in repr(value)
