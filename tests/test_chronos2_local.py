from __future__ import annotations

import builtins
import hashlib
import importlib.util
import json
import sys
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from thericher_v2.research import chronos2_local as adapter


def context(series="SPY", *, offset=0, length=128, values=None):
    origin = datetime(2026, 1, 5, tzinfo=UTC) + timedelta(days=offset)
    times = tuple(origin - timedelta(days=length - i) for i in range(length))
    return adapter.Chronos2Context(
        series,
        origin,
        times,
        origin - timedelta(hours=1),
        np.linspace(-10, 10, length) if values is None else values,
    )


def trio():
    return [
        context(series, values=np.arange(128) + i) for i, series in enumerate(("SPY", "QQQ", "IWM"))
    ]


class Tensor:
    def __init__(self, values):
        self.values = np.asarray(values)

    def detach(self):
        return self

    def cpu(self):
        return self

    def numpy(self):
        return self.values


@pytest.fixture
def model_files(tmp_path, monkeypatch):
    directory = tmp_path / "model"
    directory.mkdir()
    config = {"architectures": ["Chronos2Model"], "chronos_pipeline_class": "Chronos2Pipeline"}
    (directory / "config.json").write_text(json.dumps(config), encoding="utf-8")
    (directory / "model.safetensors").write_bytes(b"synthetic-not-real-weights")
    pins = {
        name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
        for name in adapter.CHRONOS2_SHA256
    }
    sizes = {name: (directory / name).stat().st_size for name in pins}
    monkeypatch.setattr(adapter, "CHRONOS2_SHA256", pins)
    monkeypatch.setattr(adapter, "CHRONOS2_SIZES", sizes)
    return directory, pins


@pytest.fixture
def no_backend(monkeypatch):
    original = builtins.__import__
    attempts = []

    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in {"torch", "chronos", "safetensors", "transformers"}:
            attempts.append(name)
            raise AssertionError("backend imported before validation")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    return attempts


@pytest.fixture
def backend(monkeypatch):
    state = SimpleNamespace(
        calls=[],
        available=True,
        allocation=None,
        inference=False,
        failure=None,
        output=None,
        safe_calls=[],
    )

    class Device:
        def __init__(self, name):
            self.name = name

        def __eq__(self, other):
            return isinstance(other, Device) and self.name == other.name

        def __enter__(self):
            self.previous = state.allocation
            state.allocation = self.name
            return self

        def __exit__(self, *args):
            state.allocation = self.previous

    class Model:
        def __init__(self, config):
            assert state.allocation == "cpu"
            state.config = config
            state.model = self
            self.training = True
            self.parameter = SimpleNamespace(device=Device("cpu"), requires_grad=True)
            self.buffer = SimpleNamespace(device=Device("cpu"))

        def load_state_dict(self, tensors, *, strict):
            assert strict is True and tensors == {"synthetic": True}
            state.strict_load = True

        def eval(self):
            self.training = False

        def requires_grad_(self, value):
            self.parameter.requires_grad = value

        def to(self, *, device, dtype):
            assert dtype == "float32"
            self.parameter.device = self.buffer.device = device

        def parameters(self):
            return iter([self.parameter])

        def buffers(self):
            return iter([self.buffer])

        @classmethod
        def from_pretrained(cls, *args, **kwargs):
            raise AssertionError("No Hub or remote-code loader")

    class Pipeline:
        def __init__(self, *, model):
            self.model = model

        def predict_quantiles(self, **kwargs):
            assert state.inference and state.allocation == "cpu"
            assert kwargs.keys() == {
                "inputs",
                "prediction_length",
                "quantile_levels",
                "batch_size",
                "context_length",
                "cross_learning",
                "limit_prediction_length",
            }
            assert kwargs["limit_prediction_length"] is True
            assert kwargs["context_length"] == 256
            assert kwargs["batch_size"] == len(kwargs["inputs"])
            assert all(a.ndim == 1 and a.dtype == np.float32 for a in kwargs["inputs"])
            state.calls.append(kwargs)
            if state.failure:
                raise RuntimeError(state.failure)
            if state.output is not None:
                return state.output
            count, h = len(kwargs["inputs"]), kwargs["prediction_length"]
            last = np.array([a[-1] for a in kwargs["inputs"]])
            if kwargs["cross_learning"]:
                last = np.repeat(last.mean(), count)
            q = [Tensor(np.broadcast_to(v + np.arange(9) - 4, (1, h, 9)).copy()) for v in last]
            p = [Tensor(a.values[..., 4]) for a in q]
            return q, p

    @contextmanager
    def inference_mode():
        state.inference = True
        try:
            yield
        finally:
            state.inference = False

    def load_file(path, *, device):
        assert state.allocation == "cpu" and device == "cpu"
        assert Path(path).name == "model.safetensors"
        state.safe_calls.append((path, device))
        return {"synthetic": True}

    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(
            device=Device,
            float32="float32",
            inference_mode=inference_mode,
            cuda=SimpleNamespace(is_available=lambda: state.available),
        ),
    )
    monkeypatch.setitem(sys.modules, "chronos", SimpleNamespace(Chronos2Pipeline=Pipeline))
    monkeypatch.setitem(sys.modules, "chronos.chronos2", SimpleNamespace(Chronos2Model=Model))
    monkeypatch.setitem(
        sys.modules,
        "chronos.chronos2.config",
        SimpleNamespace(
            Chronos2CoreConfig=lambda **kwargs: kwargs,
        ),
    )
    monkeypatch.setitem(sys.modules, "safetensors", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "safetensors.torch", SimpleNamespace(load_file=load_file))
    monkeypatch.setattr(adapter, "_require_offline_runtime", lambda: None)
    monkeypatch.setattr(adapter, "version", lambda name: adapter.PINNED_RUNTIME[name])
    return state


