"""Synthetic-only checks of the fixed causal features and one TRAIN-only fit."""

from __future__ import annotations

import inspect
import socket
import time

import numpy as np
import pytest
from sklearn.linear_model import Ridge

from thericher_v2.research import causal_feature_ridge as s
from thericher_v2.research.policy_graph_models import _hash


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("network forbidden")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)


def windows(count, seed=811):
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
    train_x, train_closes = windows(64)
    eval_x, eval_closes = windows(7, seed=812)
    return dict(
        train_x=train_x,
        train_closes=train_closes,
        train_y=3 + 100 * train_x[:, -1, 0] - train_x[:, -5, 3],
        eval_x=eval_x,
        eval_closes=eval_closes,
        deadline=time.monotonic() + 60,
    )


def test_exact_simple_values_and_column_order():
    x = np.zeros((1, 36, 4), dtype="float64")
    x[:, :, 0] = 0.25
    x[:, :, 1] = 0.5
    x[:, :, 2] = -0.25
    x[:, :, 3] = np.arange(36)
    closes = np.full((1, 36), 8.0)
    closes[0, -3:] = [8, 16, 8]
    actual = s.feature_matrix(x, closes)
    assert s.WINDOWS == (3, 12, 36)
    assert isinstance(s.FEATURES, tuple) and len(set(s.FEATURES)) == 15
    assert s.FEATURES == tuple(
        f"{name}_{w}"
        for w in (3, 12, 36)
        for name in (
            "window_return",
            "close_return_std",
            "mean_range",
            "mean_body",
            "logvolume_contrast",
        )
    )
    # Close returns are 1 and -1/2, plus w-3 zeros. Their mean is 0.5/(w-1).
    expected = [
        0.25,
        0.75,
        0.75,
        0.25,
        1.0,
        0.25,
        np.sqrt(1.25 / 11 - (0.5 / 11) ** 2),
        0.75,
        0.25,
        4.0,
        0.25,
        np.sqrt(1.25 / 35 - (0.5 / 35) ** 2),
        0.75,
        0.25,
        12.0,
    ]
    assert actual.shape == (1, 15) and actual.dtype == np.dtype("float64")
    np.testing.assert_allclose(actual[0], expected, rtol=1e-14)


def test_exact_varying_means_without_reconstructing_volume():
    x = np.zeros((1, 36, 4), dtype="float64")
    steps = np.arange(36)
    x[0, :, 0] = steps / 128 - 0.125
    x[0, :, 1] = steps / 64 + 0.25
    x[0, :, 2] = -0.5
    x[0, :, 3] = 1000 + steps  # expm1 would overflow; these log values are valid.
    actual = s.feature_matrix(x, np.full((1, 36), 8.0))
    expected = []
    for window in (3, 12, 36):
        mean_step = (71 - window) / 2
        expected.extend(
            (
                (36 - window) / 128 - 0.125,
                0,
                mean_step / 64 + 0.75,
                mean_step / 128 - 0.125,
                window / 3,
            )
        )
    np.testing.assert_allclose(actual[0], expected, rtol=1e-14, atol=1e-16)


def test_flat_zero_volume_and_zero_train_std(inputs):
    for key in ("train_x", "eval_x"):
        inputs[key][:] = 0
    for key in ("train_closes", "eval_closes"):
        inputs[key][:] = 8
    inputs["train_y"][:] = 7
    np.testing.assert_array_equal(s.feature_matrix(inputs["train_x"], inputs["train_closes"]), 0)
    forecast, identity = s.fit_predict(**inputs)
    np.testing.assert_array_equal(forecast, 7)
    assert identity["scaler_sha256"] == _hash(np.zeros(15), np.ones(15))


def test_price_scale_invariance_per_row(inputs):
    x, closes = windows(9)
    scales = np.geomspace(1e-6, 1e6, 9)[:, None]
    np.testing.assert_allclose(
        s.feature_matrix(x, closes * scales), s.feature_matrix(x, closes), rtol=1e-11, atol=1e-15
    )
    first, _ = s.fit_predict(**inputs)
    second, _ = s.fit_predict(
        **dict(
            inputs,
            train_closes=inputs["train_closes"] * 32,
            eval_closes=inputs["eval_closes"] / 8,
        )
    )
    np.testing.assert_array_equal(first, second)


