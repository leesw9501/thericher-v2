"""Pinned Chronos-2, offline research only; no acquisition or broker path."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    import numpy as np

CHRONOS2_MODEL_ID = "amazon/chronos-2"
CHRONOS2_REVISION = "95a9710e2596287d08352589f42634fa5abdf0a7"
CHRONOS2_CHECKPOINT_DATE = "2025-10-30T14:58:57Z"
CHRONOS2_REPO_COMMIT = "fd533389c300660f9d8e3a00fcb29e4ca1174745"
CHRONOS2_IMAGE = "sha256:d6b43213ee3877653e3c1e79c7238fb5caa71241abf238838fa0c3332cf4f039"
CHRONOS2_SHA256 = {
    "config.json": "ef1143bfdc9c0376d9a056eefca46cb4b1ec3d0ffacd541ff56feb40fb708031",
    "model.safetensors": "ddcda3c7508bf2528087723e98a20707cc04b7f370ae275a9fd88078ddba4f42",
}
CHRONOS2_SIZES = {"config.json": 1067, "model.safetensors": 477930472}
MODEL_ID = CHRONOS2_MODEL_ID
REVISION = CHRONOS2_REVISION
MODEL_PINS = CHRONOS2_SHA256
MODEL_RELATIVE_ROOT = Path("foundation-models") / "chronos-2" / REVISION
PINNED_RUNTIME = {
    "chronos-forecasting": "2.2.2",
    "torch": "2.7.0+cu128",
    "transformers": "4.57.6",
    "safetensors": "0.8.0",
    "accelerate": "1.15.0",
    "einops": "0.8.2",
    "numpy": "2.5.1",
    "scikit-learn": "1.9.1",
    "huggingface-hub": "0.36.2",
    "tokenizers": "0.22.2",
}
MAX_CONTEXT = 256
MAX_HORIZON = 32
MAX_ISOLATED_BATCH = 32
QUANTILE_LEVELS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
_OFFLINE_ENV = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "DO_NOT_TRACK": "1",
}
_ALLOWED_FILES = frozenset(CHRONOS2_SHA256) | {"README.md", "LICENSE", ".gitattributes"}


@dataclass(frozen=True)
class Chronos2Context:
    """One past-only univariate task, with caller-attested time/availability.

    forecast_origin is the first future target instant, not the last input bar.
    timestamps must be strictly increasing and strictly earlier than that instant.
    available_at is the latest availability time of the *entire* context, including
    revisions/transformations, and must be no later than forecast_origin. This is
    caller evidence, not a provider-finality or point-in-time qualification.
    Values must already have causal units/scaling; no full-sample normalization.
    """

    series_id: str
    forecast_origin: datetime
    timestamps: Sequence[datetime]
    available_at: datetime
    values: Sequence[float] | np.ndarray


class Chronos2Local:
    """Load once, then forecast; instantiate via load_chronos2_local.

    The owner keeps source/model bytes immutable and serializes use of this
    process-local object. No fitting, covariate, arbitrary-kwargs, or remote-code
    interface is exposed. CPU and cuda:0 are explicit, without device fallback.
    """

    def __init__(self, pipeline: Any, torch: Any, target: Any):
        self._pipeline = pipeline
        self._torch = torch
        self._target = target

    def forecast(
        self,
        contexts: Sequence[Chronos2Context],
        horizon: int,
        *,
        mode: Literal["isolated", "same_origin_trio"] = "isolated",
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return median (N,H) and deciles (N,H,9), in caller series order.

        isolated: list of 1D tasks with cross_learning=False, even across origins.
        same_origin_trio: exactly three distinct series, identical past timestamps
        and one origin; one batch of three with cross_learning=True. Never pass a
        sequence of origin groups in one call. No future market covariates, context
        truncation, target outcomes, resampling, padding by the caller, or pooling
        across origins. Irregular session timestamps are allowed when aligned;
        the model sees observation steps, not elapsed wall-clock time.
        """
        if type(horizon) is not int or not 1 <= horizon <= MAX_HORIZON:
            raise ValueError("Chronos-2 horizon must be an integer from 1 to 32")
        inputs = _validated_contexts(contexts, mode)
        _require_offline_runtime()
        _require_device(self._pipeline.model, self._target)
        try:
            with self._torch.inference_mode(), self._torch.device("cpu"):
                outputs = self._pipeline.predict_quantiles(
                    inputs=inputs,
                    prediction_length=horizon,
                    quantile_levels=list(QUANTILE_LEVELS),
                    batch_size=len(inputs),
                    context_length=MAX_CONTEXT,
                    cross_learning=mode == "same_origin_trio",
                    limit_prediction_length=True,
                )
        except Exception:
            raise RuntimeError("Chronos-2 offline inference failed") from None
        return _validated_outputs(outputs, len(inputs), horizon)


