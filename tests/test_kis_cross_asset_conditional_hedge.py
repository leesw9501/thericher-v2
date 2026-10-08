"""Synthetic-only conditional-hedge preparation; no fitting or source values."""

from __future__ import annotations

import builtins
import json
import os
import socket
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction
from types import SimpleNamespace

import pytest

from thericher_v2.research import kis_cross_asset_conditional_hedge as study
from thericher_v2.research import kis_cross_asset_relative_allocation as base
from thericher_v2.research import three_asset_nav as nav
from thericher_v2.research.cross_asset_daily_risk_input import DailyRiskFeatures
from thericher_v2.research.cross_asset_etf_input import CrossAssetInputUnavailable
from thericher_v2.research.cross_asset_hedge_failure_input import RawD1Price

D, VINTAGE = Decimal, "synthetic-conditional-hedge"
TLT_HEDGE_SCORES = (D(0), D(1), D(0), D(0))


def session(day, close_hour=21):
    return study.CrossAssetSession(day, datetime.combine(day, time(14, 30), UTC),
                                   datetime.combine(day, time(close_hour), UTC))


def weekdays(start, count):
    result = []
    while len(result) < count:
        if start.weekday() < 5:
            result.append(start)
        start += timedelta(days=1)
    return result


@pytest.fixture(scope="module")
def plan():
    # Deliberately synthetic caller calendar, not the measured NYSE geometry.
    history = weekdays(date(2016, 1, 4), 100) + [base.MATURITY_DAY, base.FIRST_DECISION]
    dev = weekdays(base.DEV_START, 42) + [base.VIEW_END]
    dev += weekdays(date(2024, 1, 2), 22) + [base.DEV_END]
    return study.build_plan(tuple(map(session, history + dev)))


def rows_for(sessions):
    return {s: tuple(RawD1Price(s, d.session_date, VINTAGE, open=D(100), close=D(100))
                     for d in sessions) for s in study.SYMBOLS}


def features_for(plan):
    return {plan.sessions[i].session_date: DailyRiskFeatures(
        plan.sessions[i - 1].close_at, plan.sessions[i].open_at,
        tuple(s.session_date for s in plan.sessions[i - 63:i]), ((D(0),) * 63,) * 6, VINTAGE,
    ) for i in plan.group_indices}


def seal_for(plan, scores=TLT_HEDGE_SCORES):
    predictions = {p: {g[0]: scores for g in plan.groups} for p in study.CANDIDATES}
    return study.prepare_actions(predictions, features_for(plan), plan=plan, vintage_ref=VINTAGE)


def marks(plan):
    return tuple(nav.ThreeAssetDay(d, (D(100),) * 3, (D(100),) * 3) for d in plan.dates)


def test_configuration_new_semantics_and_exact_recipe():
    c = study.configuration()
    assert c["name"] != base.NAME and c["semantic_identity"].startswith("conditional")
    assert c["dataset"]["sha256"] == study.INPUT_SHA256
    assert c["dataset"]["commitment_id"] == study.COMMITMENT_ID
    assert c["preparation_only"] and not c["paper_input"] and c["holdout"] == "none"
    assert c["cells"] == 7 * 3 * 2 == 42 and c["fits"] == 2 and c["seconds"] == 300
    assert c["ridge"] == dict(alpha=1, fit_intercept=True, solver="svd",
                              inputs="flattened6x63", output_size=4)
    assert c["gru"]["output_size"] == 4 and c["gru"]["hidden_size"] == 64
    assert c["gru"]["seed"] == 101 and c["gru"]["updates"] == 1024
    assert "5bps/side" in c["target"] and "not additive" in c["accounting"]
    assert "growth/utility improvement" not in c["kill"]
    assert "utility improvement>1e-10" in c["kill"]
    assert "not a dominance" in c["relative_growth"]
    assert json.loads(json.dumps(c))["heads"] == list(study.HEADS)