def load(model_files):
    return adapter.load_chronos2_local(model_files[0], model_files[1], device="cpu")


def test_official_identity_without_weights_access():
    assert adapter.MODEL_ID == "amazon/chronos-2"
    assert adapter.REVISION == "95a9710e2596287d08352589f42634fa5abdf0a7"
    assert adapter.MODEL_PINS == adapter.CHRONOS2_SHA256
    assert set(adapter.MODEL_PINS) == {"config.json", "model.safetensors"}
    assert (
        adapter.MODEL_RELATIVE_ROOT.as_posix() == f"foundation-models/chronos-2/{adapter.REVISION}"
    )
    assert datetime.fromisoformat(adapter.CHRONOS2_CHECKPOINT_DATE) < context().forecast_origin


@pytest.mark.parametrize("device", ["cpu", "cuda"])
def test_direct_safe_loader_and_reuse(model_files, backend, device):
    runtime = adapter.load_chronos2_local(*model_files, device=device)
    assert backend.config["attn_implementation"] == "sdpa"
    assert backend.strict_load and len(backend.safe_calls) == 1
    assert not backend.model.training and not backend.model.parameter.requires_grad
    assert backend.model.parameter.device.name == ("cpu" if device == "cpu" else "cuda:0")
    for mode in ("isolated", "same_origin_trio"):
        points, quantiles = runtime.forecast(trio(), 1, mode=mode)
        assert points.shape == (3, 1) and quantiles.shape == (3, 1, 9)
        np.testing.assert_array_equal(points, quantiles[..., 4])
    assert len(backend.safe_calls) == 1
    assert [a["cross_learning"] for a in backend.calls] == [False, True]


def test_later_origin_extreme_values_cannot_leak(model_files, backend):
    runtime = load(model_files)
    earlier, later = context(), context("QQQ", offset=3)
    first = runtime.forecast([earlier], 1)[0]
    later_extreme = replace(later, values=np.repeat(1e20, 128))
    mixed = runtime.forecast([earlier, later_extreme], 1)[0]
    np.testing.assert_array_equal(first[0], mixed[0])
    calls = len(backend.calls)
    with pytest.raises(ValueError, match="one origin"):
        runtime.forecast([earlier, later_extreme, context("IWM")], 1, mode="same_origin_trio")
    assert len(backend.calls) == calls