def test_rows_are_independent_and_future_appends_do_not_change_prefix():
    x, closes = windows(8)
    expected = s.feature_matrix(x, closes)
    for row in range(len(x)):
        np.testing.assert_array_equal(
            s.feature_matrix(x[row : row + 1], closes[row : row + 1])[0], expected[row]
        )
    changed_x, changed_closes = x.copy(), closes.copy()
    changed_x[4:], changed_closes[4:] = windows(4, seed=991)
    np.testing.assert_array_equal(s.feature_matrix(changed_x, changed_closes)[:4], expected[:4])
    future_x, future_closes = windows(5, seed=992)
    appended = s.feature_matrix(
        np.concatenate((x, future_x)), np.concatenate((closes, future_closes))
    )
    np.testing.assert_array_equal(appended[:8], expected)
    np.testing.assert_array_equal(s.feature_matrix(x[::-1], closes[::-1]), expected[::-1])


@pytest.mark.parametrize("window,columns", [(3, 5), (12, 10)])
def test_short_windows_ignore_every_older_bar(window, columns):
    x, closes = windows(4)
    expected = s.feature_matrix(x, closes)
    changed_x, changed_closes = windows(4, seed=992)
    changed_x[:, -window:] = x[:, -window:]
    changed_closes[:, -window:] = closes[:, -window:]
    actual = s.feature_matrix(changed_x, changed_closes)
    np.testing.assert_array_equal(actual[:, :columns], expected[:, :columns])
    assert not np.array_equal(actual[:, columns:], expected[:, columns:])


def test_first_open_is_specific_to_each_window():
    x = np.zeros((1, 36, 4), dtype="float64")
    x[:, :, 1] = 0.5
    x[0, [-3, -12, -36], 0] = [0.125, 0.25, 0.5]
    actual = s.feature_matrix(x, np.full((1, 36), 8.0))
    np.testing.assert_allclose(actual[0, [0, 5, 10]], [0.125, 0.25, 0.5])


def test_one_exact_ridge_train_only_scaling_and_hashes(inputs, monkeypatch):
    calls = []

    def ridge(**kwargs):
        assert kwargs == dict(alpha=1.0, solver="svd", fit_intercept=True)
        model = Ridge(**kwargs)
        fit = model.fit

        def capture(x, y):
            calls.append((x.copy(), y.copy()))
            return fit(x, y)

        model.fit = capture
        return model

    monkeypatch.setattr(s, "Ridge", ridge)
    forecast, identity = s.fit_predict(**inputs)
    assert len(calls) == 1
    features = s.feature_matrix(inputs["train_x"], inputs["train_closes"])
    mean, scale = features.mean(axis=0), features.std(axis=0, ddof=0)
    scale = np.where(scale == 0, 1.0, scale)
    train = (features - mean) / scale
    evaluation = (s.feature_matrix(inputs["eval_x"], inputs["eval_closes"]) - mean) / scale
    np.testing.assert_array_equal(calls[0][0], train)
    np.testing.assert_array_equal(calls[0][1], inputs["train_y"])
    expected = Ridge(alpha=1.0, solver="svd", fit_intercept=True).fit(train, inputs["train_y"])
    np.testing.assert_array_equal(forecast, expected.predict(evaluation))
    assert identity == dict(
        scaler_sha256=_hash(mean, scale),
        model_sha256=_hash(expected.coef_, np.asarray(expected.intercept_)),
    )
    assert forecast.shape == (7,) and forecast.dtype == np.dtype("float64")
    assert not forecast.flags.writeable
    with pytest.raises(ValueError):
        forecast[0] = 0


def test_eval_changes_cannot_change_scaler_or_model_identity(inputs):
    _, first = s.fit_predict(**inputs)
    eval_x, eval_closes = windows(19, seed=990)
    eval_x[:, :, 3] += 500
    _, second = s.fit_predict(**dict(inputs, eval_x=eval_x, eval_closes=eval_closes))
    assert first == second


def test_eval_future_append_cannot_change_earlier_forecasts(inputs):
    first, identity = s.fit_predict(**inputs)
    future_x, future_closes = windows(5, seed=992)
    second, second_identity = s.fit_predict(
        **dict(
            inputs,
            eval_x=np.concatenate((inputs["eval_x"], future_x)),
            eval_closes=np.concatenate((inputs["eval_closes"], future_closes)),
        )
    )
    np.testing.assert_allclose(second[: len(first)], first, rtol=1e-14, atol=1e-14)
    assert identity == second_identity