def test_original_plan_features_scaler_and_replay_reused_unchanged():
    assert study.AllocationPlan is base.AllocationPlan
    assert study.build_plan is base.build_plan and study.prepare_features is base.prepare_features
    assert study.prepare_entry_features is base.prepare_entry_features
    assert study.standardize is base.standardize and study.replay_groups is base.replay_groups


def test_exact_action_table_equal_thirds_and_cash_residual():
    table = study.action_table()
    assert tuple(table) == study.CONTROLS
    assert table["spy"].weights3 == (D(1), D(0), D(0))
    assert table["spy_tlt"].weights3 == (D(".5"), D(".5"), D(0))
    assert table["spy_gld"].weights3 == (D(".5"), D(0), D(".5"))
    assert table["balanced"].weights3 == (base.THIRD,) * 3
    assert table["balanced"].cash_weight > 0
    assert table["cash"].cash_weight == 1
    for t in table.values():
        assert sum(map(Fraction, t.weights3), Fraction(0)) + Fraction(t.cash_weight) == 1
    with pytest.raises(TypeError):
        table["cash"] = table["spy"]


@pytest.mark.parametrize("scores,name", [
    ((D(0),) * 4, "cash"), ((D(-1),) * 4, "cash"),
    ((D(1),) * 4, "spy"), ((D(-1), D(1), D(1), D(1)), "spy_tlt"),
    ((D(-1), D(-2), D(1), D(1)), "spy_gld"),
    ((D(0), D(0), D(0), D("1e-100")), "balanced"),
])
def test_four_scores_cash_zero_strict_ties_and_no_noise(scores, name):
    assert study.select_action(scores) == study.action_table()[name]
    assert study.TIE_ORDER == ("cash", "spy", "spy_tlt", "spy_gld", "balanced")


@pytest.mark.parametrize("scores", [
    (D(0),) * 3, (D(0),) * 5, [D(0)] * 4, (0.0,) * 4,
    (D("NaN"), D(0), D(0), D(0)), (D("Infinity"), D(0), D(0), D(0)),
])
def test_wrong_scores_not_clipped_or_rescued_as_cash(scores):
    with pytest.raises(CrossAssetInputUnavailable):
        study.select_action(scores)


def test_target_is_exact_full_ledger_utility_not_endpoint_log_factor(plan):
    i = plan.train_indices[0]
    forward = plan.sessions[i:i + 21]
    rows = rows_for(forward)
    target = study.prepare_train_target(rows, plan=plan, entry_index=i, vintage_ref=VINTAGE)
    days = tuple(nav.ThreeAssetDay(s.session_date, (D(100),) * 3, (D(100),) * 3) for s in forward)
    for j, name in enumerate(study.HEADS):
        trace = nav.replay(days, {forward[0].session_date: study.action_table()[name]}, D(5))
        assert target.utilities[j] == D(base._metrics(trace.daily, D(1))["utility"])
        assert target.net_factors[j] == trace.final_nav
        assert trace.daily[0].fees > 0 and trace.daily[-1].fees > 0
        assert trace.daily[0].log_return < 0 and trace.daily[-1].log_return < 0
    assert target.cash_utility == 0 and all(u < 0 for u in target.utilities)
    assert study.select_action(target.utilities) == study.action_table()["cash"]
    assert "utilities=" not in repr(target) and "net_factors=" not in repr(target)
    assert "label_only" in target.safe_facts()["normalized_episode"]


def test_same_endpoint_different_midpath_changes_utility(plan):
    forward = plan.sessions[plan.train_indices[0]:plan.train_indices[0] + 21]
    rows = rows_for(forward)
    before = study.build_utility_target(rows, scheduled_forward=forward, vintage_ref=VINTAGE)
    changed = {s: list(r) for s, r in rows.items()}
    changed["SPY"][8] = replace(changed["SPY"][8], close=D(120))
    after = study.build_utility_target(changed, scheduled_forward=forward, vintage_ref=VINTAGE)
    assert before.net_factors == after.net_factors
    assert all(after.utilities[j] < before.utilities[j] for j in range(4))