def load_chronos2_local(
    model_directory: Path | str,
    expected_sha256: dict[str, str] | None = None,
    *,
    device: Literal["cpu", "cuda"] = "cpu",
) -> Chronos2Local:
    """Verify the exact official config/weights, then load safetensors directly.

    Requires the pinned runtime and a Linux network namespace with only loopback
    (Docker --network none), plus _OFFLINE_ENV. No from_pretrained/AutoModel/Hub
    helper is called, no trust_remote_code, no pickle and no environment mutation.
    Installing/acquiring packages is a separate step, never done by this loader.
    Owner must use a read-only model mount and bound process resources/time.
    """
    if expected_sha256 is not None and expected_sha256 != CHRONOS2_SHA256:
        raise ValueError("Chronos-2 caller hashes must equal the official pinned files")
    if not isinstance(device, str) or device not in {"cpu", "cuda"}:
        raise ValueError("Chronos-2 device must be cpu or cuda")
    directory, config = _verified_directory(model_directory)
    _require_offline_runtime()
    _require_dependencies()
    try:
        import torch
        from chronos import Chronos2Pipeline
        from chronos.chronos2 import Chronos2Model
        from chronos.chronos2.config import Chronos2CoreConfig
        from safetensors.torch import load_file

        if device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("Chronos-2 CUDA is unavailable; no CPU fallback")
        target = torch.device("cpu" if device == "cpu" else "cuda:0")
        # Direct constructors avoid the upstream LoRA/S3/Hub discovery paths.
        with torch.device("cpu"):
            model = Chronos2Model(Chronos2CoreConfig(**config, attn_implementation="sdpa"))
            state = load_file(str(directory / "model.safetensors"), device="cpu")
            model.load_state_dict(state, strict=True)
            del state
        model.eval()
        model.requires_grad_(False)
        model.to(device=target, dtype=torch.float32)
        _require_device(model, target)
        pipeline = Chronos2Pipeline(model=model)
    except Exception:
        raise RuntimeError("Chronos-2 pinned local load failed; no fallback") from None
    return Chronos2Local(pipeline, torch, target)


def _require_dependencies() -> None:
    try:
        if any(version(name) != expected for name, expected in PINNED_RUNTIME.items()):
            raise ValueError
    except Exception:
        raise RuntimeError("Chronos-2 runtime differs from the verified pinned image") from None


def _require_offline_runtime() -> None:
    try:
        if sys.platform != "linux" or any(
            os.environ.get(key) != value for key, value in _OFFLINE_ENV.items()
        ):
            raise ValueError
        # Flags alone do not prevent arbitrary dependency network traffic.
        interfaces = {
            line.split(":", 1)[0].strip()
            for line in Path("/proc/net/dev").read_text(encoding="ascii").splitlines()
            if ":" in line
        }
        if interfaces != {"lo"}:
            raise ValueError
    except Exception:
        raise RuntimeError("Chronos-2 requires Docker network=none and offline flags") from None


def _require_device(model: Any, target: Any) -> None:
    parameters = tuple(model.parameters())
    if (
        model.training
        or not parameters
        or any(value.device != target or value.requires_grad for value in parameters)
        or any(value.device != target for value in model.buffers())
    ):
        raise ValueError("Chronos-2 model is not frozen on the requested device")


def _unlinked_stat(path: Path) -> Any:
    info = path.lstat()
    if (
        stat.S_ISLNK(info.st_mode)
        or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        or stat.S_ISREG(info.st_mode)
        and info.st_nlink != 1
    ):
        raise ValueError("Chronos-2 model links are not allowed")
    return info


