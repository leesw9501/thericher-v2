"""Synthetic-only fitter checks; no LightGBM install, CUDA job, or market data."""

from __future__ import annotations

import builtins
import importlib
import io
import sys
import time
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from thericher_v2.research import firstrate_family_models as models
from thericher_v2.research import firstrate_m5_h30_lstm_dev_20260921 as h30


def fold(rows=129, eval_rows=130):
    rng = np.random.default_rng(17)
    train = rng.normal(size=(rows, 36, 4)).astype(np.float32)
    evaluation = rng.normal(size=(eval_rows, 36, 4)).astype(np.float32)
    labels = np.linspace(-0.5, 1.5, rows, dtype=np.float32)
    for values in (train, evaluation, labels):
        values.setflags(write=False)
    return h30.PreparedFold(
        "SPY",
        1,
        train,
        evaluation,
        labels,
        100.0,
        20.0,
        np.zeros(4),
        np.ones(4),
        (),
        {},
    )


@pytest.fixture
def lightgbm(monkeypatch):
    calls = SimpleNamespace(params=None, fit=None, predict=[])

    class Regressor:
        def __init__(self, **kwargs):
            calls.params = kwargs
            self.booster_ = SimpleNamespace(
                model_to_string=lambda: "synthetic booster text", num_trees=lambda: 64
            )

        def fit(self, x, y):
            calls.fit = (x.copy(), y.copy())
            assert x.flags.writeable and y.flags.writeable
            x[:] = 0
            y[:] = 0

        def predict(self, x):
            calls.predict.append(x.copy())
            x[:] = 0
            return np.full(len(x), 0.25)

    module = SimpleNamespace(__version__="4.6.0", LGBMRegressor=Regressor)
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "lightgbm", module)
    return calls, module


