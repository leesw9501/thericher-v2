"""Broker-free local-paper replay for bounded candidate model output."""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from thericher_v2.contracts import SCHEMA_VERSION, Bar, OrderIntent, Timeframe
from thericher_v2.data import SampleBarProvider
from thericher_v2.execution import LOCAL_PAPER_SOURCE, EmergencyStore, LocalPaperBroker
from thericher_v2.serialization import to_jsonable
from thericher_v2.state import Event, EventStore

from .candidate_evaluation import (
    _candidate_from_training_payload,
    _feature_names_from_training_payload,
    _model_artifact_from_training_payload,
    _probabilities_from_result,
    _read_training_metrics,
    _run_torch_cuda_candidate_probabilities,
)
from .candidate_training import (
    CandidateTrainingDataset,
    GpuReadiness,
    _candidate_feature_set,
    _candidate_lookback,
    _reject_repo_artifact_path,
    build_candidate_training_dataset,
    detect_gpu_readiness,
    load_yahoo_intraday_1m_bars,
)

CandidateReplayStatus = Literal["candidate_replayed_only", "prepared_not_replayed"]
CandidateReplayAction = Literal["buy", "sell", "hold"]
DEFAULT_CANDIDATE_REPLAY_RUN_ID = "bounded-candidate-local-paper-replay"
MAX_CANDIDATE_REPLAY_BARS = 512
OPTIONAL_CANDIDATE_REPLAY_BACKENDS = ("torch",)


@dataclass(frozen=True)
class CandidateReplayConfig:
    run_id: str = DEFAULT_CANDIDATE_REPLAY_RUN_ID
    max_bars: int = 180
    min_examples: int = 8
    buy_threshold: float = 0.55
    sell_threshold: float = 0.45
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
        if self.max_bars > MAX_CANDIDATE_REPLAY_BARS:
            raise ValueError(f"max_bars must be <= {MAX_CANDIDATE_REPLAY_BARS}")
        if self.min_examples <= 0:
            raise ValueError("min_examples must be positive")
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


@dataclass(frozen=True)
class CandidateReplaySource:
    bars: tuple[Bar, ...]
    dataset: CandidateTrainingDataset
    data_source: str
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class CandidateReplayTrade:
    client_order_id: str
    decision_id: str
    side: str
    quantity: Decimal
    price: Decimal
    fee: Decimal
    probability: float
    signal_bar_end: datetime
    filled_at: datetime
    source: str = LOCAL_PAPER_SOURCE
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "signal_bar_end", self.signal_bar_end.astimezone(UTC))
        object.__setattr__(self, "filled_at", self.filled_at.astimezone(UTC))


@dataclass(frozen=True)
class BoundedCandidateReplayResult:
    run_id: str
    status: CandidateReplayStatus
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
    decisions_seen: int
    order_intents_seen: int
    skipped_non_contiguous: int
    trades: tuple[CandidateReplayTrade, ...]
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
    thresholds: dict[str, Any]
    probability_metrics: dict[str, Any]
    replay_artifact: Path
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_at", self.checked_at.astimezone(UTC))


CandidateProbabilityRunner = Callable[
    [CandidateTrainingDataset, Path, dict[str, Any]],
    dict[str, Any],
]


