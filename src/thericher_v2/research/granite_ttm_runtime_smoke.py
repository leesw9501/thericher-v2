"""External-only structural runtime smoke for IBM Granite TTM R1.

This module deliberately proves only that a pinned, safe-serialized public
model can be loaded locally and produce the documented tensor geometry from a
synthetic input.  It never receives market data, labels, credentials, broker
objects, or a trading decision.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import signal
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from thericher_v2.research.artifact_paths import ensure_external_artifact_directory

GRANITE_TTM_RUNTIME_SMOKE_ID = "granite-ttm-r1-isolated-runtime-smoke-v1"
GRANITE_TTM_MODEL_ID = "ibm-granite/granite-timeseries-ttm-r1"
GRANITE_TTM_MODEL_REVISION = "f04bebdd4c13475b006ce72672e74c9dc28871dc"
GRANITE_TTM_MODEL_LICENSE = "Apache-2.0"
GRANITE_TTM_SOURCE_URL = "https://huggingface.co/ibm-granite/granite-timeseries-ttm-r1"
GRANITE_TTM_PACKAGE = "granite-tsfm"
GRANITE_TTM_PACKAGE_VERSION = "0.3.1"
GRANITE_TTM_CONTEXT_LENGTH = 512
GRANITE_TTM_PREDICTION_LENGTH = 96
GRANITE_TTM_CHANNEL_COUNT = 1
GRANITE_TTM_SAFETENSORS_SHA256 = "30f8d9be619518e18c4c15c6ee504e491b9624b48e251661cd5f967bce097731"
GRANITE_TTM_SAFETENSORS_SIZE = 3_240_592
GRANITE_TTM_CPU_TIMEOUT_SECONDS = 60.0
GRANITE_TTM_CUDA_TIMEOUT_SECONDS = 60.0
GRANITE_TTM_COMPARISON_ATOL = 1e-4
GRANITE_TTM_COMPARISON_RTOL = 1e-4
GRANITE_TTM_CPU_FORWARD_COUNT = 2
GRANITE_TTM_CUDA_WARMUP_COUNT = 1
GRANITE_TTM_CUDA_FORWARD_COUNT = 16
GRANITE_TTM_CUDA_MAX_PEAK_MEMORY_BYTES = 1 * 1024 * 1024 * 1024

_REQUIRED_MODEL_FILES = frozenset(
    {"config.json", "generation_config.json", "model.safetensors"}
)
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}", re.ASCII)
_PHASES = frozenset({"cpu", "cuda"})

Phase = Literal["cpu", "cuda"]
Downloader = Callable[..., str | Path | None]
Inference = Callable[[Path, Phase], "GraniteTtmInferenceOutput"]
CudaAvailable = Callable[[], bool]
Clock = Callable[[], float]


class _PhaseTimeoutError(RuntimeError):
    """Raised by the container-local timer when one structural phase runs long."""


@dataclass(frozen=True, slots=True)
class GraniteTtmLocalModel:
    """A re-attested pinned model directory outside the repository."""

    directory: Path
    manifest_path: Path
    manifest_sha256: str
    file_sha256: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class GraniteTtmRuntimeContract:
    """Source-safe contract for one non-promoting structural smoke."""

    path: Path
    sha256: str
    run_directory: Path
    model_manifest_sha256: str


@dataclass(frozen=True, slots=True)
class GraniteTtmInferenceOutput:
    """Transient local inference result; prediction values are never persisted."""

    shape: tuple[int, int, int]
    dtype: str
    finite: bool
    comparison_value: Any | None = None
    peak_memory_bytes: int | None = None


@dataclass(frozen=True, slots=True)
class GraniteTtmRuntimeRun:
    """A source-safe terminal phase receipt."""

    phase: Phase
    status: Literal["completed", "failed", "cuda_unavailable"]
    terminal_category: str
    receipt_path: Path
    receipt_sha256: str
    contract_sha256: str


def granite_ttm_r1_model_directory(artifact_root: Path | str) -> Path:
    """Return the fixed external storage location for the pinned model."""

    return (
        Path(artifact_root)
        / "foundation-models"
        / "granite-ttm-r1"
        / GRANITE_TTM_MODEL_REVISION
    )


def prepare_granite_ttm_r1_local_model(
    *,
    artifact_root: Path | str,
    repository_root: Path | str,
    downloader: Downloader | None = None,
) -> GraniteTtmLocalModel:
    """Acquire only the fixed safe files into an external artifact directory."""

    root = _external_root(artifact_root, repository_root)
    directory = granite_ttm_r1_model_directory(root)
    manifest_path = directory / "model-manifest.json"
    if manifest_path.is_file():
        return load_verified_granite_ttm_r1_local_model(
            artifact_root=root,
            repository_root=repository_root,
        )
    if directory.exists():
        raise ValueError("Granite TTM model directory exists without a verified manifest")

    parent = ensure_external_artifact_directory(
        root,
        Path(repository_root),
        "foundation-models",
        "granite-ttm-r1",
    )
    directory = parent / GRANITE_TTM_MODEL_REVISION
    directory.mkdir()
    try:
        (downloader or _official_snapshot_download)(
            repo_id=GRANITE_TTM_MODEL_ID,
            revision=GRANITE_TTM_MODEL_REVISION,
            local_dir=str(directory),
            allow_patterns=tuple(sorted(_REQUIRED_MODEL_FILES)),
        )
        _remove_download_metadata(directory)
        records = _verified_model_file_records(directory)
        payload: dict[str, object] = {
            "kind": "granite_ttm_r1_local_model_manifest",
            "model_id": GRANITE_TTM_MODEL_ID,
            "model_revision": GRANITE_TTM_MODEL_REVISION,
            "license": GRANITE_TTM_MODEL_LICENSE,
            "source_url": GRANITE_TTM_SOURCE_URL,
            "runtime_package": {
                "name": GRANITE_TTM_PACKAGE,
                "version": GRANITE_TTM_PACKAGE_VERSION,
            },
            "safe_serialization": True,
            "files": records,
            "scope": _non_promoting_scope(),
        }
        _write_json_new(manifest_path, payload)
    except Exception:
        _remove_partial_directory(directory)
        raise
    return load_verified_granite_ttm_r1_local_model(
        artifact_root=root,
        repository_root=repository_root,
    )


def load_verified_granite_ttm_r1_local_model(
    *,
    artifact_root: Path | str,
    repository_root: Path | str,
) -> GraniteTtmLocalModel:
    """Verify an existing local model without a downloader or provider path."""

    root = _external_root(artifact_root, repository_root)
    directory = granite_ttm_r1_model_directory(root).resolve(strict=False)
    if not directory.is_dir() or directory.is_symlink() or not directory.is_relative_to(root):
        raise ValueError("Granite TTM model directory is invalid")
    manifest_path = directory / "model-manifest.json"
    payload = _read_json_object(manifest_path)
    _validate_model_manifest(payload, directory)
    records = _verified_model_file_records(directory)
    if payload.get("files") != records:
        raise ValueError("Granite TTM model files changed")
    return GraniteTtmLocalModel(
        directory=directory,
        manifest_path=manifest_path,
        manifest_sha256=_sha256_json(payload),
        file_sha256={record["path"]: record["sha256"] for record in records},
    )


def freeze_granite_ttm_r1_runtime_smoke(
    model: GraniteTtmLocalModel,
    *,
    artifact_root: Path | str,
    repository_root: Path | str,
) -> GraniteTtmRuntimeContract:
    """Freeze an image-independent local-only smoke contract."""

    root = _external_root(artifact_root, repository_root)
    _reattest_model_instance(model, root, repository_root)
    run_directory = ensure_external_artifact_directory(
        root,
        Path(repository_root),
        "research",
        GRANITE_TTM_RUNTIME_SMOKE_ID,
    )
    path = run_directory / "contract.json"
    payload: dict[str, object] = {
        "kind": GRANITE_TTM_RUNTIME_SMOKE_ID,
        "model": {
            "id": GRANITE_TTM_MODEL_ID,
            "revision": GRANITE_TTM_MODEL_REVISION,
            "manifest_sha256": model.manifest_sha256,
            "loader": "tsfm_public.models.tinytimemixer.TinyTimeMixerForPrediction",
            "local_files_only": True,
            "trust_remote_code": False,
        },
        "input": {
            "kind": "deterministic_synthetic_univariate",
            "context_length": GRANITE_TTM_CONTEXT_LENGTH,
            "channel_count": GRANITE_TTM_CHANNEL_COUNT,
            "prediction_length": GRANITE_TTM_PREDICTION_LENGTH,
        },
        "compute": {
            "cpu_first": True,
            "cpu_timeout_seconds": GRANITE_TTM_CPU_TIMEOUT_SECONDS,
            "cuda_timeout_seconds": GRANITE_TTM_CUDA_TIMEOUT_SECONDS,
            "cpu_forward_count": GRANITE_TTM_CPU_FORWARD_COUNT,
            "cuda_warmup_count": GRANITE_TTM_CUDA_WARMUP_COUNT,
            "cuda_forward_count": GRANITE_TTM_CUDA_FORWARD_COUNT,
            "cuda_max_peak_memory_bytes": GRANITE_TTM_CUDA_MAX_PEAK_MEMORY_BYTES,
            "comparison_atol": GRANITE_TTM_COMPARISON_ATOL,
            "comparison_rtol": GRANITE_TTM_COMPARISON_RTOL,
        },
        "scope": _non_promoting_scope(),
    }
    if path.exists():
        existing = _read_json_object(path)
        if existing != payload:
            raise ValueError("Granite TTM runtime contract changed")
    else:
        _write_json_new(path, payload)
    return GraniteTtmRuntimeContract(
        path=path,
        sha256=_sha256_json(payload),
        run_directory=run_directory,
        model_manifest_sha256=model.manifest_sha256,
    )


def run_granite_ttm_r1_cpu_smoke(
    contract: GraniteTtmRuntimeContract,
    model: GraniteTtmLocalModel,
    *,
    inference: Inference | None = None,
    clock: Clock = time.monotonic,
) -> GraniteTtmRuntimeRun:
    """Run or reattach the terminal CPU phase without retrying a failure."""

    run, _ = _run_phase(
        contract,
        model,
        phase="cpu",
        inference=inference,
        clock=clock,
        comparison_reference=None,
    )
    return run


def run_granite_ttm_r1_cuda_smoke(
    contract: GraniteTtmRuntimeContract,
    model: GraniteTtmLocalModel,
    *,
    inference: Inference | None = None,
    cuda_available: CudaAvailable | None = None,
    clock: Clock = time.monotonic,
    comparison_reference: Any | None = None,
) -> GraniteTtmRuntimeRun:
    """Run CUDA only after a matching successful CPU terminal receipt."""

    try:
        cpu = _read_phase_receipt(contract, phase="cpu")
    except ValueError as error:
        raise ValueError(
            "Granite TTM CUDA requires a completed matching CPU receipt"
        ) from error
    if cpu.status != "completed":
        raise ValueError("Granite TTM CUDA requires a completed matching CPU receipt")
    if not (cuda_available or _cuda_available)():
        return _write_or_read_unavailable_cuda(contract)
    run, _ = _run_phase(
        contract,
        model,
        phase="cuda",
        inference=inference,
        clock=clock,
        comparison_reference=comparison_reference,
    )
    return run


def run_granite_ttm_r1_runtime_smoke(
    contract: GraniteTtmRuntimeContract,
    model: GraniteTtmLocalModel,
    *,
    include_cuda: bool,
    inference: Inference | None = None,
    cuda_available: CudaAvailable | None = None,
    clock: Clock = time.monotonic,
) -> tuple[GraniteTtmRuntimeRun, GraniteTtmRuntimeRun | None]:
    """Run CPU first and, only on success, one optional CUDA structural phase."""

    cpu, cpu_output = _run_phase(
        contract,
        model,
        phase="cpu",
        inference=inference,
        clock=clock,
        comparison_reference=None,
    )
    if not include_cuda or cpu.status != "completed":
        return cpu, None
    cuda = run_granite_ttm_r1_cuda_smoke(
        contract,
        model,
        inference=inference,
        cuda_available=cuda_available,
        clock=clock,
        comparison_reference=cpu_output.comparison_value if cpu_output else None,
    )
    return cpu, cuda


def _run_phase(
    contract: GraniteTtmRuntimeContract,
    model: GraniteTtmLocalModel,
    *,
    phase: Phase,
    inference: Inference | None,
    clock: Clock,
    comparison_reference: Any | None,
) -> tuple[GraniteTtmRuntimeRun, GraniteTtmInferenceOutput | None]:
    _validate_contract(contract, model)
    existing = _try_read_phase_receipt(contract, phase)
    if existing is not None:
        return existing, None
    if phase == "cuda" and comparison_reference is None:
        return _write_phase_receipt(
            contract,
            phase=phase,
            status="failed",
            terminal_category="cpu_cuda_comparison_unavailable",
            elapsed_milliseconds=0,
        ), None
    started = clock()
    try:
        with _phase_timeout(_timeout_seconds(phase)):
            output = (inference or _local_ttm_inference)(model.directory, phase)
        elapsed = _elapsed_milliseconds(started, clock())
        if elapsed > _timeout_seconds(phase) * 1000:
            return _write_phase_receipt(
                contract,
                phase=phase,
                status="failed",
                terminal_category="runtime_timeout",
                elapsed_milliseconds=elapsed,
            ), None
        _validate_inference_output(output, phase=phase)
        comparison = _comparison_outcome(
            comparison_reference,
            output.comparison_value,
        )
        return _write_phase_receipt(
            contract,
            phase=phase,
            status="completed",
            terminal_category="structural_pass",
            elapsed_milliseconds=elapsed,
            output=output,
            comparison=comparison,
        ), output
    except Exception as error:
        return _write_phase_receipt(
            contract,
            phase=phase,
            status="failed",
            terminal_category=_failure_category(error),
            elapsed_milliseconds=_elapsed_milliseconds(started, clock()),
        ), None


def _local_ttm_inference(directory: Path, phase: Phase) -> GraniteTtmInferenceOutput:
    """Load the explicit local TTM class with no remote-code or auto loader."""

    torch = _torch()
    from tsfm_public.models.tinytimemixer import TinyTimeMixerForPrediction

    device = "cuda" if phase == "cuda" else "cpu"
    if phase == "cuda":
        torch.cuda.reset_peak_memory_stats()
    model = TinyTimeMixerForPrediction.from_pretrained(
        str(directory),
        local_files_only=True,
        trust_remote_code=False,
    )
    model = model.to(device)
    model.eval()
    past_values = _synthetic_input(torch, device)
    with torch.inference_mode():
        if phase == "cuda":
            _assert_cuda_peak_memory(torch)
            for _ in range(GRANITE_TTM_CUDA_WARMUP_COUNT):
                model(past_values=past_values)
                _assert_cuda_peak_memory(torch)
            for _ in range(GRANITE_TTM_CUDA_FORWARD_COUNT):
                output = model(past_values=past_values)
                _assert_cuda_peak_memory(torch)
        else:
            for _ in range(GRANITE_TTM_CPU_FORWARD_COUNT):
                output = model(past_values=past_values)
    forecast = getattr(output, "prediction_outputs", None)
    if forecast is None:
        raise ValueError("Granite TTM output has no prediction_outputs")
    forecast_cpu = forecast.detach().to("cpu")
    peak_memory = int(torch.cuda.max_memory_allocated()) if phase == "cuda" else None
    return GraniteTtmInferenceOutput(
        shape=tuple(int(value) for value in forecast_cpu.shape),
        dtype=str(forecast_cpu.dtype),
        finite=bool(torch.isfinite(forecast_cpu).all().item()),
        comparison_value=forecast_cpu,
        peak_memory_bytes=peak_memory,
    )


def _synthetic_input(torch: Any, device: str) -> Any:
    values = [
        math.sin(2.0 * math.pi * step / 64.0)
        + 0.25 * math.cos(2.0 * math.pi * step / 17.0)
        + 0.001 * step
        for step in range(GRANITE_TTM_CONTEXT_LENGTH)
    ]
    return torch.tensor(values, dtype=torch.float32, device=device).reshape(
        1,
        GRANITE_TTM_CONTEXT_LENGTH,
        GRANITE_TTM_CHANNEL_COUNT,
    )


def _comparison_outcome(reference: Any | None, candidate: Any | None) -> str:
    if reference is None or candidate is None:
        return "not_available"
    torch = _torch()
    if tuple(reference.shape) != tuple(candidate.shape):
        raise ValueError("Granite TTM CPU/CUDA shapes differ")
    if not bool(
        torch.allclose(
            reference,
            candidate,
            atol=GRANITE_TTM_COMPARISON_ATOL,
            rtol=GRANITE_TTM_COMPARISON_RTOL,
        )
    ):
        raise ValueError("Granite TTM CPU/CUDA values exceed tolerance")
    return "within_tolerance"


def _write_or_read_unavailable_cuda(contract: GraniteTtmRuntimeContract) -> GraniteTtmRuntimeRun:
    existing = _try_read_phase_receipt(contract, "cuda")
    if existing is not None:
        return existing
    return _write_phase_receipt(
        contract,
        phase="cuda",
        status="cuda_unavailable",
        terminal_category="cuda_runtime_unavailable",
        elapsed_milliseconds=0,
    )


def _write_phase_receipt(
    contract: GraniteTtmRuntimeContract,
    *,
    phase: Phase,
    status: Literal["completed", "failed", "cuda_unavailable"],
    terminal_category: str,
    elapsed_milliseconds: int,
    output: GraniteTtmInferenceOutput | None = None,
    comparison: str = "not_available",
) -> GraniteTtmRuntimeRun:
    path = contract.run_directory / f"{phase}-receipt.json"
    payload: dict[str, object] = {
        "kind": GRANITE_TTM_RUNTIME_SMOKE_ID,
        "contract_sha256": contract.sha256,
        "model_manifest_sha256": contract.model_manifest_sha256,
        "phase": phase,
        "status": status,
        "terminal_category": terminal_category,
        "elapsed_milliseconds": elapsed_milliseconds,
        "scope": _non_promoting_scope(),
    }
    if output is not None:
        payload["output"] = {
            "shape": list(output.shape),
            "dtype": output.dtype,
            "finite": output.finite,
        }
        payload["peak_memory_bytes"] = output.peak_memory_bytes
        payload["cpu_cuda_comparison"] = comparison
    _write_json_new(path, payload)
    return GraniteTtmRuntimeRun(
        phase=phase,
        status=status,
        terminal_category=terminal_category,
        receipt_path=path,
        receipt_sha256=_sha256_json(payload),
        contract_sha256=contract.sha256,
    )


def _read_phase_receipt(
    contract: GraniteTtmRuntimeContract,
    *,
    phase: Phase,
) -> GraniteTtmRuntimeRun:
    result = _try_read_phase_receipt(contract, phase)
    if result is None:
        raise ValueError("Granite TTM runtime receipt is missing")
    return result


def _try_read_phase_receipt(
    contract: GraniteTtmRuntimeContract,
    phase: Phase,
) -> GraniteTtmRuntimeRun | None:
    path = contract.run_directory / f"{phase}-receipt.json"
    if not path.is_file():
        return None
    payload = _read_json_object(path)
    _validate_phase_receipt(payload, contract=contract, phase=phase)
    return GraniteTtmRuntimeRun(
        phase=phase,
        status=payload["status"],
        terminal_category=payload["terminal_category"],
        receipt_path=path,
        receipt_sha256=_sha256_json(payload),
        contract_sha256=contract.sha256,
    )


def _validate_contract(contract: GraniteTtmRuntimeContract, model: GraniteTtmLocalModel) -> None:
    payload = _read_json_object(contract.path)
    if (
        _sha256_json(payload) != contract.sha256
        or payload.get("kind") != GRANITE_TTM_RUNTIME_SMOKE_ID
        or payload.get("model", {}).get("manifest_sha256") != model.manifest_sha256
        or payload.get("model", {}).get("loader")
        != "tsfm_public.models.tinytimemixer.TinyTimeMixerForPrediction"
        or payload.get("model", {}).get("local_files_only") is not True
        or payload.get("model", {}).get("trust_remote_code") is not False
    ):
        raise ValueError("Granite TTM runtime contract is invalid")


def _reattest_model_instance(
    model: GraniteTtmLocalModel,
    root: Path,
    repository_root: Path | str,
) -> None:
    verified = load_verified_granite_ttm_r1_local_model(
        artifact_root=root,
        repository_root=repository_root,
    )
    if verified != model:
        raise ValueError("Granite TTM model identity changed")


def _validate_model_manifest(payload: Mapping[str, object], directory: Path) -> None:
    if (
        payload.get("kind") != "granite_ttm_r1_local_model_manifest"
        or payload.get("model_id") != GRANITE_TTM_MODEL_ID
        or payload.get("model_revision") != GRANITE_TTM_MODEL_REVISION
        or payload.get("license") != GRANITE_TTM_MODEL_LICENSE
        or payload.get("source_url") != GRANITE_TTM_SOURCE_URL
        or payload.get("safe_serialization") is not True
        or payload.get("runtime_package")
        != {"name": GRANITE_TTM_PACKAGE, "version": GRANITE_TTM_PACKAGE_VERSION}
    ):
        raise ValueError("Granite TTM model manifest is invalid")
    _verified_model_file_records(directory)


def _verified_model_file_records(directory: Path) -> list[dict[str, object]]:
    paths = sorted(path for path in directory.rglob("*") if path.is_file())
    records: list[dict[str, object]] = []
    for path in paths:
        relative = path.relative_to(directory).as_posix()
        if relative == "model-manifest.json":
            continue
        if path.is_symlink() or relative not in _REQUIRED_MODEL_FILES:
            raise ValueError("Granite TTM model contains an unsupported file")
        records.append(
            {"path": relative, "sha256": _sha256_file(path), "size_bytes": path.stat().st_size}
        )
    if {str(record["path"]) for record in records} != _REQUIRED_MODEL_FILES:
        raise ValueError("Granite TTM model safe files are incomplete")
    safetensors = next(record for record in records if record["path"] == "model.safetensors")
    if (
        safetensors["sha256"] != GRANITE_TTM_SAFETENSORS_SHA256
        or safetensors["size_bytes"] != GRANITE_TTM_SAFETENSORS_SIZE
    ):
        raise ValueError("Granite TTM safetensors pin does not match")
    return records


def _external_root(artifact_root: Path | str, repository_root: Path | str) -> Path:
    root = ensure_external_artifact_directory(Path(artifact_root), Path(repository_root))
    if root.is_symlink():
        raise ValueError("Granite TTM artifact root must not be a symlink")
    return root


def _official_snapshot_download(**kwargs: object) -> str:
    from huggingface_hub import snapshot_download

    return str(snapshot_download(**kwargs))


def _failure_category(error: Exception) -> str:
    if isinstance(error, _PhaseTimeoutError):
        return "runtime_timeout"
    if isinstance(error, MemoryError):
        return "memory_cap_exceeded"
    if isinstance(error, (ImportError, ModuleNotFoundError)):
        return "runtime_dependency_unavailable"
    if isinstance(error, (ValueError, TypeError, AttributeError)):
        return "structural_validation_failed"
    return "runtime_failure"


def _validate_inference_output(output: GraniteTtmInferenceOutput, *, phase: Phase) -> None:
    expected = (1, GRANITE_TTM_PREDICTION_LENGTH, GRANITE_TTM_CHANNEL_COUNT)
    if output.shape != expected or not output.dtype or not output.finite:
        raise ValueError("Granite TTM structural output is invalid")
    if output.peak_memory_bytes is not None and output.peak_memory_bytes < 0:
        raise ValueError("Granite TTM peak memory is invalid")
    if (
        phase == "cuda"
        and output.peak_memory_bytes is not None
        and output.peak_memory_bytes > GRANITE_TTM_CUDA_MAX_PEAK_MEMORY_BYTES
    ):
        raise MemoryError("Granite TTM CUDA peak memory exceeds the fixed cap")


def _assert_cuda_peak_memory(torch: Any) -> None:
    if int(torch.cuda.max_memory_allocated()) > GRANITE_TTM_CUDA_MAX_PEAK_MEMORY_BYTES:
        raise MemoryError("Granite TTM CUDA peak memory exceeds the fixed cap")


def _validate_phase_receipt(
    payload: Mapping[str, object],
    *,
    contract: GraniteTtmRuntimeContract,
    phase: Phase,
) -> None:
    if (
        payload.get("kind") != GRANITE_TTM_RUNTIME_SMOKE_ID
        or payload.get("contract_sha256") != contract.sha256
        or payload.get("model_manifest_sha256") != contract.model_manifest_sha256
        or payload.get("phase") != phase
        or payload.get("status") not in {"completed", "failed", "cuda_unavailable"}
        or not isinstance(payload.get("terminal_category"), str)
        or not isinstance(payload.get("elapsed_milliseconds"), int)
        or payload["elapsed_milliseconds"] < 0
        or payload.get("scope") != _non_promoting_scope()
    ):
        raise ValueError("Granite TTM runtime receipt is invalid")
    if payload["status"] != "completed":
        return
    output = payload.get("output")
    if not isinstance(output, Mapping):
        raise ValueError("Granite TTM completed receipt has no structural output")
    if (
        output.get("shape")
        != [1, GRANITE_TTM_PREDICTION_LENGTH, GRANITE_TTM_CHANNEL_COUNT]
        or not isinstance(output.get("dtype"), str)
        or not output["dtype"]
        or output.get("finite") is not True
    ):
        raise ValueError("Granite TTM completed receipt output is invalid")
    if phase != "cuda":
        return
    peak_memory = payload.get("peak_memory_bytes")
    if (
        not isinstance(peak_memory, int)
        or peak_memory < 0
        or peak_memory > GRANITE_TTM_CUDA_MAX_PEAK_MEMORY_BYTES
        or payload.get("cpu_cuda_comparison") != "within_tolerance"
    ):
        raise ValueError("Granite TTM completed CUDA receipt is invalid")


class _phase_timeout:
    """Best-effort per-phase timer in the Linux container, with a portable fallback."""

    def __init__(self, seconds: float) -> None:
        self._seconds = seconds
        self._previous_handler: Any | None = None
        self._enabled = hasattr(signal, "SIGALRM") and hasattr(signal, "setitimer")

    def __enter__(self) -> None:
        if not self._enabled:
            return

        def raise_timeout(_signum: int, _frame: Any) -> None:
            raise _PhaseTimeoutError("Granite TTM structural phase exceeded its timer")

        self._previous_handler = signal.signal(signal.SIGALRM, raise_timeout)
        signal.setitimer(signal.ITIMER_REAL, self._seconds)

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        if not self._enabled:
            return
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, self._previous_handler)


def _timeout_seconds(phase: Phase) -> float:
    return GRANITE_TTM_CPU_TIMEOUT_SECONDS if phase == "cpu" else GRANITE_TTM_CUDA_TIMEOUT_SECONDS


def _elapsed_milliseconds(started: float, finished: float) -> int:
    return max(0, int(round((finished - started) * 1000)))


def _cuda_available() -> bool:
    return bool(_torch().cuda.is_available())


def _torch() -> Any:
    import torch

    return torch


def _non_promoting_scope() -> dict[str, bool]:
    return {
        "market_data_used": False,
        "labels_used": False,
        "prediction_values_persisted": False,
        "paper_input_eligible": False,
        "promotion_eligible": False,
        "profitability_claim": False,
    }


def _read_json_object(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("Granite TTM JSON artifact is invalid") from error
    if not isinstance(payload, dict):
        raise ValueError("Granite TTM JSON artifact is not an object")
    return payload


def _write_json_new(path: Path, payload: Mapping[str, object]) -> None:
    if path.exists():
        raise ValueError("Granite TTM artifact already exists")
    path.write_text(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _remove_partial_directory(directory: Path) -> None:
    if directory.exists() and not directory.is_symlink():
        shutil.rmtree(directory)


def _remove_download_metadata(directory: Path) -> None:
    """Discard downloader bookkeeping so the artifact contains only pinned files."""

    metadata = directory / ".cache"
    if not metadata.exists():
        return
    if metadata.is_symlink() or not metadata.is_dir():
        raise ValueError("Granite TTM downloader metadata is invalid")
    shutil.rmtree(metadata)