def test_mutating_same_origin_peer_changes_group_but_not_isolated(model_files, backend):
    runtime = load(model_files)
    inputs = trio()
    isolated = runtime.forecast(inputs, 1)[0]
    grouped = runtime.forecast(inputs, 1, mode="same_origin_trio")[0]
    inputs[1] = replace(inputs[1], values=np.repeat(1e6, 128))
    np.testing.assert_array_equal(isolated[0], runtime.forecast(inputs, 1)[0][0])
    assert not np.array_equal(
        grouped[0], runtime.forecast(inputs, 1, mode="same_origin_trio")[0][0]
    )


@pytest.mark.parametrize("horizon", [0, -1, 33, True, 1.0, "1", None])
def test_invalid_horizon_before_prediction(model_files, backend, horizon):
    with pytest.raises(ValueError, match="horizon"):
        load(model_files).forecast([context()], horizon)
    assert not backend.calls


@pytest.mark.parametrize("mode", [None, True, [], "grouped", "cross_learning"])
def test_invalid_mode(model_files, backend, mode):
    with pytest.raises(ValueError, match="mode"):
        load(model_files).forecast(trio(), 1, mode=mode)
    assert not backend.calls


@pytest.mark.parametrize("contexts", [[], None, "SPY", [None], [context()] * 33])
def test_invalid_task_records(contexts):
    with pytest.raises(ValueError):
        adapter._validated_contexts(contexts, "isolated")


@pytest.mark.parametrize("count", [1, 2, 4, 6])
def test_trio_cardinality(count):
    with pytest.raises(ValueError, match="exactly one trio"):
        adapter._validated_contexts([context(str(i)) for i in range(count)], "same_origin_trio")


@pytest.mark.parametrize(
    "field,value",
    [
        ("series_id", ""),
        ("series_id", 7),
        ("forecast_origin", datetime(2026, 1, 5)),
        ("forecast_origin", "2026-01-05"),
        ("available_at", datetime(2026, 1, 6, tzinfo=UTC)),
        ("available_at", datetime(2025, 1, 1, tzinfo=UTC)),
        ("timestamps", []),
        ("timestamps", [datetime(2026, 1, 5, tzinfo=UTC)]),
        ("timestamps", [datetime(2026, 1, 4, tzinfo=UTC)] * 128),
        ("timestamps", [datetime(2026, 1, 4)] * 128),
        ("timestamps", "2026-01-04"),
        ("values", np.zeros((1, 128))),
        ("values", [True] * 128),
        ("values", ["0"] * 128),
        ("values", [complex(1)] * 128),
        ("values", [float("nan")] * 128),
        ("values", [float("inf")] * 128),
        ("values", [1e300] * 128),
        ("values", [0] * 127),
    ],
)
def test_invalid_context_fields(field, value):
    with pytest.raises(ValueError):
        adapter._validated_contexts([replace(context(), **{field: value})], "isolated")


def test_reversed_timestamps_and_duplicate_identity():
    item = context()
    with pytest.raises(ValueError, match="timing"):
        adapter._validated_contexts([replace(item, timestamps=item.timestamps[::-1])], "isolated")
    with pytest.raises(ValueError, match="duplicate"):
        adapter._validated_contexts([item, item], "isolated")
    assert len(adapter._validated_contexts([item, context(offset=1)], "isolated")) == 2


@pytest.mark.parametrize("length", [0, 257])
def test_no_silent_context_truncation(length):
    with pytest.raises(ValueError):
        adapter._validated_contexts([context(length=length)], "isolated")


def test_trio_requires_entire_timestamp_alignment():
    inputs = trio()
    times = list(inputs[1].timestamps)
    times[5] += timedelta(hours=1)
    inputs[1] = replace(inputs[1], timestamps=times)
    with pytest.raises(ValueError, match="identical past timestamps"):
        adapter._validated_contexts(inputs, "same_origin_trio")


