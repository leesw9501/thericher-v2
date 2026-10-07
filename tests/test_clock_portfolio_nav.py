from __future__ import annotations

import builtins
import os
import socket
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_DOWN, Context, Decimal, localcontext
from itertools import permutations
from pathlib import Path

import numpy as np
import pytest

from thericher_v2.execution import local_paper
from thericher_v2.research import clock_portfolio_nav as nav
from thericher_v2.research.paired_allocation_utility import decimal_daily_flat_nav
from thericher_v2.state import EventStore

D = Decimal
DAY = date(2000, 1, 3)
ONE = D(1)


@pytest.fixture(autouse=True)
def decimal50():
    with localcontext(Context(prec=50)):
        yield


def opportunity(day=DAY, hour=15, entry=("2", "4"), exit_=("3", "5")):
    opened = datetime.combine(day, datetime.min.time(), UTC) + timedelta(hours=hour)
    return nav.ClockOpportunity(
        day, opened, opened + timedelta(minutes=30), tuple(map(D, entry)), tuple(map(D, exit_))
    )


def target(qqq=".5", spy=".5"):
    return nav.ClockTarget((D(qqq), D(spy)))


def replay(records, weights=None, cost="5", dates=None, initial="1"):
    if weights is None:
        weights = [target()] * len(records)
    return nav.replay(
        records,
        dict(zip((r.entry_at for r in records), weights, strict=True)),
        D(cost),
        session_dates=dates or sorted({r.session_date for r in records}),
        initial_cash=D(initial),
    )


def close(actual, expected, scale=ONE):
    assert abs(actual - expected) <= D("1e-45") * scale


@pytest.mark.parametrize("cost", ("0", "1", "2.5", "5", "100"))
@pytest.mark.parametrize("weights", ((".5", ".5"), (".5", "0"), (".1", ".2"), ("0", "0")))
def test_simultaneous_shared_fee_funding_and_cash_conservation(cost, weights):
    row, action = opportunity(), target(*weights)
    result = replay([row], [action], cost)
    slot = result.slots[0]
    fee, risk = D(cost) / 10000, sum(action.weights2)
    post_fee = D(1) / (1 + fee * risk)
    buys = [f for f in slot.fills if f.side == "buy"]
    sells = [f for f in slot.fills if f.side == "sell"]
    for i, symbol in enumerate(nav.SYMBOLS):
        expected = (action.weights2[i] * post_fee / row.entry_open2[i]).quantize(
            nav.QUANTITY_QUANTUM, rounding=ROUND_DOWN
        )
        actual = next((f.quantity for f in buys if f.symbol == symbol), D(0))
        assert actual == expected
    assert all(f.source == "local_paper" and f.quantity > 0 for f in slot.fills)
    assert slot.entry_cash >= 0
    assert slot.entry_cash + sum((f.notional + f.fee for f in buys), D(0)) == slot.pre_nav
    assert slot.final_nav == slot.entry_cash + sum((f.notional - f.fee for f in sells), D(0))
    close(result.total_fees, result.total_traded_notional * fee)
    close(sum((a.net_pnl for a in result.asset_cashflows), D(0)), result.final_nav - 1)
    assert result.daily[0].flat


def test_second_leg_not_resized_after_first_purchase():
    result = replay([opportunity(entry=("1", "1"), exit_=("1", "1"))], cost="5")
    buys = [f for f in result.slots[0].fills if f.side == "buy"]
    assert len(buys) == 2 and buys[0].quantity == buys[1].quantity
    fee = D(".0005")
    quantity = (D(".5") / (1 + fee)).quantize(nav.QUANTITY_QUANTUM, rounding=ROUND_DOWN)
    assert result.final_nav == 1 - 4 * fee * quantity
    assert sum((f.notional + f.fee for f in buys), D(0)) <= 1


def test_partial_allocation_unspent_cash_not_renormalized():
    result = replay([opportunity(entry=("1", "1"), exit_=("1", "1"))], [target(".1", ".2")], "0")
    assert result.slots[0].entry_cash == D(".7")
    assert [f.quantity for f in result.slots[0].fills[:2]] == [D(".1"), D(".2")]
    assert result.final_nav == 1 and result.total_fees == 0


