"""Descriptive probability-derived threshold calibration for candidate replay."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Literal

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.serialization import to_jsonable

from .candidate_comparison import _payload_dict, _payload_string
from .candidate_replay import CandidateProbabilityRunner
from .candidate_threshold_robustness import (
    BoundedCandidateThresholdRobustnessResult,
    CandidateThresholdRobustnessConfig,
    CandidateThresholdRobustnessSliceConfig,
    run_bounded_candidate_threshold_robustness,
)
from .candidate_threshold_sweep import (
    CandidateThresholdSweepConfig,
    _path_from_payload,
    _probabilities_from_trace_payload,
    _read_trace_artifact,
    _trace_payload_error,
    run_bounded_candidate_probability_trace,
)
from .candidate_training import (
    GpuReadiness,
    _reject_repo_artifact_path,
    detect_gpu_readiness,
)

CandidateThresholdCalibrationStatus = Literal[
    "candidate_thresholds_calibrated_only",
    "prepared_not_calibrated",
]
CandidateThresholdCalibrationTraceStatus = Literal[
    "trace_ready",
    "prepared_not_traced",
]
DEFAULT_CANDIDATE_THRESHOLD_CALIBRATION_RUN_ID = (
    "bounded-candidate-threshold-calibration"
)
MAX_CANDIDATE_THRESHOLD_CALIBRATION_PAIRS = 8
DEFAULT_CALIBRATION_QUANTILE_PAIRS: tuple[tuple[float, float], ...] = (
    (0.50, 0.25),
    (0.65, 0.25),
    (0.75, 0.25),
    (0.85, 0.10),
    (0.90, 0.10),
    (0.95, 0.10),
)
THRESHOLD_ROUNDING_STEP = Decimal("0.001")


@dataclass(frozen=True)
class CandidateThresholdCalibrationConfig:
    run_id: str = DEFAULT_CANDIDATE_THRESHOLD_CALIBRATION_RUN_ID
    max_bars: int = 180
    min_examples: int = 8
    threshold_pair_cap: int = MAX_CANDIDATE_THRESHOLD_CALIBRATION_PAIRS
    quantile_pairs: tuple[tuple[float, float], ...] = DEFAULT_CALIBRATION_QUANTILE_PAIRS
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
        if not 0 < self.threshold_pair_cap <= MAX_CANDIDATE_THRESHOLD_CALIBRATION_PAIRS:
            raise ValueError(
                "threshold_pair_cap must be between 1 and "
                f"{MAX_CANDIDATE_THRESHOLD_CALIBRATION_PAIRS}"
            )
        if not self.quantile_pairs:
            raise ValueError("at least one calibration quantile pair is required")
        for buy_quantile, sell_quantile in self.quantile_pairs:
            if not 0 <= sell_quantile < buy_quantile <= 1:
                raise ValueError(
                    "calibration quantile pairs must satisfy "
                    "0 <= sell_quantile < buy_quantile <= 1"
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
class CandidateThresholdCalibrationTraceSummary:
    slice_id: str
    status: CandidateThresholdCalibrationTraceStatus
    reason: str
    yahoo_snapshot: Path
    probability_trace_artifact: Path | None
    symbol: str
    trace_symbol: str | None
    bars_seen: int
    examples_seen: int
    probability_count: int
    probability_summary: dict[str, Any]
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class BoundedCandidateThresholdCalibrationResult:
    run_id: str
    status: CandidateThresholdCalibrationStatus
    checked_at: datetime
    gpu: GpuReadiness
    reason: str
    candidate_experiment_id: str | None
    candidate_parameters: dict[str, Any]
    training_metrics_artifact: Path | None
    evaluation_artifact: Path | None
    model_artifact: Path | None
    calibration_artifact: Path
    robustness_artifact: Path | None
    slice_count: int
    ready_trace_count: int
    probability_count: int
    trace_summaries: tuple[CandidateThresholdCalibrationTraceSummary, ...]
    probability_summary: dict[str, Any]
    threshold_pairs: tuple[tuple[float, float], ...]
    thresholds: dict[str, Any]
    robustness: BoundedCandidateThresholdRobustnessResult | None
    metrics: dict[str, Any]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_at", self.checked_at.astimezone(UTC))


def run_bounded_candidate_threshold_calibration(
    *,
    config: CandidateThresholdCalibrationConfig,
    artifact_root: Path,
    repo_root: Path | None = None,
    training_metrics_artifact: Path | None = None,
    evaluation_artifact: Path | None = None,
    model_artifact: Path | None = None,
    gpu: GpuReadiness | None = None,
    probability_runner: CandidateProbabilityRunner | None = None,
) -> BoundedCandidateThresholdCalibrationResult:
    _reject_repo_artifact_path(artifact_root, repo_root)
    output_dir = artifact_root / "candidate-threshold-calibration" / config.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    calibration_artifact = output_dir / "metrics.json"
    gpu = gpu or detect_gpu_readiness()

    traces = tuple(
        _load_or_run_calibration_trace(
            config=config,
            slice_config=slice_config,
            artifact_root=artifact_root,
            repo_root=repo_root,
            training_metrics_artifact=training_metrics_artifact,
            evaluation_artifact=evaluation_artifact,
            model_artifact=model_artifact,
            gpu=gpu,
            probability_runner=probability_runner,
        )
        for slice_config in config.slices
    )
    summaries = tuple(
        _trace_summary(slice_config=slice_config, payload=payload, artifact=artifact, error=error)
        for slice_config, payload, artifact, error in traces
    )
    ready_traces = tuple(
        (slice_config, payload, artifact, _probabilities_from_trace_payload(payload))
        for slice_config, payload, artifact, error in traces
        if error is None and artifact is not None and _probabilities_from_trace_payload(payload)
    )
    probabilities = tuple(
        probability
        for _slice_config, _payload, _artifact, trace_probabilities in ready_traces
        for probability in trace_probabilities
    )
    threshold_pairs = derive_calibration_threshold_pairs(
        probabilities,
        cap=config.threshold_pair_cap,
        quantile_pairs=config.quantile_pairs,
    )
    robustness: BoundedCandidateThresholdRobustnessResult | None = None
    if threshold_pairs and ready_traces:
        robustness = run_bounded_candidate_threshold_robustness(
            config=CandidateThresholdRobustnessConfig(
                run_id=f"{config.run_id}-robustness",
                max_bars=config.max_bars,
                min_examples=config.min_examples,
                threshold_pairs=threshold_pairs,
                slices=tuple(
                    CandidateThresholdRobustnessSliceConfig(
                        slice_id=slice_config.slice_id,
                        yahoo_snapshot=slice_config.yahoo_snapshot,
                        symbol=slice_config.symbol,
                        probability_trace_artifact=artifact,
                    )
                    for slice_config, _payload, artifact, _probabilities in ready_traces
                ),
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

    status, reason = _calibration_status_and_reason(
        config=config,
        ready_trace_count=len(ready_traces),
        threshold_pairs=threshold_pairs,
        robustness=robustness,
    )
    first_payload = _first_ready_payload(ready_traces)
    result = BoundedCandidateThresholdCalibrationResult(
        run_id=config.run_id,
        status=status,
        checked_at=datetime.now(UTC),
        gpu=gpu,
        reason=reason,
        candidate_experiment_id=_payload_string(first_payload, "candidate_experiment_id"),
        candidate_parameters=_payload_dict(first_payload, "candidate_parameters"),
        training_metrics_artifact=training_metrics_artifact
        or _path_from_payload(first_payload, "training_metrics_artifact"),
        evaluation_artifact=evaluation_artifact
        or _path_from_payload(first_payload, "evaluation_artifact"),
        model_artifact=model_artifact or _path_from_payload(first_payload, "model_artifact"),
        calibration_artifact=calibration_artifact,
        robustness_artifact=None if robustness is None else robustness.robustness_artifact,
        slice_count=len(config.slices),
        ready_trace_count=len(ready_traces),
        probability_count=len(probabilities),
        trace_summaries=summaries,
        probability_summary=probability_distribution_summary(probabilities),
        threshold_pairs=threshold_pairs,
        thresholds=_thresholds_payload(config, threshold_pairs),
        robustness=robustness,
        metrics=_calibration_metrics(robustness, len(ready_traces)),
    )
    calibration_artifact.write_text(
        json.dumps(
            _candidate_threshold_calibration_payload(result, artifact_root),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return result


def derive_calibration_threshold_pairs(
    probabilities: tuple[float, ...],
    *,
    cap: int = MAX_CANDIDATE_THRESHOLD_CALIBRATION_PAIRS,
    quantile_pairs: tuple[tuple[float, float], ...] = DEFAULT_CALIBRATION_QUANTILE_PAIRS,
) -> tuple[tuple[float, float], ...]:
    clean = tuple(sorted(float(value) for value in probabilities if 0 < float(value) < 1))
    if len(clean) < 2 or clean[-1] - clean[0] < float(THRESHOLD_ROUNDING_STEP):
        return ()
    pairs: list[tuple[float, float]] = []
    seen: set[tuple[float, float]] = set()
    for buy_quantile, sell_quantile in quantile_pairs:
        buy_threshold = _rounded_threshold(_quantile(clean, buy_quantile))
        sell_threshold = _rounded_threshold(_quantile(clean, sell_quantile))
        if sell_threshold >= buy_threshold:
            sell_threshold = _rounded_threshold(
                buy_threshold - float(THRESHOLD_ROUNDING_STEP)
            )
        pair = (buy_threshold, sell_threshold)
        if not 0 < pair[1] < pair[0] < 1 or pair in seen:
            continue
        seen.add(pair)
        pairs.append(pair)
        if len(pairs) >= cap:
            break
    return tuple(pairs)


def probability_distribution_summary(probabilities: tuple[float, ...]) -> dict[str, Any]:
    clean = tuple(sorted(float(value) for value in probabilities if 0 < float(value) < 1))
    if not clean:
        return {
            "count": 0,
            "quantile_method": "sorted_floor_index",
        }
    quantiles = {
        f"q{int(quantile * 100):02d}": f"{_quantile(clean, quantile):.6f}"
        for quantile in (0.10, 0.25, 0.50, 0.65, 0.75, 0.85, 0.90, 0.95)
    }
    return {
        "count": len(clean),
        "min": f"{clean[0]:.6f}",
        "max": f"{clean[-1]:.6f}",
        "mean": f"{sum(clean) / len(clean):.6f}",
        "quantiles": quantiles,
        "quantile_method": "sorted_floor_index",
    }


def _load_or_run_calibration_trace(
    *,
    config: CandidateThresholdCalibrationConfig,
    slice_config: CandidateThresholdRobustnessSliceConfig,
    artifact_root: Path,
    repo_root: Path | None,
    training_metrics_artifact: Path | None,
    evaluation_artifact: Path | None,
    model_artifact: Path | None,
    gpu: GpuReadiness,
    probability_runner: CandidateProbabilityRunner | None,
) -> tuple[CandidateThresholdRobustnessSliceConfig, dict[str, Any], Path | None, str | None]:
    if slice_config.probability_trace_artifact is not None:
        payload, error = _read_trace_artifact(slice_config.probability_trace_artifact)
        if error is None:
            error = _trace_payload_error(payload)
        return slice_config, payload, slice_config.probability_trace_artifact, error
    try:
        trace = run_bounded_candidate_probability_trace(
            config=CandidateThresholdSweepConfig(
                run_id=f"{config.run_id}-{slice_config.slice_id}",
                max_bars=config.max_bars,
                min_examples=config.min_examples,
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
            yahoo_snapshot=slice_config.yahoo_snapshot,
            symbol=slice_config.symbol,
            gpu=gpu,
            probability_runner=probability_runner,
        )
    except Exception as exc:  # noqa: BLE001 - calibration records prepared slices.
        return slice_config, {}, None, f"calibration probability trace unavailable: {exc}"
    payload, error = _read_trace_artifact(trace.trace_artifact)
    if error is None:
        error = _trace_payload_error(payload)
    return slice_config, payload, trace.trace_artifact, error


def _trace_summary(
    *,
    slice_config: CandidateThresholdRobustnessSliceConfig,
    payload: dict[str, Any],
    artifact: Path | None,
    error: str | None,
) -> CandidateThresholdCalibrationTraceSummary:
    probabilities = _probabilities_from_trace_payload(payload) if error is None else ()
    if error is None and not probabilities:
        error = "candidate probability trace has no probabilities"
    status: CandidateThresholdCalibrationTraceStatus = (
        "trace_ready" if error is None else "prepared_not_traced"
    )
    return CandidateThresholdCalibrationTraceSummary(
        slice_id=slice_config.slice_id,
        status=status,
        reason="probability trace ready" if error is None else str(error),
        yahoo_snapshot=slice_config.yahoo_snapshot,
        probability_trace_artifact=artifact,
        symbol=slice_config.symbol,
        trace_symbol=_payload_string(payload, "symbol"),
        bars_seen=_int_from_payload(payload.get("bars_seen")) or 0,
        examples_seen=_int_from_payload(payload.get("examples_seen")) or 0,
        probability_count=len(probabilities),
        probability_summary=probability_distribution_summary(probabilities),
    )


def _calibration_status_and_reason(
    *,
    config: CandidateThresholdCalibrationConfig,
    ready_trace_count: int,
    threshold_pairs: tuple[tuple[float, float], ...],
    robustness: BoundedCandidateThresholdRobustnessResult | None,
) -> tuple[CandidateThresholdCalibrationStatus, str]:
    if not config.slices:
        return "prepared_not_calibrated", "no calibration slices configured"
    if ready_trace_count == 0:
        return "prepared_not_calibrated", "no probability trace was ready"
    if not threshold_pairs:
        return "prepared_not_calibrated", "no valid threshold pair derived from traces"
    if robustness is None:
        return "prepared_not_calibrated", "robustness replay was not started"
    if robustness.status != "candidate_robustness_replayed_only":
        return "prepared_not_calibrated", robustness.reason
    return (
        "candidate_thresholds_calibrated_only",
        "bounded probability-derived threshold replay completed without promotion decision",
    )


def _calibration_metrics(
    robustness: BoundedCandidateThresholdRobustnessResult | None,
    ready_trace_count: int,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "ready_trace_count": ready_trace_count,
        "comparison_is_descriptive": True,
        "promotion_gate": False,
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
    config: CandidateThresholdCalibrationConfig,
    threshold_pairs: tuple[tuple[float, float], ...],
) -> dict[str, Any]:
    return {
        "derivation": "observed_probability_quantiles",
        "threshold_pair_cap": config.threshold_pair_cap,
        "threshold_rounding": str(THRESHOLD_ROUNDING_STEP),
        "quantile_method": "sorted_floor_index",
        "quantile_pairs": [
            {
                "buy_quantile": f"{buy_quantile:.2f}",
                "sell_quantile": f"{sell_quantile:.2f}",
            }
            for buy_quantile, sell_quantile in config.quantile_pairs
        ],
        "threshold_pairs": [
            {
                "buy_threshold": f"{buy_threshold:.6f}",
                "sell_threshold": f"{sell_threshold:.6f}",
            }
            for buy_threshold, sell_threshold in threshold_pairs
        ],
        "quantity": str(config.quantity),
        "starting_cash": str(config.starting_cash),
        "fee_bps": str(config.fee_bps),
        "slippage_bps": str(config.slippage_bps),
        "comparison_is_descriptive": True,
        "promotion_gate": False,
    }


def _candidate_threshold_calibration_payload(
    result: BoundedCandidateThresholdCalibrationResult,
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
            "ready_trace_count": result.ready_trace_count,
            "probability_count": result.probability_count,
            "trace_summaries": [
                _calibration_trace_summary_payload(summary)
                for summary in result.trace_summaries
            ],
            "probability_summary": result.probability_summary,
            "thresholds": result.thresholds,
            "metrics": result.metrics,
            "artifacts": {
                "candidate_threshold_calibration": str(result.calibration_artifact),
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


def _calibration_trace_summary_payload(
    summary: CandidateThresholdCalibrationTraceSummary,
) -> dict[str, Any]:
    return {
        "schema_version": summary.schema_version,
        "slice_id": summary.slice_id,
        "status": summary.status,
        "reason": summary.reason,
        "yahoo_snapshot": str(summary.yahoo_snapshot),
        "probability_trace_artifact": None
        if summary.probability_trace_artifact is None
        else str(summary.probability_trace_artifact),
        "symbol": summary.symbol,
        "trace_symbol": summary.trace_symbol,
        "bars_seen": summary.bars_seen,
        "examples_seen": summary.examples_seen,
        "probability_count": summary.probability_count,
        "probability_summary": summary.probability_summary,
    }


def _first_ready_payload(
    ready_traces: tuple[
        tuple[CandidateThresholdRobustnessSliceConfig, dict[str, Any], Path, tuple[float, ...]],
        ...,
    ],
) -> dict[str, Any]:
    return ready_traces[0][1] if ready_traces else {}


def _quantile(sorted_values: tuple[float, ...], quantile: float) -> float:
    if not sorted_values:
        raise ValueError("quantile requires at least one probability")
    index = int((len(sorted_values) - 1) * quantile)
    return sorted_values[index]


def _rounded_threshold(value: float) -> float:
    rounded = Decimal(str(value)).quantize(
        THRESHOLD_ROUNDING_STEP,
        rounding=ROUND_HALF_UP,
    )
    rounded = min(max(rounded, Decimal("0.001")), Decimal("0.999"))
    return float(rounded)


def _int_from_payload(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
