from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path

import numpy as np
import pytest

from thericher_v2.execution.local_paper import (
    LOCAL_PAPER_SOURCE,
    LocalPaperFill,
    replay_local_paper_account,
    replay_local_paper_realized_pnl,
)
from thericher_v2.research import five_session_cohort as core
from thericher_v2.state import Event, EventStore

ENTRY = datetime(2025, 1, 6, 14, 30, tzinfo=UTC)
OPENS = tuple(ENTRY + timedelta(days=i) for i in range(5))
CLOSES = tuple(at + timedelta(hours=6, minutes=30) for at in OPENS)
PRIOR = tuple(CLOSES[0] - timedelta(days=i) for i in range(21, 0, -1))


@dataclass(frozen=True)
class Features:
    identities: tuple[str, ...]
    decision: datetime
    tokens: np.ndarray
    eligible: np.ndarray
    momentum: np.ndarray
    stamp: str
    target_open: datetime
    target_close: datetime


def feature_fixture() -> tuple[Features, np.ndarray]:
    prices = np.broadcast_to(np.geomspace(100, 110, 21)[:, None], (21, 512)).copy()
    features = Features(
        identities=tuple(f"S{i:04d}/NAS" for i in range(512)),
        decision=ENTRY - timedelta(hours=1),
        tokens=np.zeros((512, 20, 5)),
        eligible=np.ones(512, dtype=bool),
        momentum=prices[-1] / prices[0] - 1,
        stamp="synthetic-prior-only",
        target_open=OPENS[0],
        target_close=CLOSES[0],
    )
    return features, prices


def frame() -> core.FiveSessionFrame:
    features, prices = feature_fixture()
    return core.make_five_session_frame(
        index=720,
        feature_frame=features,
        prior_closes=PRIOR,
        prior_close_prices=prices,
        session_opens=OPENS,
        session_closes=CLOSES,
    )


def price_fixture():
    held = [0, 4, 127, 128, 511]
    opens = np.full(512, np.nan)
    closes = np.full((5, 512), np.nan)
    weights = np.zeros(512)
    opens[held] = [10, 20, 30, 40, 50]
    closes[:, held] = [
        [11, 19, 31, 40, 55],
        [9, 24, 32, 41, 48],
        [13, 18, 29, 45, 51],
        [12, 22, 35, 39, 59],
        [14, 16, 33, 48, 60],
    ]
    weights[held] = 0.1
    return held, opens, closes, weights