def test_target_all_closes_mandatory_unused_opens_and_future_irrelevant(plan):
    forward = plan.sessions[plan.train_indices[0]:plan.train_indices[0] + 21]
    rows = rows_for(forward)
    original = study.build_utility_target(rows, scheduled_forward=forward, vintage_ref=VINTAGE)
    changed = {s: (r[0],) + tuple(replace(x, open=None) for x in r[1:])
               + (SimpleNamespace(session_date=base.DEV_END, close="invalid"),)
               for s, r in rows.items()}
    assert study.build_utility_target(changed, scheduled_forward=forward, vintage_ref=VINTAGE) == (
        original)
    changed["TLT"] = changed["TLT"][:9] + changed["TLT"][10:]
    with pytest.raises(CrossAssetInputUnavailable, match="required_session_missing"):
        study.build_utility_target(changed, scheduled_forward=forward, vintage_ref=VINTAGE)


@pytest.mark.parametrize("fault", ["duplicate", "vintage", "basis", "close", "entry_open"])
def test_required_target_fault_no_fallback(plan, fault):
    forward = plan.sessions[plan.train_indices[0]:plan.train_indices[0] + 21]
    rows = {s: list(r) for s, r in rows_for(forward).items()}
    if fault == "duplicate":
        rows["GLD"].append(rows["GLD"][10])
    else:
        index = 0 if fault == "entry_open" else 10
        row = replace(rows["GLD"][index])
        attribute, value = {"vintage": ("vintage_ref", "other"),
                            "basis": ("price_basis", "adjusted"),
                            "close": ("close", None), "entry_open": ("open", None)}[fault]
        object.__setattr__(row, attribute, value)
        rows["GLD"][index] = row
    with pytest.raises(CrossAssetInputUnavailable):
        study.build_utility_target(rows, scheduled_forward=forward, vintage_ref=VINTAGE)


def test_target_train_scope_maturity_and_calendar_shape(plan):
    cutoff = plan.sessions[plan.dev_indices[0] - 2].close_at
    assert all(plan.sessions[i + 20].close_at <= cutoff for i in plan.train_indices)
    with pytest.raises(CrossAssetInputUnavailable, match="target_not_train"):
        study.prepare_train_target({}, plan=plan, entry_index=plan.group_indices[0],
                                   vintage_ref=VINTAGE)
    forward = plan.sessions[plan.train_indices[0]:plan.train_indices[0] + 21]
    with pytest.raises(CrossAssetInputUnavailable, match="target_calendar"):
        study.build_utility_target({}, scheduled_forward=forward[:-1], vintage_ref=VINTAGE)


def test_past_only_features_ignore_future_support_and_values(plan):
    i = plan.group_indices[0]
    history = plan.sessions[i - 64:i]
    rows = rows_for(history)
    before = study.prepare_entry_features(rows, plan=plan, entry_index=i, vintage_ref=VINTAGE)
    extra = (SimpleNamespace(session_date=plan.sessions[i].session_date, open="invalid"),
             SimpleNamespace(session_date=base.DEV_END, close=None))
    changed = {s: tuple(reversed(r)) + extra * 2 for s, r in rows.items()}
    assert study.prepare_entry_features(changed, plan=plan, entry_index=i,
                                        vintage_ref=VINTAGE) == before
    assert before.features == ((D(0),) * 63,) * 6
    changed["SPY"] = changed["SPY"][1:]
    with pytest.raises(CrossAssetInputUnavailable, match="required_session_missing"):
        study.prepare_entry_features(changed, plan=plan, entry_index=i, vintage_ref=VINTAGE)


def test_early_close_clock_and_wrong_decision_rejected(plan):
    i = plan.group_indices[0]
    history = plan.sessions[i - 64:i]
    history = history[:-1] + (session(history[-1].session_date, close_hour=18),)
    feature = study.prepare_features(rows_for(history), scheduled_history=history,
                                     entry_session=plan.sessions[i],
                                     decision_at=history[-1].close_at,
                                     vintage_ref=VINTAGE)
    assert feature.decision_at.hour == 18
    with pytest.raises(CrossAssetInputUnavailable, match="decision_not_previous_close"):
        study.prepare_features(rows_for(history), scheduled_history=history,
                               entry_session=plan.sessions[i],
                               decision_at=history[-1].close_at - timedelta(minutes=1),
                               vintage_ref=VINTAGE)


