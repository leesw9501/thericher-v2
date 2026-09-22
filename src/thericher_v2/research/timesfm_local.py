"""Hash-pinned, local-only TimesFM 2.5 inference for isolated research."""

from __future__ import annotations

import hashlib
import json
import re
import stat
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    import numpy as np

TIMESFM_MODEL_ID = "google/timesfm-2.5-200m-pytorch"
MAX_CONTEXT = 256
MAX_HORIZON = 32
QUANTILE_LEVELS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
_REQUIRED_FILES = frozenset({"config.json", "model.safetensors"})
_ALLOWED_FILES = _REQUIRED_FILES | {
    "README.md",
    "LICENSE",
    "LICENSE.txt",
    ".gitattributes",
    "timesfm-2.0.2-py3-none-any.whl",  # Inert here; the external runner verifies it.
}
_MODEL_CONFIG = {
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
    "quantiles": list(QUANTILE_LEVELS),
    "rms_norm_eps": 1e-6,
    "torch_compile": False,
}


def forecast_timesfm_2p5(
    model_directory: Path | str,
    expected_sha256: dict[str, str],
    contexts: Sequence[Sequence[float]] | np.ndarray,
    horizon: int,
    device: Literal["cpu", "cuda"],
    *,
    model_id: str = TIMESFM_MODEL_ID,
) -> tuple[np.ndarray, np.ndarray]:
    """Forecast nonempty 1D contexts of 1..256 values, with horizon 1..32.

    Hashes must be exactly the two required filenames mapped to 64 hex digits.
    The caller owns model/source provenance and must keep the directory immutable
    during this call. Only the official 2.5 config and safetensors are supported;
    acquisition, dependency installation and process network isolation belong to
    the external runner. No environment, authentication or broker APIs are used.
    Optional Torch/TimesFM dependencies are imported only after validation.
    Returns the official (points, quantiles) arrays, shaped (N, H) and (N, H, 10).
    Points are medians; quantiles channel 0 is the mean, followed by the nine
    deciles in QUANTILE_LEVELS (the median is channel 5).
    CUDA means cuda:0 and fails without an available device; CPU never loads
    weights onto CUDA. No training or torch.compile is performed.
    """
    if model_id != TIMESFM_MODEL_ID:
        raise ValueError("TimesFM model ID is not allowed")
    if type(horizon) is not int or not 1 <= horizon <= MAX_HORIZON:
        raise ValueError("TimesFM horizon must be an integer from 1 to 32")
    if not isinstance(device, str) or device not in {"cpu", "cuda"}:
        raise ValueError("TimesFM device must be cpu or cuda")
    directory, config = _verified_directory(model_directory, expected_sha256)
    inputs = _validated_contexts(contexts)
    input_count = len(inputs)

    try:
        import torch
    except Exception:
        raise RuntimeError("TimesFM Torch dependency is unavailable") from None
    try:
        available = device == "cpu" or torch.cuda.is_available()
    except Exception:
        raise RuntimeError("TimesFM CUDA availability check failed") from None
    if not available:
        raise RuntimeError("TimesFM CUDA is unavailable; no CPU fallback")

    try:
        import timesfm

        target = torch.device("cpu" if device == "cpu" else "cuda:0")

        # Inspected timesfm 2.0.2: from_pretrained calls Hub even for a local
        # path. The constructor + safetensors loader never call Hub. Pin the
        # device before load_checkpoint moves weights off CPU.
        # Override any caller default allocation device without changing globals.
        with torch.device("cpu"):
            model = timesfm.TimesFM_2p5_200M_torch(torch_compile=False, config=config)
            model.model.device = target
            model.model.device_count = 1
            model.load_checkpoint(str(directory))
        model.model.eval()
        model.model.requires_grad_(False)
        _require_device(model.model, target)
        model.compile(
            timesfm.ForecastConfig(
                max_context=MAX_CONTEXT,
                max_horizon=MAX_HORIZON,
                per_core_batch_size=min(input_count, 32),
                normalize_inputs=True,
                use_continuous_quantile_head=True,
                force_flip_invariance=True,
                infer_is_positive=False,
                fix_quantile_crossing=True,
                return_backcast=False,
            )
        )
        # TimesFM internally pads to its 128-step output patch, then slices H.
        with torch.inference_mode():
            outputs = model.forecast(horizon=horizon, inputs=inputs)
    except Exception:
        raise RuntimeError("TimesFM local inference failed") from None
    return _validated_outputs(outputs, input_count, horizon)


