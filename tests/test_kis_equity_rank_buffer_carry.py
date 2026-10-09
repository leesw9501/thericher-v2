"""Synthetic, in-memory preparation tests; no observed market rows or fits."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.execution.local_paper import replay_local_paper_account
from thericher_v2.research import kis_equity_rank_buffer_carry as k
from thericher_v2.research import kis_pooled_equity_components as core
from thericher_v2.research import whole_share_portfolio_nav as native

KEYS = tuple(f"opaque-{i:03}" for i in range(128))
SESSIONS = tuple(date(2030, 1, 1) + timedelta(days=i) for i in range(113))
PLAN = k.CarryPlan(SESSIONS, KEYS)


def snapshot(entry=61, order=KEYS, eligible=KEYS):
    scores = {key: len(order) - i for i, key in enumerate(order)}
    day = SESSIONS[entry]
    return core.EligibilitySnapshot(
        entry,
        SESSIONS[entry - 1],
        day,
        tuple(
            core.FeatureRow(key, ((0.0,) * 20,) * 2, (0.0, float(scores.get(key, 0)), 0.0), 0.0)
            for key in sorted(eligible)
        ),
        tuple(sorted(set(KEYS) - set(eligible))),
        datetime.combine(SESSIONS[entry - 1], datetime.min.time(), UTC) + timedelta(hours=20),
        datetime.combine(day, datetime.min.time(), UTC) + timedelta(hours=14),
        datetime.combine(day, datetime.min.time(), UTC) + timedelta(hours=20),
    )


def initial(mode="whole"):
    return k.Ledger.initial(KEYS, mode=mode)


def selected(seal):
    return None if seal.weights is None else tuple(key for key, _ in seal.weights)


def funded():
    state = initial()
    trade = k.rebalance(
        state,
        k.seal_target(snapshot(), ()),
        dict.fromkeys(KEYS[:10], Decimal("103")),
        round_trip_bps=10,
    )
    assert trade.reason == "executed"
    return trade.state


def run(
    policy="rank_buffer_momentum20",
    mode="whole",
    price_source=None,
    snapshots=snapshot,
    terminal=False,
    on_seal=None,
):
    return k.replay(
        PLAN,
        snapshots,
        price_source or (lambda key, day, field: Decimal("103")),
        policy=policy,
        round_trip_bps=10,
        liquidate_last_close=terminal,
        initial_state=initial(mode),
        on_seal=on_seal,
    )


def test_scope_exact_and_calendar_not_window_union():
    assert (k.SESSION_COUNT, k.WARMUP, k.MARK_COUNT, k.KEY_COUNT) == (113, 61, 52, 128)
    assert tuple(PLAN.mark_entries) == tuple(range(61, 113))
    for sessions, keys in [
        (SESSIONS[:-1], KEYS),
        (SESSIONS, KEYS[:-1]),
        (tuple(reversed(SESSIONS)), KEYS),
        (SESSIONS, tuple(reversed(KEYS))),
    ]:
        with pytest.raises(ValueError):
            k.CarryPlan(sessions, keys)


def test_initial_top10_and_rank_buffer_not_top10_replacement():
    owned = KEYS[:10]
    order = KEYS[10:20] + KEYS[:10] + KEYS[20:]
    snap = snapshot(order=order)
    assert selected(k.seal_target(snap, ())) == KEYS[10:20]
    assert selected(k.seal_target(snap, owned)) == owned
    assert selected(k.seal_target(snap, owned, policy="full_top10_momentum20")) == KEYS[10:20]


def test_rank20_inclusive_rank21_removed_and_vacancy_filled():
    owned = KEYS[:10]
    order = KEYS[10:29] + (KEYS[0], KEYS[1]) + KEYS[2:10] + KEYS[29:]
    seal = k.seal_target(snapshot(order=order), owned)
    assert KEYS[0] in selected(seal)
    assert not set(KEYS[1:10]) & set(selected(seal))
    assert selected(seal) == tuple(sorted((KEYS[0], *KEYS[10:19])))


def test_missing_decision_peer_not_target_censor_and_full_ranking():
    owned = KEYS[:10]
    snap = snapshot(eligible=KEYS[1:])
    seal = k.seal_target(snap, owned)
    assert len(seal.ranked_keys) == 127
    assert selected(seal) == KEYS[1:11]
    assert snap.unavailable_keys == (KEYS[0],)


def test_ties_opaque_lexical_and_all_keys_preserved():
    snap = snapshot(order=())
    seal = k.seal_target(snap, ())
    assert seal.ranked_keys == KEYS
    assert selected(seal) == KEYS[:10]
    assert sum(w for _, w in seal.weights) == 1


def test_score_ranking_no_decimal_context_rounding_or_feature_mutation():
    snap = snapshot(order=())
    rows = list(snap.rows)
    rows[1] = replace(rows[1], momentum=(0.0, 1.0000000000000002, 0.0))
    rows[0] = replace(rows[0], momentum=(0.0, 1.0, 0.0))
    snap = replace(snap, rows=tuple(rows))
    with localcontext() as ctx:
        ctx.prec = 2
        seal = k.seal_target(snap, ())
    assert seal.ranked_keys[:2] == (KEYS[1], KEYS[0])
    assert snap.rows[1].momentum[1] == 1.0000000000000002


@pytest.mark.parametrize("count", [0, 1, 9])
def test_fewer10_keeps_inventory_not_liquidation_or_new_basket(count):
    state = funded()
    seal = k.seal_target(snapshot(eligible=KEYS[20 : 20 + count]), state.owned_keys)
    assert seal.weights is None
    assert k.rebalance(state, seal, {}, round_trip_bps=10).state is state
    assert k.mark(state, {}) is None


def test_buy_once_momentum20_same_initial_basket_then_inventory_and_cash():
    snap = snapshot(order=tuple(reversed(KEYS)))
    seal = k.seal_target(snap, (), policy="buy_once_momentum20")
    assert selected(seal) == KEYS[-10:]
    assert seal.weights == k.seal_target(snap, ()).weights
    assert seal.weights == k.seal_target(snap, (), policy="full_top10_momentum20").weights
    assert (
        k.seal_target(
            snapshot(), KEYS[:10], policy="buy_once_momentum20", buy_once_started=True
        ).weights
        is None
    )
    assert k.seal_target(snapshot(eligible=()), (), policy="cash").weights == ()
    with pytest.raises(ValueError, match="policy"):
        k.seal_target(snapshot(), (), policy="tcn")
    with pytest.raises(ValueError, match="policy"):
        k.seal_target(snapshot(), (), policy="buy_once_lex10")


@pytest.mark.parametrize("rate", k.ROUND_TRIP_BPS)
def test_exact_half_roundtrip_fees_whole_floor_no_signal_projection(rate):
    state, snap = initial(), snapshot()
    prices = dict.fromkeys(KEYS[:10], Decimal("103.005"))
    original = prices.copy()
    trade = k.rebalance(state, k.seal_target(snap, ()), prices, round_trip_bps=rate)
    assert trade.reason == "executed"
    assert all(fill.quantity == 9 and fill.price == 103 for fill in trade.fills)
    assert trade.state.fees_paid == trade.traded_notional * Fraction(rate, 20000)
    assert trade.state.cash == 10000 - trade.traded_notional - trade.state.fees_paid
    assert prices == original and snap == snapshot()
    assert k.mark(trade.state, prices) == 10000 - trade.state.fees_paid


@pytest.mark.parametrize("value,expected", [("103.005", "103.00"), ("103.015", "103.02")])
def test_projection_ties_even_independent_decimal_context(value, expected):
    with localcontext() as ctx:
        ctx.prec = 3
        projected, missing = k._prices({KEYS[0]: Decimal(value)}, (KEYS[0],))
    assert not missing and projected[KEYS[0]] == Fraction(Decimal(expected))


@pytest.mark.parametrize(
    "bad",
    [
        None,
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("0"),
        Decimal("-1"),
        Decimal("0.004"),
        103.0,
        1 + 2j,
    ],
)
def test_bad_quote_atomic_and_missing_mark_no_zero(bad):
    state = funded()
    prices = dict.fromkeys(state.owned_keys, Decimal("103"))
    prices[KEYS[0]] = bad
    trade = k.rebalance(
        state, k.seal_target(snapshot(), state.owned_keys), prices, round_trip_bps=10
    )
    assert trade.state is state and trade.fills == ()
    assert trade.unavailable_keys == (KEYS[0],)
    assert k.mark(state, prices) is None


def test_exact_divisible_initial_cash_funds_fees_before_whole_buys():
    state = initial()
    trade = k.rebalance(
        state,
        k.seal_target(snapshot(), ()),
        dict.fromkeys(KEYS[:10], Decimal("100")),
        round_trip_bps=10,
    )
    assert trade.reason == "executed"
    assert trade.state.cash == Fraction(1991, 2)
    assert all(fill.quantity == 9 for fill in trade.fills)


@pytest.mark.parametrize("mode", ["whole", "fractional_reference"])
@pytest.mark.parametrize("rate", k.ROUND_TRIP_BPS)
def test_gap_sales_and_buys_fundable_same_sizing_netcash_exact(mode, rate):
    before = k.rebalance(
        initial(mode),
        k.seal_target(snapshot(), ()),
        dict.fromkeys(KEYS[:10], Decimal("103")),
        round_trip_bps=rate,
    ).state
    prices = dict.fromkeys(KEYS[10:20], Decimal("177.01"))
    prices.update(dict.fromkeys(KEYS[:10], Decimal("51.505")))
    seal = k.seal_target(snapshot(order=KEYS[10:] + KEYS[:10]), before.owned_keys)
    trade = k.rebalance(before, seal, prices, round_trip_bps=rate)
    assert trade.reason == "executed" and trade.state.cash >= 0
    assert [fill.side for fill in trade.fills] == ["sell"] * 10 + ["buy"] * 10
    pre_nav = k.mark(before, prices)
    post_nav = k.mark(trade.state, prices)
    assert post_nav + sum(fill.fee for fill in trade.fills) == pre_nav
    assert trade.state.cash == before.cash + sum(
        ((1 if fill.side == "sell" else -1) * fill.price * fill.quantity - fill.fee)
        for fill in trade.fills
    )


def test_huge_price_whole_floor_zero_is_not_missing_or_fractional_floor():
    prices = dict.fromkeys(KEYS[:10], Decimal("100000"))
    whole = k.rebalance(initial(), k.seal_target(snapshot(), ()), prices, round_trip_bps=10)
    reference = k.rebalance(
        initial("fractional_reference"), k.seal_target(snapshot(), ()), prices, round_trip_bps=10
    )
    assert whole.reason == "no_delta" and whole.state.cash == 10000
    assert not whole.unavailable_keys
    assert reference.reason == "executed" and reference.state.cash == 0
    assert all(q > 0 for q in reference.state.quantities[:10])


def test_zero_cash_incumbent_no_delta_no_fees_and_hold_exact_book():
    quantities = (Fraction(1),) * 10 + (ZERO,) * 118
    costs = (Fraction(100),) * 10 + (ZERO,) * 118
    state = k.Ledger(KEYS, quantities, costs, gross_cash=ZERO)
    prices = dict.fromkeys(KEYS[:10], Decimal("100"))
    trade = k.rebalance(
        state, k.seal_target(snapshot(), state.owned_keys), prices, round_trip_bps=10
    )
    assert trade.state is state and trade.reason == "no_delta" and trade.fills == ()
    assert k.mark(state, prices) == 1000


def test_partial_sale_average_basis_exact_and_input_unchanged():
    state = funded()
    prices = dict.fromkeys(KEYS[:10], Decimal("103"))
    prices[KEYS[0]] = Decimal("206")
    original = prices.copy()
    trade = k.rebalance(
        state, k.seal_target(snapshot(), state.owned_keys), prices, round_trip_bps=20
    )
    assert trade.reason == "executed"
    sold = next(fill for fill in trade.fills if fill.key == KEYS[0] and fill.side == "sell")
    assert (
        trade.state.entry_costs[0]
        == state.entry_costs[0] * (state.quantities[0] - sold.quantity) / state.quantities[0]
    )
    assert prices == original and state == funded()
    assert k.mark(trade.state, prices) + sum(fill.fee for fill in trade.fills) == k.mark(
        state, prices
    )


def test_fractional_reference_piecewise_equation_bounded_exact():
    holdings = tuple(Fraction((i % 7) * 101) for i in range(128))
    weights = (Fraction(1, 128),) * 128
    nav = sum(holdings) + 13
    fee = Fraction(1, 1000)
    result = k._reference_nav(nav, holdings, weights, fee)
    assert (
        result + fee * sum(abs(w * result - h) for w, h in zip(weights, holdings, strict=True))
        == nav
    )
    assert 0 <= result <= nav


@pytest.mark.parametrize("mode", ["whole", "fractional_reference"])
@pytest.mark.parametrize("rate", k.ROUND_TRIP_BPS)
def test_initial_bank_only_profit_compounds_conservation_without_basis_cap(mode, rate):
    state = k.rebalance(
        initial(mode),
        k.seal_target(snapshot(), ()),
        dict.fromkeys(KEYS[:10], Decimal("103")),
        round_trip_bps=rate,
    ).state
    initial_fees = state.fees_paid
    for old, new in [(KEYS[:10], KEYS[10:20]), (KEYS[10:20], KEYS[20:30])]:
        order = new + tuple(key for key in KEYS if key not in new and key not in old) + old
        prices = dict.fromkeys(KEYS, Decimal("103"))
        prices.update(dict.fromkeys(old, Decimal("206")))
        before = k.mark(state, prices)
        trade = k.rebalance(
            state,
            k.seal_target(snapshot(order=order), state.owned_keys),
            prices,
            round_trip_bps=rate,
        )
        assert trade.reason == "executed" and trade.state.owned_keys == new
        assert sum(trade.state.entry_costs) > k.BANK
        assert trade.state.cash >= 0
        fees = sum(fill.fee for fill in trade.fills)
        assert fees == trade.traded_notional * Fraction(rate, 20000)
        assert k.mark(trade.state, prices) + fees == before
        assert trade.state.fees_paid == state.fees_paid + fees
        assert [fill.side for fill in trade.fills] == ["sell"] * 10 + ["buy"] * 10
        state = trade.state
    assert state.fees_paid > initial_fees
    close_prices = dict.fromkeys(state.owned_keys, Decimal("103"))
    before = k.mark(state, close_prices)
    terminal = k.liquidate_final(state, close_prices, round_trip_bps=rate)
    assert terminal.state.owned_keys == ()
    assert terminal.state.cash + sum(fill.fee for fill in terminal.fills) == before
    assert initial(mode).cash == k.BANK == 10000


def test_profitable_rotation_no_basis_cap_keeps_conservation():
    state = funded()
    order = KEYS[10:] + KEYS[:10]
    prices = dict.fromkeys(KEYS, Decimal("103"))
    prices.update(dict.fromkeys(state.owned_keys, Decimal("206")))
    trade = k.rebalance(
        state, k.seal_target(snapshot(order=order), state.owned_keys), prices, round_trip_bps=10
    )
    assert trade.reason == "executed"
    assert sum(trade.state.entry_costs) > k.BANK
    assert k.mark(trade.state, prices) + sum(fill.fee for fill in trade.fills) == k.mark(
        state, prices
    )


def test_delta_only_sells_first_and_average_entry_basis():
    state = funded()
    order = KEYS[10:] + KEYS[:10]
    prices = dict.fromkeys(KEYS, Decimal("103"))
    trade = k.rebalance(
        state, k.seal_target(snapshot(order=order), state.owned_keys), prices, round_trip_bps=10
    )
    assert trade.reason == "executed"
    assert [fill.side for fill in trade.fills] == ["sell"] * 10 + ["buy"] * 10
    assert trade.state.owned_keys == KEYS[10:20]
    assert sum(trade.state.entry_costs) == 9270
    assert (
        k.rebalance(
            trade.state,
            k.seal_target(snapshot(order=order), trade.state.owned_keys),
            prices,
            round_trip_bps=10,
        ).reason
        == "no_delta"
    )


@pytest.mark.parametrize("rate", k.ROUND_TRIP_BPS)
def test_narrow_adapter_matches_native_three_share_accounting(rate):
    names = KEYS[:3]
    state = k.Ledger.initial(names)
    incumbent = native.WholeShareState()
    for raw, weights in [
        (("103", "97", "111"), (Fraction(1, 3),) * 3),
        (("102", "96", "110"), (Fraction(1, 2), ZERO, Fraction(1, 2))),
        (("101", "95", "109"), (ZERO, ZERO, ZERO)),
    ]:
        prices = tuple(Decimal(v) for v in raw)
        trade = k._execute(
            state,
            tuple(zip(names, weights, strict=True)),
            dict(zip(names, prices, strict=True)),
            rate,
        )
        # Native's accounting is reused as an oracle, not its gross-NAV sizing.
        expected = native._trade(
            incumbent,
            tuple(map(Fraction, prices)),
            tuple(int(q) for q in trade.state.quantities),
            Fraction(rate, 20000),
        )
        assert trade.state.quantities == expected.state.quantities3
        assert trade.state.entry_costs == expected.state.entry_costs3
        assert trade.state.gross_cash == expected.state.gross_cash
        assert trade.state.fees_paid == expected.state.fees_paid
        assert trade.traded_notional == expected.traded_notional
        state, incumbent = trade.state, expected.state


ZERO = Fraction(0)


@pytest.mark.parametrize("gap_price", [Decimal("51.50"), Decimal("103"), Decimal("206")])
def test_generic_local_paper_account_cash_inventory_parity_without_store_io(gap_price):
    instrument_binding = {key: f"SYN{i:03}" for i, key in enumerate(KEYS)}
    first = funded()
    prices = dict.fromkeys(KEYS, Decimal("103"))
    buy = k.rebalance(initial(), k.seal_target(snapshot(), ()), prices, round_trip_bps=10)
    prices.update(dict.fromkeys(first.owned_keys, gap_price))
    rotation = k.rebalance(
        first,
        k.seal_target(snapshot(order=KEYS[10:] + KEYS[:10]), first.owned_keys),
        prices,
        round_trip_bps=10,
    )
    events = []
    for i, fill in enumerate((*buy.fills, *rotation.fills)):

        def decimal(value):
            return Decimal(value.numerator) / Decimal(value.denominator)

        events.append(
            SimpleNamespace(
                seq=i,
                event_type="fill",
                schema_version="1",
                created_at=datetime(2030, 1, 1, tzinfo=UTC),
                payload={
                    "source": "local_paper",
                    "symbol": instrument_binding[fill.key],
                    "market": "SYNTHETIC",
                    "side": fill.side,
                    "quantity": str(decimal(fill.quantity)),
                    "price": str(decimal(fill.price)),
                    "fee": str(decimal(fill.fee)),
                },
            )
        )
    account = replay_local_paper_account(SimpleNamespace(iter_events=lambda: iter(events)))
    assert Fraction(account.cash) == rotation.state.cash
    assert tuple((p.symbol, Fraction(p.quantity)) for p in account.positions) == tuple(
        (instrument_binding[key], q)
        for key, q in zip(KEYS, rotation.state.quantities, strict=True)
        if q
    )


@pytest.mark.parametrize("rate", k.ROUND_TRIP_BPS)
def test_fractional_reference_exact_fee_inclusive_funding(rate):
    state = initial("fractional_reference")
    trade = k.rebalance(
        state,
        k.seal_target(snapshot(), ()),
        dict.fromkeys(KEYS[:10], Decimal("100")),
        round_trip_bps=rate,
    )
    assert trade.reason == "executed"
    assert trade.state.cash == 0
    assert trade.state.quantities[0] == Fraction(10) / (1 + Fraction(rate, 20000))
    assert k.mark(trade.state, dict.fromkeys(KEYS[:10], Decimal("100"))) == (
        10000 / (1 + Fraction(rate, 20000))
    )


def test_continuous52_marks_11_opportunities_seal_before_open_only_needed_keys():
    seals, calls = {}, []

    def sealed(seal):
        seals[seal.snapshot.entry_session] = seal

    def source(key, day, field):
        assert day in SESSIONS[61:] and key in KEYS
        if field == "open":
            assert day in seals and key in selected(seals[day])
        calls.append((key, day, field))
        return Decimal("103")

    result = run(price_source=source, on_seal=sealed)
    assert len(result.days) == 52 and result.public.decision_count == 11
    assert k.REVIEW_POSITIONS == tuple(range(0, 52, 5))
    assert result.public.full_open_interval_count == 10
    assert result.public.partial_tail_mark_count == 2
    assert not result.public.independent_sample_count_claimed and k.FIT_COUNT == 0
    assert k.FAMILY_CPU_SECONDS == 300
    assert [day.entry_index for day in result.days if day.seal] == list(range(61, 113, 5))
    assert result.public.fill_count == 10
    assert result.final_state.owned_keys == KEYS[:10]
    assert result.public.unavailable_entries == ()
    assert len(calls) == 11 * 10 + 52 * 10
    assert result.public.net_growth == -result.public.fees_over_bank


def test_missing_held_mark_preserved_not_hidden_by_fewer10():
    def snapshots(entry):
        return snapshot(entry, eligible=KEYS if entry == 61 else KEYS[20:29])

    def prices(key, day, field):
        return None if key == KEYS[0] and day == SESSIONS[66] else Decimal("103")

    result = run(snapshots=snapshots, price_source=prices)
    assert len(result.days) == 52 and result.public.unavailable_entries == (66,)
    assert result.days[5].seal.weights is None
    assert result.days[5].state is result.days[4].state
    assert result.days[5].net_nav is None
    assert result.days[6].net_nav is not None
    assert result.public.net_growth is None
    assert result.final_state.owned_keys == KEYS[:10]


def test_missing_selected_open_not_replaced_using_peer_price():
    calls = []

    def source(key, day, field):
        calls.append((key, day, field))
        return None if field == "open" and key == KEYS[0] else Decimal("103")

    result = run(price_source=source)
    assert result.final_state is result.days[0].state
    assert result.final_state.owned_keys == ()
    assert result.public.unavailable_entries == tuple(range(61, 113, 5))
    assert result.public.net_growth is None
    assert all(key in KEYS[:10] and field == "open" for key, _, field in calls)


def test_buy_once_failed_batch_not_outcome_dependent_retry_and_cash_no_lookup():
    calls = []

    def source(key, day, field):
        calls.append((day, field))
        return None

    result = run(policy="buy_once_momentum20", price_source=source)
    assert result.public.fill_count == 0 and len(calls) == 10
    result = run(policy="cash", price_source=lambda *args: pytest.fail("cash read price"))
    assert result.public.net_growth == 0 and result.public.mark_count == 52


def test_buy_once_initial_momentum_basket_never_rebalances_after_peer_rank_change():
    def snapshots(entry):
        return snapshot(entry, order=tuple(reversed(KEYS)) if entry == 61 else KEYS)

    opens = []

    def prices(key, day, field):
        if field == "open":
            opens.append((key, day))
        return Decimal("103")

    result = run(policy="buy_once_momentum20", snapshots=snapshots, price_source=prices)
    assert selected(result.days[0].seal) == KEYS[-10:]
    assert result.final_state.owned_keys == KEYS[-10:]
    assert result.public.fill_count == 10 and len(opens) == 10
    assert all(day.seal is None or day.seal.weights is None for day in result.days[1:])
    assert all(day.state is result.days[0].state for day in result.days)


def test_only_explicit_final_liquidation_and_fee_on_actual_notional():
    carried, closed = run(), run(terminal=True)
    assert all(day.terminal_trade is None for day in carried.days)
    assert all(day.terminal_trade is None for day in closed.days[:-1])
    assert closed.final_state.owned_keys == () and closed.public.final_liquidation_requested
    assert closed.public.fill_count == 20
    assert closed.public.fees_over_bank == carried.public.fees_over_bank * 2
    assert closed.public.traded_notional_over_bank == carried.public.traded_notional_over_bank * 2


def test_missing_final_price_preserves_book_not_fake_liquidation():
    result = run(
        terminal=True,
        price_source=lambda key, day, field: (
            None if key == KEYS[0] and day == SESSIONS[-1] else Decimal("103")
        ),
    )
    assert result.final_state.owned_keys == KEYS[:10]
    assert result.days[-1].terminal_trade.reason == "price_unavailable"
    assert result.public.net_growth is None and result.public.unavailable_entries == (112,)


@pytest.mark.parametrize("mutation", ["entry", "day", "universe"])
def test_snapshot_binding_fails_before_price_reads(mutation):
    def bad(entry):
        snap = snapshot(entry)
        if mutation == "entry":
            return snapshot(entry + 1)
        if mutation == "day":
            return replace(snap, decision_session=snap.decision_session - timedelta(days=1))
        return replace(snap, unavailable_keys=(), rows=snap.rows[:-1])

    with pytest.raises(ValueError, match="binding"):
        run(snapshots=bad, price_source=lambda *args: pytest.fail("read before binding"))


def test_immutability_invalid_weights_and_stale_ownership():
    state, snap = funded(), snapshot()
    seal = k.seal_target(snap, state.owned_keys)
    with pytest.raises(FrozenInstanceError):
        seal.policy = "cash"
    with pytest.raises(ValueError):
        replace(seal, weights=((KEYS[0], Fraction(1)),))
    with pytest.raises(ValueError, match="binding"):
        k.rebalance(initial(), seal, {}, round_trip_bps=10)
    assert snap == snapshot()


@pytest.mark.parametrize("rate", [0, -1, 30, 10.0, True])
def test_only_fixed_cost_band(rate):
    with pytest.raises(ValueError, match="cost"):
        k.rebalance(initial(), k.seal_target(snapshot(), ()), {}, round_trip_bps=rate)


def test_source_has_no_io_training_order_broker_or_permission_surface(monkeypatch):
    tree = ast.parse(Path(k.__file__).read_text(encoding="utf-8"))
    forbidden = {
        "open",
        "write_text",
        "read_text",
        "write_bytes",
        "read_bytes",
        "fit",
        "OrderIntent",
        "LocalPaperBroker",
        "torch",
        "requests",
        "socket",
        "subprocess",
    }
    assert not any(isinstance(node, ast.Name) and node.id in forbidden for node in ast.walk(tree))
    assert not any(
        isinstance(node, ast.Attribute) and node.attr in forbidden for node in ast.walk(tree)
    )
    monkeypatch.setattr("builtins.open", lambda *a, **kw: pytest.fail("kernel opened a file"))
    result = run()
    assert result.public.development_only and not result.public.broker_fill_parity_claimed
    assert result.public.historical_decision_time_availability == "not_observed"
    assert not any(
        "permission" in name or "safe_to_submit" in name
        for name in result.public.__dataclass_fields__
    )
