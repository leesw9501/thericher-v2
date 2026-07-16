"""Bounded local-paper replay for a feature-branch candidate."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_FLOOR, Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.execution import (
    FillEventArtifact,
    collect_fill_source_evidence,
)
from thericher_v2.serialization import to_jsonable

from .candidate_replay import CandidateProbabilityRunner
from .candidate_threshold_attribution import (
    _all_artifacts_exist as _all_attribution_artifacts_exist,
)
from .candidate_threshold_attribution import (
    _artifact_payload as _attribution_artifact_payload,
)
from .candidate_threshold_attribution import (
    _attribution_slices,
)
from .candidate_threshold_attribution import (
    _int_metric as _attribution_int_metric,
)
from .candidate_threshold_attribution import (
    _payload_list as _attribution_payload_list,
)
from .candidate_threshold_attribution import (
    _slice_error as _attribution_slice_error,
)
from .candidate_threshold_attribution import (
    _threshold_pairs_from_payload as _attribution_threshold_pairs_from_payload,
)
from .candidate_threshold_rerun import (
    _payload_dict,
    _payload_string,
    _read_json_artifact,
    _resolve_optional_path,
)
from .candidate_threshold_robustness import (
    BoundedCandidateThresholdRobustnessResult,
    CandidateThresholdRobustnessConfig,
    CandidateThresholdRobustnessSliceConfig,
    run_bounded_candidate_threshold_robustness,
)
from .candidate_training import (
    GpuReadiness,
    _reject_repo_artifact_path,
    detect_gpu_readiness,
)

CandidateFeatureBranchReplayStatus = Literal[
    "candidate_feature_branch_replayed_only",
    "prepared_not_feature_branch_replayed",
]
DEFAULT_CANDIDATE_FEATURE_BRANCH_REPLAY_RUN_ID = (
    "bounded-candidate-feature-branch-replay"
)
DEFAULT_CANDIDATE_FEATURE_BRANCH_REPLAY_ATTRIBUTION_RUN_ID = (
    "bounded-candidate-feature-branch-replay-attribution"
)
MAX_FEATURE_BRANCH_REPLAY_THRESHOLD_PAIRS = 3
THRESHOLD_STEP = Decimal("0.001")
MAX_FEATURE_BRANCH_REPLAY_BUY_THRESHOLD = Decimal("0.999")
CandidateFeatureBranchReplayAttributionStatus = Literal[
    "candidate_feature_branch_replay_attribution_only",
    "prepared_not_feature_branch_replay_attributed",
]


@dataclass(frozen=True)
class CandidateFeatureBranchReplayConfig:
    run_id: str = DEFAULT_CANDIDATE_FEATURE_BRANCH_REPLAY_RUN_ID
    max_bars: int = 120
    min_examples: int = 8
    threshold_pair_cap: int = MAX_FEATURE_BRANCH_REPLAY_THRESHOLD_PAIRS
    slices: tuple[CandidateThresholdRobustnessSliceConfig, ...] = ()
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("run_id is required")
        if not 0 < self.threshold_pair_cap <= MAX_FEATURE_BRANCH_REPLAY_THRESHOLD_PAIRS:
            raise ValueError(
                "threshold_pair_cap must be between 1 and "
                f"{MAX_FEATURE_BRANCH_REPLAY_THRESHOLD_PAIRS}"
            )
        CandidateThresholdRobustnessConfig(
            run_id=f"{self.run_id}-cap-validation",
            max_bars=self.max_bars,
            min_examples=self.min_examples,
            slices=self.slices,
        )


@dataclass(frozen=True)
class BoundedCandidateFeatureBranchReplayResult:
    run_id: str
    status: CandidateFeatureBranchReplayStatus
    checked_at: datetime
    gpu: GpuReadiness
    reason: str
    source_feature_branch_artifact: Path | None
    feature_branch_replay_artifact: Path
    training_metrics_artifact: Path | None
    evaluation_artifact: Path | None
    model_artifact: Path | None
    candidate_experiment_id: str | None
    candidate_parameters: dict[str, Any]
    threshold_pairs: tuple[tuple[float, float], ...]
    threshold_derivation: dict[str, Any]
    artifact_verification: dict[str, Any]
    slice_count: int
    completed_slice_count: int
    local_paper_verification: dict[str, Any]
    robustness: BoundedCandidateThresholdRobustnessResult | None
    metrics: dict[str, Any]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_at", self.checked_at.astimezone(UTC))


@dataclass(frozen=True)
class CandidateFeatureBranchReplayAttributionConfig:
    run_id: str = DEFAULT_CANDIDATE_FEATURE_BRANCH_REPLAY_ATTRIBUTION_RUN_ID
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("run_id is required")


@dataclass(frozen=True)
class BoundedCandidateFeatureBranchReplayAttributionResult:
    run_id: str
    status: CandidateFeatureBranchReplayAttributionStatus
    checked_at: datetime
    reason: str
    source_feature_branch_replay_artifact: Path | None
    source_robustness_artifact: Path | None
    attribution_artifact: Path
    candidate_experiment_id: str | None
    candidate_parameters: dict[str, Any]
    threshold_pairs: tuple[tuple[float, float], ...]
    threshold_derivation: dict[str, Any]
    artifact_verification: dict[str, Any]
    local_paper_verification: dict[str, Any]
    slices: tuple[dict[str, Any], ...]
    metrics: dict[str, Any]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_at", self.checked_at.astimezone(UTC))


def run_bounded_candidate_feature_branch_replay(
    *,
    config: CandidateFeatureBranchReplayConfig | None = None,
    artifact_root: Path,
    repo_root: Path | None = None,
    feature_branch_artifact: Path | None = None,
    gpu: GpuReadiness | None = None,
    probability_runner: CandidateProbabilityRunner | None = None,
) -> BoundedCandidateFeatureBranchReplayResult:
    config = config or CandidateFeatureBranchReplayConfig()
    _reject_repo_artifact_path(artifact_root, repo_root)
    output_dir = artifact_root / "candidate-feature-branch-replay" / config.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    replay_artifact = output_dir / "metrics.json"
    gpu = gpu or detect_gpu_readiness()

    resolved_feature_branch_artifact = _resolve_optional_path(
        feature_branch_artifact,
        artifact_root,
    )
    if resolved_feature_branch_artifact is not None:
        _reject_repo_artifact_path(resolved_feature_branch_artifact, repo_root)
    feature_branch_payload, feature_branch_error = _read_json_artifact(
        resolved_feature_branch_artifact,
        required_label="candidate feature branch artifact",
    )
    artifacts = _payload_dict(feature_branch_payload, "artifacts")
    training_artifact = _resolved_artifact(artifacts, "candidate_training", artifact_root)
    evaluation_artifact = _resolved_artifact(artifacts, "candidate_evaluation", artifact_root)
    model_artifact = _resolved_artifact(artifacts, "model", artifact_root)
    probability_evidence = _payload_dict(
        _payload_dict(feature_branch_payload, "metrics"),
        "probability_evidence",
    )
    threshold_pairs = derive_feature_branch_replay_threshold_pairs(
        probability_evidence,
        cap=config.threshold_pair_cap,
    )
    artifact_verification = _artifact_verification(
        feature_branch_artifact=resolved_feature_branch_artifact,
        training_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        model_artifact=model_artifact,
        slices=config.slices,
    )
    initial_errors = tuple(
        error
        for error in (
            feature_branch_error,
            _status_error(
                feature_branch_payload,
                expected="candidate_feature_branch_evaluated_only",
                label="candidate feature branch",
            ),
            None if threshold_pairs else "feature branch replay threshold pairs are unavailable",
            None if config.slices else "feature branch replay slices are required",
            _artifact_error(artifact_verification),
        )
        if error is not None
    )
    robustness: BoundedCandidateThresholdRobustnessResult | None = None
    if not initial_errors:
        robustness = run_bounded_candidate_threshold_robustness(
            config=CandidateThresholdRobustnessConfig(
                run_id=f"{config.run_id}-robustness",
                max_bars=config.max_bars,
                min_examples=config.min_examples,
                threshold_pairs=threshold_pairs,
                slices=config.slices,
            ),
            artifact_root=artifact_root,
            repo_root=repo_root,
            training_metrics_artifact=training_artifact,
            evaluation_artifact=evaluation_artifact,
            model_artifact=model_artifact,
            gpu=gpu,
            probability_runner=probability_runner,
        )

    status: CandidateFeatureBranchReplayStatus = (
        "candidate_feature_branch_replayed_only"
        if robustness is not None
        and robustness.status == "candidate_robustness_replayed_only"
        else "prepared_not_feature_branch_replayed"
    )
    local_paper_verification = _local_paper_verification(robustness)
    result = BoundedCandidateFeatureBranchReplayResult(
        run_id=config.run_id,
        status=status,
        checked_at=datetime.now(UTC),
        gpu=gpu,
        reason=(
            "bounded feature-branch local-paper replay completed"
            if status == "candidate_feature_branch_replayed_only"
            else "; ".join(
                initial_errors
                or (() if robustness is None else (robustness.reason,))
                or ("feature-branch replay did not complete",)
            )
        ),
        source_feature_branch_artifact=resolved_feature_branch_artifact,
        feature_branch_replay_artifact=replay_artifact,
        training_metrics_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        model_artifact=model_artifact,
        candidate_experiment_id=_payload_string(
            feature_branch_payload,
            "candidate_experiment_id",
        ),
        candidate_parameters=_payload_dict(feature_branch_payload, "candidate_parameters"),
        threshold_pairs=threshold_pairs,
        threshold_derivation=_threshold_derivation_payload(
            probability_evidence=probability_evidence,
            threshold_pairs=threshold_pairs,
            cap=config.threshold_pair_cap,
        ),
        artifact_verification=artifact_verification,
        slice_count=len(config.slices),
        completed_slice_count=0 if robustness is None else robustness.completed_slice_count,
        local_paper_verification=local_paper_verification,
        robustness=robustness,
        metrics=_feature_branch_replay_metrics(
            threshold_pairs=threshold_pairs,
            probability_evidence=probability_evidence,
            local_paper_verification=local_paper_verification,
            robustness=robustness,
        ),
    )
    replay_artifact.write_text(
        json.dumps(
            _candidate_feature_branch_replay_payload(result, artifact_root),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return result


def run_bounded_candidate_feature_branch_replay_opportunity_attribution(
    *,
    config: CandidateFeatureBranchReplayAttributionConfig | None = None,
    artifact_root: Path,
    repo_root: Path | None = None,
    feature_branch_replay_artifact: Path | None = None,
) -> BoundedCandidateFeatureBranchReplayAttributionResult:
    config = config or CandidateFeatureBranchReplayAttributionConfig()
    _reject_repo_artifact_path(artifact_root, repo_root)
    output_dir = (
        artifact_root / "candidate-feature-branch-replay-attribution" / config.run_id
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    attribution_artifact = output_dir / "metrics.json"

    resolved_replay_artifact = _resolve_optional_path(
        feature_branch_replay_artifact,
        artifact_root,
    )
    if resolved_replay_artifact is not None:
        _reject_repo_artifact_path(resolved_replay_artifact, repo_root)
    replay_payload, replay_error = _read_json_artifact(
        resolved_replay_artifact,
        required_label="candidate feature branch replay artifact",
    )
    resolved_robustness_artifact = _resolve_optional_path(
        _payload_dict(replay_payload, "artifacts").get("candidate_threshold_robustness"),
        artifact_root,
    )
    if resolved_robustness_artifact is not None:
        _reject_repo_artifact_path(resolved_robustness_artifact, repo_root)
    robustness_payload, robustness_error = _read_json_artifact(
        resolved_robustness_artifact,
        required_label="candidate threshold robustness artifact",
    )
    slices = _attribution_slices(robustness_payload, artifact_root)
    threshold_pairs = _feature_branch_attribution_threshold_pairs(replay_payload)
    artifact_verification = _feature_branch_attribution_artifact_verification(
        replay_artifact=resolved_replay_artifact,
        robustness_artifact=resolved_robustness_artifact,
        slices=slices,
    )
    errors = tuple(
        error
        for error in (
            replay_error,
            _status_error(
                replay_payload,
                expected="candidate_feature_branch_replayed_only",
                label="candidate feature branch replay",
            ),
            robustness_error,
            _status_error(
                robustness_payload,
                expected="candidate_robustness_replayed_only",
                label="candidate threshold robustness",
            ),
            None if threshold_pairs else "feature branch replay threshold pairs are missing",
            _feature_branch_attribution_artifact_error(artifact_verification),
            _attribution_slice_error(slices),
        )
        if error is not None
    )
    status: CandidateFeatureBranchReplayAttributionStatus = (
        "candidate_feature_branch_replay_attribution_only"
        if not errors
        else "prepared_not_feature_branch_replay_attributed"
    )
    local_paper_verification = _local_paper_verification_from_attribution_slices(
        slices,
        artifact_root,
    )
    result = BoundedCandidateFeatureBranchReplayAttributionResult(
        run_id=config.run_id,
        status=status,
        checked_at=datetime.now(UTC),
        reason=(
            "bounded feature-branch replay opportunity attribution completed"
            if status == "candidate_feature_branch_replay_attribution_only"
            else "; ".join(errors)
        ),
        source_feature_branch_replay_artifact=resolved_replay_artifact,
        source_robustness_artifact=resolved_robustness_artifact,
        attribution_artifact=attribution_artifact,
        candidate_experiment_id=_payload_string(
            replay_payload,
            "candidate_experiment_id",
        ),
        candidate_parameters=_payload_dict(replay_payload, "candidate_parameters"),
        threshold_pairs=threshold_pairs,
        threshold_derivation=_payload_dict(replay_payload, "threshold_derivation"),
        artifact_verification=artifact_verification,
        local_paper_verification=local_paper_verification,
        slices=slices,
        metrics=_feature_branch_attribution_metrics(
            status=status,
            threshold_pairs=threshold_pairs,
            artifact_verification=artifact_verification,
            local_paper_verification=local_paper_verification,
            slices=slices,
        ),
    )
    attribution_artifact.write_text(
        json.dumps(
            _candidate_feature_branch_replay_attribution_payload(result, artifact_root),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return result


def derive_feature_branch_replay_threshold_pairs(
    probability_evidence: dict[str, Any],
    *,
    cap: int = MAX_FEATURE_BRANCH_REPLAY_THRESHOLD_PAIRS,
) -> tuple[tuple[float, float], ...]:
    if cap <= 0:
        return ()
    observed_max = _decimal_metric(probability_evidence.get("max_probability"))
    observed_mean = _decimal_metric(probability_evidence.get("mean_probability"))
    if observed_max is None or observed_mean is None:
        return ()
    buy_ceiling = _bounded_buy_ceiling(observed_max)
    sell_threshold = _floor_threshold(observed_mean)
    pairs: list[tuple[float, float]] = []
    buy = buy_ceiling - (THRESHOLD_STEP * Decimal(cap - 1))
    while buy <= buy_ceiling and len(pairs) < cap:
        pair = (_rounded_threshold(buy), _rounded_threshold(sell_threshold))
        if 0 < pair[1] < pair[0] < 1:
            pairs.append(pair)
        buy += THRESHOLD_STEP
    return tuple(pairs)


def _candidate_feature_branch_replay_attribution_payload(
    result: BoundedCandidateFeatureBranchReplayAttributionResult,
    artifact_root: Path,
) -> dict[str, Any]:
    return to_jsonable(
        {
            "schema_version": result.schema_version,
            "run_id": result.run_id,
            "status": result.status,
            "checked_at": result.checked_at,
            "reason": result.reason,
            "source_feature_branch_replay_artifact": None
            if result.source_feature_branch_replay_artifact is None
            else str(result.source_feature_branch_replay_artifact),
            "source_robustness_artifact": None
            if result.source_robustness_artifact is None
            else str(result.source_robustness_artifact),
            "candidate_experiment_id": result.candidate_experiment_id,
            "candidate_parameters": result.candidate_parameters,
            "threshold_pairs": [
                {
                    "buy_threshold": f"{buy_threshold:.6f}",
                    "sell_threshold": f"{sell_threshold:.6f}",
                }
                for buy_threshold, sell_threshold in result.threshold_pairs
            ],
            "threshold_derivation": result.threshold_derivation,
            "artifact_verification": result.artifact_verification,
            "local_paper_verification": result.local_paper_verification,
            "slices": result.slices,
            "metrics": result.metrics,
            "result_scope": {
                "mode": "research_feature_branch_replay_opportunity_attribution_only",
                "descriptive_only": True,
                "promotion_gate": False,
            },
            "artifacts": {
                "candidate_feature_branch_replay_attribution": str(
                    result.attribution_artifact
                ),
            },
            "artifact_policy": {
                "root": str(artifact_root),
                "repo_storage_allowed": False,
            },
        }
    )


def _candidate_feature_branch_replay_payload(
    result: BoundedCandidateFeatureBranchReplayResult,
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
            "source_feature_branch_artifact": None
            if result.source_feature_branch_artifact is None
            else str(result.source_feature_branch_artifact),
            "candidate_experiment_id": result.candidate_experiment_id,
            "candidate_parameters": result.candidate_parameters,
            "training_metrics_artifact": None
            if result.training_metrics_artifact is None
            else str(result.training_metrics_artifact),
            "evaluation_artifact": None
            if result.evaluation_artifact is None
            else str(result.evaluation_artifact),
            "model_artifact": None if result.model_artifact is None else str(result.model_artifact),
            "threshold_pairs": [
                {
                    "buy_threshold": f"{buy_threshold:.6f}",
                    "sell_threshold": f"{sell_threshold:.6f}",
                }
                for buy_threshold, sell_threshold in result.threshold_pairs
            ],
            "threshold_derivation": result.threshold_derivation,
            "artifact_verification": result.artifact_verification,
            "slice_count": result.slice_count,
            "completed_slice_count": result.completed_slice_count,
            "local_paper_verification": result.local_paper_verification,
            "metrics": result.metrics,
            "result_scope": {
                "mode": "research_feature_branch_replay_only",
                "descriptive_only": True,
                "promotion_gate": False,
            },
            "artifacts": {
                "candidate_feature_branch_replay": str(result.feature_branch_replay_artifact),
                "candidate_threshold_robustness": None
                if result.robustness is None
                else str(result.robustness.robustness_artifact),
            },
            "artifact_policy": {
                "root": str(artifact_root),
                "repo_storage_allowed": False,
            },
        }
    )


def _resolved_artifact(
    artifacts: dict[str, Any],
    key: str,
    artifact_root: Path,
) -> Path | None:
    return _resolve_optional_path(artifacts.get(key), artifact_root)


def _artifact_verification(
    *,
    feature_branch_artifact: Path | None,
    training_artifact: Path | None,
    evaluation_artifact: Path | None,
    model_artifact: Path | None,
    slices: tuple[CandidateThresholdRobustnessSliceConfig, ...],
) -> dict[str, Any]:
    return {
        "feature_branch_artifact_exists": feature_branch_artifact is not None
        and feature_branch_artifact.exists(),
        "training_artifact_exists": training_artifact is not None
        and training_artifact.exists(),
        "evaluation_artifact_exists": evaluation_artifact is not None
        and evaluation_artifact.exists(),
        "model_artifact_exists": model_artifact is not None and model_artifact.exists(),
        "slice_count": len(slices),
        "network_required": False,
        "credential_required": False,
    }


def _artifact_error(verification: dict[str, Any]) -> str | None:
    missing = [
        key
        for key in (
            "feature_branch_artifact_exists",
            "training_artifact_exists",
            "evaluation_artifact_exists",
            "model_artifact_exists",
        )
        if verification.get(key) is not True
    ]
    if not missing:
        return None
    return f"feature branch replay artifacts unavailable: {', '.join(missing)}"


def _status_error(payload: dict[str, Any], *, expected: str, label: str) -> str | None:
    if not payload:
        return None
    actual = payload.get("status")
    if actual == expected:
        return None
    return f"{label} status is {actual!r}, expected {expected!r}"


def _threshold_derivation_payload(
    *,
    probability_evidence: dict[str, Any],
    threshold_pairs: tuple[tuple[float, float], ...],
    cap: int,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "mode": "feature_branch_probability_range_probe",
        "source_probability_evidence": probability_evidence,
        "threshold_pair_cap": cap,
        "threshold_pair_count": len(threshold_pairs),
        "threshold_pairs": [
            {
                "buy_threshold": f"{buy_threshold:.6f}",
                "sell_threshold": f"{sell_threshold:.6f}",
            }
            for buy_threshold, sell_threshold in threshold_pairs
        ],
        "descriptive_only": True,
        "promotion_gate": False,
    }
    saturation_guard = _saturation_guard_payload(probability_evidence)
    if saturation_guard is not None:
        payload["saturation_guard"] = saturation_guard
    return payload


def _feature_branch_replay_metrics(
    *,
    threshold_pairs: tuple[tuple[float, float], ...],
    probability_evidence: dict[str, Any],
    local_paper_verification: dict[str, Any],
    robustness: BoundedCandidateThresholdRobustnessResult | None,
) -> dict[str, Any]:
    robustness_metrics = {} if robustness is None else robustness.metrics
    return {
        "research_feature_branch_replay_only": True,
        "threshold_pair_count": len(threshold_pairs),
        "source_probability_evidence": probability_evidence,
        "completed_slice_count": 0 if robustness is None else robustness.completed_slice_count,
        "completed_variant_count": robustness_metrics.get("completed_variant_count", 0),
        "replay_fill_count_total": robustness_metrics.get("replay_fill_count_total", 0),
        "pnl_min": robustness_metrics.get("pnl_min"),
        "pnl_max": robustness_metrics.get("pnl_max"),
        "max_drawdown_max": robustness_metrics.get("max_drawdown_max"),
        "local_paper_verification": local_paper_verification,
        "all_fills_local_paper": local_paper_verification.get("all_fills_local_paper")
        is True,
        "descriptive_only": True,
        "promotion_gate": False,
    }


def _feature_branch_attribution_threshold_pairs(
    replay_payload: dict[str, Any],
) -> tuple[tuple[float, float], ...]:
    return _attribution_threshold_pairs_from_payload(
        replay_payload,
    ) or _attribution_threshold_pairs_from_payload(
        _payload_dict(replay_payload, "threshold_derivation")
    )


def _feature_branch_attribution_artifact_verification(
    *,
    replay_artifact: Path | None,
    robustness_artifact: Path | None,
    slices: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    return {
        "feature_branch_replay": _attribution_artifact_payload(replay_artifact),
        "robustness": _attribution_artifact_payload(robustness_artifact),
        "trace_artifacts": {
            str(slice_payload.get("slice_id")): _attribution_artifact_payload(
                None
                if slice_payload.get("probability_trace_artifact") is None
                else Path(str(slice_payload["probability_trace_artifact"]))
            )
            for slice_payload in slices
        },
        "network_required": False,
        "credential_required": False,
    }


def _feature_branch_attribution_artifact_error(
    artifact_verification: dict[str, Any],
) -> str | None:
    if _all_attribution_artifacts_exist(artifact_verification):
        return None
    return "referenced feature-branch replay attribution artifacts are missing"


def _feature_branch_attribution_metrics(
    *,
    status: CandidateFeatureBranchReplayAttributionStatus,
    threshold_pairs: tuple[tuple[float, float], ...],
    artifact_verification: dict[str, Any],
    local_paper_verification: dict[str, Any],
    slices: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    variants = tuple(
        variant
        for slice_payload in slices
        for variant in _attribution_payload_list(slice_payload, "variants")
    )
    return {
        "status": status,
        "research_feature_branch_replay_opportunity_attribution_only": True,
        "comparison_is_descriptive": True,
        "descriptive_only": True,
        "promotion_gate": False,
        "all_referenced_artifacts_exist": _all_attribution_artifacts_exist(
            artifact_verification
        ),
        "threshold_pair_count": len(threshold_pairs),
        "slice_count": len(slices),
        "attributed_slice_count": sum(
            1
            for slice_payload in slices
            if slice_payload.get("status") == "slice_threshold_attributed_only"
        ),
        "attributed_variant_count": len(variants),
        "zero_fill_variant_count": sum(
            1
            for variant in variants
            if (_attribution_int_metric(variant.get("replay_fill_count")) or 0) == 0
        ),
        "buy_opportunity_count_total": sum(
            _attribution_int_metric(variant.get("buy_opportunity_count")) or 0
            for variant in variants
        ),
        "sell_opportunity_count_total": sum(
            _attribution_int_metric(variant.get("sell_opportunity_count")) or 0
            for variant in variants
        ),
        "replay_fill_count_total": sum(
            _attribution_int_metric(variant.get("replay_fill_count")) or 0
            for variant in variants
        ),
        "local_paper_verification": local_paper_verification,
        "local_paper_fill_count": local_paper_verification.get(
            "local_paper_fill_count"
        ),
        "non_local_fill_source_counts": local_paper_verification.get(
            "non_local_fill_source_counts"
        ),
        "missing_zero_fill_event_artifacts": local_paper_verification.get(
            "missing_zero_fill_event_artifacts"
        ),
        "all_fills_local_paper": local_paper_verification.get("all_fills_local_paper")
        is True,
    }


def _local_paper_verification(
    robustness: BoundedCandidateThresholdRobustnessResult | None,
) -> dict[str, Any]:
    return collect_fill_source_evidence(
        _fill_event_artifacts_from_robustness(robustness)
    ).to_summary()


def _fill_event_artifacts_from_robustness(
    robustness: BoundedCandidateThresholdRobustnessResult | None,
) -> tuple[FillEventArtifact, ...]:
    if robustness is None:
        return ()
    artifacts: list[FillEventArtifact] = []
    for slice_result in robustness.slices:
        for variant in slice_result.variants:
            artifacts.append(
                FillEventArtifact(
                    path=None
                    if variant.events_artifact is None
                    else Path(variant.events_artifact),
                    expected_fill_count=variant.replay_fill_count,
                    label=f"{slice_result.slice_id}:{variant.variant_id}",
                )
            )
    return tuple(artifacts)


def _local_paper_verification_from_attribution_slices(
    slices: tuple[dict[str, Any], ...],
    artifact_root: Path,
) -> dict[str, Any]:
    return collect_fill_source_evidence(
        _fill_event_artifacts_from_attribution_slices(slices, artifact_root)
    ).to_summary()


def _fill_event_artifacts_from_attribution_slices(
    slices: tuple[dict[str, Any], ...],
    artifact_root: Path,
) -> tuple[FillEventArtifact, ...]:
    artifacts: list[FillEventArtifact] = []
    for slice_payload in slices:
        slice_id = str(slice_payload.get("slice_id") or "")
        for variant in _attribution_payload_list(slice_payload, "variants"):
            variant_id = str(variant.get("variant_id") or "")
            expected_fill_count = (
                _attribution_int_metric(variant.get("replay_fill_count")) or 0
            )
            artifacts.append(
                FillEventArtifact(
                    path=_resolve_optional_path(variant.get("events_artifact"), artifact_root),
                    expected_fill_count=expected_fill_count,
                    label=f"{slice_id}:{variant_id}",
                )
            )
    return tuple(artifacts)


def _decimal_metric(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _floor_threshold(value: Decimal) -> Decimal:
    return value.quantize(THRESHOLD_STEP, rounding=ROUND_FLOOR)


def _bounded_buy_ceiling(value: Decimal) -> Decimal:
    return min(_floor_threshold(value), MAX_FEATURE_BRANCH_REPLAY_BUY_THRESHOLD)


def _saturation_guard_payload(probability_evidence: dict[str, Any]) -> dict[str, Any] | None:
    observed_max = _decimal_metric(probability_evidence.get("max_probability"))
    if observed_max is None:
        return None
    raw_buy_ceiling = _floor_threshold(observed_max)
    bounded_buy_ceiling = min(
        raw_buy_ceiling,
        MAX_FEATURE_BRANCH_REPLAY_BUY_THRESHOLD,
    )
    if bounded_buy_ceiling == raw_buy_ceiling:
        return None
    return {
        "mode": "max_buy_ceiling_clamped_below_one",
        "raw_buy_ceiling": f"{raw_buy_ceiling:.6f}",
        "bounded_buy_ceiling": f"{bounded_buy_ceiling:.6f}",
        "threshold_step": f"{THRESHOLD_STEP:.6f}",
        "reason": "max_probability floors to an invalid buy threshold under pair[0] < 1",
        "descriptive_only": True,
        "promotion_gate": False,
    }


def _rounded_threshold(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.000001")))
