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

from .candidate_comparison import (
    BoundedCandidateReplayComparisonResult,
    CandidateReplayComparisonConfig,
    run_bounded_candidate_replay_comparison,
)
from .candidate_evaluation import (
    BoundedCandidateEvaluationResult,
    CandidateEvaluationConfig,
    CandidateEvaluationRunner,
    run_bounded_candidate_evaluation,
)
from .candidate_replay import (
    BoundedCandidateReplayResult,
    CandidateProbabilityRunner,
    CandidateReplayConfig,
    run_bounded_candidate_replay,
)
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

ResearchJobKind = Literal[
    "gpu_training_smoke",
    "candidate_training",
    "candidate_evaluation",
    "candidate_replay",
    "candidate_replay_comparison",
]
ResearchJobStatus = Literal[
    "completed",
    "prepared_not_trained",
    "prepared_not_evaluated",
    "prepared_not_replayed",
    "prepared_not_compared",
]
DEFAULT_RESEARCH_JOB_ID = "engine-research-gpu-training-smoke"
SUPPORTED_RESEARCH_JOB_KINDS = (
    "gpu_training_smoke",
    "candidate_training",
    "candidate_evaluation",
    "candidate_replay",
    "candidate_replay_comparison",
)


@dataclass(frozen=True)
class ResearchJobSpec:
    job_id: str = DEFAULT_RESEARCH_JOB_ID
    kind: ResearchJobKind = "gpu_training_smoke"
    candidate_artifact: Path | None = None
    training_metrics_artifact: Path | None = None
    evaluation_artifact: Path | None = None
    candidate_replay_artifact: Path | None = None
    model_artifact: Path | None = None
    yahoo_snapshot: Path | None = None
    symbol: str | None = None
    max_bars: int = 120
    max_epochs: int = 8
    max_steps: int = 256
    buy_threshold: float = 0.55
    sell_threshold: float = 0.45
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
    training: (
        GpuTrainingSmokeResult
        | BoundedCandidateTrainingResult
        | BoundedCandidateEvaluationResult
        | BoundedCandidateReplayResult
        | BoundedCandidateReplayComparisonResult
    )
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
    candidate_evaluation_runner: CandidateEvaluationRunner | None = None,
    candidate_probability_runner: CandidateProbabilityRunner | None = None,
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
        candidate_evaluation_runner=candidate_evaluation_runner,
        candidate_probability_runner=candidate_probability_runner,
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
    candidate_evaluation_runner: CandidateEvaluationRunner | None,
    candidate_probability_runner: CandidateProbabilityRunner | None,
) -> tuple[
    GpuTrainingSmokeResult
    | BoundedCandidateTrainingResult
    | BoundedCandidateEvaluationResult
    | BoundedCandidateReplayResult
    | BoundedCandidateReplayComparisonResult,
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
    if spec.kind == "candidate_evaluation":
        evaluation = run_bounded_candidate_evaluation(
            config=CandidateEvaluationConfig(
                run_id=spec.job_id,
                max_bars=spec.max_bars,
            ),
            artifact_root=artifact_root,
            repo_root=repo_root,
            training_metrics_artifact=spec.training_metrics_artifact,
            model_artifact=spec.model_artifact,
            yahoo_snapshot=spec.yahoo_snapshot,
            symbol=spec.symbol,
            gpu=gpu,
            evaluation_runner=candidate_evaluation_runner,
        )
        status = (
            "completed"
            if evaluation.status == "candidate_evaluated_only"
            else "prepared_not_evaluated"
        )
        return evaluation, evaluation.evaluation_artifact, evaluation.model_artifact, status
    if spec.kind == "candidate_replay":
        replay = run_bounded_candidate_replay(
            config=CandidateReplayConfig(
                run_id=spec.job_id,
                max_bars=spec.max_bars,
                buy_threshold=spec.buy_threshold,
                sell_threshold=spec.sell_threshold,
            ),
            artifact_root=artifact_root,
            repo_root=repo_root,
            training_metrics_artifact=spec.training_metrics_artifact,
            evaluation_artifact=spec.evaluation_artifact,
            model_artifact=spec.model_artifact,
            yahoo_snapshot=spec.yahoo_snapshot,
            symbol=spec.symbol,
            gpu=gpu,
            probability_runner=candidate_probability_runner,
        )
        status = (
            "completed"
            if replay.status == "candidate_replayed_only"
            else "prepared_not_replayed"
        )
        return replay, replay.replay_artifact, replay.model_artifact, status
    if spec.kind == "candidate_replay_comparison":
        comparison = run_bounded_candidate_replay_comparison(
            config=CandidateReplayComparisonConfig(
                run_id=spec.job_id,
                max_bars=spec.max_bars,
                buy_threshold=spec.buy_threshold,
                sell_threshold=spec.sell_threshold,
            ),
            artifact_root=artifact_root,
            repo_root=repo_root,
            candidate_replay_artifact=spec.candidate_replay_artifact,
            training_metrics_artifact=spec.training_metrics_artifact,
            evaluation_artifact=spec.evaluation_artifact,
            model_artifact=spec.model_artifact,
            yahoo_snapshot=spec.yahoo_snapshot,
            symbol=spec.symbol,
            gpu=gpu,
            probability_runner=candidate_probability_runner,
        )
        status = (
            "completed"
            if comparison.status == "candidate_compared_only"
            else "prepared_not_compared"
        )
        return comparison, comparison.comparison_artifact, comparison.model_artifact, status
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
    parser.add_argument("--training-metrics-artifact", type=Path)
    parser.add_argument("--evaluation-artifact", type=Path)
    parser.add_argument("--candidate-replay-artifact", type=Path)
    parser.add_argument("--model-artifact", type=Path)
    parser.add_argument("--yahoo-snapshot", type=Path)
    parser.add_argument("--symbol")
    parser.add_argument("--max-bars", type=int, default=120)
    parser.add_argument("--max-epochs", type=int, default=8)
    parser.add_argument("--max-steps", type=int, default=256)
    parser.add_argument("--buy-threshold", type=float, default=0.55)
    parser.add_argument("--sell-threshold", type=float, default=0.45)
    parser.add_argument("--artifact-root", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    artifact_root = args.artifact_root or resolve_model_artifact_root()
    spec = ResearchJobSpec(
        job_id=args.job_id,
        kind=args.kind,
        candidate_artifact=args.candidate_artifact,
        training_metrics_artifact=args.training_metrics_artifact,
        evaluation_artifact=args.evaluation_artifact,
        candidate_replay_artifact=args.candidate_replay_artifact,
        model_artifact=args.model_artifact,
        yahoo_snapshot=args.yahoo_snapshot,
        symbol=args.symbol,
        max_bars=args.max_bars,
        max_epochs=args.max_epochs,
        max_steps=args.max_steps,
        buy_threshold=args.buy_threshold,
        sell_threshold=args.sell_threshold,
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
    candidate_artifact = getattr(training, "candidate_artifact", None)
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
            None if candidate_artifact is None else str(candidate_artifact)
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
    elif isinstance(training, BoundedCandidateEvaluationResult):
        base["candidate_artifact"] = (
            None if training.candidate_artifact is None else str(training.candidate_artifact)
        )
        base["candidate_evaluation"] = {
            "status": training.status,
            "reason": training.reason,
            "available_backends": training.available_backends,
            "selected_backend": training.selected_backend,
            "gpu": training.gpu,
            "training_metrics_artifact": (
                None
                if training.training_metrics_artifact is None
                else str(training.training_metrics_artifact)
            ),
            "model_artifact": (
                None if training.model_artifact is None else str(training.model_artifact)
            ),
            "data_source": training.data_source,
            "symbol": training.symbol,
            "market": training.market,
            "timeframe": training.timeframe,
            "bars_seen": training.bars_seen,
            "examples_seen": training.examples_seen,
            "metrics": training.metrics,
            "local_paper_conversion": training.local_paper_conversion,
        }
    elif isinstance(training, BoundedCandidateReplayResult):
        base["candidate_replay"] = {
            "status": training.status,
            "reason": training.reason,
            "available_backends": training.available_backends,
            "selected_backend": training.selected_backend,
            "gpu": training.gpu,
            "training_metrics_artifact": (
                None
                if training.training_metrics_artifact is None
                else str(training.training_metrics_artifact)
            ),
            "evaluation_artifact": (
                None if training.evaluation_artifact is None else str(training.evaluation_artifact)
            ),
            "model_artifact": (
                None if training.model_artifact is None else str(training.model_artifact)
            ),
            "data_source": training.data_source,
            "symbol": training.symbol,
            "market": training.market,
            "timeframe": training.timeframe,
            "bars_seen": training.bars_seen,
            "examples_seen": training.examples_seen,
            "decisions_seen": training.decisions_seen,
            "order_intents_seen": training.order_intents_seen,
            "trade_count": len(training.trades),
            "replay_fill_count": training.replay_fill_count,
            "ending_cash": training.ending_cash,
            "equity": training.equity,
            "pnl": training.pnl,
            "max_drawdown": training.max_drawdown,
            "thresholds": training.thresholds,
            "probability_metrics": training.probability_metrics,
        }
    elif isinstance(training, BoundedCandidateReplayComparisonResult):
        base["candidate_replay_comparison"] = {
            "status": training.status,
            "reason": training.reason,
            "gpu": training.gpu,
            "training_metrics_artifact": (
                None
                if training.training_metrics_artifact is None
                else str(training.training_metrics_artifact)
            ),
            "evaluation_artifact": (
                None if training.evaluation_artifact is None else str(training.evaluation_artifact)
            ),
            "model_artifact": (
                None if training.model_artifact is None else str(training.model_artifact)
            ),
            "candidate_replay_artifact": (
                None
                if training.candidate_replay_artifact is None
                else str(training.candidate_replay_artifact)
            ),
            "data_source": training.data_source,
            "symbol": training.symbol,
            "market": training.market,
            "timeframe": training.timeframe,
            "bars_seen": training.bars_seen,
            "candidate_status": training.candidate_status,
            "baseline_status": training.baseline_status,
            "candidate_metrics": training.candidate_metrics,
            "baseline_metrics": training.baseline_metrics,
            "source_alignment": training.source_alignment,
            "deltas": training.deltas,
            "thresholds": training.thresholds,
        }
    return to_jsonable(base)


def _research_job_artifacts(result: ResearchJobResult) -> dict[str, str]:
    if isinstance(result.training, GpuTrainingSmokeResult):
        return {"training_smoke": str(result.training_artifact)}
    if isinstance(result.training, BoundedCandidateEvaluationResult):
        artifacts = {"candidate_evaluation": str(result.training_artifact)}
        if result.model_artifact is not None:
            artifacts["source_model"] = str(result.model_artifact)
        return artifacts
    if isinstance(result.training, BoundedCandidateReplayResult):
        artifacts = {"candidate_replay": str(result.training_artifact)}
        if result.model_artifact is not None:
            artifacts["source_model"] = str(result.model_artifact)
        return artifacts
    if isinstance(result.training, BoundedCandidateReplayComparisonResult):
        artifacts = {
            "candidate_replay_comparison": str(result.training_artifact),
            "baseline_events": str(result.training.baseline_events),
        }
        if result.training.candidate_replay_artifact is not None:
            artifacts["candidate_replay"] = str(result.training.candidate_replay_artifact)
        if result.model_artifact is not None:
            artifacts["source_model"] = str(result.model_artifact)
        return artifacts
    artifacts = {"candidate_metrics": str(result.training_artifact)}
    if result.model_artifact is not None:
        artifacts["model"] = str(result.model_artifact)
    return artifacts


if __name__ == "__main__":
    main()
