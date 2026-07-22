"""Bounded model-validation loop using broker-free local paper execution."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Protocol

from thericher_v2.contracts import (
    SCHEMA_VERSION,
    Bar,
    EmergencyState,
    ModelPrediction,
    OrderIntent,
    Signal,
    Timeframe,
    require_utc,
)
from thericher_v2.data import (
    SUPPORTED_RESAMPLE_TIMEFRAMES,
    BarQuery,
    CatalogedBars,
    SampleBarProvider,
    SessionWindow,
    assess_bar_quality,
    resample_bars,
    resample_session_bars,
)
from thericher_v2.ensemble import decide
from thericher_v2.execution import (
    LOCAL_PAPER_SOURCE,
    EmergencyStore,
    FillEventArtifact,
    LocalPaperAccount,
    LocalPaperBroker,
    LocalPaperFill,
    LocalPaperPosition,
    collect_fill_source_evidence,
    replay_local_paper_account,
)
from thericher_v2.models import MomentumModel
from thericher_v2.serialization import to_jsonable
from thericher_v2.state import Event, EventStore

from .campaign import (
    CampaignContract,
    CampaignPhase,
    NaiveBaselineId,
)

DEFAULT_MODEL_ARTIFACT_ROOT = Path("D:/thericher-v2/model-artifacts")
DEFAULT_MARKET_DATA_ROOT = Path("D:/market_data")
VALIDATION_SOURCE = "bounded_validation"
INTRADAY_MULTITIMEFRAME_BASELINE_SOURCE = "intraday_multitimeframe_baseline"


class PredictionModel(Protocol):
    lookback: int

    def predict(self, bars: list[Bar]) -> ModelPrediction: ...


class _CampaignEventStore(EventStore):
    """Fresh campaign event store that defers SQLite rebuild until replay completion."""

    def __init__(self, db_path: Path, jsonl_path: Path) -> None:
        super().__init__(db_path, jsonl_path, rebuild_sqlite_on_append=False)
        self._next_sequence = 1
        self._append_observer: Callable[[Event], None] | None = None

    def next_seq(self) -> int:
        sequence = self._next_sequence
        self._next_sequence += 1
        return sequence

    def append(self, event: Event) -> Event:
        recorded = super().append(event)
        if self._append_observer is not None:
            self._append_observer(recorded)
        return recorded

    def observe_appends(self, observer: Callable[[Event], None]) -> None:
        self._append_observer = observer


class _CampaignLocalPaperBroker(LocalPaperBroker):
    """Use the normal local-paper event format without replaying every prior event per fill."""

    def __init__(
        self,
        *,
        event_store: _CampaignEventStore,
        emergency_store: EmergencyStore,
        starting_cash: Decimal,
        fee_bps: Decimal,
        slippage_bps: Decimal,
    ) -> None:
        super().__init__(
            event_store=event_store,
            emergency_store=emergency_store,
            starting_cash=starting_cash,
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
        )
        self._cash = self.starting_cash
        self._positions: dict[tuple[str, str], Decimal] = {}
        self._seen_client_order_ids: set[str] = set()
        self._accepted_orders: dict[str, OrderIntent] = {}
        self._closed_order_ids: set[str] = set()
        self._fill_events: dict[str, Event] = {}
        event_store.observe_appends(self._observe_event)

    def account(self) -> LocalPaperAccount:
        positions = tuple(
            LocalPaperPosition(market=market, symbol=symbol, quantity=quantity)
            for (market, symbol), quantity in sorted(self._positions.items())
            if quantity != 0
        )
        return LocalPaperAccount(cash=self._cash, positions=positions)

    def submit_order(
        self,
        order: OrderIntent,
        *,
        submitted_at: datetime | None = None,
    ):
        result = super().submit_order(order, submitted_at=submitted_at)
        self._seen_client_order_ids.add(order.client_order_id)
        if result.status == "accepted":
            self._accepted_orders[order.client_order_id] = order
        return result

    def _client_order_id_seen(self, client_order_id: str) -> bool:
        return client_order_id in self._seen_client_order_ids

    def _recorded_fill_event(self, client_order_id: str) -> Event | None:
        return self._fill_events.get(client_order_id)

    def _accepted_order(self, client_order_id: str) -> OrderIntent | None:
        return self._accepted_orders.get(client_order_id)

    def _pending_order(self, client_order_id: str) -> OrderIntent | None:
        if client_order_id in self._closed_order_ids:
            return None
        return self._accepted_orders.get(client_order_id)

    def _observe_event(self, event: Event) -> None:
        client_order_id = event.payload.get("client_order_id")
        if not isinstance(client_order_id, str):
            return
        if event.event_type == "fill":
            self._fill_events[client_order_id] = event
            self._closed_order_ids.add(client_order_id)
            quantity = Decimal(str(event.payload["quantity"]))
            price = Decimal(str(event.payload["price"]))
            fee = Decimal(str(event.payload.get("fee", "0")))
            market = str(event.payload["market"]).upper()
            symbol = str(event.payload["symbol"]).upper()
            key = (market, symbol)
            if event.payload["side"] == "buy":
                self._cash -= price * quantity + fee
                self._positions[key] = self._positions.get(key, Decimal("0")) + quantity
            else:
                self._cash += price * quantity - fee
                self._positions[key] = self._positions.get(key, Decimal("0")) - quantity
        elif event.event_type in {
            "local_paper_order_canceled",
            "local_paper_order_rejected",
        }:
            self._closed_order_ids.add(client_order_id)


@dataclass(frozen=True)
class _NaiveBaselineModel:
    baseline_id: NaiveBaselineId
    deterministic_seed: int
    lookback: int = 0

    def predict(self, bars: list[Bar]) -> ModelPrediction:
        if not bars:
            raise ValueError("naive baseline requires at least one completed bar")
        latest = bars[-1]
        if self.baseline_id == "always_long":
            action = "buy"
            reason = "always_long_baseline"
        elif self.baseline_id == "previous_bar_direction":
            action = "buy" if latest.close > latest.open else "hold"
            reason = "completed_bar_direction_baseline"
        elif self.baseline_id == "flat":
            action = "hold"
            reason = "flat_baseline"
        else:  # pragma: no cover - CampaignContract rejects unsupported values.
            raise ValueError(f"unsupported naive baseline: {self.baseline_id}")
        confidence = Decimal("1") if action == "buy" else Decimal("0")
        signal = Signal(
            symbol=latest.symbol,
            market=latest.market,
            action=action,
            strength=confidence,
            reason=reason,
            timeframe=Timeframe(latest.timeframe),
            generated_at=latest.end_ts,
        )
        return ModelPrediction(
            model_id=f"naive_{self.baseline_id}",
            model_version="1.0.0",
            symbol=latest.symbol,
            market=latest.market,
            signal=signal,
            confidence=confidence,
            expected_edge_bps=Decimal("0"),
            feature_window_end=latest.end_ts,
            metadata={
                "baseline_id": self.baseline_id,
                "deterministic_seed": self.deterministic_seed,
            },
        )


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
    total_fees: Decimal
    total_slippage: Decimal
    campaign_id: str | None = None
    campaign_contract_hash: str | None = None
    campaign_phase: CampaignPhase | None = None
    campaign_fold_id: str | None = None
    baseline_id: NaiveBaselineId | None = None
    deterministic_seed: int | None = None
    dataset_id: str | None = None
    dataset_hash: str | None = None
    dataset_source_path: Path | None = None
    schema_version: int = SCHEMA_VERSION

    @property
    def pnl(self) -> Decimal:
        return self.equity - self.starting_cash

    @property
    def after_cost_pnl(self) -> Decimal:
        return self.pnl

    @property
    def gross_pnl(self) -> Decimal:
        return self.after_cost_pnl + self.total_fees + self.total_slippage


@dataclass(frozen=True)
class MultiTimeframeBaselineCell:
    timeframe: Timeframe
    resampled_bar_count: int
    status: Literal["completed", "skipped"]
    skip_reason: str | None
    decision_bar_end: datetime | None
    decision_id: str | None
    local_paper_fill_count: int
    all_fills_local_paper: bool
    final_position: Decimal | None
    replayed_final_position: Decimal | None
    work_dir: Path | None
    event_jsonl_sha256: str | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "timeframe", Timeframe(self.timeframe))
        if self.resampled_bar_count < 0 or self.local_paper_fill_count < 0:
            raise ValueError("baseline counts must be non-negative")
        if self.status not in {"completed", "skipped"}:
            raise ValueError("baseline status must be completed or skipped")
        if self.decision_bar_end is not None:
            object.__setattr__(
                self,
                "decision_bar_end",
                require_utc(self.decision_bar_end, "decision_bar_end"),
            )
        if self.status == "completed":
            if (
                self.skip_reason is not None
                or self.decision_bar_end is None
                or self.decision_id is None
                or self.final_position is None
                or self.replayed_final_position is None
                or (self.work_dir is None and self.event_jsonl_sha256 is not None)
            ):
                raise ValueError("completed baseline cell is missing replay evidence")
        elif (
            self.skip_reason is None
            or self.decision_bar_end is not None
            or self.decision_id is not None
            or self.local_paper_fill_count != 0
            or self.final_position is not None
            or self.replayed_final_position is not None
            or self.work_dir is not None
            or self.event_jsonl_sha256 is not None
        ):
            raise ValueError("skipped baseline cell must not contain execution evidence")


@dataclass(frozen=True)
class MultiTimeframeBaselineResult:
    run_id: str
    dataset_id: str
    dataset_hash: str
    source_path: Path
    cells: tuple[MultiTimeframeBaselineCell, ...]
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class ReplayEvidence:
    work_dir: Path
    event_jsonl_path: Path
    event_jsonl_sha256: str
    state_sqlite_path: Path
    state_sqlite_sha256: str
    emergency_path: Path
    emergency_sha256: str
    fill_source: str = LOCAL_PAPER_SOURCE
    schema_version: int = SCHEMA_VERSION

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "fill_source": self.fill_source,
            "work_dir": str(self.work_dir),
            "event_jsonl": {
                "path": str(self.event_jsonl_path),
                "sha256": self.event_jsonl_sha256,
            },
            "state_sqlite": {
                "path": str(self.state_sqlite_path),
                "sha256": self.state_sqlite_sha256,
            },
            "emergency": {
                "path": str(self.emergency_path),
                "sha256": self.emergency_sha256,
            },
        }


@dataclass(frozen=True)
class NaiveBaselineRun:
    baseline_id: NaiveBaselineId
    result: ValidationResult
    artifact_path: Path
    replay_evidence: ReplayEvidence
    fill_source: str = LOCAL_PAPER_SOURCE
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class CampaignReplayRun:
    result: ValidationResult
    artifact_path: Path
    replay_evidence: ReplayEvidence
    fill_source: str = LOCAL_PAPER_SOURCE
    schema_version: int = SCHEMA_VERSION


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
    bars: list[Bar] | CatalogedBars,
    *,
    event_store: EventStore,
    emergency_store: EmergencyStore,
    model: PredictionModel | None = None,
    config: ValidationConfig | None = None,
    data_source: str = "sample",
    campaign: CampaignContract | None = None,
    phase: CampaignPhase = "development",
    fold_id: str | None = None,
    tuning: bool = False,
    baseline_id: NaiveBaselineId | None = None,
    eligible_signal_starts: frozenset[datetime] | None = None,
    allowed_session_windows: tuple[SessionWindow, ...] | None = None,
) -> ValidationResult:
    model = model or MomentumModel()
    cataloged_data: CatalogedBars | None = None
    if campaign is not None:
        if not isinstance(bars, CatalogedBars):
            raise ValueError("campaign validation requires Data-owned CatalogedBars")
        cataloged_data = bars
        campaign.verify_cataloged_dataset(
            dataset_id=cataloged_data.dataset_id,
            dataset_hash=cataloged_data.dataset_hash,
        )
        if any(bar.timeframe != campaign.timeframe for bar in cataloged_data.bars):
            raise ValueError("CatalogedBars timeframe does not match campaign timeframe")
        raw_bars = list(cataloged_data.bars)
        data_source = f"cataloged:{cataloged_data.source_path}"
    elif isinstance(bars, CatalogedBars):
        raw_bars = list(bars.bars)
    else:
        raw_bars = bars
    ordered = sorted(raw_bars, key=lambda bar: bar.start_ts)
    resolved_fold_id: str | None = None
    if campaign is not None:
        resolved_fold_id, window = campaign.resolve_window(
            phase,
            fold_id=fold_id,
            tuning=tuning,
        )
        ordered = [
            bar
            for bar in ordered
            if bar.start_ts >= window.start_utc and bar.end_ts <= window.end_utc
        ]
        if baseline_id is not None and baseline_id not in campaign.naive_baselines:
            raise ValueError("baseline_id is not frozen in the campaign contract")
        if config is None:
            suffix = resolved_fold_id or "sealed"
            config = ValidationConfig(
                run_id=f"{campaign.campaign_id}-{phase}-{suffix}",
                fee_bps=campaign.costs.fee_bps,
                slippage_bps=campaign.costs.slippage_bps,
            )
        elif (
            config.fee_bps != campaign.costs.fee_bps
            or config.slippage_bps != campaign.costs.slippage_bps
        ):
            raise ValueError("validation costs must match the frozen campaign contract")
    else:
        config = config or ValidationConfig()
        if baseline_id is not None:
            raise ValueError("baseline_id requires a campaign contract")

    required_tail = 3 if campaign is None else campaign.target.exit_bar_offset + 1
    _validate_bars(
        ordered,
        min_bars=max(config.min_bars, model.lookback + required_tail),
        allowed_session_windows=allowed_session_windows,
    )

    broker = (
        _CampaignLocalPaperBroker(
            event_store=event_store,
            emergency_store=emergency_store,
            starting_cash=config.starting_cash,
            fee_bps=config.fee_bps,
            slippage_bps=config.slippage_bps,
        )
        if isinstance(event_store, _CampaignEventStore)
        else LocalPaperBroker(
            event_store=event_store,
            emergency_store=emergency_store,
            starting_cash=config.starting_cash,
            fee_bps=config.fee_bps,
            slippage_bps=config.slippage_bps,
        )
    )
    trades: list[ValidationTrade] = []
    decisions_seen = 0
    total_fees = Decimal("0")
    total_slippage = Decimal("0")

    first_signal_index = model.lookback + 1 if campaign is None else model.lookback
    final_offset = 1 if campaign is None else campaign.target.exit_bar_offset
    for index in range(first_signal_index, len(ordered) - final_offset):
        signal_window = ordered[: index + 1]
        signal_bar = ordered[index]
        if (
            eligible_signal_starts is not None
            and signal_bar.start_ts not in eligible_signal_starts
        ):
            continue
        prediction = model.predict(signal_window)
        if campaign is not None and prediction.feature_window_end != signal_bar.end_ts:
            raise ValueError("campaign prediction must use only data through signal bar close")
        decision = decide([prediction])
        if campaign is not None and decision.decided_at != signal_bar.end_ts:
            raise ValueError("campaign decision must occur at the completed signal bar close")
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

        if campaign is not None:
            if decision.action != "buy":
                continue
            account = broker.account()
            if account.quantity(market=signal_bar.market, symbol=signal_bar.symbol) != 0:
                raise RuntimeError("campaign target requires a flat account before entry")
            entry_bar = ordered[index + campaign.target.entry_bar_offset]
            exit_bar = ordered[index + campaign.target.exit_bar_offset]
            if signal_bar.timeframe != Timeframe.D1 and (
                entry_bar.start_ts != signal_bar.end_ts
                or exit_bar.start_ts != entry_bar.end_ts
            ):
                raise ValueError("campaign target cannot cross a declared session boundary")
            entry_order = OrderIntent(
                client_order_id=f"{config.run_id}-{len(trades) + 1:04d}",
                symbol=signal_bar.symbol,
                market=signal_bar.market,
                side="buy",
                quantity=config.quantity,
                limit_price=None,
                decision_id=decision_id,
                created_at=signal_bar.end_ts,
            )
            entry = broker.submit_and_fill_next_bar(
                entry_order,
                signal_bar=signal_bar,
                execution_bar=entry_bar,
            )
            if entry.fill is None:
                continue
            trades.append(
                _validation_trade(
                    entry_order,
                    entry.fill,
                    signal_bar_end=signal_bar.end_ts,
                )
            )
            total_fees += entry.fill.fee
            total_slippage += _slippage_cost(
                entry.fill.price,
                entry_bar.open,
                entry.fill.quantity,
            )

            exit_order = OrderIntent(
                client_order_id=f"{config.run_id}-{len(trades) + 1:04d}",
                symbol=signal_bar.symbol,
                market=signal_bar.market,
                side="sell",
                quantity=entry.fill.quantity,
                limit_price=None,
                decision_id=f"{decision_id}:target-exit",
                created_at=entry_bar.end_ts,
            )
            exit_execution = broker.submit_and_fill_next_bar(
                exit_order,
                signal_bar=entry_bar,
                execution_bar=exit_bar,
            )
            if exit_execution.fill is None:
                raise RuntimeError("campaign target exit did not produce a local-paper fill")
            trades.append(
                _validation_trade(
                    exit_order,
                    exit_execution.fill,
                    signal_bar_end=entry_bar.end_ts,
                )
            )
            total_fees += exit_execution.fill.fee
            total_slippage += _slippage_cost(
                exit_execution.fill.price,
                exit_bar.open,
                exit_execution.fill.quantity,
            )
            continue

        execution_bar = ordered[index + 1]
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
            _validation_trade(
                order,
                execution.fill,
                signal_bar_end=signal_bar.end_ts,
            )
        )
        total_fees += execution.fill.fee
        total_slippage += _slippage_cost(
            execution.fill.price,
            execution_bar.open,
            execution.fill.quantity,
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
        total_fees=total_fees,
        total_slippage=total_slippage,
        campaign_id=None if campaign is None else campaign.campaign_id,
        campaign_contract_hash=None if campaign is None else campaign.contract_hash,
        campaign_phase=None if campaign is None else phase,
        campaign_fold_id=resolved_fold_id,
        baseline_id=baseline_id,
        deterministic_seed=None if campaign is None else campaign.deterministic_seed,
        dataset_id=None if cataloged_data is None else cataloged_data.dataset_id,
        dataset_hash=None if cataloged_data is None else cataloged_data.dataset_hash,
        dataset_source_path=(
            None if cataloged_data is None else cataloged_data.source_path.resolve()
        ),
    )


def run_intraday_multitimeframe_local_paper_baseline(
    source: CatalogedBars,
    *,
    run_id: str = "intraday-multitimeframe-local-paper-baseline",
    work_root: Path | None = None,
    repo_root: Path | None = None,
    session: SessionWindow | None = None,
) -> MultiTimeframeBaselineResult:
    """Replay one completed bar per timeframe through isolated local-paper stores.

    The completed resampled bar is the decision input. Entry and deterministic
    flattening happen on the next two contiguous 1-minute bars, so resampled
    session gaps never become invented execution bars.
    """

    _validate_run_label(run_id)
    bars = _validated_intraday_baseline_source(source)
    if work_root is None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            return _run_intraday_multitimeframe_baseline(
                source=source,
                bars=bars,
                run_id=run_id,
                work_root=Path(temp_dir),
                retain_work_paths=False,
                session=session,
            )

    resolved_root = Path(work_root)
    _reject_repo_artifact_path(resolved_root, repo_root or Path.cwd())
    run_root = resolved_root / "intraday-multitimeframe-baseline" / run_id
    _require_new_path(run_root, "intraday multitimeframe baseline work directory")
    run_root.mkdir(parents=True, exist_ok=False)
    return _run_intraday_multitimeframe_baseline(
        source=source,
        bars=bars,
        run_id=run_id,
        work_root=run_root,
        retain_work_paths=True,
        session=session,
    )


def _validated_intraday_baseline_source(source: CatalogedBars) -> tuple[Bar, ...]:
    if not isinstance(source, CatalogedBars):
        raise TypeError("intraday baseline requires Data-owned CatalogedBars")
    bars = tuple(sorted(source.bars, key=lambda bar: bar.start_ts))
    if not bars:
        raise ValueError("intraday baseline requires at least one bar")
    first = bars[0]
    if (
        first.timeframe != Timeframe.M1
        or not first.complete
        or any(
            bar.timeframe != Timeframe.M1
            or not bar.complete
            or bar.symbol != first.symbol
            or bar.market != first.market
            for bar in bars
        )
    ):
        raise ValueError("intraday baseline requires complete homogeneous 1m bars")
    if any(
        current.start_ts <= prior.start_ts
        for prior, current in zip(bars, bars[1:], strict=False)
    ):
        raise ValueError("intraday baseline bars must be strictly chronological")
    return bars


def _run_intraday_multitimeframe_baseline(
    *,
    source: CatalogedBars,
    bars: tuple[Bar, ...],
    run_id: str,
    work_root: Path,
    retain_work_paths: bool,
    session: SessionWindow | None,
) -> MultiTimeframeBaselineResult:
    source_bars = (
        bars
        if session is None
        else tuple(
            bar
            for bar in bars
            if bar.start_ts >= session.open_ts and bar.end_ts <= session.close_ts
        )
    )
    m1_by_start = {bar.start_ts: bar for bar in source_bars}
    cells: list[MultiTimeframeBaselineCell] = []
    for timeframe in SUPPORTED_RESAMPLE_TIMEFRAMES:
        resampled = (
            resample_bars(source_bars, timeframe)
            if session is None
            else list(resample_session_bars(source_bars, timeframe, session=session).bars)
        )
        resampled = tuple(resampled)
        selected = _select_multitimeframe_execution_bars(resampled, m1_by_start)
        if selected is None:
            skip_reason = (
                "no_complete_resampled_bars"
                if not resampled
                else "no_completed_bar_with_two_following_1m_bars"
            )
            cells.append(
                MultiTimeframeBaselineCell(
                    timeframe=timeframe,
                    resampled_bar_count=len(resampled),
                    status="skipped",
                    skip_reason=skip_reason,
                    decision_bar_end=None,
                    decision_id=None,
                    local_paper_fill_count=0,
                    all_fills_local_paper=True,
                    final_position=None,
                    replayed_final_position=None,
                    work_dir=None,
                    event_jsonl_sha256=None,
                )
            )
            continue

        decision_bar, signal_bar, entry_bar, exit_bar = selected
        cell_dir = work_root / timeframe.value
        cell_dir.mkdir(parents=True, exist_ok=False)
        event_store = EventStore(cell_dir / "state.sqlite", cell_dir / "events.jsonl")
        broker = LocalPaperBroker(
            event_store=event_store,
            emergency_store=EmergencyStore(cell_dir / "emergency.json"),
        )
        decision_id = _multitimeframe_decision_id(run_id, timeframe, decision_bar)
        _append_multitimeframe_baseline_decision(
            event_store=event_store,
            source=source,
            run_id=run_id,
            decision_id=decision_id,
            decision_bar=decision_bar,
            signal_bar=signal_bar,
            entry_bar=entry_bar,
            exit_bar=exit_bar,
        )
        entry_order = OrderIntent(
            client_order_id=f"{run_id}-{timeframe.value}-entry",
            symbol=decision_bar.symbol,
            market=decision_bar.market,
            side="buy",
            quantity=Decimal("1"),
            limit_price=None,
            decision_id=decision_id,
            created_at=decision_bar.end_ts,
        )
        entry = broker.submit_and_fill_next_bar(
            entry_order,
            signal_bar=signal_bar,
            execution_bar=entry_bar,
        )
        if entry.fill is None:
            raise RuntimeError("multitimeframe baseline entry did not produce a local-paper fill")

        exit_order = OrderIntent(
            client_order_id=f"{run_id}-{timeframe.value}-exit",
            symbol=decision_bar.symbol,
            market=decision_bar.market,
            side="sell",
            quantity=entry.fill.quantity,
            limit_price=None,
            decision_id=f"{decision_id}:flatten",
            created_at=entry_bar.end_ts,
        )
        exit_execution = broker.submit_and_fill_next_bar(
            exit_order,
            signal_bar=entry_bar,
            execution_bar=exit_bar,
        )
        if exit_execution.fill is None:
            raise RuntimeError("multitimeframe baseline exit did not produce a local-paper fill")

        fill_evidence = collect_fill_source_evidence(
            (
                FillEventArtifact(
                    path=event_store.jsonl_path,
                    expected_fill_count=2,
                    label=f"{run_id}:{timeframe.value}",
                ),
            )
        )
        if not fill_evidence.local_paper_replay_invariant_passed:
            raise RuntimeError("multitimeframe baseline must preserve local-paper-only fills")
        final_position = broker.account().quantity(
            market=decision_bar.market,
            symbol=decision_bar.symbol,
        )
        replayed_final_position = replay_local_paper_account(event_store).quantity(
            market=decision_bar.market,
            symbol=decision_bar.symbol,
        )
        if final_position != 0 or replayed_final_position != final_position:
            raise RuntimeError(
                "multitimeframe baseline must finish with a replayable flat position"
            )
        event_jsonl_sha256 = (
            _write_event_hash_sidecar(event_store.jsonl_path) if retain_work_paths else None
        )
        cells.append(
            MultiTimeframeBaselineCell(
                timeframe=timeframe,
                resampled_bar_count=len(resampled),
                status="completed",
                skip_reason=None,
                decision_bar_end=decision_bar.end_ts,
                decision_id=decision_id,
                local_paper_fill_count=len(fill_evidence.local_paper_fills),
                all_fills_local_paper=fill_evidence.all_fills_local_paper,
                final_position=final_position,
                replayed_final_position=replayed_final_position,
                work_dir=cell_dir if retain_work_paths else None,
                event_jsonl_sha256=event_jsonl_sha256,
            )
        )
    return MultiTimeframeBaselineResult(
        run_id=run_id,
        dataset_id=source.dataset_id,
        dataset_hash=source.dataset_hash,
        source_path=source.source_path.resolve(),
        cells=tuple(cells),
    )


def _select_multitimeframe_execution_bars(
    resampled: tuple[Bar, ...],
    m1_by_start: dict[datetime, Bar],
) -> tuple[Bar, Bar, Bar, Bar] | None:
    for decision_bar in resampled:
        signal_bar = m1_by_start.get(decision_bar.end_ts - Timeframe.M1.duration)
        entry_bar = m1_by_start.get(decision_bar.end_ts)
        exit_bar = m1_by_start.get(decision_bar.end_ts + Timeframe.M1.duration)
        if signal_bar is None or entry_bar is None or exit_bar is None:
            continue
        if signal_bar.end_ts != decision_bar.end_ts or entry_bar.start_ts != signal_bar.end_ts:
            continue
        if exit_bar.start_ts != entry_bar.end_ts:
            continue
        return decision_bar, signal_bar, entry_bar, exit_bar
    return None


def _append_multitimeframe_baseline_decision(
    *,
    event_store: EventStore,
    source: CatalogedBars,
    run_id: str,
    decision_id: str,
    decision_bar: Bar,
    signal_bar: Bar,
    entry_bar: Bar,
    exit_bar: Bar,
) -> None:
    event_store.append(
        Event(
            event_type="ensemble_decision",
            created_at=decision_bar.end_ts,
            payload=_multitimeframe_baseline_decision_payload(
                source=source,
                run_id=run_id,
                decision_id=decision_id,
                decision_bar=decision_bar,
                signal_bar=signal_bar,
                entry_bar=entry_bar,
                exit_bar=exit_bar,
            ),
        )
    )


def _multitimeframe_baseline_decision_payload(
    *,
    source: CatalogedBars,
    run_id: str,
    decision_id: str,
    decision_bar: Bar,
    signal_bar: Bar,
    entry_bar: Bar,
    exit_bar: Bar,
) -> dict[str, object]:
    return {
        "source": INTRADAY_MULTITIMEFRAME_BASELINE_SOURCE,
        "run_id": run_id,
        "decision_id": decision_id,
        "symbol": decision_bar.symbol,
        "market": decision_bar.market,
        "timeframe": decision_bar.timeframe.value,
        "action": "buy",
        "confidence": "1",
        "expected_edge_bps": "0",
        "risk_score": "0",
        "prediction_ids": [],
        "reason": "completed_bar_local_paper_baseline",
        "data_snapshot": {
            "dataset_id": source.dataset_id,
            "dataset_hash": source.dataset_hash,
        },
        "bar_lineage": {
            "decision_bar_identity": _multitimeframe_bar_identity(decision_bar),
            "signal_bar_identity": _multitimeframe_bar_identity(signal_bar),
            "entry_execution_bar_identity": _multitimeframe_bar_identity(entry_bar),
            "exit_execution_bar_identity": _multitimeframe_bar_identity(exit_bar),
        },
    }


def _multitimeframe_bar_identity(bar: Bar) -> str:
    payload = {
        "symbol": bar.symbol,
        "market": bar.market,
        "timeframe": bar.timeframe.value,
        "start_ts": bar.start_ts.isoformat(),
        "end_ts": bar.end_ts.isoformat(),
        "open": str(bar.open),
        "high": str(bar.high),
        "low": str(bar.low),
        "close": str(bar.close),
        "volume": str(bar.volume),
        "complete": bar.complete,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _multitimeframe_decision_id(run_id: str, timeframe: Timeframe, bar: Bar) -> str:
    compact_ts = bar.end_ts.strftime("%Y%m%dT%H%M%SZ")
    return f"{run_id}:{timeframe.value}:{bar.symbol}:{compact_ts}"


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


def run_naive_cpu_baseline(
    cataloged_bars: CatalogedBars,
    *,
    campaign: CampaignContract,
    artifact_root: Path,
    work_dir: Path,
    phase: CampaignPhase = "development",
    fold_id: str | None = None,
    baseline_id: NaiveBaselineId | None = None,
    repo_root: Path | None = None,
    starting_cash: Decimal = Decimal("10000"),
    quantity: Decimal = Decimal("1"),
    run_label: str | None = None,
    eligible_signal_starts: frozenset[datetime] | None = None,
    allowed_session_windows: tuple[SessionWindow, ...] | None = None,
) -> NaiveBaselineRun:
    """Run one deterministic CPU baseline through the campaign validation path."""

    selected_baseline = baseline_id or campaign.naive_baselines[0]
    if selected_baseline not in campaign.naive_baselines:
        raise ValueError("baseline_id is not frozen in the campaign contract")
    resolved_fold_id, _ = campaign.resolve_window(phase, fold_id=fold_id, tuning=False)
    suffix = resolved_fold_id or "sealed"
    run_id = f"{campaign.campaign_id}-{phase}-{suffix}-{selected_baseline}"
    if run_label is not None:
        _validate_run_label(run_label)
        run_id = f"{run_id}-{run_label}"
    replay = run_campaign_model_replay(
        cataloged_bars,
        campaign=campaign,
        model=_NaiveBaselineModel(
            baseline_id=selected_baseline,
            deterministic_seed=campaign.deterministic_seed,
        ),
        run_id=run_id,
        artifact_root=artifact_root,
        work_dir=work_dir,
        phase=phase,
        fold_id=fold_id,
        baseline_id=selected_baseline,
        repo_root=repo_root,
        starting_cash=starting_cash,
        quantity=quantity,
        eligible_signal_starts=eligible_signal_starts,
        allowed_session_windows=allowed_session_windows,
        emergency_reason="campaign_baseline_initial_state",
    )
    return NaiveBaselineRun(
        baseline_id=selected_baseline,
        result=replay.result,
        artifact_path=replay.artifact_path,
        replay_evidence=replay.replay_evidence,
    )


def run_campaign_model_replay(
    cataloged_bars: CatalogedBars,
    *,
    campaign: CampaignContract,
    model: PredictionModel,
    run_id: str,
    artifact_root: Path,
    work_dir: Path,
    phase: CampaignPhase = "validation",
    fold_id: str | None = None,
    baseline_id: NaiveBaselineId | None = None,
    repo_root: Path | None = None,
    starting_cash: Decimal = Decimal("10000"),
    quantity: Decimal = Decimal("1"),
    eligible_signal_starts: frozenset[datetime] | None = None,
    allowed_session_windows: tuple[SessionWindow, ...] | None = None,
    emergency_reason: str = "campaign_model_initial_state",
) -> CampaignReplayRun:
    """Persist one model replay through the existing local-paper evidence path."""

    _validate_run_label(run_id)
    _, selected_window = campaign.resolve_window(phase, fold_id=fold_id, tuning=False)
    config = ValidationConfig(
        run_id=run_id,
        starting_cash=starting_cash,
        quantity=quantity,
        fee_bps=campaign.costs.fee_bps,
        slippage_bps=campaign.costs.slippage_bps,
    )
    resolved_repo_root = repo_root or Path.cwd()
    resolved_work_dir = work_dir.resolve()
    _reject_repo_artifact_path(resolved_work_dir, resolved_repo_root)
    _reject_repo_artifact_path(artifact_root, resolved_repo_root)
    artifact_path = _validation_artifact_path(artifact_root, run_id)
    _require_new_path(artifact_path, "validation artifact")

    event_jsonl_path = resolved_work_dir / "events.jsonl"
    state_sqlite_path = resolved_work_dir / "state.sqlite"
    emergency_path = resolved_work_dir / "emergency.json"
    for path, label in (
        (event_jsonl_path, "event JSONL"),
        (state_sqlite_path, "state SQLite"),
        (emergency_path, "emergency state"),
    ):
        _require_new_path(path, label)
    resolved_work_dir.mkdir(parents=True, exist_ok=True)

    emergency_store = EmergencyStore(emergency_path)
    emergency_store.write(
        EmergencyState(
            stop_new_orders=False,
            cancel_open_orders_requested=False,
            reason=emergency_reason,
            updated_at=selected_window.start_utc,
        )
    )
    event_store = _CampaignEventStore(state_sqlite_path, event_jsonl_path)
    result = run_local_paper_validation(
        cataloged_bars,
        event_store=event_store,
        emergency_store=emergency_store,
        model=model,
        config=config,
        campaign=campaign,
        phase=phase,
        fold_id=fold_id,
        baseline_id=baseline_id,
        eligible_signal_starts=eligible_signal_starts,
        allowed_session_windows=allowed_session_windows,
    )
    event_store.rebuild_sqlite()
    _assert_campaign_replay_invariants(result, event_store)
    replay_evidence = ReplayEvidence(
        work_dir=resolved_work_dir,
        event_jsonl_path=event_jsonl_path,
        event_jsonl_sha256=_sha256_file(event_jsonl_path),
        state_sqlite_path=state_sqlite_path,
        state_sqlite_sha256=_sha256_file(state_sqlite_path),
        emergency_path=emergency_path,
        emergency_sha256=_sha256_file(emergency_path),
    )
    artifact_path = write_validation_artifact(
        result,
        artifact_root=artifact_root,
        repo_root=resolved_repo_root,
        campaign=campaign,
        cataloged_data=cataloged_bars,
        replay_evidence=replay_evidence,
    )
    return CampaignReplayRun(
        result=result,
        artifact_path=artifact_path,
        replay_evidence=replay_evidence,
    )


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
    campaign: CampaignContract | None = None,
    cataloged_data: CatalogedBars | None = None,
    replay_evidence: ReplayEvidence | None = None,
) -> Path:
    _reject_repo_artifact_path(artifact_root, repo_root)
    path = _validation_artifact_path(artifact_root, result.run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _result_payload(result)
    if campaign is not None:
        payload["campaign_contract"] = campaign.to_payload()
        payload["campaign_contract_hash"] = campaign.contract_hash
    if cataloged_data is not None:
        payload["cataloged_data"] = {
            "dataset_id": cataloged_data.dataset_id,
            "dataset_hash": cataloged_data.dataset_hash,
            "source_path": str(cataloged_data.source_path.resolve()),
        }
    if replay_evidence is not None:
        payload["replay_evidence"] = replay_evidence.to_payload()
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(rendered)
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
    data_quality = assess_bar_quality(tuple(bars))

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

    print(
        json.dumps(
            {
                "result": _result_payload(result),
                "data_quality": to_jsonable(data_quality),
                "artifacts": artifacts,
            },
            indent=2,
        )
    )


def _validate_bars(
    bars: list[Bar],
    *,
    min_bars: int,
    allowed_session_windows: tuple[SessionWindow, ...] | None = None,
) -> None:
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
    permitted_boundaries = _declared_session_gap_boundaries(allowed_session_windows)
    for prior, current in zip(bars, bars[1:], strict=False):
        if first.timeframe == Timeframe.D1:
            if current.start_ts <= prior.start_ts:
                raise ValueError("daily validation bars must be strictly chronological")
        elif current.start_ts == prior.end_ts:
            continue
        elif (prior.end_ts, current.start_ts) in permitted_boundaries:
            continue
        else:
            raise ValueError("validation bars must be contiguous")


def _declared_session_gap_boundaries(
    session_windows: tuple[SessionWindow, ...] | None,
) -> frozenset[tuple[datetime, datetime]]:
    if session_windows is None:
        return frozenset()
    if not isinstance(session_windows, tuple):
        raise TypeError("allowed_session_windows must be a tuple")
    if any(not isinstance(window, SessionWindow) for window in session_windows):
        raise TypeError("allowed_session_windows must contain SessionWindow values")
    for prior, current in zip(session_windows, session_windows[1:], strict=False):
        if prior.close_ts >= current.open_ts:
            raise ValueError("allowed_session_windows must be strictly chronological")
    return frozenset(
        (prior.close_ts, current.open_ts)
        for prior, current in zip(session_windows, session_windows[1:], strict=False)
    )


def _assert_campaign_replay_invariants(
    result: ValidationResult,
    event_store: EventStore,
) -> None:
    if result.final_position != 0:
        raise RuntimeError("campaign replay must finish flat")
    if len(result.trades) % 2:
        raise RuntimeError("campaign replay must contain complete entry/exit pairs")
    prior_exit: datetime | None = None
    for entry, exit_fill in zip(result.trades[::2], result.trades[1::2], strict=True):
        if entry.side != "buy" or exit_fill.side != "sell":
            raise RuntimeError("campaign replay trades must be long-only entry/exit pairs")
        if exit_fill.filled_at < entry.filled_at:
            raise RuntimeError("campaign replay exit cannot precede its entry")
        if prior_exit is not None and entry.signal_bar_end < prior_exit:
            raise RuntimeError("campaign signal cannot precede the prior exit")
        prior_exit = exit_fill.filled_at

    timestamps = [event.created_at for event in event_store.iter_events()]
    if any(current < prior for prior, current in zip(timestamps, timestamps[1:], strict=False)):
        raise RuntimeError("campaign event timestamps must be nondecreasing")


def _validation_trade(
    order: OrderIntent,
    fill: LocalPaperFill,
    *,
    signal_bar_end: datetime,
) -> ValidationTrade:
    return ValidationTrade(
        client_order_id=order.client_order_id,
        decision_id=order.decision_id,
        side=fill.side,
        quantity=fill.quantity,
        price=fill.price,
        fee=fill.fee,
        signal_bar_end=signal_bar_end,
        filled_at=fill.filled_at,
    )


def _slippage_cost(fill_price: Decimal, reference_open: Decimal, quantity: Decimal) -> Decimal:
    return abs(fill_price - reference_open) * quantity


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
            "total_fees": result.total_fees,
            "total_slippage": result.total_slippage,
            "gross_pnl": result.gross_pnl,
            "after_cost_pnl": result.after_cost_pnl,
            "campaign_id": result.campaign_id,
            "campaign_contract_hash": result.campaign_contract_hash,
            "campaign_phase": result.campaign_phase,
            "campaign_fold_id": result.campaign_fold_id,
            "baseline_id": result.baseline_id,
            "deterministic_seed": result.deterministic_seed,
            "dataset_id": result.dataset_id,
            "dataset_hash": result.dataset_hash,
            "dataset_source_path": (
                None if result.dataset_source_path is None else str(result.dataset_source_path)
            ),
        }
    )


def _validation_artifact_path(artifact_root: Path, run_id: str) -> Path:
    return artifact_root / "validation" / f"{run_id}.json"


def _require_new_path(path: Path, label: str) -> None:
    if path.exists():
        raise FileExistsError(f"{label} already exists: {path}")


def _validate_run_label(value: str) -> None:
    if not value.strip() or any(character in value for character in ("/", "\\", ":")):
        raise ValueError("run identifier must be nonempty and contain no path separators")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _write_event_hash_sidecar(event_jsonl_path: Path) -> str:
    digest = _sha256_file(event_jsonl_path)
    event_jsonl_path.with_name(f"{event_jsonl_path.name}.sha256").write_text(
        f"{digest}\n",
        encoding="utf-8",
    )
    return digest


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
