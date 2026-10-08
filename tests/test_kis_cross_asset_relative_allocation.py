"""Synthetic preparation only: no source loading, real fitting or CUDA access."""

from __future__ import annotations

import builtins
import json
import os
import socket
import sys
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, localcontext
from types import SimpleNamespace

import pytest

from thericher_v2.research import kis_cross_asset_relative_allocation as study
from thericher_v2.research import three_asset_nav as nav
from thericher_v2.research.cross_asset_daily_risk_input import DailyRiskFeatures
from thericher_v2.research.cross_asset_etf_input import CrossAssetInputUnavailable
from thericher_v2.research.cross_asset_hedge_failure_input import RawD1Price

D = Decimal
VINTAGE = "synthetic-new-cohort"
ZERO, ONE = D(0), D(1)
SPY_SCORES = (ONE, ZERO, ZERO)


def session(day, *, close_hour=21):
    return study.CrossAssetSession(
        day, datetime.combine(day, time(14, 30), UTC), datetime.combine(day, time(close_hour), UTC)
    )


def weekdays(start, count):
    result = []
    while len(result) < count:
        if start.weekday() < 5:
            result.append(start)
        start += timedelta(days=1)
    return result


@pytest.fixture(scope="module")
def full_plan():
    days = []
    day = date(2016, 1, 4)
    while day <= study.DEV_END:
        if day.weekday() < 5 and (day.month, day.day) != (1, 1):
            days.append(day)
        day += timedelta(days=1)
    # Synthetic caller calendar; this is not a measured NYSE/source geometry.
    return study.build_plan(tuple(map(session, days)))


@pytest.fixture(scope="module")
def plan():
    history = weekdays(date(2016, 1, 4), 100) + [study.MATURITY_DAY, study.FIRST_DECISION]
    dev = weekdays(study.DEV_START, 42) + [study.VIEW_END]
    dev += weekdays(date(2024, 1, 2), 22) + [study.DEV_END]
    return study.build_plan(tuple(map(session, history + dev)))


def rows_for(sessions, *, factor=ONE):
    return {
        s: tuple(
            RawD1Price(s, day.session_date, VINTAGE, open=factor * D(100), close=factor * D(100))
            for day in sessions
        )
        for s in study.SYMBOLS
    }


def synthetic_feature(plan, index, *, momentum=ZERO):
    return DailyRiskFeatures(
        plan.sessions[index - 1].close_at,
        plan.sessions[index].open_at,
        tuple(s.session_date for s in plan.sessions[index - 63 : index]),
        ((momentum,) * 63,) + ((D(0),) * 63,) * 5,
        VINTAGE,
    )


def seal_for(plan, *, scores=SPY_SCORES):
    features = {
        plan.sessions[i].session_date: synthetic_feature(plan, i) for i in plan.group_indices
    }
    predictions = {p: {g[0]: scores for g in plan.groups} for p in study.CANDIDATES}
    return study.prepare_actions(predictions, features, plan=plan, vintage_ref=VINTAGE)


def marks(plan):
    return tuple(nav.ThreeAssetDay(d, (D(100),) * 3, (D(100),) * 3) for d in plan.dates)


def test_static_contract_no_legacy_source_or_paper_qualification():
    config = study.configuration()
    assert config["dataset"]["identity"] is config["dataset"]["sha256"] is None
    assert not config["dataset"]["legacy_02dcc_input_allowed"]
    assert config["preparation_only"] and not config["paper_input"]
    assert config["cells"] == 42 and config["fits"] == 2 and config["seconds"] == 300
    assert config["gru"]["hidden_size"] == 64 and config["gru"]["updates"] == 1024
    assert "no centering" in config["target"]
    assert config["reference_only"] == "spy_buyhold"


def test_train_maturity_is_previous_session_not_first_decision(full_plan):
    cutoff = full_plan.sessions[full_plan.dev_indices[0] - 2]
    assert cutoff.session_date == date(2020, 12, 30)
    assert all(
        full_plan.sessions[i + 20].close_at <= cutoff.close_at for i in full_plan.train_indices
    )
    record = full_plan.record()
    assert record["first_dev_decision"].startswith("2020-12-31")
    assert record["independent_sample_count"] == "not_claimed"
    with pytest.raises(CrossAssetInputUnavailable, match="train_maturity"):
        replace(
            full_plan, train_indices=full_plan.train_indices + (full_plan.train_indices[-1] + 1,)
        )


