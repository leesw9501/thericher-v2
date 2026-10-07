from __future__ import annotations

import builtins
import os
from dataclasses import FrozenInstanceError
from datetime import date, datetime
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, Context, Decimal, Inexact, localcontext
from itertools import permutations
from pathlib import Path

import pytest

from thericher_v2.research import three_asset_nav as nav

D = Decimal
ZERO = D(0)
ONE = D(1)
TOL = D("1e-45")


@pytest.fixture(autouse=True)
def decimal50():
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        yield


def prices(*values):
    return nav.ThreeAssetPrices(tuple(map(D, values or ("1", "1", "1"))))


def weights(*values):
    return dict(zip(nav.SYMBOLS, map(D, values), strict=True))


def assert_close(actual, expected, scale=ONE):
    assert abs(actual - expected) <= TOL * scale


def assert_cashflow(before, marks, trade, cost):
    old = tuple(q * p for q, p in zip(before.quantities, marks.values, strict=True))
    new = tuple(q * p for q, p in zip(trade.state.quantities, marks.values, strict=True))
    delta = tuple(a - b for a, b in zip(new, old, strict=True))
    assert trade.traded_notionals == delta
    assert trade.turnover == sum(map(abs, delta), ZERO)
    assert trade.fees == cost / 10000 * trade.turnover
    assert trade.post_fee_nav == trade.state.cash + sum(new, ZERO)
    assert_close(trade.post_fee_nav + trade.fees, trade.pre_fee_nav, trade.pre_fee_nav)
    assert_close(
        trade.state.cash,
        before.cash - sum(delta, ZERO) - trade.fees,
        trade.pre_fee_nav,
    )


@pytest.mark.parametrize("cost", ("0", "2.5", "5", "10", "100"))
def test_all_buy_post_fee_targets_and_actual_notional_fees(cost):
    state, marks = nav.ThreeAssetState(ONE), prices("2", "4", "5")
    target, fee = weights(".2", ".3", ".4"), D(cost) / 10000
    trade = nav.rebalance_open(state, marks, target, D(cost))
    expected = ONE / (ONE + fee * D(".9"))
    assert_close(trade.post_fee_nav, expected)
    assert_close(trade.state.cash, D(".1") * expected)
    assert all(value > 0 for value in trade.traded_notionals)
    for quantity, price, weight in zip(
        trade.state.quantities, marks.values, target.values(), strict=True
    ):
        assert_close(quantity * price, weight * expected)
    assert_cashflow(state, marks, trade, D(cost))


@pytest.mark.parametrize("cost", ("0", "2.5", "5", "10", "100"))
def test_all_sell_charges_holdings_not_untraded_cash(cost):
    state = nav.ThreeAssetState(D(10), (D(2), D(3), D(4)))
    marks = prices("5", "6", "7")
    trade = nav.liquidate_close(state, marks, D(cost))
    invested = D(56)
    assert trade.turnover == invested
    assert trade.state.quantities == (ZERO, ZERO, ZERO)
    assert_close(trade.state.cash, D(66) - invested * D(cost) / 10000, D(66))
    assert trade.post_fee_nav == trade.state.cash
    assert all(value < 0 for value in trade.traded_notionals)
    assert_cashflow(state, marks, trade, D(cost))


@pytest.mark.parametrize("cost", ("0", "2.5", "5", "10", "100"))
def test_mixed_rebalance_funds_buys_from_simultaneous_sells(cost):
    state = nav.ThreeAssetState(ZERO, (D(".8"), D(".1"), D(".1")))
    marks, fee = prices(), D(cost) / 10000
    trade = nav.rebalance_open(state, marks, weights(".1", ".4", ".5"), D(cost))
    expected = (ONE - D(".6") * fee) / (ONE + D(".8") * fee)
    assert_close(trade.post_fee_nav, expected)
    assert trade.state.cash == ZERO
    assert trade.traded_notionals[0] < 0 < trade.traded_notionals[1]
    assert trade.traded_notionals[2] > state.cash
    assert_cashflow(state, marks, trade, D(cost))