@pytest.mark.parametrize("order", tuple(permutations(nav.SYMBOLS)))
def test_named_asset_order_is_canonical_and_no_leg_priority(order):
    original, t = opportunity(), target(".1", ".4")
    entry = dict(zip(nav.SYMBOLS, original.entry_open2, strict=True))
    exit_ = dict(zip(nav.SYMBOLS, original.exit_open2, strict=True))
    weights = dict(zip(nav.SYMBOLS, t.weights2, strict=True))
    row = nav.ClockOpportunity.from_mapping(
        original.session_date,
        original.entry_at,
        original.exit_at,
        {s: entry[s] for s in order},
        {s: exit_[s] for s in order},
    )
    action = nav.ClockTarget.from_mapping({s: weights[s] for s in order})
    assert replay([row], [action]) == replay([original], [t])


@pytest.mark.parametrize("cost", ("0", "1", "2.5", "5"))
def test_matches_existing_paired_fraction_ledger_and_slot_carry(cost):
    rows = [
        opportunity(hour=15),
        opportunity(hour=17, entry=("5", "2"), exit_=("4", "3")),
        opportunity(DAY + timedelta(days=1), entry=("4", "6"), exit_=("5", "3")),
    ]
    actions = [target(".5", ".5"), target(".2", ".3"), target(".1", ".4")]
    weights = np.array(
        [[float(w) for w in (*t.weights2, 1 - sum(t.weights2))] for t in actions], dtype=np.float64
    )
    growth = np.array(
        [[float(x / e) for e, x in zip(r.entry_open2, r.exit_open2, strict=True)] for r in rows],
        dtype=np.float64,
    )
    reference = decimal_daily_flat_nav(weights, growth, cost_bps=D(cost))
    result = replay(rows, actions, cost)
    for slot, expected in zip(result.slots, reference, strict=True):
        assert abs(slot.final_nav - expected) < D("1e-14")
    assert result.slots[1].pre_nav == result.slots[0].final_nav
    assert result.slots[2].pre_nav == result.slots[1].final_nav
    assert result.daily[0].nav == result.slots[1].final_nav
    assert result.daily[1].nav == result.slots[2].final_nav


def test_flat_dates_daily_logs_and_global_return_path():
    dates = [DAY + timedelta(days=i) for i in range(4)]
    row = opportunity(dates[1])
    result = replay([row], dates=dates)
    assert len(result.daily) == 4
    assert result.navs[0] == 1
    assert result.navs[1] == result.navs[2] == result.navs[3]
    assert result.log_returns[0] == result.log_returns[2] == result.log_returns[3] == 0
    assert result.daily[2].fees == result.daily[2].traded_notional == 0
    close(sum(result.log_returns, D(0)), result.final_nav.ln())
    assert all(day.flat for day in result.daily)
    empty = nav.replay([], {}, D(5), session_dates=dates)
    assert empty.navs == (D(1),) * 4 and empty.log_returns == (D(0),) * 4


def test_independent_restart_full_fill_account_and_per_asset_attribution():
    rows = [opportunity(), opportunity(hour=17), opportunity(DAY + timedelta(days=1))]
    result = replay(rows)
    prefix = replay(rows[:2])
    suffix = replay(rows[2:], initial=str(prefix.final_nav))
    assert result.final_nav == suffix.final_nav
    assert result.slots[2] == suffix.slots[0]
    fills = tuple(fill for slot in result.slots for fill in slot.fills)
    events = nav._events(fills)
    account = local_paper.replay_local_paper_account(nav._EventView(events), starting_cash=D(1))
    fifo = local_paper.replay_local_paper_realized_pnl(events)
    assert account.cash == result.final_nav and not account.positions and fifo.open_quantity == 0
    close(fifo.realized_after_cost_pnl, result.final_nav - 1)
    for flow in result.asset_cashflows:
        own = tuple(f for f in fills if f.symbol == flow.symbol)
        expected = local_paper.replay_local_paper_realized_pnl(nav._events(own))
        assert flow.net_pnl == expected.realized_after_cost_pnl
        close(flow.gross_pnl - flow.fees, flow.net_pnl)
        assert flow.fees == sum((f.fee for f in own), D(0))
        assert flow.traded_notional == sum((f.notional for f in own), D(0))
    assert result == replay(rows)


