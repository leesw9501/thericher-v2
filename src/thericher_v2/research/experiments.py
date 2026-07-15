"""Bounded research experiment queues built on the local validation harness."""

from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe, decimal_value
from thericher_v2.data import SampleBarProvider, resample_bars
from thericher_v2.execution import EmergencyStore
from thericher_v2.models import MomentumModel
from thericher_v2.serialization import to_jsonable
from thericher_v2.state import EventStore

from .validation import (
    GpuReadiness,
    ValidationConfig,
    _reject_repo_artifact_path,
    detect_gpu_readiness,
    load_yahoo_intraday_1m_bars,
    resolve_model_artifact_root,
    run_local_paper_validation,
)

DEFAULT_QUEUE_ID = "short-momentum-cpu-queue"
MAX_SHORT_EXPERIMENTS = 8
MAX_WALK_FORWARD_WINDOWS = 6
DEFAULT_MAX_BARS = 120
DEFAULT_WALK_FORWARD_WINDOW_BARS = 60
DEFAULT_WALK_FORWARD_STEP_BARS = 30
DEFAULT_STARTING_CASH = Decimal("10000")


@dataclass(frozen=True)
class ExperimentSpec:
    experiment_id: str
    timeframe: Timeframe = Timeframe.M1
    lookback: int = 3
    buy_threshold_bps: Decimal = Decimal("5")
    sell_threshold_bps: Decimal = Decimal("-5")
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.experiment_id:
            raise ValueError("experiment_id is required")
        object.__setattr__(self, "timeframe", Timeframe(self.timeframe))
        if self.lookback <= 0:
            raise ValueError("lookback must be positive")
        buy_threshold = decimal_value(self.buy_threshold_bps, "buy_threshold_bps")
        sell_threshold = decimal_value(self.sell_threshold_bps, "sell_threshold_bps")
        object.__setattr__(self, "buy_threshold_bps", buy_threshold)
        object.__setattr__(self, "sell_threshold_bps", sell_threshold)
        if sell_threshold >= buy_threshold:
            raise ValueError("sell_threshold_bps must be below buy_threshold_bps")

    def build_model(self) -> MomentumModel:
        return MomentumModel(
            lookback=self.lookback,
            buy_threshold_bps=self.buy_threshold_bps,
            sell_threshold_bps=self.sell_threshold_bps,
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "model_id": "momentum_close_v1",
            "timeframe": self.timeframe,
            "lookback": self.lookback,
            "buy_threshold_bps": self.buy_threshold_bps,
            "sell_threshold_bps": self.sell_threshold_bps,
        }


@dataclass(frozen=True)
class ExperimentSource:
    bars: tuple[Bar, ...]
    data_source: str
    external_path: Path | None = None
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class ExperimentMetrics:
    queue_id: str
    experiment_id: str
    run_id: str
    data_source: str
    parameters: dict[str, Any]
    symbol: str
    market: str
    timeframe: Timeframe
    bars_seen: int
    decisions_seen: int
    local_paper_trades: int
    ending_cash: Decimal
    ending_equity: Decimal
    pnl: Decimal
    max_drawdown: Decimal
    final_position: Decimal
    replay_final_position: Decimal
    replay_fill_count: int
    event_count: int
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class ExperimentQueueResult:
    queue_id: str
    created_at: datetime
    data_source: str
    experiments: tuple[ExperimentMetrics, ...]
    max_experiments: int = MAX_SHORT_EXPERIMENTS
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "created_at", self.created_at.astimezone(UTC))


@dataclass(frozen=True)
class WalkForwardWindow:
    window_id: str
    start_index: int
    end_index: int
    start_ts: datetime
    end_ts: datetime
    bars_seen: int
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.window_id:
            raise ValueError("window_id is required")
        if self.start_index < 0 or self.end_index <= self.start_index:
            raise ValueError("walk-forward window indexes are invalid")
        if self.bars_seen != self.end_index - self.start_index:
            raise ValueError("bars_seen must match window index span")
        object.__setattr__(self, "start_ts", self.start_ts.astimezone(UTC))
        object.__setattr__(self, "end_ts", self.end_ts.astimezone(UTC))
        if self.end_ts <= self.start_ts:
            raise ValueError("walk-forward window end_ts must be after start_ts")


