"""Synthetic mechanics only; no data, artifacts, network or performance claims."""

from __future__ import annotations

import inspect
import socket
import time

import numpy as np
import pytest
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.ensemble import _gb as sklearn_gb

from thericher_v2.research import causal_feature_boosting as s
from thericher_v2.research import causal_feature_ridge as ridge
from thericher_v2.research.policy_graph_models import _hash


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("network forbidden")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)


def windows(count, seed=911):
    rng = np.random.default_rng(seed)
    body = rng.uniform(-0.02, 0.02, (count, 36))
    x = np.stack(
        (
            body,
            np.maximum(body, 0) + rng.uniform(0, 0.02, body.shape),
            np.minimum(body, 0) - rng.uniform(0, 0.02, body.shape),
            rng.uniform(0, 12, body.shape),
        ),
        axis=2,
    )
    closes = 100 * np.cumprod(1 + rng.uniform(-0.02, 0.02, body.shape), axis=1)
    return x, closes


@pytest.fixture
def inputs():
    train_x, train_closes = windows(256)
    eval_x, eval_closes = windows(9, seed=912)
    return dict(
        train_x=train_x,
        train_closes=train_closes,
        train_y=3 + 100 * train_x[:, -3, 0] - train_x[:, -1, 3],
        eval_x=eval_x,
        eval_closes=eval_closes,
        deadline=time.monotonic() + 60,
    )


def test_exact_parameters_full_train_once_unscaled_and_actual_hashes(inputs, monkeypatch):
    expected_parameters = dict(
        loss="squared_error",
        learning_rate=0.05,
        n_estimators=64,
        subsample=1.0,
        criterion="friedman_mse",
        min_samples_split=2,
        min_samples_leaf=64,
        max_depth=2,
        max_features=None,
        random_state=911,
        n_iter_no_change=None,
    )
    assert s.PARAMETERS == expected_parameters
    assert s.FEATURES is ridge.FEATURES and len(s.FEATURES) == 15
    assert s.feature_matrix is ridge.feature_matrix
    calls, models = [], []

    def boosting(**kwargs):
        assert kwargs == expected_parameters
        model = GradientBoostingRegressor(**kwargs)
        fit, predict = model.fit, model.predict

        def capture_fit(x, y):
            calls.append(("fit", x.copy(), y.copy()))
            return fit(x, y)

        def capture_predict(x):
            calls.append(("predict", x.copy()))
            return predict(x)

        model.fit, model.predict = capture_fit, capture_predict
        models.append(model)
        return model

    def forbidden(*args, **kwargs):
        pytest.fail("no internal validation split")

    monkeypatch.setattr(s, "GradientBoostingRegressor", boosting)
    monkeypatch.setattr(sklearn_gb, "train_test_split", forbidden)
    forecast, identity = s.fit_predict(**inputs)
    assert len(models) == 1 and [call[0] for call in calls] == ["fit", "predict"]
    training = ridge.feature_matrix(inputs["train_x"], inputs["train_closes"])
    evaluation = ridge.feature_matrix(inputs["eval_x"], inputs["eval_closes"])
    np.testing.assert_array_equal(calls[0][1], training)
    np.testing.assert_array_equal(calls[0][2], inputs["train_y"])
    np.testing.assert_array_equal(calls[1][1], evaluation)
    model = models[0]
    assert model.n_estimators_ == 64 and model.estimators_.shape == (64, 1)
    assert model.n_iter_no_change is None and not model.warm_start
    assert model.init_.constant_[0, 0] == inputs["train_y"].mean()
    arrays = [model.init_.constant_]
    for estimator in model.estimators_[:, 0]:
        tree = estimator.tree_
        assert tree.n_node_samples[0] == len(training)
        assert tree.max_depth <= 2
        assert (tree.n_node_samples[tree.children_left == -1] >= 64).all()
        arrays.extend(
            (
                np.asarray(tree.node_count, dtype="int64"),
                tree.children_left,
                tree.children_right,
                tree.feature,
                tree.threshold,
                tree.value,
                tree.n_node_samples,
                tree.weighted_n_node_samples,
                tree.impurity,
            )
        )
    assert identity == dict(model_sha256=_hash(*arrays), training_features_sha256=_hash(training))
    np.testing.assert_array_equal(forecast, GradientBoostingRegressor.predict(model, evaluation))
    assert forecast.shape == (9,) and forecast.dtype == np.dtype("float64")
    assert not forecast.flags.writeable
    with pytest.raises(ValueError):
        forecast[0] = 0