def test_exit_prices_never_change_planned_entry_quantities():
    original = replay([opportunity()])
    changed = replay([opportunity(exit_=("1000", ".01"))])
    before = [f for f in original.slots[0].fills if f.side == "buy"]
    after = [f for f in changed.slots[0].fills if f.side == "buy"]
    assert before == after


def test_reverse_actual_fill_order_same_shared_account_and_attribution():
    result = replay([opportunity()], [target(".1", ".4")])
    fills = result.slots[0].fills
    reordered = tuple(reversed(fills[:2])) + tuple(reversed(fills[2:]))
    account = local_paper.replay_local_paper_account(
        nav._EventView(nav._events(reordered)), starting_cash=D(1)
    )
    close(account.cash, result.final_nav)
    assert not account.positions
    assert nav._asset_flows(reordered) == result.asset_cashflows


def test_second_half_uses_entering_nav_not_new_capital():
    rows = [opportunity(DAY + timedelta(days=i)) for i in range(4)]
    whole = replay(rows)
    first = replay(rows[:2])
    second = replay(rows[2:], initial=str(first.final_nav))
    assert second.daily == whole.daily[2:]
    close(sum(whole.log_returns[2:], D(0)), (whole.final_nav / first.final_nav).ln())
    assert second.slots[0].pre_nav == first.final_nav != 1


def test_quantity_lattice_explicit_uniform_no_integer_capital_resolution():
    row = opportunity(entry=("3", "7"), exit_=("3", "7"))
    result = replay([row], [target(".1", ".2")], "0")
    buys = [f for f in result.slots[0].fills if f.side == "buy"]
    assert all(f.quantity % nav.QUANTITY_QUANTUM == 0 for f in buys)
    assert 0 < buys[0].quantity < 1
    assert result.slots[0].entry_cash >= D(".7")
    dust = replay([row], [target("1e-45", "0")], "5")
    assert not dust.slots[0].fills and dust.final_nav == 1
    assert nav.QUANTITY_QUANTUM == D("1e-40") and nav.QUANTITY_ROUNDING == ROUND_DOWN


@pytest.mark.parametrize(
    "value",
    (D("-.1"), D(".500000000000000000000000000001"), D("NaN"), D("Infinity"), 0.1, True, "0.1"),
)
def test_invalid_targets_not_repaired(value):
    with pytest.raises(nav.ClockPortfolioNavError):
        nav.ClockTarget((value, D(0)))


@pytest.mark.parametrize("value", (D(0), D(-1), D("NaN"), D("Infinity"), 2, None))
@pytest.mark.parametrize("side", ("entry", "exit"))
def test_invalid_marks_unavailable_even_for_zero_action(value, side):
    row = opportunity()
    args = dict(
        session_date=row.session_date,
        entry_at=row.entry_at,
        exit_at=row.exit_at,
        entry_open2=row.entry_open2,
        exit_open2=row.exit_open2,
    )
    args[f"{side}_open2"] = (value, D(1))
    with pytest.raises(nav.ClockPortfolioNavError, match="prices_invalid"):
        nav.ClockOpportunity(**args)


@pytest.mark.parametrize("kind", ("naive", "offset", "overnight", "duration", "seconds"))
def test_invalid_opportunity_geometry(kind):
    row = opportunity()
    opened, exited = row.entry_at, row.exit_at
    if kind == "naive":
        opened = opened.replace(tzinfo=None)
    elif kind == "offset":
        from datetime import timezone

        opened = opened.replace(tzinfo=timezone(timedelta(hours=1)))
    elif kind == "overnight":
        exited += timedelta(days=1)
    elif kind == "duration":
        exited += timedelta(minutes=1)
    else:
        opened += timedelta(seconds=1)
        exited += timedelta(seconds=1)
    with pytest.raises(nav.ClockPortfolioNavError):
        nav.ClockOpportunity(row.session_date, opened, exited, row.entry_open2, row.exit_open2)