def canonical_accounting(tmp_path, held, opens, closes, weights, bps, capital):
    """Independent Decimal fills projected by real source:local_paper accounting."""
    store = EventStore(
        tmp_path / "unused.sqlite", tmp_path / "fills.jsonl", rebuild_sqlite_on_append=False
    )
    with localcontext() as context:
        context.prec = 50
        cash = Decimal(str(capital))
        cost = Decimal(bps) / Decimal(20000)
        allocation = tuple(Decimal(str(w)) for w in weights)
        reference = cash / (1 + cost * sum(allocation))
        quantities = tuple(
            reference * allocation[i] / Decimal(str(opens[i])) if i in held else Decimal(0)
            for i in range(len(weights))
        )

        def fill(i, side, price, when):
            price = Decimal(str(price))
            dto = LocalPaperFill(
                client_order_id=f"synthetic-{side}-{i}",
                market="US",
                symbol=f"S{i:04d}",
                side=side,
                quantity=quantities[i],
                price=price,
                fee=quantities[i] * price * cost,
                filled_at=when,
            )
            store.append(
                Event(
                    event_type="fill",
                    created_at=when,
                    payload={
                        "source": dto.source,
                        "client_order_id": dto.client_order_id,
                        "market": dto.market,
                        "symbol": dto.symbol,
                        "side": dto.side,
                        "quantity": str(dto.quantity),
                        "price": str(dto.price),
                        "fee": str(dto.fee),
                    },
                )
            )
            return dto.notional, dto.fee

        entries = [fill(i, "buy", opens[i], ENTRY) for i in held]
        entry_notional = sum((value for value, _ in entries), Decimal(0))
        entry_fee = sum((fee for _, fee in entries), Decimal(0))
        daily_cash, nav, inventory, exposure = [], [], [], []
        exit_notional = exit_fee = Decimal(0)
        for day in range(5):
            if day == 4:
                exits = [fill(i, "sell", closes[day, i], CLOSES[day]) for i in held]
                exit_notional = sum((value for value, _ in exits), Decimal(0))
                exit_fee = sum((fee for _, fee in exits), Decimal(0))
            account = replay_local_paper_account(store, starting_cash=cash)
            current = tuple(
                account.quantity(market="US", symbol=f"S{i:04d}") for i in range(len(weights))
            )
            marked = sum((current[i] * Decimal(str(closes[day, i])) for i in held), Decimal(0))
            assert account.cash >= 0
            inventory.append(current)
            daily_cash.append(account.cash)
            nav.append(account.cash + marked)
            exposure.append(marked / nav[-1])
        events = tuple(store.iter_events())
        assert all(event.payload["source"] == LOCAL_PAPER_SOURCE for event in events)
        realized = replay_local_paper_realized_pnl(events)
        assert not account.positions and realized.open_quantity == 0
        assert abs(account.cash - cash - realized.realized_after_cost_pnl) < Decimal("1e-40") * cash
        return {
            "entry_reference_nav": reference,
            "quantities": quantities,
            "daily_quantities": inventory,
            "cash": daily_cash,
            "daily_nav": nav,
            "entry_fee": entry_fee,
            "exit_fee": exit_fee,
            "fees": (entry_fee, 0, 0, 0, exit_fee),
            "turnover": (entry_notional + exit_notional) / cash,
            "daily_turnover": (entry_notional / cash, 0, 0, 0, exit_notional / cash),
            "daily_exposure": exposure,
        }


@pytest.mark.parametrize("bps", [5, 10, 20])
@pytest.mark.parametrize("capital", [1, 10000])
def test_512_exact_daily_accounting_fifo_actual_legs_and_overnight_gaps(tmp_path, bps, capital):
    held, opens, closes, weights = price_fixture()
    expected = canonical_accounting(tmp_path, held, opens, closes, weights, bps, capital)
    actual = core.replay_cohort(opens, closes, weights, bps, capital)
    assert actual.status == actual.reason == "complete"
    assert actual.missing_entries == 0 and actual.missing_marks == (0,) * 5
    for name, value in expected.items():
        np.testing.assert_allclose(
            np.asarray(getattr(actual, name), dtype=float),
            np.asarray(value, dtype=float),
            rtol=1e-13,
            atol=1e-14 * (1 if "exposure" in name else capital),
        )
    assert actual.daily_quantities[:4] == (actual.quantities,) * 4
    assert actual.daily_quantities[-1] == (0.0,) * 512
    assert actual.cash[-1] == actual.daily_nav[-1]
    assert max(actual.daily_exposure[:4]) > 0.5  # Entry caps do not force daily drift rebalancing.
    assert actual.entry_reference_nav == pytest.approx(capital / (1 + bps / 20000 * 0.5))
    assert np.dot(actual.quantities, np.nan_to_num(opens)) <= 0.5 * actual.entry_reference_nav


@pytest.mark.parametrize("bps", [5, 10, 20])
def test_cash_and_veto_slots_ignore_unselected_prices_no_redistribution(tmp_path, bps):
    held, opens, closes, weights = price_fixture()
    weights[128] = 0
    held.remove(128)
    opens[128] = np.nan
    closes[:, 128] = np.nan
    expected = canonical_accounting(tmp_path, held, opens, closes, weights, bps, 1)
    result = core.replay_cohort(opens, closes, weights, bps)
    np.testing.assert_allclose(
        result.quantities, np.asarray(expected["quantities"], dtype=float), rtol=1e-13, atol=1e-14
    )
    assert result.quantities[128] == 0
    assert sum(weights) == pytest.approx(0.4)
    cash = core.replay_cohort([np.nan], [[np.nan]] * 5, [0], bps)
    assert cash.status == "complete" and cash.daily_nav == cash.cash == (1.0,) * 5
    assert cash.fees == cash.daily_turnover == cash.daily_exposure == (0.0,) * 5