@dataclass(frozen=True)
class WalkForwardWindowResult:
    window: WalkForwardWindow
    experiments: tuple[ExperimentMetrics, ...]
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class WalkForwardExperimentSummary:
    experiment_id: str
    windows_seen: int
    total_trades: int
    total_pnl: Decimal
    worst_window_pnl: Decimal
    max_drawdown: Decimal
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class WalkForwardResult:
    queue_id: str
    created_at: datetime
    data_source: str
    window_bars: int
    step_bars: int
    windows: tuple[WalkForwardWindowResult, ...]
    experiment_summaries: tuple[WalkForwardExperimentSummary, ...]
    max_windows: int = MAX_WALK_FORWARD_WINDOWS
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "created_at", self.created_at.astimezone(UTC))
        if self.window_bars <= 0 or self.step_bars <= 0:
            raise ValueError("window_bars and step_bars must be positive")
        if len(self.windows) > self.max_windows:
            raise ValueError(f"walk-forward is capped at {self.max_windows} windows")


def default_short_experiment_specs() -> tuple[ExperimentSpec, ...]:
    return (
        ExperimentSpec(
            experiment_id="m1_lb3_b5_s5",
            timeframe=Timeframe.M1,
            lookback=3,
            buy_threshold_bps=Decimal("5"),
            sell_threshold_bps=Decimal("-5"),
        ),
        ExperimentSpec(
            experiment_id="m1_lb5_b5_s5",
            timeframe=Timeframe.M1,
            lookback=5,
            buy_threshold_bps=Decimal("5"),
            sell_threshold_bps=Decimal("-5"),
        ),
        ExperimentSpec(
            experiment_id="m1_lb3_b10_s10",
            timeframe=Timeframe.M1,
            lookback=3,
            buy_threshold_bps=Decimal("10"),
            sell_threshold_bps=Decimal("-10"),
        ),
        ExperimentSpec(
            experiment_id="m5_lb3_b5_s5",
            timeframe=Timeframe.M5,
            lookback=3,
            buy_threshold_bps=Decimal("5"),
            sell_threshold_bps=Decimal("-5"),
        ),
    )


def load_experiment_source(
    *,
    yahoo_snapshot: Path | None = None,
    symbol: str | None = None,
    max_bars: int = DEFAULT_MAX_BARS,
) -> ExperimentSource:
    if max_bars <= 0:
        raise ValueError("max_bars must be positive")
    if yahoo_snapshot is not None:
        bars = load_yahoo_intraday_1m_bars(
            yahoo_snapshot,
            symbol=symbol,
            max_bars=max_bars,
        )
        return ExperimentSource(
            bars=tuple(bars),
            data_source=str(yahoo_snapshot),
            external_path=yahoo_snapshot,
        )
    return ExperimentSource(
        bars=SampleBarProvider.trending_1m(count=max_bars, seed=23).base_bars,
        data_source="deterministic_sample",
    )


def run_short_experiment_queue(
    source: ExperimentSource,
    *,
    queue_id: str = DEFAULT_QUEUE_ID,
    specs: tuple[ExperimentSpec, ...] | None = None,
    work_root: Path | None = None,
) -> ExperimentQueueResult:
    specs = specs or default_short_experiment_specs()
    _validate_specs(specs)
    if work_root is not None:
        work_root.mkdir(parents=True, exist_ok=True)
        return _run_queue_in_work_root(
            source,
            queue_id=queue_id,
            specs=specs,
            work_root=work_root,
        )
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        return _run_queue_in_work_root(
            source,
            queue_id=queue_id,
            specs=specs,
            work_root=Path(temp_dir),
        )