@pytest.mark.parametrize("change", ["permutation", "append", "perturbation"])
def test_eval_changes_preserve_training_identity_and_unaffected_predictions(inputs, change):
    first, identity = s.fit_predict(**inputs)
    changed = dict(inputs)
    if change == "permutation":
        order = np.random.default_rng(913).permutation(len(first))
        changed["eval_x"] = inputs["eval_x"][order]
        changed["eval_closes"] = inputs["eval_closes"][order]
        expected = first[order]
    elif change == "append":
        future_x, future_closes = windows(5, seed=914)
        changed["eval_x"] = np.concatenate((inputs["eval_x"], future_x))
        changed["eval_closes"] = np.concatenate((inputs["eval_closes"], future_closes))
        expected = first
    else:
        changed["eval_x"], changed["eval_closes"] = windows(len(first), seed=915)
        changed["eval_x"][:4] = inputs["eval_x"][:4]
        changed["eval_closes"][:4] = inputs["eval_closes"][:4]
        expected = first[:4]
    actual, actual_identity = s.fit_predict(**changed)
    assert actual_identity == identity
    np.testing.assert_array_equal(actual[: len(expected)], expected)


def test_deterministic_readonly_inputs_and_no_eval_target_or_tuning_api(inputs):
    before = {key: value.copy() for key, value in inputs.items() if isinstance(value, np.ndarray)}
    for key in before:
        inputs[key].setflags(write=False)
    first, identity = s.fit_predict(**inputs)
    second, second_identity = s.fit_predict(**inputs)
    np.testing.assert_array_equal(first, second)
    assert identity == second_identity
    for key, value in before.items():
        np.testing.assert_array_equal(inputs[key], value)
    parameters = inspect.signature(s.fit_predict).parameters
    assert tuple(parameters) == (
        "train_x",
        "train_closes",
        "train_y",
        "eval_x",
        "eval_closes",
        "deadline",
    )
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in parameters.values())
    with pytest.raises(TypeError):
        s.fit_predict(**inputs, eval_y=np.zeros(9))
    with pytest.raises(TypeError):
        s.fit_predict(**inputs, n_estimators=1)


