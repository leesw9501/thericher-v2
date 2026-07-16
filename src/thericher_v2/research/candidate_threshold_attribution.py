"""Artifact-only attribution for strict threshold replay outcomes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.serialization import to_jsonable

from .candidate_threshold_rerun import (
    _payload_dict,
    _payload_string,
    _read_json_artifact,
    _resolve_optional_path,
)
from .candidate_threshold_sweep import (
    _probabilities_from_trace_payload,
    _read_trace_artifact,
)
from .candidate_training import _reject_repo_artifact_path

CandidateThresholdAttributionStatus = Literal[
    "candidate_threshold_attribution_only",
    "prepared_not_threshold_attributed",
]
DEFAULT_CANDIDATE_THRESHOLD_ATTRIBUTION_RUN_ID = (
    "bounded-candidate-threshold-attribution"
)


@dataclass(frozen=True)
class CandidateThresholdAttributionConfig:
    run_id: str = DEFAULT_CANDIDATE_THRESHOLD_ATTRIBUTION_RUN_ID
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("run_id is required")


@dataclass(frozen=True)
class BoundedCandidateThresholdAttributionResult:
    run_id: str
    status: CandidateThresholdAttributionStatus
    checked_at: datetime
    reason: str
    source_threshold_rerun_artifact: Path | None
    source_robustness_artifact: Path | None
    source_calibration_artifact: Path | None
    attribution_artifact: Path
    candidate_experiment_id: str | None
    candidate_parameters: dict[str, Any]
    selected_variant_id: str | None
    artifact_verification: dict[str, Any]
    threshold_band_comparison: dict[str, Any]
    slices: tuple[dict[str, Any], ...]
    metrics: dict[str, Any]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_at", self.checked_at.astimezone(UTC))


def run_bounded_candidate_threshold_attribution(
    *,
    config: CandidateThresholdAttributionConfig | None = None,
    artifact_root: Path,
    repo_root: Path | None = None,
    threshold_rerun_artifact: Path | None = None,
) -> BoundedCandidateThresholdAttributionResult:
    config = config or CandidateThresholdAttributionConfig()
    _reject_repo_artifact_path(artifact_root, repo_root)
    output_dir = artifact_root / "candidate-threshold-attribution" / config.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    attribution_artifact = output_dir / "metrics.json"

    resolved_rerun_artifact = _resolve_optional_path(
        threshold_rerun_artifact,
        artifact_root,
    )
    if resolved_rerun_artifact is not None:
        _reject_repo_artifact_path(resolved_rerun_artifact, repo_root)
    rerun_payload, rerun_error = _read_json_artifact(
        resolved_rerun_artifact,
        required_label="candidate threshold rerun artifact",
    )
    resolved_robustness_artifact = _resolve_optional_path(
        _nested_value(rerun_payload, "artifacts", "candidate_threshold_robustness"),
        artifact_root,
    )
    if resolved_robustness_artifact is not None:
        _reject_repo_artifact_path(resolved_robustness_artifact, repo_root)
    robustness_payload, robustness_error = _read_json_artifact(
        resolved_robustness_artifact,
        required_label="candidate threshold robustness artifact",
    )
    resolved_calibration_artifact = _resolve_optional_path(
        rerun_payload.get("source_calibration_artifact"),
        artifact_root,
    )
    if resolved_calibration_artifact is not None:
        _reject_repo_artifact_path(resolved_calibration_artifact, repo_root)
    calibration_payload, calibration_error = _read_json_artifact(
        resolved_calibration_artifact,
        required_label="candidate threshold calibration artifact",
    )
    source_pairs = _threshold_pairs_from_payload(
        _payload_dict(rerun_payload, "source_thresholds")
    ) or _threshold_pairs_from_payload(_payload_dict(calibration_payload, "thresholds"))
    strict_pairs = _threshold_pairs_from_payload(
        _payload_dict(rerun_payload, "threshold_schedule")
    ) or _threshold_pairs_from_payload(rerun_payload)
    slices = _attribution_slices(robustness_payload, artifact_root)
    artifact_verification = _artifact_verification(
        rerun_artifact=resolved_rerun_artifact,
        robustness_artifact=resolved_robustness_artifact,
        calibration_artifact=resolved_calibration_artifact,
        slices=slices,
    )
    errors = tuple(
        error
        for error in (
            rerun_error,
            _status_error(
                rerun_payload,
                expected="candidate_threshold_rerun_replayed_only",
                label="candidate threshold rerun",
            ),
            robustness_error,
            _status_error(
                robustness_payload,
                expected="candidate_robustness_replayed_only",
                label="candidate threshold robustness",
            ),
            calibration_error,
            None if source_pairs else "source calibration threshold band is missing",
            None if strict_pairs else "strict rerun threshold band is missing",
            _artifact_error(artifact_verification),
            _slice_error(slices),
        )
        if error is not None
    )
    status: CandidateThresholdAttributionStatus = (
        "candidate_threshold_attribution_only"
        if not errors
        else "prepared_not_threshold_attributed"
    )
    result = BoundedCandidateThresholdAttributionResult(
        run_id=config.run_id,
        status=status,
        checked_at=datetime.now(UTC),
        reason=(
            "bounded zero-fill threshold attribution completed"
            if status == "candidate_threshold_attribution_only"
            else "; ".join(errors)
        ),
        source_threshold_rerun_artifact=resolved_rerun_artifact,
        source_robustness_artifact=resolved_robustness_artifact,
        source_calibration_artifact=resolved_calibration_artifact,
        attribution_artifact=attribution_artifact,
        candidate_experiment_id=_payload_string(
            rerun_payload,
            "candidate_experiment_id",
        ),
        candidate_parameters=_payload_dict(rerun_payload, "candidate_parameters"),
        selected_variant_id=_payload_string(rerun_payload, "selected_variant_id"),
        artifact_verification=artifact_verification,
        threshold_band_comparison=_threshold_band_comparison(
            source_pairs=source_pairs,
            strict_pairs=strict_pairs,
            slices=slices,
        ),
        slices=slices,
        metrics=_attribution_metrics(
            status=status,
            rerun_payload=rerun_payload,
            artifact_verification=artifact_verification,
            slices=slices,
        ),
    )
    attribution_artifact.write_text(
        json.dumps(
            _candidate_threshold_attribution_payload(result, artifact_root),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return result


def _candidate_threshold_attribution_payload(
    result: BoundedCandidateThresholdAttributionResult,
    artifact_root: Path,
) -> dict[str, Any]:
    return to_jsonable(
        {
            "schema_version": result.schema_version,
            "run_id": result.run_id,
            "status": result.status,
            "checked_at": result.checked_at,
            "reason": result.reason,
            "source_threshold_rerun_artifact": None
            if result.source_threshold_rerun_artifact is None
            else str(result.source_threshold_rerun_artifact),
            "source_robustness_artifact": None
            if result.source_robustness_artifact is None
            else str(result.source_robustness_artifact),
            "source_calibration_artifact": None
            if result.source_calibration_artifact is None
            else str(result.source_calibration_artifact),
            "candidate_experiment_id": result.candidate_experiment_id,
            "candidate_parameters": result.candidate_parameters,
            "selected_variant_id": result.selected_variant_id,
            "artifact_verification": result.artifact_verification,
            "threshold_band_comparison": result.threshold_band_comparison,
            "slices": result.slices,
            "metrics": result.metrics,
            "selection": {
                "mode": "research_threshold_attribution_only",
                "selected_variant_id": result.selected_variant_id,
                "winner": None,
                "recommendation": None,
                "promotion_gate": False,
            },
            "artifacts": {
                "candidate_threshold_attribution": str(result.attribution_artifact),
            },
            "artifact_policy": {
                "root": str(artifact_root),
                "repo_storage_allowed": False,
            },
        }
    )


def _attribution_slices(
    robustness_payload: dict[str, Any],
    artifact_root: Path,
) -> tuple[dict[str, Any], ...]:
    raw_slices = robustness_payload.get("slices")
    if not isinstance(raw_slices, list | tuple):
        return ()
    slices: list[dict[str, Any]] = []
    for raw_slice in raw_slices:
        if not isinstance(raw_slice, dict):
            continue
        trace_artifact = _resolve_optional_path(
            raw_slice.get("probability_trace_artifact"),
            artifact_root,
        )
        trace_payload, trace_error = _read_trace(trace_artifact)
        probabilities = (
            () if trace_error is not None else _probabilities_from_trace_payload(trace_payload)
        )
        variants = _attribution_variants(
            _payload_list(raw_slice, "variants"),
            probabilities,
        )
        slices.append(
            {
                "slice_id": _payload_string(raw_slice, "slice_id"),
                "symbol": _payload_string(raw_slice, "symbol"),
                "status": (
                    "slice_threshold_attributed_only"
                    if trace_error is None and variants
                    else "prepared_not_threshold_attributed"
                ),
                "reason": (
                    "slice threshold opportunities attributed from trace"
                    if trace_error is None and variants
                    else trace_error or "slice contains no threshold variants"
                ),
                "probability_trace_artifact": None
                if trace_artifact is None
                else str(trace_artifact),
                "probability_count": len(probabilities),
                "probability_summary": _probability_summary(probabilities),
                "variants": variants,
                "metrics": _slice_metrics(variants),
            }
        )
    return tuple(slices)


def _attribution_variants(
    variants: tuple[dict[str, Any], ...],
    probabilities: tuple[float, ...],
) -> tuple[dict[str, Any], ...]:
    attributed: list[dict[str, Any]] = []
    for variant in variants:
        buy_threshold = _float_metric(variant.get("buy_threshold"))
        sell_threshold = _float_metric(variant.get("sell_threshold"))
        if buy_threshold is None or sell_threshold is None:
            continue
        buy_opportunities = tuple(
            probability for probability in probabilities if probability >= buy_threshold
        )
        sell_opportunities = tuple(
            probability for probability in probabilities if probability <= sell_threshold
        )
        attributed.append(
            {
                "variant_id": _payload_string(variant, "variant_id"),
                "status": _payload_string(variant, "status"),
                "buy_threshold": buy_threshold,
                "sell_threshold": sell_threshold,
                "probability_count": len(probabilities),
                "buy_opportunity_count": len(buy_opportunities),
                "sell_opportunity_count": len(sell_opportunities),
                "neutral_probability_count": (
                    len(probabilities)
                    - len(buy_opportunities)
                    - len(sell_opportunities)
                ),
                "replay_fill_count": _int_metric(variant.get("replay_fill_count")),
                "trade_count": _int_metric(variant.get("trade_count")),
                "final_position": variant.get("final_position"),
                "pnl": variant.get("pnl"),
                "max_drawdown": variant.get("max_drawdown"),
                "events_artifact": variant.get("events_artifact"),
                "attribution": _variant_reason(
                    buy_threshold=buy_threshold,
                    probabilities=probabilities,
                    replay_fill_count=_int_metric(variant.get("replay_fill_count")),
                ),
                "promotion_gate": False,
            }
        )
    return tuple(attributed)


def _variant_reason(
    *,
    buy_threshold: float,
    probabilities: tuple[float, ...],
    replay_fill_count: int | None,
) -> str:
    if not probabilities:
        return "no probability trace entries available"
    if max(probabilities) < buy_threshold:
        return "buy threshold exceeded observed probability range"
    if replay_fill_count == 0:
        return "buy opportunities did not produce local-paper fills"
    return "local-paper fills are present for this threshold"


def _threshold_band_comparison(
    *,
    source_pairs: tuple[tuple[float, float], ...],
    strict_pairs: tuple[tuple[float, float], ...],
    slices: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    observed_max = _observed_probability_max(slices)
    source_buy_min, source_buy_max = _threshold_min_max(source_pairs, index=0)
    strict_buy_min, strict_buy_max = _threshold_min_max(strict_pairs, index=0)
    source_sell_min, source_sell_max = _threshold_min_max(source_pairs, index=1)
    strict_sell_min, strict_sell_max = _threshold_min_max(strict_pairs, index=1)
    return {
        "mode": "research_threshold_attribution_only",
        "source_threshold_pair_count": len(source_pairs),
        "strict_threshold_pair_count": len(strict_pairs),
        "source_buy_min": source_buy_min,
        "source_buy_max": source_buy_max,
        "strict_buy_min": strict_buy_min,
        "strict_buy_max": strict_buy_max,
        "source_sell_min": source_sell_min,
        "source_sell_max": source_sell_max,
        "strict_sell_min": strict_sell_min,
        "strict_sell_max": strict_sell_max,
        "observed_probability_max": observed_max,
        "strict_buy_min_minus_source_buy_max": _number_delta(
            source_buy_max,
            strict_buy_min,
        ),
        "strict_buy_min_above_source_buy_max": (
            None
            if source_buy_max is None or strict_buy_min is None
            else strict_buy_min > source_buy_max
        ),
        "strict_buy_min_above_observed_probability_max": (
            None
            if observed_max is None or strict_buy_min is None
            else strict_buy_min > observed_max
        ),
        "winner": None,
        "recommendation": None,
        "promotion_gate": False,
    }


def _attribution_metrics(
    *,
    status: CandidateThresholdAttributionStatus,
    rerun_payload: dict[str, Any],
    artifact_verification: dict[str, Any],
    slices: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    variants = tuple(
        variant
        for slice_payload in slices
        for variant in _payload_list(slice_payload, "variants")
    )
    local_verification = _payload_dict(
        rerun_payload,
        "local_paper_verification",
    ) or _payload_dict(_payload_dict(rerun_payload, "metrics"), "local_paper_verification")
    return {
        "status": status,
        "research_threshold_attribution_only": True,
        "comparison_is_descriptive": True,
        "promotion_gate": False,
        "all_referenced_artifacts_exist": _all_artifacts_exist(artifact_verification),
        "slice_count": len(slices),
        "attributed_slice_count": sum(
            1
            for slice_payload in slices
            if slice_payload.get("status") == "slice_threshold_attributed_only"
        ),
        "attributed_variant_count": len(variants),
        "buy_opportunity_count_total": sum(
            _int_metric(variant.get("buy_opportunity_count")) or 0
            for variant in variants
        ),
        "sell_opportunity_count_total": sum(
            _int_metric(variant.get("sell_opportunity_count")) or 0
            for variant in variants
        ),
        "replay_fill_count_total": sum(
            _int_metric(variant.get("replay_fill_count")) or 0
            for variant in variants
        ),
        "local_paper_verification": local_verification,
        "all_fills_local_paper": local_verification.get("all_fills_local_paper")
        is True,
    }


def _artifact_verification(
    *,
    rerun_artifact: Path | None,
    robustness_artifact: Path | None,
    calibration_artifact: Path | None,
    slices: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    return {
        "threshold_rerun": _artifact_payload(rerun_artifact),
        "robustness": _artifact_payload(robustness_artifact),
        "source_calibration": _artifact_payload(calibration_artifact),
        "trace_artifacts": {
            str(slice_payload.get("slice_id")): _artifact_payload(
                None
                if slice_payload.get("probability_trace_artifact") is None
                else Path(str(slice_payload["probability_trace_artifact"]))
            )
            for slice_payload in slices
        },
    }


def _artifact_payload(path: Path | None) -> dict[str, Any]:
    return {
        "artifact": None if path is None else str(path),
        "exists": False if path is None else path.exists(),
    }


def _artifact_error(artifact_verification: dict[str, Any]) -> str | None:
    missing = tuple(_missing_artifact_keys(artifact_verification))
    if not missing:
        return None
    return "referenced threshold attribution artifacts are missing: " + ", ".join(
        missing
    )


def _missing_artifact_keys(payload: dict[str, Any], prefix: str = "") -> tuple[str, ...]:
    missing: list[str] = []
    for key, value in payload.items():
        label = f"{prefix}.{key}" if prefix else str(key)
        if _is_artifact_payload(value):
            if not value.get("exists"):
                missing.append(label)
            continue
        if isinstance(value, dict):
            missing.extend(_missing_artifact_keys(value, label))
    return tuple(missing)


def _is_artifact_payload(value: Any) -> bool:
    return isinstance(value, dict) and "exists" in value and "artifact" in value


def _all_artifacts_exist(artifact_verification: dict[str, Any]) -> bool:
    return not _missing_artifact_keys(artifact_verification)


def _slice_error(slices: tuple[dict[str, Any], ...]) -> str | None:
    if not slices:
        return "no threshold attribution slices found"
    prepared = tuple(
        str(slice_payload.get("slice_id"))
        for slice_payload in slices
        if slice_payload.get("status") != "slice_threshold_attributed_only"
    )
    if not prepared:
        return None
    return "threshold attribution slices are incomplete: " + ", ".join(prepared)


def _read_trace(path: Path | None) -> tuple[dict[str, Any], str | None]:
    if path is None:
        return {}, "probability trace artifact is required"
    payload, error = _read_trace_artifact(path)
    if error is not None:
        return payload, error
    if payload.get("status") != "probability_traced_only":
        return payload, _payload_string(payload, "reason") or "trace was not completed"
    return payload, None


def _threshold_pairs_from_payload(
    payload: dict[str, Any],
) -> tuple[tuple[float, float], ...]:
    raw_pairs = payload.get("threshold_pairs")
    if not isinstance(raw_pairs, list):
        return ()
    pairs: list[tuple[float, float]] = []
    for raw_pair in raw_pairs:
        if not isinstance(raw_pair, dict):
            continue
        buy = _float_metric(raw_pair.get("buy_threshold"))
        sell = _float_metric(raw_pair.get("sell_threshold"))
        if buy is None or sell is None or not 0 < sell < buy < 1:
            continue
        pairs.append((buy, sell))
    return tuple(pairs)


def _probability_summary(probabilities: tuple[float, ...]) -> dict[str, Any]:
    if not probabilities:
        return {"count": 0}
    ordered = tuple(sorted(probabilities))
    return {
        "count": len(ordered),
        "min": f"{ordered[0]:.6f}",
        "max": f"{ordered[-1]:.6f}",
        "mean": f"{sum(ordered) / len(ordered):.6f}",
    }


def _slice_metrics(variants: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    return {
        "variant_count": len(variants),
        "buy_opportunity_count_total": sum(
            _int_metric(variant.get("buy_opportunity_count")) or 0
            for variant in variants
        ),
        "sell_opportunity_count_total": sum(
            _int_metric(variant.get("sell_opportunity_count")) or 0
            for variant in variants
        ),
        "replay_fill_count_total": sum(
            _int_metric(variant.get("replay_fill_count")) or 0
            for variant in variants
        ),
        "comparison_is_descriptive": True,
        "promotion_gate": False,
    }


def _status_error(payload: dict[str, Any], *, expected: str, label: str) -> str | None:
    if not payload:
        return None
    if payload.get("status") == expected:
        return None
    return _payload_string(payload, "reason") or f"{label} was not completed"


def _observed_probability_max(slices: tuple[dict[str, Any], ...]) -> float | None:
    values = tuple(
        _float_metric(_payload_dict(slice_payload, "probability_summary").get("max"))
        for slice_payload in slices
    )
    clean = tuple(value for value in values if value is not None)
    return None if not clean else max(clean)


def _threshold_min_max(
    pairs: tuple[tuple[float, float], ...],
    *,
    index: int,
) -> tuple[float | None, float | None]:
    values = tuple(pair[index] for pair in pairs)
    if not values:
        return None, None
    return min(values), max(values)


def _number_delta(left: float | None, right: float | None) -> str | None:
    if left is None or right is None:
        return None
    return str(Decimal(str(right)) - Decimal(str(left)))


def _nested_value(payload: dict[str, Any], first: str, second: str) -> Any:
    parent = payload.get(first)
    if not isinstance(parent, dict):
        return None
    return parent.get(second)


def _payload_list(payload: dict[str, Any], key: str) -> tuple[dict[str, Any], ...]:
    value = payload.get(key)
    if not isinstance(value, list | tuple):
        return ()
    return tuple(item for item in value if isinstance(item, dict))


def _float_metric(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_metric(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

