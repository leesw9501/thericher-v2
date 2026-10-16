"""Safe epoch recovery for the NEW fixed50 GRU/TCN AdamW campaign.

One process, fixed batch order, after scheduler.step at a completed epoch. This
does not resume old studies, data loaders, unnamed RNGs, attempts or budgets.
Restore into fresh trusted objects. CUDA RNG support is not CUDA parity.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import stat
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAX_BYTES = 256 * 1024**2
MAX_JSON = 2 * 1024**2
MAX_ARRAYS = 4096
SCHEMA = "fixed50-epoch-checkpoint-v1"


def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def _path(path: Path, repo_root: Path | None) -> Path:
    from .validation import _reject_repo_artifact_path

    path = Path(path).absolute()
    for parent in (path, *path.parents):
        if parent.exists() or parent.is_symlink():
            attrs = getattr(parent.lstat(), "st_file_attributes", 0)
            _require(not parent.is_symlink() and not attrs & 0x400, "reparse_artifact_path")
    _reject_repo_artifact_path(path, repo_root or Path(__file__).resolve().parents[3])
    return path


def _read(path: Path, limit: int) -> bytes:
    _require(stat.S_ISREG(path.lstat().st_mode) and not path.is_symlink(), "regular_file_required")
    with path.open("rb") as stream:
        value = stream.read(limit + 1)
    _require(len(value) <= limit, "checkpoint_size_limit")
    return value


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _identity(identity: dict[str, str]) -> dict[str, str]:
    _require(type(identity) is dict and bool(identity), "identity_required")
    _require(
        all(type(k) is str and type(v) is str and len(v) <= 4096 for k, v in identity.items()),
        "string_identity_required",
    )
    for key in ("contract_sha256", "source_sha256", "batch_order_sha256"):
        value = identity.get(key, "")
        _require(
            len(value) == 64 and all(c in "0123456789abcdef" for c in value),
            "exact_contract_source_batch_identity_required",
        )
    return dict(identity)


def _runtime(
    torch: Any, np: Any, model: Any, optimizer: Any, scheduler: Any, rng: Any, cuda: bool
) -> dict[str, Any]:
    _require(type(optimizer) is torch.optim.AdamW, "AdamW_required")
    _require(
        type(scheduler) is torch.optim.lr_scheduler.ReduceLROnPlateau, "ReduceLROnPlateau_required"
    )
    _require(scheduler.optimizer is optimizer, "scheduler_optimizer_binding")
    _require(isinstance(rng, np.random.Generator), "supplied_numpy_generator_required")
    _require(cuda or not torch.cuda.is_initialized(), "initialized_CUDA_requires_RNG_capture")
    names = {id(p): name for name, p in model.named_parameters()}
    groups = []
    for group in optimizer.param_groups:
        _require(all(id(p) in names for p in group["params"]), "optimizer_model_binding")
        groups.append([names[id(p)] for p in group["params"]])
    flattened = [name for group in groups for name in group]
    _require(len(set(flattened)) == len(flattened), "duplicate_optimizer_parameters")
    state = model.state_dict()
    _require(
        all(m.training == model.training for m in model.modules()), "mixed_module_modes_unsupported"
    )
    _require(
        all(isinstance(v, torch.Tensor) and v.layout == torch.strided for v in state.values()),
        "tensor_only_model_state",
    )
    _require(cuda or all(v.device.type == "cpu" for v in state.values()), "CUDA_capture_required")
    config = scheduler.state_dict()
    return {
        "torch": torch.__version__,
        "numpy": np.__version__,
        "python": sys.version,
        "model": repr(model),
        "groups": groups,
        "model_schema": {k: [list(v.shape), str(v.dtype), str(v.device)] for k, v in state.items()},
        "optimizer_config": [
            {k: v for k, v in g.items() if k not in ("params", "lr", "initial_lr")}
            for g in optimizer.param_groups
        ],
        "scheduler_config": {
            k: config[k]
            for k in (
                "factor",
                "patience",
                "threshold",
                "threshold_mode",
                "cooldown",
                "min_lrs",
                "mode",
                "eps",
            )
        },
        "bit_generator": type(rng.bit_generator).__name__,
        "threads": [torch.get_num_threads(), torch.get_num_interop_threads()],
        "deterministic": torch.are_deterministic_algorithms_enabled(),
        "matmul_precision": torch.get_float32_matmul_precision(),
        "cuda": (
            [
                torch.version.cuda,
                [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())],
            ]
            if cuda
            else None
        ),
        "cudnn": [
            torch.backends.cudnn.enabled,
            torch.backends.cudnn.benchmark,
            torch.backends.cudnn.deterministic,
            torch.backends.cudnn.allow_tf32,
        ],
    }


class _Codec:
    def __init__(self, torch: Any, np: Any) -> None:
        self.torch, self.np = torch, np
        self.arrays: dict[str, Any] = {}
        self.specs: dict[str, Any] = {}
        self.nodes = 0

    def pack(self, value: Any, depth: int = 0) -> Any:
        self.nodes += 1
        _require(depth <= 32 and self.nodes <= 100000, "state_tree_limit")
        if isinstance(value, (self.torch.Tensor, self.np.ndarray)):
            tensor = isinstance(value, self.torch.Tensor)
            array = value.detach().cpu().contiguous().numpy().copy() if tensor else value.copy()
            _require(
                array.dtype.kind in "biufc" and not array.dtype.hasobject, "numeric_array_only"
            )
            key = f"a{len(self.arrays):06d}"
            self.arrays[key] = array
            self.specs[key] = dict(
                shape=list(array.shape),
                dtype=array.dtype.str,
                device=str(value.device) if tensor else None,
            )
            _require(
                len(self.arrays) <= MAX_ARRAYS
                and sum(a.nbytes for a in self.arrays.values()) <= MAX_BYTES,
                "array_budget_exceeded",
            )
            return {"tensor" if tensor else "array": key}
        if isinstance(value, self.np.generic):
            return self.pack(value.item(), depth + 1)
        if type(value) is dict or isinstance(value, dict):
            _require(all(type(k) in (int, str) for k in value), "state_key_type")
            return {"dict": [[k, self.pack(v, depth + 1)] for k, v in value.items()]}
        if type(value) in (tuple, list):
            return {
                "tuple" if type(value) is tuple else "list": [
                    self.pack(v, depth + 1) for v in value
                ]
            }
        if type(value) is float and math.isinf(value):
            return {"infinity": 1 if value > 0 else -1}
        _require(value is None or type(value) in (bool, str, int, float), "unsupported_state_type")
        _require(type(value) is not float or math.isfinite(value), "NaN_metadata_forbidden")
        return value

    def unpack(self, value: Any, depth: int = 0) -> Any:
        self.nodes += 1
        _require(depth <= 32 and self.nodes <= 100000, "state_tree_limit")
        if type(value) is not dict:
            _require(value is None or type(value) in (bool, str, int, float), "bad_state_scalar")
            return value
        _require(len(value) == 1, "bad_state_tag")
        tag, body = next(iter(value.items()))
        if tag in ("tensor", "array"):
            _require(body in self.arrays, "missing_array")
            _require(
                (self.specs[body]["device"] is None) == (tag == "array"),
                "array_tensor_tag_mismatch",
            )
            array = self.arrays[body].copy()
            if tag == "array":
                return array
            return self.torch.from_numpy(array).to(device=self.specs[body]["device"])
        if tag == "infinity":
            _require(body in (-1, 1), "bad_infinity")
            return math.inf * body
        if tag == "dict":
            _require(
                type(body) is list and all(type(p) is list and len(p) == 2 for p in body),
                "bad_state_mapping",
            )
            _require(all(type(p[0]) in (str, int) for p in body), "bad_state_key")
            _require(len({p[0] for p in body}) == len(body), "duplicate_state_key")
            return {k: self.unpack(v, depth + 1) for k, v in body}
        _require(tag in ("list", "tuple") and type(body) is list, "bad_state_container")
        result = [self.unpack(v, depth + 1) for v in body]
        return tuple(result) if tag == "tuple" else result


def _counters(epoch: int, best: float, counters: dict[str, int]) -> None:
    _require(type(epoch) is int and epoch >= 0, "completed_epoch_required")
    _require(type(best) in (int, float) and not math.isnan(best), "valid_best_required")
    _require(
        type(counters) is dict
        and "optimizer_steps" in counters
        and all(type(k) is str and type(v) is int and v >= 0 for k, v in counters.items()),
        "nonnegative_optimizer_step_counters_required",
    )


def _validate(
    torch: Any, state: dict[str, Any], model: Any, optimizer: Any, scheduler: Any, rng: Any
) -> None:
    _counters(state["epoch"], state["best"], state["counters"])
    _require(state["scheduler"]["last_epoch"] == state["epoch"], "scheduler_epoch_mismatch")
    current = model.state_dict()
    _require(current.keys() == state["model"].keys(), "model_state_keys")
    for key, value in current.items():
        saved = state["model"][key]
        _require(
            isinstance(saved, torch.Tensor)
            and saved.shape == value.shape
            and saved.dtype == value.dtype
            and saved.device == value.device,
            "model_shape_dtype",
        )
    groups = state["optimizer"]["param_groups"]
    _require(len(groups) == len(optimizer.param_groups), "optimizer_group_count")
    parameters = {}
    for group, actual in zip(groups, optimizer.param_groups, strict=True):
        _require(len(group["params"]) == len(actual["params"]), "optimizer_group_shape")
        parameters.update(zip(group["params"], actual["params"], strict=True))
    _require(
        set(state["optimizer"]["state"])
        == (set(parameters) if state["counters"]["optimizer_steps"] else set()),
        "optimizer_state_completeness",
    )
    for key, moments in state["optimizer"]["state"].items():
        _require(
            key in parameters
            and set(moments)
            in (
                {"step", "exp_avg", "exp_avg_sq"},
                {"step", "exp_avg", "exp_avg_sq", "max_exp_avg_sq"},
            ),
            "AdamW_state_schema",
        )
        for name, value in moments.items():
            if name == "step":
                _require(
                    isinstance(value, torch.Tensor)
                    and value.numel() == 1
                    and value.dtype in (torch.float32, torch.float64)
                    and value.item() == state["counters"]["optimizer_steps"],
                    "step_counter_mismatch",
                )
            else:
                parameter = parameters[key]
                _require(
                    value.shape == parameter.shape and value.dtype == parameter.dtype,
                    "optimizer_moment_shape_dtype",
                )
    _require(
        state["cpu_rng"].dtype == torch.uint8
        and state["cpu_rng"].shape == torch.get_rng_state().shape,
        "CPU_RNG_shape",
    )
    probe = type(rng.bit_generator)()
    probe.state = state["numpy_rng"]
    _require(state["scheduler"].keys() == scheduler.state_dict().keys(), "scheduler_state_schema")


@dataclass(frozen=True)
class EpochCheckpoint:
    epoch: int
    best: float
    counters: dict[str, int]


def _check_devices(specs: dict[str, Any], cuda_devices: int | None) -> None:
    allowed = {None, "cpu"}
    if cuda_devices is not None:
        allowed.update(f"cuda:{i}" for i in range(cuda_devices))
    _require(
        all(type(s) is dict and s.get("device") in allowed for s in specs.values()),
        "checkpoint_tensor_device_denied",
    )


def save_epoch_checkpoint(
    path: Path,
    *,
    model: Any,
    optimizer: Any,
    scheduler: Any,
    numpy_rng: Any,
    identity: dict[str, str],
    epoch: int,
    best: float,
    counters: dict[str, int],
    repo_root: Path | None = None,
    capture_cuda_rng: bool = False,
) -> Path:
    """Reserve a NEW directory; publish only with an atomic no-overwrite commit marker.

    Keep any incomplete directory for diagnosis. Identity must include original
    contract/source/batch-order hashes; caller retains original attempts/budget.
    """
    import numpy as np
    import torch

    path = _path(path, repo_root)
    identity = _identity(identity)
    _counters(epoch, best, counters)
    runtime = _runtime(torch, np, model, optimizer, scheduler, numpy_rng, capture_cuda_rng)
    state = dict(
        model=model.state_dict(),
        optimizer=optimizer.state_dict(),
        scheduler=scheduler.state_dict(),
        numpy_rng=numpy_rng.bit_generator.state,
        cpu_rng=torch.get_rng_state(),
        cuda_rng=(torch.cuda.get_rng_state_all() if capture_cuda_rng else []),
        epoch=epoch,
        best=best,
        counters=dict(counters),
        training=model.training,
    )
    _validate(torch, state, model, optimizer, scheduler, numpy_rng)
    codec = _Codec(torch, np)
    tree = codec.pack(state)
    runtime = json.loads(_json(runtime))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.mkdir()
    with (path / "arrays.npz").open("xb") as stream:
        np.savez(stream, **codec.arrays)
        stream.flush()
        os.fsync(stream.fileno())
    data = _read(path / "arrays.npz", MAX_BYTES)
    manifest = _json(
        dict(
            schema=SCHEMA,
            identity=identity,
            runtime=runtime,
            arrays=codec.specs,
            tree=tree,
            arrays_sha256=_hash(data),
        )
    )
    _require(len(manifest) <= MAX_JSON, "manifest_size_limit")
    for name, value in (
        ("manifest.json", manifest),
        ("COMMITTED.pending", _hash(manifest).encode()),
    ):
        with (path / name).open("xb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
    os.link(path / "COMMITTED.pending", path / "COMMITTED")
    (path / "COMMITTED.pending").unlink()
    return path


def restore_epoch_checkpoint(
    path: Path,
    *,
    model: Any,
    optimizer: Any,
    scheduler: Any,
    numpy_rng: Any,
    identity: dict[str, str],
    repo_root: Path | None = None,
    capture_cuda_rng: bool = False,
) -> EpochCheckpoint:
    """Validate a complete local checkpoint before loading fresh trusted objects.

    No budget/cap/attempt changes. Caller resumes epoch+1 with the same batches;
    normalization/cursor/best-model artifacts must be separately identity-bound.
    """
    import numpy as np
    import torch

    path = _path(path, repo_root)
    manifest_bytes = _read(path / "manifest.json", MAX_JSON)
    _require(_read(path / "COMMITTED", 64).decode() == _hash(manifest_bytes), "manifest_hash")
    manifest = json.loads(manifest_bytes)
    _require(
        manifest["schema"] == SCHEMA and manifest["identity"] == _identity(identity),
        "checkpoint_identity_mismatch",
    )
    runtime = _runtime(torch, np, model, optimizer, scheduler, numpy_rng, capture_cuda_rng)
    _require(manifest["runtime"] == json.loads(_json(runtime)), "checkpoint_runtime_mismatch")
    data = _read(path / "arrays.npz", MAX_BYTES)
    _require(_hash(data) == manifest["arrays_sha256"], "arrays_hash")
    specs = manifest["arrays"]
    _require(type(specs) is dict and len(specs) <= MAX_ARRAYS, "array_count_limit")
    _check_devices(specs, len(runtime["cuda"][1]) if capture_cuda_rng else None)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos = archive.infolist()
        _require(
            len(infos) == len(specs)
            and {v.filename for v in infos} == {k + ".npy" for k in specs}
            and sum(v.file_size for v in infos) <= MAX_BYTES,
            "bounded_NPZ_members",
        )
        for info in infos:
            spec = specs[info.filename[:-4]]
            with archive.open(info) as stream:
                _require(np.lib.format.read_magic(stream) == (1, 0), "NPY_version")
                shape, _, dtype = np.lib.format.read_array_header_1_0(stream, max_header_size=10000)
                _require(
                    dtype.kind in "biufc"
                    and not dtype.hasobject
                    and list(shape) == spec["shape"]
                    and dtype.str == spec["dtype"]
                    and dtype.itemsize * math.prod(shape) == info.file_size - stream.tell(),
                    "array_shape_dtype_size",
                )
    codec = _Codec(torch, np)
    codec.specs = specs
    with np.load(io.BytesIO(data), allow_pickle=False, max_header_size=10000) as arrays:
        codec.arrays = {key: arrays[key] for key in specs}
    state = codec.unpack(manifest["tree"])
    _validate(torch, state, model, optimizer, scheduler, numpy_rng)
    _require(
        len(state["cuda_rng"]) == (torch.cuda.device_count() if capture_cuda_rng else 0),
        "CUDA_RNG_count",
    )
    model.load_state_dict(state["model"], strict=True)
    optimizer.load_state_dict(state["optimizer"])
    scheduler.load_state_dict(state["scheduler"])
    model.train(state["training"])
    numpy_rng.bit_generator.state = state["numpy_rng"]
    torch.set_rng_state(state["cpu_rng"])
    if capture_cuda_rng:
        torch.cuda.set_rng_state_all(state["cuda_rng"])
    return EpochCheckpoint(state["epoch"], state["best"], state["counters"])
