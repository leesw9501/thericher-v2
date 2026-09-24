"""Synthetic-only pure policy graph tests; no provider, artifacts or broker."""

from __future__ import annotations

import ast
import json
import socket
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from thericher_v2.research import policy_graph_models as s


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("network forbidden")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)


def schedule(start, days):
    result = []
    day = start
    while len(result) < days * 6:
        if day.weekday() < 5:
            first = datetime(day.year, day.month, day.day, 12, 30, tzinfo=s.NY)
            result.extend((first + i * timedelta(minutes=30)).astimezone(UTC) for i in range(6))
        day += timedelta(days=1)
    return tuple(result)


@pytest.fixture
def inputs():
    rng = np.random.default_rng(811)
    train_times = schedule(datetime(2024, 1, 2), 100)
    eval_times = schedule(train_times[-1] + timedelta(days=1), 4)
    n, m = len(train_times), len(eval_times)
    train_x = rng.normal(0, 0.002, size=(n, 36, 4))
    eval_x = rng.normal(0, 0.002, size=(m, 36, 4))
    train_x[:, :, 3] += 10
    eval_x[:, :, 3] += 10
    y = 8 + 5000 * train_x[:, -1, 0] - 2000 * train_x[:, -5, 1]
    return dict(
        train_x=train_x,
        eval_x=eval_x,
        train_closes=100 * np.cumprod(1 + rng.normal(0, 0.001, (n, 36)), axis=1),
        eval_closes=100 * np.cumprod(1 + rng.normal(0, 0.001, (m, 36)), axis=1),
        train_times=train_times,
        eval_times=eval_times,
        train_y=y,
        train_net_y=y - 6.017,
        deadline=time.monotonic() + 60,
    )


def test_exact_matrix_fit_budget_diagnostics_and_readonly_outputs(inputs):
    before = {k: v.copy() for k, v in inputs.items() if isinstance(v, np.ndarray)}
    result = s.fit_predict_graph(**inputs)
    assert tuple(result.targets) == s.TARGET_KEYS
    assert all(
        a.shape == (24,) and a.dtype == np.bool_ and not a.flags.writeable
        for a in result.targets.values()
    )
    assert result.gate_choice.shape == (24,) and result.gate_choice.dtype.kind == "i"
    assert not result.gate_choice.flags.writeable
    assert set(result.gate_choice) <= {0, 1, 2, 3}
    assert (result.diagnostics["ridge_fits"], result.diagnostics["tree_fits"]) == (4, 1)
    assert result.diagnostics["oof_count"] == 450
    assert result.diagnostics["decision_cost_bps_per_side"] == 3
    assert result.diagnostics["gate_depth"] <= 2 and result.diagnostics["gate_leaves"] <= 4
    assert sum(result.diagnostics["gate_choice_counts"]) == 24
    assert sum(result.diagnostics["gate_leaf_eval_counts"]) == 24
    assert all(n >= 64 for n in result.diagnostics["gate_leaf_train_counts"])
    json.dumps(result.diagnostics, allow_nan=False)
    assert "array(" not in repr(result)
    for k, value in before.items():
        np.testing.assert_array_equal(inputs[k], value)


def test_quarters_are_unique_new_york_dates_not_rows_or_utc_dates():
    # Sparse second quarter and UTC date rollover must not change NY date cuts.
    times = []
    first = datetime(2024, 1, 1, 9, tzinfo=s.NY)
    for day in range(16):
        origin = first + timedelta(days=day)
        count = 40 if day < 4 else 30
        times.extend((origin + timedelta(minutes=20 * j)).astimezone(UTC) for j in range(count))
    splits = s._inner_splits(tuple(times))
    expected = ((4, 8), (8, 12), (12, 16))
    for (train, validation, cutoff), (left, right) in zip(splits, expected, strict=True):
        dates = {times[i].astimezone(s.NY).date() for i in validation}
        assert dates == {(first + timedelta(days=d)).date() for d in range(left, right)}
        assert max(times[i] + s.HOLD for i in train) < cutoff
        assert cutoff == times[validation[0]] - s.HISTORY


def test_exact_inner_cutoff_is_excluded():
    times = tuple(
        datetime(2024, 1, 1, tzinfo=UTC) + timedelta(minutes=5 * i) for i in range(288 * 12)
    )
    splits = s._inner_splits(times)
    for training, validation, cutoff in splits:
        boundary = cutoff - s.HOLD
        index = times.index(boundary)
        assert index not in training
        assert times[index - 1] + s.HOLD < cutoff
        assert times[validation[0]] - s.HISTORY == cutoff