def run_walk_forward_queue(
    source: ExperimentSource,
    *,
    queue_id: str = DEFAULT_QUEUE_ID,
    specs: tuple[ExperimentSpec, ...] | None = None,
    window_bars: int = DEFAULT_WALK_FORWARD_WINDOW_BARS,
    step_bars: int = DEFAULT_WALK_FORWARD_STEP_BARS,
    work_root: Path | None = None,
) -> WalkForwardResult:
    specs = specs or default_short_experiment_specs()
    _validate_specs(specs)
    windows = _build_walk_forward_windows(source.bars, window_bars=window_bars, step_bars=step_bars)
    if work_root is not None:
        work_root.mkdir(parents=True, exist_ok=True)
        return _run_walk_forward_in_work_root(
            source,
            queue_id=queue_id,
            specs=specs,
            windows=windows,
            window_bars=window_bars,
            step_bars=step_bars,
            work_root=work_root,
        )
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        return _run_walk_forward_in_work_root(
            source,
            queue_id=queue_id,
            specs=specs,
            windows=windows,
            window_bars=window_bars,
            step_bars=step_bars,
            work_root=Path(temp_dir),
        )


def write_experiment_metrics_artifact(
    result: ExperimentQueueResult,
    *,
    artifact_root: Path,
    repo_root: Path | None = None,
) -> Path:
    _reject_repo_artifact_path(artifact_root, repo_root)
    output_dir = artifact_root / "experiments"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{result.queue_id}.json"
    path.write_text(json.dumps(_queue_payload(result), indent=2, sort_keys=True), encoding="utf-8")
    return path


