"""Synthetic public fixtures; real pure Data and integer accounting dependencies."""

from __future__ import annotations

import builtins
import socket
import urllib.request
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from thericher_v2.data.federal_reserve_h15 import H15Observation
from thericher_v2.data.h15_curve_state import H15CurveSnapshot
from thericher_v2.research import kis_lagged_rate_whole_share_policy_development as study
from thericher_v2.research import whole_share_portfolio_nav as ledger
from thericher_v2.research.cross_asset_etf_input import (
    CrossAssetInputUnavailable,
    CrossAssetSession,
)
from thericher_v2.research.cross_asset_hedge_failure_input import RawD1Price

D, VINTAGE = Decimal, "synthetic-raw-OC"
PRICE = D(103)
SPY_SCORES = (D(1), D(0), D(0), D(0))


def weekdays(start, count):
    days = []
    while len(days) < count:
        if start.weekday() < 5:
            days.append(start)
        start += timedelta(days=1)
    return days


def session(day):
    return CrossAssetSession(
        day, datetime.combine(day, time(14, 30), UTC), datetime.combine(day, time(21), UTC)
    )


@pytest.fixture(scope="module")
def plan():
    # Caller-attested synthetic geometry, not an NYSE completeness assertion.
    past = weekdays(date(2016, 2, 2), 300) + [date(2020, 12, 30), date(2020, 12, 31)]
    dev = weekdays(date(2021, 1, 4), 42) + [date(2023, 12, 29)]
    dev += weekdays(date(2024, 1, 2), 42) + [date(2026, 9, 30)]
    return study.build_plan(tuple(map(session, past + dev)))


def rows_for(sessions, price=PRICE):
    return {
        s: tuple(RawD1Price(s, d.session_date, VINTAGE, open=price, close=price) for d in sessions)
        for s in study.SYMBOLS
    }


def rates_for(plan):
    dates = sorted(
        {
            plan.sessions[i - 1].close_at.astimezone(ZoneInfo("America/New_York")).date()
            - timedelta(days=30)
            for i in plan.train_indices + plan.group_indices
        }
    )
    return H15CurveSnapshot(*(tuple(H15Observation(d, D(v)) for d in dates) for v in (1, 2, 3)))


def entry_for(plan, index, rows=None, rates=None):
    return study.prepare_entry(
        rows_for(plan.sessions) if rows is None else rows,
        plan=plan,
        entry_index=index,
        vintage_ref=VINTAGE,
        curve_snapshot=rates_for(plan) if rates is None else rates,
    )


def seal_for(plan, scores=SPY_SCORES):
    entries = {plan.sessions[i].session_date: entry_for(plan, i) for i in plan.group_indices}
    predictions = {p: {g[0]: scores for g in plan.groups} for p in study.CANDIDATES}
    return study.seal_actions(predictions, entries, plan=plan, vintage_ref=VINTAGE)


