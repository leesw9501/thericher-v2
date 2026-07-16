"""Bounded probability trace and threshold sweep for candidate replay."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from thericher_v2.contracts import SCHEMA_VERSION, Timeframe
from thericher_v2.serialization import to_jsonable

from .candidate_comparison import _payload_dict, _payload_string
from .candidate_evaluation import (
    _candidate_from_training_payload,
    _feature_names_from_training_payload,
    _model_artifact_from_training_payload,
    _probabilities_from_result,
    _read_training_metrics,
    _run_torch_cuda_candidate_probabilities,
)
from .candidate_replay import (
    CandidateProbabilityRunner,
    CandidateReplayConfig,
    CandidateReplaySource,
    _available_gpu_backends,
    _fresh_event_store,
    _load_replay_source,
    _local_paper_fill_events,
    _model_artifact_from_evaluation_payload,
    _probability_metrics,
    _read_evaluation_artifact,
    _run_local_paper_replay,
    _selected_backend,
    _training_artifact_from_evaluation_payload,
)
from .candidate_training import (
    GpuReadiness,
    _reject_repo_artifact_path,
    apply_training_payload_feature_normalization,
    detect_gpu_readiness,
)

CandidateProbabilityTraceStatus = Literal["probability_traced_only", "prepared_not_traced"]
CandidateThresholdSweepStatus = Literal["candidate_swept_only", "prepared_not_swept"]
CandidateThresholdVariantStatus = Literal["candidate_replayed_only", "prepared_not_replayed"]
DEFAULT_CANDIDATE_THRESHOLD_SWEEP_RUN_ID = "bounded-candidate-threshold-sweep"
MAX_CANDIDATE_THRESHOLD_SWEEP_BARS = 512
MAX_CANDIDATE_THRESHOLD_PAIRS = 16
DEFAULT_THRESHOLD_PAIRS: tuple[tuple[float, float], ...] = (
    (0.47, 0.455),
    (0.50, 0.455),
    (0.52, 0.455),
    (0.55, 0.455),
    (0.60, 0.455),
)


@dataclass(frozen=True)
class CandidateThresholdSweepConfig:
    run_id: str = DEFAULT_CANDIDATE_THRESHOLD_SWEEP_RUN_ID
    max_bars: int = 180
    min_examples: int = 8
    threshold_pairs: tuple[tuple[float, float], ...] = DEFAULT_THRESHOLD_PAIRS
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
        if self.max_bars > MAX_CANDIDATE_THRESHOLD_SWEEP_BARS:
            raise ValueError(
                f"max_bars must be <= {MAX_CANDIDATE_THRESHOLD_SWEEP_BARS}"
            )
        if self.min_examples <= 0:
            raise ValueError("min_examples must be positive")
        if not self.threshold_pairs:
            raise ValueError("at least one threshold pair is required")
        if len(self.threshold_pairs) > MAX_CANDIDATE_THRESHOLD_PAIRS:
            raise ValueError(
                f"threshold_pairs must be <= {MAX_CANDIDATE_THRESHOLD_PAIRS}"
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
class CandidateProbabilityTraceEntry:
    offset: int
    probability: float
    signal_bar_start: datetime
    signal_bar_end: datetime
    execution_bar_start: datetime
    execution_bar_end: datetime
    signal_close: Decimal
    execution_open: Decimal
    execution_close: Decimal
    contiguous: bool
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "signal_bar_start", self.signal_bar_start.astimezone(UTC))
        object.__setattr__(self, "signal_bar_end", self.signal_bar_end.astimezone(UTC))
        object.__setattr__(
            self,
            "execution_bar_start",
            self.execution_bar_start.astimezone(UTC),
        )
        object.__setattr__(self, "execution_bar_end", self.execution_bar_end.astimezone(UTC))


@dataclass(frozen=True)
class BoundedCandidateProbabilityTraceResult:
    run_id: str
    status: CandidateProbabilityTraceStatus
    checked_at: datetime
    gpu: GpuReadiness
    reason: str
    available_backends: tuple[str, ...]
    selected_backend: str | None
    training_metrics_artifact: Path | None
    evaluation_artifact: Path | None
    model_artifact: Path | None
    candidate_experiment_id: str | None
    candidate_parameters: dict[str, Any]
    data_source: str
    symbol: str | None
    market: str | None
    timeframe: Timeframe | None
    bars_seen: int
    examples_seen: int
    lookback: int
    entries: tuple[CandidateProbabilityTraceEntry, ...]
    probability_metrics: dict[str, Any]
    trace_artifact: Path
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_at", self.checked_at.astimezone(UTC))


@dataclass(frozen=True)
class CandidateThresholdSweepVariant:
    variant_id: str
    status: CandidateThresholdVariantStatus
    reason: str
    buy_threshold: float
    sell_threshold: float
    decisions_seen: int
    order_intents_seen: int
    skipped_non_contiguous: int
    trade_count: int
    replay_fill_count: int
    event_count: int
    ending_cash: Decimal
    equity: Decimal
    pnl: Decimal
    max_drawdown: Decimal
    final_position: Decimal
    replay_final_position: Decimal
    deltas: dict[str, Any]
    events_artifact: str | None
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class BoundedCandidateThresholdSweepResult:
    run_id: str
    status: CandidateThresholdSweepStatus
    checked_at: datetime
    gpu: GpuReadiness
    reason: str
    candidate_experiment_id: str | None
    candidate_parameters: dict[str, Any]
    training_metrics_artifact: Path | None
    evaluation_artifact: Path | None
    model_artifact: Path | None
    probability_trace_artifact: Path | None
    comparison_artifact: Path | None
    sweep_artifact: Path
    data_source: str
    symbol: str | None
    market: str | None
    timeframe: Timeframe | None
    bars_seen: int
    examples_seen: int
    trace_status: CandidateProbabilityTraceStatus | None
    trace_reason: str | None
    source_alignment: dict[str, Any]
    baseline_metrics: dict[str, Any]
    variants: tuple[CandidateThresholdSweepVariant, ...]
    thresholds: dict[str, Any]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_at", self.checked_at.astimezone(UTC))


def run_bounded_candidate_threshold_sweep(
    *,
    config: CandidateThresholdSweepConfig | None = None,
    artifact_root: Path,
    repo_root: Path | None = None,
    probability_trace_artifact: Path | None = None,
    comparison_artifact: Path | None = None,
    training_metrics_artifact: Path | None = None,
    evaluation_artifact: Path | None = None,
    model_artifact: Path | None = None,
    yahoo_snapshot: Path | None = None,
    symbol: str | None = None,
    gpu: GpuReadiness | None = None,
    probability_runner: CandidateProbabilityRunner | None = None,
) -> BoundedCandidateThresholdSweepResult:
    config = config or CandidateThresholdSweepConfig()
    _reject_repo_artifact_path(artifact_root, repo_root)
    output_dir = artifact_root / "candidate-threshold-sweep" / config.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    sweep_artifact = output_dir / "metrics.json"
    gpu = gpu or detect_gpu_readiness()

    trace_payload, trace_result, selected_trace_artifact, trace_error = _load_or_run_trace(
        config=config,
        artifact_root=artifact_root,
        repo_root=repo_root,
        probability_trace_artifact=probability_trace_artifact,
        training_metrics_artifact=training_metrics_artifact,
        evaluation_artifact=evaluation_artifact,
        model_artifact=model_artifact,
        yahoo_snapshot=yahoo_snapshot,
        symbol=symbol,
        gpu=gpu,
        probability_runner=probability_runner,
    )
    comparison_payload, comparison_error = _read_comparison_artifact(comparison_artifact)
    baseline_metrics = _baseline_metrics_from_comparison_payload(comparison_payload)
    source, source_alignment = _load_aligned_source_from_trace(
        config=config,
        trace_payload=trace_payload,
        yahoo_snapshot=yahoo_snapshot,
        symbol=symbol,
    )
    variants: tuple[CandidateThresholdSweepVariant, ...] = ()
    if trace_error is None and comparison_error is None and source_alignment["same_trace_evidence"]:
        variants = _run_threshold_variants(
            config=config,
            artifact_root=artifact_root,
            output_dir=output_dir,
            trace_payload=trace_payload,
            source=source,
            baseline_metrics=baseline_metrics,
            gpu=gpu,
        )
    status, reason = _sweep_status_and_reason(
        trace_error=trace_error,
        comparison_error=comparison_error,
        source_alignment=source_alignment,
        variants=variants,
    )
    result = BoundedCandidateThresholdSweepResult(
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
        probability_trace_artifact=selected_trace_artifact,
        comparison_artifact=comparison_artifact,
        sweep_artifact=sweep_artifact,
        data_source=str(trace_payload.get("data_source") or ""),
        symbol=_payload_string(trace_payload, "symbol"),
        market=_payload_string(trace_payload, "market"),
        timeframe=_timeframe_from_payload(trace_payload.get("timeframe")),
        bars_seen=_int_from_payload(trace_payload.get("bars_seen")) or 0,
        examples_seen=_int_from_payload(trace_payload.get("examples_seen")) or 0,
        trace_status=_trace_status_from_payload(trace_payload),
        trace_reason=_payload_string(trace_payload, "reason"),
        source_alignment=source_alignment,
        baseline_metrics=baseline_metrics,
        variants=variants,
        thresholds=_sweep_threshold_payload(config),
    )
    sweep_artifact.write_text(
        json.dumps(
            _candidate_threshold_sweep_payload(result, artifact_root),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return result


def run_bounded_candidate_probability_trace(
    *,
    config: CandidateThresholdSweepConfig,
    artifact_root: Path,
    repo_root: Path | None = None,
    training_metrics_artifact: Path | None = None,
    evaluation_artifact: Path | None = None,
    model_artifact: Path | None = None,
    yahoo_snapshot: Path | None = None,
    symbol: str | None = None,
    gpu: GpuReadiness | None = None,
    probability_runner: CandidateProbabilityRunner | None = None,
) -> BoundedCandidateProbabilityTraceResult:
    _reject_repo_artifact_path(artifact_root, repo_root)
    output_dir = artifact_root / "candidate-probability-trace" / config.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    trace_artifact = output_dir / "trace.json"
    gpu = gpu or detect_gpu_readiness()
    evaluation_payload, evaluation_error = _read_evaluation_artifact(evaluation_artifact)
    selected_training_metrics_artifact = (
        training_metrics_artifact
        or _training_artifact_from_evaluation_payload(evaluation_payload)
    )
    training_payload, training_error = _read_training_metrics(selected_training_metrics_artifact)
    candidate = _candidate_from_training_payload(training_payload)
    source = _load_replay_source(
        config=_candidate_replay_config(config, run_id=f"{config.run_id}-trace-source"),
        candidate=candidate,
        yahoo_snapshot=yahoo_snapshot,
        symbol=symbol,
    )
    selected_model_artifact = (
        model_artifact
        or _model_artifact_from_evaluation_payload(evaluation_payload)
        or _model_artifact_from_training_payload(training_payload)
    )
    available_backends = _available_gpu_backends()
    selected_backend = "injected" if probability_runner is not None else _selected_backend()
    result = _run_trace_result(
        config=config,
        training_metrics_artifact=selected_training_metrics_artifact,
        training_error=training_error,
        evaluation_artifact=evaluation_artifact,
        evaluation_error=evaluation_error,
        model_artifact=selected_model_artifact,
        candidate=candidate,
        training_payload=training_payload,
        source=source,
        gpu=gpu,
        available_backends=available_backends,
        selected_backend=selected_backend,
        trace_artifact=trace_artifact,
        probability_runner=probability_runner,
    )
    trace_artifact.write_text(
        json.dumps(
            _candidate_probability_trace_payload(result, artifact_root),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return result


def _run_trace_result(
    *,
    config: CandidateThresholdSweepConfig,
    training_metrics_artifact: Path | None,
    training_error: str | None,
    evaluation_artifact: Path | None,
    evaluation_error: str | None,
    model_artifact: Path | None,
    candidate: dict[str, Any],
    training_payload: dict[str, Any],
    source: CandidateReplaySource,
    gpu: GpuReadiness,
    available_backends: tuple[str, ...],
    selected_backend: str | None,
    trace_artifact: Path,
    probability_runner: CandidateProbabilityRunner | None,
) -> BoundedCandidateProbabilityTraceResult:
    if evaluation_error is not None:
        return _prepared_trace_result(
            config=config,
            training_metrics_artifact=training_metrics_artifact,
            evaluation_artifact=evaluation_artifact,
            model_artifact=model_artifact,
            candidate=candidate,
            source=source,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=selected_backend,
            trace_artifact=trace_artifact,
            reason=evaluation_error,
        )
    if training_error is not None:
        return _prepared_trace_result(
            config=config,
            training_metrics_artifact=training_metrics_artifact,
            evaluation_artifact=evaluation_artifact,
            model_artifact=model_artifact,
            candidate=candidate,
            source=source,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=selected_backend,
            trace_artifact=trace_artifact,
            reason=training_error,
        )
    expected_feature_names = _feature_names_from_training_payload(training_payload)
    if expected_feature_names and expected_feature_names != source.dataset.feature_names:
        return _prepared_trace_result(
            config=config,
            training_metrics_artifact=training_metrics_artifact,
            evaluation_artifact=evaluation_artifact,
            model_artifact=model_artifact,
            candidate=candidate,
            source=source,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=selected_backend,
            trace_artifact=trace_artifact,
            reason=(
                "training/trace feature names mismatch: "
                f"{expected_feature_names} != {source.dataset.feature_names}"
            ),
        )
    try:
        inference_source = CandidateReplaySource(
            bars=source.bars,
            dataset=apply_training_payload_feature_normalization(
                source.dataset,
                training_payload,
            ),
            data_source=source.data_source,
        )
    except ValueError as exc:
        return _prepared_trace_result(
            config=config,
            training_metrics_artifact=training_metrics_artifact,
            evaluation_artifact=evaluation_artifact,
            model_artifact=model_artifact,
            candidate=candidate,
            source=source,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=selected_backend,
            trace_artifact=trace_artifact,
            reason=f"candidate feature preprocessing unavailable: {exc}",
        )
    if model_artifact is None or not model_artifact.exists():
        return _prepared_trace_result(
            config=config,
            training_metrics_artifact=training_metrics_artifact,
            evaluation_artifact=evaluation_artifact,
            model_artifact=model_artifact,
            candidate=candidate,
            source=source,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=selected_backend,
            trace_artifact=trace_artifact,
            reason="candidate model artifact is missing",
        )
    if probability_runner is None and not gpu.available:
        return _prepared_trace_result(
            config=config,
            training_metrics_artifact=training_metrics_artifact,
            evaluation_artifact=evaluation_artifact,
            model_artifact=model_artifact,
            candidate=candidate,
            source=source,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=selected_backend,
            trace_artifact=trace_artifact,
            reason=f"GPU readiness unavailable: {gpu.detail}",
        )
    if len(inference_source.dataset.labels) < config.min_examples:
        return _prepared_trace_result(
            config=config,
            training_metrics_artifact=training_metrics_artifact,
            evaluation_artifact=evaluation_artifact,
            model_artifact=model_artifact,
            candidate=candidate,
            source=source,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=selected_backend,
            trace_artifact=trace_artifact,
            reason=(
                "insufficient trace examples: "
                f"{len(inference_source.dataset.labels)} < {config.min_examples}"
            ),
        )
    if probability_runner is None and selected_backend is None:
        return _prepared_trace_result(
            config=config,
            training_metrics_artifact=training_metrics_artifact,
            evaluation_artifact=evaluation_artifact,
            model_artifact=model_artifact,
            candidate=candidate,
            source=source,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=None,
            trace_artifact=trace_artifact,
            reason="no operator-approved research GPU probability backend installed",
        )

    runner = probability_runner or _run_torch_cuda_candidate_probabilities
    try:
        probability_result = runner(inference_source.dataset, model_artifact, training_payload)
        probabilities = _probabilities_from_result(probability_result)
    except Exception as exc:  # noqa: BLE001 - trace jobs record backend failures.
        return _prepared_trace_result(
            config=config,
            training_metrics_artifact=training_metrics_artifact,
            evaluation_artifact=evaluation_artifact,
            model_artifact=model_artifact,
            candidate=candidate,
            source=source,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=selected_backend,
            trace_artifact=trace_artifact,
            reason=f"bounded probability trace unavailable: {exc}",
        )
    if len(probabilities) != len(inference_source.dataset.labels):
        return _prepared_trace_result(
            config=config,
            training_metrics_artifact=training_metrics_artifact,
            evaluation_artifact=evaluation_artifact,
            model_artifact=model_artifact,
            candidate=candidate,
            source=source,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=selected_backend,
            trace_artifact=trace_artifact,
            reason="probability count must match trace examples",
        )
    return BoundedCandidateProbabilityTraceResult(
        run_id=config.run_id,
        status="probability_traced_only",
        checked_at=datetime.now(UTC),
        gpu=gpu,
        reason="bounded candidate probability trace completed",
        available_backends=available_backends,
        selected_backend=selected_backend,
        training_metrics_artifact=training_metrics_artifact,
        evaluation_artifact=evaluation_artifact,
        model_artifact=model_artifact,
        candidate_experiment_id=candidate.get("candidate_experiment_id"),
        candidate_parameters=candidate.get("candidate_parameters") or {},
        data_source=inference_source.data_source,
        symbol=inference_source.dataset.symbol,
        market=inference_source.dataset.market,
        timeframe=inference_source.dataset.timeframe,
        bars_seen=inference_source.dataset.bars_seen,
        examples_seen=len(inference_source.dataset.labels),
        lookback=inference_source.dataset.lookback,
        entries=_trace_entries(inference_source, probabilities),
        probability_metrics=_probability_metrics(probabilities, probability_result),
        trace_artifact=trace_artifact,
    )


def _prepared_trace_result(
    *,
    config: CandidateThresholdSweepConfig,
    training_metrics_artifact: Path | None,
    evaluation_artifact: Path | None,
    model_artifact: Path | None,
    candidate: dict[str, Any],
    source: CandidateReplaySource,
    gpu: GpuReadiness,
    available_backends: tuple[str, ...],
    selected_backend: str | None,
    trace_artifact: Path,
    reason: str,
) -> BoundedCandidateProbabilityTraceResult:
    return BoundedCandidateProbabilityTraceResult(
        run_id=config.run_id,
        status="prepared_not_traced",
        checked_at=datetime.now(UTC),
        gpu=gpu,
        reason=reason,
        available_backends=available_backends,
        selected_backend=selected_backend,
        training_metrics_artifact=training_metrics_artifact,
        evaluation_artifact=evaluation_artifact,
        model_artifact=model_artifact,
        candidate_experiment_id=candidate.get("candidate_experiment_id"),
        candidate_parameters=candidate.get("candidate_parameters") or {},
        data_source=source.data_source,
        symbol=source.dataset.symbol,
        market=source.dataset.market,
        timeframe=source.dataset.timeframe,
        bars_seen=source.dataset.bars_seen,
        examples_seen=len(source.dataset.labels),
        lookback=source.dataset.lookback,
        entries=(),
        probability_metrics={},
        trace_artifact=trace_artifact,
    )


def _load_or_run_trace(
    *,
    config: CandidateThresholdSweepConfig,
    artifact_root: Path,
    repo_root: Path | None,
    probability_trace_artifact: Path | None,
    training_metrics_artifact: Path | None,
    evaluation_artifact: Path | None,
    model_artifact: Path | None,
    yahoo_snapshot: Path | None,
    symbol: str | None,
    gpu: GpuReadiness,
    probability_runner: CandidateProbabilityRunner | None,
) -> tuple[dict[str, Any], BoundedCandidateProbabilityTraceResult | None, Path | None, str | None]:
    if probability_trace_artifact is not None:
        payload, error = _read_trace_artifact(probability_trace_artifact)
        if error is None:
            error = _trace_payload_error(payload)
        return payload, None, probability_trace_artifact, error
    trace = run_bounded_candidate_probability_trace(
        config=config,
        artifact_root=artifact_root,
        repo_root=repo_root,
        training_metrics_artifact=training_metrics_artifact,
        evaluation_artifact=evaluation_artifact,
        model_artifact=model_artifact,
        yahoo_snapshot=yahoo_snapshot,
        symbol=symbol,
        gpu=gpu,
        probability_runner=probability_runner,
    )
    payload, error = _read_trace_artifact(trace.trace_artifact)
    if error is None:
        error = _trace_payload_error(payload)
    return payload, trace, trace.trace_artifact, error


def _run_threshold_variants(
    *,
    config: CandidateThresholdSweepConfig,
    artifact_root: Path,
    output_dir: Path,
    trace_payload: dict[str, Any],
    source: CandidateReplaySource,
    baseline_metrics: dict[str, Any],
    gpu: GpuReadiness,
) -> tuple[CandidateThresholdSweepVariant, ...]:
    probabilities = _probabilities_from_trace_payload(trace_payload)
    model_artifact = _path_from_payload(trace_payload, "model_artifact") or Path("missing-model")
    variants: list[CandidateThresholdSweepVariant] = []
    for ordinal, (buy_threshold, sell_threshold) in enumerate(config.threshold_pairs, start=1):
        variant_id = _threshold_variant_id(ordinal, buy_threshold, sell_threshold)
        threshold_error = _threshold_pair_error(buy_threshold, sell_threshold)
        variant_dir = output_dir / "variants" / variant_id
        variant_dir.mkdir(parents=True, exist_ok=True)
        if threshold_error is not None:
            variants.append(
                _prepared_variant(
                    variant_id=variant_id,
                    buy_threshold=buy_threshold,
                    sell_threshold=sell_threshold,
                    reason=threshold_error,
                    events_artifact=None,
                )
            )
            continue
        event_store = _fresh_event_store(variant_dir)
        replay = _run_local_paper_replay(
            config=CandidateReplayConfig(
                run_id=f"{config.run_id}-{variant_id}",
                max_bars=config.max_bars,
                min_examples=config.min_examples,
                buy_threshold=buy_threshold,
                sell_threshold=sell_threshold,
                sample_seed=config.sample_seed,
                starting_cash=config.starting_cash,
                quantity=config.quantity,
                fee_bps=config.fee_bps,
                slippage_bps=config.slippage_bps,
            ),
            training_metrics_artifact=_path_from_payload(
                trace_payload,
                "training_metrics_artifact",
            ),
            evaluation_artifact=_path_from_payload(trace_payload, "evaluation_artifact"),
            model_artifact=model_artifact,
            candidate={
                "candidate_experiment_id": trace_payload.get("candidate_experiment_id"),
                "candidate_parameters": _payload_dict(trace_payload, "candidate_parameters"),
            },
            source=source,
            probabilities=probabilities,
            probability_result=_probability_result_from_trace(trace_payload),
            gpu=gpu,
            available_backends=tuple(trace_payload.get("available_backends") or ()),
            selected_backend=str(trace_payload.get("selected_backend") or "trace"),
            replay_artifact=variant_dir / "metrics.json",
            event_store=event_store,
            record_decision_events=False,
        )
        events_artifact = variant_dir / "events.jsonl"
        fill_events = _local_paper_fill_events(event_store)
        if len(fill_events) != replay.replay_fill_count:
            raise RuntimeError("threshold sweep fill count must match local paper replay")
        variants.append(
            CandidateThresholdSweepVariant(
                variant_id=variant_id,
                status="candidate_replayed_only",
                reason="threshold replay completed from probability trace",
                buy_threshold=buy_threshold,
                sell_threshold=sell_threshold,
                decisions_seen=replay.decisions_seen,
                order_intents_seen=replay.order_intents_seen,
                skipped_non_contiguous=replay.skipped_non_contiguous,
                trade_count=len(replay.trades),
                replay_fill_count=replay.replay_fill_count,
                event_count=replay.event_count,
                ending_cash=replay.ending_cash,
                equity=replay.equity,
                pnl=replay.pnl,
                max_drawdown=replay.max_drawdown,
                final_position=replay.final_position,
                replay_final_position=replay.replay_final_position,
                deltas=_variant_deltas(replay, baseline_metrics),
                events_artifact=str(events_artifact),
            )
        )
    return tuple(variants)


def _trace_entries(
    source: CandidateReplaySource,
    probabilities: tuple[float, ...],
) -> tuple[CandidateProbabilityTraceEntry, ...]:
    ordered = list(source.bars)
    entries: list[CandidateProbabilityTraceEntry] = []
    for offset, probability in enumerate(probabilities):
        index = source.dataset.lookback + offset
        signal_bar = ordered[index]
        execution_bar = ordered[index + 1]
        entries.append(
            CandidateProbabilityTraceEntry(
                offset=offset,
                probability=probability,
                signal_bar_start=signal_bar.start_ts,
                signal_bar_end=signal_bar.end_ts,
                execution_bar_start=execution_bar.start_ts,
                execution_bar_end=execution_bar.end_ts,
                signal_close=signal_bar.close,
                execution_open=execution_bar.open,
                execution_close=execution_bar.close,
                contiguous=execution_bar.start_ts == signal_bar.end_ts,
            )
        )
    return tuple(entries)


def _candidate_probability_trace_payload(
    result: BoundedCandidateProbabilityTraceResult,
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
            "available_backends": result.available_backends,
            "selected_backend": result.selected_backend,
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
            "candidate_experiment_id": result.candidate_experiment_id,
            "candidate_parameters": result.candidate_parameters,
            "data_source": result.data_source,
            "symbol": result.symbol,
            "market": result.market,
            "timeframe": result.timeframe,
            "bars_seen": result.bars_seen,
            "examples_seen": result.examples_seen,
            "lookback": result.lookback,
            "entries": result.entries,
            "probability_metrics": result.probability_metrics,
            "artifacts": {
                "probability_trace": str(result.trace_artifact),
                "source_model": None
                if result.model_artifact is None
                else str(result.model_artifact),
            },
            "artifact_policy": {
                "root": str(artifact_root),
                "repo_storage_allowed": False,
            },
        }
    )


def _candidate_threshold_sweep_payload(
    result: BoundedCandidateThresholdSweepResult,
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
            "probability_trace_artifact": (
                None
                if result.probability_trace_artifact is None
                else str(result.probability_trace_artifact)
            ),
            "comparison_artifact": (
                None if result.comparison_artifact is None else str(result.comparison_artifact)
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
            "baseline_metrics": result.baseline_metrics,
            "variants": result.variants,
            "variant_count": len(result.variants),
            "completed_variant_count": sum(
                1 for variant in result.variants if variant.status == "candidate_replayed_only"
            ),
            "thresholds": result.thresholds,
            "artifacts": {
                "sweep": str(result.sweep_artifact),
                "probability_trace": None
                if result.probability_trace_artifact is None
                else str(result.probability_trace_artifact),
                "comparison": None
                if result.comparison_artifact is None
                else str(result.comparison_artifact),
            },
            "artifact_policy": {
                "root": str(artifact_root),
                "repo_storage_allowed": False,
            },
        }
    )


def _read_trace_artifact(path: Path) -> tuple[dict[str, Any], str | None]:
    if not path.exists():
        return {}, f"candidate probability trace artifact is missing: {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, f"candidate probability trace artifact is unreadable: {exc}"
    if not isinstance(payload, dict):
        return {}, "candidate probability trace artifact must contain a JSON object"
    return payload, None


def _read_comparison_artifact(path: Path | None) -> tuple[dict[str, Any], str | None]:
    if path is None:
        return {}, "candidate replay comparison artifact is required"
    if not path.exists():
        return {}, f"candidate replay comparison artifact is missing: {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, f"candidate replay comparison artifact is unreadable: {exc}"
    if not isinstance(payload, dict):
        return {}, "candidate replay comparison artifact must contain a JSON object"
    return payload, None


def _baseline_metrics_from_comparison_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("baseline_metrics"), dict):
        return dict(payload["baseline_metrics"])
    comparison = payload.get("candidate_replay_comparison")
    if isinstance(comparison, dict) and isinstance(comparison.get("baseline_metrics"), dict):
        return dict(comparison["baseline_metrics"])
    return {}


def _load_aligned_source_from_trace(
    *,
    config: CandidateThresholdSweepConfig,
    trace_payload: dict[str, Any],
    yahoo_snapshot: Path | None,
    symbol: str | None,
) -> tuple[CandidateReplaySource, dict[str, Any]]:
    candidate = {
        "candidate_experiment_id": trace_payload.get("candidate_experiment_id"),
        "candidate_parameters": _payload_dict(trace_payload, "candidate_parameters"),
    }
    source = _load_replay_source(
        config=_candidate_replay_config(config, run_id=f"{config.run_id}-sweep-source"),
        candidate=candidate,
        yahoo_snapshot=yahoo_snapshot,
        symbol=symbol or _payload_string(trace_payload, "symbol"),
    )
    return source, _trace_source_alignment(trace_payload, source)


def _trace_source_alignment(
    trace_payload: dict[str, Any],
    source: CandidateReplaySource,
) -> dict[str, Any]:
    entries = trace_payload.get("entries")
    entry_count = len(entries) if isinstance(entries, list) else 0
    bars_match = _int_from_payload(trace_payload.get("bars_seen")) == len(source.bars)
    examples_match = entry_count == len(source.dataset.labels)
    symbol_match = _normalized(trace_payload.get("symbol")) == source.dataset.symbol
    market_match = _normalized(trace_payload.get("market")) == source.dataset.market
    timeframe_match = str(trace_payload.get("timeframe") or "") == str(source.dataset.timeframe)
    lookback_match = _int_from_payload(trace_payload.get("lookback")) == source.dataset.lookback
    return {
        "same_trace_evidence": (
            bars_match
            and examples_match
            and symbol_match
            and market_match
            and timeframe_match
            and lookback_match
        ),
        "bars_seen_match": bars_match,
        "examples_seen_match": examples_match,
        "symbol_match": symbol_match,
        "market_match": market_match,
        "timeframe_match": timeframe_match,
        "lookback_match": lookback_match,
        "data_source_string_match": str(trace_payload.get("data_source") or "")
        == source.data_source,
        "trace_data_source": trace_payload.get("data_source"),
        "sweep_data_source": source.data_source,
        "note": (
            "data_source strings may differ across host and Docker mounts; "
            "same_trace_evidence uses symbol, market, timeframe, bars, examples, and lookback"
        ),
    }


def _sweep_status_and_reason(
    *,
    trace_error: str | None,
    comparison_error: str | None,
    source_alignment: dict[str, Any],
    variants: tuple[CandidateThresholdSweepVariant, ...],
) -> tuple[CandidateThresholdSweepStatus, str]:
    if trace_error is not None:
        return "prepared_not_swept", trace_error
    if comparison_error is not None:
        return "prepared_not_swept", comparison_error
    if not source_alignment["same_trace_evidence"]:
        return "prepared_not_swept", "probability trace does not match sweep bars"
    if not any(variant.status == "candidate_replayed_only" for variant in variants):
        return "prepared_not_swept", "no valid threshold pair replayed"
    return (
        "candidate_swept_only",
        "bounded candidate threshold sweep completed without promotion decision",
    )


def _candidate_replay_config(
    config: CandidateThresholdSweepConfig,
    *,
    run_id: str,
) -> CandidateReplayConfig:
    return CandidateReplayConfig(
        run_id=run_id,
        max_bars=config.max_bars,
        min_examples=config.min_examples,
        buy_threshold=0.55,
        sell_threshold=0.45,
        sample_seed=config.sample_seed,
        starting_cash=config.starting_cash,
        quantity=config.quantity,
        fee_bps=config.fee_bps,
        slippage_bps=config.slippage_bps,
    )


def _probabilities_from_trace_payload(payload: dict[str, Any]) -> tuple[float, ...]:
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return ()
    ordered = sorted(
        (entry for entry in entries if isinstance(entry, dict)),
        key=lambda item: int(item.get("offset", 0)),
    )
    return tuple(float(entry["probability"]) for entry in ordered)


def _probability_result_from_trace(payload: dict[str, Any]) -> dict[str, Any]:
    metrics = payload.get("probability_metrics")
    result = dict(metrics) if isinstance(metrics, dict) else {}
    result["operation"] = "threshold_sweep_from_probability_trace"
    result["probabilities"] = _probabilities_from_trace_payload(payload)
    result["candidate_experiment_id"] = payload.get("candidate_experiment_id")
    return result


def _variant_deltas(replay: Any, baseline_metrics: dict[str, Any]) -> dict[str, Any]:
    baseline_pnl = _decimal_from_payload(baseline_metrics.get("pnl"))
    baseline_drawdown = _decimal_from_payload(baseline_metrics.get("max_drawdown"))
    baseline_equity = _decimal_from_payload(baseline_metrics.get("equity"))
    baseline_final_position = _decimal_from_payload(baseline_metrics.get("final_position"))
    baseline_trade_count = _int_from_payload(baseline_metrics.get("trade_count"))
    baseline_fill_count = _int_from_payload(baseline_metrics.get("replay_fill_count"))
    baseline_event_count = _int_from_payload(baseline_metrics.get("event_count"))
    return to_jsonable(
        {
            "candidate_minus_baseline_pnl": None
            if baseline_pnl is None
            else replay.pnl - baseline_pnl,
            "candidate_minus_baseline_max_drawdown": None
            if baseline_drawdown is None
            else replay.max_drawdown - baseline_drawdown,
            "candidate_minus_baseline_equity": None
            if baseline_equity is None
            else replay.equity - baseline_equity,
            "candidate_minus_baseline_final_position": None
            if baseline_final_position is None
            else replay.final_position - baseline_final_position,
            "candidate_minus_baseline_trade_count": None
            if baseline_trade_count is None
            else len(replay.trades) - baseline_trade_count,
            "candidate_minus_baseline_replay_fill_count": None
            if baseline_fill_count is None
            else replay.replay_fill_count - baseline_fill_count,
            "candidate_minus_baseline_event_count": None
            if baseline_event_count is None
            else replay.event_count - baseline_event_count,
            "comparison_is_descriptive": True,
            "promotion_gate": False,
        }
    )


def _prepared_variant(
    *,
    variant_id: str,
    buy_threshold: float,
    sell_threshold: float,
    reason: str,
    events_artifact: str | None,
) -> CandidateThresholdSweepVariant:
    return CandidateThresholdSweepVariant(
        variant_id=variant_id,
        status="prepared_not_replayed",
        reason=reason,
        buy_threshold=buy_threshold,
        sell_threshold=sell_threshold,
        decisions_seen=0,
        order_intents_seen=0,
        skipped_non_contiguous=0,
        trade_count=0,
        replay_fill_count=0,
        event_count=0,
        ending_cash=Decimal("0"),
        equity=Decimal("0"),
        pnl=Decimal("0"),
        max_drawdown=Decimal("0"),
        final_position=Decimal("0"),
        replay_final_position=Decimal("0"),
        deltas={},
        events_artifact=events_artifact,
    )


def _threshold_pair_error(buy_threshold: float, sell_threshold: float) -> str | None:
    if not 0 < sell_threshold < buy_threshold < 1:
        return "thresholds must satisfy 0 < sell < buy < 1"
    return None


def _threshold_variant_id(ordinal: int, buy_threshold: float, sell_threshold: float) -> str:
    buy = f"{buy_threshold:.3f}".replace(".", "p")
    sell = f"{sell_threshold:.3f}".replace(".", "p")
    return f"t{ordinal:02d}_b{buy}_s{sell}"


def _sweep_threshold_payload(config: CandidateThresholdSweepConfig) -> dict[str, Any]:
    return {
        "threshold_pairs": [
            {
                "buy_threshold": f"{buy:.6f}",
                "sell_threshold": f"{sell:.6f}",
            }
            for buy, sell in config.threshold_pairs
        ],
        "quantity": str(config.quantity),
        "starting_cash": str(config.starting_cash),
        "fee_bps": str(config.fee_bps),
        "slippage_bps": str(config.slippage_bps),
        "promotion_gate": "false",
    }


def _trace_status_from_payload(
    payload: dict[str, Any],
) -> CandidateProbabilityTraceStatus | None:
    value = payload.get("status")
    if value in {"probability_traced_only", "prepared_not_traced"}:
        return value  # type: ignore[return-value]
    return None


def _trace_payload_error(payload: dict[str, Any]) -> str | None:
    if payload.get("status") == "probability_traced_only":
        return None
    return _payload_string(payload, "reason") or "candidate probability trace was not completed"


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


def _normalized(value: object) -> str:
    return str(value or "").upper()


def _int_from_payload(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _decimal_from_payload(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def parse_threshold_pairs(values: list[str] | None) -> tuple[tuple[float, float], ...]:
    if not values:
        return DEFAULT_THRESHOLD_PAIRS
    pairs: list[tuple[float, float]] = []
    for value in values:
        buy, separator, sell = value.partition(":")
        if not separator:
            raise ValueError("threshold pairs must use BUY:SELL format")
        pairs.append((float(buy), float(sell)))
    return tuple(pairs)