@pytest.mark.parametrize("day", range(5))
def test_missing_held_mark_preserves_slots_and_does_not_free_liquidate(day):
    _, opens, closes, weights = price_fixture()
    closes[day, 128] = np.nan
    result = core.replay_cohort(opens, closes, weights, 10)
    assert result.status == "input_unavailable" and result.daily_nav[day] is None
    assert result.missing_marks[day] == 1
    assert result.daily_quantities[day] == result.quantities
    if day == 4:
        assert result.exit_fee is result.turnover is result.daily_turnover[-1] is None
        assert result.daily_exposure[-1] is None and result.cash[-1] == result.cash[0]
    else:
        assert result.exit_fee > 0 and result.daily_quantities[-1] == (0.0,) * 512


def test_missing_selected_open_retains_unknown_not_cash_approval():
    _, opens, closes, weights = price_fixture()
    opens[4] = 0
    result = core.replay_cohort(opens, closes, weights, 10)
    assert result.status == "input_unavailable" and result.missing_entries == 1
    assert result.daily_nav == result.cash == result.fees == (None,) * 5
    assert result.quantities is result.entry_reference_nav is result.entry_fee is None


@pytest.mark.parametrize("weights", [[-0.01], [0.11], [np.nan], [np.inf], [0.1] * 6])
def test_no_negative_allocations_leverage_or_entry_cap_relaxation(weights):
    with pytest.raises(core.CohortError, match="entry_caps"):
        core.replay_cohort([10] * len(weights), [[10] * len(weights)] * 5, weights, 10)


@pytest.mark.parametrize("bps", [0, 11, 10.0, True])
def test_fixed_cost_band_not_silently_coerced(bps):
    with pytest.raises(core.CohortError, match="fixed_cost_band"):
        core.replay_cohort([10], [[10]] * 5, [0.1], bps)


def test_frame_factory_preserves_first_session_clocks_prior21_and_immutable_stamp():
    features, prices = feature_fixture()
    value = core.make_five_session_frame(
        index=720,
        feature_frame=features,
        prior_closes=PRIOR,
        prior_close_prices=prices,
        session_opens=OPENS,
        session_closes=CLOSES,
    )
    assert value.target_open == features.target_open
    assert value.target_close == CLOSES[-1] != features.target_close
    assert value.supported and np.all(value.volatility == 0.1)
    stamp = value.stamp
    features.tokens[:] = 2
    assert np.all(value.tokens == 0) and value.stamp == stamp
    for array in (value.tokens, value.eligible, value.momentum, value.volatility):
        with pytest.raises(ValueError):
            array.setflags(write=True)
    assert replace(value, feature_stamp="another-prior-frame").stamp != stamp
    assert replace(value, index=800).index == 800  # Dataset upper bounds belong to the caller.
    with pytest.raises(core.CohortError, match="first_session_feature_binding"):
        core.make_five_session_frame(
            index=720,
            feature_frame=replace(features, target_close=CLOSES[-1]),
            prior_closes=PRIOR,
            prior_close_prices=prices,
            session_opens=OPENS,
            session_closes=CLOSES,
        )


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"decision": ENTRY}, "causal_prior_clocks"),
        ({"decision": ENTRY.replace(tzinfo=None)}, "utc_clock"),
        ({"prior_closes": PRIOR[:-1]}, "five_session_geometry"),
        ({"prior_closes": (*PRIOR[:-1], ENTRY)}, "causal_prior_clocks"),
        (
            {"session_closes": (*CLOSES[:-1], CLOSES[-1] + timedelta(days=1))},
            "five_actual_session_clocks",
        ),
        ({"session_opens": (OPENS[0], OPENS[0], *OPENS[2:])}, "five_actual_session_clocks"),
    ],
)
def test_causal_and_five_actual_session_clock_kills(change, reason):
    with pytest.raises(core.CohortError, match=reason):
        replace(frame(), **change)