def test_each_inner_fit_and_gate_use_only_matching_oof_records(inputs, monkeypatch):
    ridge_calls, tree_calls = [], []
    original = s.Ridge
    original_tree = s.DecisionTreeRegressor

    def ridge(**kwargs):
        assert kwargs == dict(alpha=1.0, solver="svd", fit_intercept=True)
        model = original(**kwargs)
        fit = model.fit

        def capture(x, y):
            ridge_calls.append((x.copy(), y.copy()))
            return fit(x, y)

        model.fit = capture
        return model

    def tree(**kwargs):
        assert kwargs == dict(max_depth=2, min_samples_leaf=64, random_state=811)
        model = original_tree(**kwargs)
        fit = model.fit

        def capture(x, y):
            tree_calls.append((x.copy(), y.copy()))
            return fit(x, y)

        model.fit = capture
        return model

    monkeypatch.setattr(s, "Ridge", ridge)
    monkeypatch.setattr(s, "DecisionTreeRegressor", tree)
    result = s.fit_predict_graph(**inputs)
    assert len(ridge_calls) == 4 and len(tree_calls) == 1
    splits = s._inner_splits(inputs["train_times"])
    for (train, _, _), (x, y), fact in zip(
        splits, ridge_calls[:3], result.diagnostics["inner"], strict=True
    ):
        raw = inputs["train_x"][train]
        mean, scale = raw.mean(axis=(0, 1)), raw.std(axis=(0, 1))
        scale = np.where(scale == 0, 1, scale)
        np.testing.assert_array_equal(x, ((raw - mean) / scale).reshape(len(train), -1))
        np.testing.assert_array_equal(y, inputs["train_y"][train])
        assert fact["scaler_sha256"] == s._hash(mean, scale)
        assert datetime.fromisoformat(fact["train_label_end"]) < datetime.fromisoformat(
            fact["validation_history_start"]
        )
    np.testing.assert_array_equal(ridge_calls[-1][1], inputs["train_y"])
    meta_x, utility = tree_calls[0]
    selected = np.concatenate([v for _, v, _ in splits])
    assert meta_x.shape == (450, 6) and utility.shape == (450, 3)
    assert set(np.unique(meta_x[:, :3])) <= {0, 1}
    np.testing.assert_array_equal(utility, meta_x[:, :3] * inputs["train_net_y"][selected, None])
    # This intentionally differs from gross-6: the helper must consume exact caller net labels.
    assert np.any(utility != meta_x[:, :3] * (inputs["train_y"][selected, None] - 6))


def test_eval_mutation_never_changes_fit_scalers_oof_or_gate(inputs):
    first = s.fit_predict_graph(**inputs)
    changed = dict(
        inputs, eval_x=inputs["eval_x"] * 8, eval_closes=inputs["eval_closes"][:, ::-1].copy()
    )
    second = s.fit_predict_graph(**changed)
    for key in ("inner", "final", "oof_sha256", "gate_sha256", "gate_leaf_train_counts"):
        assert first.diagnostics[key] == second.diagnostics[key]


def test_future_inner_labels_and_features_do_not_change_earlier_prefix_model(inputs):
    first = s.fit_predict_graph(**inputs)
    _, validation, _ = s._inner_splits(inputs["train_times"])[0]
    x, y = inputs["train_x"].copy(), inputs["train_y"].copy()
    x[validation] *= 2
    y[validation] += 100
    second = s.fit_predict_graph(**dict(inputs, train_x=x, train_y=y))
    a, b = first.diagnostics["inner"][0], second.diagnostics["inner"][0]
    assert a["model_sha256"] == b["model_sha256"]
    assert a["scaler_sha256"] == b["scaler_sha256"]
    assert (
        first.diagnostics["inner"][1]["model_sha256"]
        != second.diagnostics["inner"][1]["model_sha256"]
    )


def test_net_labels_affect_gate_not_any_ridge_fit(inputs):
    a = s.fit_predict_graph(**inputs)
    b = s.fit_predict_graph(**dict(inputs, train_net_y=-np.ones(len(inputs["train_y"]))))
    assert a.diagnostics["inner"] == b.diagnostics["inner"]
    assert a.diagnostics["final"] == b.diagnostics["final"]
    assert np.all(b.gate_choice == 0) and not b.targets["gate"].any()


