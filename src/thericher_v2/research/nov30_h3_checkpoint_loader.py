"""Bind the Nov30 forecast seal to the original SELF and OLD60 CPU models."""

import builtins
import hashlib
import io
from collections.abc import Callable, Mapping
from types import ModuleType
from zipfile import BadZipFile

import numpy as np

from thericher_v2.models import h3_shadow_point
from thericher_v2.research.prospective_h3_forecast import _FIELDS, _KEYS, H3ModelPin

SELF_PIN = H3ModelPin(
    "5b023d107fb068398a645217aad7db4d3852ef3306601937680d04a26198a0f3",
    "8b5edb4472d245c31d1d8335b70c24c5dd458efbc2d680972fd49733cf2141d0",
)
OLD60_PIN = H3ModelPin(h3_shadow_point.MODEL_SHA, h3_shadow_point.WEIGHTS_SHA)
FIT_SHA256 = h3_shadow_point.STATS_SHA
_ADAPTER_SHA256 = "ade1efe76b3ef7ed124b8a2aa7a0afdd4cdc31f6649e3a22d1b2ccefbfe1e2d6"
_ENTRY_IO_SHA256 = "2b15818314c112288c183a0df79df658a27637801a046d1b151ba53886ebdb9c"
_H3_SCALE = 0.03734792272176389

H3Forward = Callable[[str, H3ModelPin, str, Mapping[str, np.ndarray]], dict[str, float]]


def _verify(raw: bytes, pin: str, stage: str) -> None:
    if type(raw) is not bytes or hashlib.sha256(raw).hexdigest() != pin:
        raise ValueError(f"h3_loader_{stage}_digest_mismatch")


def _fit_stats(raw: bytes) -> dict[str, np.ndarray]:
    fields = {"mean": (12,), "std": (12,), "zmean": (8,), "zstd": (8,), "scale": ()}
    try:
        with np.load(io.BytesIO(raw), allow_pickle=False) as archive:
            if sorted(archive.files) != sorted(fields):
                raise ValueError
            stats = {name: archive[name] for name in fields}
        if (
            any(
                value.shape != fields[name]
                or value.dtype.kind != "f"
                or not np.isfinite(value).all()
                for name, value in stats.items()
            )
            or not (stats["std"] > 0).all()
            or not (stats["zstd"] > 0).all()
            or float(stats["scale"]) != _H3_SCALE
        ):
            raise ValueError
    except (AttributeError, BadZipFile, OSError, TypeError, ValueError):
        raise ValueError("h3_loader_fit_invalid") from None
    return stats


def _check_arrays(arrays: Mapping[str, np.ndarray]) -> None:
    if (
        set(arrays) != _FIELDS
        or any(not isinstance(value, np.ndarray) for value in arrays.values())
        or arrays["key"].tolist() != list(_KEYS)
        or arrays["x"].shape != (17, 60, 12)
        or arrays["x"].dtype != np.float32
        or arrays["z"].shape != (17, 8)
        or arrays["z"].dtype != np.float64
        or not np.isfinite(arrays["x"]).all()
        or not np.isfinite(arrays["z"]).all()
        or arrays["known"].shape != (17,)
        or arrays["known"].dtype != np.bool_
        or not arrays["known"].all()
        or arrays["entry_index"].shape != (17,)
        or arrays["entry_index"].dtype != np.int64
        or arrays["entry_index"].any()
        or any(arrays[key].shape != (17,) for key in ("context_close", "decision_at"))
    ):
        raise ValueError("h3_loader_input_invalid")