def _verified_directory(directory: Path | str) -> tuple[Path, dict[str, Any]]:
    try:
        path = Path(directory)
        if ".." in path.parts or path.anchor.startswith(("\\\\", "//")):
            raise ValueError("Chronos-2 directory must be local and unlinked")
        path = path.absolute()
        for parent in (*reversed(path.parents), path):
            if not stat.S_ISDIR(_unlinked_stat(parent).st_mode):
                raise ValueError("Chronos-2 model directory is invalid")
        names = set()
        for child in path.iterdir():
            if child.name not in _ALLOWED_FILES or not stat.S_ISREG(_unlinked_stat(child).st_mode):
                raise ValueError("Chronos-2 contains an unsupported file")
            names.add(child.name)
        if not CHRONOS2_SHA256.keys() <= names:
            raise ValueError("Chronos-2 required files are missing")
        for name, digest in CHRONOS2_SHA256.items():
            if (path / name).stat().st_size != CHRONOS2_SIZES[name]:
                raise ValueError("Chronos-2 model size mismatch")
            with (path / name).open("rb") as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            if actual != digest:
                raise ValueError("Chronos-2 model SHA256 mismatch")
        config = json.loads((path / "config.json").read_text(encoding="utf-8"))
        if (
            config["architectures"] != ["Chronos2Model"]
            or config["chronos_pipeline_class"] != "Chronos2Pipeline"
            or "auto_map" in config
        ):
            raise ValueError("Chronos-2 architecture is unsupported")
    except (OSError, TypeError, KeyError, UnicodeError, json.JSONDecodeError):
        raise ValueError("Chronos-2 local model files are invalid") from None
    return path, config


def _utc(value: Any) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Chronos-2 requires timezone-aware timestamps")
    return value.astimezone(UTC)


def _validated_contexts(contexts: Any, mode: Any) -> list[np.ndarray]:
    import numpy as np

    if not isinstance(mode, str) or mode not in {"isolated", "same_origin_trio"}:
        raise ValueError("Chronos-2 mode is invalid")
    if (
        not isinstance(contexts, Sequence)
        or isinstance(contexts, (str, bytes))
        or not 1 <= len(contexts) <= MAX_ISOLATED_BATCH
        or mode == "same_origin_trio"
        and len(contexts) != 3
    ):
        raise ValueError("Chronos-2 requires 1..32 isolated tasks or exactly one trio")
    identities, origins, clocks, inputs = set(), [], [], []
    for context in contexts:
        if (
            not isinstance(context, Chronos2Context)
            or not isinstance(context.series_id, str)
            or not context.series_id.strip()
        ):
            raise ValueError("Chronos-2 requires named context records")
        origin, available = _utc(context.forecast_origin), _utc(context.available_at)
        if not isinstance(context.timestamps, Sequence) or isinstance(
            context.timestamps, (str, bytes)
        ):
            raise ValueError("Chronos-2 requires past timestamps")
        times = tuple(_utc(value) for value in context.timestamps)
        if (
            not 1 <= len(times) <= MAX_CONTEXT
            or any(a >= b for a, b in zip(times, times[1:], strict=False))
            or times[-1] >= origin
            or not times[-1] <= available <= origin
        ):
            raise ValueError("Chronos-2 context timing or availability is invalid")
        identity = (context.series_id, origin)
        if identity in identities:
            raise ValueError("Chronos-2 duplicate series/origin")
        identities.add(identity)
        origins.append(origin)
        clocks.append(times)
        try:
            values = np.asarray(context.values)
            if values.shape != (len(times),) or values.dtype.kind not in "iuf":
                raise ValueError
            with np.errstate(over="ignore", invalid="ignore"):
                values = values.astype(np.float32, copy=True)
            if not np.isfinite(values).all():
                raise ValueError
        except Exception:
            raise ValueError("Chronos-2 context must contain finite real 1D values") from None
        inputs.append(values)
    if mode == "same_origin_trio" and (
        len(set(origins)) != 1 or any(times != clocks[0] for times in clocks)
    ):
        raise ValueError("Chronos-2 trio requires one origin and identical past timestamps")
    return inputs


def _validated_outputs(outputs: Any, count: int, horizon: int) -> tuple[np.ndarray, np.ndarray]:
    import numpy as np

    try:
        quantiles, medians = outputs
        if len(quantiles) != count or len(medians) != count:
            raise ValueError
        q = np.stack([value.detach().cpu().numpy() for value in quantiles])
        p = np.stack([value.detach().cpu().numpy() for value in medians])
        if (
            q.shape != (count, 1, horizon, len(QUANTILE_LEVELS))
            or p.shape != (count, 1, horizon)
            or q.dtype.kind not in "iuf"
            or p.dtype.kind not in "iuf"
            or not np.isfinite(q).all()
            or not np.isfinite(p).all()
            or not np.array_equal(p, q[..., QUANTILE_LEVELS.index(0.5)])
        ):
            raise ValueError
        return p[:, 0].copy(), q[:, 0].copy()
    except Exception:
        raise ValueError("Chronos-2 output shape, values or median is invalid") from None