def test_partition_once_across_year_views_and_cash_tail(full_plan):
    groups = full_plan.groups
    flattened = tuple(d for group in groups for d in group)
    assert flattened == full_plan.dates[: len(groups) * 21]
    assert any(g[0].year == 2023 and g[-1].year == 2024 for g in groups)
    assert len(full_plan.dates[len(flattened) :]) < 21
    assert full_plan.record()["tail_cash_days"] == len(full_plan.dates) % 21


def test_calendar_type_order_and_fixed_boundary_rejected(plan):
    with pytest.raises(CrossAssetInputUnavailable):
        study.build_plan(tuple(reversed(plan.sessions)))
    with pytest.raises(CrossAssetInputUnavailable, match="study_calendar"):
        replace(plan, block_cut=plan.block_cut + 1)
    with pytest.raises(CrossAssetInputUnavailable):
        study.build_plan(tuple(s for s in plan.sessions if s.session_date != study.FIRST_DECISION))


def test_features_ignore_current_future_values_duplicates_and_support(plan):
    i = plan.group_indices[0]
    history = plan.sessions[i - 64 : i]
    rows = rows_for(history)
    original = study.prepare_entry_features(rows, plan=plan, entry_index=i, vintage_ref=VINTAGE)
    assert original.features == ((D(0),) * 63,) * 6
    additions = (
        SimpleNamespace(session_date=plan.sessions[i].session_date, close="invalid"),
        SimpleNamespace(session_date=study.DEV_END, close=None),
    )
    changed = {s: tuple(reversed(r)) + additions * 2 for s, r in rows.items()}
    mutated = study.prepare_entry_features(changed, plan=plan, entry_index=i, vintage_ref=VINTAGE)
    assert mutated == original
    assert (
        study.prepare_entry_features(
            rows_for(history, factor=D(10)), plan=plan, entry_index=i, vintage_ref=VINTAGE
        ).features
        == original.features
    )


@pytest.mark.parametrize("fault", ["missing", "duplicate", "vintage", "close", "basis"])
def test_required_past_fault_is_scoped_not_older_fallback(plan, fault):
    i = plan.group_indices[0]
    history = plan.sessions[i - 64 : i]
    rows = {s: list(r) for s, r in rows_for(history).items()}
    if fault == "missing":
        rows["TLT"].pop(12)
    elif fault == "duplicate":
        rows["TLT"].append(rows["TLT"][12])
    else:
        row = replace(rows["TLT"][12])
        object.__setattr__(
            row,
            {"vintage": "vintage_ref", "close": "close", "basis": "price_basis"}[fault],
            {"vintage": "other", "close": None, "basis": "adjusted"}[fault],
        )
        rows["TLT"][12] = row
    with pytest.raises(CrossAssetInputUnavailable):
        study.prepare_entry_features(rows, plan=plan, entry_index=i, vintage_ref=VINTAGE)


def test_early_close_is_decision_clock_not_assumed_regular_close(plan):
    i = plan.group_indices[0]
    history = plan.sessions[i - 64 : i]
    last = session(history[-1].session_date, close_hour=18)
    history = history[:-1] + (last,)
    context = study.prepare_features(
        rows_for(history),
        scheduled_history=history,
        entry_session=plan.sessions[i],
        decision_at=last.close_at,
        vintage_ref=VINTAGE,
    )
    assert context.decision_at == last.close_at
    with pytest.raises(CrossAssetInputUnavailable, match="decision_not_previous_close"):
        study.prepare_features(
            rows_for(history),
            scheduled_history=history,
            entry_session=plan.sessions[i],
            decision_at=last.close_at - timedelta(1),
            vintage_ref=VINTAGE,
        )