@pytest.mark.parametrize("holding,weight", (("0", ".8"), (".3", ".8"), ("1", ".2"), (".3", "0")))
@pytest.mark.parametrize("cost", ("0", "2.5", "5", "10"))
def test_single_asset_matches_independent_scalar_cashflow(holding, weight, cost):
    stock, weight, fee = D(holding), D(weight), D(cost) / 10000
    state = nav.ThreeAssetState(ONE - stock, (stock / 2, ZERO, ZERO))
    marks = prices("2", "3", "5")
    trade = nav.rebalance_open(state, marks, weights(str(weight), "0", "0"), D(cost))
    sign = ONE if weight >= stock else -ONE
    expected = (ONE + fee * sign * stock) / (ONE + fee * sign * weight)
    assert_close(trade.post_fee_nav, expected)
    assert_close(trade.state.quantities[0] * 2, weight * expected)
    assert_cashflow(state, marks, trade, D(cost))


@pytest.mark.parametrize("order", tuple(permutations(nav.SYMBOLS)))
def test_mapping_order_never_changes_asset_assignment_or_funding(order):
    holdings = dict(zip(nav.SYMBOLS, map(D, ("2", "3", "4")), strict=True))
    quotes = dict(zip(nav.SYMBOLS, map(D, ("5", "7", "11")), strict=True))
    target = weights(".6", ".1", ".2")
    reference = nav.rebalance_open(
        nav.ThreeAssetState.from_mapping(D(13), holdings),
        nav.ThreeAssetPrices.from_mapping(quotes),
        target,
        D(5),
    )
    reordered = nav.rebalance_open(
        nav.ThreeAssetState.from_mapping(D(13), {key: holdings[key] for key in order}),
        nav.ThreeAssetPrices.from_mapping({key: quotes[key] for key in order}),
        {key: target[key] for key in order},
        D(5),
    )
    assert reordered == reference


def test_zero_cost_and_cash_residual_are_not_renormalized():
    trade = nav.rebalance_open(
        nav.ThreeAssetState(D(100)), prices(), weights(".1", ".2", ".3"), ZERO
    )
    assert trade.state == nav.ThreeAssetState(D(40), (D(10), D(20), D(30)))
    assert trade.post_fee_nav == D(100) and trade.fees == ZERO


@pytest.mark.parametrize("cost", ("0", "2.5", "5", "10"))
def test_exact_no_trade_and_all_cash_are_fee_free(cost):
    state = nav.ThreeAssetState(D(4), (D(2), D(3), D(1)))
    trade = nav.rebalance_open(state, prices(), weights(".2", ".3", ".1"), D(cost))
    assert trade.state == state and trade.turnover == trade.fees == ZERO
    empty = nav.ThreeAssetState(ONE)
    cash = nav.rebalance_open(empty, prices(), weights("0", "0", "0"), D(cost))
    assert cash.state == empty and cash.turnover == cash.fees == ZERO


def test_zero_wealth_cannot_manufacture_inventory():
    empty = nav.ThreeAssetState(ZERO)
    trade = nav.rebalance_open(empty, prices(), weights(".5", ".3", ".2"), D(100))
    assert trade.state == empty and trade.post_fee_nav == trade.fees == ZERO


def test_tiny_real_trade_is_not_dust_clipped():
    trade = nav.rebalance_open(
        nav.ThreeAssetState(ONE), prices(), weights("1e-42", "0", "0"), D(10)
    )
    assert trade.state.quantities[0] > 0 and trade.turnover > 0 and trade.fees > 0


