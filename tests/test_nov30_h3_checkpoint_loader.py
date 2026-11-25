import hashlib
import io
import sys
from types import MappingProxyType, ModuleType

import numpy as np
import pytest

from thericher_v2.research import nov30_h3_checkpoint_loader as loader

KEYS = tuple(f"20261130|{i:02d}" for i in range(17))
SCALE = 0.03734792272176389
SELF_SOURCE = b"""
import torch

class EntryCritic(torch.nn.Module):
    def __init__(self, kind):
        assert kind == 'SELF'
        super().__init__()
        self.weight = torch.nn.Parameter(torch.zeros(1))

    def forward(self, x):
        assert not self.training and torch.is_inference_mode_enabled()
        assert x.device.type == 'cpu' and x.dtype == torch.float32
        return self.weight * x[:, :, -1]
"""
OLD60_SOURCE = b"""
import torch

class HorizonModel(torch.nn.Module):
    def __init__(self, kind):
        assert kind == 'LSTM'
        super().__init__()
        self.weight = torch.nn.Parameter(torch.zeros(3))

    def forward(self, x, z):
        assert not self.training and torch.is_inference_mode_enabled()
        assert x.device.type == z.device.type == 'cpu'
        assert x.dtype == z.dtype == torch.float32
        return x[:, -1, 0, None] * self.weight + z[:, :1]
"""
ENTRY_IO = b"SENTINEL = 'pinned private dependency'\n"
ADAPTER = b"""
import numpy as np
from entry_io import SENTINEL

def adapt(a, stats):
    assert SENTINEL == 'pinned private dependency'
    assert not a['x'].flags.writeable
    x = ((a['x'].astype(np.float64) - stats['mean']) / stats['std']).astype(np.float32)
    z = ((a['z'] - stats['zmean']) / stats['zstd']).astype(np.float32)
    return dict(features=np.concatenate((x.reshape(17, 720), z), axis=1)[None, ...],
                key=a['key'], date_known=np.asarray([a['known'].all()]))
"""


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _fit(**overrides):
    fields = dict(
        mean=np.full(12, 2.0),
        std=np.full(12, 2.0),
        zmean=np.full(8, 3.0),
        zstd=np.full(8, 4.0),
        scale=np.array(SCALE),
    )
    buffer = io.BytesIO()
    np.savez(buffer, **(fields | overrides))
    return buffer.getvalue()


@pytest.fixture
def synthetic(monkeypatch):
    torch = pytest.importorskip("torch")
    safetensors = pytest.importorskip("safetensors.torch")
    blobs = dict(
        self_source=SELF_SOURCE,
        self_checkpoint=safetensors.save({"weight": torch.tensor([2.0])}),
        old60_source=OLD60_SOURCE,
        old60_checkpoint=safetensors.save({"weight": torch.tensor([11.0, 13.0, -3.0])}),
        fit=_fit(),
        entry_io=ENTRY_IO,
        input_adapter=ADAPTER,
    )
    own = loader.H3ModelPin(_sha(blobs["self_source"]), _sha(blobs["self_checkpoint"]))
    old = loader.H3ModelPin(_sha(blobs["old60_source"]), _sha(blobs["old60_checkpoint"]))
    monkeypatch.setattr(loader, "SELF_PIN", own)
    monkeypatch.setattr(loader, "OLD60_PIN", old)
    monkeypatch.setattr(loader, "FIT_SHA256", _sha(blobs["fit"]))
    monkeypatch.setattr(loader, "_ADAPTER_SHA256", _sha(ADAPTER))
    monkeypatch.setattr(loader, "_ENTRY_IO_SHA256", _sha(ENTRY_IO))
    monkeypatch.setattr(loader.h3_shadow_point, "MODEL_SHA", old.source_sha256)
    monkeypatch.setattr(loader.h3_shadow_point, "WEIGHTS_SHA", old.checkpoint_sha256)
    monkeypatch.setattr(loader.h3_shadow_point, "STATS_SHA", loader.FIT_SHA256)
    return blobs


@pytest.fixture
def arrays():
    row = np.arange(17, dtype=np.float64)
    x = np.broadcast_to((2 * row + 2).astype(np.float32)[:, None, None], (17, 60, 12))
    z = np.broadcast_to((4 * row + 3)[:, None], (17, 8))
    return MappingProxyType(
        dict(
            x=x,
            z=z,
            key=np.array(KEYS),
            known=np.ones(17, dtype=bool),
            entry_index=np.zeros(17, dtype=np.int64),
            context_close=np.full(17, "2026-11-27T18:00:00+00:00"),
            decision_at=np.full(17, "2026-11-30T14:25:00+00:00"),
        )
    )