def test_deterministic_immutable_inputs_and_no_eval_target_api(inputs):
    before = {k: v.copy() for k, v in inputs.items() if isinstance(v, np.ndarray)}
    for value in inputs.values():
        if isinstance(value, np.ndarray):
            value.setflags(write=False)
    first, first_identity = s.fit_predict(**inputs)
    second, second_identity = s.fit_predict(**inputs)
    np.testing.assert_array_equal(first, second)
    assert first_identity == second_identity
    for key, value in before.items():
        np.testing.assert_array_equal(inputs[key], value)
    assert tuple(inspect.signature(s.fit_predict).parameters) == (
        "train_x",
        "train_closes",
        "train_y",
        "eval_x",
        "eval_closes",
        "deadline",
    )
    with pytest.raises(TypeError):
        s.fit_predict(**inputs, eval_y=np.zeros(7))


@pytest.mark.parametrize("key", ["train_x", "train_closes", "train_y", "eval_x", "eval_closes"])
@pytest.mark.parametrize("issue", ["shape", "float32", "integer", "list", "nan", "inf"])
def test_invalid_arrays_reject_before_fit(inputs, monkeypatch, key, issue):
    def forbidden(**kwargs):
        pytest.fail("invalid inputs must not fit")

    monkeypatch.setattr(s, "Ridge", forbidden)
    value = inputs[key]
    if issue == "shape":
        inputs[key] = value[..., None]
    elif issue in ("float32", "integer"):
        inputs[key] = value.astype("float32" if issue == "float32" else "int64")
    elif issue == "list":
        inputs[key] = value.tolist()
    else:
        value.flat[0] = np.nan if issue == "nan" else np.inf
    with pytest.raises(ValueError):
        s.fit_predict(**inputs)


@pytest.mark.parametrize("key", ["train_x", "train_closes", "train_y", "eval_x", "eval_closes"])
def test_mismatched_row_counts_rejected(inputs, key):
    inputs[key] = inputs[key][:-1]
    with pytest.raises(ValueError):
        s.fit_predict(**inputs)


@pytest.mark.parametrize("side", ["train", "eval"])
def test_empty_fit_partition_rejected(inputs, side):
    inputs[f"{side}_x"] = inputs[f"{side}_x"][:0]
    inputs[f"{side}_closes"] = inputs[f"{side}_closes"][:0]
    if side == "train":
        inputs["train_y"] = inputs["train_y"][:0]
    with pytest.raises(ValueError, match="empty_input"):
        s.fit_predict(**inputs)


@pytest.mark.parametrize("shape", [(2, 35, 4), (2, 37, 4), (2, 36, 5), (2, 36)])
def test_fixed_context_and_channel_shape(shape):
    with pytest.raises(ValueError, match="x_shape"):
        s.feature_matrix(np.zeros(shape), np.ones((2, 36)))


@pytest.mark.parametrize(
    "bar",
    [
        [-1, 0, -1, 0],
        [-1.1, 0, -1.1, 0],
        [0, 0, -1, 0],
        [0.1, 0.05, 0, 0],
        [-0.2, 0, -0.1, 0],
        [-0.2, -0.1, -0.3, 0],
        [0.2, 0.3, 0.1, 0],
        [0, -0.1, 0.1, 0],
    ],
)
@pytest.mark.parametrize("side", ["train", "eval"])
def test_invalid_normalized_ohlc(inputs, side, bar):
    inputs[f"{side}_x"][0, 0] = bar
    with pytest.raises(ValueError, match="invalid_normalized_ohlc"):
        s.fit_predict(**inputs)


@pytest.mark.parametrize("value", [0, -1])
@pytest.mark.parametrize("side", ["train", "eval"])
def test_nonpositive_closes(inputs, side, value):
    inputs[f"{side}_closes"][0, 0] = value
    with pytest.raises(ValueError, match="closes_positive_required"):
        s.fit_predict(**inputs)


@pytest.mark.parametrize("side", ["train", "eval"])
def test_negative_logvolume(inputs, side):
    inputs[f"{side}_x"][0, 0, 3] = -0.001
    with pytest.raises(ValueError, match="logvolume_nonnegative_required"):
        s.fit_predict(**inputs)


