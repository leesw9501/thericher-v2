from __future__ import annotations

import builtins
import json
import socket
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction
from types import SimpleNamespace

import numpy as np
import pytest

from thericher_v2.research import kis_cross_asset_regime_experts as study
from thericher_v2.research.cross_asset_daily_risk_input import DailyRiskFeatures, RawD1Price
from thericher_v2.research.cross_asset_etf_input import CrossAssetSession

D = Decimal


def session(day):
    return CrossAssetSession(
        day, datetime.combine(day, time(14, 30), UTC), datetime.combine(day, time(21), UTC)
    )


def source():
    schedule = tuple(session(date(2024, 1, 1) + timedelta(days=i)) for i in range(64))
    rows = {}
    with localcontext(study.CONTEXT):
        for asset, symbol in enumerate(study.kernel.SYMBOLS):
            values, price = [], D(100 + 17 * asset)
            for i, s in enumerate(schedule):
                price *= 1 + D((i * (asset + 1) % 11) - 4) / 1000
                values.append(
                    RawD1Price(
                        symbol,
                        s.session_date,
                        "synthetic-only",
                        close=price,
                        open=None if i == 0 else price / D("1.003"),
                    )
                )
            rows[symbol] = tuple(values)
    return schedule, rows


def context(rows=None):
    schedule, original = source()
    return study.prepare_context(
        original if rows is None else rows,
        scheduled_history=schedule,
        entry_session=session(schedule[-1].session_date + timedelta(days=1)),
        decision_at=schedule[-1].close_at,
        vintage_ref="synthetic-only",
    )


def synthetic_context(momentum=(".1", ".1", ".01")):
    schedule, _ = source()
    channels = tuple(
        tuple(D(v) / 63 for _ in range(63)) if k % 2 == 0 else (D(0),) * 63
        for k, v in enumerate(x for v in momentum for x in (v, "0"))
    )
    features = DailyRiskFeatures(
        schedule[-1].close_at,
        session(schedule[-1].session_date + timedelta(days=1)).open_at,
        tuple(s.session_date for s in schedule[1:]),
        channels,
        "synthetic-only",
    )
    covariance = (
        (0.0004, 0.00005, -0.00003),
        (0.00005, 0.0001, 0.00002),
        (-0.00003, 0.00002, 0.0002),
    )
    return study.kernel.CausalRiskContext(features, covariance)


def groups(count=2):
    result = []
    for k in range(count):
        days = []
        for j in range(21):
            opened = tuple(D(100 + 30 * a + 7 * k) for a in range(3))
            closed = tuple(
                v * (1 + D((a + 1) * (j + 1) - k * 8) / 1000) for a, v in enumerate(opened)
            )
            days.append(
                study.nav.ThreeAssetDay(
                    date(2024, 1, 1) + timedelta(days=21 * k + j), opened, closed
                )
            )
        result.append(tuple(days))
    return tuple(result)


def training_geometry():
    sessions = tuple(session(date(2016, 1, 1) + timedelta(days=i)) for i in range(55 * 21 + 2))
    windows = tuple((sessions[i * 21].open_at, sessions[i * 21 + 20].close_at) for i in range(55))
    return windows, sessions


@pytest.fixture
def torch():
    return pytest.importorskip("torch")


def test_fixed_source_free_contract_geometry():
    cfg = study.configuration()
    assert cfg["cells"] == len(study.POLICIES) * 3 * 2 == 36
    assert cfg["fits"] == cfg["oof"]["fits"] + cfg["final_fits"] == 8
    assert cfg["family_seconds"] == 300 and cfg["mlp"]["widths"] == [6, 8, 3]
    assert cfg["tree"]["depth"] == 2 and cfg["tree"]["min_leaf"] == 5
    assert cfg["oof"]["validation_groups"] == [13, 13, 14]
    assert cfg["source_io"] is cfg["paper_input"] is False and cfg["actual_fits"] == 0
    assert "RELATED_OUTCOME_INFORMED_SEEN" in cfg["grade"]