def run_bounded_candidate_replay(
    *,
    config: CandidateReplayConfig | None = None,
    artifact_root: Path,
    repo_root: Path | None = None,
    training_metrics_artifact: Path | None = None,
    evaluation_artifact: Path | None = None,
    model_artifact: Path | None = None,
    yahoo_snapshot: Path | None = None,
    symbol: str | None = None,
    gpu: GpuReadiness | None = None,
    probability_runner: CandidateProbabilityRunner | None = None,
) -> BoundedCandidateReplayResult:
    config = config or CandidateReplayConfig()
    _reject_repo_artifact_path(artifact_root, repo_root)
    output_dir = artifact_root / "candidate-replay" / config.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    replay_artifact = output_dir / "metrics.json"
    event_store = _fresh_event_store(output_dir)
    gpu = gpu or detect_gpu_readiness()
    evaluation_payload, evaluation_error = _read_evaluation_artifact(evaluation_artifact)
    selected_training_metrics_artifact = (
        training_metrics_artifact
        or _training_artifact_from_evaluation_payload(evaluation_payload)
    )
    training_payload, training_error = _read_training_metrics(selected_training_metrics_artifact)
    candidate = _candidate_from_training_payload(training_payload)
    source = _load_replay_source(
        config=config,
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

    result = _run_candidate_replay_result(
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
        replay_artifact=replay_artifact,
        event_store=event_store,
        probability_runner=probability_runner,
    )
    replay_artifact.write_text(
        json.dumps(_candidate_replay_payload(result, artifact_root), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return result


def _run_candidate_replay_result(
    *,
    config: CandidateReplayConfig,
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
    replay_artifact: Path,
    event_store: EventStore,
    probability_runner: CandidateProbabilityRunner | None,
) -> BoundedCandidateReplayResult:
    if evaluation_error is not None:
        return _prepared_result(
            config=config,
            training_metrics_artifact=training_metrics_artifact,
            evaluation_artifact=evaluation_artifact,
            model_artifact=model_artifact,
            candidate=candidate,
            source=source,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=selected_backend,
            replay_artifact=replay_artifact,
            reason=evaluation_error,
        )
    if training_error is not None:
        return _prepared_result(
            config=config,
            training_metrics_artifact=training_metrics_artifact,
            evaluation_artifact=evaluation_artifact,
            model_artifact=model_artifact,
            candidate=candidate,
            source=source,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=selected_backend,
            replay_artifact=replay_artifact,
            reason=training_error,
        )
    expected_feature_names = _feature_names_from_training_payload(training_payload)
    if expected_feature_names and expected_feature_names != source.dataset.feature_names:
        return _prepared_result(
            config=config,
            training_metrics_artifact=training_metrics_artifact,
            evaluation_artifact=evaluation_artifact,
            model_artifact=model_artifact,
            candidate=candidate,
            source=source,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=selected_backend,
            replay_artifact=replay_artifact,
            reason=(
                "training/replay feature names mismatch: "
                f"{expected_feature_names} != {source.dataset.feature_names}"
            ),
        )
    if model_artifact is None or not model_artifact.exists():
        return _prepared_result(
            config=config,
            training_metrics_artifact=training_metrics_artifact,
            evaluation_artifact=evaluation_artifact,
            model_artifact=model_artifact,
            candidate=candidate,
            source=source,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=selected_backend,
            replay_artifact=replay_artifact,
            reason="candidate model artifact is missing",
        )
    if probability_runner is None and not gpu.available:
        return _prepared_result(
            config=config,
            training_metrics_artifact=training_metrics_artifact,
            evaluation_artifact=evaluation_artifact,
            model_artifact=model_artifact,
            candidate=candidate,
            source=source,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=selected_backend,
            replay_artifact=replay_artifact,
            reason=f"GPU readiness unavailable: {gpu.detail}",
        )
    if len(source.dataset.labels) < config.min_examples:
        return _prepared_result(
            config=config,
            training_metrics_artifact=training_metrics_artifact,
            evaluation_artifact=evaluation_artifact,
            model_artifact=model_artifact,
            candidate=candidate,
            source=source,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=selected_backend,
            replay_artifact=replay_artifact,
            reason=(
                "insufficient replay examples: "
                f"{len(source.dataset.labels)} < {config.min_examples}"
            ),
        )
    if probability_runner is None and selected_backend is None:
        return _prepared_result(
            config=config,
            training_metrics_artifact=training_metrics_artifact,
            evaluation_artifact=evaluation_artifact,
            model_artifact=model_artifact,
            candidate=candidate,
            source=source,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=None,
            replay_artifact=replay_artifact,
            reason="no operator-approved research GPU replay backend installed",
        )

    runner = probability_runner or _run_torch_cuda_candidate_probabilities
    try:
        probability_result = runner(source.dataset, model_artifact, training_payload)
        probabilities = _probabilities_from_result(probability_result)
    except Exception as exc:  # noqa: BLE001 - replay jobs record backend failures.
        return _prepared_result(
            config=config,
            training_metrics_artifact=training_metrics_artifact,
            evaluation_artifact=evaluation_artifact,
            model_artifact=model_artifact,
            candidate=candidate,
            source=source,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=selected_backend,
            replay_artifact=replay_artifact,
            reason=f"bounded candidate replay unavailable: {exc}",
        )
    if len(probabilities) != len(source.dataset.labels):
        return _prepared_result(
            config=config,
            training_metrics_artifact=training_metrics_artifact,
            evaluation_artifact=evaluation_artifact,
            model_artifact=model_artifact,
            candidate=candidate,
            source=source,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=selected_backend,
            replay_artifact=replay_artifact,
            reason="probability count must match replay examples",
        )
    return _run_local_paper_replay(
        config=config,
        training_metrics_artifact=training_metrics_artifact,
        evaluation_artifact=evaluation_artifact,
        model_artifact=model_artifact,
        candidate=candidate,
        source=source,
        probabilities=probabilities,
        probability_result=probability_result,
        gpu=gpu,
        available_backends=available_backends,
        selected_backend=selected_backend,
        replay_artifact=replay_artifact,
        event_store=event_store,
    )


def _run_local_paper_replay(
    *,
    config: CandidateReplayConfig,
    training_metrics_artifact: Path | None,
    evaluation_artifact: Path | None,
    model_artifact: Path,
    candidate: dict[str, Any],
    source: CandidateReplaySource,
    probabilities: tuple[float, ...],
    probability_result: dict[str, Any],
    gpu: GpuReadiness,
    available_backends: tuple[str, ...],
    selected_backend: str | None,
    replay_artifact: Path,
    event_store: EventStore,
    record_decision_events: bool = True,
) -> BoundedCandidateReplayResult:
    broker = LocalPaperBroker(
        event_store=event_store,
        emergency_store=EmergencyStore(replay_artifact.parent / "emergency.json"),
        starting_cash=config.starting_cash,
        fee_bps=config.fee_bps,
        slippage_bps=config.slippage_bps,
    )
    trades: list[CandidateReplayTrade] = []
    decisions_seen = 0
    order_intents_seen = 0
    skipped_non_contiguous = 0
    ordered = list(source.bars)
    for offset, probability in enumerate(probabilities):
        index = source.dataset.lookback + offset
        signal_bar = ordered[index]
        execution_bar = ordered[index + 1]
        decisions_seen += 1
        decision_id = _decision_id(config.run_id, signal_bar.symbol, signal_bar.end_ts)
        action = _action_for_probability(probability, config)
        if record_decision_events:
            event_store.append(
                Event(
                    event_type="candidate_replay_decision",
                    created_at=signal_bar.end_ts,
                    payload={
                        "source": "candidate_replay",
                        "run_id": config.run_id,
                        "decision_id": decision_id,
                        "market": signal_bar.market,
                        "symbol": signal_bar.symbol,
                        "action": action,
                        "probability": f"{probability:.8f}",
                        "buy_threshold": f"{config.buy_threshold:.6f}",
                        "sell_threshold": f"{config.sell_threshold:.6f}",
                        "model_artifact": str(model_artifact),
                    },
                )
            )
        if execution_bar.start_ts != signal_bar.end_ts:
            skipped_non_contiguous += 1
            continue
        position = broker.account().quantity(market=signal_bar.market, symbol=signal_bar.symbol)
        if action == "buy" and position <= 0:
            side = "buy"
        elif action == "sell" and position > 0:
            side = "sell"
        else:
            continue
        order_intents_seen += 1
        order = OrderIntent(
            client_order_id=f"{config.run_id}-{order_intents_seen:04d}",
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
            CandidateReplayTrade(
                client_order_id=order.client_order_id,
                decision_id=decision_id,
                side=execution.fill.side,
                quantity=execution.fill.quantity,
                price=execution.fill.price,
                fee=execution.fill.fee,
                probability=probability,
                signal_bar_end=signal_bar.end_ts,
                filled_at=execution.fill.filled_at,
                source=execution.fill.source,
            )
        )

    fill_events = _local_paper_fill_events(event_store)
    replay_state = event_store.replay()
    if any(event.payload.get("source") != LOCAL_PAPER_SOURCE for event in fill_events):
        raise RuntimeError("candidate replay only supports local_paper fills")
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
        raise RuntimeError("candidate replay equity must reconcile with local paper replay")
    replay_final_position = replay_state.positions.get((market, symbol), Decimal("0"))
    return BoundedCandidateReplayResult(
        run_id=config.run_id,
        status="candidate_replayed_only",
        checked_at=datetime.now(UTC),
        gpu=gpu,
        reason="bounded candidate local-paper replay completed",
        available_backends=available_backends,
        selected_backend=selected_backend,
        training_metrics_artifact=training_metrics_artifact,
        evaluation_artifact=evaluation_artifact,
        model_artifact=model_artifact,
        candidate_experiment_id=candidate.get("candidate_experiment_id"),
        candidate_parameters=candidate.get("candidate_parameters") or {},
        data_source=source.data_source,
        symbol=symbol,
        market=market,
        timeframe=ordered[-1].timeframe,
        bars_seen=len(ordered),
        examples_seen=len(source.dataset.labels),
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
        thresholds=_threshold_payload(config),
        probability_metrics=_probability_metrics(probabilities, probability_result),
        replay_artifact=replay_artifact,
    )


def _prepared_result(
    *,
    config: CandidateReplayConfig,
    training_metrics_artifact: Path | None,
    evaluation_artifact: Path | None,
    model_artifact: Path | None,
    candidate: dict[str, Any],
    source: CandidateReplaySource,
    gpu: GpuReadiness,
    available_backends: tuple[str, ...],
    selected_backend: str | None,
    replay_artifact: Path,
    reason: str,
) -> BoundedCandidateReplayResult:
    return BoundedCandidateReplayResult(
        run_id=config.run_id,
        status="prepared_not_replayed",
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
        thresholds=_threshold_payload(config),
        probability_metrics={},
        replay_artifact=replay_artifact,
    )


def _load_replay_source(
    *,
    config: CandidateReplayConfig,
    candidate: dict[str, Any],
    yahoo_snapshot: Path | None,
    symbol: str | None,
) -> CandidateReplaySource:
    if yahoo_snapshot is not None:
        bars = load_yahoo_intraday_1m_bars(
            yahoo_snapshot,
            symbol=symbol,
            max_bars=config.max_bars,
        )
        data_source = str(yahoo_snapshot)
    else:
        bars = list(
            SampleBarProvider.trending_1m(
                count=config.max_bars,
                seed=config.sample_seed,
            ).base_bars
        )
        data_source = f"deterministic_sample_replay_seed{config.sample_seed}"
    ordered = tuple(sorted(bars, key=lambda bar: bar.start_ts))
    dataset = build_candidate_training_dataset(
        list(ordered),
        lookback=_candidate_lookback(candidate),
        data_source=data_source,
        feature_set=_candidate_feature_set(candidate),
    )
    return CandidateReplaySource(bars=ordered, dataset=dataset, data_source=data_source)


def _candidate_replay_payload(
    result: BoundedCandidateReplayResult,
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
            "decisions_seen": result.decisions_seen,
            "order_intents_seen": result.order_intents_seen,
            "skipped_non_contiguous": result.skipped_non_contiguous,
            "trades": result.trades,
            "trade_count": len(result.trades),
            "starting_cash": result.starting_cash,
            "ending_cash": result.ending_cash,
            "final_position": result.final_position,
            "replay_final_position": result.replay_final_position,
            "last_price": result.last_price,
            "equity": result.equity,
            "pnl": result.pnl,
            "max_drawdown": result.max_drawdown,
            "replay_fill_count": result.replay_fill_count,
            "event_count": result.event_count,
            "thresholds": result.thresholds,
            "probability_metrics": result.probability_metrics,
            "artifacts": {
                "replay": str(result.replay_artifact),
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


def _read_evaluation_artifact(path: Path | None) -> tuple[dict[str, Any], str | None]:
    if path is None:
        return {}, "candidate evaluation artifact is required"
    if not path.exists():
        return {}, f"candidate evaluation artifact is missing: {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, f"candidate evaluation artifact is unreadable: {exc}"
    if not isinstance(payload, dict):
        return {}, "candidate evaluation artifact must contain a JSON object"
    return payload, None


def _training_artifact_from_evaluation_payload(payload: dict[str, Any]) -> Path | None:
    value = payload.get("training_metrics_artifact")
    if not value:
        return None
    return Path(str(value))


def _model_artifact_from_evaluation_payload(payload: dict[str, Any]) -> Path | None:
    value = payload.get("model_artifact")
    if value:
        return Path(str(value))
    artifacts = payload.get("artifacts")
    if isinstance(artifacts, dict) and artifacts.get("source_model"):
        return Path(str(artifacts["source_model"]))
    return None


def _fresh_event_store(output_dir: Path) -> EventStore:
    db_path = output_dir / "state.sqlite"
    jsonl_path = output_dir / "events.jsonl"
    for path in (db_path, jsonl_path):
        if path.exists():
            path.unlink()
    return EventStore(db_path, jsonl_path)


def _action_for_probability(
    probability: float,
    config: CandidateReplayConfig,
) -> CandidateReplayAction:
    if probability >= config.buy_threshold:
        return "buy"
    if probability <= config.sell_threshold:
        return "sell"
    return "hold"


def _decision_id(run_id: str, symbol: str, signal_end: datetime) -> str:
    compact_ts = signal_end.strftime("%Y%m%dT%H%M%SZ")
    return f"{run_id}:{symbol}:{compact_ts}"


def _local_paper_fill_events(event_store: EventStore) -> list[Event]:
    return [
        event
        for event in event_store.iter_events()
        if event.event_type == "fill" and event.payload.get("source") == LOCAL_PAPER_SOURCE
    ]


def _max_drawdown_from_local_paper(
    *,
    bars: list[Bar],
    fill_events: list[Event],
    starting_cash: Decimal,
) -> tuple[Decimal, Decimal]:
    cash = starting_cash
    position = Decimal("0")
    peak_equity = starting_cash
    max_drawdown = Decimal("0")
    fill_index = 0
    ordered_fills = sorted(fill_events, key=lambda event: event.created_at)
    for bar in sorted(bars, key=lambda item: item.start_ts):
        while (
            fill_index < len(ordered_fills)
            and ordered_fills[fill_index].created_at <= bar.start_ts
        ):
            payload = ordered_fills[fill_index].payload
            quantity = Decimal(str(payload["quantity"]))
            price = Decimal(str(payload["price"]))
            fee = Decimal(str(payload.get("fee", "0")))
            notional = price * quantity
            if str(payload["side"]) == "buy":
                cash -= notional + fee
                position += quantity
            else:
                cash += notional - fee
                position -= quantity
            fill_index += 1
        equity = cash + position * bar.close
        if equity > peak_equity:
            peak_equity = equity
        drawdown = peak_equity - equity
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    if not bars:
        return Decimal("0"), starting_cash
    return max_drawdown, cash + position * sorted(bars, key=lambda item: item.start_ts)[-1].close


def _probability_metrics(
    probabilities: tuple[float, ...],
    probability_result: dict[str, Any],
) -> dict[str, Any]:
    if not probabilities:
        return {}
    return {
        "backend": probability_result.get("backend"),
        "operation": probability_result.get("operation"),
        "device": probability_result.get("device"),
        "feature_names": probability_result.get("feature_names"),
        "feature_names_match": probability_result.get("feature_names_match"),
        "hidden_units": probability_result.get("hidden_units"),
        "min_probability": f"{min(probabilities):.6f}",
        "max_probability": f"{max(probabilities):.6f}",
        "mean_probability": f"{(sum(probabilities) / len(probabilities)):.6f}",
        "candidate_experiment_id": probability_result.get("candidate_experiment_id"),
    }


def _threshold_payload(config: CandidateReplayConfig) -> dict[str, str]:
    return {
        "buy_threshold": f"{config.buy_threshold:.6f}",
        "sell_threshold": f"{config.sell_threshold:.6f}",
        "quantity": str(config.quantity),
        "starting_cash": str(config.starting_cash),
        "fee_bps": str(config.fee_bps),
        "slippage_bps": str(config.slippage_bps),
        "promotion_gate": "false",
    }


def _available_gpu_backends() -> tuple[str, ...]:
    return tuple(
        backend
        for backend in OPTIONAL_CANDIDATE_REPLAY_BACKENDS
        if importlib.util.find_spec(backend) is not None
    )


def _selected_backend() -> str | None:
    if importlib.util.find_spec("torch") is not None:
        return "torch"
    return None