def test_actions_fixed_all_controls_copied_immutable_and_cost_independent(plan):
    seal = seal_for(plan)
    table = study.action_table()
    for p in study.CONTROLS:
        assert set(seal.actions[p]) == {g[0] for g in plan.groups}
        assert all(t == table[p] for t in seal.actions[p].values())
    mutable = {p: dict(a) for p, a in seal.actions.items()}
    copied = study.HedgeActionSeal(plan, VINTAGE, mutable)
    mutable["ridge"].clear()
    assert len(copied.actions["ridge"]) == len(plan.groups)
    with pytest.raises(TypeError):
        seal.actions["ridge"][plan.groups[0][0]] = table["cash"]
    frozen = seal.record()
    with pytest.raises(CrossAssetInputUnavailable, match="forward_mark_gap"):
        study.evaluate(marks(plan)[:-1], seal)
    assert seal.record() == frozen


@pytest.mark.parametrize("fault", ["control", "candidate", "extra_key", "mixed_vintage"])
def test_action_constructor_and_feature_binding_reject_forged_inputs(plan, fault):
    seal = seal_for(plan)
    mutable = {p: dict(a) for p, a in seal.actions.items()}
    day = plan.groups[0][0]
    if fault == "mixed_vintage":
        features = features_for(plan)
        features[day] = replace(features[day], vintage_ref="other")
        predictions = {p: {g[0]: (D(0),) * 4 for g in plan.groups} for p in study.CANDIDATES}
        with pytest.raises(CrossAssetInputUnavailable, match="feature_binding"):
            study.prepare_actions(predictions, features, plan=plan, vintage_ref=VINTAGE)
        return
    if fault == "control":
        mutable["cash"][day] = study.action_table()["spy"]
    elif fault == "candidate":
        mutable["ridge"][day] = nav.ThreeAssetTarget((D(".2"), D(".8"), D(0)), D(0))
    else:
        mutable["ridge"][base.FIRST_DECISION] = study.action_table()["cash"]
    with pytest.raises(CrossAssetInputUnavailable):
        study.HedgeActionSeal(plan, VINTAGE, mutable)


def test_shared_capital_cross_view_hold_and_tail_never_reset(plan):
    seal, days = seal_for(plan), marks(plan)
    trace = study.replay_groups(days, seal.actions["gru"], plan=plan, cost_bps=D(5))
    unit = nav.replay(days[:21], {days[0].date: study.action_table()["spy_tlt"]}, D(5))
    with localcontext(base.CONTEXT):
        assert abs(trace.final_nav - unit.final_nav ** len(plan.groups)) < D("1e-43")
        assert abs(sum(trace.log_returns, D(0)) - trace.final_nav.ln()) < D("1e-43")
    assert not trace.daily[plan.block_cut - 1].flat
    assert trace.daily[plan.block_cut].fees == 0
    second_entry = next(r for r in trace.daily if r.date == plan.groups[1][0])
    assert second_entry.fees < trace.daily[0].fees
    assert all(r.flat and r.log_return == 0 for r in trace.daily[len(plan.groups) * 21:])
    assert trace.daily[-1].flat
    changed = list(days)
    changed[1] = replace(changed[1], adj_open3=(D(999),) * 3)
    assert study.replay_groups(changed, seal.actions["gru"], plan=plan, cost_bps=D(5)) == trace


