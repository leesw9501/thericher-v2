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
DEFAULT_MAX_BARS = 120


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
    result = run_short_experiment_queue(source, queue_id=args.queue_id)
    artifact_root = args.artifact_root or resolve_model_artifact_root()
    artifacts: dict[str, str] = {}
    gpu_payload: dict[str, Any] | None = None
    if args.write_artifact:
        artifacts["metrics"] = str(
            write_experiment_metrics_artifact(
                result,
                artifact_root=artifact_root,
                repo_root=Path.cwd(),
            )
        )
    if args.prepare_gpu_candidate:
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
                "result": _queue_payload(result),
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


def _metrics_from_validation(
    *,
    queue_id: str,
    spec: ExperimentSpec,
    run_id: str,
    data_source: str,
    event_store: EventStore,
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


def _bars_for_spec(source_bars: tuple[Bar, ...], spec: ExperimentSpec) -> list[Bar]:
    if not source_bars:
        raise ValueError("source must contain bars")
    source_timeframe = source_bars[0].timeframe
    if source_timeframe == spec.timeframe:
        return list(source_bars)
    return resample_bars(source_bars, spec.timeframe)


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
            "final_position": metrics.final_position,
            "replay_final_position": metrics.replay_final_position,
            "replay_fill_count": metrics.replay_fill_count,
            "event_count": metrics.event_count,
        }
    )


if __name__ == "__main__":
    main()
