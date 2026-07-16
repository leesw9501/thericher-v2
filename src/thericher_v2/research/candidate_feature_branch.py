"""Bounded feature/model branch after threshold-only loop closure."""

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
from .candidate_threshold_rerun import (
    _payload_dict,
    _payload_string,
    _read_json_artifact,
    _resolve_optional_path,
)
from .candidate_training import (
    CORE_PLUS_BAR_POSITION_FEATURE_SET_ID,
    CORE_PLUS_BAR_PRESSURE_FEATURE_SET_ID,
    DEFAULT_CANDIDATE_FEATURE_PREPROCESSING,
    DEFAULT_CANDIDATE_TRAINING_HIDDEN_UNITS,
    DEFAULT_CANDIDATE_TRAINING_WEIGHT_DECAY,
    SUPPORTED_CANDIDATE_FEATURE_SETS,
    BoundedCandidateTrainingResult,
    CandidateDataSliceConfig,
    CandidateTrainerRunner,
    CandidateTrainingConfig,
    GpuReadiness,
    _preprocessing_axis_payload,
    _regularization_axis_payload,
    _reject_repo_artifact_path,
    detect_gpu_readiness,
    run_bounded_candidate_training,
)

CandidateFeatureBranchStatus = Literal[
    "candidate_feature_branch_evaluated_only",
    "prepared_not_feature_branched",
]
DEFAULT_CANDIDATE_FEATURE_BRANCH_RUN_ID = "bounded-candidate-feature-branch"
DEFAULT_CANDIDATE_FEATURE_BRANCH_FEATURE_SET_ID = CORE_PLUS_BAR_POSITION_FEATURE_SET_ID
FEATURE_BRANCH_AXIS_BY_FEATURE_SET = {
    CORE_PLUS_BAR_POSITION_FEATURE_SET_ID: "bar_position",
    CORE_PLUS_BAR_PRESSURE_FEATURE_SET_ID: "bar_pressure",
}


@dataclass(frozen=True)
class CandidateFeatureBranchConfig:
    run_id: str = DEFAULT_CANDIDATE_FEATURE_BRANCH_RUN_ID
    feature_set_id: str = DEFAULT_CANDIDATE_FEATURE_BRANCH_FEATURE_SET_ID
    max_bars: int = 120
    max_epochs: int = 4
    max_steps: int = 128
    hidden_units: int = DEFAULT_CANDIDATE_TRAINING_HIDDEN_UNITS
    weight_decay: float = DEFAULT_CANDIDATE_TRAINING_WEIGHT_DECAY
    feature_preprocessing: str = DEFAULT_CANDIDATE_FEATURE_PREPROCESSING
    min_examples: int = 8
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("run_id is required")
        if not self.feature_set_id:
            raise ValueError("feature_set_id is required")
        if self.feature_set_id not in SUPPORTED_CANDIDATE_FEATURE_SETS:
            raise ValueError(f"unsupported candidate feature_set: {self.feature_set_id}")
        CandidateTrainingConfig(
            run_id=f"{self.run_id}-cap-validation",
            max_bars=self.max_bars,
            max_epochs=self.max_epochs,
            max_steps=self.max_steps,
            hidden_units=self.hidden_units,
            weight_decay=self.weight_decay,
            feature_preprocessing=self.feature_preprocessing,
            min_examples=self.min_examples,
        )
        CandidateEvaluationConfig(
            run_id=f"{self.run_id}-cap-validation",
            max_bars=self.max_bars,
            min_examples=self.min_examples,
        )


@dataclass(frozen=True)
class BoundedCandidateFeatureBranchResult:
    run_id: str
    status: CandidateFeatureBranchStatus
    checked_at: datetime
    gpu: GpuReadiness
    reason: str
    source_threshold_band_rerun_artifact: Path | None
    feature_branch_artifact: Path
    candidate_artifact: Path | None
    training_metrics_artifact: Path | None
    evaluation_artifact: Path | None
    model_artifact: Path | None
    candidate_experiment_id: str | None
    candidate_parameters: dict[str, Any]
    feature_set_id: str
    weight_decay: float
    feature_preprocessing: str
    feature_normalization: dict[str, Any] | None
    threshold_loop_closure: dict[str, Any]
    artifact_verification: dict[str, Any]
    training_source_slices: tuple[dict[str, Any], ...]
    evaluation_source_slices: tuple[dict[str, Any], ...]
    training: BoundedCandidateTrainingResult | None
    evaluation: BoundedCandidateEvaluationResult | None
    metrics: dict[str, Any]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_at", self.checked_at.astimezone(UTC))


