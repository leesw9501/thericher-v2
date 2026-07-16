"""Bounded depth target for one breadth-holdout candidate."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.serialization import to_jsonable

from .candidate_evaluation import (
    BoundedCandidateEvaluationResult,
    CandidateEvaluationConfig,
    CandidateEvaluationRunner,
    run_bounded_candidate_evaluation,
)
from .candidate_replay import CandidateProbabilityRunner
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
from .candidate_threshold_robustness import CandidateThresholdRobustnessSliceConfig
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

CandidateDepthTargetStatus = Literal[
    "candidate_depth_target_ran_only",
    "prepared_not_depth_targeted",
]
DEFAULT_CANDIDATE_DEPTH_TARGET_RUN_ID = "bounded-candidate-depth-target"
APP_MODEL_ARTIFACT_ROOT = PurePosixPath("/app/model_artifacts")


@dataclass(frozen=True)
class CandidateDepthTargetConfig:
    run_id: str = DEFAULT_CANDIDATE_DEPTH_TARGET_RUN_ID
    max_bars: int = 240
    max_epochs: int = 8
    max_steps: int = 256
    min_examples: int = 8
    source_slices: tuple[CandidateDataSliceConfig, ...] = ()
    holdout_slices: tuple[CandidateThresholdRobustnessSliceConfig, ...] = ()
    sample_seed: int = 37
    starting_cash: Decimal = Decimal("10000")
    quantity: Decimal = Decimal("1")
    fee_bps: Decimal = Decimal("1")
    slippage_bps: Decimal = Decimal("0")
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("run_id is required")
        CandidateTrainingConfig(
            run_id=f"{self.run_id}-cap-validation",
            max_bars=self.max_bars,
            max_epochs=self.max_epochs,
            max_steps=self.max_steps,
            min_examples=self.min_examples,
        )
        CandidateEvaluationConfig(
            run_id=f"{self.run_id}-cap-validation",
            max_bars=self.max_bars,
            min_examples=self.min_examples,
        )
        if self.starting_cash <= 0:
            raise ValueError("starting_cash must be positive")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.fee_bps < 0:
            raise ValueError("fee_bps must be non-negative")
        if self.slippage_bps < 0:
            raise ValueError("slippage_bps must be non-negative")


@dataclass(frozen=True)
class CandidateDepthTargetSelection:
    variant_id: str
    candidate_experiment_id: str | None
    candidate_parameters: dict[str, Any]
    selection_rank: int
    mode: str
    heuristic: dict[str, Any]
    source_training_metrics_artifact: Path | None
    source_evaluation_artifact: Path | None
    source_model_artifact: Path | None
    source_calibration_artifact: Path | None
    source_holdout_artifact: Path | None
    source_robustness_artifact: Path | None
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class BoundedCandidateDepthTargetResult:
    run_id: str
    status: CandidateDepthTargetStatus
    checked_at: datetime
    gpu: GpuReadiness
    reason: str
    source_breadth_holdout_artifact: Path | None
    candidate_experiment_id: str | None
    candidate_parameters: dict[str, Any]
    target_artifact: Path
    candidate_artifact: Path | None
    training_metrics_artifact: Path | None
    evaluation_artifact: Path | None
    calibration_artifact: Path | None
    holdout_artifact: Path | None
    robustness_artifact: Path | None
    model_artifact: Path | None
    input_variant_count: int
    eligible_variant_count: int
    selected_variant_count: int
    source_slice_count: int
    holdout_slice_count: int
    max_bars: int
    max_epochs: int
    max_steps: int
    selection: CandidateDepthTargetSelection | None
    variants_considered: tuple[dict[str, Any], ...]
    training: BoundedCandidateTrainingResult | None
    evaluation: BoundedCandidateEvaluationResult | None
    calibration: BoundedCandidateThresholdCalibrationResult | None
    holdout: BoundedCandidateThresholdHoldoutResult | None
    metrics: dict[str, Any]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_at", self.checked_at.astimezone(UTC))


def run_bounded_candidate_depth_target(
    *,
    config: CandidateDepthTargetConfig,
    artifact_root: Path,
    repo_root: Path | None = None,
    breadth_holdout_artifact: Path | None = None,
    gpu: GpuReadiness | None = None,
    trainer_runner: CandidateTrainerRunner | None = None,
    evaluation_runner: CandidateEvaluationRunner | None = None,
    probability_runner: CandidateProbabilityRunner | None = None,
) -> BoundedCandidateDepthTargetResult:
    _reject_repo_artifact_path(artifact_root, repo_root)
    if breadth_holdout_artifact is not None:
        _reject_repo_artifact_path(breadth_holdout_artifact, repo_root)
    output_dir = artifact_root / "candidate-depth-target" / config.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    target_artifact = output_dir / "metrics.json"
    gpu = gpu or detect_gpu_readiness()

    holdout_payload, holdout_error = _read_breadth_holdout_artifact(
        breadth_holdout_artifact
    )
    raw_variants = _holdout_variants(holdout_payload) if holdout_error is None else ()
    considered = tuple(
        _variant_considered_payload(raw_variant, artifact_root)
        for raw_variant in raw_variants
    )
    selected_raw, eligible_variant_count = _select_depth_target_variant(raw_variants)

    if holdout_error is not None:
        return _write_prepared_result(
            config=config,
            artifact_root=artifact_root,
            target_artifact=target_artifact,
            breadth_holdout_artifact=breadth_holdout_artifact,
            gpu=gpu,
            reason=holdout_error,
            input_variant_count=len(raw_variants),
            eligible_variant_count=eligible_variant_count,
            variants_considered=considered,
        )
    if selected_raw is None:
        return _write_prepared_result(
            config=config,
            artifact_root=artifact_root,
            target_artifact=target_artifact,
            breadth_holdout_artifact=breadth_holdout_artifact,
            gpu=gpu,
            reason="no completed breadth holdout variant available for depth target",
            input_variant_count=len(raw_variants),
            eligible_variant_count=eligible_variant_count,
            variants_considered=considered,
        )

    selection = _selection_from_variant(
        selected_raw,
        artifact_root=artifact_root,
        selection_rank=1,
    )
    source_error = _source_artifact_error(selection)
    if source_error is not None:
        return _write_prepared_result(
            config=config,
            artifact_root=artifact_root,
            target_artifact=target_artifact,
            breadth_holdout_artifact=breadth_holdout_artifact,
            gpu=gpu,
            reason=source_error,
            input_variant_count=len(raw_variants),
            eligible_variant_count=eligible_variant_count,
            selection=selection,
            variants_considered=considered,
        )

    candidate_artifact = _write_depth_candidate_artifact(
        output_dir=output_dir,
        selection=selection,
        breadth_holdout_artifact=breadth_holdout_artifact,
    )
    safe_variant_id = _safe_run_id_part(selection.variant_id)
    training = run_bounded_candidate_training(
        config=CandidateTrainingConfig(
            run_id=f"{config.run_id}-{safe_variant_id}-train",
            max_epochs=config.max_epochs,
            max_steps=config.max_steps,
            max_bars=config.max_bars,
            min_examples=config.min_examples,
        ),
        artifact_root=artifact_root,
        repo_root=repo_root,
        candidate_artifact=candidate_artifact,
        data_slices=config.source_slices,
        gpu=gpu,
        trainer_runner=trainer_runner,
    )
    evaluation = run_bounded_candidate_evaluation(
        config=CandidateEvaluationConfig(
            run_id=f"{config.run_id}-{safe_variant_id}-eval",
            max_bars=config.max_bars,
            min_examples=config.min_examples,
        ),
        artifact_root=artifact_root,
        repo_root=repo_root,
        training_metrics_artifact=training.metrics_artifact,
        model_artifact=training.model_artifact,
        data_slices=config.source_slices,
        gpu=gpu,
        evaluation_runner=evaluation_runner,
    )
    calibration = run_bounded_candidate_threshold_calibration(
        config=CandidateThresholdCalibrationConfig(
            run_id=f"{config.run_id}-{safe_variant_id}-cal",
            max_bars=config.max_bars,
            min_examples=config.min_examples,
            slices=_calibration_slices(config.source_slices),
            sample_seed=config.sample_seed,
            starting_cash=config.starting_cash,
            quantity=config.quantity,
            fee_bps=config.fee_bps,
            slippage_bps=config.slippage_bps,
        ),
        artifact_root=artifact_root,
        repo_root=repo_root,
        training_metrics_artifact=training.metrics_artifact,
        evaluation_artifact=evaluation.evaluation_artifact,
        model_artifact=training.model_artifact,
        gpu=gpu,
        probability_runner=probability_runner,
    )
    holdout = run_bounded_candidate_threshold_holdout(
        config=CandidateThresholdHoldoutConfig(
            run_id=f"{config.run_id}-{safe_variant_id}-hold",
            max_bars=config.max_bars,
            min_examples=config.min_examples,
            slices=config.holdout_slices,
            sample_seed=config.sample_seed,
            starting_cash=config.starting_cash,
            quantity=config.quantity,
            fee_bps=config.fee_bps,
            slippage_bps=config.slippage_bps,
        ),
        artifact_root=artifact_root,
        repo_root=repo_root,
        calibration_artifact=calibration.calibration_artifact,
        training_metrics_artifact=training.metrics_artifact,
        evaluation_artifact=evaluation.evaluation_artifact,
        model_artifact=training.model_artifact,
        gpu=gpu,
        probability_runner=probability_runner,
    )
    status: CandidateDepthTargetStatus = (
        "candidate_depth_target_ran_only"
        if holdout.status == "candidate_threshold_holdout_replayed_only"
        else "prepared_not_depth_targeted"
    )
    result = BoundedCandidateDepthTargetResult(
        run_id=config.run_id,
        status=status,
        checked_at=datetime.now(UTC),
        gpu=gpu,
        reason=(
            "bounded candidate depth target ran without promotion decision"
            if status == "candidate_depth_target_ran_only"
            else f"{training.reason}; {evaluation.reason}; "
            f"{calibration.reason}; {holdout.reason}"
        ),
        source_breadth_holdout_artifact=breadth_holdout_artifact,
        candidate_experiment_id=selection.candidate_experiment_id,
        candidate_parameters=selection.candidate_parameters,
        target_artifact=target_artifact,
        candidate_artifact=candidate_artifact,
        training_metrics_artifact=training.metrics_artifact,
        evaluation_artifact=evaluation.evaluation_artifact,
        calibration_artifact=calibration.calibration_artifact,
        holdout_artifact=holdout.holdout_artifact,
        robustness_artifact=holdout.robustness_artifact,
        model_artifact=training.model_artifact,
        input_variant_count=len(raw_variants),
        eligible_variant_count=eligible_variant_count,
        selected_variant_count=1,
        source_slice_count=len(config.source_slices),
        holdout_slice_count=len(config.holdout_slices),
        max_bars=config.max_bars,
        max_epochs=config.max_epochs,
        max_steps=config.max_steps,
        selection=selection,
        variants_considered=considered,
        training=training,
        evaluation=evaluation,
        calibration=calibration,
        holdout=holdout,
        metrics=_depth_metrics(
            training=training,
            evaluation=evaluation,
            calibration=calibration,
            holdout=holdout,
            selection=selection,
        ),
    )
    _write_result(result, artifact_root)
    return result


def _write_prepared_result(
    *,
    config: CandidateDepthTargetConfig,
    artifact_root: Path,
    target_artifact: Path,
    breadth_holdout_artifact: Path | None,
    gpu: GpuReadiness,
    reason: str,
    input_variant_count: int,
    eligible_variant_count: int,
    variants_considered: tuple[dict[str, Any], ...],
    selection: CandidateDepthTargetSelection | None = None,
) -> BoundedCandidateDepthTargetResult:
    result = BoundedCandidateDepthTargetResult(
        run_id=config.run_id,
        status="prepared_not_depth_targeted",
        checked_at=datetime.now(UTC),
        gpu=gpu,
        reason=reason,
        source_breadth_holdout_artifact=breadth_holdout_artifact,
        candidate_experiment_id=None if selection is None else selection.candidate_experiment_id,
        candidate_parameters={} if selection is None else selection.candidate_parameters,
        target_artifact=target_artifact,
        candidate_artifact=None,
        training_metrics_artifact=None,
        evaluation_artifact=None,
        calibration_artifact=None,
        holdout_artifact=None,
        robustness_artifact=None,
        model_artifact=None,
        input_variant_count=input_variant_count,
        eligible_variant_count=eligible_variant_count,
        selected_variant_count=0 if selection is None else 1,
        source_slice_count=len(config.source_slices),
        holdout_slice_count=len(config.holdout_slices),
        max_bars=config.max_bars,
        max_epochs=config.max_epochs,
        max_steps=config.max_steps,
        selection=selection,
        variants_considered=variants_considered,
        training=None,
        evaluation=None,
        calibration=None,
        holdout=None,
        metrics={
            "promotion_gate": False,
            "comparison_is_descriptive": True,
            "research_scheduling_only": True,
            "prepared_reason": reason,
        },
    )
    _write_result(result, artifact_root)
    return result


def _write_result(
    result: BoundedCandidateDepthTargetResult,
    artifact_root: Path,
) -> None:
    result.target_artifact.write_text(
        json.dumps(
            _candidate_depth_target_payload(result, artifact_root),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _candidate_depth_target_payload(
    result: BoundedCandidateDepthTargetResult,
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
            "source_breadth_holdout_artifact": None
            if result.source_breadth_holdout_artifact is None
            else str(result.source_breadth_holdout_artifact),
            "candidate_experiment_id": result.candidate_experiment_id,
            "candidate_parameters": result.candidate_parameters,
            "input_variant_count": result.input_variant_count,
            "eligible_variant_count": result.eligible_variant_count,
            "selected_variant_count": result.selected_variant_count,
            "source_slice_count": result.source_slice_count,
            "holdout_slice_count": result.holdout_slice_count,
            "max_bars": result.max_bars,
            "max_epochs": result.max_epochs,
            "max_steps": result.max_steps,
            "selection": _selection_payload(result.selection),
            "variants_considered": result.variants_considered,
            "training": _training_payload(result.training),
            "evaluation": _evaluation_payload(result.evaluation),
            "calibration": _calibration_payload(result.calibration),
            "holdout": _holdout_payload(result.holdout),
            "metrics": result.metrics,
            "artifacts": {
                "candidate_depth_target": str(result.target_artifact),
                "depth_candidate": None
                if result.candidate_artifact is None
                else str(result.candidate_artifact),
                "training_metrics": None
                if result.training_metrics_artifact is None
                else str(result.training_metrics_artifact),
                "evaluation": None
                if result.evaluation_artifact is None
                else str(result.evaluation_artifact),
                "calibration": None
                if result.calibration_artifact is None
                else str(result.calibration_artifact),
                "holdout": None
                if result.holdout_artifact is None
                else str(result.holdout_artifact),
                "robustness": None
                if result.robustness_artifact is None
                else str(result.robustness_artifact),
                "model": None if result.model_artifact is None else str(result.model_artifact),
            },
            "artifact_policy": {
                "root": str(artifact_root),
                "repo_storage_allowed": False,
            },
        }
    )


def _selection_payload(selection: CandidateDepthTargetSelection | None) -> dict[str, Any]:
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
        "selected_variant_count": 1,
        "candidate_experiment_id": selection.candidate_experiment_id,
        "candidate_parameters": selection.candidate_parameters,
        "selection_rank": selection.selection_rank,
        "heuristic": selection.heuristic,
        "source_training_metrics_artifact": None
        if selection.source_training_metrics_artifact is None
        else str(selection.source_training_metrics_artifact),
        "source_evaluation_artifact": None
        if selection.source_evaluation_artifact is None
        else str(selection.source_evaluation_artifact),
        "source_model_artifact": None
        if selection.source_model_artifact is None
        else str(selection.source_model_artifact),
        "source_calibration_artifact": None
        if selection.source_calibration_artifact is None
        else str(selection.source_calibration_artifact),
        "source_holdout_artifact": None
        if selection.source_holdout_artifact is None
        else str(selection.source_holdout_artifact),
        "source_robustness_artifact": None
        if selection.source_robustness_artifact is None
        else str(selection.source_robustness_artifact),
        "winner": None,
        "recommendation": None,
        "promotion_gate": False,
    }


def _training_payload(result: BoundedCandidateTrainingResult | None) -> dict[str, Any]:
    if result is None:
        return {}
    return {
        "status": result.status,
        "reason": result.reason,
        "selected_backend": result.selected_backend,
        "available_backends": result.available_backends,
        "metrics_artifact": str(result.metrics_artifact),
        "model_artifact": None if result.model_artifact is None else str(result.model_artifact),
        "bars_seen": result.bars_seen,
        "examples_seen": result.examples_seen,
        "max_epochs": result.max_epochs,
        "max_steps": result.max_steps,
        "metrics": result.metrics,
    }


def _evaluation_payload(result: BoundedCandidateEvaluationResult | None) -> dict[str, Any]:
    if result is None:
        return {}
    return {
        "status": result.status,
        "reason": result.reason,
        "selected_backend": result.selected_backend,
        "available_backends": result.available_backends,
        "evaluation_artifact": str(result.evaluation_artifact),
        "model_artifact": None if result.model_artifact is None else str(result.model_artifact),
        "bars_seen": result.bars_seen,
        "examples_seen": result.examples_seen,
        "metrics": result.metrics,
    }


def _calibration_payload(
    result: BoundedCandidateThresholdCalibrationResult | None,
) -> dict[str, Any]:
    if result is None:
        return {}
    return {
        "status": result.status,
        "reason": result.reason,
        "calibration_artifact": str(result.calibration_artifact),
        "robustness_artifact": None
        if result.robustness_artifact is None
        else str(result.robustness_artifact),
        "slice_count": result.slice_count,
        "ready_trace_count": result.ready_trace_count,
        "probability_summary": result.probability_summary,
        "thresholds": result.thresholds,
        "metrics": result.metrics,
    }


def _holdout_payload(result: BoundedCandidateThresholdHoldoutResult | None) -> dict[str, Any]:
    if result is None:
        return {}
    return {
        "status": result.status,
        "reason": result.reason,
        "holdout_artifact": str(result.holdout_artifact),
        "robustness_artifact": None
        if result.robustness_artifact is None
        else str(result.robustness_artifact),
        "slice_count": result.slice_count,
        "completed_slice_count": result.completed_slice_count,
        "probability_summary": result.probability_summary,
        "local_paper_verification": result.local_paper_verification,
        "data_requests": result.data_requests,
        "thresholds": result.thresholds,
        "metrics": result.metrics,
    }


def _read_breadth_holdout_artifact(
    path: Path | None,
) -> tuple[dict[str, Any], str | None]:
    if path is None:
        return {}, "candidate breadth holdout artifact is required"
    if not path.exists():
        return {}, f"candidate breadth holdout artifact is missing: {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, f"candidate breadth holdout artifact is unreadable: {exc}"
    if not isinstance(payload, dict):
        return {}, "candidate breadth holdout artifact must contain a JSON object"
    if payload.get("status") != "candidate_breadth_holdout_replayed_only":
        reason = _payload_string(payload, "reason") or "breadth holdout artifact was not completed"
        return payload, reason
    return payload, None


def _holdout_variants(payload: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    variants = payload.get("variants")
    if not isinstance(variants, list | tuple):
        return ()
    return tuple(variant for variant in variants if isinstance(variant, dict))


def _select_depth_target_variant(
    variants: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any] | None, int]:
    eligible = tuple(variant for variant in variants if _completed_holdout(variant))
    if not eligible:
        return None, 0
    return sorted(eligible, key=_selection_sort_key)[0], len(eligible)


def _selection_from_variant(
    variant: dict[str, Any],
    *,
    artifact_root: Path,
    selection_rank: int,
) -> CandidateDepthTargetSelection:
    metrics = _variant_metrics(variant)
    return CandidateDepthTargetSelection(
        variant_id=_variant_id(variant),
        candidate_experiment_id=_payload_string(variant, "candidate_experiment_id"),
        candidate_parameters=_payload_dict(variant, "candidate_parameters"),
        selection_rank=selection_rank,
        mode="research_scheduling_only",
        heuristic={
            "mode": "research_scheduling_only",
            "rules": (
                "completed_holdout_first",
                "fewer_local_paper_fills",
                "lower_max_drawdown",
                "higher_pnl_floor",
                "variant_id_order",
            ),
            "completed_holdout": _completed_holdout(variant),
            "local_paper_fill_count": _local_paper_fill_count(metrics),
            "max_drawdown": _metric_decimal_text(metrics.get("max_drawdown_max")),
            "pnl_floor": _metric_decimal_text(metrics.get("pnl_min")),
            "promotion_gate": False,
        },
        source_training_metrics_artifact=_variant_artifact(
            variant,
            "training_metrics_artifact",
            artifact_root,
        ),
        source_evaluation_artifact=_variant_artifact(
            variant,
            "evaluation_artifact",
            artifact_root,
        ),
        source_model_artifact=_variant_artifact(
            variant,
            "model_artifact",
            artifact_root,
        ),
        source_calibration_artifact=_variant_artifact(
            variant,
            "calibration_artifact",
            artifact_root,
            nested=("calibration", "artifact"),
        ),
        source_holdout_artifact=_variant_artifact(
            variant,
            "holdout_artifact",
            artifact_root,
            nested=("holdout", "artifact"),
        ),
        source_robustness_artifact=_variant_artifact(
            variant,
            "robustness_artifact",
            artifact_root,
            nested=("holdout", "robustness_artifact"),
        ),
    )


def _variant_considered_payload(
    variant: dict[str, Any],
    artifact_root: Path,
) -> dict[str, Any]:
    metrics = _variant_metrics(variant)
    training_artifact = _variant_artifact(variant, "training_metrics_artifact", artifact_root)
    evaluation_artifact = _variant_artifact(variant, "evaluation_artifact", artifact_root)
    model_artifact = _variant_artifact(variant, "model_artifact", artifact_root)
    return {
        "variant_id": _variant_id(variant),
        "status": _payload_string(variant, "status"),
        "eligible_for_depth_target": _completed_holdout(variant),
        "candidate_experiment_id": _payload_string(variant, "candidate_experiment_id"),
        "heuristic": {
            "mode": "research_scheduling_only",
            "completed_holdout": _completed_holdout(variant),
            "local_paper_fill_count": _local_paper_fill_count(metrics),
            "max_drawdown": _metric_decimal_text(metrics.get("max_drawdown_max")),
            "pnl_floor": _metric_decimal_text(metrics.get("pnl_min")),
        },
        "source_artifact_exists": {
            "training_metrics": False
            if training_artifact is None
            else training_artifact.exists(),
            "evaluation": False
            if evaluation_artifact is None
            else evaluation_artifact.exists(),
            "model": False if model_artifact is None else model_artifact.exists(),
        },
    }


def _completed_holdout(variant: dict[str, Any]) -> bool:
    metrics = _variant_metrics(variant)
    return (
        variant.get("status") == "variant_holdout_replayed_only"
        and metrics.get("holdout_status") == "candidate_threshold_holdout_replayed_only"
    )


def _selection_sort_key(
    variant: dict[str, Any],
) -> tuple[int, int, Decimal, Decimal, str]:
    metrics = _variant_metrics(variant)
    fill_count = _local_paper_fill_count(metrics)
    drawdown = _metric_decimal(metrics.get("max_drawdown_max"))
    pnl_floor = _metric_decimal(metrics.get("pnl_min"))
    return (
        0 if _completed_holdout(variant) else 1,
        fill_count if fill_count is not None else 10**12,
        drawdown if drawdown is not None else Decimal("Infinity"),
        -pnl_floor if pnl_floor is not None else Decimal("Infinity"),
        _variant_id(variant),
    )


def _source_artifact_error(selection: CandidateDepthTargetSelection) -> str | None:
    if not selection.candidate_parameters:
        return f"selected variant {selection.variant_id} has no candidate parameters"
    required = {
        "source training metrics artifact": selection.source_training_metrics_artifact,
        "source evaluation artifact": selection.source_evaluation_artifact,
        "source model artifact": selection.source_model_artifact,
        "source calibration artifact": selection.source_calibration_artifact,
        "source holdout artifact": selection.source_holdout_artifact,
        "source robustness artifact": selection.source_robustness_artifact,
    }
    for label, artifact in required.items():
        if artifact is None:
            return f"selected variant {selection.variant_id} is missing {label}"
        if not artifact.exists():
            return f"selected variant {selection.variant_id} {label} is missing: {artifact}"
    return None


def _write_depth_candidate_artifact(
    *,
    output_dir: Path,
    selection: CandidateDepthTargetSelection,
    breadth_holdout_artifact: Path | None,
) -> Path:
    candidate_dir = output_dir / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    path = candidate_dir / f"{_safe_run_id_part(selection.variant_id)}.json"
    path.write_text(
        json.dumps(
            to_jsonable(
                {
                    "schema_version": selection.schema_version,
                    "candidate_experiment_id": selection.candidate_experiment_id
                    or selection.variant_id,
                    "candidate_parameters": selection.candidate_parameters,
                    "source_breadth_holdout_artifact": None
                    if breadth_holdout_artifact is None
                    else str(breadth_holdout_artifact),
                    "source_variant_id": selection.variant_id,
                    "selection": _selection_payload(selection),
                    "research_scheduling_only": True,
                    "promotion_gate": False,
                }
            ),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def _calibration_slices(
    source_slices: tuple[CandidateDataSliceConfig, ...],
) -> tuple[CandidateThresholdRobustnessSliceConfig, ...]:
    return tuple(
        CandidateThresholdRobustnessSliceConfig(
            slice_id=item.slice_id,
            yahoo_snapshot=item.yahoo_snapshot,
            symbol=item.symbol,
        )
        for item in source_slices
    )


def _depth_metrics(
    *,
    training: BoundedCandidateTrainingResult,
    evaluation: BoundedCandidateEvaluationResult,
    calibration: BoundedCandidateThresholdCalibrationResult,
    holdout: BoundedCandidateThresholdHoldoutResult,
    selection: CandidateDepthTargetSelection,
) -> dict[str, Any]:
    robustness_metrics = dict(holdout.metrics.get("robustness_metrics") or {})
    local_paper_verification = dict(holdout.local_paper_verification)
    return {
        "training_status": training.status,
        "evaluation_status": evaluation.status,
        "calibration_status": calibration.status,
        "holdout_status": holdout.status,
        "selected_backend": training.selected_backend,
        "bars_seen": training.bars_seen,
        "examples_seen": training.examples_seen,
        "source_ready_trace_count": calibration.ready_trace_count,
        "holdout_completed_slice_count": holdout.completed_slice_count,
        "probability_summary": {
            "source": calibration.probability_summary,
            "holdout": holdout.probability_summary,
        },
        "local_paper_verification": local_paper_verification,
        "local_paper_fill_count": local_paper_verification.get("local_paper_fill_count", 0),
        "all_fills_local_paper": local_paper_verification.get(
            "all_fills_local_paper",
            False,
        ),
        "replay_fill_count_total": robustness_metrics.get("replay_fill_count_total", 0),
        "pnl_min": robustness_metrics.get("pnl_min"),
        "pnl_max": robustness_metrics.get("pnl_max"),
        "max_drawdown_max": robustness_metrics.get("max_drawdown_max"),
        "source_verification": {
            "source_variant_id": selection.variant_id,
            "source_training_metrics_artifact": None
            if selection.source_training_metrics_artifact is None
            else str(selection.source_training_metrics_artifact),
            "source_evaluation_artifact": None
            if selection.source_evaluation_artifact is None
            else str(selection.source_evaluation_artifact),
            "source_model_artifact": None
            if selection.source_model_artifact is None
            else str(selection.source_model_artifact),
            "source_calibration_artifact": None
            if selection.source_calibration_artifact is None
            else str(selection.source_calibration_artifact),
            "source_holdout_artifact": None
            if selection.source_holdout_artifact is None
            else str(selection.source_holdout_artifact),
            "source_robustness_artifact": None
            if selection.source_robustness_artifact is None
            else str(selection.source_robustness_artifact),
            "source_artifacts_exist": {
                "training_metrics": selection.source_training_metrics_artifact.exists()
                if selection.source_training_metrics_artifact is not None
                else False,
                "evaluation": selection.source_evaluation_artifact.exists()
                if selection.source_evaluation_artifact is not None
                else False,
                "model": selection.source_model_artifact.exists()
                if selection.source_model_artifact is not None
                else False,
                "calibration": selection.source_calibration_artifact.exists()
                if selection.source_calibration_artifact is not None
                else False,
                "holdout": selection.source_holdout_artifact.exists()
                if selection.source_holdout_artifact is not None
                else False,
                "robustness": selection.source_robustness_artifact.exists()
                if selection.source_robustness_artifact is not None
                else False,
            },
        },
        "research_scheduling_only": True,
        "comparison_is_descriptive": True,
        "promotion_gate": False,
    }


def _variant_artifact(
    variant: dict[str, Any],
    key: str,
    artifact_root: Path,
    *,
    nested: tuple[str, str] | None = None,
) -> Path | None:
    value: Any = variant.get(key)
    if value is None and nested is not None:
        parent = variant.get(nested[0])
        if isinstance(parent, dict):
            value = parent.get(nested[1])
    return _resolve_artifact_path(value, artifact_root)


def _resolve_artifact_path(value: Any, artifact_root: Path) -> Path | None:
    if not value:
        return None
    raw = str(value)
    if raw.startswith(str(APP_MODEL_ARTIFACT_ROOT)):
        relative = PurePosixPath(raw).relative_to(APP_MODEL_ARTIFACT_ROOT)
        return artifact_root.joinpath(*relative.parts)
    return Path(raw)


def _variant_metrics(variant: dict[str, Any]) -> dict[str, Any]:
    value = variant.get("metrics")
    return dict(value) if isinstance(value, dict) else {}


def _local_paper_fill_count(metrics: dict[str, Any]) -> int | None:
    verification = metrics.get("local_paper_verification")
    if isinstance(verification, dict):
        count = _int_metric(verification.get("local_paper_fill_count"))
        if count is not None:
            return count
    return _int_metric(metrics.get("replay_fill_count_total"))


def _int_metric(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _metric_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _metric_decimal_text(value: Any) -> str | None:
    metric = _metric_decimal(value)
    return None if metric is None else str(metric)


def _payload_string(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    return str(value)


def _payload_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _variant_id(variant: dict[str, Any]) -> str:
    return _payload_string(variant, "variant_id") or "unknown"


def _safe_run_id_part(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in ("-", "_") else "-" for char in value)
    return safe or "unknown"
