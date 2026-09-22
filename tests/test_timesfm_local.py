from __future__ import annotations

import builtins
import hashlib
import importlib
import json
import os
import stat
import sys
import traceback
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from thericher_v2.research import timesfm_local as adapter


@pytest.fixture
def local_model(tmp_path):
    directory = tmp_path / "model"
    directory.mkdir()
    # The public 2.5 model card's config, not a downloaded fixture.
    config = {
        "architectures": ["TimesFmModelForPrediction"],
        "context_length": 16384,
        "head_dim": 80,
        "hidden_size": 1280,
        "horizon_length": 128,
        "intermediate_size": 1280,
        "model_type": "timesfm",
        "num_attention_heads": 16,
        "num_hidden_layers": 20,
        "patch_length": 32,
        "quantile_horizon_length": 1024,
        "quantiles": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
        "rms_norm_eps": 1e-6,
        "torch_compile": False,
    }
    (directory / "config.json").write_text(json.dumps(config), encoding="utf-8")
    (directory / "model.safetensors").write_bytes(b"mock-safetensors-only")
    return directory, _hashes(directory)


def _hashes(directory):
    return {
        name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
        for name in ("config.json", "model.safetensors")
    }


@pytest.fixture
def no_backend_import(monkeypatch):
    original = builtins.__import__
    attempts = []

    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in {"torch", "timesfm", "timesfm3", "huggingface_hub"}:
            attempts.append(name)
            raise AssertionError("optional backend imported before validation")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    return attempts


@pytest.fixture
def backend(monkeypatch):
    state = SimpleNamespace(
        available=True,
        calls=[],
        inference=False,
        allocation=None,
        output=None,
        failure=None,
        misplaced=None,
    )

    class Device:
        def __init__(self, name):
            self.type, _, self.index = name.partition(":")
            self.name = name

        def __eq__(self, other):
            return isinstance(other, Device) and self.name == other.name

        def __enter__(self):
            self.previous = state.allocation
            state.allocation = self.name
            return self

        def __exit__(self, *args):
            state.allocation = self.previous

    class Module:
        def __init__(self):
            self.device = Device("cuda:0" if state.available else "cpu")
            self.device_count = 4 if state.available else 1
            self.parameter = SimpleNamespace(device=Device("cpu"))
            self.buffer = SimpleNamespace(device=Device("cpu"))

        def eval(self):
            state.calls.append("eval")

        def requires_grad_(self, enabled):
            assert enabled is False
            state.calls.append("no_grad")

        def parameters(self):
            return iter([self.parameter])

        def buffers(self):
            return iter([self.buffer])

    class TimesFM:
        def __init__(self, *, torch_compile, config):
            assert state.allocation == "cpu"
            assert torch_compile is False
            state.model_config = config
            self.model = Module()
            state.model = self

        @classmethod
        def from_pretrained(cls, *args, **kwargs):
            raise AssertionError("Hub loader must not be called")

        def load_checkpoint(self, path, **kwargs):
            assert state.allocation == "cpu"
            state.calls.append(("load", path, kwargs))
            state.calls.append(("weights", self.model.device.name, self.model.device_count))
            self.model.parameter.device = self.model.device
            self.model.buffer.device = self.model.device
            if state.misplaced is not None:
                getattr(self.model, state.misplaced).device = Device("cuda:3")

        def compile(self, config):
            state.config = config

        def forecast(self, *, horizon, inputs):
            assert state.inference is True
            state.inputs = [value.copy() for value in inputs]
            count = len(inputs)
            # Official base implementation may append batch padding to this list.
            inputs.append(np.zeros(3, dtype=np.float32))
            if state.failure:
                raise RuntimeError(state.failure)
            if state.output is not None:
                return state.output
            full = np.broadcast_to(np.arange(10.0), (count, horizon, 10)).copy()
            return full[..., 5], full

    @contextmanager
    def inference_mode():
        state.inference = True
        try:
            yield
        finally:
            state.inference = False

    def cuda_available():
        state.calls.append("cuda_available")
        return state.available

    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(
            device=Device,
            cuda=SimpleNamespace(is_available=cuda_available),
            inference_mode=inference_mode,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "timesfm",
        SimpleNamespace(
            TimesFM_2p5_200M_torch=TimesFM,
            ForecastConfig=SimpleNamespace,
        ),
    )

    def forbidden_hub(*args, **kwargs):
        raise AssertionError("Hub must not be called")

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(
            hf_hub_download=forbidden_hub,
            snapshot_download=forbidden_hub,
            get_token=forbidden_hub,
        ),
    )
    return state