def test_absolute_target_exact_ledger_cost_and_no_centering(plan):
    i = plan.train_indices[0]
    forward = plan.sessions[i : i + 21]
    rows = rows_for((forward[0], forward[-1]))
    target = study.prepare_train_target(rows, plan=plan, entry_index=i, vintage_ref=VINTAGE)
    with localcontext(study.CONTEXT):
        expected = (1 - D(".0005")) / (1 + D(".0005"))
        assert all(abs(f - expected) < D("1e-45") for f in target.net_factors)
    assert all(v < 0 for v in target.log_net_factors)
    assert study.absolute_action(target.log_net_factors).cash_weight == 1
    assert (
        study.build_absolute_target(
            rows_for((forward[0], forward[-1]), factor=D(10)),
            scheduled_forward=forward,
            vintage_ref=VINTAGE,
        ).net_factors
        == target.net_factors
    )
    assert "not_centered" in target.safe_facts()["target"]
    with pytest.raises(CrossAssetInputUnavailable, match="target_not_train"):
        study.prepare_train_target(
            {}, plan=plan, entry_index=plan.group_indices[0], vintage_ref=VINTAGE
        )


def test_target_missing_endpoint_cannot_substitute_or_drop_asset(plan):
    forward = plan.sessions[plan.train_indices[0] : plan.train_indices[0] + 21]
    rows = rows_for((forward[0], forward[-1]))
    rows["GLD"] = rows["GLD"][:1]
    with pytest.raises(CrossAssetInputUnavailable, match="required_session_missing"):
        study.build_absolute_target(rows, scheduled_forward=forward, vintage_ref=VINTAGE)


@pytest.mark.parametrize(
    "scores,index",
    [
        ((D(0),) * 3, None),
        ((D(-1), D(-2), D(-3)), None),
        ((D(1), D(1), D(1)), 0),
        ((D(-1), D(1), D(1)), 1),
        ((D(0), D(0), D("1e-30")), 2),
    ],
)
def test_absolute_cash_threshold_and_canonical_ties(scores, index):
    assert study.absolute_action(scores) == study.unit_target(index)


@pytest.mark.parametrize(
    "scores", [(D("NaN"), D(0), D(0)), (D("Infinity"), D(0), D(0)), (D(0), D(1)), (0.0, 1.0, 2.0)]
)
def test_bad_prediction_no_clipping_or_cash_rescue(scores):
    with pytest.raises(CrossAssetInputUnavailable):
        study.absolute_action(scores)


def test_seal_cost_independent_foreign_future_mark_gaps_cannot_change_actions(plan):
    seal = seal_for(plan)
    for day in seal.actions["group_spy"]:
        assert seal.actions["group_spy"][day] == study.unit_target(0)
        assert seal.actions["cash"][day] == study.unit_target()
        assert seal.actions["momentum63"][day] == study.unit_target()
    assert len(seal.actions[study.REFERENCE]) == 1
    with pytest.raises(TypeError):
        seal.actions["cash"][plan.groups[0][0]] = study.unit_target(0)
    before = {p: dict(t) for p, t in seal.actions.items()}
    with pytest.raises(CrossAssetInputUnavailable, match="forward_mark_gap"):
        study.evaluate(marks(plan)[:-1], seal)
    assert before == {p: dict(t) for p, t in seal.actions.items()}


def test_seal_does_not_accept_mixed_feature_cohort_or_wrong_decision(plan):
    features = {
        plan.sessions[i].session_date: synthetic_feature(plan, i) for i in plan.group_indices
    }
    predictions = {p: {g[0]: (D(0),) * 3 for g in plan.groups} for p in study.CANDIDATES}
    first = plan.groups[0][0]
    features[first] = replace(features[first], vintage_ref="another")
    with pytest.raises(CrossAssetInputUnavailable, match="feature_binding"):
        study.prepare_actions(predictions, features, plan=plan, vintage_ref=VINTAGE)


