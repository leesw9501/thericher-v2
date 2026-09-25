"""Synthetic-only fixed fitter checks; no real CUDA, market data or artifact writes."""

from __future__ import annotations

import builtins
import importlib
import io
import time
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from thericher_v2.research import firstrate_family_comparison as comparison
from thericher_v2.research import firstrate_m5_h30_lstm_dev_20260921 as h30
from thericher_v2.research import session_sequence_models as models


def fold(rows=129, eval_rows=130):
    rng = np.random.default_rng(17)
    arrays = (
        rng.normal(size=(rows, 36, 4)).astype(np.float32),
        rng.normal(size=(eval_rows, 36, 4)).astype(np.float32),
        np.linspace(-0.5, 1.5, rows, dtype=np.float32),
    )
    for values in arrays:
        values.setflags(write=False)
    return h30.PreparedFold("SYNTHETIC", 1, *arrays, 100.0, 20.0, np.zeros(4), np.ones(4), (), {})


def test_import_does_not_load_torch(monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        assert name.split(".")[0] != "torch"
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    importlib.reload(models)


@pytest.mark.parametrize("field", ("train_x", "eval_x", "train_y"))
@pytest.mark.parametrize("bad", (np.nan, np.inf, -np.inf))
def test_nonfinite_inputs_fail_before_runtime(field, bad):
    prepared = fold()
    values = getattr(prepared, field).copy()
    values.flat[-1] = bad
    with pytest.raises(h30.StudyFailure, match="input_dtype_or_nonfinite"):
        models.fit(None, replace(prepared, **{field: values}), "dilated_tcn", 101, 0)


@pytest.mark.parametrize(
    "field,values,reason",
    [
        ("train_x", np.zeros((1, 35, 4), np.float32), "feature_shape"),
        ("eval_x", np.zeros((1, 36, 3), np.float32), "feature_shape"),
        ("train_x", np.zeros((1, 144), np.float32), "feature_shape"),
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
def test_geometry_and_dtype_fail_before_runtime(field, values, reason):
    with pytest.raises(h30.StudyFailure, match=reason):
        models.fit(None, replace(fold(), **{field: values}), "dilated_tcn", 101, 0)


@pytest.mark.parametrize(
    "architecture,seed", [("lstm", 101), ("dilated_tcn", 102), ("compact_attention", 101.0)]
)
def test_frozen_architecture_and_seed(architecture, seed):
    with pytest.raises(h30.StudyFailure, match="architecture_or_seed"):
        models.fit(None, fold(), architecture, seed, time.monotonic() + 30)


@pytest.mark.parametrize("deadline", [np.nan, np.inf, -np.inf, "later"])
def test_nonfinite_deadline_rejected(deadline):
    with pytest.raises(h30.StudyFailure, match="session_deadline"):
        models.fit(None, fold(), "dilated_tcn", 101, deadline)


def test_cuda_and_deadline_required():
    runtime = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
    with pytest.raises(h30.StudyFailure, match="cuda_unavailable"):
        models.fit(runtime, fold(), "dilated_tcn", 101, time.monotonic() + 30)
    with pytest.raises(h30.StudyFailure, match="budget_exhausted"):
        models.fit(None, fold(), "dilated_tcn", 101, 0)
    for value in (
        SimpleNamespace(is_cuda=False),
        SimpleNamespace(is_cuda=True, device=SimpleNamespace(index=1)),
    ):
        with pytest.raises(h30.StudyFailure, match="cuda_device_required"):
            models._require_cuda(value)


@pytest.fixture
def torch_cpu():
    torch = pytest.importorskip("torch", reason="optional synthetic CPU-only Torch tests")
    threads = torch.get_num_threads()
    torch.set_num_threads(1)
    yield torch
    torch.set_num_threads(threads)


@pytest.fixture
def cpu_shim(monkeypatch, torch_cpu):
    """Only tests replace device placement; production has no CPU fallback."""
    torch = torch_cpu
    factory = models.family.build_sequence
    calls = SimpleNamespace(
        uploads=[],
        forward=[],
        optimizer=[],
        seeds=[],
        syncs=0,
        resets=[],
        model=None,
        allocations=[],
        steps=0,
    )

    def build(_runtime, architecture):
        model = factory(torch, architecture)
        calls.model = model

        def to(device):
            assert device == "cuda:0"
            return model

        def record(model, args):
            calls.forward.append(
                (
                    args[0].detach().numpy().copy(),
                    model.training,
                    torch.is_grad_enabled(),
                    args[0].untyped_storage().data_ptr(),
                )
            )

        monkeypatch.setattr(model, "to", to)
        model.register_forward_pre_hook(record)
        return model

    def tensor(values, *, dtype, device):
        assert device == "cuda:0" and dtype == torch.float32
        result = torch.tensor(values, dtype=dtype)
        calls.uploads.append((values.copy(), result.untyped_storage().data_ptr()))
        return result

    def allocate(method):
        def inner(*args, device, **kwargs):
            assert device == "cuda:0"
            calls.allocations.append(method)
            return getattr(torch, method)(*args, **kwargs)

        return inner

    def adamw(parameters, **kwargs):
        calls.optimizer.append(kwargs)
        optimizer = torch.optim.AdamW(parameters, **kwargs)
        step = optimizer.step

        def counted_step():
            calls.steps += 1
            return step()

        monkeypatch.setattr(optimizer, "step", counted_step)
        return optimizer

    def synchronize(device):
        assert device == "cuda:0"
        calls.syncs += 1

    runtime = SimpleNamespace(
        cuda=SimpleNamespace(
            is_available=lambda: True,
            manual_seed_all=calls.seeds.append,
            synchronize=synchronize,
            reset_peak_memory_stats=calls.resets.append,
            max_memory_allocated=lambda device: 123456 if device == "cuda:0" else None,
        ),
        manual_seed=torch.manual_seed,
        tensor=tensor,
        float32=torch.float32,
        float64=torch.float64,
        isfinite=torch.isfinite,
        no_grad=torch.no_grad,
        empty=allocate("empty"),
        zeros=allocate("zeros"),
        nn=torch.nn,
        optim=SimpleNamespace(AdamW=adamw),
    )
    monkeypatch.setattr(models.family, "build_sequence", build)
    monkeypatch.setattr(models, "_require_cuda", lambda value: None)
    return runtime, calls


@pytest.mark.parametrize("architecture", models.ARCHITECTURES)
@pytest.mark.parametrize("seed", models.SEEDS)
def test_full_fixed_fit_preloads_once_and_roundtrips(
    monkeypatch, torch_cpu, cpu_shim, architecture, seed
):
    runtime, calls = cpu_shim
    prepared = fold()
    originals = [a.copy() for a in (prepared.train_x, prepared.train_y, prepared.eval_x)]
    checks = []
    monkeypatch.setattr(h30, "check_time", checks.append)

    class InputsOnly:
        train_x, train_y, eval_x = prepared.train_x, prepared.train_y, prepared.eval_x

        def __getattr__(self, name):
            raise AssertionError(f"Fitter accessed non-input field: {name}")

    prediction, state, facts = models.fit(runtime, InputsOnly(), architecture, seed, 123.0)
    assert calls.seeds == [seed] and calls.resets == ["cuda:0"]
    assert calls.optimizer == [{"lr": 0.001, "weight_decay": 0.01}]
    assert len(calls.uploads) == 3
    for upload, original in zip(calls.uploads, originals, strict=True):
        np.testing.assert_array_equal(upload[0], original)
    assert facts["epochs"] == 32 and facts["updates"] == calls.steps == 64
    assert facts["train_rows"] == 129 and facts["peak_cuda_memory_bytes"] == 123456
    assert facts["parameter_count"] == sum(p.numel() for p in calls.model.parameters())
    assert len(calls.forward) == 70 and calls.syncs == 71
    assert len(checks) == 143 and set(checks) == {123.0}
    for index in range(34):
        pair = calls.forward[2 * index : 2 * index + 2]
        np.testing.assert_array_equal(np.concatenate([p[0] for p in pair]), prepared.train_x)
        assert [p[1:3] for p in pair] == [(0 < index < 33, 0 < index < 33)] * 2
        assert all(p[3] == calls.uploads[0][1] for p in pair)
    evaluation = calls.forward[-2:]
    np.testing.assert_array_equal(np.concatenate([p[0] for p in evaluation]), prepared.eval_x)
    assert all(p[1:3] == (False, False) for p in evaluation)
    assert all(p[3] == calls.uploads[2][1] for p in evaluation)
    assert prediction.shape == (130,) and prediction.dtype == np.float32
    assert np.isfinite(prediction).all()
    assert set(facts) == {
        "epochs",
        "updates",
        "train_rows",
        "initial_train_mse",
        "final_train_mse",
        "train_mean_baseline_mse",
        "parameter_count",
        "peak_cuda_memory_bytes",
    }
    targets = prepared.train_y.astype(np.float64)
    assert facts["train_mean_baseline_mse"] == pytest.approx(np.var(targets))
    with torch_cpu.no_grad():
        final = calls.model(torch_cpu.tensor(prepared.train_x)).flatten().numpy()
    assert facts["final_train_mse"] == pytest.approx(
        np.mean((final.astype(np.float64) - targets) ** 2), rel=1e-5
    )
    assert set(state) == {"state." + k for k in calls.model.state_dict()}
    assert all(v.dtype == np.float32 and np.isfinite(v).all() for v in state.values())
    archive = io.BytesIO()
    np.savez(archive, **state)
    archive.seek(0)
    # Restore the real builder before testing the existing consumer, not a new loader.
    monkeypatch.undo()
    with np.load(archive, allow_pickle=False) as saved:
        restored = comparison.restore_sequence(torch_cpu, architecture, dict(saved))
    reloaded = comparison.sequence_predict(torch_cpu, restored, prepared.eval_x)
    np.testing.assert_allclose(prediction, reloaded, rtol=1e-5, atol=1e-6)
    for threshold in (0.0, 0.3, -0.3):
        np.testing.assert_array_equal(prediction > threshold, reloaded > threshold)
    torch_cpu.manual_seed(seed)
    initial_model = models.family.build_sequence(torch_cpu, architecture)
    initial = comparison.sequence_predict(torch_cpu, initial_model, prepared.train_x)
    assert facts["initial_train_mse"] == pytest.approx(
        np.mean((initial.astype(np.float64) - targets) ** 2), rel=1e-5
    )
    for name, value in calls.model.state_dict().items():
        assert not np.shares_memory(state["state." + name], value.numpy())
    for actual, original in zip(
        (prepared.train_x, prepared.train_y, prepared.eval_x), originals, strict=True
    ):
        np.testing.assert_array_equal(actual, original)
        assert not actual.flags.writeable


@pytest.mark.parametrize("failure", ["loss", "gradient", "deadline", "shape", "prediction"])
def test_invalid_training_stops_without_result(monkeypatch, torch_cpu, cpu_shim, failure):
    runtime, calls = cpu_shim
    reason = "nonfinite_" + failure
    if failure == "loss":
        runtime.nn = SimpleNamespace(MSELoss=lambda: lambda x, y: (x - y).mean() * np.nan)
    elif failure in ("gradient", "shape", "prediction"):
        original = models.family.build_sequence

        def broken(*args):
            model = original(*args)
            if failure == "gradient":
                next(model.parameters()).register_hook(lambda grad: grad * np.nan)
            elif failure == "shape":
                model.register_forward_hook(lambda model, args, output: output.flatten())
            else:
                model.register_forward_hook(lambda model, args, output: output * np.nan)
            return model

        monkeypatch.setattr(models.family, "build_sequence", broken)
        if failure != "gradient":
            reason = "prediction_shape_or_nonfinite"
    else:
        checks = 0

        def expire(deadline):
            nonlocal checks
            checks += 1
            if checks == 8:
                raise h30.StudyFailure("budget_exhausted")

        monkeypatch.setattr(h30, "check_time", expire)
        reason = "budget_exhausted"
    with pytest.raises(h30.StudyFailure, match=reason):
        models.fit(runtime, fold(), "dilated_tcn", 101, time.monotonic() + 60)
    assert calls.steps == (1 if failure == "deadline" else 0)