def test_import_does_not_load_optional_backends(no_backend_import):
    importlib.reload(adapter)
    assert no_backend_import == []


@pytest.mark.parametrize("device", ["cpu", "cuda"])
@pytest.mark.parametrize("horizon", [1, 32])
def test_local_load_placement_and_forecast(local_model, backend, device, horizon):
    contexts = [np.arange(256, dtype=np.float64), np.array([7.0])]
    points, quantiles = adapter.forecast_timesfm_2p5(*local_model, contexts, horizon, device)
    assert points.shape == (2, horizon)
    assert quantiles.shape == (2, horizon, 10)
    assert adapter.QUANTILE_LEVELS == tuple(x / 10 for x in range(1, 10))
    np.testing.assert_array_equal(points, quantiles[..., 5])
    np.testing.assert_array_equal(quantiles[0, 0], np.arange(10))
    load = next(call for call in backend.calls if isinstance(call, tuple) and call[0] == "load")
    assert load == ("load", str(local_model[0].absolute()), {})
    assert backend.model_config == json.loads((local_model[0] / "config.json").read_text())
    target = "cpu" if device == "cpu" else "cuda:0"
    assert ("weights", target, 1) in backend.calls
    assert "eval" in backend.calls and "no_grad" in backend.calls
    assert ("cuda_available" in backend.calls) == (device == "cuda")
    assert backend.config.max_context == 256
    assert backend.config.max_horizon == 32
    assert backend.config.per_core_batch_size == 2
    assert backend.config.return_backcast is False
    assert backend.config.use_continuous_quantile_head is True
    assert backend.config.infer_is_positive is False
    assert len(contexts) == 2
    assert contexts[0].dtype == np.float64
    assert all(value.dtype == np.float32 for value in backend.inputs)
    assert not np.shares_memory(contexts[0], backend.inputs[0])
    assert backend.allocation is None and backend.inference is False


def test_batched_array_is_accepted(local_model, backend):
    points, _ = adapter.forecast_timesfm_2p5(*local_model, np.ones((33, 3)), 2, "cpu")
    assert points.shape == (33, 2)
    assert backend.config.per_core_batch_size == 32


def test_pinned_wheel_is_allowed_but_never_read(local_model, backend, monkeypatch):
    wheel = local_model[0] / "timesfm-2.0.2-py3-none-any.whl"
    wheel.write_bytes(b"inert wheel verified only by external runner")
    original = Path.open

    def guarded(path, *args, **kwargs):
        assert path != wheel, "adapter must not load the wheel"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)
    points, _ = adapter.forecast_timesfm_2p5(*local_model, [[1]], 1, "cpu")
    assert points.shape == (1, 1)


def test_missing_cuda_never_loads_or_falls_back(local_model, backend):
    backend.available = False
    with pytest.raises(RuntimeError, match="CUDA is unavailable; no CPU fallback"):
        adapter.forecast_timesfm_2p5(*local_model, [[1]], 1, "cuda")
    assert backend.calls == ["cuda_available"]


@pytest.mark.parametrize("misplaced", ["parameter", "buffer"])
def test_wrong_actual_device_is_rejected(local_model, backend, misplaced):
    backend.misplaced = misplaced
    with pytest.raises(RuntimeError, match="local inference failed"):
        adapter.forecast_timesfm_2p5(*local_model, [[1]], 1, "cpu")
    assert not hasattr(backend, "inputs")


@pytest.mark.parametrize("horizon", [0, -1, 33, True, 1.5, "1", None, np.int64(1)])
def test_invalid_horizon_before_import(local_model, no_backend_import, horizon):
    with pytest.raises(ValueError, match="horizon"):
        adapter.forecast_timesfm_2p5(*local_model, [[1]], horizon, "cpu")
    assert no_backend_import == []