@pytest.fixture(autouse=True)
def no_external_effects(monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("pure campaign cannot perform IO, provider calls or fitting")

    monkeypatch.setattr(builtins, "open", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)


def test_static_recipe_geometry_and_no_new_family_budget(plan):
    config = study.configuration()
    assert config["cells"] == 54 and config["fits"] == study.FITS == 4
    assert config["seconds"] == 600 and config["costs_bps_side"] == ["2.5", "5", "10"]
    assert config["ridge"]["inputs"] == 381 and config["ridge"]["solver"] == "svd"
    assert config["gru"]["input_size"] == 6 and config["gru"]["head_inputs"] == 67
    assert config["gru"]["updates"] == 512 and "clone identical" in config["gru"]["initialization"]
    assert "state-omitted" in config["target_limitation"] and config["holdout"] == "none"
    assert not config["paper_input"] and "no rounding" in config["quote_grid"]
    assert plan.train_indices[0] == 253
    assert all(plan.sessions[i + 20].session_date <= date(2020, 12, 30) for i in plan.train_indices)
    assert any(g[0] <= date(2023, 12, 29) < g[-1] for g in plan.groups)
    assert plan.record()["tail_cash_days"] == 2
    with pytest.raises(CrossAssetInputUnavailable, match="train_warmup"):
        replace(plan, train_indices=(252,) + plan.train_indices)


def test_real_rates_selector_and_price_geometry_no_factor_stub(plan):
    entry = entry_for(plan, plan.train_indices[0])
    assert entry.rates3 == (D(2), D(2), D(0))
    assert entry.curve.factors_percent == (Fraction(2), Fraction(2), Fraction(0))
    assert entry.price.observation_dates == tuple(s.session_date for s in plan.sessions[190:253])
    assert tuple(entry.actions) == study.CONTROLS
    assert entry.actions["balanced"] == (Fraction(1, 3),) * 3
    assert "103" not in repr(entry) and entry.safe_facts()["price_shape"] == (6, 63)


def test_broad_calendar_warmup_counts_from_fixed_cohort_not_calendar_origin(plan):
    prefix = tuple(map(session, weekdays(date(2015, 1, 2), 50)))
    broad = study.build_plan(prefix + plan.sessions)
    assert broad.train_indices[0] == len(prefix) + 253
    assert broad.sessions[broad.train_indices[0] - 253].session_date == study.COHORT_START
    assert len(broad.train_indices) == len(plan.train_indices)


def test_future_prices_rates_presence_and_invalid_support_do_not_affect_past(plan):
    index = plan.train_indices[0]
    rows, rates = rows_for(plan.sessions), rates_for(plan)
    original = entry_for(plan, index, rows, rates)
    used = {s.session_date for s in plan.sessions[index - 253 : index]}
    changed = {
        s: tuple(
            r
            if r.session_date in used
            else SimpleNamespace(session_date=r.session_date, close="invalid", open="invalid")
            for r in column
        )
        for s, column in rows.items()
    }
    future = date(2030, 1, 1)
    changed_rates = H15CurveSnapshot(
        *(
            column + (H15Observation(future, D("NaN")),)
            for column in (rates.three_month, rates.two_year, rates.ten_year)
        )
    )
    assert entry_for(plan, index, changed, changed_rates) == original
    assert (
        entry_for(
            plan,
            index,
            {s: tuple(r for r in c if r.session_date in used) for s, c in rows.items()},
            rates,
        )
        == original
    )


@pytest.mark.parametrize("fault", ["missing", "duplicate", "off_cent", "vintage"])
def test_required_covariance_past_fault_cannot_use_shorter_price_context(plan, fault):
    rows = {s: list(c) for s, c in rows_for(plan.sessions).items()}
    if fault == "missing":
        rows["TLT"].pop(0)
    elif fault == "duplicate":
        rows["TLT"].append(rows["TLT"][0])
    elif fault == "off_cent":
        rows["TLT"][0] = replace(rows["TLT"][0], close=D("103.001"))
    else:
        rows["TLT"][0] = replace(rows["TLT"][0], vintage_ref="other")
    with pytest.raises(CrossAssetInputUnavailable):
        entry_for(plan, plan.train_indices[0], rows)


def test_rates_unavailable_is_scoped_not_price_arm_row_deletion(plan):
    empty = H15CurveSnapshot((), (), ())
    with pytest.raises(CrossAssetInputUnavailable, match="rate_state_unavailable"):
        entry_for(plan, plan.train_indices[0], rates=empty)


def test_covariance_is_once_shrunk_population_on_252_prior_returns(plan):
    rows = {
        s: tuple(replace(r, close=D(100) + D(i % (j + 3)) / 100) for i, r in enumerate(column))
        for j, (s, column) in enumerate(rows_for(plan.sessions).items())
    }
    entry = entry_for(plan, plan.train_indices[0], rows)
    closes = np.asarray([[float(r.close) for r in rows[s][:253]] for s in study.SYMBOLS]).T
    returns = np.asarray(
        [
            [
                float(Fraction(rows[s][i + 1].close) / Fraction(rows[s][i].close) - 1)
                for s in study.SYMBOLS
            ]
            for i in range(252)
        ]
    )
    assert closes.shape == (253, 3)
    raw = study._population_covariance(returns)
    expected = 0.9 * raw + 0.1 * np.diag(np.diag(raw))
    assert entry.covariance3 == tuple(tuple(Fraction(float(v)) for v in r) for r in expected)


def test_common_risk_scaling_is_capped_not_renormalized(plan):
    entry = entry_for(plan, plan.train_indices[0])
    c = tuple(
        tuple(Fraction(1, 100) if i == j else Fraction(0) for j in range(3)) for i in range(3)
    )
    scaled = replace(entry, covariance3=c, actions=study._scaled_actions(c))
    for weights in scaled.actions.values():
        variance = 252 * sum(weights[i] * c[i][j] * weights[j] for i in range(3) for j in range(3))
        assert variance <= Fraction(1, 100) and sum(weights) < 1
    assert len(set(scaled.actions["balanced"])) == 1


@pytest.mark.parametrize(
    "scores,action",
    [
        ((D(0),) * 4, "cash"),
        ((D(-1),) * 4, "cash"),
        ((D(1),) * 4, "spy"),
        ((D(-1), D(1), D(1), D(1)), "spy_tlt"),
        ((D(-1), D(-1), D(1), D(1)), "spy_gld"),
    ],
)
def test_four_head_ties_cash_first(scores, action):
    assert study.select_action(scores) == action


@pytest.mark.parametrize("scores", [(D(0),) * 3, (0.0,) * 4, (D("NaN"),) * 4])
def test_bad_scores_not_coerced_to_cash(scores):
    with pytest.raises(CrossAssetInputUnavailable, match="prediction_invalid"):
        study.select_action(scores)


def test_paired_train_scaler_final_rates_zero_slots_and_dev_no_fit(plan):
    first = entry_for(plan, plan.train_indices[0])
    second = entry_for(plan, plan.train_indices[1])
    dev = entry_for(plan, plan.group_indices[0])
    scaled = study.standardize((first, second), (dev,))
    price_x, price_dev = scaled.ridge_inputs(augmented=False)
    rate_x, rate_dev = scaled.ridge_inputs(augmented=True)
    assert price_x.shape == rate_x.shape == (2, 381)
    np.testing.assert_array_equal(price_x[:, :378], rate_x[:, :378])
    np.testing.assert_array_equal(price_dev[:, :378], rate_dev[:, :378])
    assert not price_x[:, 378:].any() and not price_dev[:, 378:].any()
    assert (scaled.rate_divisor == 1).all() and not scaled.train_rates.flags.writeable
    altered_price = replace(dev.price, features=((D(999),) * 63,) * 6)
    changed = study.standardize((first, second), (replace(dev, price=altered_price),))
    np.testing.assert_array_equal(scaled.price_mean, changed.price_mean)
    np.testing.assert_array_equal(scaled.train_price, changed.train_price)


def test_real_integer_episode_target_not_fractional_endpoint_label(plan):
    i = plan.train_indices[0]
    entry = entry_for(plan, i)
    rows = rows_for(plan.sessions)
    target = study.prepare_train_targets(
        rows, plan=plan, entry_index=i, vintage_ref=VINTAGE, entry=entry
    )
    forward = plan.sessions[i : i + 21]
    days = tuple(
        ledger.WholeShareDay(s.session_date, (D(103),) * 3, (D(103),) * 3) for s in forward
    )
    for j, name in enumerate(study.HEADS):
        trace = ledger.replay(
            days,
            {days[0].date: entry.actions[name]},
            D(5),
            initial_state=study._initial(ledger),
            liquidate_last_close=True,
        )
        assert target.utilities[j] == D(
            study._metrics(tuple(d.mark.net_nav for d in trace.daily), study.BANK)["utility"]
        )
        assert trace.final_state.quantities3 == (0, 0, 0)
        assert trace.total_fees == Fraction(5, 10000) * trace.total_traded_notional
    assert target.cash_utility == 0 and "utilities=" not in repr(target)
    assert target.safe_facts()["state_omitted"]


def test_full_bank_fee_rejection_remains_zero_trade_not_clipped(plan):
    i = plan.train_indices[0]
    rows = rows_for(plan.sessions, D(100))
    entry = entry_for(plan, i, rows)
    target = study.prepare_train_targets(
        rows, plan=plan, entry_index=i, vintage_ref=VINTAGE, entry=entry
    )
    assert target.utilities[0] == target.cash_utility == 0
    direct = ledger.rebalance_open(
        study._initial(ledger), (D(100),) * 3, entry.actions["spy"], D(5)
    )
    assert direct.status == "no_intent" and direct.reason == "analytical_cash_negative"
    assert direct.state == study._initial(ledger) and direct.fees == 0


def test_target_all_close_path_required_unused_intermediate_opens_ignored(plan):
    i = plan.train_indices[0]
    entry, rows = entry_for(plan, i), rows_for(plan.sessions)
    expected = study.prepare_train_targets(
        rows, plan=plan, entry_index=i, vintage_ref=VINTAGE, entry=entry
    )
    changed = {
        s: tuple(
            replace(r, open=None)
            if r.session_date in {d.session_date for d in plan.sessions[i + 1 : i + 21]}
            else r
            for r in c
        )
        for s, c in rows.items()
    }
    assert (
        study.prepare_train_targets(
            changed, plan=plan, entry_index=i, vintage_ref=VINTAGE, entry=entry
        )
        == expected
    )
    changed["GLD"] = tuple(
        r for r in changed["GLD"] if r.session_date != plan.sessions[i + 10].session_date
    )
    with pytest.raises(CrossAssetInputUnavailable, match="required_session_missing"):
        study.prepare_train_targets(
            changed, plan=plan, entry_index=i, vintage_ref=VINTAGE, entry=entry
        )


def test_seal_rejects_arbitrary_controls_and_is_immutable(plan):
    seal = seal_for(plan)
    changed = {p: dict(v) for p, v in seal.actions.items()}
    changed["cash"][plan.groups[0][0]] = (Fraction(1), Fraction(0), Fraction(0))
    with pytest.raises(CrossAssetInputUnavailable, match="action_binding"):
        replace(seal, actions=changed)
    with pytest.raises(TypeError):
        seal.actions["cash"][plan.groups[0][0]] = (Fraction(1),) * 3


def test_actual_ledger_54_cells_continuous_cash_and_group_crossing_view(plan):
    seal = seal_for(plan)
    days = study.prepare_marks(rows_for(plan.sessions), plan=plan, vintage_ref=VINTAGE)
    cells = study.evaluate(days, seal)
    assert len(cells) == 54
    selected = {(c["policy"], c["cost_bps"], c["view"]): c for c in cells}
    assert selected["cash", "10", 0]["metrics"]["growth"] == "0"
    state, navs = study._initial(ledger), []
    for start in range(0, 84, 21):
        block = days[start : start + 21]
        result = ledger.replay(
            block,
            {block[0].date: seal.actions["ridge_price"][block[0].date]},
            D(10),
            initial_state=state,
            liquidate_last_close=True,
        )
        state = result.final_state
        navs.extend(d.mark.net_nav for d in result.daily)
        assert state.basis_usd == study.BASIS and state.allocated_usd == study.BANK
    tail = ledger.replay(days[84:], {}, D(10), initial_state=state, liquidate_last_close=True)
    assert tail.total_fees == 0 and tail.final_state == state
    navs.extend(d.mark.net_nav for d in tail.daily)
    assert selected["ridge_price", "10", 1]["metrics"] == study._metrics(tuple(navs[43:]), navs[42])
    assert study.criterion(cells) == dict(ridge_rates="rejected", gru_rates="rejected")


def fake_cells():
    return [
        dict(
            policy=p,
            cost_bps=str(c),
            view=v,
            metrics=dict(growth=".1", utility="1" if p.endswith("rates") else "0"),
        )
        for p in study.POLICIES
        for c in study.COSTS
        for v in (0, 1)
    ]


@pytest.mark.parametrize("failure", ["growth", "matched", "control", "tolerance"])
def test_original_augmentation_kill_not_other_candidate_dominance(failure):
    cells = fake_cells()
    assert study.criterion(cells) == dict(
        ridge_rates="survived_development", gru_rates="survived_development"
    )
    cell = next(
        c for c in cells if (c["policy"], c["cost_bps"], c["view"]) == ("ridge_rates", "10", 1)
    )
    if failure == "growth":
        cell["metrics"]["growth"] = "0"
    elif failure == "tolerance":
        cell["metrics"]["utility"] = "1e-10"
    else:
        name = "ridge_price" if failure == "matched" else "balanced"
        next(c for c in cells if (c["policy"], c["cost_bps"], c["view"]) == (name, "10", 1))[
            "metrics"
        ]["utility"] = "1"
    assert study.criterion(cells)["ridge_rates"] == "rejected"


def test_exact_cells_and_hostile_context_metrics():
    cells = fake_cells()
    with pytest.raises(CrossAssetInputUnavailable, match="cell_matrix"):
        study.criterion(cells[:-1] + [cells[0]])
    before = study._metrics((Fraction(9999), Fraction(10001)), study.BANK)
    with localcontext() as context:
        context.prec = 2
        assert study._metrics((Fraction(9999), Fraction(10001)), study.BANK) == before