def test_flat_data_constant_and_mean_controls_bind_init_and_training_separately(inputs):
    for key in ("train_x", "eval_x"):
        inputs[key][:] = 0
    for key in ("train_closes", "eval_closes"):
        inputs[key][:] = 8
    inputs["train_y"][:] = 7
    constant, identity = s.fit_predict(**inputs)
    np.testing.assert_array_equal(constant, 7)
    inputs["train_y"][:] = np.tile([0.0, 4.0], len(inputs["train_y"]) // 2)
    mean, mean_identity = s.fit_predict(**inputs)
    np.testing.assert_array_equal(mean, 2)
    assert mean_identity["model_sha256"] != identity["model_sha256"]
    assert mean_identity["training_features_sha256"] == identity["training_features_sha256"]
    inputs["train_y"][:] = 7
    inputs["train_x"][0, -1, 3] = 1
    changed, changed_identity = s.fit_predict(**inputs)
    np.testing.assert_array_equal(changed, constant)
    assert changed_identity["model_sha256"] == identity["model_sha256"]
    assert changed_identity["training_features_sha256"] != identity["training_features_sha256"]


def test_synthetic_nonlinear_interaction_mechanics_only():
    # A balanced two-factor AND truth table is not an additive linear target.
    body = np.array([-0.1, -0.1, 0.1, 0.1])
    volume = np.array([0.0, 2.0, 0.0, 2.0])
    x = np.zeros((4, 36, 4), dtype="float64")
    x[:, :, 0] = body[:, None]
    x[:, :, 1] = np.maximum(body[:, None], 0) + 0.01
    x[:, :, 2] = np.minimum(body[:, None], 0) - 0.01
    x[:, -12:, 3] = volume[:, None]
    closes = np.full((4, 36), 100.0)
    target = np.array([-10.0, -10.0, -10.0, 10.0])
    forecast, _ = s.fit_predict(
        train_x=np.repeat(x, 128, axis=0),
        train_closes=np.repeat(closes, 128, axis=0),
        train_y=np.repeat(target, 128),
        eval_x=x,
        eval_closes=closes,
        deadline=time.monotonic() + 60,
    )
    linear_x = np.column_stack((np.ones(4), ridge.feature_matrix(x, closes)))
    linear = linear_x @ np.linalg.lstsq(linear_x, target, rcond=None)[0]
    error = np.mean((forecast - target) ** 2)
    assert error < 0.01 * np.mean((target - target.mean()) ** 2)
    assert error < 0.05 * np.mean((linear - target) ** 2)
    np.testing.assert_array_equal(forecast > 0, target > 0)


@pytest.mark.parametrize(
    "key,issue",
    [
        ("train_x", "empty"),
        ("train_x", "shape"),
        ("train_closes", "nan"),
        ("train_y", "shape"),
        ("train_y", "float32"),
        ("train_y", "inf"),
        ("eval_x", "empty"),
        ("eval_x", "nan"),
        ("eval_closes", "shape"),
    ],
)
def test_invalid_inputs_reject_before_fit(inputs, monkeypatch, key, issue):
    def forbidden(**kwargs):
        pytest.fail("invalid inputs must not fit")

    monkeypatch.setattr(s, "GradientBoostingRegressor", forbidden)
    if issue == "empty":
        inputs[key] = inputs[key][:0]
    elif issue == "shape":
        inputs[key] = inputs[key][..., None]
    elif issue == "float32":
        inputs[key] = inputs[key].astype("float32")
    else:
        inputs[key].flat[0] = np.nan if issue == "nan" else np.inf
    with pytest.raises(ValueError):
        s.fit_predict(**inputs)


@pytest.mark.parametrize("deadline", [True, None, "1", np.nan, np.inf])
def test_invalid_deadline(inputs, deadline):
    with pytest.raises(ValueError, match="^deadline_finite_required$"):
        s.fit_predict(**dict(inputs, deadline=deadline))


@pytest.mark.parametrize("stage", ["features", "fit", "hash", "predict", "return"])
def test_deadlines_surround_features_fit_and_predict(inputs, monkeypatch, stage):
    now = 2 if stage == "features" else 0
    original_features, original_hash = s.feature_matrix, s._model_sha256

    def features(*args):
        nonlocal now
        assert stage != "features", "expired deadline must not compute features"
        result = original_features(*args)
        if stage == "fit":
            now = 2
        return result

    def model_hash(model):
        nonlocal now
        assert stage != "hash", "expired fit must not hash or predict"
        result = original_hash(model)
        if stage == "predict":
            now = 2
        return result

    def boosting(**kwargs):
        nonlocal now
        assert stage != "fit", "expired features must not fit"
        model = GradientBoostingRegressor(**kwargs)
        fit, predict = model.fit, model.predict

        def finish(x, y):
            nonlocal now
            fit(x, y)
            if stage == "hash":
                now = 2
            return model

        def forecast(x):
            nonlocal now
            assert stage not in ("hash", "predict"), "expired deadline must not predict"
            result = predict(x)
            if stage == "return":
                now = 2
            return result

        model.fit, model.predict = finish, forecast
        return model

    monkeypatch.setattr(s.time, "monotonic", lambda: now)
    monkeypatch.setattr(s, "feature_matrix", features)
    monkeypatch.setattr(s, "_model_sha256", model_hash)
    monkeypatch.setattr(s, "GradientBoostingRegressor", boosting)
    with pytest.raises(TimeoutError, match="^causal_feature_boosting_deadline_exceeded$"):
        s.fit_predict(**dict(inputs, deadline=1))


@pytest.mark.parametrize("field", ["n_estimators_", "estimators_"])
def test_partial_estimator_count_is_rejected_before_predict(inputs, monkeypatch, field):
    def boosting(**kwargs):
        model = GradientBoostingRegressor(**kwargs)
        fit = model.fit

        def finish(x, y):
            fit(x, y)
            setattr(model, field, 63 if field == "n_estimators_" else model.estimators_[:-1])
            return model

        def forbidden(x):
            pytest.fail("partial model must not predict")

        model.fit, model.predict = finish, forbidden
        return model

    monkeypatch.setattr(s, "GradientBoostingRegressor", boosting)
    with pytest.raises(ValueError, match="^boosting_estimator_count$"):
        s.fit_predict(**inputs)


@pytest.mark.parametrize("stage", ["fit", "predict"])
@pytest.mark.parametrize("error", [FloatingPointError, OverflowError, ValueError])
def test_numerical_errors_have_no_raw_bodies(inputs, monkeypatch, stage, error):
    def boosting(**kwargs):
        model = GradientBoostingRegressor(**kwargs)

        def fail(*args):
            raise error("raw internal body")

        setattr(model, stage, fail)
        return model

    monkeypatch.setattr(s, "GradientBoostingRegressor", boosting)
    with pytest.raises(ValueError, match="^boosting_numerical_failure$") as caught:
        s.fit_predict(**inputs)
    assert caught.value.__suppress_context__ and caught.value.__cause__ is None


@pytest.mark.parametrize("side", ["train", "eval"])
def test_finite_features_exceeding_tree_float32_range_are_closed(inputs, side):
    inputs[f"{side}_x"][:, :, 1] = 1e40
    features = ridge.feature_matrix(inputs[f"{side}_x"], inputs[f"{side}_closes"])
    assert np.isfinite(features).all()
    with pytest.raises(ValueError, match="^boosting_numerical_failure$"):
        s.fit_predict(**inputs)


@pytest.mark.parametrize("stage", ["init", "last_tree", "predict"])
def test_nonfinite_fitted_state_and_predictions_are_rejected(inputs, monkeypatch, stage):
    def boosting(**kwargs):
        model = GradientBoostingRegressor(**kwargs)
        fit = model.fit

        def finish(x, y):
            fit(x, y)
            if stage == "init":
                model.init_.constant_[0, 0] = np.inf
            elif stage == "last_tree":
                model.estimators_[-1, 0].tree_.value[-1, 0, 0] = np.nan
            return model

        def predict(x):
            assert stage == "predict", "nonfinite model must not predict"
            return np.full(len(x), np.nan)

        model.fit, model.predict = finish, predict
        return model

    monkeypatch.setattr(s, "GradientBoostingRegressor", boosting)
    reason = "forecast_nonfinite" if stage == "predict" else "nonfinite_boosting"
    with pytest.raises(ValueError, match=f"^{reason}$"):
        s.fit_predict(**inputs)
