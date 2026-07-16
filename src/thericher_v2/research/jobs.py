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

from .candidate_breadth_holdout import (
    BoundedCandidateBreadthHoldoutResult,
    CandidateBreadthHoldoutConfig,
    CandidateBreadthHoldoutVariantResult,
    run_bounded_candidate_breadth_holdout,
)
from .candidate_breadth_queue import (
    BoundedCandidateBreadthQueueResult,
    CandidateBreadthQueueConfig,
    CandidateBreadthVariantResult,
    run_bounded_candidate_breadth_queue,
)
from .candidate_comparison import (
    BoundedCandidateReplayComparisonResult,
    CandidateReplayComparisonConfig,
    run_bounded_candidate_replay_comparison,
)
from .candidate_depth_comparison import (
    BoundedCandidateDepthComparisonResult,
    CandidateDepthComparisonConfig,
    run_bounded_candidate_depth_comparison,
)
from .candidate_depth_target import (
    BoundedCandidateDepthTargetResult,
    CandidateDepthTargetConfig,
    run_bounded_candidate_depth_target,
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
from .candidate_threshold_calibration import (
    BoundedCandidateThresholdCalibrationResult,
    CandidateThresholdCalibrationConfig,
    run_bounded_candidate_threshold_calibration,
)
from .candidate_threshold_holdout import (
    BoundedCandidateThresholdHoldoutResult,
    CandidateThresholdHoldoutConfig,
    run_bounded_candidate_threshold_holdout,
)
from .candidate_threshold_robustness import (
    BoundedCandidateThresholdRobustnessResult,
    CandidateThresholdRobustnessConfig,
    CandidateThresholdRobustnessSliceConfig,
    _candidate_threshold_robustness_slice_payload,
    parse_robustness_slices,
    run_bounded_candidate_threshold_robustness,
)
from .candidate_threshold_sweep import (
    BoundedCandidateThresholdSweepResult,
    CandidateThresholdSweepConfig,
    parse_threshold_pairs,
    run_bounded_candidate_threshold_sweep,
)
from .candidate_training import (
    BoundedCandidateTrainingResult,
    CandidateDataSliceConfig,
    CandidateTrainerRunner,
    CandidateTrainingConfig,
    parse_candidate_data_slices,
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
    "candidate_breadth_holdout",
    "candidate_breadth_queue",
    "candidate_depth_comparison",
    "candidate_depth_target",
    "candidate_training",
    "candidate_evaluation",
    "candidate_replay",
    "candidate_replay_comparison",
    "candidate_threshold_sweep",
    "candidate_threshold_robustness",
    "candidate_threshold_calibration",
    "candidate_threshold_holdout",
]
ResearchJobStatus = Literal[
    "completed",
    "prepared_not_breadth_holdout_replayed",
    "prepared_not_breadth_queued",
    "prepared_not_depth_compared",
    "prepared_not_depth_targeted",
    "prepared_not_trained",
    "prepared_not_evaluated",
    "prepared_not_replayed",
    "prepared_not_compared",
    "prepared_not_swept",
    "prepared_not_robustness_replayed",
    "prepared_not_calibrated",
    "prepared_not_holdout_replayed",
]
DEFAULT_RESEARCH_JOB_ID = "engine-research-gpu-training-smoke"
SUPPORTED_RESEARCH_JOB_KINDS = (
    "gpu_training_smoke",
    "candidate_breadth_holdout",
    "candidate_breadth_queue",
    "candidate_depth_comparison",
    "candidate_depth_target",
    "candidate_training",
    "candidate_evaluation",
    "candidate_replay",
    "candidate_replay_comparison",
    "candidate_threshold_sweep",
    "candidate_threshold_robustness",
    "candidate_threshold_calibration",
    "candidate_threshold_holdout",
)


@dataclass(frozen=True)
class ResearchJobSpec:
    job_id: str = DEFAULT_RESEARCH_JOB_ID
    kind: ResearchJobKind = "gpu_training_smoke"
    candidate_artifact: Path | None = None
    breadth_queue_artifact: Path | None = None
    breadth_holdout_artifact: Path | None = None
    depth_target_artifact: Path | None = None
    training_metrics_artifact: Path | None = None
    evaluation_artifact: Path | None = None
    candidate_replay_artifact: Path | None = None
    probability_trace_artifact: Path | None = None
    comparison_artifact: Path | None = None
    calibration_artifact: Path | None = None
    model_artifact: Path | None = None
    yahoo_snapshot: Path | None = None
    symbol: str | None = None
    max_bars: int = 120
    max_epochs: int = 8
    max_steps: int = 256
    buy_threshold: float = 0.55
    sell_threshold: float = 0.45
    data_slices: tuple[CandidateDataSliceConfig, ...] = ()
    threshold_pairs: tuple[tuple[float, float], ...] = ()
    robustness_slices: tuple[CandidateThresholdRobustnessSliceConfig, ...] = ()
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
        | BoundedCandidateBreadthHoldoutResult
        | BoundedCandidateBreadthQueueResult
        | BoundedCandidateDepthComparisonResult
        | BoundedCandidateDepthTargetResult
        | BoundedCandidateTrainingResult
        | BoundedCandidateEvaluationResult
        | BoundedCandidateReplayResult
        | BoundedCandidateReplayComparisonResult
        | BoundedCandidateThresholdSweepResult
        | BoundedCandidateThresholdRobustnessResult
        | BoundedCandidateThresholdCalibrationResult
        | BoundedCandidateThresholdHoldoutResult
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
    | BoundedCandidateBreadthHoldoutResult
    | BoundedCandidateBreadthQueueResult
    | BoundedCandidateDepthComparisonResult
    | BoundedCandidateDepthTargetResult
    | BoundedCandidateTrainingResult
    | BoundedCandidateEvaluationResult
    | BoundedCandidateReplayResult
    | BoundedCandidateReplayComparisonResult
    | BoundedCandidateThresholdSweepResult
    | BoundedCandidateThresholdRobustnessResult
    | BoundedCandidateThresholdCalibrationResult
    | BoundedCandidateThresholdHoldoutResult,
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
    if spec.kind == "candidate_breadth_holdout":
        holdout = run_bounded_candidate_breadth_holdout(
            config=CandidateBreadthHoldoutConfig(
                run_id=spec.job_id,
                max_bars=spec.max_bars,
                source_slices=_robustness_slices_from_data_slices(spec.data_slices),
                holdout_slices=spec.robustness_slices,
            ),
            artifact_root=artifact_root,
            repo_root=repo_root,
            breadth_queue_artifact=spec.breadth_queue_artifact,
            gpu=gpu,
            probability_runner=candidate_probability_runner,
        )
        status = (
            "completed"
            if holdout.status == "candidate_breadth_holdout_replayed_only"
            else "prepared_not_breadth_holdout_replayed"
        )
        return holdout, holdout.holdout_artifact, None, status
    if spec.kind == "candidate_depth_comparison":
        comparison = run_bounded_candidate_depth_comparison(
            config=CandidateDepthComparisonConfig(run_id=spec.job_id),
            artifact_root=artifact_root,
            repo_root=repo_root,
            depth_target_artifact=spec.depth_target_artifact,
            breadth_holdout_artifact=spec.breadth_holdout_artifact,
        )
        status = (
            "completed"
            if comparison.status == "candidate_depth_compared_only"
            else "prepared_not_depth_compared"
        )
        return comparison, comparison.comparison_artifact, None, status
    if spec.kind == "candidate_depth_target":
        depth = run_bounded_candidate_depth_target(
            config=CandidateDepthTargetConfig(
                run_id=spec.job_id,
                max_bars=spec.max_bars,
                max_epochs=spec.max_epochs,
                max_steps=spec.max_steps,
                source_slices=spec.data_slices,
                holdout_slices=spec.robustness_slices,
            ),
            artifact_root=artifact_root,
            repo_root=repo_root,
            breadth_holdout_artifact=spec.breadth_holdout_artifact,
            gpu=gpu,
            trainer_runner=candidate_trainer_runner,
            evaluation_runner=candidate_evaluation_runner,
            probability_runner=candidate_probability_runner,
        )
        status = (
            "completed"
            if depth.status == "candidate_depth_target_ran_only"
            else "prepared_not_depth_targeted"
        )
        return depth, depth.target_artifact, depth.model_artifact, status
    if spec.kind == "candidate_breadth_queue":
        breadth = run_bounded_candidate_breadth_queue(
            config=CandidateBreadthQueueConfig(
                run_id=spec.job_id,
                max_epochs=spec.max_epochs,
                max_steps=spec.max_steps,
                max_bars=spec.max_bars,
            ),
            artifact_root=artifact_root,
            repo_root=repo_root,
            yahoo_snapshot=spec.yahoo_snapshot,
            symbol=spec.symbol,
            data_slices=spec.data_slices,
            gpu=gpu,
            trainer_runner=candidate_trainer_runner,
            evaluation_runner=candidate_evaluation_runner,
        )
        status = (
            "completed"
            if breadth.status == "candidate_breadth_queued_only"
            else "prepared_not_breadth_queued"
        )
        return breadth, breadth.queue_artifact, None, status
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
            data_slices=spec.data_slices,
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
            data_slices=spec.data_slices,
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
    if spec.kind == "candidate_threshold_sweep":
        sweep = run_bounded_candidate_threshold_sweep(
            config=CandidateThresholdSweepConfig(
                run_id=spec.job_id,
                max_bars=spec.max_bars,
                threshold_pairs=spec.threshold_pairs
                or CandidateThresholdSweepConfig().threshold_pairs,
            ),
            artifact_root=artifact_root,
            repo_root=repo_root,
            probability_trace_artifact=spec.probability_trace_artifact,
            comparison_artifact=spec.comparison_artifact,
            training_metrics_artifact=spec.training_metrics_artifact,
            evaluation_artifact=spec.evaluation_artifact,
            model_artifact=spec.model_artifact,
            yahoo_snapshot=spec.yahoo_snapshot,
            symbol=spec.symbol,
            gpu=gpu,
            probability_runner=candidate_probability_runner,
        )
        status = "completed" if sweep.status == "candidate_swept_only" else "prepared_not_swept"
        return sweep, sweep.sweep_artifact, sweep.model_artifact, status
    if spec.kind == "candidate_threshold_robustness":
        robustness = run_bounded_candidate_threshold_robustness(
            config=CandidateThresholdRobustnessConfig(
                run_id=spec.job_id,
                max_bars=spec.max_bars,
                threshold_pairs=spec.threshold_pairs
                or CandidateThresholdSweepConfig().threshold_pairs,
                slices=spec.robustness_slices,
            ),
            artifact_root=artifact_root,
            repo_root=repo_root,
            training_metrics_artifact=spec.training_metrics_artifact,
            evaluation_artifact=spec.evaluation_artifact,
            model_artifact=spec.model_artifact,
            gpu=gpu,
            probability_runner=candidate_probability_runner,
        )
        status = (
            "completed"
            if robustness.status == "candidate_robustness_replayed_only"
            else "prepared_not_robustness_replayed"
        )
        return robustness, robustness.robustness_artifact, robustness.model_artifact, status
    if spec.kind == "candidate_threshold_calibration":
        calibration = run_bounded_candidate_threshold_calibration(
            config=CandidateThresholdCalibrationConfig(
                run_id=spec.job_id,
                max_bars=spec.max_bars,
                slices=spec.robustness_slices,
            ),
            artifact_root=artifact_root,
            repo_root=repo_root,
            training_metrics_artifact=spec.training_metrics_artifact,
            evaluation_artifact=spec.evaluation_artifact,
            model_artifact=spec.model_artifact,
            gpu=gpu,
            probability_runner=candidate_probability_runner,
        )
        status = (
            "completed"
            if calibration.status == "candidate_thresholds_calibrated_only"
            else "prepared_not_calibrated"
        )
        return (
            calibration,
            calibration.calibration_artifact,
            calibration.model_artifact,
            status,
        )
    if spec.kind == "candidate_threshold_holdout":
        holdout = run_bounded_candidate_threshold_holdout(
            config=CandidateThresholdHoldoutConfig(
                run_id=spec.job_id,
                max_bars=spec.max_bars,
                slices=spec.robustness_slices,
            ),
            artifact_root=artifact_root,
            repo_root=repo_root,
            calibration_artifact=spec.calibration_artifact,
            training_metrics_artifact=spec.training_metrics_artifact,
            evaluation_artifact=spec.evaluation_artifact,
            model_artifact=spec.model_artifact,
            gpu=gpu,
            probability_runner=candidate_probability_runner,
        )
        status = (
            "completed"
            if holdout.status == "candidate_threshold_holdout_replayed_only"
            else "prepared_not_holdout_replayed"
        )
        return holdout, holdout.holdout_artifact, holdout.model_artifact, status
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
    parser.add_argument("--breadth-queue-artifact", type=Path)
    parser.add_argument("--breadth-holdout-artifact", type=Path)
    parser.add_argument("--depth-target-artifact", type=Path)
    parser.add_argument("--training-metrics-artifact", type=Path)
    parser.add_argument("--evaluation-artifact", type=Path)
    parser.add_argument("--candidate-replay-artifact", type=Path)
    parser.add_argument("--probability-trace-artifact", type=Path)
    parser.add_argument("--comparison-artifact", type=Path)
    parser.add_argument("--calibration-artifact", type=Path)
    parser.add_argument("--model-artifact", type=Path)
    parser.add_argument("--yahoo-snapshot", type=Path)
    parser.add_argument("--symbol")
    parser.add_argument("--max-bars", type=int, default=120)
    parser.add_argument("--max-epochs", type=int, default=8)
    parser.add_argument("--max-steps", type=int, default=256)
    parser.add_argument("--buy-threshold", type=float, default=0.55)
    parser.add_argument("--sell-threshold", type=float, default=0.45)
    parser.add_argument("--data-slice", action="append", default=[])
    parser.add_argument("--threshold-pair", action="append", default=[])
    parser.add_argument("--robustness-slice", action="append", default=[])
    parser.add_argument("--artifact-root", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    artifact_root = args.artifact_root or resolve_model_artifact_root()
    spec = ResearchJobSpec(
        job_id=args.job_id,
        kind=args.kind,
        candidate_artifact=args.candidate_artifact,
        breadth_queue_artifact=args.breadth_queue_artifact,
        breadth_holdout_artifact=args.breadth_holdout_artifact,
        depth_target_artifact=args.depth_target_artifact,
        training_metrics_artifact=args.training_metrics_artifact,
        evaluation_artifact=args.evaluation_artifact,
        candidate_replay_artifact=args.candidate_replay_artifact,
        probability_trace_artifact=args.probability_trace_artifact,
        comparison_artifact=args.comparison_artifact,
        calibration_artifact=args.calibration_artifact,
        model_artifact=args.model_artifact,
        yahoo_snapshot=args.yahoo_snapshot,
        symbol=args.symbol,
        max_bars=args.max_bars,
        max_epochs=args.max_epochs,
        max_steps=args.max_steps,
        buy_threshold=args.buy_threshold,
        sell_threshold=args.sell_threshold,
        data_slices=parse_candidate_data_slices(args.data_slice),
        threshold_pairs=parse_threshold_pairs(args.threshold_pair),
        robustness_slices=parse_robustness_slices(args.robustness_slice),
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
    elif isinstance(training, BoundedCandidateBreadthHoldoutResult):
        base["source_breadth_queue_artifact"] = (
            None
            if training.source_breadth_queue_artifact is None
            else str(training.source_breadth_queue_artifact)
        )
        base["candidate_breadth_holdout"] = {
            "status": training.status,
            "reason": training.reason,
            "gpu": training.gpu,
            "input_variant_count": training.input_variant_count,
            "processed_variant_count": training.processed_variant_count,
            "completed_variant_count": training.completed_variant_count,
            "source_slice_count": training.source_slice_count,
            "holdout_slice_count": training.holdout_slice_count,
            "max_bars": training.max_bars,
            "variants": tuple(
                _candidate_breadth_holdout_variant_payload(item)
                for item in training.variants
            ),
            "metrics": training.metrics,
            "selection": {
                "winner": None,
                "recommendation": None,
                "promotion_gate": False,
                "mode": "descriptive_breadth_holdout_only",
            },
        }
    elif isinstance(training, BoundedCandidateDepthComparisonResult):
        base["source_depth_target_artifact"] = (
            None
            if training.source_depth_target_artifact is None
            else str(training.source_depth_target_artifact)
        )
        base["source_breadth_holdout_artifact"] = (
            None
            if training.source_breadth_holdout_artifact is None
            else str(training.source_breadth_holdout_artifact)
        )
        base["candidate_depth_comparison"] = {
            "status": training.status,
            "reason": training.reason,
            "selected_variant_id": training.selected_variant_id,
            "selected_variant_count": training.selected_variant_count,
            "input_variant_count": training.input_variant_count,
            "artifact_verification": training.artifact_verification,
            "breadth_evidence": training.breadth_evidence,
            "depth_evidence": training.depth_evidence,
            "deltas": training.deltas,
            "metrics": training.metrics,
            "selection": {
                "mode": "research_comparison_only",
                "selected_variant_id": training.selected_variant_id,
                "selected_variant_count": training.selected_variant_count,
                "winner": None,
                "recommendation": None,
                "promotion_gate": False,
            },
        }
    elif isinstance(training, BoundedCandidateDepthTargetResult):
        base["source_breadth_holdout_artifact"] = (
            None
            if training.source_breadth_holdout_artifact is None
            else str(training.source_breadth_holdout_artifact)
        )
        base["candidate_depth_target"] = {
            "status": training.status,
            "reason": training.reason,
            "gpu": training.gpu,
            "input_variant_count": training.input_variant_count,
            "eligible_variant_count": training.eligible_variant_count,
            "selected_variant_count": training.selected_variant_count,
            "source_slice_count": training.source_slice_count,
            "holdout_slice_count": training.holdout_slice_count,
            "max_bars": training.max_bars,
            "max_epochs": training.max_epochs,
            "max_steps": training.max_steps,
            "selection": _candidate_depth_target_selection_payload(training),
            "variants_considered": training.variants_considered,
            "training_status": None
            if training.training is None
            else training.training.status,
            "evaluation_status": None
            if training.evaluation is None
            else training.evaluation.status,
            "calibration_status": None
            if training.calibration is None
            else training.calibration.status,
            "holdout_status": None
            if training.holdout is None
            else training.holdout.status,
            "metrics": training.metrics,
        }
    elif isinstance(training, BoundedCandidateBreadthQueueResult):
        base["candidate_breadth_queue"] = {
            "status": training.status,
            "reason": training.reason,
            "gpu": training.gpu,
            "variant_count": training.variant_count,
            "trained_variant_count": training.trained_variant_count,
            "completed_variant_count": training.completed_variant_count,
            "max_bars": training.max_bars,
            "max_epochs": training.max_epochs,
            "max_steps": training.max_steps,
            "variants": tuple(
                _candidate_breadth_queue_variant_payload(item)
                for item in training.variants
            ),
            "metrics": training.metrics,
            "selection": {
                "winner": None,
                "recommendation": None,
                "promotion_gate": False,
                "mode": "descriptive_breadth_only",
            },
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
            "source_slices": training.source_slices,
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
            "source_slices": training.source_slices,
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
    elif isinstance(training, BoundedCandidateThresholdSweepResult):
        base["candidate_threshold_sweep"] = {
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
            "probability_trace_artifact": (
                None
                if training.probability_trace_artifact is None
                else str(training.probability_trace_artifact)
            ),
            "comparison_artifact": (
                None if training.comparison_artifact is None else str(training.comparison_artifact)
            ),
            "data_source": training.data_source,
            "symbol": training.symbol,
            "market": training.market,
            "timeframe": training.timeframe,
            "bars_seen": training.bars_seen,
            "examples_seen": training.examples_seen,
            "trace_status": training.trace_status,
            "source_alignment": training.source_alignment,
            "baseline_metrics": training.baseline_metrics,
            "variant_count": len(training.variants),
            "completed_variant_count": sum(
                1 for variant in training.variants if variant.status == "candidate_replayed_only"
            ),
            "variants": training.variants,
            "thresholds": training.thresholds,
        }
    elif isinstance(training, BoundedCandidateThresholdRobustnessResult):
        base["candidate_threshold_robustness"] = {
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
            "slice_count": training.slice_count,
            "completed_slice_count": training.completed_slice_count,
            "slices": [
                _candidate_threshold_robustness_slice_payload(item)
                for item in training.slices
            ],
            "thresholds": training.thresholds,
            "metrics": training.metrics,
        }
    elif isinstance(training, BoundedCandidateThresholdCalibrationResult):
        base["candidate_threshold_calibration"] = {
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
            "slice_count": training.slice_count,
            "ready_trace_count": training.ready_trace_count,
            "probability_count": training.probability_count,
            "probability_summary": training.probability_summary,
            "thresholds": training.thresholds,
            "metrics": training.metrics,
        }
    elif isinstance(training, BoundedCandidateThresholdHoldoutResult):
        base["candidate_threshold_holdout"] = {
            "status": training.status,
            "reason": training.reason,
            "gpu": training.gpu,
            "source_calibration_artifact": (
                None
                if training.source_calibration_artifact is None
                else str(training.source_calibration_artifact)
            ),
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
            "slice_count": training.slice_count,
            "completed_slice_count": training.completed_slice_count,
            "holdout_slices": training.holdout_slices,
            "probability_summary": training.probability_summary,
            "thresholds": training.thresholds,
            "metrics": training.metrics,
            "local_paper_verification": training.local_paper_verification,
            "data_requests": training.data_requests,
        }
    return to_jsonable(base)


def _research_job_artifacts(result: ResearchJobResult) -> dict[str, str]:
    if isinstance(result.training, GpuTrainingSmokeResult):
        return {"training_smoke": str(result.training_artifact)}
    if isinstance(result.training, BoundedCandidateBreadthHoldoutResult):
        return {"candidate_breadth_holdout": str(result.training_artifact)}
    if isinstance(result.training, BoundedCandidateBreadthQueueResult):
        return {"candidate_breadth_queue": str(result.training_artifact)}
    if isinstance(result.training, BoundedCandidateDepthComparisonResult):
        return {"candidate_depth_comparison": str(result.training_artifact)}
    if isinstance(result.training, BoundedCandidateDepthTargetResult):
        artifacts = {"candidate_depth_target": str(result.training_artifact)}
        if result.training.candidate_artifact is not None:
            artifacts["depth_candidate"] = str(result.training.candidate_artifact)
        if result.training.training_metrics_artifact is not None:
            artifacts["candidate_training"] = str(result.training.training_metrics_artifact)
        if result.training.evaluation_artifact is not None:
            artifacts["candidate_evaluation"] = str(result.training.evaluation_artifact)
        if result.training.calibration_artifact is not None:
            artifacts["candidate_threshold_calibration"] = str(
                result.training.calibration_artifact
            )
        if result.training.holdout_artifact is not None:
            artifacts["candidate_threshold_holdout"] = str(result.training.holdout_artifact)
        if result.training.robustness_artifact is not None:
            artifacts["candidate_threshold_robustness"] = str(
                result.training.robustness_artifact
            )
        if result.model_artifact is not None:
            artifacts["model"] = str(result.model_artifact)
        return artifacts
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
    if isinstance(result.training, BoundedCandidateThresholdSweepResult):
        artifacts = {"candidate_threshold_sweep": str(result.training_artifact)}
        if result.training.probability_trace_artifact is not None:
            artifacts["candidate_probability_trace"] = str(
                result.training.probability_trace_artifact
            )
        if result.training.comparison_artifact is not None:
            artifacts["candidate_replay_comparison"] = str(result.training.comparison_artifact)
        if result.model_artifact is not None:
            artifacts["source_model"] = str(result.model_artifact)
        return artifacts
    if isinstance(result.training, BoundedCandidateThresholdRobustnessResult):
        artifacts = {
            "candidate_threshold_robustness": str(result.training_artifact),
        }
        if result.model_artifact is not None:
            artifacts["source_model"] = str(result.model_artifact)
        return artifacts
    if isinstance(result.training, BoundedCandidateThresholdCalibrationResult):
        artifacts = {
            "candidate_threshold_calibration": str(result.training_artifact),
        }
        if result.training.robustness_artifact is not None:
            artifacts["candidate_threshold_robustness"] = str(
                result.training.robustness_artifact
            )
        if result.model_artifact is not None:
            artifacts["source_model"] = str(result.model_artifact)
        return artifacts
    if isinstance(result.training, BoundedCandidateThresholdHoldoutResult):
        artifacts = {
            "candidate_threshold_holdout": str(result.training_artifact),
        }
        if result.training.robustness_artifact is not None:
            artifacts["candidate_threshold_robustness"] = str(
                result.training.robustness_artifact
            )
        if result.training.source_calibration_artifact is not None:
            artifacts["source_calibration"] = str(
                result.training.source_calibration_artifact
            )
        if result.model_artifact is not None:
            artifacts["source_model"] = str(result.model_artifact)
        return artifacts
    artifacts = {"candidate_metrics": str(result.training_artifact)}
    if result.model_artifact is not None:
        artifacts["model"] = str(result.model_artifact)
    return artifacts


def _candidate_breadth_holdout_variant_payload(
    item: CandidateBreadthHoldoutVariantResult,
) -> dict[str, object]:
    return {
        "variant_id": item.variant_id,
        "status": item.status,
        "reason": item.reason,
        "candidate_experiment_id": item.candidate_experiment_id,
        "candidate_parameters": item.candidate_parameters,
        "training_metrics_artifact": (
            None
            if item.training_metrics_artifact is None
            else str(item.training_metrics_artifact)
        ),
        "evaluation_artifact": (
            None if item.evaluation_artifact is None else str(item.evaluation_artifact)
        ),
        "model_artifact": None if item.model_artifact is None else str(item.model_artifact),
        "calibration_artifact": (
            None if item.calibration_artifact is None else str(item.calibration_artifact)
        ),
        "holdout_artifact": None if item.holdout_artifact is None else str(item.holdout_artifact),
        "robustness_artifact": (
            None if item.robustness_artifact is None else str(item.robustness_artifact)
        ),
        "metrics": item.metrics,
    }


def _candidate_depth_target_selection_payload(
    result: BoundedCandidateDepthTargetResult,
) -> dict[str, object]:
    selection = result.selection
    if selection is None:
        return {
            "mode": "research_scheduling_only",
            "selected_variant_id": None,
            "selected_variant_count": 0,
            "winner": None,
            "recommendation": None,
            "promotion_gate": False,
        }
    return {
        "mode": selection.mode,
        "selected_variant_id": selection.variant_id,
        "selected_variant_count": result.selected_variant_count,
        "candidate_experiment_id": selection.candidate_experiment_id,
        "candidate_parameters": selection.candidate_parameters,
        "selection_rank": selection.selection_rank,
        "heuristic": selection.heuristic,
        "winner": None,
        "recommendation": None,
        "promotion_gate": False,
    }


def _candidate_breadth_queue_variant_payload(
    item: CandidateBreadthVariantResult,
) -> dict[str, object]:
    return {
        "variant_id": item.variant_id,
        "status": item.status,
        "reason": item.reason,
        "candidate_artifact": str(item.candidate_artifact),
        "candidate_experiment_id": item.candidate_experiment_id,
        "candidate_parameters": item.candidate_parameters,
        "training": {
            "status": item.training.status,
            "reason": item.training.reason,
            "metrics_artifact": str(item.training.metrics_artifact),
            "model_artifact": (
                None
                if item.training.model_artifact is None
                else str(item.training.model_artifact)
            ),
            "selected_backend": item.training.selected_backend,
            "examples_seen": item.training.examples_seen,
            "max_epochs": item.training.max_epochs,
            "max_steps": item.training.max_steps,
        },
        "evaluation": {
            "status": item.evaluation.status,
            "reason": item.evaluation.reason,
            "evaluation_artifact": str(item.evaluation.evaluation_artifact),
            "selected_backend": item.evaluation.selected_backend,
            "examples_seen": item.evaluation.examples_seen,
            "local_paper_conversion": item.evaluation.local_paper_conversion,
        },
        "metrics": item.metrics,
    }


def _robustness_slices_from_data_slices(
    data_slices: tuple[CandidateDataSliceConfig, ...],
) -> tuple[CandidateThresholdRobustnessSliceConfig, ...]:
    return tuple(
        CandidateThresholdRobustnessSliceConfig(
            slice_id=data_slice.slice_id,
            yahoo_snapshot=data_slice.yahoo_snapshot,
            symbol=data_slice.symbol,
        )
        for data_slice in data_slices
    )


if __name__ == "__main__":
    main()