def test_exact_six_states_and_hidden_immutable_values():
    schedule, rows = source()
    actual = context()
    base = study.kernel.prepare_context(
        rows,
        scheduled_history=schedule,
        entry_session=session(schedule[-1].session_date + timedelta(days=1)),
        decision_at=schedule[-1].close_at,
        vintage_ref="synthetic-only",
    )
    with localcontext(study.CONTEXT):
        expected_momentum = tuple(float(sum(base.features.features[2 * k], D(0))) for k in range(3))
    c = np.asarray(base.covariance)
    np.testing.assert_allclose(actual.state[:3], expected_momentum, rtol=0, atol=0)
    assert actual.state[3] == np.sqrt(252 * c[0, 0])
    np.testing.assert_allclose(
        actual.state[4:], [c[0, j] / np.sqrt(c[0, 0] * c[j, j]) for j in (1, 2)]
    )
    assert repr(actual) == "ExpertContext()"
    with pytest.raises(FrozenInstanceError):
        actual.state = ()


@pytest.mark.parametrize("kind", ["absent", "extreme", "duplicate", "unreadable"])
def test_all_forward_support_cannot_change_state_experts_or_blend(kind):
    schedule, rows = source()
    changed = dict(rows)
    for symbol in study.kernel.SYMBOLS:
        future = RawD1Price(
            symbol,
            schedule[-1].session_date + timedelta(days=1),
            "synthetic-only",
            open=D("1e30"),
            close=D("1e-20"),
        )
        if kind == "unreadable":

            class Future:
                session_date = schedule[-1].session_date + timedelta(days=2)

                @property
                def close(self):
                    raise AssertionError("future_label_read")

            changed[symbol] += (Future(),)
        elif kind != "absent":
            changed[symbol] += (future,) * (2 if kind == "duplicate" else 1)
    assert context(changed) == context(rows)
    assert study.uniform_blend(context(changed)) == study.uniform_blend(context(rows))


@pytest.mark.parametrize("fault", ["gap", "symbol", "vintage"])
def test_required_past_unavailable_not_fallback(fault):
    _, rows = source()
    if fault == "gap":
        rows["TLT"] = rows["TLT"][:17] + rows["TLT"][18:]
    elif fault == "symbol":
        del rows["GLD"]
    else:
        rows["SPY"] = tuple(replace(r, vintage_ref="wrong") for r in rows["SPY"])
    with pytest.raises(ValueError):
        context(rows)


@pytest.mark.parametrize(
    "momentum,chosen",
    [
        ((".1", ".1", ".01"), 0),
        (("-.1", ".02", ".03"), 2),
        (("0", "0", "0"), None),
        (("-.1", "-.2", "-.01"), None),
    ],
)
def test_momentum_strict_positive_and_fixed_instrument_ties(momentum, chosen):
    actual = study.experts_from_context(synthetic_context(momentum))
    target = actual.targets[0]
    assert [k for k, v in enumerate(target.weights3) if v > 0] == (
        [] if chosen is None else [chosen]
    )


def test_single_shrink_minvar_and_convex_risk_cap(monkeypatch):
    base = synthetic_context()
    seen = []
    solve = study.kernel.controls.solver.minimum_variance_weights

    def capture(matrix):
        seen.append(matrix.copy())
        return solve(matrix)

    monkeypatch.setattr(study.kernel.controls.solver, "minimum_variance_weights", capture)
    actual = study.experts_from_context(base)
    c = np.asarray(base.covariance)
    shrunk = 0.75 * c + 0.25 * np.diag(np.diag(c))
    np.testing.assert_allclose(0.9 * seen[0] + 0.1 * np.diag(np.diag(seen[0])), shrunk, atol=1e-20)
    for target in (*actual.targets, study.uniform_blend(actual)):
        v = np.asarray(target.weights3, dtype=np.float64)
        assert np.sqrt(252 * (v @ shrunk @ v)) <= 0.10 + 1e-14
        assert sum(map(Fraction, target.weights3)) + Fraction(target.cash_weight) == 1
    with localcontext(study.CONTEXT):
        expected = tuple(sum((t.weights3[k] for t in actual.targets), D(0)) / 3 for k in range(3))
    assert study.uniform_blend(actual).weights3 == expected


