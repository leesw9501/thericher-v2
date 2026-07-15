"""Research-profile GPU runtime smoke helpers."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.serialization import to_jsonable

from .validation import (
    GpuReadiness,
    _reject_repo_artifact_path,
    detect_gpu_readiness,
    resolve_model_artifact_root,
)

GpuRuntimeSmokeStatus = Literal["runtime_ready_only", "prepared_not_trained"]
DEFAULT_GPU_RUNTIME_RUN_ID = "research-gpu-runtime-smoke"


@dataclass(frozen=True)
class GpuRuntimeSmokeResult:
    run_id: str
    status: GpuRuntimeSmokeStatus
    checked_at: datetime
    gpu: GpuReadiness
    reason: str
    candidate_artifact: Path | None = None
    candidate_experiment_id: str | None = None
    candidate_parameters: dict[str, Any] | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("run_id is required")
        object.__setattr__(self, "checked_at", self.checked_at.astimezone(UTC))


def run_gpu_runtime_smoke(
    *,
    run_id: str = DEFAULT_GPU_RUNTIME_RUN_ID,
    candidate_artifact: Path | None = None,
    gpu: GpuReadiness | None = None,
) -> GpuRuntimeSmokeResult:
    gpu = gpu or detect_gpu_readiness()
    candidate = _read_candidate_artifact(candidate_artifact)
    if gpu.available:
        status: GpuRuntimeSmokeStatus = "runtime_ready_only"
        reason = "nvidia-smi readiness detected; GPU compute smoke deferred"
    else:
        status = "prepared_not_trained"
        reason = f"GPU runtime unavailable: {gpu.detail}"
    return GpuRuntimeSmokeResult(
        run_id=run_id,
        status=status,
        checked_at=datetime.now(UTC),
        gpu=gpu,
        reason=reason,
        candidate_artifact=candidate_artifact,
        candidate_experiment_id=candidate.get("candidate_experiment_id"),
        candidate_parameters=candidate.get("candidate_parameters"),
    )


def write_gpu_runtime_smoke_artifact(
    result: GpuRuntimeSmokeResult,
    *,
    artifact_root: Path,
    repo_root: Path | None = None,
) -> Path:
    _reject_repo_artifact_path(artifact_root, repo_root)
    output_dir = artifact_root / "gpu-runtime"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{result.run_id}.json"
    path.write_text(
        json.dumps(_gpu_runtime_payload(result, artifact_root), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=DEFAULT_GPU_RUNTIME_RUN_ID)
    parser.add_argument("--candidate-artifact", type=Path)
    parser.add_argument("--artifact-root", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    artifact_root = args.artifact_root or resolve_model_artifact_root()
    result = run_gpu_runtime_smoke(
        run_id=args.run_id,
        candidate_artifact=args.candidate_artifact,
    )
    artifact = write_gpu_runtime_smoke_artifact(
        result,
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
    )
    print(
        json.dumps(
            {
                "result": _gpu_runtime_payload(result, artifact_root),
                "artifacts": {"gpu_runtime_smoke": str(artifact)},
            },
            indent=2,
            sort_keys=True,
        )
    )


def _read_candidate_artifact(candidate_artifact: Path | None) -> dict[str, Any]:
    if candidate_artifact is None:
        return {}
    payload = json.loads(candidate_artifact.read_text(encoding="utf-8"))
    return {
        "candidate_experiment_id": payload.get("candidate_experiment_id"),
        "candidate_parameters": payload.get("candidate_parameters"),
    }


def _gpu_runtime_payload(
    result: GpuRuntimeSmokeResult,
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