@pytest.mark.parametrize("issue", ["first_open", "close_ratio", "return_std", "range", "volume"])
def test_finite_inputs_that_overflow_features_are_closed(issue):
    x = np.zeros((1, 36, 4), dtype="float64")
    closes = np.full((1, 36), 8.0)
    if issue == "first_open":
        closes[:] = np.finfo("float64").max
        x[:, :, 0] = x[:, :, 2] = -0.5
    elif issue == "close_ratio":
        closes[0, -2:] = [1e-300, 1e300]
    elif issue == "return_std":
        closes[0, -1] = 1e200
    elif issue == "range":
        x[:, :, 1] = np.finfo("float64").max
    else:
        x[:, :, 3] = np.finfo("float64").max
    with pytest.raises(ValueError, match="^nonfinite_features$"):
        s.feature_matrix(x, closes)


def test_scaler_overflow_rejected_before_fit(inputs, monkeypatch):
    inputs["train_x"][:, :, 1] = 0
    inputs["train_x"][:, :, 0] = 0
    inputs["train_x"][0, :, 1] = 1e200

    def forbidden(**kwargs):
        pytest.fail("overflowing scaler must not fit")

    monkeypatch.setattr(s, "Ridge", forbidden)
    assert np.isfinite(s.feature_matrix(inputs["train_x"], inputs["train_closes"])).all()
    with pytest.raises(ValueError, match="^nonfinite_scaler$"):
        s.fit_predict(**inputs)


@pytest.mark.parametrize("deadline", [True, None, "1", np.nan, np.inf, -np.inf])
def test_invalid_deadline(inputs, deadline):
    with pytest.raises(ValueError, match="deadline_finite_required"):
        s.fit_predict(**dict(inputs, deadline=deadline))


def test_expired_deadline_rejects_before_features(inputs, monkeypatch):
    def forbidden(*args):
        pytest.fail("expired deadline must not compute features")

    monkeypatch.setattr(s, "feature_matrix", forbidden)
    monkeypatch.setattr(s.time, "monotonic", lambda: 1)
    with pytest.raises(TimeoutError, match="causal_feature_ridge_deadline_exceeded"):
        s.fit_predict(**dict(inputs, deadline=1))


def test_deadline_checked_immediately_before_fit(inputs, monkeypatch):
    ticks = iter([0, 1])
    monkeypatch.setattr(s.time, "monotonic", lambda: next(ticks))

    def forbidden(**kwargs):
        pytest.fail("deadline expired during features/scaling must not fit")

    monkeypatch.setattr(s, "Ridge", forbidden)
    with pytest.raises(TimeoutError):
        s.fit_predict(**dict(inputs, deadline=1))


def test_deadline_checked_after_fit_before_predict(inputs, monkeypatch):
    expired = False

    def ridge(**kwargs):
        model = Ridge(**kwargs)
        fit = model.fit

        def finish(x, y):
            nonlocal expired
            fit(x, y)
            expired = True
            return model

        def forbidden(x):
            pytest.fail("expired fit must not predict")

        model.fit = finish
        model.predict = forbidden
        return model

    monkeypatch.setattr(s, "Ridge", ridge)
    monkeypatch.setattr(s.time, "monotonic", lambda: 2 if expired else 0)
    with pytest.raises(TimeoutError):
        s.fit_predict(**dict(inputs, deadline=1))


@pytest.mark.parametrize("stage", ["fit", "predict"])
@pytest.mark.parametrize("failure", ["overflow", "nonfinite"])
def test_fit_and_predict_numerical_failures_are_closed(inputs, monkeypatch, stage, failure):
    def ridge(**kwargs):
        model = Ridge(**kwargs)
        fit = model.fit

        def finish(x, y):
            if stage == "fit" and failure == "overflow":
                raise FloatingPointError("internal details")
            fit(x, y)
            if stage == "fit":
                model.coef_[0] = np.inf
            return model

        def predict(x):
            if failure == "overflow":
                raise FloatingPointError("internal details")
            return np.full(len(x), np.nan)

        model.fit = finish
        if stage == "predict":
            model.predict = predict
        return model

    monkeypatch.setattr(s, "Ridge", ridge)
    reason = (
        "ridge_numerical_failure"
        if failure == "overflow"
        else "nonfinite_ridge"
        if stage == "fit"
        else "forecast_nonfinite"
    )
    with pytest.raises(ValueError, match=f"^{reason}$"):
        s.fit_predict(**inputs)