@pytest.mark.parametrize("device", ["gpu", "cuda:0", "CPU", None, []])
def test_invalid_device_before_import(local_model, no_backend_import, device):
    with pytest.raises(ValueError, match="device"):
        adapter.forecast_timesfm_2p5(*local_model, [[1]], 1, device)
    assert no_backend_import == []


@pytest.mark.parametrize(
    "contexts",
    [
        [],
        [[]],
        [[1] * 257],
        [[np.nan]],
        [[np.inf]],
        [[-np.inf]],
        [[1e100]],
        [[True]],
        [[1j]],
        [["private-context"]],
        [1, 2],
        [[[1]]],
        None,
        "private-context",
        np.array(1),
        {"private-context": [1]},
        iter([[1]]),
        [[object()]],
    ],
)
def test_invalid_contexts_before_import(local_model, no_backend_import, contexts):
    with pytest.raises(ValueError, match="contexts") as caught:
        adapter.forecast_timesfm_2p5(*local_model, contexts, 1, "cpu")
    assert "private-context" not in "".join(traceback.format_exception(caught.value))
    assert no_backend_import == []


@pytest.mark.parametrize(
    "model_id",
    [
        "google/timesfm-3.0-pytorch",
        "google/timesfm-2.0-500m-pytorch",
        "model.pkl",
        None,
    ],
)
def test_only_25_model_id_is_allowed(local_model, no_backend_import, model_id):
    with pytest.raises(ValueError, match="model ID"):
        adapter.forecast_timesfm_2p5(*local_model, [[1]], 1, "cpu", model_id=model_id)
    assert no_backend_import == []


@pytest.mark.parametrize(
    "hashes",
    [
        None,
        {},
        {"config.json": "0" * 64},
        {
            "config.json": "0" * 64,
            "model.safetensors": "not-a-hash",
        },
        {"config.json": "0" * 64, "model.safetensors": 1},
        {
            "config.json": "0" * 64,
            "model.safetensors": "0" * 64,
            "extra": "0" * 64,
        },
    ],
)
def test_exact_hash_contract_is_required(local_model, no_backend_import, hashes):
    with pytest.raises(ValueError, match="SHA256"):
        adapter.forecast_timesfm_2p5(local_model[0], hashes, [[1]], 1, "cpu")
    assert no_backend_import == []


@pytest.mark.parametrize("filename", ["config.json", "model.safetensors"])
def test_hash_mismatch_before_import(local_model, no_backend_import, filename):
    (local_model[0] / filename).write_bytes(b"changed")
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        adapter.forecast_timesfm_2p5(*local_model, [[1]], 1, "cpu")
    assert no_backend_import == []


@pytest.mark.parametrize("filename", ["config.json", "model.safetensors"])
def test_missing_file_before_import(local_model, no_backend_import, filename):
    (local_model[0] / filename).unlink()
    with pytest.raises(ValueError, match="missing"):
        adapter.forecast_timesfm_2p5(*local_model, [[1]], 1, "cpu")
    assert no_backend_import == []


@pytest.mark.parametrize(
    "filename",
    [
        "pytorch_model.bin",
        "model.pkl",
        "model.pt",
        "model.ckpt",
        "model.py",
        "timesfm3.json",
    ],
)
def test_unallowlisted_file_before_import(local_model, no_backend_import, filename):
    (local_model[0] / filename).write_bytes(b"unsupported")
    with pytest.raises(ValueError, match="unsupported file"):
        adapter.forecast_timesfm_2p5(*local_model, [[1]], 1, "cpu")
    assert no_backend_import == []


@pytest.mark.parametrize("config", ["private-json-error", "[]", "{}", '{"model_type":"timesfm3"}'])
def test_malformed_or_wrong_config_even_when_hash_matches(local_model, no_backend_import, config):
    directory = local_model[0]
    (directory / "config.json").write_text(config, encoding="utf-8")
    with pytest.raises(ValueError) as caught:
        adapter.forecast_timesfm_2p5(directory, _hashes(directory), [[1]], 1, "cpu")
    assert "private-json-error" not in "".join(traceback.format_exception(caught.value))
    assert no_backend_import == []


