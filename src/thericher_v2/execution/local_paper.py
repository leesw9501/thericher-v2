"""Broker-free local paper execution simulator.

This module intentionally has no KIS, network, credential, or live-broker
surface. It records local paper lifecycle events into the existing append-only
event log so paper behavior can be replayed during research.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, cast

from thericher_v2.contracts import (
    SCHEMA_VERSION,
    Bar,
    OrderIntent,
    Side,
    Timeframe,
    decimal_value,
    non_negative,
    positive,
    require_utc,
)
from thericher_v2.execution.emergency import EmergencyStore
from thericher_v2.state import Event, EventStore

LocalPaperOrderStatus = Literal["accepted", "rejected", "canceled"]
LOCAL_PAPER_SOURCE = "local_paper"
_US_D1_SESSION_LABEL_MARKETS = frozenset(
    {"US", "NAS", "NASD", "NYS", "NYSE", "AMS", "AMEX", "NYSE_ARCA"}
)


@dataclass(frozen=True)
class LocalPaperOrderResult:
    order: OrderIntent
    status: LocalPaperOrderStatus
    reason: str
    recorded_at: datetime
    event_seq: int
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "recorded_at", require_utc(self.recorded_at, "recorded_at"))


@dataclass(frozen=True)
class LocalPaperFill:
    client_order_id: str
    symbol: str
    market: str
    side: Side
    quantity: Decimal
    price: Decimal
    fee: Decimal
    filled_at: datetime
    source: str = LOCAL_PAPER_SOURCE
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "market", self.market.upper())
        object.__setattr__(self, "quantity", non_negative(self.quantity, "quantity"))
        object.__setattr__(self, "price", non_negative(self.price, "price"))
        object.__setattr__(self, "fee", non_negative(self.fee, "fee"))
        object.__setattr__(self, "filled_at", require_utc(self.filled_at, "filled_at"))

    @property
    def notional(self) -> Decimal:
        return self.price * self.quantity


@dataclass(frozen=True)
class LocalPaperPosition:
    symbol: str
    market: str
    quantity: Decimal
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "market", self.market.upper())
        object.__setattr__(self, "quantity", non_negative(self.quantity, "quantity"))


@dataclass(frozen=True)
class LocalPaperAccount:
    cash: Decimal
    positions: tuple[LocalPaperPosition, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "cash", decimal_value(self.cash, "cash"))

    def quantity(self, *, market: str, symbol: str) -> Decimal:
        key = (market.upper(), symbol.upper())
        for position in self.positions:
            if (position.market, position.symbol) == key:
                return position.quantity
        return Decimal("0")


@dataclass(frozen=True)
class LocalPaperRealizedPnl:
    """FIFO realized accounting for replayable local-paper fills only.

    Open lots remain deliberately unvalued. This projection is not a broker
    account balance, a mark-to-market result, or an input to execution risk.
    """

    realized_after_cost_pnl: Decimal
    closed_segment_count: int
    closed_quantity: Decimal
    open_quantity: Decimal
    local_paper_fill_count: int
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "realized_after_cost_pnl",
            decimal_value(self.realized_after_cost_pnl, "realized_after_cost_pnl"),
        )
        object.__setattr__(
            self,
            "closed_quantity",
            non_negative(self.closed_quantity, "closed_quantity"),
        )
        object.__setattr__(
            self,
            "open_quantity",
            non_negative(self.open_quantity, "open_quantity"),
        )
        if self.closed_segment_count < 0:
            raise ValueError("closed_segment_count must be non-negative")
        if self.local_paper_fill_count < 0:
            raise ValueError("local_paper_fill_count must be non-negative")


@dataclass(frozen=True)
class LocalPaperDecisionPnlSegment:
    """One FIFO local-paper close linked to both decision identities.

    The entry and exit identities show accounting provenance only. They do not
    establish causal credit, broker PnL, or a model-performance result.
    """

    market: str
    symbol: str
    entry_decision_id: str
    exit_decision_id: str
    entry_filled_at: datetime
    exit_filled_at: datetime
    quantity: Decimal
    gross_pnl: Decimal
    entry_fee: Decimal
    exit_fee: Decimal
    realized_after_cost_pnl: Decimal
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "market", self.market.upper())
        object.__setattr__(self, "symbol", self.symbol.upper())
        if not self.market or not self.symbol:
            raise ValueError("market and symbol are required")
        if not self.entry_decision_id or not self.exit_decision_id:
            raise ValueError("entry and exit decision IDs are required")
        entry_filled_at = require_utc(self.entry_filled_at, "entry_filled_at")
        exit_filled_at = require_utc(self.exit_filled_at, "exit_filled_at")
        if exit_filled_at < entry_filled_at:
            raise ValueError("exit_filled_at cannot precede entry_filled_at")
        object.__setattr__(self, "entry_filled_at", entry_filled_at)
        object.__setattr__(self, "exit_filled_at", exit_filled_at)
        object.__setattr__(self, "quantity", positive(self.quantity, "quantity"))
        gross_pnl = decimal_value(self.gross_pnl, "gross_pnl")
        entry_fee = non_negative(self.entry_fee, "entry_fee")
        exit_fee = non_negative(self.exit_fee, "exit_fee")
        realized_after_cost_pnl = decimal_value(
            self.realized_after_cost_pnl,
            "realized_after_cost_pnl",
        )
        if gross_pnl - entry_fee - exit_fee != realized_after_cost_pnl:
            raise ValueError("decision PnL segment does not reconcile fees")
        object.__setattr__(self, "gross_pnl", gross_pnl)
        object.__setattr__(self, "entry_fee", entry_fee)
        object.__setattr__(self, "exit_fee", exit_fee)
        object.__setattr__(self, "realized_after_cost_pnl", realized_after_cost_pnl)


@dataclass(frozen=True)
class LocalPaperDecisionPnlTotal:
    """FIFO realized PnL grouped by a decision in one explicit role."""

    decision_id: str
    closed_segment_count: int
    closed_quantity: Decimal
    gross_pnl: Decimal
    fee_total: Decimal
    realized_after_cost_pnl: Decimal
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.decision_id:
            raise ValueError("decision_id is required")
        if self.closed_segment_count <= 0:
            raise ValueError("closed_segment_count must be positive")
        closed_quantity = positive(self.closed_quantity, "closed_quantity")
        gross_pnl = decimal_value(self.gross_pnl, "gross_pnl")
        fee_total = non_negative(self.fee_total, "fee_total")
        realized_after_cost_pnl = decimal_value(
            self.realized_after_cost_pnl,
            "realized_after_cost_pnl",
        )
        if gross_pnl - fee_total != realized_after_cost_pnl:
            raise ValueError("decision PnL total does not reconcile fees")
        object.__setattr__(self, "closed_quantity", closed_quantity)
        object.__setattr__(self, "gross_pnl", gross_pnl)
        object.__setattr__(self, "fee_total", fee_total)
        object.__setattr__(self, "realized_after_cost_pnl", realized_after_cost_pnl)


@dataclass(frozen=True)
class LocalPaperDecisionPairPnlTotal:
    """FIFO realized PnL grouped by the entry and exit decision pair."""

    entry_decision_id: str
    exit_decision_id: str
    closed_segment_count: int
    closed_quantity: Decimal
    gross_pnl: Decimal
    fee_total: Decimal
    realized_after_cost_pnl: Decimal
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.entry_decision_id or not self.exit_decision_id:
            raise ValueError("entry and exit decision IDs are required")
        if self.closed_segment_count <= 0:
            raise ValueError("closed_segment_count must be positive")
        closed_quantity = positive(self.closed_quantity, "closed_quantity")
        gross_pnl = decimal_value(self.gross_pnl, "gross_pnl")
        fee_total = non_negative(self.fee_total, "fee_total")
        realized_after_cost_pnl = decimal_value(
            self.realized_after_cost_pnl,
            "realized_after_cost_pnl",
        )
        if gross_pnl - fee_total != realized_after_cost_pnl:
            raise ValueError("decision-pair PnL total does not reconcile fees")
        object.__setattr__(self, "closed_quantity", closed_quantity)
        object.__setattr__(self, "gross_pnl", gross_pnl)
        object.__setattr__(self, "fee_total", fee_total)
        object.__setattr__(self, "realized_after_cost_pnl", realized_after_cost_pnl)


@dataclass(frozen=True)
class LocalPaperDecisionPnl:
    """Offline decision-identity projection of existing local-paper accounting."""

    aggregate: LocalPaperRealizedPnl
    closed_segments: tuple[LocalPaperDecisionPnlSegment, ...]
    entry_decision_totals: tuple[LocalPaperDecisionPnlTotal, ...]
    exit_decision_totals: tuple[LocalPaperDecisionPnlTotal, ...]
    decision_pair_totals: tuple[LocalPaperDecisionPairPnlTotal, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.schema_version != SCHEMA_VERSION
            or not isinstance(self.aggregate, LocalPaperRealizedPnl)
            or self.aggregate.schema_version != SCHEMA_VERSION
            or not isinstance(self.closed_segments, tuple)
            or not isinstance(self.entry_decision_totals, tuple)
            or not isinstance(self.exit_decision_totals, tuple)
            or not isinstance(self.decision_pair_totals, tuple)
        ):
            raise ValueError("local-paper decision PnL projection is invalid")
        if any(
            not isinstance(segment, LocalPaperDecisionPnlSegment)
            or segment.schema_version != SCHEMA_VERSION
            for segment in self.closed_segments
        ):
            raise ValueError("local-paper decision PnL segments are invalid")
        totals = (
            *self.entry_decision_totals,
            *self.exit_decision_totals,
            *self.decision_pair_totals,
        )
        if any(
            not isinstance(
                total,
                LocalPaperDecisionPnlTotal | LocalPaperDecisionPairPnlTotal,
            )
            or total.schema_version != SCHEMA_VERSION
            for total in totals
        ):
            raise ValueError("local-paper decision PnL totals are invalid")
        if (
            self.aggregate.closed_segment_count != len(self.closed_segments)
            or self.aggregate.closed_quantity
            != sum((segment.quantity for segment in self.closed_segments), Decimal("0"))
            or self.aggregate.realized_after_cost_pnl
            != sum(
                (segment.realized_after_cost_pnl for segment in self.closed_segments),
                Decimal("0"),
            )
        ):
            raise ValueError("local-paper decision PnL does not reconcile closed segments")
        if self.closed_segments and self.aggregate.local_paper_fill_count < len(
            self.closed_segments
        ) + 1:
            raise ValueError("local-paper decision PnL fill count cannot close its segments")
        if self.entry_decision_totals != _decision_pnl_totals(
            self.closed_segments,
            role="entry",
        ):
            raise ValueError("local-paper decision PnL entry totals do not reconcile")
        if self.exit_decision_totals != _decision_pnl_totals(
            self.closed_segments,
            role="exit",
        ):
            raise ValueError("local-paper decision PnL exit totals do not reconcile")
        if self.decision_pair_totals != _decision_pair_pnl_totals(self.closed_segments):
            raise ValueError("local-paper decision PnL pair totals do not reconcile")


@dataclass(frozen=True)
class LocalPaperExecutionResult:
    order_result: LocalPaperOrderResult
    account: LocalPaperAccount
    fill: LocalPaperFill | None = None


class LocalPaperBroker:
    def __init__(
        self,
        *,
        event_store: EventStore,
        emergency_store: EmergencyStore,
        starting_cash: Decimal = Decimal("10000"),
        fee_bps: Decimal = Decimal("1"),
        slippage_bps: Decimal = Decimal("0"),
    ) -> None:
        self.event_store = event_store
        self.emergency_store = emergency_store
        self.starting_cash = decimal_value(starting_cash, "starting_cash")
        self.fee_bps = non_negative(fee_bps, "fee_bps")
        self.slippage_bps = non_negative(slippage_bps, "slippage_bps")

    def account(self) -> LocalPaperAccount:
        return replay_local_paper_account(self.event_store, starting_cash=self.starting_cash)

    def submit_order(
        self,
        order: OrderIntent,
        *,
        submitted_at: datetime | None = None,
    ) -> LocalPaperOrderResult:
        recorded_at = require_utc(submitted_at or order.created_at, "submitted_at")
        if recorded_at < order.created_at:
            raise ValueError("submitted_at cannot precede order.created_at")
        if self._client_order_id_seen(order.client_order_id):
            return self._record_order_result(
                order,
                status="rejected",
                reason="duplicate_client_order_id",
                recorded_at=recorded_at,
            )
        if order.valid_until is not None and recorded_at >= order.valid_until:
            return self._record_order_result(
                order,
                status="rejected",
                reason="intent_expired",
                recorded_at=recorded_at,
            )
        if self.emergency_store.read().blocks_new_orders:
            return self._record_order_result(
                order,
                status="rejected",
                reason="emergency_stop_active",
                recorded_at=recorded_at,
            )
        return self._record_order_result(
            order,
            status="accepted",
            reason="accepted_for_next_bar_open",
            recorded_at=recorded_at,
        )

    def fill_next_bar(
        self,
        client_order_id: str,
        *,
        signal_bar: Bar,
        execution_bar: Bar,
    ) -> LocalPaperExecutionResult:
        recorded_fill = self._recorded_fill_event(client_order_id)
        if recorded_fill is not None:
            order = self._accepted_order(client_order_id)
            accepted_at = self._accepted_order_recorded_at(client_order_id)
            if order is None or accepted_at is None:
                raise ValueError("recorded local paper fill has no accepted local paper order")
            self._validate_next_bar(order, signal_bar, execution_bar)
            self._validate_execution_after_acceptance(
                order,
                accepted_at,
                execution_bar,
            )
            return self._recover_recorded_fill(
                order,
                recorded_fill=recorded_fill,
                signal_bar=signal_bar,
                execution_bar=execution_bar,
            )

        order = self._pending_order(client_order_id)
        accepted_at = self._accepted_order_recorded_at(client_order_id)
        if order is None or accepted_at is None:
            raise ValueError("client_order_id has no pending accepted local paper order")
        self._validate_next_bar(order, signal_bar, execution_bar)
        self._validate_execution_after_acceptance(
            order,
            accepted_at,
            execution_bar,
        )
        if order.valid_until is not None and execution_bar.start_ts >= order.valid_until:
            return self._rejected_execution(
                order,
                reason="intent_expired",
                recorded_at=execution_bar.start_ts,
            )
        fill = self._expected_fill(order, execution_bar)
        if order.limit_price is not None and not self._limit_is_marketable(order, fill.price):
            return self._rejected_execution(
                order,
                reason="limit_not_marketable_at_next_bar_open",
                recorded_at=execution_bar.start_ts,
            )

        account = self.account()
        quantity = order.quantity
        notional = fill.notional
        if order.side == "buy" and account.cash < notional + fill.fee:
            return self._rejected_execution(
                order,
                reason="insufficient_cash",
                recorded_at=execution_bar.start_ts,
            )
        if (
            order.side == "sell"
            and account.quantity(market=order.market, symbol=order.symbol) < quantity
        ):
            return self._rejected_execution(
                order,
                reason="insufficient_position",
                recorded_at=execution_bar.start_ts,
            )

        fill_event = self.event_store.append(
            Event(
                event_type="fill",
                created_at=fill.filled_at,
                payload={
                    "source": LOCAL_PAPER_SOURCE,
                    "client_order_id": fill.client_order_id,
                    "market": fill.market,
                    "symbol": fill.symbol,
                    "side": fill.side,
                    "quantity": str(fill.quantity),
                    "price": str(fill.price),
                    "fee": str(fill.fee),
                    "signal_bar_identity": _bar_identity(signal_bar),
                    "execution_bar_identity": _bar_identity(execution_bar),
                },
            )
        )
        account = self.account()
        self._record_portfolio_snapshot(account, recorded_at=fill.filled_at)
        return LocalPaperExecutionResult(
            order_result=LocalPaperOrderResult(
                order=order,
                status="accepted",
                reason="filled_at_next_bar_open",
                recorded_at=fill.filled_at,
                event_seq=fill_event.seq,
            ),
            account=account,
            fill=fill,
        )

    def _expected_fill(self, order: OrderIntent, execution_bar: Bar) -> LocalPaperFill:
        price = self._execution_price(execution_bar.open, order.side)
        return LocalPaperFill(
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            market=order.market,
            side=order.side,
            quantity=order.quantity,
            price=price,
            fee=self._fee(price * order.quantity),
            filled_at=execution_bar.start_ts,
        )

    def _recorded_fill_event(self, client_order_id: str) -> Event | None:
        fills = [
            event
            for event in self.event_store.iter_events()
            if event.event_type == "fill"
            and event.payload.get("source") == LOCAL_PAPER_SOURCE
            and event.payload.get("client_order_id") == client_order_id
        ]
        if len(fills) > 1:
            raise ValueError("client_order_id has multiple recorded local paper fills")
        return fills[0] if fills else None

    def _accepted_order(self, client_order_id: str) -> OrderIntent | None:
        accepted = [
            _order_from_payload(event.payload)
            for event in self.event_store.iter_events()
            if event.event_type == "local_paper_order_accepted"
            and event.payload.get("source") == LOCAL_PAPER_SOURCE
            and event.payload.get("client_order_id") == client_order_id
        ]
        if len(accepted) > 1:
            raise ValueError("client_order_id has multiple accepted local paper orders")
        return accepted[0] if accepted else None

    def _accepted_order_recorded_at(self, client_order_id: str) -> datetime | None:
        accepted = [
            event
            for event in self.event_store.iter_events()
            if event.event_type == "local_paper_order_accepted"
            and event.payload.get("source") == LOCAL_PAPER_SOURCE
            and event.payload.get("client_order_id") == client_order_id
        ]
        if len(accepted) > 1:
            raise ValueError("client_order_id has multiple accepted local paper orders")
        return accepted[0].created_at if accepted else None

    def _recover_recorded_fill(
        self,
        order: OrderIntent,
        *,
        recorded_fill: Event,
        signal_bar: Bar,
        execution_bar: Bar,
    ) -> LocalPaperExecutionResult:
        expected_fill = self._expected_fill(order, execution_bar)
        actual_fill = _fill_from_event(recorded_fill)
        if actual_fill != expected_fill:
            raise ValueError("recorded local paper fill does not match requested execution")
        if (
            recorded_fill.payload.get("signal_bar_identity") != _bar_identity(signal_bar)
            or recorded_fill.payload.get("execution_bar_identity") != _bar_identity(execution_bar)
        ):
            raise ValueError(
                "recorded local paper fill bar identity does not match requested execution"
            )

        # Fill events are authoritative; a retry must not manufacture another fill
        # or a derived snapshot after a post-fill interruption.
        return LocalPaperExecutionResult(
            order_result=LocalPaperOrderResult(
                order=order,
                status="accepted",
                reason="filled_at_next_bar_open",
                recorded_at=actual_fill.filled_at,
                event_seq=recorded_fill.seq,
            ),
            account=self.account(),
            fill=actual_fill,
        )

    def submit_and_fill_next_bar(
        self,
        order: OrderIntent,
        *,
        signal_bar: Bar,
        execution_bar: Bar,
    ) -> LocalPaperExecutionResult:
        order_result = self.submit_order(order)
        if order_result.status != "accepted":
            return LocalPaperExecutionResult(order_result=order_result, account=self.account())
        return self.fill_next_bar(
            order.client_order_id,
            signal_bar=signal_bar,
            execution_bar=execution_bar,
        )

    def cancel_order(
        self,
        client_order_id: str,
        *,
        canceled_at: datetime,
        reason: str = "local_cancel",
    ) -> LocalPaperOrderResult:
        order = self._pending_order(client_order_id)
        if order is None:
            raise ValueError("client_order_id has no pending accepted local paper order")
        return self._record_order_result(
            order,
            status="canceled",
            reason=reason,
            recorded_at=canceled_at,
        )

    def _record_order_result(
        self,
        order: OrderIntent,
        *,
        status: LocalPaperOrderStatus,
        reason: str,
        recorded_at: datetime,
    ) -> LocalPaperOrderResult:
        recorded_at = require_utc(recorded_at, "recorded_at")
        event = self.event_store.append(
            Event(
                event_type=f"local_paper_order_{status}",
                created_at=recorded_at,
                payload={
                    "source": LOCAL_PAPER_SOURCE,
                    "status": status,
                    "reason": reason,
                    **_order_payload(order),
                },
            )
        )
        return LocalPaperOrderResult(
            order=order,
            status=status,
            reason=reason,
            recorded_at=recorded_at,
            event_seq=event.seq,
        )

    def _rejected_execution(
        self,
        order: OrderIntent,
        *,
        reason: str,
        recorded_at: datetime,
    ) -> LocalPaperExecutionResult:
        order_result = self._record_order_result(
            order,
            status="rejected",
            reason=reason,
            recorded_at=recorded_at,
        )
        return LocalPaperExecutionResult(order_result=order_result, account=self.account())

    def _record_portfolio_snapshot(
        self,
        account: LocalPaperAccount,
        *,
        recorded_at: datetime,
    ) -> None:
        self.event_store.append(
            Event(
                event_type="local_paper_portfolio_snapshot",
                created_at=recorded_at,
                payload={
                    "source": LOCAL_PAPER_SOURCE,
                    "cash": str(account.cash),
                    "positions": [
                        {
                            "market": position.market,
                            "symbol": position.symbol,
                            "quantity": str(position.quantity),
                        }
                        for position in account.positions
                    ],
                },
            )
        )

    def _client_order_id_seen(self, client_order_id: str) -> bool:
        return any(
            event.payload.get("source") == LOCAL_PAPER_SOURCE
            and event.payload.get("client_order_id") == client_order_id
            for event in self.event_store.iter_events()
        )

    def _pending_order(self, client_order_id: str) -> OrderIntent | None:
        accepted: OrderIntent | None = None
        closed = False
        for event in sorted(self.event_store.iter_events(), key=lambda item: item.seq):
            if (
                event.payload.get("source") != LOCAL_PAPER_SOURCE
                or event.payload.get("client_order_id") != client_order_id
            ):
                continue
            if event.event_type == "local_paper_order_accepted":
                accepted = _order_from_payload(event.payload)
                closed = False
            elif event.event_type in {"fill", "local_paper_order_canceled"}:
                closed = True
            elif (
                event.event_type == "local_paper_order_rejected"
                and event.payload.get("reason") != "duplicate_client_order_id"
            ):
                closed = True
        if accepted is None or closed:
            return None
        return accepted

    def _validate_next_bar(self, order: OrderIntent, signal_bar: Bar, execution_bar: Bar) -> None:
        if signal_bar.symbol != order.symbol or signal_bar.market != order.market:
            raise ValueError("signal_bar must match order market and symbol")
        if execution_bar.symbol != order.symbol or execution_bar.market != order.market:
            raise ValueError("execution_bar must match order market and symbol")
        if execution_bar.timeframe != signal_bar.timeframe:
            raise ValueError("signal and execution bars must use the same timeframe")
        if not signal_bar.complete or not execution_bar.complete:
            raise ValueError("signal and execution bars must be complete")
        if signal_bar.timeframe == Timeframe.D1:
            if (
                execution_bar.start_ts <= signal_bar.start_ts
                or execution_bar.start_ts.date() <= signal_bar.start_ts.date()
            ):
                raise ValueError("daily execution_bar must be on a later observed UTC date")
            return
        if execution_bar.start_ts != signal_bar.end_ts:
            raise ValueError("execution_bar must start at signal_bar.end_ts")

    @staticmethod
    def _validate_execution_after_acceptance(
        order: OrderIntent,
        accepted_at: datetime,
        execution_bar: Bar,
    ) -> None:
        available_at = max(require_utc(accepted_at, "accepted_at"), order.created_at)
        if execution_bar.timeframe == Timeframe.D1:
            if order.market not in _US_D1_SESSION_LABEL_MARKETS:
                raise ValueError(
                    "daily local-paper next-bar timing requires a US session-label market"
                )
            if available_at.date() <= execution_bar.start_ts.date():
                return
            raise ValueError("accepted local paper order must not follow execution bar")
        if available_at > execution_bar.start_ts:
            raise ValueError("accepted local paper order must not follow execution bar")

    def _execution_price(self, price: Decimal, side: Side) -> Decimal:
        adjustment = Decimal("1") + (self.slippage_bps / Decimal("10000"))
        if side == "sell":
            adjustment = Decimal("1") - (self.slippage_bps / Decimal("10000"))
        return (price * adjustment).quantize(Decimal("0.0001"))

    def _fee(self, notional: Decimal) -> Decimal:
        return (notional * self.fee_bps / Decimal("10000")).quantize(Decimal("0.0001"))

    @staticmethod
    def _limit_is_marketable(order: OrderIntent, fill_price: Decimal) -> bool:
        if order.limit_price is None:
            return True
        if order.side == "buy":
            return fill_price <= order.limit_price
        return fill_price >= order.limit_price


def replay_local_paper_account(
    event_store: EventStore,
    *,
    starting_cash: Decimal = Decimal("10000"),
) -> LocalPaperAccount:
    cash = decimal_value(starting_cash, "starting_cash")
    positions: dict[tuple[str, str], Decimal] = {}
    for event in sorted(event_store.iter_events(), key=lambda item: item.seq):
        if event.event_type != "fill" or event.payload.get("source") != LOCAL_PAPER_SOURCE:
            continue
        market = str(event.payload["market"]).upper()
        symbol = str(event.payload["symbol"]).upper()
        side = str(event.payload["side"])
        quantity = Decimal(str(event.payload["quantity"]))
        price = Decimal(str(event.payload["price"]))
        fee = Decimal(str(event.payload.get("fee", "0")))
        notional = price * quantity
        key = (market, symbol)
        if side == "buy":
            cash -= notional + fee
            positions[key] = positions.get(key, Decimal("0")) + quantity
        elif side == "sell":
            cash += notional - fee
            positions[key] = positions.get(key, Decimal("0")) - quantity
        else:
            raise ValueError(f"unknown fill side: {side}")

    position_items = tuple(
        LocalPaperPosition(market=market, symbol=symbol, quantity=quantity)
        for (market, symbol), quantity in sorted(positions.items())
        if quantity != 0
    )
    return LocalPaperAccount(cash=cash, positions=position_items)


@dataclass(frozen=True)
class _LocalPaperPnlLot:
    price: Decimal
    remaining_quantity: Decimal
    remaining_fee: Decimal


@dataclass(frozen=True)
class _LocalPaperDecisionPnlLot:
    decision_id: str
    filled_at: datetime
    price: Decimal
    remaining_quantity: Decimal
    remaining_fee: Decimal


def replay_local_paper_realized_pnl(events: Iterable[Event]) -> LocalPaperRealizedPnl:
    """Replay FIFO realized-after-fee PnL from the supplied local-paper events.

    Events from other routes are intentionally ignored so a local monitor stays
    isolated from broker or test-double activity. A malformed local fill or an
    oversold local history raises instead of manufacturing a PnL value.
    """

    open_lots: dict[tuple[str, str], list[_LocalPaperPnlLot]] = {}
    realized_after_cost_pnl = Decimal("0")
    closed_segment_count = 0
    closed_quantity = Decimal("0")
    local_paper_fill_count = 0

    for event in sorted(events, key=lambda item: item.seq):
        if event.event_type != "fill" or event.payload.get("source") != LOCAL_PAPER_SOURCE:
            continue
        fill = _fill_from_event(event)
        if fill.side not in {"buy", "sell"}:
            raise ValueError("local paper fill side is invalid")
        if fill.quantity <= 0 or fill.price <= 0:
            raise ValueError("local paper fill quantity and price must be positive")

        local_paper_fill_count += 1
        key = (fill.market, fill.symbol)
        if fill.side == "buy":
            open_lots.setdefault(key, []).append(
                _LocalPaperPnlLot(
                    price=fill.price,
                    remaining_quantity=fill.quantity,
                    remaining_fee=fill.fee,
                )
            )
            continue

        sell_quantity_remaining = fill.quantity
        sell_fee_remaining = fill.fee
        lots = open_lots.get(key, [])
        while sell_quantity_remaining > 0:
            if not lots:
                raise ValueError("local paper sell fill exceeds available FIFO lots")
            entry = lots[0]
            matched_quantity = min(entry.remaining_quantity, sell_quantity_remaining)
            entry_fee = _allocated_fee(
                total_fee=entry.remaining_fee,
                total_quantity=entry.remaining_quantity,
                matched_quantity=matched_quantity,
            )
            exit_fee = _allocated_fee(
                total_fee=sell_fee_remaining,
                total_quantity=sell_quantity_remaining,
                matched_quantity=matched_quantity,
            )
            realized_after_cost_pnl += (
                (fill.price - entry.price) * matched_quantity - entry_fee - exit_fee
            )
            closed_segment_count += 1
            closed_quantity += matched_quantity

            entry_quantity_remaining = entry.remaining_quantity - matched_quantity
            if entry_quantity_remaining == 0:
                lots.pop(0)
            else:
                lots[0] = _LocalPaperPnlLot(
                    price=entry.price,
                    remaining_quantity=entry_quantity_remaining,
                    remaining_fee=entry.remaining_fee - entry_fee,
                )
            sell_quantity_remaining -= matched_quantity
            sell_fee_remaining -= exit_fee

    open_quantity = sum(
        (lot.remaining_quantity for lots in open_lots.values() for lot in lots),
        Decimal("0"),
    )
    return LocalPaperRealizedPnl(
        realized_after_cost_pnl=realized_after_cost_pnl,
        closed_segment_count=closed_segment_count,
        closed_quantity=closed_quantity,
        open_quantity=open_quantity,
        local_paper_fill_count=local_paper_fill_count,
    )


def replay_local_paper_decision_pnl(events: Iterable[Event]) -> LocalPaperDecisionPnl:
    """Replay FIFO local-paper accounting with explicit decision identities.

    Only existing `local_paper` acceptance and fill events participate. This is
    an offline accounting projection: it does not establish decision causality,
    broker PnL, or a model result.
    """

    ordered_events = tuple(sorted(events, key=lambda item: item.seq))
    accepted_orders: dict[str, OrderIntent] = {}
    inactive_order_ids: set[str] = set()
    filled_order_ids: set[str] = set()
    open_lots: dict[tuple[str, str], list[_LocalPaperDecisionPnlLot]] = {}
    closed_segments: list[LocalPaperDecisionPnlSegment] = []
    local_paper_fill_count = 0

    for event in ordered_events:
        if event.payload.get("source") != LOCAL_PAPER_SOURCE:
            continue
        if event.event_type == "local_paper_order_accepted":
            order = _order_from_payload(event.payload)
            if not order.client_order_id or not order.decision_id:
                raise ValueError("accepted local paper order requires IDs")
            if order.client_order_id in accepted_orders:
                raise ValueError("client_order_id has multiple accepted local paper orders")
            accepted_orders[order.client_order_id] = order
            continue

        if event.event_type in {"local_paper_order_canceled", "local_paper_order_rejected"}:
            client_order_id = str(event.payload.get("client_order_id") or "")
            if (
                client_order_id in accepted_orders
                and event.payload.get("reason") != "duplicate_client_order_id"
            ):
                inactive_order_ids.add(client_order_id)
            continue

        if event.event_type != "fill":
            continue

        fill = _fill_from_event(event)
        order = accepted_orders.get(fill.client_order_id)
        if order is None:
            raise ValueError("local paper fill has no accepted local paper order")
        if fill.client_order_id in inactive_order_ids:
            raise ValueError("local paper fill follows an inactive local paper order")
        if fill.client_order_id in filled_order_ids:
            raise ValueError("client_order_id has multiple recorded local paper fills")
        if (
            fill.market != order.market
            or fill.symbol != order.symbol
            or fill.side != order.side
            or fill.quantity != order.quantity
        ):
            raise ValueError("local paper fill does not match accepted local paper order")
        if fill.side not in {"buy", "sell"}:
            raise ValueError("local paper fill side is invalid")
        if fill.quantity <= 0 or fill.price <= 0:
            raise ValueError("local paper fill quantity and price must be positive")

        filled_order_ids.add(fill.client_order_id)
        local_paper_fill_count += 1
        key = (fill.market, fill.symbol)
        if fill.side == "buy":
            open_lots.setdefault(key, []).append(
                _LocalPaperDecisionPnlLot(
                    decision_id=order.decision_id,
                    filled_at=fill.filled_at,
                    price=fill.price,
                    remaining_quantity=fill.quantity,
                    remaining_fee=fill.fee,
                )
            )
            continue

        sell_quantity_remaining = fill.quantity
        sell_fee_remaining = fill.fee
        lots = open_lots.get(key, [])
        while sell_quantity_remaining > 0:
            if not lots:
                raise ValueError("local paper sell fill exceeds available FIFO lots")
            entry = lots[0]
            matched_quantity = min(entry.remaining_quantity, sell_quantity_remaining)
            entry_fee = _allocated_fee(
                total_fee=entry.remaining_fee,
                total_quantity=entry.remaining_quantity,
                matched_quantity=matched_quantity,
            )
            exit_fee = _allocated_fee(
                total_fee=sell_fee_remaining,
                total_quantity=sell_quantity_remaining,
                matched_quantity=matched_quantity,
            )
            gross_pnl = (fill.price - entry.price) * matched_quantity
            closed_segments.append(
                LocalPaperDecisionPnlSegment(
                    market=fill.market,
                    symbol=fill.symbol,
                    entry_decision_id=entry.decision_id,
                    exit_decision_id=order.decision_id,
                    entry_filled_at=entry.filled_at,
                    exit_filled_at=fill.filled_at,
                    quantity=matched_quantity,
                    gross_pnl=gross_pnl,
                    entry_fee=entry_fee,
                    exit_fee=exit_fee,
                    realized_after_cost_pnl=gross_pnl - entry_fee - exit_fee,
                )
            )

            entry_quantity_remaining = entry.remaining_quantity - matched_quantity
            if entry_quantity_remaining == 0:
                lots.pop(0)
            else:
                lots[0] = _LocalPaperDecisionPnlLot(
                    decision_id=entry.decision_id,
                    filled_at=entry.filled_at,
                    price=entry.price,
                    remaining_quantity=entry_quantity_remaining,
                    remaining_fee=entry.remaining_fee - entry_fee,
                )
            sell_quantity_remaining -= matched_quantity
            sell_fee_remaining -= exit_fee

    aggregate = replay_local_paper_realized_pnl(ordered_events)
    segments = tuple(closed_segments)
    open_quantity = sum(
        (lot.remaining_quantity for lots in open_lots.values() for lot in lots),
        Decimal("0"),
    )
    if (
        aggregate.realized_after_cost_pnl
        != sum((segment.realized_after_cost_pnl for segment in segments), Decimal("0"))
        or aggregate.closed_segment_count != len(segments)
        or aggregate.closed_quantity
        != sum((segment.quantity for segment in segments), Decimal("0"))
        or aggregate.open_quantity != open_quantity
        or aggregate.local_paper_fill_count != local_paper_fill_count
    ):
        raise ValueError("decision PnL replay does not match local paper accounting")
    return LocalPaperDecisionPnl(
        aggregate=aggregate,
        closed_segments=segments,
        entry_decision_totals=_decision_pnl_totals(segments, role="entry"),
        exit_decision_totals=_decision_pnl_totals(segments, role="exit"),
        decision_pair_totals=_decision_pair_pnl_totals(segments),
    )


def _decision_pnl_totals(
    segments: tuple[LocalPaperDecisionPnlSegment, ...],
    *,
    role: Literal["entry", "exit"],
) -> tuple[LocalPaperDecisionPnlTotal, ...]:
    totals: dict[str, tuple[int, Decimal, Decimal, Decimal, Decimal]] = {}
    for segment in segments:
        decision_id = (
            segment.entry_decision_id if role == "entry" else segment.exit_decision_id
        )
        count, quantity, gross_pnl, fee_total, realized_after_cost_pnl = totals.get(
            decision_id,
            (0, Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0")),
        )
        totals[decision_id] = (
            count + 1,
            quantity + segment.quantity,
            gross_pnl + segment.gross_pnl,
            fee_total + segment.entry_fee + segment.exit_fee,
            realized_after_cost_pnl + segment.realized_after_cost_pnl,
        )
    return tuple(
        LocalPaperDecisionPnlTotal(
            decision_id=decision_id,
            closed_segment_count=count,
            closed_quantity=quantity,
            gross_pnl=gross_pnl,
            fee_total=fee_total,
            realized_after_cost_pnl=realized_after_cost_pnl,
        )
        for decision_id, (count, quantity, gross_pnl, fee_total, realized_after_cost_pnl) in sorted(
            totals.items()
        )
    )


def _decision_pair_pnl_totals(
    segments: tuple[LocalPaperDecisionPnlSegment, ...],
) -> tuple[LocalPaperDecisionPairPnlTotal, ...]:
    totals: dict[tuple[str, str], tuple[int, Decimal, Decimal, Decimal, Decimal]] = {}
    for segment in segments:
        key = (segment.entry_decision_id, segment.exit_decision_id)
        count, quantity, gross_pnl, fee_total, realized_after_cost_pnl = totals.get(
            key,
            (0, Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0")),
        )
        totals[key] = (
            count + 1,
            quantity + segment.quantity,
            gross_pnl + segment.gross_pnl,
            fee_total + segment.entry_fee + segment.exit_fee,
            realized_after_cost_pnl + segment.realized_after_cost_pnl,
        )
    return tuple(
        LocalPaperDecisionPairPnlTotal(
            entry_decision_id=entry_decision_id,
            exit_decision_id=exit_decision_id,
            closed_segment_count=count,
            closed_quantity=quantity,
            gross_pnl=gross_pnl,
            fee_total=fee_total,
            realized_after_cost_pnl=realized_after_cost_pnl,
        )
        for (
            entry_decision_id,
            exit_decision_id,
        ), (count, quantity, gross_pnl, fee_total, realized_after_cost_pnl) in sorted(
            totals.items()
        )
    )


def _allocated_fee(
    *,
    total_fee: Decimal,
    total_quantity: Decimal,
    matched_quantity: Decimal,
) -> Decimal:
    if total_quantity <= 0 or matched_quantity <= 0 or matched_quantity > total_quantity:
        raise ValueError("FIFO fee allocation quantity is invalid")
    if matched_quantity == total_quantity:
        return total_fee
    return total_fee * matched_quantity / total_quantity


def _order_payload(order: OrderIntent) -> dict[str, str]:
    payload = {
        "client_order_id": order.client_order_id,
        "market": order.market,
        "symbol": order.symbol,
        "side": order.side,
        "quantity": str(order.quantity),
        "decision_id": order.decision_id,
        "created_at": order.created_at.isoformat(),
    }
    if order.limit_price is not None:
        payload["limit_price"] = str(order.limit_price)
    if order.valid_until is not None:
        payload["valid_until"] = order.valid_until.isoformat()
    return payload


def _order_from_payload(payload: dict[str, object]) -> OrderIntent:
    limit_price = payload.get("limit_price")
    valid_until = payload.get("valid_until")
    return OrderIntent(
        client_order_id=str(payload["client_order_id"]),
        symbol=str(payload["symbol"]),
        market=str(payload["market"]),
        side=cast(Side, str(payload["side"])),
        quantity=Decimal(str(payload["quantity"])),
        limit_price=None if limit_price is None else Decimal(str(limit_price)),
        decision_id=str(payload["decision_id"]),
        created_at=datetime.fromisoformat(str(payload["created_at"])).astimezone(UTC),
        valid_until=(
            None
            if valid_until is None
            else datetime.fromisoformat(str(valid_until)).astimezone(UTC)
        ),
    )


def _fill_from_event(event: Event) -> LocalPaperFill:
    payload = event.payload
    return LocalPaperFill(
        client_order_id=str(payload["client_order_id"]),
        symbol=str(payload["symbol"]),
        market=str(payload["market"]),
        side=cast(Side, str(payload["side"])),
        quantity=Decimal(str(payload["quantity"])),
        price=Decimal(str(payload["price"])),
        fee=Decimal(str(payload.get("fee", "0"))),
        filled_at=event.created_at,
        source=str(payload["source"]),
        schema_version=event.schema_version,
    )


def _bar_identity(bar: Bar) -> str:
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
