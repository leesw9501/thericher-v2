"""Bounded robustness replay for candidate threshold variants."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from thericher_v2.contracts import SCHEMA_VERSION, Timeframe
from thericher_v2.serialization import to_jsonable

from .candidate_comparison import _payload_dict, _payload_string
from .candidate_replay import CandidateProbabilityRunner
from .candidate_threshold_sweep import (
    CandidateThresholdSweepConfig,
    CandidateThresholdSweepVariant,
    _load_aligned_source_from_trace,
    _read_trace_artifact,
    _run_threshold_variants,
    _trace_payload_error,
    parse_threshold_pairs,
    run_bounded_candidate_probability_trace,
)
from .candidate_training import (
    GpuReadiness,
    _reject_repo_artifact_path,
    detect_gpu_readiness,
    parse_candidate_data_slices,
)

CandidateThresholdRobustnessStatus = Literal[
    "candidate_robustness_replayed_only",
    "prepared_not_robustness_replayed",
]
CandidateThresholdRobustnessSliceStatus = Literal[
    "slice_replayed_only",
    "prepared_not_replayed",
]
DEFAULT_CANDIDATE_THRESHOLD_ROBUSTNESS_RUN_ID = "bounded-candidate-threshold-robustness"
MAX_CANDIDATE_THRESHOLD_ROBUSTNESS_SLICES = 6


@dataclass(frozen=True)
class CandidateThresholdRobustnessSliceConfig:
    slice_id: str
    yahoo_snapshot: Path
    symbol: str
    probability_trace_artifact: Path | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.slice_id:
            raise ValueError("slice_id is required")
        if any(part in self.slice_id for part in ("\\", "/", ":")):
            raise ValueError("slice_id must not contain path separators")
        if not self.symbol:
            raise ValueError("symbol is required")
        object.__setattr__(self, "symbol", self.symbol.upper())


@dataclass(frozen=True)
class CandidateThresholdRobustnessConfig:
    run_id: str = DEFAULT_CANDIDATE_THRESHOLD_ROBUSTNESS_RUN_ID
    max_bars: int = 180
    min_examples: int = 8
    threshold_pairs: tuple[tuple[float, float], ...] = ()
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
        if len(self.slices) > MAX_CANDIDATE_THRESHOLD_ROBUSTNESS_SLICES:
            raise ValueError(
                "slices must be <= "
                f"{MAX_CANDIDATE_THRESHOLD_ROBUSTNESS_SLICES}"
            )
        slice_ids = [item.slice_id for item in self.slices]
        if len(set(slice_ids)) != len(slice_ids):
            raise ValueError("robustness slice ids must be unique")
        _sweep_config(self, run_id=f"{self.run_id}-validation")


@dataclass(frozen=True)
class CandidateThresholdRobustnessSliceResult:
    slice_id: str
    status: CandidateThresholdRobustnessSliceStatus
    reason: str
    yahoo_snapshot: Path
    probability_trace_artifact: Path | None
    data_source: str
    symbol: str | None
    market: str | None
    timeframe: Timeframe | None
    bars_seen: int
    examples_seen: int
    trace_status: str | None
    trace_reason: str | None
    source_alignment: dict[str, Any]
    variants: tuple[CandidateThresholdSweepVariant, ...]
    metrics: dict[str, Any]
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class BoundedCandidateThresholdRobustnessResult:
    run_id: str
    status: CandidateThresholdRobustnessStatus
    checked_at: datetime
    gpu: GpuReadiness
    reason: str
    candidate_experiment_id: str | None
    candidate_parameters: dict[str, Any]
    training_metrics_artifact: Path | None
    evaluation_artifact: Path | None
    model_artifact: Path | None
    robustness_artifact: Path
    slice_count: int
    completed_slice_count: int
    slices: tuple[CandidateThresholdRobustnessSliceResult, ...]
    thresholds: dict[str, Any]
    metrics: dict[str, Any]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_at", self.checked_at.astimezone(UTC))


def run_bounded_candidate_threshold_robustness(
    *,
    config: CandidateThresholdRobustnessConfig,
    artifact_root: Path,
    repo_root: Path | None = None,
    training_metrics_artifact: Path | None = None,
    evaluation_artifact: Path | None = None,
    model_artifact: Path | None = None,
    gpu: GpuReadiness | None = None,
    probability_runner: CandidateProbabilityRunner | None = None,
) -> BoundedCandidateThresholdRobustnessResult:
    _reject_repo_artifact_path(artifact_root, repo_root)
    output_dir = artifact_root / "candidate-threshold-robustness" / config.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    robustness_artifact = output_dir / "metrics.json"
    gpu = gpu or detect_gpu_readiness()
    slices = tuple(
        _run_robustness_slice(
            config=config,
            slice_config=slice_config,
            artifact_root=artifact_root,
            repo_root=repo_root,
            output_dir=output_dir,
            training_metrics_artifact=training_metrics_artifact,
            evaluation_artifact=evaluation_artifact,
            model_artifact=model_artifact,
            gpu=gpu,
            probability_runner=probability_runner,
        )
        for slice_config in config.slices
    )
    completed_slice_count = sum(
        1 for item in slices if item.status == "slice_replayed_only"
    )
    status: CandidateThresholdRobustnessStatus = (
        "candidate_robustness_replayed_only"
        if completed_slice_count > 0
        else "prepared_not_robustness_replayed"
    )
    reason = (
        "bounded threshold robustness replay completed without promotion decision"
        if completed_slice_count > 0
        else "no robustness slice replayed"
    )
    trace_payload = _first_trace_payload(slices)
    result = BoundedCandidateThresholdRobustnessResult(
        run_id=config.run_id,
        status=status,
        checked_at=datetime.now(UTC),
        gpu=gpu,
        reason=reason,
        candidate_experiment_id=_payload_string(trace_payload, "candidate_experiment_id"),
        candidate_parameters=_payload_dict(trace_payload, "candidate_parameters"),
        training_metrics_artifact=training_metrics_artifact
        or _path_from_payload(trace_payload, "training_metrics_artifact"),
        evaluation_artifact=evaluation_artifact
        or _path_from_payload(trace_payload, "evaluation_artifact"),
        model_artifact=model_artifact or _path_from_payload(trace_payload, "model_artifact"),
        robustness_artifact=robustness_artifact,
        slice_count=len(slices),
        completed_slice_count=completed_slice_count,
        slices=slices,
        thresholds=_thresholds_payload(config),
        metrics=_aggregate_robustness_metrics(slices),
    )
    robustness_artifact.write_text(
        json.dumps(
            _candidate_threshold_robustness_payload(result, artifact_root),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return result


def _run_robustness_slice(
    *,
    config: CandidateThresholdRobustnessConfig,
    slice_config: CandidateThresholdRobustnessSliceConfig,
    artifact_root: Path,
    repo_root: Path | None,
    output_dir: Path,
    training_metrics_artifact: Path | None,
    evaluation_artifact: Path | None,
    model_artifact: Path | None,
    gpu: GpuReadiness,
    probability_runner: CandidateProbabilityRunner | None,
) -> CandidateThresholdRobustnessSliceResult:
    sweep_config = _sweep_config(config, run_id=f"{config.run_id}-{slice_config.slice_id}")
    trace_payload, selected_trace_artifact, trace_error = _load_or_run_slice_trace(
        config=sweep_config,
        slice_config=slice_config,
        artifact_root=artifact_root,
        repo_root=repo_root,
        training_metrics_artifact=training_metrics_artifact,
        evaluation_artifact=evaluation_artifact,
        model_artifact=model_artifact,
        gpu=gpu,
        probability_runner=probability_runner,
    )
    source_alignment: dict[str, Any] = {
        "same_trace_evidence": False,
        "reason": "trace was not loaded",
    }
    variants: tuple[CandidateThresholdSweepVariant, ...] = ()
    source_error: str | None = None
    if trace_error is None:
        try:
            source, source_alignment = _load_aligned_source_from_trace(
                config=sweep_config,
                trace_payload=trace_payload,
                yahoo_snapshot=slice_config.yahoo_snapshot,
                symbol=slice_config.symbol,
            )
        except Exception as exc:  # noqa: BLE001 - robustness records prepared slices.
            source_error = f"robustness source unavailable: {exc}"
        else:
            if source_alignment["same_trace_evidence"]:
                try:
                    variants = _run_threshold_variants(
                        config=sweep_config,
                        artifact_root=artifact_root,
                        output_dir=output_dir / "slices" / slice_config.slice_id,
                        trace_payload=trace_payload,
                        source=source,
                        baseline_metrics={},
                        gpu=gpu,
                    )
                except Exception as exc:  # noqa: BLE001 - robustness records prepared slices.
                    source_error = f"robustness threshold replay unavailable: {exc}"
    status, reason = _slice_status_and_reason(
        trace_error=trace_error,
        source_error=source_error,
        source_alignment=source_alignment,
        variants=variants,
    )
    return CandidateThresholdRobustnessSliceResult(
        slice_id=slice_config.slice_id,
        status=status,
        reason=reason,
        yahoo_snapshot=slice_config.yahoo_snapshot,
        probability_trace_artifact=selected_trace_artifact,
        data_source=str(trace_payload.get("data_source") or slice_config.yahoo_snapshot),
        symbol=_payload_string(trace_payload, "symbol") or slice_config.symbol,
        market=_payload_string(trace_payload, "market"),
        timeframe=_timeframe_from_payload(trace_payload.get("timeframe")),
        bars_seen=_int_from_payload(trace_payload.get("bars_seen")) or 0,
        examples_seen=_int_from_payload(trace_payload.get("examples_seen")) or 0,
        trace_status=_payload_string(trace_payload, "status"),
        trace_reason=_payload_string(trace_payload, "reason"),
        source_alignment=source_alignment,
        variants=variants,
        metrics=_slice_metrics(variants),
    )


def _load_or_run_slice_trace(
    *,
    config: CandidateThresholdSweepConfig,
    slice_config: CandidateThresholdRobustnessSliceConfig,
    artifact_root: Path,
    repo_root: Path | None,
    training_metrics_artifact: Path | None,
    evaluation_artifact: Path | None,
    model_artifact: Path | None,
    gpu: GpuReadiness,
    probability_runner: CandidateProbabilityRunner | None,
) -> tuple[dict[str, Any], Path | None, str | None]:
    if slice_config.probability_trace_artifact is not None:
        payload, error = _read_trace_artifact(slice_config.probability_trace_artifact)
        if error is None:
            error = _trace_payload_error(payload)
        return payload, slice_config.probability_trace_artifact, error
    try:
        trace = run_bounded_candidate_probability_trace(
            config=config,
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
    except Exception as exc:  # noqa: BLE001 - robustness records prepared slices.
        return {}, None, f"robustness probability trace unavailable: {exc}"
    payload, error = _read_trace_artifact(trace.trace_artifact)
    if error is None:
        error = _trace_payload_error(payload)
    return payload, trace.trace_artifact, error


def _slice_status_and_reason(
    *,
    trace_error: str | None,
    source_error: str | None,
    source_alignment: dict[str, Any],
    variants: tuple[CandidateThresholdSweepVariant, ...],
) -> tuple[CandidateThresholdRobustnessSliceStatus, str]:
    if trace_error is not None:
        return "prepared_not_replayed", trace_error
    if source_error is not None:
        return "prepared_not_replayed", source_error
    if not source_alignment["same_trace_evidence"]:
        return "prepared_not_replayed", "probability trace does not match robustness slice"
    if not any(variant.status == "candidate_replayed_only" for variant in variants):
        return "prepared_not_replayed", "no valid threshold pair replayed for slice"
    return "slice_replayed_only", "slice threshold variants replayed from probability trace"


def _sweep_config(
    config: CandidateThresholdRobustnessConfig,
    *,
    run_id: str,
) -> CandidateThresholdSweepConfig:
    return CandidateThresholdSweepConfig(
        run_id=run_id,
        max_bars=config.max_bars,
        min_examples=config.min_examples,
        threshold_pairs=config.threshold_pairs or parse_threshold_pairs(None),
        sample_seed=config.sample_seed,
        starting_cash=config.starting_cash,
        quantity=config.quantity,
        fee_bps=config.fee_bps,
        slippage_bps=config.slippage_bps,
    )


def _slice_metrics(variants: tuple[CandidateThresholdSweepVariant, ...]) -> dict[str, Any]:
    completed = tuple(
        variant for variant in variants if variant.status == "candidate_replayed_only"
    )
    if not completed:
        return {
            "completed_variant_count": 0,
            "replay_fill_count_total": 0,
            "promotion_gate": False,
        }
    pnls = [variant.pnl for variant in completed]
    drawdowns = [variant.max_drawdown for variant in completed]
    fill_counts = [variant.replay_fill_count for variant in completed]
    final_positions = [variant.final_position for variant in completed]
    return to_jsonable(
        {
            "completed_variant_count": len(completed),
            "replay_fill_count_total": sum(fill_counts),
            "pnl_min": min(pnls),
            "pnl_max": max(pnls),
            "max_drawdown_max": max(drawdowns),
            "fill_count_min": min(fill_counts),
            "fill_count_max": max(fill_counts),
            "final_positions": final_positions,
            "comparison_is_descriptive": True,
            "promotion_gate": False,
        }
    )


def _aggregate_robustness_metrics(
    slices: tuple[CandidateThresholdRobustnessSliceResult, ...],
) -> dict[str, Any]:
    completed = tuple(item for item in slices if item.status == "slice_replayed_only")
    completed_variants = tuple(
        variant
        for item in completed
        for variant in item.variants
        if variant.status == "candidate_replayed_only"
    )
    if not completed_variants:
        return {
            "completed_slice_count": len(completed),
            "completed_variant_count": 0,
            "promotion_gate": False,
        }
    pnls = [variant.pnl for variant in completed_variants]
    drawdowns = [variant.max_drawdown for variant in completed_variants]
    fill_counts = [variant.replay_fill_count for variant in completed_variants]
    return to_jsonable(
        {
            "completed_slice_count": len(completed),
            "completed_variant_count": len(completed_variants),
            "replay_fill_count_total": sum(fill_counts),
            "pnl_min": min(pnls),
            "pnl_max": max(pnls),
            "max_drawdown_max": max(drawdowns),
            "fill_count_min": min(fill_counts),
            "fill_count_max": max(fill_counts),
            "comparison_is_descriptive": True,
            "promotion_gate": False,
        }
    )


def _thresholds_payload(config: CandidateThresholdRobustnessConfig) -> dict[str, Any]:
    return {
        "threshold_pairs": [
            {
                "buy_threshold": f"{buy:.6f}",
                "sell_threshold": f"{sell:.6f}",
            }
            for buy, sell in (config.threshold_pairs or parse_threshold_pairs(None))
        ],
        "quantity": str(config.quantity),
        "starting_cash": str(config.starting_cash),
        "fee_bps": str(config.fee_bps),
        "slippage_bps": str(config.slippage_bps),
        "slice_cap": MAX_CANDIDATE_THRESHOLD_ROBUSTNESS_SLICES,
        "comparison_is_descriptive": True,
        "promotion_gate": False,
    }


def _candidate_threshold_robustness_payload(
    result: BoundedCandidateThresholdRobustnessResult,
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
            "completed_slice_count": result.completed_slice_count,
            "slices": [
                _candidate_threshold_robustness_slice_payload(item)
                for item in result.slices
            ],
            "thresholds": result.thresholds,
            "metrics": result.metrics,
            "artifacts": {
                "candidate_threshold_robustness": str(result.robustness_artifact),
            },
            "artifact_policy": {
                "root": str(artifact_root),
                "repo_storage_allowed": False,
            },
        }
    )


def _candidate_threshold_robustness_slice_payload(
    result: CandidateThresholdRobustnessSliceResult,
) -> dict[str, Any]:
    return {
        "schema_version": result.schema_version,
        "slice_id": result.slice_id,
        "status": result.status,
        "reason": result.reason,
        "yahoo_snapshot": str(result.yahoo_snapshot),
        "probability_trace_artifact": (
            None
            if result.probability_trace_artifact is None
            else str(result.probability_trace_artifact)
        ),
        "data_source": result.data_source,
        "symbol": result.symbol,
        "market": result.market,
        "timeframe": result.timeframe,
        "bars_seen": result.bars_seen,
        "examples_seen": result.examples_seen,
        "trace_status": result.trace_status,
        "trace_reason": result.trace_reason,
        "source_alignment": result.source_alignment,
        "variants": result.variants,
        "metrics": result.metrics,
    }


def _first_trace_payload(
    slices: tuple[CandidateThresholdRobustnessSliceResult, ...],
) -> dict[str, Any]:
    for item in slices:
        if item.probability_trace_artifact is None:
            continue
        payload, error = _read_trace_artifact(item.probability_trace_artifact)
        if error is None and payload:
            return payload
    return {}


def _path_from_payload(payload: dict[str, Any], key: str) -> Path | None:
    value = payload.get(key)
    if value:
        return Path(str(value))
    return None


def _timeframe_from_payload(value: object) -> Timeframe | None:
    if value is None:
        return None
    try:
        return Timeframe(str(value))
    except ValueError:
        return None


def _int_from_payload(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_robustness_slices(
    values: list[str] | None,
) -> tuple[CandidateThresholdRobustnessSliceConfig, ...]:
    return tuple(
        CandidateThresholdRobustnessSliceConfig(
            slice_id=data_slice.slice_id,
            yahoo_snapshot=data_slice.yahoo_snapshot,
            symbol=data_slice.symbol,
        )
        for data_slice in parse_candidate_data_slices(values)
    )