def test_callback_preserves_axis_heads_and_scale(synthetic, arrays, monkeypatch):
    decoy = ModuleType("entry_io")
    monkeypatch.setitem(sys.modules, "entry_io", decoy)
    forward = loader.make_nov30_h3_forward(**synthetic)
    for name, pin, slope in (("SELF", loader.SELF_PIN, 2), ("OLD60", loader.OLD60_PIN, -2)):
        scores = forward(name, pin, loader.FIT_SHA256, arrays)
        assert tuple(scores) == KEYS
        assert all(type(score) is float for score in scores.values())
        assert list(scores.values()) == [slope * i * SCALE for i in range(17)]
    assert sys.modules["entry_io"] is decoy


@pytest.mark.parametrize(
    "artifact",
    [
        "self_source",
        "self_checkpoint",
        "old60_source",
        "old60_checkpoint",
        "fit",
        "input_adapter",
        "entry_io",
    ],
)
def test_rejects_substituted_or_mutable_buffers(synthetic, artifact):
    with pytest.raises(ValueError, match="digest_mismatch"):
        loader.make_nov30_h3_forward(**(synthetic | {artifact: synthetic[artifact] + b" "}))
    with pytest.raises(ValueError, match="digest_mismatch"):
        loader.make_nov30_h3_forward(**(synthetic | {artifact: bytearray(synthetic[artifact])}))


def test_rejects_repacked_self_with_same_tensors(synthetic):
    from safetensors.torch import load, save

    repacked = save(load(synthetic["self_checkpoint"]), metadata={"repacked": "true"})
    with pytest.raises(ValueError, match="self_checkpoint_digest_mismatch"):
        loader.make_nov30_h3_forward(**(synthetic | {"self_checkpoint": repacked}))


@pytest.mark.parametrize("extra", ["optimizer.0.step", "rng.cpu", "weight", "unknown.slot"])
def test_exact_training_bundle_selects_only_model_state(synthetic, arrays, monkeypatch, extra):
    import torch
    from safetensors.torch import save

    raw = save({"model.weight": torch.tensor([2.0]), extra: torch.tensor([9.0])})
    monkeypatch.setattr(loader, "SELF_PIN", loader.H3ModelPin(_sha(SELF_SOURCE), _sha(raw)))
    forward = loader.make_nov30_h3_forward(**(synthetic | {"self_checkpoint": raw}))
    if extra.startswith(("optimizer.", "rng.")):
        scores = forward("SELF", loader.SELF_PIN, loader.FIT_SHA256, arrays)
        assert list(scores.values()) == [2 * i * SCALE for i in range(17)]
    else:
        with pytest.raises(ValueError, match="self_checkpoint_invalid"):
            forward("SELF", loader.SELF_PIN, loader.FIT_SHA256, arrays)


@pytest.mark.parametrize(
    "overrides", [{"scale": np.array(1.0)}, {"std": np.zeros(12)}, {"mean": np.full(12, np.nan)}]
)
def test_rejects_invalid_fit_even_at_pinned_digest(synthetic, monkeypatch, overrides):
    synthetic["fit"] = _fit(**overrides)
    monkeypatch.setattr(loader, "FIT_SHA256", _sha(synthetic["fit"]))
    with pytest.raises(ValueError, match="fit_invalid"):
        loader.make_nov30_h3_forward(**synthetic)


def test_checks_seal_pins_and_input_before_forward(synthetic, arrays):
    forward = loader.make_nov30_h3_forward(**synthetic)
    for name, pin, fit in (
        ("SELF", loader.OLD60_PIN, loader.FIT_SHA256),
        ("OLD60", loader.OLD60_PIN, "0" * 64),
        ("unknown", loader.SELF_PIN, loader.FIT_SHA256),
    ):
        with pytest.raises(ValueError, match="seal_pin_mismatch"):
            forward(name, pin, fit, arrays)
    for changed in (
        {"key": arrays["key"][::-1]},
        {"target": np.zeros(17)},
        {"known": np.zeros(17, dtype=bool)},
        {"z": np.full((17, 8), np.inf)},
    ):
        with pytest.raises(ValueError, match="input_invalid"):
            forward("SELF", loader.SELF_PIN, loader.FIT_SHA256, dict(arrays) | changed)


@pytest.mark.parametrize("values", [[1.0, 2.0], [float("nan")], [2**127]])
def test_rejects_wrong_shape_nonfinite_weights_and_output(synthetic, arrays, monkeypatch, values):
    import torch
    from safetensors.torch import save

    raw = save({"weight": torch.tensor(values, dtype=torch.float32)})
    monkeypatch.setattr(loader, "SELF_PIN", loader.H3ModelPin(_sha(SELF_SOURCE), _sha(raw)))
    forward = loader.make_nov30_h3_forward(**(synthetic | {"self_checkpoint": raw}))
    with pytest.raises(
        ValueError, match="output_invalid" if values == [2**127] else "checkpoint_invalid"
    ):
        forward("SELF", loader.SELF_PIN, loader.FIT_SHA256, arrays)