def test_42_cells_exact_geometry_continuous_second_denominator_and_no_rescue(plan):
    seal, days = seal_for(plan), marks(plan)
    cells = study.evaluate(days, seal)
    assert len(cells) == 42
    assert {(c["block"], c["policy"], c["cost_bps"]) for c in cells} == {
        (b, p, str(cost)) for b in (0, 1) for p in study.POLICIES for cost in study.COSTS}
    trace = study.replay_groups(days, seal.actions["gru"], plan=plan, cost_bps=D(5))
    later = next(c for c in cells if (c["block"], c["policy"], c["cost_bps"]) == (1, "gru", "5"))
    assert later["metrics"] == base._metrics(trace.daily[plan.block_cut:],
                                              trace.daily[plan.block_cut - 1].nav)
    by_key = {(c["block"], c["policy"], c["cost_bps"]): c["metrics"] for c in cells}
    with localcontext(base.CONTEXT):
        for cell in cells:
            if cell["policy"] in study.CANDIDATES:
                controls = study.CONTROLS + (("ridge",) if cell["policy"] == "gru" else ())
                assert cell["control_relative_growth"] == {
                    p: str(D(cell["metrics"]["growth"])
                           - D(by_key[cell["block"], p, cell["cost_bps"]]["growth"]))
                    for p in controls}
    assert study.criterion(cells) == dict(ridge="rejected", gru="rejected")


def test_episode_utility_matches_same_hold_in_continuous_capital_not_a_new_nav1(plan):
    rows = {s: tuple(RawD1Price(s, d, VINTAGE, open=D(100 + i + 3 * k),
                               close=D(101 + i + 3 * k + (i % 3)))
                     for i, d in enumerate(plan.dates)) for k, s in enumerate(study.SYMBOLS)}
    days = study.prepare_marks(rows, plan=plan, vintage_ref=VINTAGE)
    sessions = {s.session_date: s for s in plan.sessions}
    labels = [study.build_utility_target(rows, scheduled_forward=tuple(sessions[d] for d in g),
                                         vintage_ref=VINTAGE) for g in plan.groups]
    with localcontext(base.CONTEXT):
        for head, name in enumerate(study.HEADS):
            actions = {g[0]: study.action_table()[name] for g in plan.groups}
            trace = study.replay_groups(days, actions, plan=plan, cost_bps=D(5))
            for index, label in enumerate(labels):
                start = index * 21
                episode = trace.daily[start:start + 21]
                entering = trace.daily[start - 1].nav if start else D(1)
                utility = D(base._metrics(episode, entering)["utility"])
                assert abs(utility - label.utilities[head]) < D("1e-43")
                assert abs(episode[-1].nav / entering - label.net_factors[head]) < D("1e-43")
            assert trace.daily[21].fees != trace.daily[0].fees


def good_cells():
    return [dict(block=b, policy=p, cost_bps=str(c),
                 metrics=dict(growth="3" if p == "gru" else "2" if p == "ridge" else "1",
                              utility="3" if p == "gru" else "2" if p == "ridge" else "1"))
            for b in (0, 1) for p in study.POLICIES for c in study.COSTS]


@pytest.mark.parametrize("candidate,block", [
    ("ridge", 0), ("ridge", 1), ("gru", 0), ("gru", 1),
])
def test_new_family_strict_utility_kill_both_views(candidate, block):
    cells = good_cells()
    assert study.criterion(cells) == dict(ridge="development_survivor", gru="development_survivor")
    cell = next(c for c in cells if (c["policy"], c["block"], c["cost_bps"]) == (
        candidate, block, "10"))
    cell["metrics"]["utility"] = "1.0000000001" if candidate == "ridge" else "2.0000000001"
    assert study.criterion(cells)[candidate] == "rejected"


@pytest.mark.parametrize("candidate", study.CANDIDATES)
def test_positive_growth_but_utility_inferior_rejects(candidate):
    cells = good_cells()
    for c in cells:
        if c["policy"] == candidate:
            c["metrics"] = dict(growth="100", utility="0.5")
    assert study.criterion(cells)[candidate] == "rejected"


@pytest.mark.parametrize("candidate", study.CANDIDATES)
def test_negative_growth_but_high_utility_rejects(candidate):
    cells = good_cells()
    for c in cells:
        if c["policy"] == candidate:
            c["metrics"] = dict(growth="-0.01", utility="100")
    assert study.criterion(cells)[candidate] == "rejected"