def _source_module(name: str, raw: bytes, *, entry_io: ModuleType | None = None) -> ModuleType:
    obj = ModuleType(name)
    if entry_io is not None:
        # Resolve the adapter's local import without changing sys.modules or sys.path.
        def import_pinned(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "entry_io" and level == 0:
                return entry_io
            if level != 0 or name not in {"numpy", "pathlib"}:
                raise ImportError("h3_loader_adapter_import_invalid")
            return builtins.__import__(name, globals, locals, fromlist, level)

        obj.__dict__["__builtins__"] = dict(vars(builtins), __import__=import_pinned)
        del obj.__dict__["__builtins__"]["open"]
    exec(compile(raw, f"<pinned {name}>", "exec", dont_inherit=True), vars(obj))
    return obj


def _self_forward(
    arrays: Mapping[str, np.ndarray],
    source: bytes,
    checkpoint: bytes,
    adapter: bytes,
    entry_io: bytes,
    stats: dict[str, np.ndarray],
) -> np.ndarray:
    import torch
    from safetensors import SafetensorError
    from safetensors.torch import load

    io_module = _source_module("entry_io", entry_io)
    adapt = _source_module("input_adapter", adapter, entry_io=io_module).adapt
    packed = adapt(arrays, stats)
    features = packed["features"]
    if (
        features.shape != (1, 17, 728)
        or features.dtype != np.float32
        or not np.isfinite(features).all()
        or packed["key"].tolist() != list(_KEYS)
        or packed["date_known"].tolist() != [True]
    ):
        raise ValueError("h3_loader_self_features_invalid")

    model = _source_module("entry_models", source).EntryCritic("SELF").cpu()
    try:
        state = load(checkpoint)
    except SafetensorError:
        raise ValueError("h3_loader_self_checkpoint_invalid") from None
    slots = model.state_dict()
    if state.keys() != slots.keys() or any(
        value.shape != slots[key].shape
        or value.dtype != slots[key].dtype
        or not torch.isfinite(value).all()
        for key, value in state.items()
    ):
        raise ValueError("h3_loader_self_checkpoint_invalid")
    model.load_state_dict(state, strict=True)
    model.requires_grad_(False).eval()
    with torch.inference_mode():
        output = model(torch.from_numpy(features)).double().numpy()
    if output.shape != (1, 17):
        raise ValueError("h3_loader_output_invalid")
    return output[0] * float(stats["scale"])


def make_nov30_h3_forward(
    *,
    self_source: bytes,
    self_checkpoint: bytes,
    old60_source: bytes,
    old60_checkpoint: bytes,
    fit: bytes,
    input_adapter: bytes,
    entry_io: bytes,
) -> H3Forward:
    """Return the ready-to-bind `seal_nov30_h3_forecast(forward=...)` callback.

    The isolated caller owns the read-only file bindings and runtime/clock
    attestation. This factory verifies immutable buffers without path discovery,
    model imports or model execution. Only the seal should invoke the callback.
    """
    for raw, pin, stage in (
        (self_source, SELF_PIN.source_sha256, "self_source"),
        (self_checkpoint, SELF_PIN.checkpoint_sha256, "self_checkpoint"),
        (old60_source, OLD60_PIN.source_sha256, "old60_source"),
        (old60_checkpoint, OLD60_PIN.checkpoint_sha256, "old60_checkpoint"),
        (fit, FIT_SHA256, "fit"),
        (input_adapter, _ADAPTER_SHA256, "adapter"),
        (entry_io, _ENTRY_IO_SHA256, "entry_io"),
    ):
        _verify(raw, pin, stage)
    stats = _fit_stats(fit)

    def forward(
        name: str, pin: H3ModelPin, fit_sha256: str, arrays: Mapping[str, np.ndarray]
    ) -> dict[str, float]:
        expected = {"SELF": SELF_PIN, "OLD60": OLD60_PIN}.get(name)
        if type(pin) is not H3ModelPin or pin != expected or fit_sha256 != FIT_SHA256:
            raise ValueError("h3_loader_seal_pin_mismatch")
        _check_arrays(arrays)
        if name == "SELF":
            values = _self_forward(
                arrays, self_source, self_checkpoint, input_adapter, entry_io, stats
            )
        else:
            from safetensors import SafetensorError

            try:
                values = h3_shadow_point._frozen_lstm(
                    arrays, old60_source, fit, old60_checkpoint, before_forward=lambda: None
                )
            except SafetensorError:
                raise ValueError("h3_loader_old60_checkpoint_invalid") from None
        if values.shape != (17,) or not np.isfinite(values).all():
            raise ValueError("h3_loader_output_invalid")
        return dict(zip(_KEYS, values.tolist(), strict=True))

    return forward