def test_initial_entry_overnight_carry_close_marks_and_final_exit():
    initial = nav.ThreeAssetState(ONE)
    entry = nav.rebalance_open(initial, prices("2", "4", "5"), weights(".2", ".3", ".4"), D(5))
    quantities, cash = entry.state.quantities, entry.state.cash
    day_one = nav.mark_close(entry.state, prices("3", "4", "6"))
    next_open = nav.mark_close(day_one.state, prices("5", "3", "9"))
    day_two = nav.mark_close(next_open.state, prices("4", "2", "8"))
    assert day_one.state is next_open.state is day_two.state is entry.state
    assert day_two.state.quantities == quantities and day_two.state.cash == cash
    assert day_two.nav == cash + quantities[0] * 4 + quantities[1] * 2 + quantities[2] * 8
    final = nav.liquidate_close(day_two.state, prices("4", "2", "8"), D(5))
    assert final.state.quantities == (ZERO, ZERO, ZERO)
    assert_close(final.state.cash, day_two.nav - final.fees, day_two.nav)
    repeated = nav.liquidate_close(final.state, prices("4", "2", "8"), D(5))
    assert repeated.state == final.state and repeated.fees == repeated.turnover == ZERO
    assert initial == nav.ThreeAssetState(ONE)


def test_higher_cost_reduces_fixed_path_final_nav_without_changing_targets():
    finals = []
    for cost in map(D, ("0", "2.5", "5", "10")):
        trade = nav.rebalance_open(
            nav.ThreeAssetState(ONE), prices(), weights(".2", ".3", ".4"), cost
        )
        finals.append(nav.liquidate_close(trade.state, prices("2", "2", "2"), cost).post_fee_nav)
    assert all(a > b for a, b in zip(finals, finals[1:], strict=False))


@pytest.mark.parametrize(
    "bad", (None, True, 1, 1.0, "1", D("NaN"), D("sNaN"), D("Infinity"), D("-1"))
)
def test_invalid_cash_prices_quantities_weights_and_costs_are_not_repaired(bad):
    with pytest.raises(nav.ThreeAssetNavError):
        nav.ThreeAssetState(bad)
    with pytest.raises(nav.ThreeAssetNavError):
        nav.ThreeAssetState(ONE, (bad, ZERO, ZERO))
    with pytest.raises(nav.ThreeAssetNavError):
        nav.ThreeAssetPrices((bad, ONE, ONE))
    with pytest.raises(nav.ThreeAssetNavError):
        nav.rebalance_open(
            nav.ThreeAssetState(ONE), prices(), dict(SPY=bad, QQQ=ZERO, IWM=ZERO), ZERO
        )
    with pytest.raises(nav.ThreeAssetNavError):
        nav.liquidate_close(nav.ThreeAssetState(ONE), prices(), bad)


@pytest.mark.parametrize("bad", (None, (), (ONE,), (ONE, ONE), (ONE,) * 4, [ONE] * 3))
def test_invalid_vector_shapes_are_unavailable_not_partial_portfolios(bad):
    with pytest.raises(nav.ThreeAssetNavError):
        nav.ThreeAssetPrices(bad)
    with pytest.raises(nav.ThreeAssetNavError):
        nav.ThreeAssetState(ONE, bad)


@pytest.mark.parametrize(
    "bad",
    (
        None,
        {},
        {"SPY": ONE},
        {"SPY": ONE, "QQQ": ONE, "TLT": ONE},
        dict(SPY=ONE, QQQ=ONE, IWM=ONE, TLT=ONE),
    ),
)
def test_unknown_missing_or_extra_symbols_are_rejected(bad):
    with pytest.raises(nav.ThreeAssetNavError):
        nav.ThreeAssetPrices.from_mapping(bad)
    with pytest.raises(nav.ThreeAssetNavError):
        nav.ThreeAssetState.from_mapping(ONE, bad)
    with pytest.raises(nav.ThreeAssetNavError):
        nav.rebalance_open(nav.ThreeAssetState(ONE), prices(), bad, ZERO)


@pytest.mark.parametrize(
    "target",
    (
        (".5", ".5", ".1"),
        ("1", "1e-60", "0"),
        (".50000000000000000000000000000000000000000000000000000000000001", ".5", "0"),
    ),
)
def test_excess_weights_are_rejected_even_below_decimal50_roundoff(target):
    with pytest.raises(nav.ThreeAssetNavError, match="targets_exceed_one"):
        nav.rebalance_open(nav.ThreeAssetState(ONE), prices(), weights(*target), ZERO)


