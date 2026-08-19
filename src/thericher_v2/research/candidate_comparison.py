"""Descriptive comparison of candidate replay against a momentum baseline."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from thericher_v2.contracts import SCHEMA_VERSION, OrderIntent, Timeframe
from thericher_v2.ensemble import decide
from thericher_v2.execution import LOCAL_PAPER_SOURCE, EmergencyStore, LocalPaperBroker
from thericher_v2.models import MomentumModel
from thericher_v2.serialization import to_jsonable
from thericher_v2.state import EventStore

from .candidate_evaluation import (
    _candidate_from_training_payload,
    _read_training_metrics,
)
from .candidate_replay import (
    CandidateProbabilityRunner,
    CandidateReplayConfig,
    CandidateReplaySource,
    _load_replay_source,
    _local_paper_fill_events,
    _max_drawdown_from_local_paper,
    run_bounded_candidate_replay,
)
from .candidate_training import GpuReadiness, _reject_repo_artifact_path, detect_gpu_readiness

CandidateReplayComparisonStatus = Literal["candidate_compared_only", "prepared_not_compared"]
MomentumBaselineStatus = Literal["baseline_replayed_only", "prepared_not_replayed"]
DEFAULT_CANDIDATE_REPLAY_COMPARISON_RUN_ID = "bounded-candidate-replay-comparison"
MAX_CANDIDATE_REPLAY_COMPARISON_BARS = 512
BASELINE_SOURCE = "momentum_baseline"


@dataclass(frozen=True)
class CandidateReplayComparisonConfig:
    run_id: str = DEFAULT_CANDIDATE_REPLAY_COMPARISON_RUN_ID
    max_bars: int = 180
    min_bars: int = 8
    buy_threshold: float = 0.55
    sell_threshold: float = 0.45
    sample_seed: int = 37
    starting_cash: Decimal = Decimal("10000")
    quantity: Decimal = Decimal("1")
    fee_bps: Decimal = Decimal("1")
    slippage_bps: Decimal = Decimal("0")
    momentum_lookback: int = 3
    momentum_buy_threshold_bps: Decimal = Decimal("5")
    momentum_sell_threshold_bps: Decimal = Decimal("-5")
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("run_id is required")
        if self.max_bars <= 0:
            raise ValueError("max_bars must be positive")
        if self.max_bars > MAX_CANDIDATE_REPLAY_COMPARISON_BARS:
            raise ValueError(
                f"max_bars must be <= {MAX_CANDIDATE_REPLAY_COMPARISON_BARS}"
            )
        if self.min_bars <= 0:
            raise ValueError("min_bars must be positive")
        if not 0 < self.sell_threshold < self.buy_threshold < 1:
            raise ValueError("thresholds must satisfy 0 < sell < buy < 1")
        if self.starting_cash <= 0:
            raise ValueError("starting_cash must be positive")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.fee_bps < 0:
            raise ValueError("fee_bps must be non-negative")
        if self.slippage_bps < 0:
            raise ValueError("slippage_bps must be non-negative")
        if self.momentum_lookback <= 0:
            raise ValueError("momentum_lookback must be positive")


@dataclass(frozen=True)
class MomentumBaselineTrade:
    client_order_id: str
    decision_id: str
    side: str
    quantity: Decimal
    price: Decimal
    fee: Decimal
    signal_bar_end: datetime
    filled_at: datetime
    source: str = LOCAL_PAPER_SOURCE
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "signal_bar_end", self.signal_bar_end.astimezone(UTC))
        object.__setattr__(self, "filled_at", self.filled_at.astimezone(UTC))


@dataclass(frozen=True)
class MomentumBaselineResult:
    run_id: str
    status: MomentumBaselineStatus
    reason: str
    data_source: str
    symbol: str | None
    market: str | None
    timeframe: Timeframe | None
    bars_seen: int
    decisions_seen: int
    order_intents_seen: int
    skipped_non_contiguous: int
    trades: tuple[MomentumBaselineTrade, ...]
    starting_cash: Decimal
    ending_cash: Decimal
    final_position: Decimal
    replay_final_position: Decimal
    last_price: Decimal
    equity: Decimal
    pnl: Decimal
    max_drawdown: Decimal
    replay_fill_count: int
    event_count: int
    parameters: dict[str, Any]
    baseline_events: Path
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class BoundedCandidateReplayComparisonResult:
    run_id: str
    status: CandidateReplayComparisonStatus
    checked_at: datetime
    gpu: GpuReadiness
    reason: str
    training_metrics_artifact: Path | None
    evaluation_artifact: Path | None
    model_artifact: Path | None
    candidate_experiment_id: str | None
    candidate_parameters: dict[str, Any]
    candidate_replay_artifact: Path | None
    comparison_artifact: Path
    baseline_events: Path
    data_source: str
    symbol: str | None
    market: str | None
    timeframe: Timeframe | None
    bars_seen: int
    candidate_status: str | None
    baseline_status: MomentumBaselineStatus
    candidate_metrics: dict[str, Any]
    baseline_metrics: dict[str, Any]
    source_alignment: dict[str, Any]
    deltas: dict[str, Any]
    thresholds: dict[str, Any]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_at", self.checked_at.astimezone(UTC))


def run_bounded_candidate_replay_comparison(
    *,
    config: CandidateReplayComparisonConfig | None = None,
    artifact_root: Path,
    repo_root: Path | None = None,
    candidate_replay_artifact: Path | None = None,
    training_metrics_artifact: Path | None = None,
    evaluation_artifact: Path | None = None,
    model_artifact: Path | None = None,
    yahoo_snapshot: Path | None = None,
    symbol: str | None = None,
    gpu: GpuReadiness | None = None,
    probability_runner: CandidateProbabilityRunner | None = None,
) -> BoundedCandidateReplayComparisonResult:
    config = config or CandidateReplayComparisonConfig()
    _reject_repo_artifact_path(artifact_root, repo_root)
    output_dir = artifact_root / "candidate-replay-comparison" / config.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    _clear_baseline_event_artifacts(output_dir)
    comparison_artifact = output_dir / "metrics.json"
    gpu = gpu or detect_gpu_readiness()

    candidate_payload, selected_replay_artifact, candidate_error = _load_or_run_candidate_replay(
        config=config,
        artifact_root=artifact_root,
        repo_root=repo_root,
        candidate_replay_artifact=candidate_replay_artifact,
        training_metrics_artifact=training_metrics_artifact,
        evaluation_artifact=evaluation_artifact,
        model_artifact=model_artifact,
        yahoo_snapshot=yahoo_snapshot,
        symbol=symbol,
        gpu=gpu,
        probability_runner=probability_runner,
    )
    candidate = _candidate_from_inputs(training_metrics_artifact, candidate_payload)
    source = _load_replay_source(
        config=_candidate_replay_config(config, run_id=f"{config.run_id}-source"),
        candidate=candidate,
        yahoo_snapshot=yahoo_snapshot,
        symbol=symbol or _payload_string(candidate_payload, "symbol"),
    )
    candidate_metrics = _candidate_metrics_from_payload(candidate_payload)
    source_alignment = _source_alignment(candidate_payload, source)
    candidate_replay_ready = (
        candidate_error is None
        and candidate_metrics.get("status") == "candidate_replayed_only"
        and source_alignment["same_bar_evidence"]
    )
    baseline = (
        _run_momentum_baseline(
            config=config,
            source=source,
            output_dir=output_dir,
        )
        if candidate_replay_ready
        else _prepared_baseline_result(
            config=config,
            source=source,
            baseline_events=output_dir / "baseline-events.jsonl",
            reason=(
                "baseline replay deferred until candidate replay evidence is "
                "completed and aligned"
            ),
        )
    )
    status, reason = _comparison_status_and_reason(
        candidate_error=candidate_error,
        candidate_metrics=candidate_metrics,
        baseline=baseline,
        source_alignment=source_alignment,
    )
    result = BoundedCandidateReplayComparisonResult(
        run_id=config.run_id,
        status=status,
        checked_at=datetime.now(UTC),
        gpu=gpu,
        reason=reason,
        training_metrics_artifact=training_metrics_artifact,
        evaluation_artifact=evaluation_artifact,
        model_artifact=model_artifact or _path_from_payload(candidate_payload, "model_artifact"),
        candidate_experiment_id=_payload_string(candidate_payload, "candidate_experiment_id"),
        candidate_parameters=_payload_dict(candidate_payload, "candidate_parameters"),
        candidate_replay_artifact=selected_replay_artifact,
        comparison_artifact=comparison_artifact,
        baseline_events=baseline.baseline_events,
        data_source=source.data_source,
        symbol=source.dataset.symbol or baseline.symbol,
        market=source.dataset.market or baseline.market,
        timeframe=source.dataset.timeframe or baseline.timeframe,
        bars_seen=len(source.bars),
        candidate_status=_payload_string(candidate_payload, "status"),
        baseline_status=baseline.status,
        candidate_metrics=candidate_metrics,
        baseline_metrics=_baseline_metrics_payload(baseline),
        source_alignment=source_alignment,
        deltas=_comparison_deltas(candidate_metrics, baseline),
        thresholds=_threshold_payload(config),
    )
    comparison_artifact.write_text(
        json.dumps(
            _candidate_replay_comparison_payload(result, artifact_root),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return result


def _load_or_run_candidate_replay(
    *,
    config: CandidateReplayComparisonConfig,
    artifact_root: Path,
    repo_root: Path | None,
    candidate_replay_artifact: Path | None,
    training_metrics_artifact: Path | None,
    evaluation_artifact: Path | None,
    model_artifact: Path | None,
    yahoo_snapshot: Path | None,
    symbol: str | None,
    gpu: GpuReadiness,
    probability_runner: CandidateProbabilityRunner | None,
) -> tuple[dict[str, Any], Path | None, str | None]:
    if candidate_replay_artifact is not None:
        payload, error = _read_candidate_replay_artifact(candidate_replay_artifact)
        return payload, candidate_replay_artifact, error

    replay = run_bounded_candidate_replay(
        config=_candidate_replay_config(
            config,
            run_id=f"{config.run_id}-candidate-replay",
        ),
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
    payload, error = _read_candidate_replay_artifact(replay.replay_artifact)
    return payload, replay.replay_artifact, error


def _run_momentum_baseline(
    *,
    config: CandidateReplayComparisonConfig,
    source: CandidateReplaySource,
    output_dir: Path,
) -> MomentumBaselineResult:
    baseline_events = output_dir / "baseline-events.jsonl"
    event_store = _fresh_baseline_event_store(output_dir)
    ordered = list(source.bars)
    model = MomentumModel(
        lookback=config.momentum_lookback,
        buy_threshold_bps=config.momentum_buy_threshold_bps,
        sell_threshold_bps=config.momentum_sell_threshold_bps,
    )
    min_bars = max(config.min_bars, model.lookback + 3)
    if len(ordered) < min_bars:
        return _prepared_baseline_result(
            config=config,
            source=source,
            baseline_events=baseline_events,
            reason=f"insufficient baseline bars: {len(ordered)} < {min_bars}",
        )

    broker = LocalPaperBroker(
        event_store=event_store,
        emergency_store=EmergencyStore(output_dir / "baseline-emergency.json"),
        starting_cash=config.starting_cash,
        fee_bps=config.fee_bps,
        slippage_bps=config.slippage_bps,
    )
    trades: list[MomentumBaselineTrade] = []
    decisions_seen = 0
    order_intents_seen = 0
    skipped_non_contiguous = 0
    for index in range(model.lookback + 1, len(ordered) - 1):
        signal_window = ordered[: index + 1]
        signal_bar = ordered[index]
        execution_bar = ordered[index + 1]
        prediction = model.predict(signal_window)
        decision = decide([prediction])
        decisions_seen += 1
        decision_id = _decision_id(config.run_id, signal_bar.symbol, signal_bar.end_ts)
        if execution_bar.start_ts != signal_bar.end_ts:
            skipped_non_contiguous += 1
            continue

        position = broker.account().quantity(market=signal_bar.market, symbol=signal_bar.symbol)
        if decision.action == "buy" and position <= 0:
            side = "buy"
        elif decision.action == "sell" and position > 0:
            side = "sell"
        else:
            continue

        order_intents_seen += 1
        order = OrderIntent(
            client_order_id=f"{config.run_id}-baseline-{order_intents_seen:04d}",
            symbol=signal_bar.symbol,
            market=signal_bar.market,
            side=side,
            quantity=config.quantity,
            limit_price=None,
            decision_id=decision_id,
            created_at=signal_bar.end_ts,
        )
        execution = broker.submit_and_fill_next_bar(
            order,
            signal_bar=signal_bar,
            execution_bar=execution_bar,
        )
        if execution.fill is None:
            continue
        trades.append(
            MomentumBaselineTrade(
                client_order_id=order.client_order_id,
                decision_id=decision_id,
                side=execution.fill.side,
                quantity=execution.fill.quantity,
                price=execution.fill.price,
                fee=execution.fill.fee,
                signal_bar_end=signal_bar.end_ts,
                filled_at=execution.fill.filled_at,
                source=execution.fill.source,
            )
        )

    all_fill_events = [
        event for event in event_store.iter_events() if event.event_type == "fill"
    ]
    if any(event.payload.get("source") != LOCAL_PAPER_SOURCE for event in all_fill_events):
        raise RuntimeError("baseline comparison only supports local_paper fills")
    fill_events = _local_paper_fill_events(event_store)
    if len(fill_events) != len(all_fill_events):
        raise RuntimeError("baseline fill count must match local_paper fill count")

    account = broker.account()
    market = ordered[-1].market
    symbol = ordered[-1].symbol
    final_position = account.quantity(market=market, symbol=symbol)
    last_price = ordered[-1].close
    equity = account.cash + final_position * last_price
    max_drawdown, replay_final_equity = _max_drawdown_from_local_paper(
        bars=ordered,
        fill_events=fill_events,
        starting_cash=config.starting_cash,
    )
    if replay_final_equity != equity:
        raise RuntimeError("baseline equity must reconcile with local paper replay")
    replay_state = event_store.replay()
    replay_final_position = replay_state.positions.get((market, symbol), Decimal("0"))
    return MomentumBaselineResult(
        run_id=config.run_id,
        status="baseline_replayed_only",
        reason="bounded momentum baseline local-paper replay completed",
        data_source=source.data_source,
        symbol=symbol,
        market=market,
        timeframe=ordered[-1].timeframe,
        bars_seen=len(ordered),
        decisions_seen=decisions_seen,
        order_intents_seen=order_intents_seen,
        skipped_non_contiguous=skipped_non_contiguous,
        trades=tuple(trades),
        starting_cash=config.starting_cash,
        ending_cash=account.cash,
        final_position=final_position,
        replay_final_position=replay_final_position,
        last_price=last_price,
        equity=equity,
        pnl=equity - config.starting_cash,
        max_drawdown=max_drawdown,
        replay_fill_count=len(fill_events),
        event_count=len(list(event_store.iter_events())),
        parameters=_baseline_parameters(config, model),
        baseline_events=baseline_events,
    )


def _prepared_baseline_result(
    *,
    config: CandidateReplayComparisonConfig,
    source: CandidateReplaySource,
    baseline_events: Path,
    reason: str,
) -> MomentumBaselineResult:
    symbol = source.dataset.symbol or None
    market = source.dataset.market or None
    timeframe = source.dataset.timeframe if source.dataset.symbol else None
    return MomentumBaselineResult(
        run_id=config.run_id,
        status="prepared_not_replayed",
        reason=reason,
        data_source=source.data_source,
        symbol=symbol,
        market=market,
        timeframe=timeframe,
        bars_seen=len(source.bars),
        decisions_seen=0,
        order_intents_seen=0,
        skipped_non_contiguous=0,
        trades=(),
        starting_cash=config.starting_cash,
        ending_cash=config.starting_cash,
        final_position=Decimal("0"),
        replay_final_position=Decimal("0"),
        last_price=Decimal("0"),
        equity=config.starting_cash,
        pnl=Decimal("0"),
        max_drawdown=Decimal("0"),
        replay_fill_count=0,
        event_count=0,
        parameters=_baseline_parameters(
            config,
            MomentumModel(
                lookback=config.momentum_lookback,
                buy_threshold_bps=config.momentum_buy_threshold_bps,
                sell_threshold_bps=config.momentum_sell_threshold_bps,
            ),
        ),
        baseline_events=baseline_events,
    )


def _candidate_replay_comparison_payload(
    result: BoundedCandidateReplayComparisonResult,
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
            "candidate_replay_artifact": (
                None
                if result.candidate_replay_artifact is None
                else str(result.candidate_replay_artifact)
            ),
            "data_source": result.data_source,
            "symbol": result.symbol,
            "market": result.market,
            "timeframe": result.timeframe,
            "bars_seen": result.bars_seen,
            "candidate_status": result.candidate_status,
            "baseline_status": result.baseline_status,
            "candidate_metrics": result.candidate_metrics,
            "baseline_metrics": result.baseline_metrics,
            "source_alignment": result.source_alignment,
            "deltas": result.deltas,
            "thresholds": result.thresholds,
            "artifacts": {
                "comparison": str(result.comparison_artifact),
                "candidate_replay": None
                if result.candidate_replay_artifact is None
                else str(result.candidate_replay_artifact),
                "baseline_events": str(result.baseline_events),
            },
            "artifact_policy": {
                "root": str(artifact_root),
                "repo_storage_allowed": False,
            },
        }
    )


def _read_candidate_replay_artifact(path: Path) -> tuple[dict[str, Any], str | None]:
    if not path.exists():
        return {}, f"candidate replay artifact is missing: {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, f"candidate replay artifact is unreadable: {exc}"
    if not isinstance(payload, dict):
        return {}, "candidate replay artifact must contain a JSON object"
    return payload, None


def _candidate_from_inputs(
    training_metrics_artifact: Path | None,
    candidate_payload: dict[str, Any],
) -> dict[str, Any]:
    training_payload, training_error = _read_training_metrics(training_metrics_artifact)
    if training_error is None:
        candidate = _candidate_from_training_payload(training_payload)
        if candidate.get("candidate_experiment_id") or candidate.get("candidate_parameters"):
            return candidate
    parameters = candidate_payload.get("candidate_parameters")
    return {
        "candidate_experiment_id": candidate_payload.get("candidate_experiment_id"),
        "candidate_parameters": parameters if isinstance(parameters, dict) else {},
    }


def _candidate_replay_config(
    config: CandidateReplayComparisonConfig,
    *,
    run_id: str,
) -> CandidateReplayConfig:
    return CandidateReplayConfig(
        run_id=run_id,
        max_bars=config.max_bars,
        min_examples=max(1, config.min_bars - 2),
        buy_threshold=config.buy_threshold,
        sell_threshold=config.sell_threshold,
        sample_seed=config.sample_seed,
        starting_cash=config.starting_cash,
        quantity=config.quantity,
        fee_bps=config.fee_bps,
        slippage_bps=config.slippage_bps,
    )


def _clear_baseline_event_artifacts(output_dir: Path) -> None:
    for filename in (
        "baseline-emergency.json",
        "baseline-events.jsonl",
        "baseline-state.sqlite",
        "baseline-state.sqlite-journal",
        "baseline-state.sqlite-shm",
        "baseline-state.sqlite-wal",
    ):
        path = output_dir / filename
        if path.is_file() or path.is_symlink():
            path.unlink()


def _fresh_baseline_event_store(output_dir: Path) -> EventStore:
    _clear_baseline_event_artifacts(output_dir)
    db_path = output_dir / "baseline-state.sqlite"
    jsonl_path = output_dir / "baseline-events.jsonl"
    return EventStore(db_path, jsonl_path)


def _comparison_status_and_reason(
    *,
    candidate_error: str | None,
    candidate_metrics: dict[str, Any],
    baseline: MomentumBaselineResult,
    source_alignment: dict[str, Any],
) -> tuple[CandidateReplayComparisonStatus, str]:
    if candidate_error is not None:
        return "prepared_not_compared", candidate_error
    if candidate_metrics.get("status") != "candidate_replayed_only":
        reason = candidate_metrics.get("reason") or "candidate replay was not completed"
        return "prepared_not_compared", f"candidate replay unavailable: {reason}"
    if not source_alignment["same_bar_evidence"]:
        return "prepared_not_compared", "candidate replay artifact does not match baseline bars"
    if baseline.status != "baseline_replayed_only":
        return "prepared_not_compared", baseline.reason
    return (
        "candidate_compared_only",
        "bounded candidate replay comparison completed without promotion decision",
    )


def _candidate_metrics_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    trades = payload.get("trades")
    trade_count = payload.get("trade_count")
    if trade_count is None and isinstance(trades, list):
        trade_count = len(trades)
    return {
        "status": payload.get("status"),
        "reason": payload.get("reason"),
        "data_source": payload.get("data_source"),
        "symbol": payload.get("symbol"),
        "market": payload.get("market"),
        "timeframe": payload.get("timeframe"),
        "bars_seen": payload.get("bars_seen"),
        "decisions_seen": payload.get("decisions_seen"),
        "order_intents_seen": payload.get("order_intents_seen"),
        "skipped_non_contiguous": payload.get("skipped_non_contiguous"),
        "trade_count": trade_count,
        "replay_fill_count": payload.get("replay_fill_count"),
        "event_count": payload.get("event_count"),
        "ending_cash": payload.get("ending_cash"),
        "equity": payload.get("equity"),
        "pnl": payload.get("pnl"),
        "max_drawdown": payload.get("max_drawdown"),
        "final_position": payload.get("final_position"),
        "replay_final_position": payload.get("replay_final_position"),
        "thresholds": payload.get("thresholds") or {},
        "probability_metrics": payload.get("probability_metrics") or {},
    }


def _baseline_metrics_payload(baseline: MomentumBaselineResult) -> dict[str, Any]:
    return to_jsonable(
        {
            "status": baseline.status,
            "reason": baseline.reason,
            "data_source": baseline.data_source,
            "symbol": baseline.symbol,
            "market": baseline.market,
            "timeframe": baseline.timeframe,
            "bars_seen": baseline.bars_seen,
            "decisions_seen": baseline.decisions_seen,
            "order_intents_seen": baseline.order_intents_seen,
            "skipped_non_contiguous": baseline.skipped_non_contiguous,
            "trade_count": len(baseline.trades),
            "trades": baseline.trades,
            "replay_fill_count": baseline.replay_fill_count,
            "event_count": baseline.event_count,
            "starting_cash": baseline.starting_cash,
            "ending_cash": baseline.ending_cash,
            "equity": baseline.equity,
            "pnl": baseline.pnl,
            "max_drawdown": baseline.max_drawdown,
            "final_position": baseline.final_position,
            "replay_final_position": baseline.replay_final_position,
            "last_price": baseline.last_price,
            "parameters": baseline.parameters,
            "baseline_events": str(baseline.baseline_events),
            "event_count_scope": "local_paper_order_fill_snapshot_events_only",
        }
    )


def _source_alignment(
    candidate_payload: dict[str, Any],
    source: CandidateReplaySource,
) -> dict[str, Any]:
    bars_match = _int_from_payload(candidate_payload.get("bars_seen")) == len(source.bars)
    symbol_match = _normalized(candidate_payload.get("symbol")) == source.dataset.symbol
    market_match = _normalized(candidate_payload.get("market")) == source.dataset.market
    timeframe_match = str(candidate_payload.get("timeframe") or "") == str(
        source.dataset.timeframe
    )
    data_source_match = str(candidate_payload.get("data_source") or "") == source.data_source
    return {
        "same_bar_evidence": bars_match and symbol_match and market_match and timeframe_match,
        "bars_seen_match": bars_match,
        "symbol_match": symbol_match,
        "market_match": market_match,
        "timeframe_match": timeframe_match,
        "data_source_string_match": data_source_match,
        "candidate_data_source": candidate_payload.get("data_source"),
        "baseline_data_source": source.data_source,
        "note": (
            "data_source strings may differ across host and Docker mounts; "
            "same_bar_evidence uses symbol, market, timeframe, and bars_seen"
        ),
    }


def _comparison_deltas(
    candidate_metrics: dict[str, Any],
    baseline: MomentumBaselineResult,
) -> dict[str, Any]:
    candidate_pnl = _decimal_from_payload(candidate_metrics.get("pnl"))
    candidate_drawdown = _decimal_from_payload(candidate_metrics.get("max_drawdown"))
    candidate_equity = _decimal_from_payload(candidate_metrics.get("equity"))
    candidate_final_position = _decimal_from_payload(candidate_metrics.get("final_position"))
    candidate_trade_count = _int_from_payload(candidate_metrics.get("trade_count"))
    candidate_fill_count = _int_from_payload(candidate_metrics.get("replay_fill_count"))
    candidate_event_count = _int_from_payload(candidate_metrics.get("event_count"))
    return to_jsonable(
        {
            "candidate_minus_baseline_pnl": None
            if candidate_pnl is None
            else candidate_pnl - baseline.pnl,
            "candidate_minus_baseline_max_drawdown": None
            if candidate_drawdown is None
            else candidate_drawdown - baseline.max_drawdown,
            "candidate_minus_baseline_equity": None
            if candidate_equity is None
            else candidate_equity - baseline.equity,
            "candidate_minus_baseline_final_position": None
            if candidate_final_position is None
            else candidate_final_position - baseline.final_position,
            "candidate_minus_baseline_trade_count": None
            if candidate_trade_count is None
            else candidate_trade_count - len(baseline.trades),
            "candidate_minus_baseline_replay_fill_count": None
            if candidate_fill_count is None
            else candidate_fill_count - baseline.replay_fill_count,
            "candidate_minus_baseline_event_count": None
            if candidate_event_count is None
            else candidate_event_count - baseline.event_count,
            "comparison_is_descriptive": True,
            "promotion_gate": False,
        }
    )


def _threshold_payload(config: CandidateReplayComparisonConfig) -> dict[str, Any]:
    return {
        "candidate_buy_threshold": f"{config.buy_threshold:.6f}",
        "candidate_sell_threshold": f"{config.sell_threshold:.6f}",
        "baseline_momentum_lookback": config.momentum_lookback,
        "baseline_buy_threshold_bps": str(config.momentum_buy_threshold_bps),
        "baseline_sell_threshold_bps": str(config.momentum_sell_threshold_bps),
        "quantity": str(config.quantity),
        "starting_cash": str(config.starting_cash),
        "fee_bps": str(config.fee_bps),
        "slippage_bps": str(config.slippage_bps),
        "promotion_gate": "false",
    }


def _baseline_parameters(
    config: CandidateReplayComparisonConfig,
    model: MomentumModel,
) -> dict[str, Any]:
    return {
        "model_id": model.model_id,
        "model_version": model.model_version,
        "lookback": model.lookback,
        "buy_threshold_bps": str(config.momentum_buy_threshold_bps),
        "sell_threshold_bps": str(config.momentum_sell_threshold_bps),
        "source": BASELINE_SOURCE,
    }


def _decision_id(run_id: str, symbol: str, signal_end: datetime) -> str:
    compact_ts = signal_end.strftime("%Y%m%dT%H%M%SZ")
    return f"{run_id}:baseline:{symbol}:{compact_ts}"


def _payload_string(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    text = str(value)
    return text or None


def _payload_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _path_from_payload(payload: dict[str, Any], key: str) -> Path | None:
    value = payload.get(key)
    if value:
        return Path(str(value))
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
