"""Synthetic exact sizing and attribution; no source data, artifacts or fits."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction

import pytest

from thericher_v2.research import kis_equity_rank_buffer_carry as book
from thericher_v2.research import kis_pooled_equity_components as core
from thericher_v2.research import kis_stock_risk_attribution as risk
from thericher_v2.research import kis_stock_score_replay as score

KEYS = tuple(f"opaque-{i:03}" for i in range(128))
SESSIONS = tuple(date(2030, 1, 1) + timedelta(days=i) for i in range(113))
PLAN = book.CarryPlan(SESSIONS, KEYS)
ZERO = Fraction(0)
ARMS = score.ARMS + book.POLICIES


def snapshot(entry=61, *, order=KEYS, eligible=KEYS):
    ranks = {key: float(len(order) - i) for i, key in enumerate(order)}
    return core.EligibilitySnapshot(
        entry,
        SESSIONS[entry - 1],
        SESSIONS[entry],
        tuple(
            core.FeatureRow(key, ((0.0,) * 20,) * 2, (0.0, ranks.get(key, 0.0), 0.0), 0.0)
            for key in sorted(eligible)
        ),
        tuple(sorted(set(KEYS) - set(eligible))),
        datetime.combine(SESSIONS[entry - 1], datetime.min.time(), UTC) + timedelta(hours=20),
        datetime.combine(SESSIONS[entry], datetime.min.time(), UTC) + timedelta(hours=14),
        datetime.combine(SESSIONS[entry], datetime.min.time(), UTC) + timedelta(hours=20),
    )


def predictions(entry):
    return {key: float(i) for i, key in enumerate(KEYS)}


def constant_price(*args):
    return Decimal("103.005")


@pytest.mark.parametrize(
    "arm", ["tcn10", "tcn20", "chronos2_stock_isolated", "chronos2_stock_group"]
)
@pytest.mark.parametrize("mode", ["whole", "fractional_reference"])
def test_additional_model_scores_share_exact_risk_accounting(arm, mode):
    actual = risk.replay_risk(
        PLAN,
        snapshot,
        constant_price,
        exposure=Fraction(1, 10),
        round_trip_bps=10,
        liquidate_last_close=True,
        mode=mode,
        arm=arm,
        score_source=predictions,
    )
    reference = risk.replay_risk(
        PLAN,
        snapshot,
        constant_price,
        exposure=Fraction(1, 10),
        round_trip_bps=10,
        liquidate_last_close=True,
        mode=mode,
        arm="ridge",
        score_source=predictions,
    )
    assert actual.attribution_complete
    assert actual.assets == reference.assets
    assert actual.net_gain == reference.net_gain
    assert actual.fees == reference.fees
    assert actual.replay.final_state == reference.replay.final_state


def run(
    arm="ridge",
    exposure=Fraction(1, 4),
    mode="whole",
    rate=10,
    prices=constant_price,
    snapshots=snapshot,
    scores=predictions,
    terminal=True,
    on_seal=None,
):
    kwargs = dict(arm=arm, score_source=scores) if arm in score.ARMS else dict(policy=arm)
    return risk.replay_risk(
        PLAN,
        snapshots,
        prices,
        exposure=exposure,
        mode=mode,
        round_trip_bps=rate,
        liquidate_last_close=terminal,
        on_seal=on_seal,
        **kwargs,
    )


def original(arm, mode, rate, prices=constant_price, snapshots=snapshot, scores=predictions):
    kwargs = dict(
        round_trip_bps=rate,
        liquidate_last_close=True,
        initial_state=book.Ledger.initial(KEYS, mode=mode),
    )
    if arm in score.ARMS:
        return score.replay_scores(PLAN, snapshots, scores, prices, arm=arm, **kwargs)
    return book.replay(PLAN, snapshots, prices, policy=arm, **kwargs)


def check_totals(result):
    assert len(result.days) == 52 and len(result.assets) == 128 and len(result.seals) == 11
    assert all(tuple(stock.key for stock in day.stocks) == KEYS for day in result.days)
    assert result.attribution_complete
    previous = book.BANK
    for day, attribution in zip(result.replay.days, result.days, strict=True):
        assert attribution.nav_delta == day.net_nav - previous
        assert attribution.net_contribution == attribution.nav_delta
        assert sum(stock.net_contribution for stock in attribution.stocks) == attribution.nav_delta
        assert sum(stock.fees for stock in attribution.stocks) == attribution.fees
        for stock in attribution.stocks:
            assert stock.net_contribution == (
                stock.marked_value - stock.prior_marked_value - stock.signed_fill_cash - stock.fees
            )
        previous = day.net_nav
    assert result.net_gain == previous - book.BANK == sum(a.net_contribution for a in result.assets)
    assert result.fees == result.replay.final_state.fees_paid == sum(a.fees for a in result.assets)
    assert result.traded_notional == sum(a.traded_notional for a in result.assets)
    if result.traded_notional:
        assert result.fees / result.traded_notional in tuple(
            Fraction(rate, 20000) for rate in (5, 10, 20)
        )
    else:
        assert result.fees == 0


@pytest.mark.parametrize("arm", ARMS)
@pytest.mark.parametrize("mode", ["whole", "fractional_reference"])
@pytest.mark.parametrize("rate", [5, 10, 20])
def test_all_48_full_exposure_references_exact_original_parity(arm, mode, rate):
    result = run(arm, Fraction(1), mode, rate)
    assert result.replay == original(arm, mode, rate)
    check_totals(result)
    assert all(seal.weights == seal.original.weights for seal in result.seals)


@pytest.mark.parametrize("exposure", [Fraction(1, 10), Fraction(1, 4)])
@pytest.mark.parametrize("mode", ["whole", "fractional_reference"])
def test_all_fixed_96_sizing_cells_conserve_and_stay_flat_at_terminal(exposure, mode):
    for arm in ARMS:
        for rate in (5, 10, 20):
            result = run(arm, exposure, mode, rate)
            check_totals(result)
            assert result.replay.final_state.owned_keys == ()
            assert result.fees == result.traded_notional * Fraction(rate, 20000)
            for seal in result.seals:
                if seal.weights:
                    assert sum(w for _, w in seal.weights) == exposure
                    assert seal.cash_weight == 1 - exposure


@pytest.mark.parametrize("exposure", risk.EXPOSURES)
def test_seal_is_immutable_and_scales_only_weights_not_ranks_or_raw_scores(exposure):
    raw = predictions(61)
    original_seal = score.seal_scores(snapshot(), (), raw, arm="ridge")
    scaled = risk.scale_seal(original_seal, exposure)
    raw[KEYS[0]] = 99999.0
    assert scaled.original is original_seal and original_seal.scores[0] == (KEYS[0], 0.0)
    assert scaled.weights == tuple((key, exposure / 10) for key in KEYS[-10:])
    with pytest.raises(FrozenInstanceError):
        scaled.exposure = Fraction(1)


@pytest.mark.parametrize("bad", [0, 1, True, 0.1, Decimal("0.1"), Fraction(0), Fraction(1, 2)])
def test_only_exact_frozen_exposures_accepted(bad):
    with pytest.raises(ValueError, match="exposure"):
        risk.scale_seal(book.seal_target(snapshot(), ()), bad)
    with pytest.raises(ValueError, match="exposure"):
        run(exposure=bad)


def test_scaled_rank_buffer_uses_actual_floor_inventory_not_full_exposure_actions():
    order = KEYS[10:20] + KEYS[:10] + KEYS[20:]

    def snapshots(entry):
        return snapshot(entry, order=KEYS if entry == 61 else order)

    def prices(key, day, field):
        return Decimal("103") if key in KEYS[:10] else Decimal("10")

    full = run("rank_buffer_momentum20", Fraction(1), prices=prices, snapshots=snapshots)
    scaled = run("rank_buffer_momentum20", Fraction(1, 10), prices=prices, snapshots=snapshots)
    assert full.replay.days[0].state.owned_keys == KEYS[:10]
    assert scaled.replay.days[0].state.owned_keys == ()
    assert tuple(key for key, _ in full.seals[1].weights) == KEYS[:10]
    assert tuple(key for key, _ in scaled.seals[1].weights) == KEYS[10:20]
    assert scaled.seals[1].original.owned_keys == ()
    check_totals(scaled)


def test_whole_floors_leave_cash_and_never_renormalize_surviving_names():
    seal = risk.scale_seal(book.seal_target(snapshot(), ()), Fraction(1, 10))
    prices = dict.fromkeys(KEYS[:10], Decimal("10"))
    prices.update(dict.fromkeys(KEYS[:5], Decimal("100000")))
    state = book.Ledger.initial(KEYS)
    trade = risk.rebalance_scaled(state, seal, prices, round_trip_bps=10)
    assert trade == book._execute(state, seal.weights, prices, 10)
    assert trade.state.quantities[:5] == (ZERO,) * 5
    assert trade.state.quantities[5:10] == (Fraction(9),) * 5
    assert trade.state.cash > 9500
    assert seal.cash_weight == Fraction(9, 10)


@pytest.mark.parametrize("mode", ["whole", "fractional_reference"])
def test_scaled_fee_aware_funding_uses_post_fee_nav_and_actual_delta(mode):
    state = book.Ledger.initial(KEYS, mode=mode)
    seal = risk.scale_seal(book.seal_target(snapshot(), ()), Fraction(1, 4))
    quotes = dict.fromkeys(KEYS[:10], Decimal("10"))
    trade = risk.rebalance_scaled(state, seal, quotes, round_trip_bps=20)
    fee = Fraction(20, 20000)
    solved = book.BANK / (1 + fee * Fraction(1, 4))
    q = Fraction(1, 40) * solved / 10
    expected = q if mode == "fractional_reference" else Fraction(q.numerator // q.denominator)
    assert trade.state.quantities[:10] == (expected,) * 10
    assert trade.state.cash == book.BANK - trade.traded_notional - trade.state.fees_paid
    assert trade.state.fees_paid == trade.traded_notional * fee
    if mode == "fractional_reference":
        assert trade.state.cash == solved * Fraction(3, 4)


@pytest.mark.parametrize("mode", ["whole", "fractional_reference"])
def test_buys_sells_increase_reduce_gaps_and_terminal_exact_stock_day_formula(mode):
    def snapshots(entry):
        order = KEYS if entry < 71 else KEYS[10:] + KEYS[:10]
        return snapshot(entry, order=order)

    def prices(key, day, field):
        pos = SESSIONS.index(day)
        if key == KEYS[0] and pos >= 66:
            return Decimal("40.015" if field == "open" else "41.005")
        return Decimal("10.005" if field == "open" else "11.015")

    result = run("full_top10_momentum20", mode=mode, prices=prices, snapshots=snapshots)
    check_totals(result)
    day = result.replay.days[5]
    assert any(f.side == "sell" and f.key == KEYS[0] for f in day.trade.fills)
    assert any(f.side == "buy" for f in day.trade.fills)
    rotation = result.replay.days[10].trade.fills
    assert [f.side for f in rotation] == sorted([f.side for f in rotation], reverse=True)
    assert result.replay.days[-1].terminal_trade.fills
    terminal = result.days[-1]
    assert all(stock.marked_value == 0 for stock in terminal.stocks)
    assert sum(stock.signed_fill_cash for stock in terminal.stocks) < 0


def test_terminal_fee_and_prior_overnight_gap_not_double_counted():
    result = run(
        "buy_once_momentum20",
        exposure=Fraction(1, 4),
        prices=lambda key, day, field: Decimal("10") if day == SESSIONS[61] else Decimal("12"),
    )
    first, next_day, last = result.days[0], result.days[1], result.days[-1]
    assert first.net_contribution == -first.fees
    quantities = result.replay.days[0].state.quantities
    assert next_day.net_contribution == sum(quantities) * 2
    assert last.net_contribution == -last.fees
    assert last.fees == result.replay.days[-1].terminal_trade.traded_notional * Fraction(10, 20000)
    check_totals(result)


@pytest.mark.parametrize("arm", ["ridge", "rank_buffer_momentum20"])
@pytest.mark.parametrize("count", [0, 1, 9])
def test_fewer_than_ten_keeps_scaled_inventory_and_never_liquidates(arm, count):
    def snapshots(entry):
        return snapshot(entry, eligible=KEYS if entry == 61 else KEYS[:count])

    def scores(entry):
        return {key: float(i) for i, key in enumerate(snapshots(entry).eligible_keys)}

    result = run(arm, snapshots=snapshots, scores=scores, terminal=False)
    assert result.replay.days[0].state.owned_keys
    assert all(seal.weights is None and seal.cash_weight is None for seal in result.seals[1:])
    assert all(day.state is result.replay.days[0].state for day in result.replay.days[1:])
    assert result.replay.final_state.owned_keys
    check_totals(result)


def test_cash_zero_weights_no_quotes_no_fees_exact_zero_stock_contributions():
    result = run("cash", prices=lambda *args: pytest.fail("cash requested a quote"))
    assert result.net_gain == result.fees == result.traded_notional == 0
    assert all(seal.weights == () and seal.cash_weight == 1 for seal in result.seals)
    assert all(stock.net_contribution == 0 for day in result.days for stock in day.stocks)
    check_totals(result)


def test_seal_callback_before_quotes_and_failed_durability_prevents_all_lookup():
    observed = set()

    def on_seal(seal):
        assert isinstance(seal, risk.ScaledSeal)
        assert sum(w for _, w in seal.weights) == Fraction(1, 4)
        observed.add(seal.original.snapshot.entry_session)

    def prices(key, day, field):
        if field == "open":
            assert day in observed
        return Decimal("10")

    run(prices=prices, on_seal=on_seal)
    assert len(observed) == 11

    def failure(seal):
        raise OSError("synthetic durable write failure")

    with pytest.raises(OSError):
        run(prices=lambda *args: pytest.fail("lookup before durable seal"), on_seal=failure)


@pytest.mark.parametrize("field,entry", [("open", 61), ("close", 62), ("close", 112)])
def test_missing_selected_or_held_marks_never_zero_or_complete(field, entry):
    def prices(key, day, quote):
        return (
            None if key == KEYS[-1] and day == SESSIONS[entry] and quote == field else Decimal("10")
        )

    result = run(prices=prices)
    assert not result.attribution_complete and result.net_gain is None
    assert entry in result.replay.public.unavailable_entries
    assert result.days[entry - 61].net_contribution is None
    assert all(asset.net_contribution is None for asset in result.assets)
    assert result.fees == result.replay.final_state.fees_paid
    if field == "close":
        assert result.days[entry - 61].stocks[-1].net_contribution is None
        if entry != 112:
            assert result.days[entry - 60].stocks[-1].net_contribution is None
            assert result.days[entry - 59].stocks[-1].net_contribution is not None
        else:
            assert result.replay.final_state.owned_keys


def test_failed_open_batch_is_atomic_and_buy_once_does_not_retry_missing_basket():
    calls = []

    def missing(key, day, field):
        calls.append((key, day, field))
        return None

    result = run("buy_once_momentum20", prices=missing)
    assert len(calls) == 10
    assert result.replay.final_state.cash == book.BANK
    assert result.replay.final_state.owned_keys == ()
    assert result.replay.days[0].trade.fills == ()
    assert not result.attribution_complete


def test_rebalance_binding_and_invalid_cost_fail_even_on_keep():
    state = book.Ledger.initial(KEYS)
    seal = risk.scale_seal(
        score.seal_scores(snapshot(), (), predictions(61), arm="ridge"), Fraction(1, 4)
    )
    funded = risk.rebalance_scaled(
        state, seal, dict.fromkeys(KEYS, Decimal("10")), round_trip_bps=10
    ).state
    with pytest.raises(ValueError, match="binding"):
        risk.rebalance_scaled(funded, seal, {}, round_trip_bps=10)
    keep = risk.scale_seal(
        book.seal_target(snapshot(eligible=()), funded.owned_keys), Fraction(1, 4)
    )
    for bad in (True, 0, 30, 10.0):
        with pytest.raises(ValueError, match="cost"):
            risk.rebalance_scaled(funded, keep, {}, round_trip_bps=bad)


def test_attribution_rejects_fabricated_fill_cash_quantity_or_nav():
    result = run()
    before = book.Ledger.initial(KEYS)
    day = result.replay.days[0]
    quotes = dict.fromkeys(KEYS, Decimal("103.005"))
    bad_fill = replace(day.trade.fills[0], quantity=day.trade.fills[0].quantity + 1)
    bad_trade = replace(day.trade, fills=(bad_fill,) + day.trade.fills[1:])
    with pytest.raises(ValueError, match="conservation"):
        risk.attribute_day(
            before, replace(day, trade=bad_trade), {}, quotes, previous_nav=book.BANK
        )
    with pytest.raises(ValueError, match="nav_mark"):
        risk.attribute_day(
            before, replace(day, net_nav=day.net_nav + 1), {}, quotes, previous_nav=book.BANK
        )


def test_projection_ties_even_attribution_independent_low_decimal_context():
    with localcontext() as ctx:
        ctx.prec = 2
        result = run(prices=lambda key, day, field: Decimal("10.015"))
    check_totals(result)
    first = result.replay.days[0]
    assert all(fill.price == Fraction(Decimal("10.02")) for fill in first.trade.fills)
    assert result.days[0].net_contribution == -result.days[0].fees


def test_full_reference_parity_with_rotation_missing_mark_and_failed_open():
    def snapshots(entry):
        return snapshot(entry, order=KEYS if entry < 71 else KEYS[10:] + KEYS[:10])

    def scores(entry):
        return {key: float(i if entry < 71 else -i) for i, key in enumerate(KEYS)}

    def prices(key, day, field):
        if day == SESSIONS[62] and field == "close" and key in (KEYS[0], KEYS[-1]):
            return None
        if day == SESSIONS[71] and field == "open" and key == KEYS[0]:
            return None
        return Decimal("10") if day < SESSIONS[71] else Decimal("11")

    for arm in ARMS:
        result = run(arm, Fraction(1), prices=prices, snapshots=snapshots, scores=scores)
        assert result.replay == original(arm, "whole", 10, prices, snapshots, scores)


@pytest.mark.parametrize("mutation", ["calendar", "universe", "both_arms"])
def test_bad_scope_prevents_quotes(mutation):
    kwargs = dict(arm="ridge", score_source=predictions)
    if mutation == "both_arms":
        kwargs["policy"] = "cash"

    def snapshots(entry):
        if mutation == "calendar":
            return snapshot(entry + 1)
        if mutation == "universe":
            return replace(snapshot(entry), rows=snapshot(entry).rows[:-1])
        return snapshot(entry)

    with pytest.raises(ValueError):
        risk.replay_risk(
            PLAN,
            snapshots,
            lambda *args: pytest.fail("invalid scope read quotes"),
            exposure=Fraction(1, 4),
            round_trip_bps=10,
            liquidate_last_close=True,
            **kwargs,
        )


def test_pure_adapter_does_not_open_files(monkeypatch):
    monkeypatch.setattr("builtins.open", lambda *a, **kw: pytest.fail("adapter opened a file"))
    result = run("cash")
    assert result.replay.public.development_only
    assert not result.replay.public.broker_fill_parity_claimed
    assert result.replay.public.historical_decision_time_availability == "not_observed"
