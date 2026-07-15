"""Minimal Engine Research job runner."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.serialization import to_jsonable

from .candidate_training import (
    BoundedCandidateTrainingResult,
    CandidateTrainerRunner,
    CandidateTrainingConfig,
    run_bounded_candidate_training,
)
from .gpu_training import (
    GpuTrainingSmokeResult,
    TrainingSmokeRunner,
    run_gpu_training_smoke,
    write_gpu_training_smoke_artifact,
)
from .validation import (
    GpuReadiness,
    _reject_repo_artifact_path,
    resolve_model_artifact_root,
)

ResearchJobKind = Literal["gpu_training_smoke", "candidate_training"]
ResearchJobStatus = Literal["completed", "prepared_not_trained"]
DEFAULT_RESEARCH_JOB_ID = "engine-research-gpu-training-smoke"
SUPPORTED_RESEARCH_JOB_KINDS = ("gpu_training_smoke", "candidate_training")


@dataclass(frozen=True)
class ResearchJobSpec:
    job_id: str = DEFAULT_RESEARCH_JOB_ID
    kind: ResearchJobKind = "gpu_training_smoke"
    candidate_artifact: Path | None = None
    yahoo_snapshot: Path | None = None
    symbol: str | None = None
    max_bars: int = 120
    max_epochs: int = 8
    max_steps: int = 256
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.job_id:
            raise ValueError("job_id is required")
        if self.kind not in SUPPORTED_RESEARCH_JOB_KINDS:
            raise ValueError(f"unsupported research job kind: {self.kind}")
        object.__setattr__(self, "created_at", self.created_at.astimezone(UTC))


@dataclass(frozen=True)
class ResearchJobResult:
    job_id: str
    kind: ResearchJobKind
    status: ResearchJobStatus
    created_at: datetime
    started_at: datetime
    completed_at: datetime
    reason: str
    training: GpuTrainingSmokeResult | BoundedCandidateTrainingResult
    training_artifact: Path
    model_artifact: Path | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "created_at", self.created_at.astimezone(UTC))
        object.__setattr__(self, "started_at", self.started_at.astimezone(UTC))
        object.__setattr__(self, "completed_at", self.completed_at.astimezone(UTC))


@dataclass(frozen=True)
class ResearchJobRun:
    result: ResearchJobResult
    job_artifact: Path


def run_and_write_research_job(
    spec: ResearchJobSpec,
    *,
    artifact_root: Path,
    repo_root: Path | None = None,
    gpu: GpuReadiness | None = None,
    trainer_runner: TrainingSmokeRunner | None = None,
    candidate_trainer_runner: CandidateTrainerRunner | None = None,
) -> ResearchJobRun:
    _reject_repo_artifact_path(artifact_root, repo_root)
    started_at = datetime.now(UTC)
    training, training_artifact, model_artifact, status = _run_job_kind(
        spec,
        artifact_root=artifact_root,
        repo_root=repo_root,
        gpu=gpu,
        trainer_runner=trainer_runner,
        candidate_trainer_runner=candidate_trainer_runner,
    )
    result = ResearchJobResult(
        job_id=spec.job_id,
        kind=spec.kind,
        status=status,
        created_at=spec.created_at,
        started_at=started_at,
        completed_at=datetime.now(UTC),
        reason=training.reason,
        training=training,
        training_artifact=training_artifact,
        model_artifact=model_artifact,
    )
    job_artifact = write_research_job_artifact(
        result,
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    return ResearchJobRun(result=result, job_artifact=job_artifact)


def _run_job_kind(
    spec: ResearchJobSpec,
    *,
    artifact_root: Path,
    repo_root: Path | None,
    gpu: GpuReadiness | None,
    trainer_runner: TrainingSmokeRunner | None,
    candidate_trainer_runner: CandidateTrainerRunner | None,
) -> tuple[
    GpuTrainingSmokeResult | BoundedCandidateTrainingResult,
    Path,
    Path | None,
    ResearchJobStatus,
]:
    if spec.kind == "gpu_training_smoke":
        training = run_gpu_training_smoke(
            run_id=spec.job_id,
            candidate_artifact=spec.candidate_artifact,
            gpu=gpu,
            trainer_runner=trainer_runner,
        )
        training_artifact = write_gpu_training_smoke_artifact(
            training,
            artifact_root=artifact_root,
            repo_root=repo_root,
        )
        status: ResearchJobStatus = (
            "completed" if training.status == "training_ran_only" else "prepared_not_trained"
        )
        return training, training_artifact, None, status
    if spec.kind == "candidate_training":
        training = run_bounded_candidate_training(
            config=CandidateTrainingConfig(
                run_id=spec.job_id,
                max_epochs=spec.max_epochs,
                max_steps=spec.max_steps,
                max_bars=spec.max_bars,
            ),
            artifact_root=artifact_root,
            repo_root=repo_root,
            candidate_artifact=spec.candidate_artifact,
            yahoo_snapshot=spec.yahoo_snapshot,
            symbol=spec.symbol,
            gpu=gpu,
            trainer_runner=candidate_trainer_runner,
        )
        status = (
            "completed"
            if training.status == "candidate_trained_only"
            else "prepared_not_trained"
        )
        return training, training.metrics_artifact, training.model_artifact, status
    raise ValueError(f"unsupported research job kind: {spec.kind}")


def write_research_job_artifact(
    result: ResearchJobResult,
    *,
    artifact_root: Path,
    repo_root: Path | None = None,
) -> Path:
    _reject_repo_artifact_path(artifact_root, repo_root)
    output_dir = artifact_root / "research-jobs"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{result.job_id}.json"
    path.write_text(
        json.dumps(_research_job_payload(result, artifact_root), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", default=DEFAULT_RESEARCH_JOB_ID)
    parser.add_argument(
        "--kind",
        default="gpu_training_smoke",
        choices=SUPPORTED_RESEARCH_JOB_KINDS,
    )
    parser.add_argument("--candidate-artifact", type=Path)
    parser.add_argument("--yahoo-snapshot", type=Path)
    parser.add_argument("--symbol")
    parser.add_argument("--max-bars", type=int, default=120)
    parser.add_argument("--max-epochs", type=int, default=8)
    parser.add_argument("--max-steps", type=int, default=256)
    parser.add_argument("--artifact-root", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    artifact_root = args.artifact_root or resolve_model_artifact_root()
    spec = ResearchJobSpec(
        job_id=args.job_id,
        kind=args.kind,
        candidate_artifact=args.candidate_artifact,
        yahoo_snapshot=args.yahoo_snapshot,
        symbol=args.symbol,
        max_bars=args.max_bars,
        max_epochs=args.max_epochs,
        max_steps=args.max_steps,
    )
    run = run_and_write_research_job(
        spec,
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
    )
    print(
        json.dumps(
            {
                "result": _research_job_payload(run.result, artifact_root),
                "artifacts": {
                    "research_job": str(run.job_artifact),
                    **_research_job_artifacts(run.result),
                },
            },
            indent=2,
            sort_keys=True,
        )
    )


def _research_job_payload(
    result: ResearchJobResult,
    artifact_root: Path,
) -> dict[str, object]:
    training = result.training
    base: dict[str, object] = {
        "schema_version": result.schema_version,
        "job_id": result.job_id,
        "kind": result.kind,
        "status": result.status,
        "created_at": result.created_at,
        "started_at": result.started_at,
        "completed_at": result.completed_at,
        "reason": result.reason,
        "candidate_artifact": (
            None if training.candidate_artifact is None else str(training.candidate_artifact)
        ),
        "candidate_experiment_id": training.candidate_experiment_id,
        "candidate_parameters": training.candidate_parameters or {},
        "artifacts": _research_job_artifacts(result),
        "artifact_policy": {
            "root": str(artifact_root),
            "repo_storage_allowed": False,
        },
    }
    if isinstance(training, GpuTrainingSmokeResult):
        base["training"] = {
            "status": training.status,
            "reason": training.reason,
            "available_backends": training.available_backends,
            "selected_backend": training.selected_backend,
            "gpu": training.gpu,
            "result": training.training_result or {},
        }
    elif isinstance(training, BoundedCandidateTrainingResult):
        base["candidate_training"] = {
            "status": training.status,
            "reason": training.reason,
            "available_backends": training.available_backends,
            "selected_backend": training.selected_backend,
            "gpu": training.gpu,
            "data_source": training.data_source,
            "symbol": training.symbol,
            "market": training.market,
            "timeframe": training.timeframe,
            "bars_seen": training.bars_seen,
            "examples_seen": training.examples_seen,
            "max_epochs": training.max_epochs,
            "max_steps": training.max_steps,
            "metrics": training.metrics,
        }
    return to_jsonable(base)


def _research_job_artifacts(result: ResearchJobResult) -> dict[str, str]:
    if isinstance(result.training, GpuTrainingSmokeResult):
        return {"training_smoke": str(result.training_artifact)}
    artifacts = {"candidate_metrics": str(result.training_artifact)}
    if result.model_artifact is not None:
        artifacts["model"] = str(result.model_artifact)
    return artifacts


if __name__ == "__main__":
    main()
