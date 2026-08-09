"""Optional research-profile GPU compute smoke helpers."""

from __future__ import annotations

import argparse
import importlib.util
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.serialization import to_jsonable

from .gpu_runtime import _read_candidate_artifact
from .validation import (
    GpuReadiness,
    _reject_repo_artifact_path,
    detect_gpu_readiness,
    resolve_model_artifact_root,
)

GpuComputeSmokeStatus = Literal["compute_ran_only", "prepared_not_trained"]
TensorSmokeRunner = Callable[[], dict[str, Any]]
DEFAULT_GPU_COMPUTE_RUN_ID = "research-gpu-compute-smoke"
OPTIONAL_GPU_BACKENDS = ("torch", "cupy", "jax", "tensorflow", "numba")


@dataclass(frozen=True)
class GpuComputeSmokeResult:
    run_id: str
    status: GpuComputeSmokeStatus
    checked_at: datetime
    gpu: GpuReadiness
    reason: str
    available_backends: tuple[str, ...]
    selected_backend: str | None = None
    compute_result: dict[str, Any] | None = None
    candidate_artifact: Path | None = None
    candidate_experiment_id: str | None = None
    candidate_parameters: dict[str, Any] | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("run_id is required")
        object.__setattr__(self, "checked_at", self.checked_at.astimezone(UTC))


def run_gpu_compute_smoke(
    *,
    run_id: str = DEFAULT_GPU_COMPUTE_RUN_ID,
    candidate_artifact: Path | None = None,
    gpu: GpuReadiness | None = None,
    tensor_runner: TensorSmokeRunner | None = None,
) -> GpuComputeSmokeResult:
    gpu = gpu or detect_gpu_readiness()
    candidate = _read_candidate_artifact(candidate_artifact)
    available_backends = _available_gpu_backends()
    selected_backend = "injected" if tensor_runner is not None else _selected_backend()
    if not gpu.available:
        return _prepared_result(
            run_id=run_id,
            candidate_artifact=candidate_artifact,
            candidate=candidate,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=selected_backend,
            reason=f"GPU readiness unavailable: {gpu.detail}",
        )
    if tensor_runner is None and selected_backend is None:
        return _prepared_result(
            run_id=run_id,
            candidate_artifact=candidate_artifact,
            candidate=candidate,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=None,
            reason="no research GPU compute backend installed",
        )
    runner = tensor_runner or _run_torch_cuda_tensor_smoke
    try:
        compute_result = runner()
    except Exception as exc:  # noqa: BLE001 - smoke records non-fatal backend failures.
        return _prepared_result(
            run_id=run_id,
            candidate_artifact=candidate_artifact,
            candidate=candidate,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=selected_backend,
            reason=f"GPU compute backend unavailable: {exc}",
        )
    return GpuComputeSmokeResult(
        run_id=run_id,
        status="compute_ran_only",
        checked_at=datetime.now(UTC),
        gpu=gpu,
        reason="tiny deterministic GPU compute smoke completed",
        available_backends=available_backends,
        selected_backend=selected_backend,
        compute_result=compute_result,
        candidate_artifact=candidate_artifact,
        candidate_experiment_id=candidate.get("candidate_experiment_id"),
        candidate_parameters=candidate.get("candidate_parameters"),
    )


def write_gpu_compute_smoke_artifact(
    result: GpuComputeSmokeResult,
    *,
    artifact_root: Path,
    repo_root: Path | None = None,
) -> Path:
    _reject_repo_artifact_path(artifact_root, repo_root)
    output_dir = artifact_root / "gpu-compute"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{result.run_id}.json"
    path.write_text(
        json.dumps(_gpu_compute_payload(result, artifact_root), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=DEFAULT_GPU_COMPUTE_RUN_ID)
    parser.add_argument("--candidate-artifact", type=Path)
    parser.add_argument("--artifact-root", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    artifact_root = args.artifact_root or resolve_model_artifact_root()
    result = run_gpu_compute_smoke(
        run_id=args.run_id,
        candidate_artifact=args.candidate_artifact,
    )
    artifact = write_gpu_compute_smoke_artifact(
        result,
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
    )
    print(
        json.dumps(
            {
                "result": _gpu_compute_payload(result, artifact_root),
                "artifacts": {"gpu_compute_smoke": str(artifact)},
            },
            indent=2,
            sort_keys=True,
        )
    )


def _prepared_result(
    *,
    run_id: str,
    candidate_artifact: Path | None,
    candidate: dict[str, Any],
    gpu: GpuReadiness,
    available_backends: tuple[str, ...],
    selected_backend: str | None,
    reason: str,
) -> GpuComputeSmokeResult:
    return GpuComputeSmokeResult(
        run_id=run_id,
        status="prepared_not_trained",
        checked_at=datetime.now(UTC),
        gpu=gpu,
        reason=reason,
        available_backends=available_backends,
        selected_backend=selected_backend,
        candidate_artifact=candidate_artifact,
        candidate_experiment_id=candidate.get("candidate_experiment_id"),
        candidate_parameters=candidate.get("candidate_parameters"),
    )


def _available_gpu_backends() -> tuple[str, ...]:
    return tuple(
        backend
        for backend in OPTIONAL_GPU_BACKENDS
        if importlib.util.find_spec(backend) is not None
    )


def _selected_backend() -> str | None:
    if importlib.util.find_spec("torch") is not None:
        return "torch"
    return None


def _run_torch_cuda_tensor_smoke() -> dict[str, Any]:
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("torch CUDA is not available")
    device = torch.device("cuda")
    tensor = torch.tensor([1.0, 2.0, 3.0], device=device)
    result = (tensor * tensor).sum()
    torch.cuda.synchronize()
    return {
        "backend": "torch",
        "operation": "sum_of_squares",
        "input_size": 3,
        "result": f"{result.item():.4f}",
        "device": torch.cuda.get_device_name(device),
    }


def _gpu_compute_payload(
    result: GpuComputeSmokeResult,
    artifact_root: Path,
) -> dict[str, Any]:
    return to_jsonable(
        {
            "schema_version": result.schema_version,
            "run_id": result.run_id,
            "status": result.status,
            "checked_at": result.checked_at,
            "gpu": result.gpu,
            "reason": result.reason,
            "available_backends": result.available_backends,
            "selected_backend": result.selected_backend,
            "compute_result": result.compute_result or {},
            "candidate_artifact": (
                None if result.candidate_artifact is None else str(result.candidate_artifact)
            ),
            "candidate_experiment_id": result.candidate_experiment_id,
            "candidate_parameters": result.candidate_parameters or {},
            "artifact_policy": {
                "root": str(artifact_root),
                "repo_storage_allowed": False,
            },
        }
    )


if __name__ == "__main__":
    main()