def test_float_copy_preserves_input_and_caller_order(model_files, backend):
    inputs = trio()[::-1]
    originals = [x.values.copy() for x in inputs]
    points, _ = load(model_files).forecast(inputs, 32)
    np.testing.assert_array_equal(points[:, 0], [x[-1] for x in originals])
    backend.calls[0]["inputs"][0][:] = 0
    for item, original in zip(inputs, originals, strict=True):
        np.testing.assert_array_equal(item.values, original)


@pytest.mark.parametrize("bad_device", ["auto", "cuda:1", "mps", None, []])
def test_invalid_device_before_import(model_files, no_backend, bad_device):
    with pytest.raises(ValueError, match="device"):
        adapter.load_chronos2_local(model_files[0], device=bad_device)
    assert not no_backend


def test_caller_cannot_substitute_weights(model_files, no_backend):
    with pytest.raises(ValueError, match="caller hashes"):
        adapter.load_chronos2_local(model_files[0], {"model.safetensors": "0" * 64})
    assert not no_backend


@pytest.mark.parametrize("name", ["config.json", "model.safetensors"])
def test_tampering_fails_before_backend(model_files, no_backend, name):
    path = model_files[0] / name
    data = bytearray(path.read_bytes())
    data[-1] ^= 1
    path.write_bytes(data)
    with pytest.raises(ValueError, match="SHA256"):
        adapter.load_chronos2_local(model_files[0])
    assert not no_backend


@pytest.mark.parametrize(
    "name",
    [
        "model.bin",
        "pytorch_model.bin",
        "adapter_config.json",
        "model.py",
        "model.safetensors.index.json",
        "subdirectory",
    ],
)
def test_reject_extra_load_paths(model_files, no_backend, name):
    path = model_files[0] / name
    if name == "subdirectory":
        path.mkdir()
    else:
        path.write_bytes(b"inert")
    with pytest.raises(ValueError, match="unsupported"):
        adapter.load_chronos2_local(model_files[0])
    assert not no_backend


def test_reject_links_and_parent_traversal(model_files):
    directory = model_files[0]
    link = directory / "LICENSE"
    link.hardlink_to(directory / "model.safetensors")
    try:
        with pytest.raises(ValueError, match="links"):
            adapter._verified_directory(directory)
    finally:
        link.unlink()
    with pytest.raises(ValueError, match="local"):
        adapter._verified_directory(directory / ".." / "model")


def test_required_files_missing_or_wrong_size(model_files):
    path = model_files[0] / "model.safetensors"
    path.write_bytes(b"")
    with pytest.raises(ValueError, match="size"):
        adapter._verified_directory(model_files[0])
    path.unlink()
    with pytest.raises(ValueError, match="missing"):
        adapter._verified_directory(model_files[0])


@pytest.mark.parametrize("name", adapter.PINNED_RUNTIME)
def test_exact_dependency_versions_required(monkeypatch, name):
    monkeypatch.setattr(
        adapter, "version", lambda key: "wrong" if key == name else adapter.PINNED_RUNTIME[key]
    )
    with pytest.raises(RuntimeError, match="runtime differs"):
        adapter._require_dependencies()


@pytest.mark.parametrize("interfaces", ["lo: 0", "lo: 0\neth0: 0", "", "wlan0: 0"])
def test_network_namespace_check(monkeypatch, interfaces):
    monkeypatch.setattr(adapter.sys, "platform", "linux")
    for key, value in adapter._OFFLINE_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(Path, "read_text", lambda *args, **kwargs: interfaces)
    if interfaces == "lo: 0":
        adapter._require_offline_runtime()
    else:
        with pytest.raises(RuntimeError, match="network=none"):
            adapter._require_offline_runtime()