def test_empty_weights_even_when_hash_matches(local_model, no_backend_import):
    directory = local_model[0]
    (directory / "model.safetensors").write_bytes(b"")
    with pytest.raises(ValueError, match="empty"):
        adapter.forecast_timesfm_2p5(directory, _hashes(directory), [[1]], 1, "cpu")
    assert no_backend_import == []


@pytest.mark.parametrize("kind", ["missing", "file", "parent_traversal"])
def test_not_a_local_directory(local_model, no_backend_import, kind):
    directory, hashes = local_model
    path = {
        "missing": directory / "missing",
        "file": directory / "config.json",
        "parent_traversal": directory / ".." / "model",
    }[kind]
    with pytest.raises(ValueError):
        adapter.forecast_timesfm_2p5(path, hashes, [[1]], 1, "cpu")
    assert no_backend_import == []


def test_hardlinked_weights_rejected(local_model, no_backend_import, tmp_path):
    os.link(local_model[0] / "model.safetensors", tmp_path / "linked.safetensors")
    with pytest.raises(ValueError, match="links"):
        adapter.forecast_timesfm_2p5(*local_model, [[1]], 1, "cpu")
    assert no_backend_import == []


@pytest.mark.parametrize("location", ["ancestor", "directory", "weights", "config"])
@pytest.mark.parametrize("kind", ["symlink", "reparse"])
def test_links_are_checked_before_resolving(
    local_model, no_backend_import, monkeypatch, location, kind
):
    directory = local_model[0]
    linked = {
        "ancestor": directory.parent,
        "directory": directory,
        "weights": directory / "model.safetensors",
        "config": directory / "config.json",
    }[location]
    original = Path.lstat

    def linked_stat(path, *args, **kwargs):
        info = original(path, *args, **kwargs)
        if path == linked:
            return SimpleNamespace(
                st_mode=stat.S_IFLNK if kind == "symlink" else info.st_mode,
                st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT if kind == "reparse" else 0,
                st_nlink=1,
            )
        return info

    monkeypatch.setattr(Path, "lstat", linked_stat)
    with pytest.raises(ValueError, match="links"):
        adapter.forecast_timesfm_2p5(*local_model, [[1]], 1, "cpu")
    assert no_backend_import == []


@pytest.mark.parametrize(
    "output",
    [
        (np.zeros((2, 1)), np.zeros((1, 1, 10))),
        (np.zeros((1, 2)), np.zeros((1, 1, 10))),
        (np.zeros((1, 1)), np.zeros((1, 1, 9))),
        (np.zeros((1, 1)), np.zeros((1, 2, 10))),
        (np.zeros((1, 1)), np.zeros((2, 1, 10))),
        (np.array([[np.nan]]), np.zeros((1, 1, 10))),
        (np.zeros((1, 1)), np.full((1, 1, 10), np.inf)),
        (np.array([["private-prediction"]]), np.zeros((1, 1, 10))),
        (np.zeros((1, 1), dtype=complex), np.zeros((1, 1, 10))),
        (np.zeros((1, 1)),),
    ],
)
def test_invalid_outputs_are_rejected_without_values(local_model, backend, output):
    backend.output = output
    with pytest.raises(ValueError, match="output shape or values") as caught:
        adapter.forecast_timesfm_2p5(*local_model, [[1]], 1, "cpu")
    assert "private-prediction" not in "".join(traceback.format_exception(caught.value))


def test_backend_errors_do_not_disclose_contexts_or_predictions(local_model, backend):
    backend.failure = "private-context private-prediction"
    with pytest.raises(RuntimeError, match="local inference failed") as caught:
        adapter.forecast_timesfm_2p5(*local_model, [[1]], 1, "cpu")
    formatted = "".join(traceback.format_exception(caught.value))
    assert "private-context" not in formatted and "private-prediction" not in formatted


def test_no_adapter_environment_or_auth_access(local_model, backend, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("environment access is forbidden")

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "getenv", forbidden)
        scoped.setattr(type(os.environ), "__getitem__", forbidden)
        scoped.setattr(type(os.environ), "get", forbidden)
        points, _ = adapter.forecast_timesfm_2p5(*local_model, [[1]], 1, "cpu")
    assert points.shape == (1, 1)
