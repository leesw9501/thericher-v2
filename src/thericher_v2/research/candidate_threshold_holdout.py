"""Holdout replay for a previously calibrated candidate threshold grid."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.execution import LOCAL_PAPER_SOURCE
from thericher_v2.serialization import to_jsonable

from .candidate_comparison import _payload_dict, _payload_string
from .candidate_replay import CandidateProbabilityRunner
from .candidate_threshold_calibration import probability_distribution_summary
from .candidate_threshold_robustness import (
    BoundedCandidateThresholdRobustnessResult,
    CandidateThresholdRobustnessConfig,
    CandidateThresholdRobustnessSliceConfig,
    run_bounded_candidate_threshold_robustness,
)
from .candidate_threshold_sweep import (
    _path_from_payload,
    _probabilities_from_trace_payload,
    _read_trace_artifact,
)
from .candidate_training import (
    GpuReadiness,
    _reject_repo_artifact_path,
    detect_gpu_readiness,
)

CandidateThresholdHoldoutStatus = Literal[
    "candidate_threshold_holdout_replayed_only",
    "prepared_not_holdout_replayed",
]
DEFAULT_CANDIDATE_THRESHOLD_HOLDOUT_RUN_ID = "bounded-candidate-threshold-holdout"


@dataclass(frozen=True)
class CandidateThresholdHoldoutConfig:
    run_id: str = DEFAULT_CANDIDATE_THRESHOLD_HOLDOUT_RUN_ID
    max_bars: int = 180
    min_examples: int = 8
    slices: tuple[CandidateThresholdRobustnessSliceConfig, ...] = ()
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
class BoundedCandidateThresholdHoldoutResult:
    run_id: str
    status: CandidateThresholdHoldoutStatus
    checked_at: datetime
    gpu: GpuReadiness
    reason: str
    source_calibration_artifact: Path | None
    candidate_experiment_id: str | None
    candidate_parameters: dict[str, Any]
    training_metrics_artifact: Path | None
    evaluation_artifact: Path | None
    model_artifact: Path | None
    holdout_artifact: Path
    robustness_artifact: Path | None
    slice_count: int
    completed_slice_count: int
    threshold_pairs: tuple[tuple[float, float], ...]
    thresholds: dict[str, Any]
    holdout_slices: tuple[dict[str, Any], ...]
    probability_summary: dict[str, Any]
    local_paper_verification: dict[str, Any]
    data_requests: tuple[dict[str, Any], ...]
    robustness: BoundedCandidateThresholdRobustnessResult | None
    metrics: dict[str, Any]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_at", self.checked_at.astimezone(UTC))


def run_bounded_candidate_threshold_holdout(
    *,
    config: CandidateThresholdHoldoutConfig,
    artifact_root: Path,
    repo_root: Path | None = None,
    calibration_artifact: Path | None = None,
    training_metrics_artifact: Path | None = None,
    evaluation_artifact: Path | None = None,
    model_artifact: Path | None = None,
    gpu: GpuReadiness | None = None,
    probability_runner: CandidateProbabilityRunner | None = None,
) -> BoundedCandidateThresholdHoldoutResult:
    _reject_repo_artifact_path(artifact_root, repo_root)
    output_dir = artifact_root / "candidate-threshold-holdout" / config.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    holdout_artifact = output_dir / "metrics.json"
    gpu = gpu or detect_gpu_readiness()

    calibration_payload, calibration_error = _read_calibration_artifact(
        calibration_artifact
    )
    threshold_pairs = (
        ()
        if calibration_error is not None
        else _threshold_pairs_from_calibration_payload(calibration_payload)
    )
    threshold_error = (
        None
        if calibration_error is not None or threshold_pairs
        else "calibration artifact contains no threshold pairs"
    )
    selected_training_metrics_artifact = (
        training_metrics_artifact
        or _path_from_payload(calibration_payload, "training_metrics_artifact")
    )
    selected_evaluation_artifact = (
        evaluation_artifact
        or _path_from_payload(calibration_payload, "evaluation_artifact")
    )
    selected_model_artifact = model_artifact or _path_from_payload(
        calibration_payload,
        "model_artifact",
    )
    robustness: BoundedCandidateThresholdRobustnessResult | None = None
    if calibration_error is None and threshold_error is None and config.slices:
        robustness = run_bounded_candidate_threshold_robustness(
            config=CandidateThresholdRobustnessConfig(
                run_id=f"{config.run_id}-robustness",
                max_bars=config.max_bars,
                min_examples=config.min_examples,
                threshold_pairs=threshold_pairs,
                slices=config.slices,
                sample_seed=config.sample_seed,
                starting_cash=config.starting_cash,
                quantity=config.quantity,
                fee_bps=config.fee_bps,
                slippage_bps=config.slippage_bps,
            ),
            artifact_root=artifact_root,
            repo_root=repo_root,
            training_metrics_artifact=selected_training_metrics_artifact,
            evaluation_artifact=selected_evaluation_artifact,
            model_artifact=selected_model_artifact,
            gpu=gpu,
            probability_runner=probability_runner,
        )

    status, reason = _holdout_status_and_reason(
        config=config,
        calibration_error=calibration_error,
        threshold_error=threshold_error,
        robustness=robustness,
    )
    probabilities = _holdout_probabilities(robustness)
    local_paper_verification = _local_paper_verification(robustness)
    data_requests = _holdout_data_requests(config.slices, robustness)
    result = BoundedCandidateThresholdHoldoutResult(
        run_id=config.run_id,
        status=status,
        checked_at=datetime.now(UTC),
        gpu=gpu,
        reason=reason,
        source_calibration_artifact=calibration_artifact,
        candidate_experiment_id=_payload_string(
            calibration_payload,
            "candidate_experiment_id",
        ),
        candidate_parameters=_payload_dict(calibration_payload, "candidate_parameters"),
        training_metrics_artifact=selected_training_metrics_artifact,
        evaluation_artifact=selected_evaluation_artifact,
        model_artifact=selected_model_artifact,
        holdout_artifact=holdout_artifact,
        robustness_artifact=None if robustness is None else robustness.robustness_artifact,
        slice_count=len(config.slices),
        completed_slice_count=0 if robustness is None else robustness.completed_slice_count,
        threshold_pairs=threshold_pairs,
        thresholds=_thresholds_payload(threshold_pairs, calibration_artifact),
        holdout_slices=_holdout_slice_payloads(config.slices, robustness),
        probability_summary=probability_distribution_summary(probabilities),
        local_paper_verification=local_paper_verification,
        data_requests=data_requests,
        robustness=robustness,
        metrics=_holdout_metrics(
            robustness=robustness,
            local_paper_verification=local_paper_verification,
        ),
    )
    holdout_artifact.write_text(
        json.dumps(
            _candidate_threshold_holdout_payload(result, artifact_root),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return result


def _read_calibration_artifact(path: Path | None) -> tuple[dict[str, Any], str | None]:
    if path is None:
        return {}, "candidate threshold calibration artifact is required"
    if not path.exists():
        return {}, f"candidate threshold calibration artifact is missing: {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, f"candidate threshold calibration artifact is unreadable: {exc}"
    if not isinstance(payload, dict):
        return {}, "candidate threshold calibration artifact must contain a JSON object"
    if payload.get("status") != "candidate_thresholds_calibrated_only":
        reason = _payload_string(payload, "reason") or "calibration artifact was not completed"
        return payload, reason
    return payload, None


def _threshold_pairs_from_calibration_payload(
    payload: dict[str, Any],
) -> tuple[tuple[float, float], ...]:
    thresholds = payload.get("thresholds")
    if not isinstance(thresholds, dict):
        return ()
    pairs = thresholds.get("threshold_pairs")
    if not isinstance(pairs, list):
        return ()
    parsed: list[tuple[float, float]] = []
    for pair in pairs:
        if not isinstance(pair, dict):
            continue
        try:
            buy_threshold = float(pair["buy_threshold"])
            sell_threshold = float(pair["sell_threshold"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 < sell_threshold < buy_threshold < 1:
            parsed.append((buy_threshold, sell_threshold))
    return tuple(parsed)


def _holdout_status_and_reason(
    *,
    config: CandidateThresholdHoldoutConfig,
    calibration_error: str | None,
    threshold_error: str | None,
    robustness: BoundedCandidateThresholdRobustnessResult | None,
) -> tuple[CandidateThresholdHoldoutStatus, str]:
    if calibration_error is not None:
        return "prepared_not_holdout_replayed", calibration_error
    if threshold_error is not None:
        return "prepared_not_holdout_replayed", threshold_error
    if not config.slices:
        return "prepared_not_holdout_replayed", "no holdout slices configured"
    if robustness is None:
        return "prepared_not_holdout_replayed", "holdout robustness replay was not started"
    if robustness.status != "candidate_robustness_replayed_only":
        return "prepared_not_holdout_replayed", robustness.reason
    return (
        "candidate_threshold_holdout_replayed_only",
        "bounded calibration holdout replay completed without promotion decision",
    )


def _holdout_probabilities(
    robustness: BoundedCandidateThresholdRobustnessResult | None,
) -> tuple[float, ...]:
    if robustness is None:
        return ()
    probabilities: list[float] = []
    for slice_result in robustness.slices:
        artifact = slice_result.probability_trace_artifact
        if artifact is None:
            continue
        payload, error = _read_trace_artifact(artifact)
        if error is None:
            probabilities.extend(_probabilities_from_trace_payload(payload))
    return tuple(probabilities)


def _local_paper_verification(
    robustness: BoundedCandidateThresholdRobustnessResult | None,
) -> dict[str, Any]:
    source_counts: dict[str, int] = {}
    unreadable_artifacts: list[str] = []
    if robustness is not None:
        for slice_result in robustness.slices:
            for variant in slice_result.variants:
                artifact = variant.events_artifact
                if not artifact:
                    continue
                try:
                    lines = Path(artifact).read_text(encoding="utf-8").splitlines()
                except OSError:
                    if variant.replay_fill_count == 0:
                        continue
                    unreadable_artifacts.append(str(artifact))
                    continue
                for line in lines:
                    event = json.loads(line)
                    if event.get("event_type") != "fill":
                        continue
                    source = str(event.get("payload", {}).get("source") or "")
                    source_counts[source] = source_counts.get(source, 0) + 1
    non_local = {
        source: count
        for source, count in source_counts.items()
        if source != LOCAL_PAPER_SOURCE
    }
    return {
        "fill_source_counts": source_counts,
        "local_paper_fill_count": source_counts.get(LOCAL_PAPER_SOURCE, 0),
        "non_local_fill_source_counts": non_local,
        "unreadable_event_artifacts": unreadable_artifacts,
        "all_fills_local_paper": not non_local and not unreadable_artifacts,
    }


def _holdout_data_requests(
    slices: tuple[CandidateThresholdRobustnessSliceConfig, ...],
    robustness: BoundedCandidateThresholdRobustnessResult | None,
) -> tuple[dict[str, Any], ...]:
    requests: list[dict[str, Any]] = []
    for item in slices:
        if not item.yahoo_snapshot.exists():
            requests.append(
                _data_request(
                    slice_id=item.slice_id,
                    yahoo_snapshot=item.yahoo_snapshot,
                    symbol=item.symbol,
                    reason="holdout snapshot is missing",
                )
            )
    if robustness is None:
        return tuple(requests)
    known = {(request["slice_id"], request["symbol"]) for request in requests}
    for item in robustness.slices:
        reason = item.reason.lower()
        key = (item.slice_id, str(item.symbol or ""))
        if key in known:
            continue
        if item.status == "slice_replayed_only":
            continue
        if "no bars loaded" not in reason and "file not found" not in reason:
            continue
        requests.append(
            _data_request(
                slice_id=item.slice_id,
                yahoo_snapshot=item.yahoo_snapshot,
                symbol=str(item.symbol or ""),
                reason=item.reason,
            )
        )
    return tuple(requests)


def _data_request(
    *,
    slice_id: str,
    yahoo_snapshot: Path,
    symbol: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "slice_id": slice_id,
        "symbol": symbol,
        "market": "US",
        "timeframe": "1m",
        "yahoo_snapshot": str(yahoo_snapshot),
        "requested_format": "canonical Yahoo intraday ohlcv_1m.csv.gz",
        "reason": reason,
    }


def _holdout_slice_payloads(
    slices: tuple[CandidateThresholdRobustnessSliceConfig, ...],
    robustness: BoundedCandidateThresholdRobustnessResult | None,
) -> tuple[dict[str, Any], ...]:
    results = {item.slice_id: item for item in robustness.slices} if robustness else {}
    payloads: list[dict[str, Any]] = []
    for slice_config in slices:
        result = results.get(slice_config.slice_id)
        payloads.append(
            {
                "slice_id": slice_config.slice_id,
                "symbol": slice_config.symbol,
                "yahoo_snapshot": str(slice_config.yahoo_snapshot),
                "status": None if result is None else result.status,
                "reason": None if result is None else result.reason,
                "probability_trace_artifact": None
                if result is None or result.probability_trace_artifact is None
                else str(result.probability_trace_artifact),
                "bars_seen": 0 if result is None else result.bars_seen,
                "examples_seen": 0 if result is None else result.examples_seen,
                "metrics": {} if result is None else result.metrics,
            }
        )
    return tuple(payloads)


def _holdout_metrics(
    *,
    robustness: BoundedCandidateThresholdRobustnessResult | None,
    local_paper_verification: dict[str, Any],
) -> dict[str, Any]:
    base = {
        "comparison_is_descriptive": True,
        "promotion_gate": False,
        "local_paper_verification": local_paper_verification,
    }
    if robustness is None:
        return {
            **base,
            "completed_slice_count": 0,
            "completed_variant_count": 0,
            "replay_fill_count_total": 0,
        }
    return {
        **base,
        "robustness_status": robustness.status,
        "completed_slice_count": robustness.completed_slice_count,
        "completed_variant_count": robustness.metrics.get("completed_variant_count", 0),
        "replay_fill_count_total": robustness.metrics.get("replay_fill_count_total", 0),
        "robustness_metrics": robustness.metrics,
    }


def _thresholds_payload(
    threshold_pairs: tuple[tuple[float, float], ...],
    calibration_artifact: Path | None,
) -> dict[str, Any]:
    return {
        "derivation": "source_calibration_artifact_unchanged",
        "source_calibration_artifact": None
        if calibration_artifact is None
        else str(calibration_artifact),
        "threshold_pairs": [
            {
                "buy_threshold": f"{buy_threshold:.6f}",
                "sell_threshold": f"{sell_threshold:.6f}",
            }
            for buy_threshold, sell_threshold in threshold_pairs
        ],
        "comparison_is_descriptive": True,
        "promotion_gate": False,
    }


def _candidate_threshold_holdout_payload(
    result: BoundedCandidateThresholdHoldoutResult,
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
            "source_calibration_artifact": None
            if result.source_calibration_artifact is None
            else str(result.source_calibration_artifact),
            "candidate_experiment_id": result.candidate_experiment_id,
            "candidate_parameters": result.candidate_parameters,
            "training_metrics_artifact": (
                None
                if result.training_metrics_artifact is None
                else str(result.training_metrics_artifact)
            ),
            "evaluation_artifact": (
                None if result.evaluation_artifact is None else str(result.evaluation_artifact)
            ),
            "model_artifact": (
                None if result.model_artifact is None else str(result.model_artifact)
            ),
            "slice_count": result.slice_count,
            "completed_slice_count": result.completed_slice_count,
            "holdout_slices": result.holdout_slices,
            "probability_summary": result.probability_summary,
            "thresholds": result.thresholds,
            "metrics": result.metrics,
            "local_paper_verification": result.local_paper_verification,
            "data_requests": result.data_requests,
            "artifacts": {
                "candidate_threshold_holdout": str(result.holdout_artifact),
                "candidate_threshold_robustness": None
                if result.robustness_artifact is None
                else str(result.robustness_artifact),
            },
            "artifact_policy": {
                "root": str(artifact_root),
                "repo_storage_allowed": False,
            },
        }
    )