def test_mutable_actions_copied_and_forged_control_rejected(plan):
    original = seal_for(plan)
    mutable = {p: dict(t) for p, t in original.actions.items()}
    copied = study.ActionSeal(plan, VINTAGE, mutable)
    mutable["gru"].clear()
    assert len(copied.actions["gru"]) == len(plan.groups)
    mutable = {p: dict(t) for p, t in original.actions.items()}
    mutable["cash"][plan.groups[0][0]] = study.unit_target(0)
    with pytest.raises(CrossAssetInputUnavailable, match="policy_allocation"):
        study.ActionSeal(plan, VINTAGE, mutable)


@pytest.mark.parametrize("tail", [0, 1, 20])
def test_tail_calendar_cash_never_truncates_a_hold(plan, tail):
    history = plan.sessions[: plan.dev_indices[0]]
    dev = list(plan.dates[:-1])
    extra = (tail - (len(dev) + 1) % 21) % 21
    dev += weekdays(date(2025, 1, 2), extra)
    dev.append(study.DEV_END)
    changed = study.build_plan(history + tuple(map(session, dev)))
    assert len(changed.dates) % 21 == tail
    seal = seal_for(changed)
    replay = study.replay_groups(
        marks(changed), seal.actions["group_spy"], plan=changed, cost_bps=D(5)
    )
    if tail:
        assert all(
            row.flat and row.fees == 0 and row.log_return == 0 for row in replay.daily[-tail:]
        )
    assert replay.daily[-1].flat


def test_continuous_group_capital_matches_compounded_unit_factors(plan):
    seal, days = seal_for(plan), marks(plan)
    replay = study.replay_groups(days, seal.actions["group_spy"], plan=plan, cost_bps=D(5))
    forward = tuple(plan.sessions[i] for i in plan.dev_indices[:21])
    unit = study.build_absolute_target(
        rows_for((forward[0], forward[-1])), scheduled_forward=forward, vintage_ref=VINTAGE
    ).net_factors[0]
    with localcontext(study.CONTEXT):
        assert abs(replay.final_nav - unit ** len(plan.groups)) < D("1e-43")
        assert abs(sum(replay.log_returns, D(0)) - replay.final_nav.ln()) < D("1e-43")
    group_entry = plan.groups[1][0]
    row = next(r for r in replay.daily if r.date == group_entry)
    first_entry = replay.daily[0]
    assert row.fees < first_entry.fees  # Less net capital, not a fresh NAV1 sleeve.
    assert all(r.flat and r.log_return == 0 for r in replay.daily[len(plan.groups) * 21 :])
    assert replay.daily[-1].flat


def test_no_midgroup_open_rebalance_and_cross_view_position_not_reset(plan):
    seal, days = seal_for(plan), list(marks(plan))
    original = study.replay_groups(days, seal.actions["group_spy"], plan=plan, cost_bps=D(5))
    days[1] = replace(days[1], adj_open3=(D(999),) * 3)
    changed = study.replay_groups(days, seal.actions["group_spy"], plan=plan, cost_bps=D(5))
    assert changed == original
    crossing = next(g for g in plan.groups if g[0] <= plan.dates[plan.block_cut - 1] < g[-1])
    assert not original.daily[plan.block_cut - 1].flat
    assert original.daily[plan.block_cut].fees == 0
    assert crossing[-1] > plan.dates[plan.block_cut]


def test_42_cells_views_use_matching_entering_nav_and_reference_path(plan):
    seal, days = seal_for(plan), marks(plan)
    cells = study.evaluate(days, seal)
    assert len(cells) == 42
    assert {(c["block"], c["policy"], c["cost_bps"]) for c in cells} == {
        (b, p, str(c)) for b in (0, 1) for p in study.POLICIES for c in study.COSTS
    }
    replay = study.replay_groups(days, seal.actions["gru"], plan=plan, cost_bps=D(5))
    later = next(c for c in cells if (c["block"], c["policy"], c["cost_bps"]) == (1, "gru", "5"))
    with localcontext(study.CONTEXT):
        assert (
            D(later["metrics"]["growth"])
            == replay.final_nav / replay.daily[plan.block_cut - 1].nav - 1
        )
    reference = nav.replay(days, seal.actions[study.REFERENCE], D(5))
    assert replay.final_nav < reference.final_nav
    assert study.criterion(cells) == dict(ridge="rejected", gru="rejected")