@pytest.mark.parametrize("key", adapter._OFFLINE_ENV)
def test_offline_flags_required(monkeypatch, key):
    monkeypatch.setattr(adapter.sys, "platform", "linux")
    for name, value in adapter._OFFLINE_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv(key)
    with pytest.raises(RuntimeError, match="offline flags"):
        adapter._require_offline_runtime()


def test_network_rechecked_on_each_forecast(model_files, backend, monkeypatch):
    runtime = load(model_files)

    def online():
        raise RuntimeError("network=none required")

    monkeypatch.setattr(adapter, "_require_offline_runtime", online)
    with pytest.raises(RuntimeError, match="network=none"):
        runtime.forecast([context()], 1)
    assert not backend.calls


def test_no_cuda_fallback(model_files, backend):
    backend.available = False
    with pytest.raises(RuntimeError, match="no fallback"):
        adapter.load_chronos2_local(model_files[0], device="cuda")
    assert not backend.safe_calls


@pytest.mark.parametrize("mutation", ["training", "requires_grad", "parameter", "buffer"])
def test_mutated_model_rejected(model_files, backend, mutation):
    runtime = load(model_files)
    if mutation == "training":
        backend.model.training = True
    elif mutation == "requires_grad":
        backend.model.parameter.requires_grad = True
    else:
        getattr(backend.model, mutation).device = None
    with pytest.raises(ValueError, match="frozen"):
        runtime.forecast([context()], 1)
    assert not backend.calls


@pytest.mark.parametrize("kind", ["empty", "count", "shape", "nan", "median", "boolean"])
def test_bad_backend_outputs(model_files, backend, kind):
    q = np.zeros((1, 1, 9))
    p = np.zeros((1, 1))
    if kind == "empty":
        backend.output = ([], [])
    elif kind == "count":
        backend.output = ([Tensor(q), Tensor(q)], [Tensor(p), Tensor(p)])
    else:
        if kind == "shape":
            q = np.zeros((1, 9, 1))
        elif kind == "nan":
            q[0, 0, 0] = np.nan
        elif kind == "median":
            p[:] = 1
        elif kind == "boolean":
            q, p = q.astype(bool), p.astype(bool)
        backend.output = ([Tensor(q)], [Tensor(p)])
    with pytest.raises(ValueError, match="output"):
        load(model_files).forecast([context()], 1)


def test_backend_error_is_redacted(model_files, backend):
    backend.failure = "unnecessary row values or path"
    with pytest.raises(RuntimeError, match="offline inference failed") as error:
        load(model_files).forecast([context()], 1)
    assert backend.failure not in str(error.value) and error.value.__suppress_context__


@pytest.fixture
def prepare_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "prepare_chronos2_model.py"
    spec = importlib.util.spec_from_file_location("prepare_chronos2", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_acquisition_preserves_existing_partial(tmp_path, prepare_script):
    path = tmp_path / "asset"
    partial = tmp_path / "asset.partial"
    partial.write_bytes(b"other-owned")
    with pytest.raises(FileExistsError):
        prepare_script._download("https://example.invalid/", path, 10)
    assert partial.read_bytes() == b"other-owned"


def test_storage_floor_is_projected(tmp_path, monkeypatch, prepare_script):
    monkeypatch.setattr(
        prepare_script.shutil,
        "disk_usage",
        lambda path: SimpleNamespace(
            free=160,
            total=1000,
        ),
    )
    with pytest.raises(ValueError, match="15 percent"):
        prepare_script._storage_floor(tmp_path, 11)
    with pytest.warns(UserWarning, match="20 percent"):
        prepare_script._storage_floor(tmp_path, 10)


def test_existing_asset_hash_and_no_network(tmp_path, prepare_script):
    path = tmp_path / "asset"
    path.write_bytes(b"official")
    digest = hashlib.sha256(b"official").hexdigest()
    receipt = prepare_script._download("https://example.invalid/", path, 8, digest)
    assert receipt["sha256"] == digest
    with pytest.raises(ValueError, match="immutable asset"):
        prepare_script._download("https://example.invalid/", path, 8, "0" * 64)