def _require_device(module: Any, target: Any) -> None:
    if module.device != target or module.device_count != 1:
        raise ValueError("TimesFM device placement is invalid")
    parameters = tuple(module.parameters())
    if not parameters or any(value.device != target for value in parameters):
        raise ValueError("TimesFM parameter placement is invalid")
    if any(value.device != target for value in module.buffers()):
        raise ValueError("TimesFM buffer placement is invalid")


def _unlinked_stat(path: Path) -> Any:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or (
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    ):
        raise ValueError("TimesFM model links are not allowed")
    if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
        raise ValueError("TimesFM model links are not allowed")
    return info


def _verified_directory(
    directory: Path | str, hashes: dict[str, str]
) -> tuple[Path, dict[str, Any]]:
    if (
        not isinstance(hashes, dict)
        or set(hashes) != _REQUIRED_FILES
        or any(
            not isinstance(value, str) or re.fullmatch(r"[0-9a-fA-F]{64}", value) is None
            for value in hashes.values()
        )
    ):
        raise ValueError("TimesFM requires exact config and safetensors SHA256 hashes")
    try:
        path = Path(directory)
        if ".." in path.parts or path.anchor.startswith(("\\\\", "//")):
            raise ValueError("TimesFM model directory must be local and unlinked")
        path = path.absolute()
        for parent in (*reversed(path.parents), path):
            if not stat.S_ISDIR(_unlinked_stat(parent).st_mode):
                raise ValueError("TimesFM model directory is invalid")
        names = set()
        for child in path.iterdir():
            info = _unlinked_stat(child)
            if child.name not in _ALLOWED_FILES or not stat.S_ISREG(info.st_mode):
                raise ValueError("TimesFM model contains an unsupported file")
            names.add(child.name)
        if not _REQUIRED_FILES <= names:
            raise ValueError("TimesFM required model files are missing")
        for name in sorted(_REQUIRED_FILES):
            with (path / name).open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != hashes[name].lower():
                raise ValueError("TimesFM model SHA256 mismatch")
        config = json.loads((path / "config.json").read_text(encoding="utf-8"))
        if config != _MODEL_CONFIG:
            raise ValueError("TimesFM config is not the supported 2.5 architecture")
        if (path / "model.safetensors").stat().st_size == 0:
            raise ValueError("TimesFM model weights are empty")
    except (OSError, TypeError, UnicodeError, json.JSONDecodeError):
        raise ValueError("TimesFM local model files are invalid") from None
    return path, config


def _validated_contexts(contexts: Any) -> list[np.ndarray]:
    import numpy as np

    try:
        if not isinstance(contexts, (Sequence, np.ndarray)) or isinstance(contexts, (str, bytes)):
            raise ValueError
        if len(contexts) < 1:
            raise ValueError
        inputs = []
        for context in contexts:
            values = np.asarray(context)
            if (
                values.ndim != 1
                or not 1 <= values.size <= MAX_CONTEXT
                or values.dtype.kind not in "iuf"
            ):
                raise ValueError
            with np.errstate(over="ignore", invalid="ignore"):
                values = values.astype(np.float32, copy=True)
            if not np.isfinite(values).all():
                raise ValueError
            inputs.append(values)
        if len(inputs) != len(contexts):
            raise ValueError
    except Exception:
        raise ValueError(
            "TimesFM contexts must be nonempty finite real 1D series of length 1..256"
        ) from None
    return inputs


def _validated_outputs(outputs: Any, count: int, horizon: int) -> tuple[np.ndarray, np.ndarray]:
    import numpy as np

    try:
        points, full = outputs
        points, full = np.asarray(points), np.asarray(full)
        if (
            points.shape != (count, horizon)
            or full.shape != (count, horizon, 10)
            or points.dtype.kind not in "iuf"
            or full.dtype.kind not in "iuf"
            or not np.isfinite(points).all()
            or not np.isfinite(full).all()
        ):
            raise ValueError
        return points.copy(), full.copy()
    except Exception:
        raise ValueError("TimesFM output shape or values are invalid") from None