def test_heavy_dependencies_are_lazy(monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        assert name.split(".")[0] not in {"lightgbm", "torch"}
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    importlib.reload(models)


def test_lightgbm_fixed_train_only_contract_and_no_mutation(lightgbm):
    calls, _ = lightgbm
    prepared = fold()
    before = [value.copy() for value in (prepared.train_x, prepared.eval_x, prepared.train_y)]
    predicted, text, facts = models.fit_lightgbm(prepared)
    assert calls.params == {
        "objective": "regression",
        "n_estimators": 64,
        "num_leaves": 7,
        "max_depth": 3,
        "learning_rate": 0.05,
        "min_child_samples": 64,
        "reg_lambda": 1,
        "subsample": 1,
        "colsample_bytree": 1,
        "random_state": 101,
        "n_jobs": 1,
        "deterministic": True,
        "force_col_wise": True,
        "verbosity": -1,
    }
    np.testing.assert_array_equal(calls.fit[0], prepared.train_x.reshape(129, 144))
    np.testing.assert_array_equal(calls.fit[1], prepared.train_y)
    np.testing.assert_array_equal(calls.predict[0], prepared.train_x.reshape(129, 144))
    np.testing.assert_array_equal(calls.predict[1], prepared.eval_x.reshape(130, 144))
    np.testing.assert_array_equal(predicted, np.full(130, 0.25))
    assert text == "synthetic booster text"
    y = prepared.train_y.astype(np.float64)
    assert facts == {
        "train_rows": 129,
        "eval_rows": 130,
        "tree_count": 64,
        "initial_train_mse": pytest.approx(np.mean((y - y.mean()) ** 2)),
        "final_train_mse": pytest.approx(np.mean((y - 0.25) ** 2)),
        "train_mean_baseline_mse": pytest.approx(np.mean((y - y.mean()) ** 2)),
    }
    for actual, expected in zip(
        (prepared.train_x, prepared.eval_x, prepared.train_y), before, strict=True
    ):
        np.testing.assert_array_equal(actual, expected)
        assert not actual.flags.writeable


def test_lightgbm_requires_exact_version(lightgbm):
    calls, module = lightgbm
    module.__version__ = "4.5.0"
    with pytest.raises(h30.StudyFailure, match="lightgbm_version"):
        models.fit_lightgbm(fold())
    assert calls.fit is None


def test_lightgbm_loads_torch_openmp_first(monkeypatch, lightgbm):
    imported = []
    original = builtins.__import__

    def record(name, *args, **kwargs):
        if name in {"torch", "lightgbm"}:
            imported.append(name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", record)
    models.fit_lightgbm(fold())
    assert imported == ["torch", "lightgbm"]


@pytest.mark.parametrize("field", ("train_x", "eval_x", "train_y"))
@pytest.mark.parametrize("bad", (float("nan"), float("inf"), -float("inf")))
@pytest.mark.parametrize("fitter", ("lightgbm", "sequence"))
def test_nonfinite_inputs_rejected_before_runtime(field, bad, fitter):
    prepared = fold()
    values = getattr(prepared, field).copy()
    values.flat[-1] = bad
    prepared = replace(prepared, **{field: values})
    with pytest.raises(h30.StudyFailure, match="input_dtype_or_nonfinite"):
        if fitter == "lightgbm":
            models.fit_lightgbm(prepared)
        else:
            models.fit_sequence(None, prepared, "dilated_tcn", 101, 0)


@pytest.mark.parametrize(
    "field,values,reason",
    [
        ("train_x", np.zeros((129, 35, 4), np.float32), "feature_shape"),
        ("eval_x", np.zeros((130, 36, 3), np.float32), "feature_shape"),
        ("train_x", np.zeros((129, 144), np.float32), "feature_shape"),
        ("train_x", np.zeros((0, 36, 4), np.float32), "feature_shape"),
        ("eval_x", np.zeros((0, 36, 4), np.float32), "feature_shape"),
        ("eval_x", [], "feature_shape"),
        ("train_y", np.zeros((129, 1), np.float32), "target_shape"),
        ("train_y", np.zeros(128, np.float32), "target_shape"),
        ("train_y", [0] * 129, "target_shape"),
        ("train_x", np.zeros((129, 36, 4), np.float64), "input_dtype"),
        ("eval_x", np.zeros((130, 36, 4), object), "input_dtype"),
        ("train_y", np.zeros(129, np.int32), "input_dtype"),
    ],
)
@pytest.mark.parametrize("fitter", ("lightgbm", "sequence"))
def test_geometry_and_dtype_rejected_before_runtime(field, values, reason, fitter):
    prepared = replace(fold(), **{field: values})
    with pytest.raises(h30.StudyFailure, match=reason):
        if fitter == "lightgbm":
            models.fit_lightgbm(prepared)
        else:
            models.fit_sequence(None, prepared, "dilated_tcn", 101, 0)


@pytest.mark.parametrize("call", (1, 2))
@pytest.mark.parametrize("bad", ("nan", "inf", "shape", "object"))
def test_lightgbm_rejects_invalid_predictions(monkeypatch, lightgbm, call, bad):
    _, module = lightgbm
    original = module.LGBMRegressor.predict
    count = 0

    def predict(self, values):
        nonlocal count
        count += 1
        if count != call:
            return original(self, values)
        if bad == "shape":
            return np.zeros((len(values), 1))
        if bad == "object":
            return np.zeros(len(values), dtype=object)
        return np.full(len(values), float(bad))

    monkeypatch.setattr(module.LGBMRegressor, "predict", predict)
    with pytest.raises(h30.StudyFailure, match="prediction_shape_or_nonfinite"):
        models.fit_lightgbm(fold())


def test_attention_delegates_exact_shared_geometry(monkeypatch):
    captured = {}
    sentinel = object()

    def build(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(models, "build_torch_sequence_model", build)
    assert models.build_sequence(sentinel, "compact_attention") is sentinel
    assert captured == {
        "torch": sentinel,
        "architecture_id": "compact_attention",
        "feature_count": 4,
        "hidden_size": 16,
        "attention_heads": 2,
        "tcn_kernel_size": 3,
    }


def test_sequence_rejects_unknown_architecture_and_seed():
    with pytest.raises(h30.StudyFailure, match="family_architecture"):
        models.build_sequence(None, "causal_tcn")
    for architecture, seed in (("lstm", 101), ("dilated_tcn", 102)):
        with pytest.raises(h30.StudyFailure, match="family_architecture_or_seed"):
            models.fit_sequence(None, fold(), architecture, seed, time.monotonic() + 30)


def test_sequence_requires_cuda_and_checks_deadline():
    runtime = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
    with pytest.raises(h30.StudyFailure, match="cuda_unavailable"):
        models.fit_sequence(runtime, fold(), "dilated_tcn", 101, time.monotonic() + 30)
    with pytest.raises(h30.StudyFailure, match="budget_exhausted"):
        models.fit_sequence(None, fold(), "dilated_tcn", 101, 0)


@pytest.fixture
def torch_cpu():
    torch = pytest.importorskip("torch", reason="optional synthetic PyTorch tests")
    threads = torch.get_num_threads()
    torch.set_num_threads(1)
    yield torch
    torch.set_num_threads(threads)


def test_tcn_causality_and_earliest_context_reach(torch_cpu):
    torch = torch_cpu
    model = models.build_sequence(torch, "dilated_tcn").eval()
    convolutions = [m for m in model.modules() if isinstance(m, torch.nn.Conv1d)]
    assert [m.dilation for m in convolutions] == [(d,) for d in (1, 2, 4, 8, 16)]
    assert all(m.kernel_size == (3,) and m.padding == (0,) for m in convolutions)
    assert sum(p.numel() for p in model.parameters()) == 3361
    assert 1 + sum(2 * m.dilation[0] for m in convolutions) == 63
    with torch.no_grad():
        for parameter in model.parameters():
            parameter.fill_(0.05)
        values = torch.ones((2, 36, 4))
        future = values.clone()
        future[:, 20:] += 10
        encoded = model.encoder(values.transpose(1, 2))
        changed = model.encoder(future.transpose(1, 2))
        torch.testing.assert_close(encoded[:, :, :20], changed[:, :, :20], rtol=0, atol=0)
        early = values.clone()
        early[:, 0] += 1
        assert bool((model(early) > model(values)).all())
        assert model(values).shape == (2, 1)
        assert bool(torch.isfinite(model(values)).all())


def test_shared_attention_is_fixed_and_finite(torch_cpu):
    model = models.build_sequence(torch_cpu, "compact_attention").eval()
    layer = model.encoder.layers[0]
    assert layer.self_attn.embed_dim == 16 and layer.self_attn.num_heads == 2
    assert layer.self_attn.dropout == 0
    assert all(m.p == 0 for m in model.modules() if isinstance(m, torch_cpu.nn.Dropout))
    with torch_cpu.no_grad():
        result = model(torch_cpu.zeros((2, 36, 4)))
    assert result.shape == (2, 1) and bool(torch_cpu.isfinite(result).all())


@pytest.fixture
def cpu_shim(monkeypatch, torch_cpu):
    """Explicit test-only CUDA stand-in; production has no device override."""
    torch = torch_cpu
    build = models.build_sequence
    calls = SimpleNamespace(forward=[], adamw=[], seeds=[], syncs=0, model=None, factory=build)

    def builder(_runtime, architecture):
        model = build(torch, architecture)
        calls.model = model

        def to(device):
            assert device == "cuda:0"
            return model

        def record(model, args):
            calls.forward.append(
                (args[0].detach().numpy().copy(), model.training, torch.is_grad_enabled())
            )

        monkeypatch.setattr(model, "to", to)
        model.register_forward_pre_hook(record)
        return model

    def tensor(values, *, dtype, device):
        assert device == "cuda:0" and dtype == torch.float32
        assert 0 < len(values) <= 128
        return torch.tensor(values, dtype=dtype)

    def adamw(parameters, **kwargs):
        calls.adamw.append(kwargs)
        return torch.optim.AdamW(parameters, **kwargs)

    def synchronize():
        calls.syncs += 1

    runtime = SimpleNamespace(
        cuda=SimpleNamespace(
            is_available=lambda: True,
            manual_seed_all=calls.seeds.append,
            synchronize=synchronize,
        ),
        manual_seed=torch.manual_seed,
        tensor=tensor,
        float32=torch.float32,
        isfinite=torch.isfinite,
        no_grad=torch.no_grad,
        nn=torch.nn,
        optim=SimpleNamespace(AdamW=adamw),
    )
    monkeypatch.setattr(models, "build_sequence", builder)
    return runtime, calls


@pytest.mark.parametrize("architecture", models.ARCHITECTURES)
@pytest.mark.parametrize("seed", (101, 103))
def test_sequence_fixed_training_batching_metrics_and_numeric_state(
    monkeypatch, torch_cpu, cpu_shim, architecture, seed
):
    runtime, calls = cpu_shim
    prepared = fold()
    originals = [a.copy() for a in (prepared.train_x, prepared.eval_x, prepared.train_y)]
    checks = []
    monkeypatch.setattr(h30, "check_time", checks.append)
    prediction, state, facts = models.fit_sequence(runtime, prepared, architecture, seed, 123.0)
    assert calls.seeds == [seed] and calls.syncs == 16
    assert calls.adamw == [{"lr": 0.001, "weight_decay": 0.01}]
    assert len(calls.forward) == 22 and len(checks) == 46 and set(checks) == {123.0}
    for index in range(10):
        pair = calls.forward[index * 2 : index * 2 + 2]
        np.testing.assert_array_equal(np.concatenate([p[0] for p in pair]), prepared.train_x)
        assert [p[1:] for p in pair] == [(0 < index < 9, 0 < index < 9)] * 2
    np.testing.assert_array_equal(
        np.concatenate([p[0] for p in calls.forward[-2:]]), prepared.eval_x
    )
    assert all(p[1:] == (False, False) for p in calls.forward[-2:])
    assert prediction.shape == (130,) and np.isfinite(prediction).all()
    assert facts["epochs"] == 8 and facts["updates"] == 16 and facts["train_rows"] == 129
    assert facts["parameter_count"] == sum(p.numel() for p in calls.model.parameters())
    assert all(
        np.isfinite(facts[k])
        for k in ("initial_train_mse", "final_train_mse", "train_mean_baseline_mse")
    )
    y = prepared.train_y.astype(np.float64)
    assert facts["train_mean_baseline_mse"] == pytest.approx(np.mean((y - y.mean()) ** 2))
    with torch_cpu.no_grad():
        final = calls.model(torch_cpu.tensor(prepared.train_x)).flatten().numpy()
    assert facts["final_train_mse"] == pytest.approx(np.mean((final.astype(np.float64) - y) ** 2))
    assert set(state) == {"state." + key for key in calls.model.state_dict()}
    assert all(a.dtype == np.float32 and np.isfinite(a).all() for a in state.values())
    archive = io.BytesIO()
    np.savez(archive, **state)
    archive.seek(0)
    with np.load(archive, allow_pickle=False) as saved:
        for name, expected in state.items():
            np.testing.assert_array_equal(saved[name], expected)
        restored = calls.factory(torch_cpu, architecture).eval()
        restored.load_state_dict(
            {name.removeprefix("state."): torch_cpu.from_numpy(saved[name]) for name in saved},
            strict=True,
        )
    torch_cpu.manual_seed(seed)
    initial_model = calls.factory(torch_cpu, architecture).eval()
    with torch_cpu.no_grad():
        reloaded = restored(torch_cpu.tensor(prepared.eval_x)).flatten().numpy()
        initial = initial_model(torch_cpu.tensor(prepared.train_x)).flatten().numpy()
    np.testing.assert_allclose(prediction, reloaded, rtol=1e-5, atol=1e-6)
    assert facts["initial_train_mse"] == pytest.approx(
        np.mean((initial.astype(np.float64) - y) ** 2)
    )
    for name, parameter in calls.model.state_dict().items():
        assert not np.shares_memory(state["state." + name], parameter.numpy())
    for actual, expected in zip(
        (prepared.train_x, prepared.eval_x, prepared.train_y), originals, strict=True
    ):
        np.testing.assert_array_equal(actual, expected)
        assert not actual.flags.writeable


@pytest.mark.parametrize("failure", ("loss", "gradient", "deadline"))
def test_sequence_stops_on_bad_training_or_midfit_deadline(
    monkeypatch, torch_cpu, cpu_shim, failure
):
    runtime, calls = cpu_shim
    if failure == "loss":
        runtime.nn = SimpleNamespace(MSELoss=lambda: lambda x, y: (x - y).mean() * float("nan"))
    elif failure == "gradient":
        original = models.build_sequence

        def bad_gradient(*args):
            model = original(*args)
            next(model.parameters()).register_hook(lambda grad: grad * float("nan"))
            return model

        monkeypatch.setattr(models, "build_sequence", bad_gradient)
    else:
        checks = 0

        def expire(_deadline):
            nonlocal checks
            checks += 1
            if checks == 8:
                raise h30.StudyFailure("budget_exhausted")

        monkeypatch.setattr(h30, "check_time", expire)
    reason = "budget_exhausted" if failure == "deadline" else "nonfinite_" + failure
    with pytest.raises(h30.StudyFailure, match=reason):
        models.fit_sequence(runtime, fold(), "dilated_tcn", 101, time.monotonic() + 30)
    assert calls.syncs == (1 if failure == "deadline" else 0)
