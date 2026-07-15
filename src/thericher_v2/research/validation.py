"""Bounded model-validation loop using broker-free local paper execution."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from thericher_v2.contracts import SCHEMA_VERSION, Bar, OrderIntent, Timeframe
from thericher_v2.data import BarQuery, SampleBarProvider
from thericher_v2.ensemble import decide
from thericher_v2.execution import EmergencyStore, LocalPaperBroker
from thericher_v2.models import MomentumModel
from thericher_v2.serialization import to_jsonable
from thericher_v2.state import Event, EventStore

DEFAULT_MODEL_ARTIFACT_ROOT = Path("D:/thericher-v2/model-artifacts")
DEFAULT_MARKET_DATA_ROOT = Path("D:/market_data")
VALIDATION_SOURCE = "bounded_validation"


@dataclass(frozen=True)
class MarketDataInventory:
    root: Path
    root_exists: bool
    useful_paths: tuple[Path, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class GpuReadiness:
    available: bool
    detail: str
    checked_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_at", self.checked_at.astimezone(UTC))


@dataclass(frozen=True)
class ValidationConfig:
    run_id: str = "bounded-validation-smoke"
    starting_cash: Decimal = Decimal("10000")
    quantity: Decimal = Decimal("1")
    fee_bps: Decimal = Decimal("1")
    slippage_bps: Decimal = Decimal("0")
    min_bars: int = 8
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class ValidationTrade:
    client_order_id: str
    decision_id: str
    side: str
    quantity: Decimal
    price: Decimal
    fee: Decimal
    signal_bar_end: datetime
    filled_at: datetime
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class ValidationResult:
    run_id: str
    symbol: str
    market: str
    timeframe: Timeframe
    bars_seen: int
    decisions_seen: int
    trades: tuple[ValidationTrade, ...]
    starting_cash: Decimal
    ending_cash: Decimal
    final_position: Decimal
    last_price: Decimal
    equity: Decimal
    event_count: int
    data_source: str
    schema_version: int = SCHEMA_VERSION

    @property
    def pnl(self) -> Decimal:
        return self.equity - self.starting_cash


def discover_market_data_inventory(
    root: Path = DEFAULT_MARKET_DATA_ROOT,
) -> MarketDataInventory:
    useful_paths: list[Path] = []
    notes: list[str] = []
    if not root.exists():
        return MarketDataInventory(
            root=root,
            root_exists=False,
            useful_paths=(),
            notes=("market data root missing",),
        )

    intraday_root = (
        root
        / "us_equities"
        / "yahoo_intraday_starter"
        / "canonical"
        / "ohlcv_1m"
    )
    if intraday_root.exists():
        notes.append("found yahoo_intraday_starter canonical 1m root")
        for snapshot in sorted(intraday_root.glob("snapshot=*"))[-3:]:
            csv_path = snapshot / "ohlcv_1m.csv.gz"
            if csv_path.exists():
                useful_paths.append(csv_path)

    daily_root = root / "us_equities" / "yahoo_daily_universe" / "canonical" / "ohlcv_daily"
    if daily_root.exists():
        notes.append("found yahoo_daily_universe canonical daily root")
        for snapshot in sorted(daily_root.glob("snapshot=*"))[-2:]:
            csv_path = snapshot / "ohlcv_daily.csv.gz"
            if csv_path.exists():
                useful_paths.append(csv_path)

    if not notes:
        notes.append("no known useful market-data folders found")
    return MarketDataInventory(
        root=root,
        root_exists=True,
        useful_paths=tuple(useful_paths),
        notes=tuple(notes),
    )


def load_yahoo_intraday_1m_bars(
    path: Path,
    *,
    symbol: str | None = None,
    market: str = "US",
    max_bars: int = 120,
) -> list[Bar]:
    if max_bars <= 0:
        raise ValueError("max_bars must be positive")
    selected_symbol = symbol.upper() if symbol else None
    bars: list[Bar] = []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            row_symbol = str(row["symbol"]).upper()
            if selected_symbol is None:
                selected_symbol = row_symbol
            if row_symbol != selected_symbol:
                if bars:
                    break
                continue
            bars.append(
                Bar(
                    symbol=row_symbol,
                    market=market,
                    timeframe=Timeframe.M1,
                    start_ts=_parse_utc(row["timestamp_utc"]),
                    open=Decimal(str(row["open"])),
                    high=Decimal(str(row["high"])),
                    low=Decimal(str(row["low"])),
                    close=Decimal(str(row["close"])),
                    volume=Decimal(str(row["volume"])),
                    complete=True,
                )
            )
            if len(bars) >= max_bars:
                break
    if not bars:
        raise ValueError("no bars loaded from yahoo intraday file")
    return bars


def run_local_paper_validation(
    bars: list[Bar],
    *,
    event_store: EventStore,
    emergency_store: EmergencyStore,
    model: MomentumModel | None = None,
    config: ValidationConfig | None = None,
    data_source: str = "sample",
) -> ValidationResult:
    config = config or ValidationConfig()
    model = model or MomentumModel()
    ordered = sorted(bars, key=lambda bar: bar.start_ts)
    _validate_bars(ordered, min_bars=max(config.min_bars, model.lookback + 3))

    broker = LocalPaperBroker(
        event_store=event_store,
        emergency_store=emergency_store,
        starting_cash=config.starting_cash,
        fee_bps=config.fee_bps,
        slippage_bps=config.slippage_bps,
    )
    trades: list[ValidationTrade] = []
    decisions_seen = 0

    for index in range(model.lookback + 1, len(ordered) - 1):
        signal_window = ordered[: index + 1]
        signal_bar = ordered[index]
        execution_bar = ordered[index + 1]
        prediction = model.predict(signal_window)
        decision = decide([prediction])
        decisions_seen += 1
        decision_id = _decision_id(config.run_id, decision.symbol, signal_bar.end_ts)
        event_store.append(
            Event(
                event_type="model_prediction",
                created_at=prediction.feature_window_end,
                payload={
                    "source": VALIDATION_SOURCE,
                    "run_id": config.run_id,
                    "prediction_id": f"{prediction.model_id}:{prediction.model_version}",
                    **to_jsonable(prediction),
                },
            )
        )
        event_store.append(
            Event(
                event_type="ensemble_decision",
                created_at=decision.decided_at,
                payload={
                    "source": VALIDATION_SOURCE,
                    "run_id": config.run_id,
                    "decision_id": decision_id,
                    **to_jsonable(decision),
                },
            )
        )

        account = broker.account()
        position = account.quantity(market=signal_bar.market, symbol=signal_bar.symbol)
        if decision.action == "buy" and position <= 0:
            side = "buy"
        elif decision.action == "sell" and position > 0:
            side = "sell"
        else:
            continue

        order = OrderIntent(
            client_order_id=f"{config.run_id}-{len(trades) + 1:04d}",
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
            ValidationTrade(
                client_order_id=order.client_order_id,
                decision_id=decision_id,
                side=execution.fill.side,
                quantity=execution.fill.quantity,
                price=execution.fill.price,
                fee=execution.fill.fee,
                signal_bar_end=signal_bar.end_ts,
                filled_at=execution.fill.filled_at,
            )
        )

    account = broker.account()
    symbol = ordered[-1].symbol
    market = ordered[-1].market
    final_position = account.quantity(market=market, symbol=symbol)
    last_price = ordered[-1].close
    equity = account.cash + final_position * last_price
    return ValidationResult(
        run_id=config.run_id,
        symbol=symbol,
        market=market,
        timeframe=ordered[-1].timeframe,
        bars_seen=len(ordered),
        decisions_seen=decisions_seen,
        trades=tuple(trades),
        starting_cash=config.starting_cash,
        ending_cash=account.cash,
        final_position=final_position,
        last_price=last_price,
        equity=equity,
        event_count=len(list(event_store.iter_events())),
        data_source=data_source,
    )


def run_sample_cpu_smoke(work_dir: Path | None = None) -> ValidationResult:
    provider = SampleBarProvider.trending_1m(count=90, seed=23)
    bars = provider.get_bars(
        query=BarQuery(
            symbol="AAPL",
            market="US",
            timeframe=Timeframe.M1,
        )
    )
    if work_dir is not None:
        work_dir.mkdir(parents=True, exist_ok=True)
        return run_local_paper_validation(
            bars,
            event_store=EventStore(work_dir / "state.sqlite", work_dir / "events.jsonl"),
            emergency_store=EmergencyStore(work_dir / "emergency.json"),
            config=ValidationConfig(run_id="sample-cpu-smoke"),
            data_source="deterministic_sample",
        )
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        temp_path = Path(temp_dir)
        result = run_local_paper_validation(
            bars,
            event_store=EventStore(temp_path / "state.sqlite", temp_path / "events.jsonl"),
            emergency_store=EmergencyStore(temp_path / "emergency.json"),
            config=ValidationConfig(run_id="sample-cpu-smoke"),
            data_source="deterministic_sample",
        )
    return result


def resolve_model_artifact_root() -> Path:
    configured = (
        os.environ.get("THERICHER_HOST_MODEL_ARTIFACT_ROOT")
        or os.environ.get("THERICHER_MODEL_ARTIFACT_ROOT")
    )
    return Path(configured) if configured else DEFAULT_MODEL_ARTIFACT_ROOT


def write_validation_artifact(
    result: ValidationResult,
    *,
    artifact_root: Path,
    repo_root: Path | None = None,
) -> Path:
    _reject_repo_artifact_path(artifact_root, repo_root)
    output_dir = artifact_root / "validation"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{result.run_id}.json"
    path.write_text(json.dumps(_result_payload(result), indent=2, sort_keys=True), encoding="utf-8")
    return path


def detect_gpu_readiness() -> GpuReadiness:
    checked_at = datetime.now(UTC)
    try:
        completed = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return GpuReadiness(available=False, detail=str(exc), checked_at=checked_at)
    detail = completed.stdout.strip() or completed.stderr.strip()
    return GpuReadiness(
        available=completed.returncode == 0 and bool(completed.stdout.strip()),
        detail=detail,
        checked_at=checked_at,
    )


def write_gpu_experiment_plan(
    *,
    result: ValidationResult,
    gpu: GpuReadiness,
    artifact_root: Path,
    repo_root: Path | None = None,
) -> Path:
    _reject_repo_artifact_path(artifact_root, repo_root)
    output_dir = artifact_root / "validation"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{result.run_id}-gpu-plan.json"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": result.run_id,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "gpu": to_jsonable(gpu),
        "queues": {
            "short_experiments": [
                "sweep momentum thresholds against local-paper replay",
                "test timeframe confirmation inputs",
            ],
            "long_candidate_training": [
                "train only after CPU validation target is stable",
                "write model artifacts outside Git",
            ],
        },
        "baseline": _result_payload(result),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--yahoo-snapshot", type=Path)
    parser.add_argument("--symbol")
    parser.add_argument("--max-bars", type=int, default=90)
    parser.add_argument("--write-artifact", action="store_true")
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--prepare-gpu-plan", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.yahoo_snapshot is not None:
        bars = load_yahoo_intraday_1m_bars(
            args.yahoo_snapshot,
            symbol=args.symbol,
            max_bars=args.max_bars,
        )
        data_source = str(args.yahoo_snapshot)
    else:
        bars = SampleBarProvider.trending_1m(count=args.max_bars, seed=23).base_bars
        data_source = "deterministic_sample"

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        temp_path = Path(temp_dir)
        result = run_local_paper_validation(
            list(bars),
            event_store=EventStore(temp_path / "state.sqlite", temp_path / "events.jsonl"),
            emergency_store=EmergencyStore(temp_path / "emergency.json"),
            config=ValidationConfig(run_id="bounded-validation-smoke"),
            data_source=data_source,
        )

        artifact_root = args.artifact_root or resolve_model_artifact_root()
        artifacts: dict[str, str] = {}
        if args.write_artifact:
            artifacts["validation"] = str(
                write_validation_artifact(
                    result,
                    artifact_root=artifact_root,
                    repo_root=Path.cwd(),
                )
            )
        if args.prepare_gpu_plan:
            gpu = detect_gpu_readiness()
            if gpu.available:
                artifacts["gpu_plan"] = str(
                    write_gpu_experiment_plan(
                        result=result,
                        gpu=gpu,
                        artifact_root=artifact_root,
                        repo_root=Path.cwd(),
                    )
                )

    print(json.dumps({"result": _result_payload(result), "artifacts": artifacts}, indent=2))


def _validate_bars(bars: list[Bar], *, min_bars: int) -> None:
    if len(bars) < min_bars:
        raise ValueError(f"at least {min_bars} bars are required")
    first = bars[0]
    if any(
        bar.symbol != first.symbol
        or bar.market != first.market
        or bar.timeframe != first.timeframe
        or not bar.complete
        for bar in bars
    ):
        raise ValueError("validation bars must be complete and share symbol, market, timeframe")
    for prior, current in zip(bars, bars[1:], strict=False):
        if current.start_ts != prior.end_ts:
            raise ValueError("validation bars must be contiguous")


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _decision_id(run_id: str, symbol: str, signal_end: datetime) -> str:
    compact_ts = signal_end.strftime("%Y%m%dT%H%M%SZ")
    return f"{run_id}:{symbol}:{compact_ts}"


def _result_payload(result: ValidationResult) -> dict[str, Any]:
    return to_jsonable(
        {
            "schema_version": result.schema_version,
            "run_id": result.run_id,
            "symbol": result.symbol,
            "market": result.market,
            "timeframe": result.timeframe,
            "bars_seen": result.bars_seen,
            "decisions_seen": result.decisions_seen,
            "trades": result.trades,
            "starting_cash": result.starting_cash,
            "ending_cash": result.ending_cash,
            "final_position": result.final_position,
            "last_price": result.last_price,
            "equity": result.equity,
            "pnl": result.pnl,
            "event_count": result.event_count,
            "data_source": result.data_source,
        }
    )


def _reject_repo_artifact_path(artifact_root: Path, repo_root: Path | None) -> None:
    if repo_root is None:
        return
    resolved_artifact = artifact_root.resolve()
    resolved_repo = repo_root.resolve()
    if os.name != "nt":
        docker_repo_root = Path("/app").resolve()
        docker_artifact_root = docker_repo_root / "model_artifacts"
        if resolved_repo == docker_repo_root and (
            resolved_artifact == docker_artifact_root
            or docker_artifact_root in resolved_artifact.parents
        ):
            return
    if resolved_artifact == resolved_repo or resolved_repo in resolved_artifact.parents:
        raise ValueError("artifact_root must be outside the Git workspace")


if __name__ == "__main__":
    main()