def write_walk_forward_metrics_artifact(
    result: WalkForwardResult,
    *,
    artifact_root: Path,
    repo_root: Path | None = None,
) -> Path:
    _reject_repo_artifact_path(artifact_root, repo_root)
    output_dir = artifact_root / "experiments"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{result.queue_id}-walk-forward.json"
    path.write_text(
        json.dumps(_walk_forward_payload(result), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def write_gpu_candidate_smoke_artifact(
    result: ExperimentQueueResult,
    *,
    gpu: GpuReadiness,
    artifact_root: Path,
    repo_root: Path | None = None,
) -> Path:
    if not gpu.available:
        raise ValueError("GPU must be available to prepare a candidate smoke artifact")
    _reject_repo_artifact_path(artifact_root, repo_root)
    output_dir = artifact_root / "experiments"
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate = _candidate_metrics(result)
    path = output_dir / f"{result.queue_id}-gpu-candidate-smoke.json"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "queue_id": result.queue_id,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": "prepared_not_trained",
        "gpu": to_jsonable(gpu),
        "candidate_experiment_id": candidate.experiment_id,
        "candidate_parameters": to_jsonable(candidate.parameters),
        "source_metrics": _metrics_payload(candidate),
        "artifact_policy": {
            "root": str(artifact_root),
            "repo_storage_allowed": False,
        },
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue-id", default=DEFAULT_QUEUE_ID)
    parser.add_argument("--yahoo-snapshot", type=Path)
    parser.add_argument("--symbol")
    parser.add_argument("--max-bars", type=int, default=DEFAULT_MAX_BARS)
    parser.add_argument("--walk-forward", action="store_true")
    parser.add_argument("--window-bars", type=int, default=DEFAULT_WALK_FORWARD_WINDOW_BARS)
    parser.add_argument("--step-bars", type=int, default=DEFAULT_WALK_FORWARD_STEP_BARS)
    parser.add_argument("--write-artifact", action="store_true")
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--prepare-gpu-candidate", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    source = load_experiment_source(
        yahoo_snapshot=args.yahoo_snapshot,
        symbol=args.symbol,
        max_bars=args.max_bars,
    )
    result: ExperimentQueueResult | WalkForwardResult
    if args.walk_forward:
        result = run_walk_forward_queue(
            source,
            queue_id=args.queue_id,
            window_bars=args.window_bars,
            step_bars=args.step_bars,
        )
    else:
        result = run_short_experiment_queue(source, queue_id=args.queue_id)
    artifact_root = args.artifact_root or resolve_model_artifact_root()
    artifacts: dict[str, str] = {}
    gpu_payload: dict[str, Any] | None = None
    if args.write_artifact:
        if isinstance(result, WalkForwardResult):
            artifacts["walk_forward_metrics"] = str(
                write_walk_forward_metrics_artifact(
                    result,
                    artifact_root=artifact_root,
                    repo_root=Path.cwd(),
                )
            )
        else:
            artifacts["metrics"] = str(
                write_experiment_metrics_artifact(
                    result,
                    artifact_root=artifact_root,
                    repo_root=Path.cwd(),
                )
            )
    if args.prepare_gpu_candidate and not isinstance(result, WalkForwardResult):
        gpu = detect_gpu_readiness()
        gpu_payload = to_jsonable(gpu)
        if gpu.available:
            artifacts["gpu_candidate"] = str(
                write_gpu_candidate_smoke_artifact(
                    result,
                    gpu=gpu,
                    artifact_root=artifact_root,
                    repo_root=Path.cwd(),
                )
            )

    print(
        json.dumps(
            {
                "result": (
                    _walk_forward_payload(result)
                    if isinstance(result, WalkForwardResult)
                    else _queue_payload(result)
                ),
                "artifacts": artifacts,
                "gpu": gpu_payload,
            },
            indent=2,
            sort_keys=True,
        )
    )


def _run_queue_in_work_root(
    source: ExperimentSource,
    *,
    queue_id: str,
    specs: tuple[ExperimentSpec, ...],
    work_root: Path,
) -> ExperimentQueueResult:
    metrics: list[ExperimentMetrics] = []
    for spec in specs:
        bars = _bars_for_spec(source.bars, spec)
        run_id = f"{queue_id}-{spec.experiment_id}"
        work_dir = work_root / spec.experiment_id
        event_store = EventStore(work_dir / "state.sqlite", work_dir / "events.jsonl")
        result = run_local_paper_validation(
            bars,
            event_store=event_store,
            emergency_store=EmergencyStore(work_dir / "emergency.json"),
            model=spec.build_model(),
            config=ValidationConfig(run_id=run_id),
            data_source=source.data_source,
        )
        metrics.append(
            _metrics_from_validation(
                queue_id=queue_id,
                spec=spec,
                run_id=run_id,
                data_source=source.data_source,
                event_store=event_store,
                bars=bars,
                starting_cash=result.starting_cash,
                symbol=result.symbol,
                market=result.market,
                timeframe=result.timeframe,
                bars_seen=result.bars_seen,
                decisions_seen=result.decisions_seen,
                local_paper_trades=len(result.trades),
                ending_cash=result.ending_cash,
                ending_equity=result.equity,
                pnl=result.pnl,
                final_position=result.final_position,
                event_count=result.event_count,
            )
        )
    return ExperimentQueueResult(
        queue_id=queue_id,
        created_at=datetime.now(UTC),
        data_source=source.data_source,
        experiments=tuple(metrics),
    )


def _run_walk_forward_in_work_root(
    source: ExperimentSource,
    *,
    queue_id: str,
    specs: tuple[ExperimentSpec, ...],
    windows: tuple[WalkForwardWindow, ...],
    window_bars: int,
    step_bars: int,
    work_root: Path,
) -> WalkForwardResult:
    window_results: list[WalkForwardWindowResult] = []
    for window in windows:
        window_source = ExperimentSource(
            bars=source.bars[window.start_index : window.end_index],
            data_source=source.data_source,
            external_path=source.external_path,
        )
        window_result = _run_queue_in_work_root(
            window_source,
            queue_id=f"{queue_id}-{window.window_id}",
            specs=specs,
            work_root=work_root / window.window_id,
        )
        window_results.append(
            WalkForwardWindowResult(
                window=window,
                experiments=window_result.experiments,
            )
        )
    return WalkForwardResult(
        queue_id=queue_id,
        created_at=datetime.now(UTC),
        data_source=source.data_source,
        window_bars=window_bars,
        step_bars=step_bars,
        windows=tuple(window_results),
        experiment_summaries=_summarize_walk_forward(window_results),
    )


def _metrics_from_validation(
    *,
    queue_id: str,
    spec: ExperimentSpec,
    run_id: str,
    data_source: str,
    event_store: EventStore,
    bars: list[Bar],
    starting_cash: Decimal,
    symbol: str,
    market: str,
    timeframe: Timeframe,
    bars_seen: int,
    decisions_seen: int,
    local_paper_trades: int,
    ending_cash: Decimal,
    ending_equity: Decimal,
    pnl: Decimal,
    final_position: Decimal,
    event_count: int,
) -> ExperimentMetrics:
    events = list(event_store.iter_events())
    fill_events = [event for event in events if event.event_type == "fill"]
    if any(event.payload.get("source") != "local_paper" for event in fill_events):
        raise RuntimeError("experiment queue only supports local_paper fills")
    replay = event_store.replay()
    replay_position = replay.positions.get((market.upper(), symbol.upper()), Decimal("0"))
    max_drawdown, replay_final_equity = _max_drawdown_from_local_paper(
        bars=bars,
        fill_events=fill_events,
        starting_cash=starting_cash,
    )
    if replay_final_equity != ending_equity:
        raise RuntimeError("attribution equity must reconcile with validation equity")
    return ExperimentMetrics(
        queue_id=queue_id,
        experiment_id=spec.experiment_id,
        run_id=run_id,
        data_source=data_source,
        parameters=spec.parameters,
        symbol=symbol,
        market=market,
        timeframe=timeframe,
        bars_seen=bars_seen,
        decisions_seen=decisions_seen,
        local_paper_trades=local_paper_trades,
        ending_cash=ending_cash,
        ending_equity=ending_equity,
        pnl=pnl,
        max_drawdown=max_drawdown,
        final_position=final_position,
        replay_final_position=replay_position,
        replay_fill_count=len(fill_events),
        event_count=event_count,
    )


def _validate_specs(specs: tuple[ExperimentSpec, ...]) -> None:
    if not specs:
        raise ValueError("at least one experiment spec is required")
    if len(specs) > MAX_SHORT_EXPERIMENTS:
        raise ValueError(f"short experiment queue is capped at {MAX_SHORT_EXPERIMENTS}")
    ids = [spec.experiment_id for spec in specs]
    if len(ids) != len(set(ids)):
        raise ValueError("experiment_id values must be unique")


def _build_walk_forward_windows(
    source_bars: tuple[Bar, ...],
    *,
    window_bars: int,
    step_bars: int,
) -> tuple[WalkForwardWindow, ...]:
    if window_bars <= 0 or step_bars <= 0:
        raise ValueError("window_bars and step_bars must be positive")
    if len(source_bars) < window_bars:
        raise ValueError("source must contain at least window_bars bars")
    ordered = tuple(sorted(source_bars, key=lambda bar: bar.start_ts))
    windows: list[WalkForwardWindow] = []
    for start_index in range(0, len(ordered) - window_bars + 1, step_bars):
        if len(windows) >= MAX_WALK_FORWARD_WINDOWS:
            raise ValueError(f"walk-forward is capped at {MAX_WALK_FORWARD_WINDOWS} windows")
        end_index = start_index + window_bars
        window_bars_slice = ordered[start_index:end_index]
        windows.append(
            WalkForwardWindow(
                window_id=f"w{len(windows) + 1:02d}",
                start_index=start_index,
                end_index=end_index,
                start_ts=window_bars_slice[0].start_ts,
                end_ts=window_bars_slice[-1].end_ts,
                bars_seen=len(window_bars_slice),
            )
        )
    return tuple(windows)


def _bars_for_spec(source_bars: tuple[Bar, ...], spec: ExperimentSpec) -> list[Bar]:
    if not source_bars:
        raise ValueError("source must contain bars")
    source_timeframe = source_bars[0].timeframe
    if source_timeframe == spec.timeframe:
        return list(source_bars)
    return resample_bars(source_bars, spec.timeframe)


def _summarize_walk_forward(
    windows: list[WalkForwardWindowResult],
) -> tuple[WalkForwardExperimentSummary, ...]:
    grouped: dict[str, list[ExperimentMetrics]] = {}
    for window in windows:
        for metrics in window.experiments:
            grouped.setdefault(metrics.experiment_id, []).append(metrics)
    summaries: list[WalkForwardExperimentSummary] = []
    for experiment_id in sorted(grouped):
        items = grouped[experiment_id]
        summaries.append(
            WalkForwardExperimentSummary(
                experiment_id=experiment_id,
                windows_seen=len(items),
                total_trades=sum(item.local_paper_trades for item in items),
                total_pnl=sum((item.pnl for item in items), Decimal("0")),
                worst_window_pnl=min(item.pnl for item in items),
                max_drawdown=max(item.max_drawdown for item in items),
            )
        )
    return tuple(summaries)


def _max_drawdown_from_local_paper(
    *,
    bars: list[Bar],
    fill_events: list[Any],
    starting_cash: Decimal,
) -> tuple[Decimal, Decimal]:
    ordered_bars = sorted(bars, key=lambda bar: bar.start_ts)
    ordered_fills = sorted(fill_events, key=lambda event: event.created_at)
    cash = starting_cash
    position = Decimal("0")
    peak_equity = starting_cash
    max_drawdown = Decimal("0")
    fill_index = 0
    for bar in ordered_bars:
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
    if not ordered_bars:
        return Decimal("0"), starting_cash
    return max_drawdown, cash + position * ordered_bars[-1].close


def _candidate_metrics(result: ExperimentQueueResult) -> ExperimentMetrics:
    if not result.experiments:
        raise ValueError("queue result must contain experiments")
    for metrics in result.experiments:
        if metrics.local_paper_trades > 0:
            return metrics
    return result.experiments[0]


def _queue_payload(result: ExperimentQueueResult) -> dict[str, Any]:
    return to_jsonable(
        {
            "schema_version": result.schema_version,
            "queue_id": result.queue_id,
            "created_at": result.created_at,
            "data_source": result.data_source,
            "max_experiments": result.max_experiments,
            "experiment_count": len(result.experiments),
            "experiments": [_metrics_payload(metrics) for metrics in result.experiments],
        }
    )


def _walk_forward_payload(result: WalkForwardResult) -> dict[str, Any]:
    return to_jsonable(
        {
            "schema_version": result.schema_version,
            "queue_id": result.queue_id,
            "created_at": result.created_at,
            "data_source": result.data_source,
            "window_bars": result.window_bars,
            "step_bars": result.step_bars,
            "max_windows": result.max_windows,
            "window_count": len(result.windows),
            "experiment_summaries": [
                _walk_forward_summary_payload(summary)
                for summary in result.experiment_summaries
            ],
            "windows": [
                {
                    "schema_version": window_result.schema_version,
                    "window": _walk_forward_window_payload(window_result.window),
                    "experiments": [
                        _metrics_payload(metrics)
                        for metrics in window_result.experiments
                    ],
                }
                for window_result in result.windows
            ],
        }
    )


def _walk_forward_window_payload(window: WalkForwardWindow) -> dict[str, Any]:
    return to_jsonable(
        {
            "schema_version": window.schema_version,
            "window_id": window.window_id,
            "start_index": window.start_index,
            "end_index": window.end_index,
            "start_ts": window.start_ts,
            "end_ts": window.end_ts,
            "bars_seen": window.bars_seen,
        }
    )


def _walk_forward_summary_payload(summary: WalkForwardExperimentSummary) -> dict[str, Any]:
    return to_jsonable(
        {
            "schema_version": summary.schema_version,
            "experiment_id": summary.experiment_id,
            "windows_seen": summary.windows_seen,
            "total_trades": summary.total_trades,
            "total_pnl": summary.total_pnl,
            "worst_window_pnl": summary.worst_window_pnl,
            "max_drawdown": summary.max_drawdown,
        }
    )


def _metrics_payload(metrics: ExperimentMetrics) -> dict[str, Any]:
    return to_jsonable(
        {
            "schema_version": metrics.schema_version,
            "queue_id": metrics.queue_id,
            "experiment_id": metrics.experiment_id,
            "run_id": metrics.run_id,
            "data_source": metrics.data_source,
            "parameters": metrics.parameters,
            "symbol": metrics.symbol,
            "market": metrics.market,
            "timeframe": metrics.timeframe,
            "bars_seen": metrics.bars_seen,
            "decisions_seen": metrics.decisions_seen,
            "local_paper_trades": metrics.local_paper_trades,
            "ending_cash": metrics.ending_cash,
            "ending_equity": metrics.ending_equity,
            "pnl": metrics.pnl,
            "max_drawdown": metrics.max_drawdown,
            "final_position": metrics.final_position,
            "replay_final_position": metrics.replay_final_position,
            "replay_fill_count": metrics.replay_fill_count,
            "event_count": metrics.event_count,
        }
    )


if __name__ == "__main__":
    main()