def run_bounded_candidate_feature_branch(
    *,
    config: CandidateFeatureBranchConfig | None = None,
    artifact_root: Path,
    repo_root: Path | None = None,
    threshold_band_rerun_artifact: Path | None = None,
    yahoo_snapshot: Path | None = None,
    symbol: str | None = None,
    data_slices: tuple[CandidateDataSliceConfig, ...] = (),
    evaluation_data_slices: tuple[CandidateDataSliceConfig, ...] = (),
    gpu: GpuReadiness | None = None,
    trainer_runner: CandidateTrainerRunner | None = None,
    evaluation_runner: CandidateEvaluationRunner | None = None,
) -> BoundedCandidateFeatureBranchResult:
    config = config or CandidateFeatureBranchConfig()
    _reject_repo_artifact_path(artifact_root, repo_root)
    output_dir = artifact_root / "candidate-feature-branch" / config.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    feature_branch_artifact = output_dir / "metrics.json"
    gpu = gpu or detect_gpu_readiness()

    resolved_band_artifact = _resolve_optional_path(
        threshold_band_rerun_artifact,
        artifact_root,
    )
    if resolved_band_artifact is not None:
        _reject_repo_artifact_path(resolved_band_artifact, repo_root)
    band_payload, band_error = _read_json_artifact(
        resolved_band_artifact,
        required_label="candidate threshold band rerun artifact",
    )
    artifact_verification = _artifact_verification(
        band_artifact=resolved_band_artifact,
        band_payload=band_payload,
    )
    threshold_loop_closure = _threshold_loop_closure(band_payload)
    initial_errors = tuple(
        error
        for error in (
            band_error,
            _status_error(
                band_payload,
                expected="candidate_threshold_band_rerun_replayed_only",
                label="candidate threshold band rerun",
            ),
            _artifact_error(artifact_verification),
        )
        if error is not None
    )

    candidate_artifact: Path | None = None
    training: BoundedCandidateTrainingResult | None = None
    evaluation: BoundedCandidateEvaluationResult | None = None
    candidate_experiment_id = _feature_branch_experiment_id(
        _payload_string(band_payload, "candidate_experiment_id"),
        config.feature_set_id,
    )
    candidate_parameters = _feature_branch_parameters(
        _payload_dict(band_payload, "candidate_parameters"),
        config.feature_set_id,
    )
    if not initial_errors:
        candidate_artifact = _write_candidate_artifact(
            output_dir=output_dir,
            candidate_experiment_id=candidate_experiment_id,
            candidate_parameters=candidate_parameters,
            source_threshold_band_rerun_artifact=resolved_band_artifact,
        )
        training = run_bounded_candidate_training(
            config=CandidateTrainingConfig(
                run_id=f"{config.run_id}-training",
                max_bars=config.max_bars,
                max_epochs=config.max_epochs,
                max_steps=config.max_steps,
                hidden_units=config.hidden_units,
                weight_decay=config.weight_decay,
                feature_preprocessing=config.feature_preprocessing,
                min_examples=config.min_examples,
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
                run_id=f"{config.run_id}-evaluation",
                max_bars=config.max_bars,
                min_examples=config.min_examples,
            ),
            artifact_root=artifact_root,
            repo_root=repo_root,
            training_metrics_artifact=training.metrics_artifact,
            model_artifact=training.model_artifact,
            yahoo_snapshot=yahoo_snapshot,
            symbol=symbol,
            data_slices=evaluation_data_slices or data_slices,
            gpu=gpu,
            evaluation_runner=evaluation_runner,
        )

    status: CandidateFeatureBranchStatus = (
        "candidate_feature_branch_evaluated_only"
        if evaluation is not None and evaluation.status == "candidate_evaluated_only"
        else "prepared_not_feature_branched"
    )
    result = BoundedCandidateFeatureBranchResult(
        run_id=config.run_id,
        status=status,
        checked_at=datetime.now(UTC),
        gpu=gpu,
        reason=(
            "bounded feature/model branch evaluated without promotion decision"
            if status == "candidate_feature_branch_evaluated_only"
            else "; ".join(
                initial_errors
                or _pipeline_reasons(training=training, evaluation=evaluation)
                or ("feature/model branch did not complete",)
            )
        ),
        source_threshold_band_rerun_artifact=resolved_band_artifact,
        feature_branch_artifact=feature_branch_artifact,
        candidate_artifact=candidate_artifact,
        training_metrics_artifact=None if training is None else training.metrics_artifact,
        evaluation_artifact=None if evaluation is None else evaluation.evaluation_artifact,
        model_artifact=None if training is None else training.model_artifact,
        candidate_experiment_id=candidate_experiment_id,
        candidate_parameters=candidate_parameters,
        feature_set_id=config.feature_set_id,
        weight_decay=config.weight_decay,
        feature_preprocessing=config.feature_preprocessing,
        feature_normalization=None if training is None else training.feature_normalization,
        threshold_loop_closure=threshold_loop_closure,
        artifact_verification=artifact_verification,
        training_source_slices=() if training is None else training.source_slices,
        evaluation_source_slices=() if evaluation is None else evaluation.source_slices,
        training=training,
        evaluation=evaluation,
        metrics=_feature_branch_metrics(
            config=config,
            threshold_loop_closure=threshold_loop_closure,
            training=training,
            evaluation=evaluation,
        ),
    )
    feature_branch_artifact.write_text(
        json.dumps(
            _candidate_feature_branch_payload(result, artifact_root),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return result


def _candidate_feature_branch_payload(
    result: BoundedCandidateFeatureBranchResult,
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
            "source_threshold_band_rerun_artifact": None
            if result.source_threshold_band_rerun_artifact is None
            else str(result.source_threshold_band_rerun_artifact),
            "candidate_artifact": None
            if result.candidate_artifact is None
            else str(result.candidate_artifact),
            "candidate_experiment_id": result.candidate_experiment_id,
            "candidate_parameters": result.candidate_parameters,
            "feature_set_id": result.feature_set_id,
            "model_axis": _model_axis_payload(result),
            "regularization_axis": _regularization_axis_payload(result.weight_decay),
            "feature_preprocessing": result.feature_preprocessing,
            "preprocessing_axis": _preprocessing_axis_payload(result.feature_preprocessing),
            "feature_normalization": result.feature_normalization,
            "threshold_loop_closure": result.threshold_loop_closure,
            "artifact_verification": result.artifact_verification,
            "training_source_slices": result.training_source_slices,
            "evaluation_source_slices": result.evaluation_source_slices,
            "training_status": None if result.training is None else result.training.status,
            "evaluation_status": None
            if result.evaluation is None
            else result.evaluation.status,
            "metrics": result.metrics,
            "result_scope": {
                "mode": "research_feature_branch_only",
                "descriptive_only": True,
                "promotion_gate": False,
            },
            "artifacts": {
                "candidate_feature_branch": str(result.feature_branch_artifact),
                "candidate": None
                if result.candidate_artifact is None
                else str(result.candidate_artifact),
                "candidate_training": None
                if result.training_metrics_artifact is None
                else str(result.training_metrics_artifact),
                "candidate_evaluation": None
                if result.evaluation_artifact is None
                else str(result.evaluation_artifact),
                "model": None
                if result.model_artifact is None
                else str(result.model_artifact),
            },
            "artifact_policy": {
                "root": str(artifact_root),
                "repo_storage_allowed": False,
            },
        }
    )


def _write_candidate_artifact(
    *,
    output_dir: Path,
    candidate_experiment_id: str,
    candidate_parameters: dict[str, Any],
    source_threshold_band_rerun_artifact: Path | None,
) -> Path:
    candidate_dir = output_dir / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    path = candidate_dir / "feature_branch_candidate.json"
    path.write_text(
        json.dumps(
            to_jsonable(
                {
                    "schema_version": SCHEMA_VERSION,
                    "candidate_experiment_id": candidate_experiment_id,
                    "candidate_parameters": candidate_parameters,
                    "source_threshold_band_rerun_artifact": None
                    if source_threshold_band_rerun_artifact is None
                    else str(source_threshold_band_rerun_artifact),
                    "promotion_gate": False,
                    "research_scope": "feature_branch_context_candidate",
                }
            ),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def _feature_branch_experiment_id(source_id: str | None, feature_set_id: str) -> str:
    base = source_id or "candidate"
    safe_feature_set = feature_set_id.replace("\\", "_").replace("/", "_").replace(":", "_")
    return f"{base}__{safe_feature_set}"


def _feature_branch_parameters(
    source_parameters: dict[str, Any],
    feature_set_id: str,
) -> dict[str, Any]:
    parameters = dict(source_parameters)
    parameters["feature_set"] = feature_set_id
    parameters["feature_branch_axis"] = _feature_branch_axis(feature_set_id)
    return parameters


def _feature_branch_axis(feature_set_id: str) -> str:
    return FEATURE_BRANCH_AXIS_BY_FEATURE_SET.get(feature_set_id, feature_set_id)


def _threshold_loop_closure(payload: dict[str, Any]) -> dict[str, Any]:
    metrics = _payload_dict(payload, "metrics")
    local_paper = _payload_dict(payload, "local_paper_verification")
    return {
        "mode": "threshold_loop_closed_until_feature_branch_changes_probability_evidence",
        "closed_for_current_candidate": payload.get("status")
        == "candidate_threshold_band_rerun_replayed_only",
        "source_status": payload.get("status"),
        "replay_fill_count_total": metrics.get("replay_fill_count_total"),
        "completed_variant_count": metrics.get("completed_variant_count"),
        "source_context_all_fills_local_paper": local_paper.get("all_fills_local_paper"),
        "descriptive_only": True,
        "promotion_gate": False,
    }


def _artifact_verification(
    *,
    band_artifact: Path | None,
    band_payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "threshold_band_rerun_artifact_exists": band_artifact is not None
        and band_artifact.exists(),
        "threshold_band_rerun_status": band_payload.get("status"),
        "threshold_band_context_only": True,
        "network_required": False,
        "credential_required": False,
    }


def _artifact_error(verification: dict[str, Any]) -> str | None:
    if not verification["threshold_band_rerun_artifact_exists"]:
        return "candidate threshold band rerun artifact is unavailable"
    return None


def _status_error(payload: dict[str, Any], *, expected: str, label: str) -> str | None:
    actual = payload.get("status")
    if actual == expected:
        return None
    return f"{label} status is {actual!r}, expected {expected!r}"


def _pipeline_reasons(
    *,
    training: BoundedCandidateTrainingResult | None,
    evaluation: BoundedCandidateEvaluationResult | None,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if training is not None and training.status != "candidate_trained_only":
        reasons.append(training.reason)
    if evaluation is not None and evaluation.status != "candidate_evaluated_only":
        reasons.append(evaluation.reason)
    return tuple(reasons)


def _feature_branch_metrics(
    *,
    config: CandidateFeatureBranchConfig,
    threshold_loop_closure: dict[str, Any],
    training: BoundedCandidateTrainingResult | None,
    evaluation: BoundedCandidateEvaluationResult | None,
) -> dict[str, Any]:
    evaluation_metrics = {} if evaluation is None else evaluation.metrics
    return {
        "research_feature_branch_only": True,
        "feature_set_id": config.feature_set_id,
        "model_axis": {
            "axis": "hidden_units",
            "hidden_units": config.hidden_units,
            "descriptive_only": True,
            "promotion_gate": False,
        },
        "regularization_axis": _regularization_axis_payload(config.weight_decay),
        "feature_preprocessing": config.feature_preprocessing,
        "preprocessing_axis": _preprocessing_axis_payload(config.feature_preprocessing),
        "feature_normalization": None if training is None else training.feature_normalization,
        "threshold_loop_closure_recorded": bool(
            threshold_loop_closure.get("closed_for_current_candidate")
        ),
        "training_source_slices": () if training is None else training.source_slices,
        "evaluation_source_slices": () if evaluation is None else evaluation.source_slices,
        "training_status": None if training is None else training.status,
        "evaluation_status": None if evaluation is None else evaluation.status,
        "training_examples_seen": 0 if training is None else training.examples_seen,
        "evaluation_examples_seen": 0 if evaluation is None else evaluation.examples_seen,
        "feature_names": ()
        if training is None
        else training.metrics.get("feature_names", ()),
        "probability_evidence": _probability_evidence(evaluation_metrics),
        "local_paper_context": {
            "replay_executed_by_feature_branch": False,
            "source_context_all_fills_local_paper": threshold_loop_closure.get(
                "source_context_all_fills_local_paper"
            ),
        },
        "descriptive_only": True,
        "promotion_gate": False,
    }


def _probability_evidence(metrics: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "min_probability",
        "max_probability",
        "mean_probability",
        "probability_range",
        "predicted_positive_rate",
        "label_positive_rate",
        "accuracy",
        "loss",
    )
    return {field: metrics[field] for field in fields if field in metrics}


def _model_axis_payload(result: BoundedCandidateFeatureBranchResult) -> dict[str, Any]:
    return {
        "axis": "hidden_units",
        "hidden_units": result.metrics.get("model_axis", {}).get("hidden_units"),
        "descriptive_only": True,
        "promotion_gate": False,
    }