def test_original_first_support_membership_not_outcome_or_positional_replacement():
    value = frame()
    mask = np.zeros(512, dtype=bool)
    mask[:128] = True
    unsupported = replace(value, eligible=mask)
    assert not unsupported.supported
    assert not core.seal_policy(unsupported, policy="candidate").weights.any()
    mask[64:128] = False
    mask[128:192] = True
    assert replace(value, eligible=mask).supported


def test_top10_veto_cash_no_rerank_resize_or_replacement():
    momentum = np.full(512, -0.01)
    momentum[:9], momentum[9], momentum[10] = 0.10, 0.01, 0.009
    value = replace(frame(), momentum=momentum)
    candidate = core.seal_policy(value, policy="candidate")
    assert candidate.original_selected == tuple(range(10))
    assert candidate.weights[9] == candidate.weights[10] == 0
    np.testing.assert_allclose(candidate.weights[:9], 0.05)
    assert candidate.weights.sum() == pytest.approx(0.45)
    assert not candidate.weights.flags.writeable
    for policy in ("cash", "momentum", "ridge"):
        plan = core.seal_policy(value, policy=policy, ridge_scores=-np.arange(512))
        assert plan.weights.sum() == pytest.approx(0 if policy == "cash" else 0.5)


def test_inverse_volatility_clips_before_triangle_scale_and_veto():
    value = frame()
    volatility = np.full(512, 0.1)
    volatility[:10] = [0.1, 0.2, 0.3, 0.4, 0.5, 1, 2, 3, 4, 5]
    value = replace(value, volatility=volatility)
    result = core.seal_policy(value, policy="candidate")
    sigma = volatility[:10]
    original = np.minimum(0.1, 0.5 / sigma / sum(1 / sigma))
    expected = original * min(1, 0.08 / np.dot(original, sigma))
    np.testing.assert_allclose(result.weights[:10], expected, rtol=1e-14)
    assert result.weights.max() <= 0.1 and result.weights.sum() <= 0.5
    assert np.dot(result.weights, volatility) <= 0.08 + 1e-12


def test_labels_wait_for_fifth_close_and_missing_eligible_is_whole_date_unavailable():
    value = frame()
    with pytest.raises(core.CohortError, match="five_session_labels_not_completed"):
        core.make_labels(
            value, open_prices=np.ones(512), close_prices=np.ones((5, 512)), observed_at=CLOSES[0]
        )
    labels = core.make_labels(
        value,
        open_prices=np.full(512, 10),
        close_prices=np.full((5, 512), 11),
        observed_at=CLOSES[-1],
    )
    assert labels.complete and labels.exit_at == CLOSES[-1]
    np.testing.assert_allclose(labels.values, 11 * (1 - 0.0005) / (10 * (1 + 0.0005)) - 1)
    missing = np.ones((5, 512))
    missing[2, 511] = np.nan
    unavailable = core.make_labels(
        value, open_prices=np.ones(512), close_prices=missing, observed_at=CLOSES[-1]
    )
    assert not unavailable.complete and not unavailable.values.any()
    with pytest.raises(ValueError):
        labels.values.setflags(write=True)


def test_import_is_lazy_numpy_leaf_without_model_broker_or_training_imports():
    src = str(Path(__file__).resolve().parents[1] / "src")
    code = f"""
import sys
sys.path.insert(0, {src!r})
import thericher_v2.research
assert 'numpy' not in sys.modules
from thericher_v2.research import five_session_cohort
assert 'numpy' in sys.modules
for name in sys.modules:
    assert not name.startswith(('torch', 'sklearn', 'chronos', 'thericher_v2.execution'))
assert not hasattr(five_session_cohort, 'contract_binding')
"""
    completed = subprocess.run(
        [sys.executable, "-I", "-B", "-c", code],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr
