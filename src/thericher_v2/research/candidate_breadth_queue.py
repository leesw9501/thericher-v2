"""Bounded breadth queue for descriptive candidate training and evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.serialization import to_jsonable

from .candidate_evaluation import (
    BoundedCandidateEvaluationResult,
    CandidateEvaluationConfig,
    CandidateEvaluationRunner,
    run_bounded_candidate_evaluation,
)
from .candidate_training import (
    BoundedCandidateTrainingResult,
    CandidateDataSliceConfig,
    CandidateTrainerRunner,
    CandidateTrainingConfig,
    GpuReadiness,
    _reject_repo_artifact_path,
    detect_gpu_readiness,
    run_bounded_candidate_training,
)

CandidateBreadthQueueStatus = Literal[
    "candidate_breadth_queued_only",
    "prepared_not_breadth_queued",
]
CandidateBreadthVariantStatus = Literal[
    "variant_evaluated_only",
    "prepared_not_evaluated",
]
DEFAULT_CANDIDATE_BREADTH_QUEUE_RUN_ID = "bounded-candidate-breadth-queue"
MAX_CANDIDATE_BREADTH_VARIANTS = 3


@dataclass(frozen=True)
class CandidateBreadthVariantConfig:
    variant_id: str
    candidate_experiment_id: str
    candidate_parameters: dict[str, Any]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.variant_id:
            raise ValueError("variant_id is required")
        if any(part in self.variant_id for part in ("\\", "/", ":")):
            raise ValueError("variant_id must not contain path separators")
        if not self.candidate_experiment_id:
            raise ValueError("candidate_experiment_id is required")


@dataclass(frozen=True)
class CandidateBreadthQueueConfig:
    run_id: str = DEFAULT_CANDIDATE_BREADTH_QUEUE_RUN_ID
    max_bars: int = 180
    max_epochs: int = 4
    max_steps: int = 128
    variants: tuple[CandidateBreadthVariantConfig, ...] | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("run_id is required")
        variants = (
            default_candidate_breadth_variants()
            if self.variants is None
            else self.variants
        )
        if len(variants) > MAX_CANDIDATE_BREADTH_VARIANTS:
            raise ValueError(
                f"variants must be <= {MAX_CANDIDATE_BREADTH_VARIANTS}"
            )
        variant_ids = [variant.variant_id for variant in variants]
        if len(set(variant_ids)) != len(variant_ids):
            raise ValueError("variant ids must be unique")
        object.__setattr__(self, "variants", variants)
        CandidateTrainingConfig(
            run_id=f"{self.run_id}-cap-validation",
            max_bars=self.max_bars,
            max_epochs=self.max_epochs,
            max_steps=self.max_steps,
        )
        CandidateEvaluationConfig(
            run_id=f"{self.run_id}-cap-validation",
            max_bars=self.max_bars,
        )


@dataclass(frozen=True)
class CandidateBreadthVariantResult:
    variant_id: str
    status: CandidateBreadthVariantStatus
    reason: str
    candidate_artifact: Path
    candidate_experiment_id: str
    candidate_parameters: dict[str, Any]
    training: BoundedCandidateTrainingResult
    evaluation: BoundedCandidateEvaluationResult
    metrics: dict[str, Any]
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class BoundedCandidateBreadthQueueResult:
    run_id: str
    status: CandidateBreadthQueueStatus
    checked_at: datetime
    gpu: GpuReadiness
    reason: str
    candidate_artifact: Path | None
    candidate_experiment_id: str | None
    candidate_parameters: dict[str, Any]
    queue_artifact: Path
    variant_count: int
    trained_variant_count: int
    completed_variant_count: int
    max_bars: int
    max_epochs: int
    max_steps: int
    variants: tuple[CandidateBreadthVariantResult, ...]
    metrics: dict[str, Any]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_at", self.checked_at.astimezone(UTC))


def default_candidate_breadth_variants() -> tuple[CandidateBreadthVariantConfig, ...]:
    return (
        _variant("m1_lb3_b10_s10", lookback=3),
        _variant("m1_lb5_b10_s10", lookback=5),
        _variant("m1_lb8_b10_s10", lookback=8),
    )


def run_bounded_candidate_breadth_queue(
    *,
    config: CandidateBreadthQueueConfig | None = None,
    artifact_root: Path,
    repo_root: Path | None = None,
    yahoo_snapshot: Path | None = None,
    symbol: str | None = None,
    data_slices: tuple[CandidateDataSliceConfig, ...] = (),
    gpu: GpuReadiness | None = None,
    trainer_runner: CandidateTrainerRunner | None = None,
    evaluation_runner: CandidateEvaluationRunner | None = None,
) -> BoundedCandidateBreadthQueueResult:
    config = config or CandidateBreadthQueueConfig()
    _reject_repo_artifact_path(artifact_root, repo_root)
    output_dir = artifact_root / "candidate-breadth-queue" / config.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    queue_artifact = output_dir / "metrics.json"
    gpu = gpu or detect_gpu_readiness()

    variants = tuple(
        _run_variant(
            config=config,
            variant=variant,
            artifact_root=artifact_root,
            repo_root=repo_root,
            output_dir=output_dir,
            yahoo_snapshot=yahoo_snapshot,
            symbol=symbol,
            data_slices=data_slices,
            gpu=gpu,
            trainer_runner=trainer_runner,
            evaluation_runner=evaluation_runner,
        )
        for variant in config.variants
    )
    trained_variant_count = sum(
        1 for item in variants if item.training.status == "candidate_trained_only"
    )
    completed_variant_count = sum(
        1 for item in variants if item.status == "variant_evaluated_only"
    )
    status: CandidateBreadthQueueStatus = (
        "candidate_breadth_queued_only"
        if completed_variant_count > 0
        else "prepared_not_breadth_queued"
    )
    reason = (
        "bounded candidate breadth queue completed without promotion decision"
        if completed_variant_count > 0
        else "no candidate variants evaluated"
    )
    first_variant = variants[0] if variants else None
    result = BoundedCandidateBreadthQueueResult(
        run_id=config.run_id,
        status=status,
        checked_at=datetime.now(UTC),
        gpu=gpu,
        reason=reason,
        candidate_artifact=None if first_variant is None else first_variant.candidate_artifact,
        candidate_experiment_id=None
        if first_variant is None
        else first_variant.candidate_experiment_id,
        candidate_parameters={}
        if first_variant is None
        else first_variant.candidate_parameters,
        queue_artifact=queue_artifact,
        variant_count=len(variants),
        trained_variant_count=trained_variant_count,
        completed_variant_count=completed_variant_count,
        max_bars=config.max_bars,
        max_epochs=config.max_epochs,
        max_steps=config.max_steps,
        variants=variants,
        metrics=_queue_metrics(variants),
    )
    queue_artifact.write_text(
        json.dumps(
            _candidate_breadth_queue_payload(result, artifact_root),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return result


def _run_variant(
    *,
    config: CandidateBreadthQueueConfig,
    variant: CandidateBreadthVariantConfig,
    artifact_root: Path,
    repo_root: Path | None,
    output_dir: Path,
    yahoo_snapshot: Path | None,
    symbol: str | None,
    data_slices: tuple[CandidateDataSliceConfig, ...],
    gpu: GpuReadiness,
    trainer_runner: CandidateTrainerRunner | None,
    evaluation_runner: CandidateEvaluationRunner | None,
) -> CandidateBreadthVariantResult:
    candidate_artifact = _write_candidate_artifact(output_dir, variant)
    training = run_bounded_candidate_training(
        config=CandidateTrainingConfig(
            run_id=f"{config.run_id}-{variant.variant_id}-training",
            max_bars=config.max_bars,
            max_epochs=config.max_epochs,
            max_steps=config.max_steps,
        ),
        artifact_root=artifact_root,
        repo_root=repo_root,
        candidate_artifact=candidate_artifact,
        yahoo_snapshot=yahoo_snapshot,
        symbol=symbol,
        data_slices=data_slices,
        gpu=gpu,
        trainer_runner=trainer_runner,
    )
    evaluation = run_bounded_candidate_evaluation(
        config=CandidateEvaluationConfig(
            run_id=f"{config.run_id}-{variant.variant_id}-evaluation",
            max_bars=config.max_bars,
        ),
        artifact_root=artifact_root,
        repo_root=repo_root,
        training_metrics_artifact=training.metrics_artifact,
        model_artifact=training.model_artifact,
        yahoo_snapshot=yahoo_snapshot,
        symbol=symbol,
        data_slices=data_slices,
        gpu=gpu,
        evaluation_runner=evaluation_runner,
    )
    status: CandidateBreadthVariantStatus = (
        "variant_evaluated_only"
        if evaluation.status == "candidate_evaluated_only"
        else "prepared_not_evaluated"
    )
    reason = (
        "candidate variant trained and evaluated without promotion decision"
        if status == "variant_evaluated_only"
        else f"{training.reason}; {evaluation.reason}"
    )
    return CandidateBreadthVariantResult(
        variant_id=variant.variant_id,
        status=status,
        reason=reason,
        candidate_artifact=candidate_artifact,
        candidate_experiment_id=variant.candidate_experiment_id,
        candidate_parameters=dict(variant.candidate_parameters),
        training=training,
        evaluation=evaluation,
        metrics=_variant_metrics(training, evaluation),
    )


def _write_candidate_artifact(
    output_dir: Path,
    variant: CandidateBreadthVariantConfig,
) -> Path:
    candidate_dir = output_dir / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    path = candidate_dir / f"{variant.variant_id}.json"
    path.write_text(
        json.dumps(
            to_jsonable(
                {
                    "schema_version": variant.schema_version,
                    "candidate_experiment_id": variant.candidate_experiment_id,
                    "candidate_parameters": variant.candidate_parameters,
                    "promotion_gate": False,
                    "selection": "breadth_queue_variant",
                }
            ),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def _candidate_breadth_queue_payload(
    result: BoundedCandidateBreadthQueueResult,
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
            "candidate_parameters": result.candidate_parameters,
            "variant_count": result.variant_count,
            "trained_variant_count": result.trained_variant_count,
            "completed_variant_count": result.completed_variant_count,
            "max_bars": result.max_bars,
            "max_epochs": result.max_epochs,
            "max_steps": result.max_steps,
            "variants": tuple(_variant_payload(item) for item in result.variants),
            "metrics": result.metrics,
            "selection": {
                "winner": None,
                "recommendation": None,
                "promotion_gate": False,
                "mode": "descriptive_breadth_only",
            },
            "artifacts": {
                "queue": str(result.queue_artifact),
                "candidates": tuple(str(item.candidate_artifact) for item in result.variants),
                "training_metrics": tuple(
                    str(item.training.metrics_artifact) for item in result.variants
                ),
                "models": tuple(
                    None
                    if item.training.model_artifact is None
                    else str(item.training.model_artifact)
                    for item in result.variants
                ),
                "evaluations": tuple(
                    str(item.evaluation.evaluation_artifact) for item in result.variants
                ),
            },
            "artifact_policy": {
                "root": str(artifact_root),
                "repo_storage_allowed": False,
            },
        }
    )


def _variant_payload(item: CandidateBreadthVariantResult) -> dict[str, Any]:
    return {
        "schema_version": item.schema_version,
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
            "bars_seen": item.training.bars_seen,
            "examples_seen": item.training.examples_seen,
            "max_epochs": item.training.max_epochs,
            "max_steps": item.training.max_steps,
        },
        "evaluation": {
            "status": item.evaluation.status,
            "reason": item.evaluation.reason,
            "evaluation_artifact": str(item.evaluation.evaluation_artifact),
            "selected_backend": item.evaluation.selected_backend,
            "bars_seen": item.evaluation.bars_seen,
            "examples_seen": item.evaluation.examples_seen,
            "local_paper_conversion": item.evaluation.local_paper_conversion,
        },
        "metrics": item.metrics,
    }


def _variant_metrics(
    training: BoundedCandidateTrainingResult,
    evaluation: BoundedCandidateEvaluationResult,
) -> dict[str, Any]:
    training_metrics = _select_metrics(
        training.metrics,
        keys=(
            "backend",
            "operation",
            "epochs_run",
            "steps_run",
            "examples_seen",
            "initial_loss",
            "final_loss",
            "accuracy",
        ),
    )
    evaluation_metrics = _select_metrics(
        evaluation.metrics,
        keys=(
            "backend",
            "operation",
            "examples_seen",
            "loss",
            "accuracy",
            "mean_probability",
            "predicted_positive_rate",
            "baseline_majority_accuracy",
            "baseline_always_up_accuracy",
            "label_positive_rate",
            "probability_threshold",
        ),
    )
    return {
        "training": training_metrics,
        "evaluation": evaluation_metrics,
    }


def _queue_metrics(variants: tuple[CandidateBreadthVariantResult, ...]) -> dict[str, Any]:
    return {
        "descriptive_only": True,
        "promotion_gate": False,
        "variant_ids": tuple(item.variant_id for item in variants),
        "training_statuses": tuple(item.training.status for item in variants),
        "evaluation_statuses": tuple(item.evaluation.status for item in variants),
    }


def _select_metrics(
    metrics: dict[str, Any],
    *,
    keys: tuple[str, ...],
) -> dict[str, Any]:
    return {key: metrics[key] for key in keys if key in metrics}


def _variant(variant_id: str, *, lookback: int) -> CandidateBreadthVariantConfig:
    return CandidateBreadthVariantConfig(
        variant_id=variant_id,
        candidate_experiment_id=variant_id,
        candidate_parameters={
            "model_id": "momentum_close_v1",
            "timeframe": "1m",
            "lookback": lookback,
            "buy_threshold_bps": 10,
            "sell_threshold_bps": -10,
        },
    )