def test_rule_formulas_population_std_context_and_zero_std():
    closes = np.full((4, 36), 100.0)
    closes[0, -3:] = 110
    closes[1, -12:] = [100 + 2 * i for i in range(11)] + [103]
    closes[3, -3:] = [120, 120, 90]
    x = np.zeros((4, 36, 4), dtype="float64")
    x[:, :, 0] = np.arange(36) * 0.001
    trend, reversal, context = s._rule_context(x, closes)
    np.testing.assert_array_equal(trend, [True, True, False, True])
    np.testing.assert_array_equal(reversal, [False, True, False, True])
    assert closes[1, -1] >= closes[1, -12:].mean() - closes[1, -12:].std(ddof=1)
    np.testing.assert_allclose(context[:, 0], closes[:, -3:].mean(1) / closes[:, -12:].mean(1) - 1)
    np.testing.assert_allclose(context[:, 1], closes[:, -1] / closes[:, -12:].mean(1) - 1)
    np.testing.assert_allclose(context[:, 2], x[:, -12:, 0].std(1, ddof=0))


@pytest.mark.parametrize("level", [6.0, 6.0001])
def test_strict_ridge_vote_majority_and_leave_one_controls(inputs, level):
    inputs["train_y"][:] = level
    result = s.fit_predict_graph(**inputs)
    a, b, c = [result.targets[k] for k in ("trend", "reversion", "ridge")]
    assert np.all(c == (level > 6))
    np.testing.assert_array_equal(result.targets["majority"], a.astype(int) + b + c >= 2)
    np.testing.assert_array_equal(result.targets["without_trend"], b & c)
    np.testing.assert_array_equal(result.targets["without_reversion"], a & c)
    np.testing.assert_array_equal(result.targets["without_ridge"], a & b)
    assert not result.targets["always_flat"].any() and result.targets["always_long"].all()


def test_gate_strict_positive_tie_order_and_current_expert_flat():
    votes = np.array([[1, 1, 1], [1, 1, 1], [1, 1, 1], [1, 1, 1], [0, 1, 1]], dtype=bool)
    utilities = np.array([[0, -1, 0], [2, 2, 2], [1, 3, 3], [-1, -2, 4], [5, 0, 0]], dtype=float)
    choice, target = s._gate_decision(votes, utilities)
    np.testing.assert_array_equal(choice, [0, 1, 2, 3, 1])
    np.testing.assert_array_equal(target, [False, True, True, True, False])


def test_price_unit_rescaling_and_no_current_position_input(inputs):
    first = s.fit_predict_graph(**inputs)
    train_scale = np.arange(len(inputs["train_closes"]))[:, None] + 1.0
    eval_scale = np.arange(len(inputs["eval_closes"]))[:, None] + 2.0
    second = s.fit_predict_graph(
        **dict(
            inputs,
            train_closes=inputs["train_closes"] * train_scale,
            eval_closes=inputs["eval_closes"] * eval_scale,
        )
    )
    for key in s.TARGET_KEYS:
        np.testing.assert_array_equal(first.targets[key], second.targets[key])
    with pytest.raises(TypeError):
        s.fit_predict_graph(**inputs, current_position=np.zeros(len(inputs["eval_x"])))
    with pytest.raises(TypeError):
        s.fit_predict_graph(**inputs, eval_y=np.zeros(len(inputs["eval_x"])))


@pytest.mark.parametrize(
    "key", ["train_x", "eval_x", "train_closes", "eval_closes", "train_y", "train_net_y"]
)
@pytest.mark.parametrize("issue", ["shape", "nonfinite", "dtype"])
def test_bad_arrays_fail_before_fit(inputs, monkeypatch, key, issue):
    def forbidden(**kwargs):
        pytest.fail("fit must not start")

    monkeypatch.setattr(s, "Ridge", forbidden)
    if issue == "shape":
        inputs[key] = inputs[key][:-1]
    elif issue == "dtype":
        inputs[key] = inputs[key].astype("float32")
    else:
        inputs[key].flat[0] = np.nan
    with pytest.raises(ValueError):
        s.fit_predict_graph(**inputs)


@pytest.mark.parametrize(
    "issue", ["naive", "offset", "duplicate", "reverse", "count", "outer_equal"]
)
def test_times_and_outer_purge_are_fail_closed(inputs, issue):
    times = list(inputs["eval_times"])
    if issue == "naive":
        times[0] = times[0].replace(tzinfo=None)
    elif issue == "offset":
        times[0] = times[0].astimezone(ZoneInfo("Asia/Seoul"))
    elif issue == "duplicate":
        times[1] = times[0]
    elif issue == "reverse":
        times.reverse()
    elif issue == "count":
        times.pop()
    else:
        start = inputs["train_times"][-1] + s.HOLD + s.HISTORY
        times = [start + timedelta(minutes=30 * i) for i in range(len(times))]
    with pytest.raises(ValueError):
        s.fit_predict_graph(**dict(inputs, eval_times=times))