def test_lower_growth_than_spy_with_positive_growth_and_better_utility_can_screen():
    cells = good_cells()
    for c in cells:
        if c["policy"] in study.CANDIDATES:
            c["metrics"]["growth"] = "0.02" if c["policy"] == "ridge" else "0.01"
            # Deliberately hostile descriptive contrast must never become a kill input.
            c["control_relative_growth"] = dict(spy="-999")
        if c["policy"] == "cash":
            c["metrics"] = dict(growth="0", utility="0")
    assert study.criterion(cells) == dict(ridge="development_survivor", gru="development_survivor")
    assert not study.configuration()["paper_input"]
    assert study.configuration()["grade"] == "RELATED_SEEN_RAW_PRICE_ONLY_DEVELOPMENT"


def test_kill_positive_growth_strict_zero_and_no_matrix_or_numeric_fallback():
    cells = good_cells()
    for c in cells:
        c["metrics"]["growth"] = "1e-20" if c["policy"] in study.CANDIDATES else "-1"
    assert study.criterion(cells)["ridge"] == "development_survivor"
    next(c for c in cells if (c["policy"], c["block"], c["cost_bps"]) == (
        "ridge", 0, "10"))["metrics"]["growth"] = "0"
    assert study.criterion(cells)["ridge"] == "rejected"
    with pytest.raises(CrossAssetInputUnavailable, match="cell_matrix"):
        study.criterion(cells[:-1])
    cells[-1]["metrics"]["utility"] = "NaN"
    with pytest.raises(CrossAssetInputUnavailable, match="cell_metrics"):
        study.criterion(cells)


def test_target_and_replay_per_asset_scale_and_hostile_context(plan):
    forward = plan.sessions[plan.train_indices[0]:plan.train_indices[0] + 21]
    rows = rows_for(forward)
    before = study.build_utility_target(rows, scheduled_forward=forward, vintage_ref=VINTAGE)
    scale = dict(SPY=D(10), TLT=D(".01"), GLD=D(100))
    changed = {s: tuple(replace(r, open=r.open * scale[s], close=r.close * scale[s])
                         for r in rs) for s, rs in rows.items()}
    after = study.build_utility_target(changed, scheduled_forward=forward, vintage_ref=VINTAGE)
    assert after == before
    with localcontext() as c:
        c.prec = 6
        assert study.build_utility_target(rows, scheduled_forward=forward, vintage_ref=VINTAGE) == (
            before)
        assert study.action_table()["balanced"] == base.balanced_target()
        assert study.criterion(good_cells())["gru"] == "development_survivor"


def test_train_scaler_dev_mutation_zero_std_immutable_and_no_target_scaling():
    np = pytest.importorskip("numpy")
    train = np.arange(2 * 6 * 63, dtype=float).reshape(2, 6, 63)
    dev = np.ones((3, 6, 63))
    before, changed = study.standardize(train, dev), study.standardize(train, dev * 999)
    assert np.array_equal(before.train, changed.train)
    assert np.array_equal(before.mean, changed.mean)
    assert np.array_equal(before.divisor, changed.divisor)
    assert not before.train.flags.writeable and not before.mean.flags.writeable
    assert np.array_equal(study.standardize(np.zeros((1, 6, 63)), dev).divisor, np.ones(6))


def test_source_io_env_network_and_old_outcomes_not_reachable(plan, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("source IO/model/provider forbidden")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(base, "fit_ridge", forbidden)
    monkeypatch.setattr(base, "fit_gru", forbidden)
    monkeypatch.setattr(base, "prepare_actions", forbidden)
    monkeypatch.setattr(base, "criterion", forbidden)
    assert study.configuration()["fits"] == 2
    assert study.prepare_train_target(rows_for(plan.sessions), plan=plan,
                                      entry_index=plan.train_indices[0], vintage_ref=VINTAGE)
    assert len(study.evaluate(marks(plan), seal_for(plan))) == 42
