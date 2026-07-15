"""Bounded holdout bridge for candidate breadth queue artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.serialization import to_jsonable

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
    GpuReadiness,
    _reject_repo_artifact_path,
    detect_gpu_readiness,
)

CandidateBreadthHoldoutStatus = Literal[
    "candidate_breadth_holdout_replayed_only",
    "prepared_not_breadth_holdout_replayed",
]
CandidateBreadthHoldoutVariantStatus = Literal[
    "variant_holdout_replayed_only",
    "prepared_not_holdout_replayed",
]
DEFAULT_CANDIDATE_BREADTH_HOLDOUT_RUN_ID = "bounded-candidate-breadth-holdout"
MAX_CANDIDATE_BREADTH_HOLDOUT_VARIANTS = 3
APP_MODEL_ARTIFACT_ROOT = PurePosixPath("/app/model_artifacts")


@dataclass(frozen=True)
class CandidateBreadthHoldoutConfig:
    run_id: str = DEFAULT_CANDIDATE_BREADTH_HOLDOUT_RUN_ID
    max_bars: int = 180
    min_examples: int = 8
    source_slices: tuple[CandidateThresholdRobustnessSliceConfig, ...] = ()
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
        if self.max_bars <= 0:
            raise ValueError("max_bars must be positive")
        if self.min_examples <= 0:
            raise ValueError("min_examples must be positive")
        if self.starting_cash <= 0:
            raise ValueError("starting_cash must be positive")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.fee_bps < 0:
            raise ValueError("fee_bps must be non-negative")
        if self.slippage_bps < 0:
            raise ValueError("slippage_bps must be non-negative")


@dataclass(frozen=True)
class CandidateBreadthHoldoutVariantResult:
    variant_id: str
    status: CandidateBreadthHoldoutVariantStatus
    reason: str
    candidate_experiment_id: str | None
    candidate_parameters: dict[str, Any]
    training_metrics_artifact: Path | None
    evaluation_artifact: Path | None
    model_artifact: Path | None
    calibration_artifact: Path | None
    holdout_artifact: Path | None
    robustness_artifact: Path | None
    calibration: BoundedCandidateThresholdCalibrationResult | None
    holdout: BoundedCandidateThresholdHoldoutResult | None
    metrics: dict[str, Any]
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class BoundedCandidateBreadthHoldoutResult:
    run_id: str
    status: CandidateBreadthHoldoutStatus
    checked_at: datetime
    gpu: GpuReadiness
    reason: str
    source_breadth_queue_artifact: Path | None
    candidate_experiment_id: str | None
    candidate_parameters: dict[str, Any]
    holdout_artifact: Path
    input_variant_count: int
    processed_variant_count: int
    completed_variant_count: int
    source_slice_count: int
    holdout_slice_count: int
    max_bars: int
    variants: tuple[CandidateBreadthHoldoutVariantResult, ...]
    metrics: dict[str, Any]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_at", self.checked_at.astimezone(UTC))


def run_bounded_candidate_breadth_holdout(
    *,
    config: CandidateBreadthHoldoutConfig,
    artifact_root: Path,
    repo_root: Path | None = None,
    breadth_queue_artifact: Path | None = None,
    gpu: GpuReadiness | None = None,
    probability_runner: CandidateProbabilityRunner | None = None,
) -> BoundedCandidateBreadthHoldoutResult:
    _reject_repo_artifact_path(artifact_root, repo_root)
    if breadth_queue_artifact is not None:
        _reject_repo_artifact_path(breadth_queue_artifact, repo_root)
    output_dir = artifact_root / "candidate-breadth-holdout" / config.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    holdout_artifact = output_dir / "metrics.json"
    gpu = gpu or detect_gpu_readiness()

    queue_payload, queue_error = _read_breadth_queue_artifact(breadth_queue_artifact)
    raw_variants = _queue_variants(queue_payload) if queue_error is None else ()
    selected_variants = raw_variants[:MAX_CANDIDATE_BREADTH_HOLDOUT_VARIANTS]
    variants = tuple(
        _run_variant(
            config=config,
            artifact_root=artifact_root,
            repo_root=repo_root,
            raw_variant=raw_variant,
            gpu=gpu,
            probability_runner=probability_runner,
        )
        for raw_variant in selected_variants
    )
    completed_variant_count = sum(
        1 for variant in variants if variant.status == "variant_holdout_replayed_only"
    )
    status: CandidateBreadthHoldoutStatus = (
        "candidate_breadth_holdout_replayed_only"
        if completed_variant_count > 0
        else "prepared_not_breadth_holdout_replayed"
    )
    first_variant = variants[0] if variants else None
    result = BoundedCandidateBreadthHoldoutResult(
        run_id=config.run_id,
        status=status,
        checked_at=datetime.now(UTC),
        gpu=gpu,
        reason=_result_reason(
            queue_error=queue_error,
            variant_count=len(selected_variants),
            completed_variant_count=completed_variant_count,
        ),
        source_breadth_queue_artifact=breadth_queue_artifact,
        candidate_experiment_id=None
        if first_variant is None
        else first_variant.candidate_experiment_id,
        candidate_parameters={}
        if first_variant is None
        else first_variant.candidate_parameters,
        holdout_artifact=holdout_artifact,
        input_variant_count=len(raw_variants),
        processed_variant_count=len(selected_variants),
        completed_variant_count=completed_variant_count,
        source_slice_count=len(config.source_slices),
        holdout_slice_count=len(config.holdout_slices),
        max_bars=config.max_bars,
        variants=variants,
        metrics=_aggregate_metrics(variants),
    )
    holdout_artifact.write_text(
        json.dumps(
            _candidate_breadth_holdout_payload(result, artifact_root),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return result


def _run_variant(
    *,
    config: CandidateBreadthHoldoutConfig,
    artifact_root: Path,
    repo_root: Path | None,
    raw_variant: dict[str, Any],
    gpu: GpuReadiness,
    probability_runner: CandidateProbabilityRunner | None,
) -> CandidateBreadthHoldoutVariantResult:
    variant_id = _payload_string(raw_variant, "variant_id") or "unknown"
    training_metrics_artifact = _variant_training_artifact(raw_variant, artifact_root)
    evaluation_artifact = _variant_evaluation_artifact(raw_variant, artifact_root)
    model_artifact = _variant_model_artifact(raw_variant, artifact_root)
    calibration = run_bounded_candidate_threshold_calibration(
        config=CandidateThresholdCalibrationConfig(
            run_id=_variant_run_id(config.run_id, variant_id, "cal"),
            max_bars=config.max_bars,
            min_examples=config.min_examples,
            slices=config.source_slices,
            sample_seed=config.sample_seed,
            starting_cash=config.starting_cash,
            quantity=config.quantity,
            fee_bps=config.fee_bps,
            slippage_bps=config.slippage_bps,
        ),
        artifact_root=artifact_root,
        repo_root=repo_root,
        training_metrics_artifact=training_metrics_artifact,
        evaluation_artifact=evaluation_artifact,
        model_artifact=model_artifact,
        gpu=gpu,
        probability_runner=probability_runner,
    )
    holdout = run_bounded_candidate_threshold_holdout(
        config=CandidateThresholdHoldoutConfig(
            run_id=_variant_run_id(config.run_id, variant_id, "hold"),
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
        gpu=gpu,
        probability_runner=probability_runner,
    )
    status: CandidateBreadthHoldoutVariantStatus = (
        "variant_holdout_replayed_only"
        if holdout.status == "candidate_threshold_holdout_replayed_only"
        else "prepared_not_holdout_replayed"
    )
    return CandidateBreadthHoldoutVariantResult(
        variant_id=variant_id,
        status=status,
        reason=(
            "candidate breadth variant holdout replay completed without promotion decision"
            if status == "variant_holdout_replayed_only"
            else f"{calibration.reason}; {holdout.reason}"
        ),
        candidate_experiment_id=_payload_string(raw_variant, "candidate_experiment_id"),
        candidate_parameters=_payload_dict(raw_variant, "candidate_parameters"),
        training_metrics_artifact=training_metrics_artifact,
        evaluation_artifact=evaluation_artifact,
        model_artifact=model_artifact,
        calibration_artifact=calibration.calibration_artifact,
        holdout_artifact=holdout.holdout_artifact,
        robustness_artifact=holdout.robustness_artifact,
        calibration=calibration,
        holdout=holdout,
        metrics=_variant_metrics(calibration, holdout),
    )


def _candidate_breadth_holdout_payload(
    result: BoundedCandidateBreadthHoldoutResult,
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
            "source_breadth_queue_artifact": None
            if result.source_breadth_queue_artifact is None
            else str(result.source_breadth_queue_artifact),
            "candidate_experiment_id": result.candidate_experiment_id,
            "candidate_parameters": result.candidate_parameters,
            "input_variant_count": result.input_variant_count,
            "processed_variant_count": result.processed_variant_count,
            "completed_variant_count": result.completed_variant_count,
            "source_slice_count": result.source_slice_count,
            "holdout_slice_count": result.holdout_slice_count,
            "max_bars": result.max_bars,
            "variants": tuple(_variant_payload(variant) for variant in result.variants),
            "metrics": result.metrics,
            "selection": {
                "winner": None,
                "recommendation": None,
                "promotion_gate": False,
                "mode": "descriptive_breadth_holdout_only",
            },
            "artifacts": {
                "candidate_breadth_holdout": str(result.holdout_artifact),
                "calibrations": tuple(
                    None
                    if variant.calibration_artifact is None
                    else str(variant.calibration_artifact)
                    for variant in result.variants
                ),
                "holdouts": tuple(
                    None
                    if variant.holdout_artifact is None
                    else str(variant.holdout_artifact)
                    for variant in result.variants
                ),
                "robustness": tuple(
                    None
                    if variant.robustness_artifact is None
                    else str(variant.robustness_artifact)
                    for variant in result.variants
                ),
            },
            "artifact_policy": {
                "root": str(artifact_root),
                "repo_storage_allowed": False,
            },
        }
    )


def _variant_payload(variant: CandidateBreadthHoldoutVariantResult) -> dict[str, Any]:
    holdout = variant.holdout
    calibration = variant.calibration
    return {
        "schema_version": variant.schema_version,
        "variant_id": variant.variant_id,
        "status": variant.status,
        "reason": variant.reason,
        "candidate_experiment_id": variant.candidate_experiment_id,
        "candidate_parameters": variant.candidate_parameters,
        "training_metrics_artifact": None
        if variant.training_metrics_artifact is None
        else str(variant.training_metrics_artifact),
        "evaluation_artifact": None
        if variant.evaluation_artifact is None
        else str(variant.evaluation_artifact),
        "model_artifact": None if variant.model_artifact is None else str(variant.model_artifact),
        "calibration": {
            "status": None if calibration is None else calibration.status,
            "reason": None if calibration is None else calibration.reason,
            "artifact": None
            if variant.calibration_artifact is None
            else str(variant.calibration_artifact),
            "ready_trace_count": 0 if calibration is None else calibration.ready_trace_count,
            "threshold_pairs": ()
            if calibration is None
            else calibration.threshold_pairs,
            "probability_summary": {}
            if calibration is None
            else calibration.probability_summary,
        },
        "holdout": {
            "status": None if holdout is None else holdout.status,
            "reason": None if holdout is None else holdout.reason,
            "artifact": None
            if variant.holdout_artifact is None
            else str(variant.holdout_artifact),
            "robustness_artifact": None
            if variant.robustness_artifact is None
            else str(variant.robustness_artifact),
            "completed_slice_count": 0 if holdout is None else holdout.completed_slice_count,
            "probability_summary": {} if holdout is None else holdout.probability_summary,
            "local_paper_verification": {}
            if holdout is None
            else holdout.local_paper_verification,
            "data_requests": () if holdout is None else holdout.data_requests,
        },
        "metrics": variant.metrics,
    }


def _variant_metrics(
    calibration: BoundedCandidateThresholdCalibrationResult,
    holdout: BoundedCandidateThresholdHoldoutResult,
) -> dict[str, Any]:
    robustness_metrics = dict(holdout.metrics.get("robustness_metrics") or {})
    local_paper_verification = dict(holdout.local_paper_verification)
    return {
        "calibration_status": calibration.status,
        "holdout_status": holdout.status,
        "source_ready_trace_count": calibration.ready_trace_count,
        "holdout_completed_slice_count": holdout.completed_slice_count,
        "threshold_pair_count": len(holdout.threshold_pairs),
        "probability_summary": holdout.probability_summary,
        "replay_fill_count_total": robustness_metrics.get("replay_fill_count_total", 0),
        "pnl_min": robustness_metrics.get("pnl_min"),
        "pnl_max": robustness_metrics.get("pnl_max"),
        "max_drawdown_max": robustness_metrics.get("max_drawdown_max"),
        "local_paper_verification": local_paper_verification,
        "comparison_is_descriptive": True,
        "promotion_gate": False,
    }


def _aggregate_metrics(
    variants: tuple[CandidateBreadthHoldoutVariantResult, ...],
) -> dict[str, Any]:
    local_paper_fill_count = 0
    all_fills_local_paper = True
    data_requests: list[dict[str, Any]] = []
    for variant in variants:
        verification = variant.metrics.get("local_paper_verification")
        if isinstance(verification, dict):
            local_paper_fill_count += int(verification.get("local_paper_fill_count") or 0)
            all_fills_local_paper = (
                all_fills_local_paper
                and verification.get("all_fills_local_paper") is not False
            )
        if variant.holdout is not None:
            data_requests.extend(variant.holdout.data_requests)
    return {
        "completed_variant_count": sum(
            1
            for variant in variants
            if variant.status == "variant_holdout_replayed_only"
        ),
        "processed_variant_count": len(variants),
        "local_paper_fill_count_total": local_paper_fill_count,
        "all_fills_local_paper": all_fills_local_paper,
        "data_requests": tuple(data_requests),
        "comparison_is_descriptive": True,
        "promotion_gate": False,
    }


def _read_breadth_queue_artifact(
    path: Path | None,
) -> tuple[dict[str, Any], str | None]:
    if path is None:
        return {}, "candidate breadth queue artifact is required"
    if not path.exists():
        return {}, f"candidate breadth queue artifact is missing: {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, f"candidate breadth queue artifact is unreadable: {exc}"
    if not isinstance(payload, dict):
        return {}, "candidate breadth queue artifact must contain a JSON object"
    if payload.get("status") != "candidate_breadth_queued_only":
        reason = _payload_string(payload, "reason") or "breadth queue artifact was not completed"
        return payload, reason
    return payload, None


def _queue_variants(payload: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    variants = payload.get("variants")
    if not isinstance(variants, list | tuple):
        return ()
    return tuple(variant for variant in variants if isinstance(variant, dict))


def _variant_training_artifact(
    variant: dict[str, Any],
    artifact_root: Path,
) -> Path | None:
    training = variant.get("training")
    if not isinstance(training, dict):
        return None
    return _resolve_artifact_path(training.get("metrics_artifact"), artifact_root)


def _variant_evaluation_artifact(
    variant: dict[str, Any],
    artifact_root: Path,
) -> Path | None:
    evaluation = variant.get("evaluation")
    if not isinstance(evaluation, dict):
        return None
    return _resolve_artifact_path(evaluation.get("evaluation_artifact"), artifact_root)


def _variant_model_artifact(
    variant: dict[str, Any],
    artifact_root: Path,
) -> Path | None:
    training = variant.get("training")
    if not isinstance(training, dict):
        return None
    return _resolve_artifact_path(training.get("model_artifact"), artifact_root)


def _resolve_artifact_path(value: Any, artifact_root: Path) -> Path | None:
    if not value:
        return None
    raw = str(value)
    if raw.startswith(str(APP_MODEL_ARTIFACT_ROOT)):
        relative = PurePosixPath(raw).relative_to(APP_MODEL_ARTIFACT_ROOT)
        return artifact_root.joinpath(*relative.parts)
    return Path(raw)


def _variant_run_id(run_id: str, variant_id: str, suffix: str) -> str:
    return f"{run_id}-{variant_id}-{suffix}"


def _result_reason(
    *,
    queue_error: str | None,
    variant_count: int,
    completed_variant_count: int,
) -> str:
    if queue_error is not None:
        return queue_error
    if variant_count == 0:
        return "no breadth queue variants available"
    if completed_variant_count == 0:
        return "no breadth variant holdout replay completed"
    return "bounded breadth holdout replay completed without promotion decision"


def _payload_string(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    return str(value)


def _payload_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return dict(value) if isinstance(value, dict) else {}
