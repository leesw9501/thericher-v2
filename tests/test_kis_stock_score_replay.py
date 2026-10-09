"""Supplied predictions and causal synthetic books; no fitting or broker access."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from fractions import Fraction

import pytest

from thericher_v2.research import kis_equity_rank_buffer_carry as book
from thericher_v2.research import kis_pooled_equity_components as core
from thericher_v2.research import kis_stock_score_replay as score

KEYS = tuple(f"opaque-{i:03}" for i in range(128))
SESSIONS = tuple(date(2030, 1, 1) + timedelta(days=i) for i in range(113))
PLAN = book.CarryPlan(SESSIONS, KEYS)


def snapshot(entry=61, eligible=KEYS):
    return core.EligibilitySnapshot(
        entry,
        SESSIONS[entry - 1],
        SESSIONS[entry],
        tuple(core.FeatureRow(key, ((0.0,) * 20,) * 2, (0.0,) * 3, 0.0) for key in eligible),
        tuple(sorted(set(KEYS) - set(eligible))),
        datetime.combine(SESSIONS[entry - 1], datetime.min.time(), UTC) + timedelta(hours=20),
        datetime.combine(SESSIONS[entry], datetime.min.time(), UTC) + timedelta(hours=14),
        datetime.combine(SESSIONS[entry], datetime.min.time(), UTC) + timedelta(hours=20),
    )


def predictions(keys=KEYS):
    return {key: float(i) for i, key in enumerate(keys)}


def run(*, arm="ridge", mode="whole", rate=10, prices=None, on_seal=None):
    return score.replay_scores(
        PLAN,
        snapshot,
        lambda entry: predictions(),
        prices or (lambda key, day, field: Decimal("103.005")),
        arm=arm,
        round_trip_bps=rate,
        liquidate_last_close=True,
        initial_state=book.Ledger.initial(KEYS, mode=mode),
        on_seal=on_seal,
    )


@pytest.mark.parametrize("arm", score.ARMS)
def test_fixed_scores_distinct_from_momentum_and_immutable(arm):
    raw = predictions()
    seal = score.seal_scores(snapshot(), (), raw, arm=arm)
    assert seal.arm == arm
    assert seal.ranked_keys == tuple(reversed(KEYS))
    assert seal.weights == tuple((key, Fraction(1, 10)) for key in KEYS[-10:])
    raw[KEYS[0]] = 9999.0
    assert seal.scores[0] == (KEYS[0], 0.0)
    with pytest.raises(FrozenInstanceError):
        seal.arm = "cash"


@pytest.mark.parametrize(
    "arm",
    [
        "tcn10",
        "tcn20",
        "chronos2_stock_isolated",
        "chronos2_stock_group",
        "pointwise20",
        "pointwise60",
        "peer20",
        "peer60",
    ],
)
def test_additional_model_identity_uses_same_supplied_score_book(arm):
    assert score.ARMS == ("ridge", "hgb", "gru", "equal_fixed_mean_blend")
    seal = score.seal_scores(snapshot(), (), predictions(), arm=arm)
    assert seal.arm == arm
    assert seal.ranked_keys == tuple(reversed(KEYS))
    assert seal.weights == tuple((key, Fraction(1, 10)) for key in KEYS[-10:])
    reference, actual = run(), run(arm=arm)
    assert actual.final_state == reference.final_state
    assert actual.public == reference.public


@pytest.mark.parametrize("arm", ["pointwise10", "peer120", "arbitrary_model"])
def test_unknown_model_identity_rejected_before_prices(arm):
    with pytest.raises(ValueError, match="arm_invalid"):
        score.seal_scores(snapshot(), (), predictions(), arm=arm)
    with pytest.raises(ValueError, match="replay_contract_invalid"):
        run(arm=arm, prices=lambda *args: pytest.fail("unrecognized arm reached prices"))


def test_ties_lexical_and_no_score_rounding():
    raw = dict.fromkeys(KEYS, 1.0)
    raw[KEYS[1]] = 1.0000000000000002
    seal = score.seal_scores(snapshot(), (), raw, arm="ridge")
    assert seal.ranked_keys[:3] == (KEYS[1], KEYS[0], KEYS[2])


@pytest.mark.parametrize("value", [True, 1, float("nan"), float("inf"), Decimal("1")])
def test_non_float_or_nonfinite_score_rejected(value):
    raw = predictions()
    raw[KEYS[0]] = value
    with pytest.raises(ValueError, match="finite"):
        score.seal_scores(snapshot(), (), raw, arm="ridge")


@pytest.mark.parametrize("change", ["missing", "extra", "duplicates_rank", "weights", "arm"])
def test_exact_peer_binding_and_constructor_rechecks(change):
    raw = predictions()
    if change in {"missing", "extra"}:
        raw.pop(KEYS[0]) if change == "missing" else raw.update(extra=1.0)
        with pytest.raises(ValueError, match="peers"):
            score.seal_scores(snapshot(), (), raw, arm="ridge")
    else:
        seal = score.seal_scores(snapshot(), (), raw, arm="ridge")
        kwargs = {
            "duplicates_rank": {"ranked_keys": (KEYS[0],) * 128},
            "weights": {"weights": tuple((key, Fraction(1, 10)) for key in KEYS[:10])},
            "arm": {"arm": "full_top10_momentum20"},
        }
        with pytest.raises(ValueError):
            replace(seal, **kwargs[change])


@pytest.mark.parametrize("count", [0, 1, 9])
def test_insufficient_peers_keep_inventory_no_cash_conversion(count):
    state = run().days[0].state
    eligible = KEYS[:count]
    seal = score.seal_scores(
        snapshot(eligible=eligible), state.owned_keys, predictions(eligible), arm="gru"
    )
    assert seal.weights is None
    trade = score.rebalance_scores(state, seal, {}, round_trip_bps=10)
    assert trade.state is state
    assert not trade.fills


def test_exact_owned_binding_and_atomic_missing_quote():
    seal = score.seal_scores(snapshot(), (), predictions(), arm="hgb")
    state = book.Ledger.initial(KEYS)
    raw = dict.fromkeys(KEYS[-9:], Decimal("103"))
    trade = score.rebalance_scores(state, seal, raw, round_trip_bps=10)
    assert trade.state is state and not trade.fills
    assert trade.unavailable_keys == (KEYS[-10],)
    with pytest.raises(ValueError, match="binding"):
        score.rebalance_scores(run().days[0].state, seal, raw, round_trip_bps=10)


@pytest.mark.parametrize("arm", score.ARMS)
@pytest.mark.parametrize("mode", ["whole", "fractional_reference"])
@pytest.mark.parametrize("rate", [5, 10, 20])
def test_all_arm_book_cost_geometry_fees_and_final_flat(arm, mode, rate):
    result = run(arm=arm, mode=mode, rate=rate)
    public = result.public
    assert (public.mark_count, public.decision_count) == (52, 11)
    assert (public.full_open_interval_count, public.partial_tail_mark_count) == (10, 2)
    assert public.final_inventory_count == 0
    assert not public.unavailable_entries
    assert result.final_state.cash == book.BANK * (1 + public.net_growth)
    assert public.fees_over_bank == public.traded_notional_over_bank * Fraction(rate, 20000)
    assert public.net_growth < 0
    assert all(day.seal is None or day.seal.arm == arm for day in result.days)


def test_seal_callback_precedes_every_open_quote_and_keeps_missing_marks():
    sealed = set()

    def observe(seal):
        sealed.add(seal.snapshot.entry_session)
        assert seal.weights is not None

    def prices(key, day, field):
        if field == "open":
            assert day in sealed
        if field == "close" and day == SESSIONS[62] and key == KEYS[-1]:
            return None
        return Decimal("103")

    result = run(prices=prices, on_seal=observe)
    assert result.public.unavailable_entries == (62,)
    assert result.public.net_growth is None
    assert result.days[1].net_nav is None
    assert result.days[1].state.owned_keys == KEYS[-10:]


def test_calendar_mismatch_before_any_price_callback():
    def forbidden(*args):
        pytest.fail("price callback before valid decision")

    with pytest.raises(ValueError, match="calendar"):
        score.replay_scores(
            PLAN,
            lambda entry: snapshot(entry + 1),
            lambda entry: predictions(),
            forbidden,
            arm="ridge",
            round_trip_bps=10,
            liquidate_last_close=True,
        )


def test_model_score_replay_matches_same_weight_accounting_exactly():
    seal = score.seal_scores(snapshot(), (), predictions(), arm="ridge")
    state = book.Ledger.initial(KEYS)
    prices = dict.fromkeys(KEYS[-10:], Decimal("103"))
    actual = score.rebalance_scores(state, seal, prices, round_trip_bps=10)
    expected = book._execute(state, seal.weights, prices, 10)
    assert actual == expected


@pytest.mark.parametrize("rate", [True, 1, 0, 30])
def test_invalid_cost_rejected_even_if_keep(rate):
    seal = score.seal_scores(snapshot(eligible=()), (), {}, arm="gru")
    with pytest.raises(ValueError, match="cost"):
        score.rebalance_scores(book.Ledger.initial(KEYS), seal, {}, round_trip_bps=rate)