def test_qualified_prefix_purges_same_close_and_uses_scheduled_lag():
    windows, sessions = training_geometry()
    folds = study.build_oof(windows, sessions)
    assert [len(f.train_indices) for f in folds] == [14, 27, 40]
    assert [len(f.test_indices) for f in folds] == [13, 13, 14]
    assert tuple(i for f in folds for i in f.test_indices) == tuple(range(15, 55))
    decision = sessions[55 * 21].close_at
    assert study.qualified_prefix(windows, sessions, decision, 55) == tuple(range(55))
    same_close = windows[14][1]
    assert 14 not in study.qualified_prefix(windows, sessions, same_close, 15)
    assert 14 in study.qualified_prefix(windows, sessions, sessions[315].close_at, 15)


@pytest.mark.parametrize("fault", ["date_guess", "wrong_exit", "wrong_count"])
def test_oof_clock_and_shape_rejected(fault):
    windows, sessions = training_geometry()
    if fault == "date_guess":
        decision = sessions[400].close_at + timedelta(seconds=1)
        with pytest.raises(ValueError, match="decision_clock"):
            study.qualified_prefix(windows, sessions, decision, 15)
    else:
        changed = list(windows)
        if fault == "wrong_exit":
            changed[0] = (windows[0][0], sessions[19].close_at)
        else:
            changed.pop()
        with pytest.raises(ValueError):
            study.build_oof(tuple(changed), sessions)


def test_prefix_scaler_reads_only_qualified_states_never_oof_labels():
    windows, sessions = training_geometry()
    fold = study.build_oof(windows, sessions)[0]
    base = study.experts_from_context(synthetic_context())
    states = tuple(replace(base, state=tuple(float(i + j) for j in range(6))) for i in range(55))
    scaler = study.prefix_scaler(states, fold)
    assert scaler.train_indices == tuple(range(14))
    np.testing.assert_allclose(scaler.mean, np.arange(6) + 6.5)
    changed = states[:14] + (object(),) * 41
    assert study.prefix_scaler(changed, fold) == scaler
    zero = study.prefix_scaler((base,) * 55, fold)
    assert zero.scale == (1.0,) * 6
    transformed = study.scale_states(states, scaler, fold.train_indices)
    np.testing.assert_allclose(transformed.mean(0), 0, atol=1e-15)
    assert "mean=" not in repr(scaler)


def test_local_target_cost_cash_and_ties_are_separate_from_features():
    actual = study.experts_from_context(synthetic_context())
    group = groups(1)[0]
    scores, winner = study.local_utility_labels(group, actual.targets)
    with localcontext(study.CONTEXT):
        trace = study.kernel.decimal_reference((group,), (actual.targets[0],), cost_bps=D(10))
        logs = tuple(v.log_return for v in trace.daily)
        mean = sum(logs, D(0)) / 21
        assert scores[0] == 252 * (mean - 5 * sum(((v - mean) ** 2 for v in logs), D(0)) / 21)
    assert scores[2] == 0 and winner in (0, 1, 2)
    cash = actual.targets[2]
    assert study.local_utility_labels(group, (cash,) * 3) == ((D(0),) * 3, 2)
    duplicated = (actual.targets[0], actual.targets[0], cash)
    scores, winner = study.local_utility_labels(group, duplicated)
    assert scores[0] == scores[1] > 0 and winner == 1