def test_outer_purge_is_strict_but_allows_later_microsecond(inputs):
    start = inputs["train_times"][-1] + s.HOLD + s.HISTORY + timedelta(microseconds=1)
    times = tuple(start + timedelta(minutes=30 * i) for i in range(len(inputs["eval_times"])))
    assert s.fit_predict_graph(**dict(inputs, eval_times=times)).diagnostics["ridge_fits"] == 4


@pytest.mark.parametrize("minimum", [127, 128])
def test_exact_inner_minimum_preflight(minimum):
    first = datetime(2024, 1, 1, 9, tzinfo=s.NY)
    times = tuple(
        (first + timedelta(days=2 * d, minutes=i)).astimezone(UTC)
        for d in range(4)
        for i in range(minimum)
    )
    if minimum == 127:
        with pytest.raises(s.GraphInputUnavailable, match="insufficient_inner_train") as error:
            s._inner_splits(times)
        assert error.value.status == "input_unavailable" and error.value.count == 127
    else:
        assert [len(a) for a, _, _ in s._inner_splits(times)] == [128, 256, 384]


@pytest.mark.parametrize("pooled", [127, 128])
def test_exact_pooled_oof_minimum(pooled):
    origin = datetime(2024, 1, 1, 9, tzinfo=s.NY)
    counts = [128, 42, 42, pooled - 84]
    times = tuple(
        (origin + timedelta(days=2 * d, minutes=i)).astimezone(UTC)
        for d, count in enumerate(counts)
        for i in range(count)
    )
    if pooled == 127:
        with pytest.raises(s.GraphInputUnavailable, match="insufficient_pooled_oof"):
            s._inner_splits(times)
    else:
        assert sum(len(v) for _, v, _ in s._inner_splits(times)) == 128


def test_all_support_checks_precede_any_fit(inputs, monkeypatch):
    def forbidden(**kwargs):
        pytest.fail("insufficient must not partially fit")

    monkeypatch.setattr(s, "Ridge", forbidden)
    # Retain only ten dates: first quarter cannot provide 128 training examples.
    for key in ("train_x", "train_closes", "train_y", "train_net_y", "train_times"):
        inputs[key] = inputs[key][:70]
    with pytest.raises(s.GraphInputUnavailable):
        s.fit_predict_graph(**inputs)


@pytest.mark.parametrize("key", ["train_closes", "eval_closes"])
def test_nonpositive_closing_price_is_rejected(inputs, key):
    inputs[key][0, 0] = 0
    with pytest.raises(ValueError, match="closes_positive_required"):
        s.fit_predict_graph(**inputs)


def test_constant_feature_channels_are_finite(inputs):
    inputs["train_x"][:] = 0
    result = s.fit_predict_graph(**inputs)
    assert result.diagnostics["ridge_fits"] == 4
    json.dumps(result.diagnostics, allow_nan=False)


@pytest.mark.parametrize("deadline", [0, float("nan"), float("inf"), True])
def test_deadline_validation_and_expiry(inputs, deadline):
    with pytest.raises((TimeoutError, ValueError)):
        s.fit_predict_graph(**dict(inputs, deadline=deadline))


def test_deadline_checked_after_fit(inputs, monkeypatch):
    original = s.Ridge
    expired = False

    def ridge(**kwargs):
        model = original(**kwargs)
        fit = model.fit

        def finish(x, y):
            nonlocal expired
            fit(x, y)
            expired = True
            return model

        model.fit = finish
        return model

    monkeypatch.setattr(s, "Ridge", ridge)
    monkeypatch.setattr(s.time, "monotonic", lambda: 2 if expired else 0)
    with pytest.raises(TimeoutError):
        s.fit_predict_graph(**dict(inputs, deadline=1))


def test_pure_module_has_no_broker_artifact_provider_or_gpu_imports():
    tree = ast.parse(Path(s.__file__).read_text())
    imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert all(not (name or "").startswith("thericher_v2") for name in imports)
    names = [n.id for n in ast.walk(tree) if isinstance(n, ast.Name)]
    assert not {"open", "torch", "socket", "subprocess", "pickle", "Path"}.intersection(names)