def good_cells():
    return [
        dict(
            block=b,
            policy=p,
            cost_bps=str(c),
            metrics=dict(
                growth="1e-20" if p in study.CANDIDATES else "100",
                utility="3"
                if p == "gru"
                else "2"
                if p == "ridge"
                else "999"
                if p == study.REFERENCE
                else "1",
            ),
        )
        for b in (0, 1)
        for p in study.POLICIES
        for c in study.COSTS
    ]


def test_public_criteria_noncyclic_utility_not_wealth_or_reference_dominance():
    cells = good_cells()
    assert study.criterion(cells) == dict(ridge="development_survivor", gru="development_survivor")
    for cell in cells:
        if cell["policy"] == "gru" and cell["block"] == 1 and cell["cost_bps"] == "10":
            cell["metrics"]["utility"] = "2.0000000001"
    assert study.criterion(cells) == dict(ridge="development_survivor", gru="rejected")
    for cell in cells:
        if cell["policy"] == "ridge" and cell["block"] == 0 and cell["cost_bps"] == "10":
            cell["metrics"]["growth"] = "0"
    assert study.criterion(cells)["ridge"] == "rejected"
    with pytest.raises(CrossAssetInputUnavailable, match="cell_matrix"):
        study.criterion(cells[:-1])


def test_hostile_decimal_context_does_not_change_targets_replay_or_criterion(plan):
    seal, days = seal_for(plan), marks(plan)
    original = study.replay_groups(days, seal.actions["group_spy"], plan=plan, cost_bps=D(5))
    with localcontext() as context:
        context.prec = 6
        assert study.balanced_target().weights3 == (study.THIRD,) * 3
        assert (
            study.replay_groups(days, seal.actions["group_spy"], plan=plan, cost_bps=D(5))
            == original
        )
        assert study.criterion(good_cells())["gru"] == "development_survivor"


def test_price_scale_and_missing_mandatory_daily_marks(plan):
    seal, days = seal_for(plan), marks(plan)
    original = study.replay_groups(days, seal.actions["group_spy"], plan=plan, cost_bps=D(5))
    scaled = tuple(
        replace(
            d,
            adj_open3=tuple(v * D(10) for v in d.adj_open3),
            adj_close3=tuple(v * D(10) for v in d.adj_close3),
        )
        for d in days
    )
    assert (
        study.replay_groups(scaled, seal.actions["group_spy"], plan=plan, cost_bps=D(5)).navs
        == original.navs
    )
    with pytest.raises(CrossAssetInputUnavailable, match="forward_mark_gap"):
        study.replay_groups(
            days[:3] + days[4:], seal.actions["group_spy"], plan=plan, cost_bps=D(5)
        )


def test_scaler_train_only_future_mutation_zero_variance_and_private_repr():
    np = pytest.importorskip("numpy")
    train = np.arange(2 * 6 * 63, dtype=float).reshape(2, 6, 63)
    dev = np.ones((3, 6, 63))
    before, after = study.standardize(train, dev), study.standardize(train, dev * 999)
    assert np.array_equal(before.train, after.train)
    assert np.array_equal(before.mean, after.mean) and np.array_equal(before.divisor, after.divisor)
    zero = study.standardize(np.zeros((1, 6, 63)), dev)
    assert np.array_equal(zero.divisor, np.ones(6))
    assert not before.train.flags.writeable and not before.mean.flags.writeable
    assert "mean=" not in repr(before) and "train=" not in repr(before)


def test_cpu_gru_forward_absolute_three_outputs_no_softmax_or_fit():
    torch = pytest.importorskip("torch")
    model = study.make_gru()
    with torch.no_grad():
        model.output.weight.zero_()
        model.output.bias.fill_(-1)
        result = model(torch.zeros((2, 6, 63)))
    assert result.shape == (2, 3) and torch.all(result == -1)
    assert model.encoder.hidden_size == 64 and model.encoder.num_layers == 1


