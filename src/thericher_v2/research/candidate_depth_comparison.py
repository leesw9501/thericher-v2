"""Descriptive comparison between breadth holdout and depth target evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.serialization import to_jsonable

from .candidate_training import _reject_repo_artifact_path

CandidateDepthComparisonStatus = Literal[
    "candidate_depth_compared_only",
    "prepared_not_depth_compared",
]
DEFAULT_CANDIDATE_DEPTH_COMPARISON_RUN_ID = "bounded-candidate-depth-comparison"
APP_MODEL_ARTIFACT_ROOT = PurePosixPath("/app/model_artifacts")


@dataclass(frozen=True)
class CandidateDepthComparisonConfig:
    run_id: str = DEFAULT_CANDIDATE_DEPTH_COMPARISON_RUN_ID
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("run_id is required")


@dataclass(frozen=True)
class BoundedCandidateDepthComparisonResult:
    run_id: str
    status: CandidateDepthComparisonStatus
    checked_at: datetime
    reason: str
    source_depth_target_artifact: Path | None
    source_breadth_holdout_artifact: Path | None
    comparison_artifact: Path
    candidate_experiment_id: str | None
    candidate_parameters: dict[str, Any]
    selected_variant_id: str | None
    selected_variant_count: int
    input_variant_count: int
    artifact_verification: dict[str, Any]
    breadth_evidence: dict[str, Any]
    depth_evidence: dict[str, Any]
    deltas: dict[str, Any]
    metrics: dict[str, Any]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_at", self.checked_at.astimezone(UTC))


def run_bounded_candidate_depth_comparison(
    *,
    config: CandidateDepthComparisonConfig | None = None,
    artifact_root: Path,
    repo_root: Path | None = None,
    depth_target_artifact: Path | None = None,
    breadth_holdout_artifact: Path | None = None,
) -> BoundedCandidateDepthComparisonResult:
    config = config or CandidateDepthComparisonConfig()
    _reject_repo_artifact_path(artifact_root, repo_root)
    output_dir = artifact_root / "candidate-depth-comparison" / config.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    comparison_artifact = output_dir / "metrics.json"

    resolved_depth_artifact = _resolve_optional_path(depth_target_artifact, artifact_root)
    if resolved_depth_artifact is not None:
        _reject_repo_artifact_path(resolved_depth_artifact, repo_root)
    depth_payload, depth_error = _read_json_artifact(
        resolved_depth_artifact,
        required_label="candidate depth target artifact",
    )
    selected_variant_id = _selected_variant_id(depth_payload)
    breadth_artifact_value = breadth_holdout_artifact or depth_payload.get(
        "source_breadth_holdout_artifact"
    )
    resolved_breadth_artifact = _resolve_optional_path(
        breadth_artifact_value,
        artifact_root,
    )
    if resolved_breadth_artifact is not None:
        _reject_repo_artifact_path(resolved_breadth_artifact, repo_root)
    breadth_payload, breadth_error = _read_json_artifact(
        resolved_breadth_artifact,
        required_label="candidate breadth holdout artifact",
    )
    raw_variants = _payload_list(breadth_payload, "variants")
    selected_breadth = _find_variant(raw_variants, selected_variant_id)

    artifact_verification = _artifact_verification(
        depth_payload=depth_payload,
        breadth_variant=selected_breadth,
        artifact_root=artifact_root,
    )
    source_payloads = _read_source_payloads(artifact_verification)
    breadth_evidence = _breadth_evidence(selected_breadth, breadth_payload, source_payloads)
    depth_evidence = _depth_evidence(depth_payload, source_payloads)
    deltas = _evidence_deltas(breadth_evidence, depth_evidence)
    errors = tuple(
        error
        for error in (
            depth_error,
            _status_error(
                depth_payload,
                expected="candidate_depth_target_ran_only",
                label="candidate depth target",
            ),
            breadth_error,
            _status_error(
                breadth_payload,
                expected="candidate_breadth_holdout_replayed_only",
                label="candidate breadth holdout",
            ),
            None if selected_variant_id else "depth target selected variant is missing",
            None
            if selected_breadth is not None
            else f"selected variant is missing from breadth holdout: {selected_variant_id}",
            _artifact_error(artifact_verification),
            _source_payload_error(source_payloads),
        )
        if error is not None
    )
    status: CandidateDepthComparisonStatus = (
        "candidate_depth_compared_only"
        if not errors
        else "prepared_not_depth_compared"
    )
    result = BoundedCandidateDepthComparisonResult(
        run_id=config.run_id,
        status=status,
        checked_at=datetime.now(UTC),
        reason=(
            "bounded depth-vs-breadth evidence comparison completed"
            if status == "candidate_depth_compared_only"
            else "; ".join(errors)
        ),
        source_depth_target_artifact=resolved_depth_artifact,
        source_breadth_holdout_artifact=resolved_breadth_artifact,
        comparison_artifact=comparison_artifact,
        candidate_experiment_id=_payload_string(depth_payload, "candidate_experiment_id"),
        candidate_parameters=_payload_dict(depth_payload, "candidate_parameters"),
        selected_variant_id=selected_variant_id,
        selected_variant_count=1 if selected_variant_id and selected_breadth is not None else 0,
        input_variant_count=len(raw_variants),
        artifact_verification=artifact_verification,
        breadth_evidence=breadth_evidence,
        depth_evidence=depth_evidence,
        deltas=deltas,
        metrics=_comparison_metrics(
            status=status,
            artifact_verification=artifact_verification,
            breadth_evidence=breadth_evidence,
            depth_evidence=depth_evidence,
            deltas=deltas,
        ),
    )
    comparison_artifact.write_text(
        json.dumps(
            _candidate_depth_comparison_payload(result, artifact_root),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return result


def _candidate_depth_comparison_payload(
    result: BoundedCandidateDepthComparisonResult,
    artifact_root: Path,
) -> dict[str, Any]:
    return to_jsonable(
        {
            "schema_version": result.schema_version,
            "run_id": result.run_id,
            "status": result.status,
            "checked_at": result.checked_at,
            "reason": result.reason,
            "source_depth_target_artifact": None
            if result.source_depth_target_artifact is None
            else str(result.source_depth_target_artifact),
            "source_breadth_holdout_artifact": None
            if result.source_breadth_holdout_artifact is None
            else str(result.source_breadth_holdout_artifact),
            "candidate_experiment_id": result.candidate_experiment_id,
            "candidate_parameters": result.candidate_parameters,
            "selected_variant_id": result.selected_variant_id,
            "selected_variant_count": result.selected_variant_count,
            "input_variant_count": result.input_variant_count,
            "selection": {
                "mode": "research_comparison_only",
                "selected_variant_id": result.selected_variant_id,
                "selected_variant_count": result.selected_variant_count,
                "winner": None,
                "recommendation": None,
                "promotion_gate": False,
            },
            "artifact_verification": result.artifact_verification,
            "breadth_evidence": result.breadth_evidence,
            "depth_evidence": result.depth_evidence,
            "deltas": result.deltas,
            "metrics": result.metrics,
            "artifacts": {
                "candidate_depth_comparison": str(result.comparison_artifact),
            },
            "artifact_policy": {
                "root": str(artifact_root),
                "repo_storage_allowed": False,
            },
        }
    )


def _breadth_evidence(
    variant: dict[str, Any] | None,
    breadth_payload: dict[str, Any],
    source_payloads: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    metrics = _payload_dict(variant or {}, "metrics")
    training = source_payloads.get("breadth_training_metrics", {})
    calibration = source_payloads.get("breadth_calibration", {})
    return {
        "variant_id": _payload_string(variant or {}, "variant_id"),
        "status": _payload_string(variant or {}, "status"),
        "training_status": _payload_string(training, "status"),
        "holdout_status": metrics.get("holdout_status"),
        "selected_backend": _payload_string(training, "selected_backend"),
        "max_bars": _payload_int(breadth_payload, "max_bars"),
        "max_epochs": _payload_int(training, "max_epochs"),
        "max_steps": _payload_int(training, "max_steps"),
        "bars_seen": _payload_int(training, "bars_seen"),
        "examples_seen": _payload_int(training, "examples_seen"),
        "source_slices": _payload_list(training, "source_slices"),
        "probability_summary": {
            "source": _payload_dict(calibration, "probability_summary"),
            "holdout": _payload_dict(metrics, "probability_summary"),
        },
        "local_paper_verification": _payload_dict(metrics, "local_paper_verification"),
        "local_paper_fill_count": _local_paper_fill_count(metrics),
        "pnl_min": metrics.get("pnl_min"),
        "pnl_max": metrics.get("pnl_max"),
        "max_drawdown_max": metrics.get("max_drawdown_max"),
    }


def _depth_evidence(
    payload: dict[str, Any],
    source_payloads: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    metrics = _payload_dict(payload, "metrics")
    training = source_payloads.get("depth_training_metrics", {})
    return {
        "variant_id": _selected_variant_id(payload),
        "status": _payload_string(payload, "status"),
        "training_status": metrics.get("training_status"),
        "holdout_status": metrics.get("holdout_status"),
        "selected_backend": metrics.get("selected_backend"),
        "max_bars": _payload_int(payload, "max_bars"),
        "max_epochs": _payload_int(payload, "max_epochs"),
        "max_steps": _payload_int(payload, "max_steps"),
        "bars_seen": metrics.get("bars_seen"),
        "examples_seen": metrics.get("examples_seen"),
        "source_slices": _payload_list(training, "source_slices"),
        "probability_summary": _payload_dict(metrics, "probability_summary"),
        "local_paper_verification": _payload_dict(metrics, "local_paper_verification"),
        "local_paper_fill_count": _local_paper_fill_count(metrics),
        "pnl_min": metrics.get("pnl_min"),
        "pnl_max": metrics.get("pnl_max"),
        "max_drawdown_max": metrics.get("max_drawdown_max"),
    }


def _evidence_deltas(
    breadth: dict[str, Any],
    depth: dict[str, Any],
) -> dict[str, Any]:
    return {
        "mode": "research_comparison_only",
        "local_paper_fill_count": _number_delta(
            breadth.get("local_paper_fill_count"),
            depth.get("local_paper_fill_count"),
        ),
        "pnl_min": _decimal_delta(breadth.get("pnl_min"), depth.get("pnl_min")),
        "pnl_max": _decimal_delta(breadth.get("pnl_max"), depth.get("pnl_max")),
        "max_drawdown_max": _decimal_delta(
            breadth.get("max_drawdown_max"),
            depth.get("max_drawdown_max"),
        ),
        "bars_seen": _number_delta(breadth.get("bars_seen"), depth.get("bars_seen")),
        "examples_seen": _number_delta(
            breadth.get("examples_seen"),
            depth.get("examples_seen"),
        ),
        "max_bars": _number_delta(breadth.get("max_bars"), depth.get("max_bars")),
        "max_epochs": _number_delta(breadth.get("max_epochs"), depth.get("max_epochs")),
        "max_steps": _number_delta(breadth.get("max_steps"), depth.get("max_steps")),
        "source_probability": _probability_delta(
            _nested_dict(breadth, "probability_summary", "source"),
            _nested_dict(depth, "probability_summary", "source"),
        ),
        "holdout_probability": _probability_delta(
            _nested_dict(breadth, "probability_summary", "holdout"),
            _nested_dict(depth, "probability_summary", "holdout"),
        ),
        "promotion_gate": False,
    }


def _artifact_verification(
    *,
    depth_payload: dict[str, Any],
    breadth_variant: dict[str, Any] | None,
    artifact_root: Path,
) -> dict[str, Any]:
    depth_artifacts = _payload_dict(depth_payload, "artifacts")
    source_verification = _payload_dict(
        _payload_dict(depth_payload, "metrics"),
        "source_verification",
    )
    paths = {
        "breadth_training_metrics": source_verification.get("source_training_metrics_artifact")
        or (breadth_variant or {}).get("training_metrics_artifact"),
        "breadth_evaluation": source_verification.get("source_evaluation_artifact")
        or (breadth_variant or {}).get("evaluation_artifact"),
        "breadth_model": source_verification.get("source_model_artifact")
        or (breadth_variant or {}).get("model_artifact"),
        "breadth_calibration": source_verification.get("source_calibration_artifact")
        or _nested_value(breadth_variant or {}, "calibration", "artifact"),
        "breadth_holdout": source_verification.get("source_holdout_artifact")
        or _nested_value(breadth_variant or {}, "holdout", "artifact"),
        "breadth_robustness": source_verification.get("source_robustness_artifact")
        or _nested_value(breadth_variant or {}, "holdout", "robustness_artifact"),
        "depth_training_metrics": depth_artifacts.get("training_metrics"),
        "depth_evaluation": depth_artifacts.get("evaluation"),
        "depth_model": depth_artifacts.get("model"),
        "depth_calibration": depth_artifacts.get("calibration"),
        "depth_holdout": depth_artifacts.get("holdout"),
        "depth_robustness": depth_artifacts.get("robustness"),
    }
    verified = {}
    for key, value in paths.items():
        path = _resolve_optional_path(value, artifact_root)
        verified[key] = {
            "artifact": None if path is None else str(path),
            "exists": False if path is None else path.exists(),
        }
    return verified


def _read_source_payloads(
    artifact_verification: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for key in (
        "breadth_training_metrics",
        "breadth_calibration",
        "depth_training_metrics",
    ):
        artifact = _nested_value(artifact_verification, key, "artifact")
        payload, error = _read_json_artifact(
            None if artifact is None else Path(str(artifact)),
            required_label=key,
        )
        if error is None:
            payloads[key] = payload
    return payloads


def _comparison_metrics(
    *,
    status: CandidateDepthComparisonStatus,
    artifact_verification: dict[str, Any],
    breadth_evidence: dict[str, Any],
    depth_evidence: dict[str, Any],
    deltas: dict[str, Any],
) -> dict[str, Any]:
    breadth_local = _payload_dict(breadth_evidence, "local_paper_verification").get(
        "all_fills_local_paper"
    )
    depth_local = _payload_dict(depth_evidence, "local_paper_verification").get(
        "all_fills_local_paper"
    )
    return {
        "status": status,
        "research_comparison_only": True,
        "comparison_is_descriptive": True,
        "promotion_gate": False,
        "all_referenced_artifacts_exist": _all_artifacts_exist(artifact_verification),
        "all_fills_local_paper": breadth_local is True and depth_local is True,
        "selected_variant_id": depth_evidence.get("variant_id"),
        "local_paper_fill_count_delta": deltas.get("local_paper_fill_count"),
        "pnl_min_delta": deltas.get("pnl_min"),
        "pnl_max_delta": deltas.get("pnl_max"),
        "max_drawdown_delta": deltas.get("max_drawdown_max"),
    }


def _read_json_artifact(
    path: Path | None,
    *,
    required_label: str,
) -> tuple[dict[str, Any], str | None]:
    if path is None:
        return {}, f"{required_label} is required"
    if not path.exists():
        return {}, f"{required_label} is missing: {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, f"{required_label} is unreadable: {exc}"
    if not isinstance(payload, dict):
        return {}, f"{required_label} must contain a JSON object"
    return payload, None


def _status_error(payload: dict[str, Any], *, expected: str, label: str) -> str | None:
    if not payload:
        return None
    if payload.get("status") == expected:
        return None
    reason = _payload_string(payload, "reason") or f"{label} was not completed"
    return reason


def _artifact_error(artifact_verification: dict[str, Any]) -> str | None:
    missing = tuple(
        key
        for key, value in artifact_verification.items()
        if not _verification_exists(value)
    )
    if not missing:
        return None
    return "referenced comparison artifacts are missing: " + ", ".join(missing)


def _source_payload_error(source_payloads: dict[str, dict[str, Any]]) -> str | None:
    required = ("breadth_training_metrics", "breadth_calibration", "depth_training_metrics")
    missing = tuple(key for key in required if key not in source_payloads)
    if not missing:
        return None
    return "referenced comparison artifacts are unreadable: " + ", ".join(missing)


def _selected_variant_id(payload: dict[str, Any]) -> str | None:
    selection = _payload_dict(payload, "selection")
    return _payload_string(selection, "selected_variant_id")


def _find_variant(
    variants: tuple[dict[str, Any], ...],
    variant_id: str | None,
) -> dict[str, Any] | None:
    if variant_id is None:
        return None
    for variant in variants:
        if _payload_string(variant, "variant_id") == variant_id:
            return variant
    return None


def _resolve_optional_path(value: Any, artifact_root: Path) -> Path | None:
    if value is None or value == "":
        return None
    raw = str(value)
    if raw.startswith(str(APP_MODEL_ARTIFACT_ROOT)):
        relative = PurePosixPath(raw).relative_to(APP_MODEL_ARTIFACT_ROOT)
        return artifact_root.joinpath(*relative.parts)
    return Path(raw)


def _probability_delta(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    return {
        "count": _number_delta(baseline.get("count"), candidate.get("count")),
        "min": _decimal_delta(baseline.get("min"), candidate.get("min")),
        "mean": _decimal_delta(baseline.get("mean"), candidate.get("mean")),
        "max": _decimal_delta(baseline.get("max"), candidate.get("max")),
    }


def _decimal_delta(baseline: Any, candidate: Any) -> str | None:
    left = _decimal_metric(baseline)
    right = _decimal_metric(candidate)
    if left is None or right is None:
        return None
    return str(right - left)


def _number_delta(baseline: Any, candidate: Any) -> int | None:
    left = _int_metric(baseline)
    right = _int_metric(candidate)
    if left is None or right is None:
        return None
    return right - left


def _local_paper_fill_count(metrics: dict[str, Any]) -> int | None:
    verification = _payload_dict(metrics, "local_paper_verification")
    local_paper_count = _int_metric(verification.get("local_paper_fill_count"))
    if local_paper_count is not None:
        return local_paper_count
    return _int_metric(metrics.get("replay_fill_count_total"))


def _decimal_metric(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _int_metric(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _payload_int(payload: dict[str, Any], key: str) -> int | None:
    return _int_metric(payload.get(key))


def _payload_string(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    return str(value)


def _payload_dict(payload: dict[str, Any] | None, key: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    value = payload.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _payload_list(payload: dict[str, Any], key: str) -> tuple[dict[str, Any], ...]:
    value = payload.get(key)
    if not isinstance(value, list | tuple):
        return ()
    return tuple(item for item in value if isinstance(item, dict))


def _nested_value(payload: dict[str, Any], first: str, second: str) -> Any:
    parent = payload.get(first)
    if not isinstance(parent, dict):
        return None
    return parent.get(second)


def _nested_dict(payload: dict[str, Any], first: str, second: str) -> dict[str, Any]:
    return _payload_dict(_payload_dict(payload, first), second)


def _all_artifacts_exist(artifact_verification: dict[str, Any]) -> bool:
    return all(_verification_exists(value) for value in artifact_verification.values())


def _verification_exists(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return bool(value.get("exists"))