@pytest.mark.parametrize("cost", (D(-1), D(101), D("NaN"), D("Infinity"), 5, True, "5"))
def test_invalid_cost_domain(cost):
    row = opportunity()
    with pytest.raises(nav.ClockPortfolioNavError, match="cost_bps_invalid"):
        nav.replay([row], {row.entry_at: target()}, cost, session_dates=[DAY])


@pytest.mark.parametrize(
    "kind",
    (
        "duplicate",
        "reversed",
        "overlap",
        "missing-target",
        "extra-target",
        "duplicate-date",
        "outside-date",
        "no-date",
    ),
)
def test_duplicate_order_split_and_key_cardinality_fail_closed(kind):
    first, second = opportunity(), opportunity(hour=17)
    records, dates = [first, second], [DAY]
    actions = {r.entry_at: target() for r in records}
    if kind == "duplicate":
        records = [first, first]
    elif kind == "reversed":
        records.reverse()
    elif kind == "overlap":
        records[1] = nav.ClockOpportunity(
            DAY,
            first.entry_at + timedelta(minutes=10),
            first.exit_at + timedelta(minutes=10),
            first.entry_open2,
            first.exit_open2,
        )
        actions = {r.entry_at: target() for r in records}
    elif kind == "missing-target":
        actions.pop(second.entry_at)
    elif kind == "extra-target":
        actions[second.exit_at] = target()
    elif kind == "duplicate-date":
        dates *= 2
    elif kind == "outside-date":
        dates = [DAY + timedelta(days=1)]
    else:
        dates = []
    with pytest.raises(nav.ClockPortfolioNavError):
        nav.replay(records, actions, D(5), session_dates=dates)


@pytest.mark.parametrize("symbol", ("IWM", "spy", "UNKNOWN"))
def test_unknown_or_incomplete_symbol_maps_invalid(symbol):
    with pytest.raises(nav.ClockPortfolioNavError, match="target_symbols_invalid"):
        nav.ClockTarget.from_mapping({"QQQ": D(".5"), symbol: D(".5")})


@pytest.mark.parametrize("cash", (D(0), D(-1), D("NaN"), D("Infinity"), 1))
def test_invalid_initial_cash(cash):
    with pytest.raises(nav.ClockPortfolioNavError, match="initial_cash_invalid"):
        nav.replay([], {}, D(5), session_dates=[DAY], initial_cash=cash)


def test_numeric_range_categorical_no_silent_quantity_repair():
    row = opportunity(entry=("1e-1000", "1"))
    with pytest.raises(nav.ClockPortfolioNavError, match="numeric_range"):
        replay([row])


def test_underflow_is_unavailable_not_zero_exit_price_or_fee():
    row = opportunity(exit_=("1e-1000100", "1"))
    with pytest.raises(nav.ClockPortfolioNavError, match="numeric_range"):
        replay([row])


def test_frozen_hidden_results_and_caller_decimal_context_independent():
    row, action = opportunity(), target()
    expected = replay([row], [action])
    with localcontext(Context(prec=12, rounding=ROUND_DOWN)):
        actual = replay([row], [action])
    assert actual == expected and row == opportunity() and action == target()
    assert repr(actual) == "ClockPortfolioReplay()"
    assert all(not f.repr for f in fields(actual))
    for item in (row, action, actual, actual.daily[0], actual.slots[0], actual.slots[0].fills[0]):
        with pytest.raises(FrozenInstanceError):
            item.extra = 1
    fill = actual.slots[0].fills[0]
    assert not any(f.repr for f in fields(fill) if f.name in {"quantity", "price", "fee"})


def test_pure_no_files_network_credentials_or_broker_calls(monkeypatch):
    row, action = opportunity(), target()

    def prohibited(*args, **kwargs):
        raise AssertionError("pure clock ledger cannot access external state")

    with monkeypatch.context() as isolated:
        for owner, name in (
            (builtins, "open"),
            (Path, "open"),
            (Path, "read_bytes"),
            (Path, "read_text"),
            (os, "getenv"),
            (socket, "create_connection"),
            (EventStore, "__init__"),
            (local_paper.LocalPaperBroker, "__init__"),
        ):
            isolated.setattr(owner, name, prohibited)
        result = replay([row], [action])
    assert result.final_nav > 0