def test_zero_prices_and_cost_above_bound_are_invalid():
    with pytest.raises(nav.ThreeAssetNavError, match="prices_invalid"):
        prices("1", "0", "1")
    with pytest.raises(nav.ThreeAssetNavError, match="cost_bps_invalid"):
        nav.liquidate_close(nav.ThreeAssetState(ONE), prices(), D("100.0001"))


def test_calls_revalidate_state_and_price_fields_instead_of_trusting_type():
    state = nav.ThreeAssetState(ONE)
    object.__setattr__(state, "quantities", (D(-1), ZERO, ZERO))
    with pytest.raises(nav.ThreeAssetNavError, match="quantities_invalid"):
        nav.mark_close(state, prices())
    quote = prices()
    object.__setattr__(quote, "values", (ONE, D("NaN"), ONE))
    with pytest.raises(nav.ThreeAssetNavError, match="prices_invalid"):
        nav.mark_close(nav.ThreeAssetState(ONE), quote)
    with pytest.raises(nav.ThreeAssetNavError, match="state_invalid"):
        nav.mark_close(None, prices())


def test_immutability_repr_safety_and_no_io(monkeypatch):
    quantities = dict(SPY=D(2), QQQ=D(3), IWM=D(4))
    quotes = dict(SPY=D(5), QQQ=D(7), IWM=D(11))
    target = weights(".6", ".1", ".2")
    state = nav.ThreeAssetState.from_mapping(D(13), quantities)
    marks = nav.ThreeAssetPrices.from_mapping(quotes)
    before = (quantities.copy(), quotes.copy(), target.copy())

    def forbidden(*args, **kwargs):
        pytest.fail("ledger must not perform I/O or read environment")

    with monkeypatch.context() as guard:
        guard.setattr(builtins, "open", forbidden)
        guard.setattr(Path, "open", forbidden)
        guard.setattr(Path, "read_text", forbidden)
        guard.setattr(Path, "write_text", forbidden)
        guard.setattr(os, "getenv", forbidden)
        trade = nav.rebalance_open(state, marks, target, D(5))
        close = nav.mark_close(trade.state, marks)
        nav.liquidate_close(close.state, marks, D(5))
    assert before == (quantities, quotes, target)
    quantities["SPY"], quotes["SPY"] = D(999), D(999)
    assert state.quantities[0] == D(2) and marks.values[0] == D(5)
    for obj, field, value in (
        (state, "cash", ZERO),
        (marks, "values", (ONE,) * 3),
        (trade, "fees", ZERO),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(obj, field, value)
    assert repr(state) == "ThreeAssetState()"
    assert repr(marks) == "ThreeAssetPrices()"
    assert repr(trade) == "ThreeAssetTrade()" and repr(close) == "ThreeAssetMark()"


def test_decimal50_half_even_is_independent_of_caller_context():
    state, marks, target = (
        nav.ThreeAssetState(ONE),
        prices("3", "7", "11"),
        weights(".2", ".3", ".4"),
    )
    expected = nav.rebalance_open(state, marks, target, D(5))
    with localcontext() as context:
        context.prec, context.rounding = 6, ROUND_DOWN
        context.traps[Inexact] = True
        actual = nav.rebalance_open(state, marks, target, D(5))
        assert nav.mark_close(actual.state, marks) == nav.mark_close(expected.state, marks)
        assert context.prec == 6 and context.rounding == ROUND_DOWN and context.traps[Inexact]
    assert actual == expected


def days():
    return (
        nav.ThreeAssetDay(
            date(2026, 1, 2), prices("2", "4", "5").values, prices("3", "4", "6").values
        ),
        nav.ThreeAssetDay(
            date(2026, 1, 5), prices("5", "3", "9").values, prices("4", "2", "8").values
        ),
        nav.ThreeAssetDay(
            date(2026, 1, 6), prices("3", "5", "7").values, prices("5", "6", "9").values
        ),
    )


def test_replay_daily_marks_carry_and_final_exit_match_low_level_operations():
    records = days()
    target = nav.ThreeAssetTarget((D(".2"), D(".3"), D(".4")), D(".1"))
    result = nav.replay(records, {records[0].date: target}, D(5))
    entry = nav.rebalance_open(
        nav.ThreeAssetState(ONE),
        nav.ThreeAssetPrices(records[0].adj_open3),
        weights(".2", ".3", ".4"),
        D(5),
    )
    first = nav.mark_close(entry.state, nav.ThreeAssetPrices(records[0].adj_close3))
    second = nav.mark_close(entry.state, nav.ThreeAssetPrices(records[1].adj_close3))
    exit_trade = nav.liquidate_close(entry.state, nav.ThreeAssetPrices(records[2].adj_close3), D(5))
    assert result.navs == (first.nav, second.nav, exit_trade.post_fee_nav)
    assert tuple(day.fees for day in result.daily) == (entry.fees, ZERO, exit_trade.fees)
    assert tuple(day.traded_notional for day in result.daily) == (
        entry.turnover,
        ZERO,
        exit_trade.turnover,
    )
    assert tuple(day.cash for day in result.daily) == (
        entry.state.cash,
        entry.state.cash,
        exit_trade.state.cash,
    )
    assert tuple(day.flat for day in result.daily) == (False, False, True)
    assert result.final_state == exit_trade.state
    assert result.final_nav == result.final_state.cash
    assert result.total_fees == entry.fees + exit_trade.fees
    assert result.total_traded_notional == entry.turnover + exit_trade.turnover
    previous = ONE
    for day in result.daily:
        assert day.simple_return == day.nav / previous - 1
        assert day.log_return == (day.nav / previous).ln()
        previous = day.nav
    assert result.simple_returns == tuple(day.simple_return for day in result.daily)
    assert result.log_returns == tuple(day.log_return for day in result.daily)
    assert result.simple_returns != result.log_returns
    assert_close(sum(result.log_returns, ZERO), result.final_nav.ln())


@pytest.mark.parametrize("cost", ("0", "2.5", "5", "10"))
def test_one_day_replay_includes_initial_fee_and_final_exit_in_both_return_series(cost):
    record = nav.ThreeAssetDay(date(2026, 1, 2), (ONE,) * 3, (D(2),) * 3)
    target = nav.ThreeAssetTarget((ONE, ZERO, ZERO), ZERO)
    result = nav.replay((record,), {record.date: target}, D(cost))
    fee = D(cost) / 10000
    expected = 2 * (1 - fee) / (1 + fee)
    assert_close(result.final_nav, expected, expected)
    assert_close(result.total_fees, fee * 3 / (1 + fee))
    assert result.daily[0].simple_return == result.final_nav - 1
    assert result.daily[0].log_return == result.final_nav.ln()
    assert result.daily[0].flat and result.daily[0].cash == result.final_nav


def test_replay_applies_only_supplied_action_dates_and_includes_final_open_action():
    records = days()
    buy = nav.ThreeAssetTarget((D(".5"), D(".2"), D(".1")), D(".2"))
    switch = nav.ThreeAssetTarget((D(".1"), D(".2"), D(".6")), D(".1"))
    actions = {records[0].date: buy, records[-1].date: switch}
    result = nav.replay(records, actions, D(10))
    state = nav.ThreeAssetState(ONE)
    trades = []
    for record in records:
        if record.date in actions:
            target = actions[record.date]
            trade = nav.rebalance_open(
                state,
                nav.ThreeAssetPrices(record.adj_open3),
                dict(zip(nav.SYMBOLS, target.weights3, strict=True)),
                D(10),
            )
            trades.append(trade)
            state = trade.state
    exit_trade = nav.liquidate_close(state, nav.ThreeAssetPrices(records[-1].adj_close3), D(10))
    assert result.final_state == exit_trade.state
    assert result.daily[-1].fees == trades[-1].fees + exit_trade.fees
    assert result.total_fees == sum((trade.fees for trade in trades), ZERO) + exit_trade.fees
    assert result.daily[1].fees == result.daily[1].traded_notional == ZERO


def test_empty_actions_and_explicit_cash_policy_are_identical():
    records = days()
    cash = nav.ThreeAssetTarget((ZERO,) * 3, ONE)
    result = nav.replay(records, {}, D(100))
    assert result == nav.replay(records, {day.date: cash for day in records}, D(100))
    assert result.navs == (ONE,) * len(records)
    assert result.simple_returns == result.log_returns == (ZERO,) * len(records)
    assert result.total_fees == result.total_traded_notional == ZERO
    assert all(day.flat and day.cash == ONE for day in result.daily)


@pytest.mark.parametrize("cash", (D(".3"), D(".5"), D(-1), None, True, D("NaN")))
def test_explicit_cash_weight_cannot_renormalize_or_discard_capital(cash):
    with pytest.raises(nav.ThreeAssetNavError):
        nav.ThreeAssetTarget((D(".1"), D(".2"), D(".3")), cash)


@pytest.mark.parametrize("bad", (None, "2026-01-02", datetime(2026, 1, 2)))
def test_day_requires_a_date_not_an_unaligned_string_or_timestamp(bad):
    with pytest.raises(nav.ThreeAssetNavError, match="date_invalid"):
        nav.ThreeAssetDay(bad, (ONE,) * 3, (ONE,) * 3)


@pytest.mark.parametrize(
    "bad", (None, (), (None,), (days()[0], days()[0]), tuple(reversed(days())))
)
def test_replay_rejects_empty_unavailable_duplicate_or_reversed_days(bad):
    with pytest.raises(nav.ThreeAssetNavError):
        nav.replay(bad, {}, ZERO)


@pytest.mark.parametrize(
    "bad",
    (
        None,
        {date(2026, 1, 3): nav.ThreeAssetTarget((ZERO,) * 3, ONE)},
        {"2026-01-02": nav.ThreeAssetTarget((ZERO,) * 3, ONE)},
        {date(2026, 1, 2): None},
    ),
)
def test_replay_rejects_off_grid_or_untyped_targets(bad):
    with pytest.raises(nav.ThreeAssetNavError):
        nav.replay(days(), bad, ZERO)


def test_replay_revalidates_tampered_records_and_targets_without_modifying_inputs():
    records = days()
    record = records[0]
    object.__setattr__(record, "adj_close3", (ONE, ZERO, ONE))
    with pytest.raises(nav.ThreeAssetNavError, match="prices_invalid"):
        nav.replay(records, {}, ZERO)
    target = nav.ThreeAssetTarget((ZERO,) * 3, ONE)
    object.__setattr__(target, "cash_weight", ZERO)
    with pytest.raises(nav.ThreeAssetNavError, match="cash_weight_mismatch"):
        nav.replay(days(), {days()[0].date: target}, ZERO)


def test_replay_result_repr_and_fields_are_private_immutable_and_io_free(monkeypatch):
    records = list(days())
    target = nav.ThreeAssetTarget((D(".2"), D(".3"), D(".4")), D(".1"))
    actions = {records[0].date: target}
    before = (records.copy(), actions.copy())

    def forbidden(*args, **kwargs):
        pytest.fail("replay must not perform I/O")

    with monkeypatch.context() as guard:
        guard.setattr(builtins, "open", forbidden)
        guard.setattr(os, "getenv", forbidden)
        result = nav.replay(records, actions, D(5))
    assert before == (records, actions)
    assert repr(result) == "ThreeAssetReplay()" and repr(target) == "ThreeAssetTarget()"
    assert "nav=" not in repr(result.daily[0]) and "adj_open3=" not in repr(records[0])
    with pytest.raises(FrozenInstanceError):
        result.daily[0].nav = ZERO
    with pytest.raises(FrozenInstanceError):
        target.cash_weight = ZERO


def test_replay_returns_and_costs_are_independent_of_hostile_decimal_context():
    records = days()
    target = nav.ThreeAssetTarget((D(".2"), D(".3"), D(".4")), D(".1"))
    actions = {records[0].date: target}
    expected = nav.replay(records, actions, D(5))
    with localcontext() as context:
        context.prec, context.rounding = 6, ROUND_DOWN
        context.traps[Inexact] = True
        actual = nav.replay(records, actions, D(5))
        assert context.prec == 6 and context.traps[Inexact]
    assert actual == expected