def test_mock_ridge_completion_record_survives_postfit_prediction_failure(monkeypatch):
    np = pytest.importorskip("numpy")
    events = []

    class FakeRidge:
        def __init__(self, **kwargs):
            assert kwargs == dict(alpha=1, fit_intercept=True, solver="svd")

        def fit(self, x, y):
            assert x.shape == (2, 378) and y.shape == (2, 3)
            return self

        def predict(self, x):
            raise RuntimeError("synthetic-postfit-failure")

    monkeypatch.setitem(sys.modules, "sklearn.linear_model", SimpleNamespace(Ridge=FakeRidge))
    with pytest.raises(RuntimeError, match="synthetic-postfit"):
        study.fit_ridge(
            np.zeros((2, 6, 63)),
            np.zeros((2, 3)),
            np.zeros((1, 6, 63)),
            progress=lambda *e: events.append(e),
        )
    assert events == [("ridge", "started", 0), ("ridge", "completed", 1)]


@pytest.mark.parametrize("postfit_fault", [False, True])
def test_fake_cuda_recipe_updates_and_immediate_completion_no_real_fit(monkeypatch, postfit_fault):
    np = pytest.importorskip("numpy")
    events, steps, syncs = [], [], []

    class Tensor:
        def __sub__(self, other):
            return self

        def __pow__(self, other):
            return self

        def mean(self):
            return self

        def backward(self):
            pass

        def item(self):
            return True

        def cpu(self):
            return self

        def numpy(self):
            return np.zeros((1, 3))

    class Model:
        def to(self, device):
            assert device == "cuda"
            return self

        def parameters(self):
            return ()

        def train(self):
            pass

        def eval(self):
            if postfit_fault:
                raise RuntimeError("synthetic-postfit-failure")

        def __call__(self, x):
            return Tensor()

    class Optimizer:
        def __init__(self, params, **kw):
            assert kw == dict(lr=0.001, weight_decay=0.01)

        def zero_grad(self, **kw):
            assert kw == dict(set_to_none=True)

        def step(self):
            steps.append(1)

    class NoGrad:
        def __enter__(self):
            pass

        def __exit__(self, *a):
            pass

    fake = SimpleNamespace(
        manual_seed=lambda s: events.append(("seed", s)),
        use_deterministic_algorithms=lambda flag: events.append(("deterministic", flag)),
        backends=SimpleNamespace(
            cuda=SimpleNamespace(matmul=SimpleNamespace(allow_tf32=True)),
            cudnn=SimpleNamespace(allow_tf32=True),
        ),
        tensor=lambda a, *, device: Tensor(),
        isfinite=lambda x: Tensor(),
        optim=SimpleNamespace(AdamW=Optimizer),
        cuda=SimpleNamespace(synchronize=lambda: syncs.append(1)),
        no_grad=NoGrad,
    )
    monkeypatch.setitem(sys.modules, "torch", fake)
    monkeypatch.setattr(study, "make_gru", Model)
    args = (np.zeros((2, 6, 63)), np.zeros((2, 3)), np.zeros((1, 6, 63)))
    if postfit_fault:
        with pytest.raises(RuntimeError, match="synthetic-postfit"):
            study.fit_gru(*args, progress=lambda *e: events.append(e))
    else:
        _, predictions = study.fit_gru(*args, progress=lambda *e: events.append(e))
        assert predictions.shape == (1, 3)
    assert len(steps) == 1024 and len(syncs) == 5
    assert events[-1] == ("gru", "completed", 1024)
    assert ("gru", "started", 0) in events
    assert not fake.backends.cuda.matmul.allow_tf32 and not fake.backends.cudnn.allow_tf32


def test_pure_preparation_no_source_env_network_or_fit_access(monkeypatch, plan):
    def forbidden(*a, **kw):
        pytest.fail("unexpected IO/provider/model access")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(study, "fit_ridge", forbidden)
    monkeypatch.setattr(study, "fit_gru", forbidden)
    monkeypatch.setattr(study, "make_gru", forbidden)
    seal = seal_for(plan)
    assert study.evaluate(marks(plan), seal)
    assert study.criterion(good_cells())["gru"] == "development_survivor"
    assert VINTAGE not in repr(seal)
    assert "pending_new_2016_cohort" in json.dumps(study.configuration())
