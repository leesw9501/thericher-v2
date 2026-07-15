"""Optional research-profile GPU training smoke helpers."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.serialization import to_jsonable

from .gpu_compute import _available_gpu_backends, _selected_backend
from .gpu_runtime import _read_candidate_artifact
from .validation import (
    GpuReadiness,
    _reject_repo_artifact_path,
    detect_gpu_readiness,
    resolve_model_artifact_root,
)

GpuTrainingSmokeStatus = Literal["training_ran_only", "prepared_not_trained"]
TrainingSmokeRunner = Callable[[dict[str, Any]], dict[str, Any]]
DEFAULT_GPU_TRAINING_RUN_ID = "research-gpu-training-smoke"


@dataclass(frozen=True)
class GpuTrainingSmokeResult:
    run_id: str
    status: GpuTrainingSmokeStatus
    checked_at: datetime
    gpu: GpuReadiness
    reason: str
    available_backends: tuple[str, ...]
    selected_backend: str | None = None
    training_result: dict[str, Any] | None = None
    candidate_artifact: Path | None = None
    candidate_experiment_id: str | None = None
    candidate_parameters: dict[str, Any] | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("run_id is required")
        object.__setattr__(self, "checked_at", self.checked_at.astimezone(UTC))


def run_gpu_training_smoke(
    *,
    run_id: str = DEFAULT_GPU_TRAINING_RUN_ID,
    candidate_artifact: Path | None = None,
    gpu: GpuReadiness | None = None,
    trainer_runner: TrainingSmokeRunner | None = None,
) -> GpuTrainingSmokeResult:
    gpu = gpu or detect_gpu_readiness()
    candidate = _read_candidate_artifact(candidate_artifact)
    available_backends = _available_gpu_backends()
    selected_backend = "injected" if trainer_runner is not None else _selected_backend()
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
    if trainer_runner is None and selected_backend is None:
        return _prepared_result(
            run_id=run_id,
            candidate_artifact=candidate_artifact,
            candidate=candidate,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=None,
            reason="no operator-approved research GPU training backend installed",
        )
    runner = trainer_runner or _run_torch_cuda_training_smoke
    try:
        training_result = runner(candidate)
    except Exception as exc:  # noqa: BLE001 - smoke records non-fatal backend failures.
        return _prepared_result(
            run_id=run_id,
            candidate_artifact=candidate_artifact,
            candidate=candidate,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=selected_backend,
            reason=f"GPU training smoke unavailable: {exc}",
        )
    return GpuTrainingSmokeResult(
        run_id=run_id,
        status="training_ran_only",
        checked_at=datetime.now(UTC),
        gpu=gpu,
        reason="tiny deterministic GPU training smoke completed",
        available_backends=available_backends,
        selected_backend=selected_backend,
        training_result=training_result,
        candidate_artifact=candidate_artifact,
        candidate_experiment_id=candidate.get("candidate_experiment_id"),
        candidate_parameters=candidate.get("candidate_parameters"),
    )


def write_gpu_training_smoke_artifact(
    result: GpuTrainingSmokeResult,
    *,
    artifact_root: Path,
    repo_root: Path | None = None,
) -> Path:
    _reject_repo_artifact_path(artifact_root, repo_root)
    output_dir = artifact_root / "gpu-training"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{result.run_id}.json"
    path.write_text(
        json.dumps(_gpu_training_payload(result, artifact_root), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=DEFAULT_GPU_TRAINING_RUN_ID)
    parser.add_argument("--candidate-artifact", type=Path)
    parser.add_argument("--artifact-root", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    artifact_root = args.artifact_root or resolve_model_artifact_root()
    result = run_gpu_training_smoke(
        run_id=args.run_id,
        candidate_artifact=args.candidate_artifact,
    )
    artifact = write_gpu_training_smoke_artifact(
        result,
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
    )
    print(
        json.dumps(
            {
                "result": _gpu_training_payload(result, artifact_root),
                "artifacts": {"gpu_training_smoke": str(artifact)},
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
) -> GpuTrainingSmokeResult:
    return GpuTrainingSmokeResult(
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


def _run_torch_cuda_training_smoke(candidate: dict[str, Any]) -> dict[str, Any]:
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("torch CUDA is not available")
    torch.manual_seed(23)
    device = torch.device("cuda")
    x = torch.tensor([[0.0], [1.0], [2.0], [3.0]], device=device)
    y = 2 * x + 1
    model = torch.nn.Linear(1, 1).to(device)
    with torch.no_grad():
        model.weight.fill_(0.1)
        model.bias.fill_(0.0)
    optimizer = torch.optim.SGD(model.parameters(), lr=0.01)
    loss_fn = torch.nn.MSELoss()
    initial_loss = loss_fn(model(x), y)
    for _ in range(5):
        optimizer.zero_grad()
        loss = loss_fn(model(x), y)
        loss.backward()
        optimizer.step()
    torch.cuda.synchronize()
    final_loss = loss_fn(model(x), y)
    return {
        "backend": "torch",
        "operation": "tiny_linear_regression_training_step",
        "steps": 5,
        "input_rows": 4,
        "initial_loss": f"{initial_loss.item():.6f}",
        "final_loss": f"{final_loss.item():.6f}",
        "device": torch.cuda.get_device_name(device),
        "candidate_experiment_id": candidate.get("candidate_experiment_id"),
    }


def _gpu_training_payload(
    result: GpuTrainingSmokeResult,
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
            "training_result": result.training_result or {},
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