def test_cpu_gate_default_shape_seed_and_rng_preserved_without_fit_or_gpu(torch, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("GPU_or_fit")

    monkeypatch.setattr(torch.cuda, "init", forbidden)
    monkeypatch.setattr(torch.cuda, "is_available", forbidden)
    state = torch.random.get_rng_state().clone()
    first, second = study.make_gate(), study.make_gate()
    assert torch.equal(state, torch.random.get_rng_state())
    assert all(
        torch.equal(a, b) for a, b in zip(first.parameters(), second.parameters(), strict=True)
    )
    assert first(torch.zeros((2, 6), dtype=torch.float32)).shape == (2, 3)
    assert sum(p.numel() for p in first.parameters()) == 83
    assert all(p.device.type == "cpu" and p.dtype == torch.float32 for p in first.parameters())


def test_mixture_gradient_fee_and_continuous_kernel_decimal_parity(torch):
    actual = study.experts_from_context(synthetic_context())
    expert = torch.tensor(
        [[tuple(float(v) for v in (*t.weights3, t.cash_weight)) for t in actual.targets]] * 2,
        dtype=torch.float64,
    )
    logits = torch.tensor(
        [[0.2, -0.1, 0.3], [-0.4, 0.1, 0.2]], dtype=torch.float64, requires_grad=True
    )
    weights = study.mix_experts(logits, expert)
    marks = groups()
    opened = torch.tensor([[float(v) for v in g[0].adj_open3] for g in marks], dtype=torch.float64)
    closed = torch.tensor(
        [[[float(v) for v in d.adj_close3] for d in g] for g in marks], dtype=torch.float64
    )
    replay = study.kernel.replay_closed_groups(opened, closed, weights, 10.0, tail_days=2)
    loss = study.kernel.net_utility(replay)
    (gradient,) = torch.autograd.grad(loss, logits)
    assert torch.isfinite(gradient).all() and gradient.abs().sum() > 0
    epsilon = 1e-5
    plus, minus = logits.detach().clone(), logits.detach().clone()
    plus[0, 0] += epsilon
    minus[0, 0] -= epsilon

    def objective(v):
        return study.kernel.net_utility(
            study.kernel.replay_closed_groups(
                opened, closed, study.mix_experts(v, expert), 10.0, tail_days=2
            )
        ).item()

    assert gradient[0, 0].item() == pytest.approx(
        (objective(plus) - objective(minus)) / (2 * epsilon), abs=1e-8
    )
    targets = []
    for w in weights.detach().numpy():
        with localcontext(study.CONTEXT):
            risky = tuple(D(str(float(v))) for v in w[:3])
        targets.append(study._target(risky))
    last = marks[-1][-1]
    tail = tuple(
        study.nav.ThreeAssetDay(last.date + timedelta(days=i + 1), last.adj_close3, last.adj_close3)
        for i in range(2)
    )
    exact = study.kernel.decimal_reference(marks, tuple(targets), cost_bps=D(10), tail=tail)
    np.testing.assert_allclose(
        replay.nav.detach().numpy(), [float(d.nav) for d in exact.daily], atol=1e-10
    )
    np.testing.assert_allclose(
        replay.fees.detach().numpy(), [float(d.fees) for d in exact.daily], atol=1e-10
    )
    assert exact.daily[21].nav != pytest.approx(exact.daily[0].nav)
    c = np.asarray(actual.covariance)
    shrunk = 0.75 * c + 0.25 * np.diag(np.diag(c))
    for w in weights.detach().numpy():
        assert np.sqrt(252 * (w[:3] @ shrunk @ w[:3])) <= 0.10 + 1e-14


@pytest.mark.parametrize("fault", ["shape", "not_simplex", "nonfinite"])
def test_gate_mixture_rejects_invalid_domains(torch, fault):
    logits = torch.zeros((1, 3), dtype=torch.float64)
    expert = torch.tensor([[[0.0, 0.0, 0.0, 1.0]] * 3], dtype=torch.float64)
    if fault == "shape":
        logits = logits[:, :2]
    elif fault == "not_simplex":
        expert[0, 0, 3] = 2
    else:
        logits[0, 0] = float("nan")
    with pytest.raises(ValueError):
        study.mix_experts(logits, expert)


def fake_tree():
    return SimpleNamespace(
        classes_=np.array([0, 1, 2]),
        tree_=SimpleNamespace(
            node_count=3,
            max_depth=1,
            children_left=np.array([1, -1, -1]),
            children_right=np.array([2, -1, -1]),
            feature=np.array([0, -2, -2]),
            threshold=np.array([0.5, -2.0, -2.0]),
            value=np.array([[[0.3, 0.3, 0.4]], [[0.5, 0.5, 0]], [[0, 0.5, 0.5]]]),
        ),
    )


def test_safe_json_tree_routing_float32_and_cash_first_probability_ties():
    record = study.tree_to_record(fake_tree())
    restored = json.loads(json.dumps(record, allow_nan=False))
    assert study.tree_decisions([[0.5, 0, 0, 0, 0, 0], [0.51, 0, 0, 0, 0, 0]], restored) == (1, 2)
    one = SimpleNamespace(
        classes_=np.array([1]),
        tree_=SimpleNamespace(
            node_count=1,
            max_depth=0,
            children_left=np.array([-1]),
            children_right=np.array([-1]),
            feature=np.array([-2]),
            threshold=np.array([-2.0]),
            value=np.array([[[1.0]]]),
        ),
    )
    assert study.tree_decisions([[0] * 6], study.tree_to_record(one)) == (1,)


@pytest.mark.parametrize("fault", ["cycle", "nan", "unknown", "unreachable"])
def test_tree_json_rejects_executable_or_invalid_structure(fault):
    record = study.tree_to_record(fake_tree())
    if fault == "cycle":
        record["nodes"][0]["left"] = 0
    elif fault == "nan":
        record["nodes"][0]["threshold"] = float("nan")
    elif fault == "unknown":
        record["pickle"] = "never"
    else:
        record["nodes"].append(dict(action=0))
    with pytest.raises(ValueError):
        study.tree_decisions([[0] * 6], record)


def cells():
    return [
        dict(
            block=b,
            policy=p,
            cost_bps=str(c),
            metrics=dict(
                growth=".01" if p in study.CANDIDATES else ".50",
                utility=".3" if p == "mlp" else ".2" if p == "tree" else ".1",
            ),
        )
        for b in (0, 1)
        for p in study.POLICIES
        for c in study.COSTS
    ]


@pytest.mark.parametrize("fault", [None, "negative_growth", "utility_inferior", "mlp_loses_tree"])
def test_original_kill_requires_positive_growth_and_utility_not_wealth(fault):
    matrix = cells()
    for row in matrix:
        if row["block"] == 1 and row["cost_bps"] == "10":
            if fault == "negative_growth" and row["policy"] in study.CANDIDATES:
                row["metrics"]["growth"] = "-.001"
            elif fault == "utility_inferior" and row["policy"] in study.CANDIDATES:
                row["metrics"]["utility"] = ".05"
            elif fault == "mlp_loses_tree" and row["policy"] == "mlp":
                row["metrics"]["utility"] = ".2"
    result = study.criterion(matrix)
    assert result["tree"] == (
        "rejected" if fault in ("negative_growth", "utility_inferior") else "development_survivor"
    )
    assert result["mlp"] == ("development_survivor" if fault is None else "rejected")


@pytest.mark.parametrize("side", [-1, 0, 1])
def test_kill_decimal50_boundary_under_hostile_ambient_context(side):
    matrix = cells()
    with localcontext(study.CONTEXT):
        score = str(D(".1") + D("1e-10") + side * D("1e-39"))
    for row in matrix:
        if row["policy"] == "tree":
            row["metrics"]["utility"] = score
    with localcontext() as ambient:
        ambient.prec = 6
        assert study.criterion(matrix)["tree"] == (
            "development_survivor" if side > 0 else "rejected"
        )


def test_pure_context_has_no_source_or_network_side_effects(monkeypatch):
    _, rows = source()

    def forbidden(*args, **kwargs):
        raise AssertionError("source_IO")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    assert context(rows).targets[2].cash_weight == 1
