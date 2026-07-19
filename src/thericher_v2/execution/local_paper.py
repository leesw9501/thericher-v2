"""Broker-free local paper execution simulator.

This module intentionally has no KIS, network, credential, or live-broker
surface. It records local paper lifecycle events into the existing append-only
event log so paper behavior can be replayed during research.
"""

from __future__ import annotations

import hashlib
import json
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
    require_utc,
)
from thericher_v2.execution.emergency import EmergencyStore
from thericher_v2.state import Event, EventStore

LocalPaperOrderStatus = Literal["accepted", "rejected", "canceled"]
LOCAL_PAPER_SOURCE = "local_paper"


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
        if self._client_order_id_seen(order.client_order_id):
            return self._record_order_result(
                order,
                status="rejected",
                reason="duplicate_client_order_id",
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
            if order is None:
                raise ValueError("recorded local paper fill has no accepted local paper order")
            self._validate_next_bar(order, signal_bar, execution_bar)
            return self._recover_recorded_fill(
                order,
                recorded_fill=recorded_fill,
                signal_bar=signal_bar,
                execution_bar=execution_bar,
            )

        order = self._pending_order(client_order_id)
        if order is None:
            raise ValueError("client_order_id has no pending accepted local paper order")
        self._validate_next_bar(order, signal_bar, execution_bar)
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
    return payload


def _order_from_payload(payload: dict[str, object]) -> OrderIntent:
    limit_price = payload.get("limit_price")
    return OrderIntent(
        client_order_id=str(payload["client_order_id"]),
        symbol=str(payload["symbol"]),
        market=str(payload["market"]),
        side=cast(Side, str(payload["side"])),
        quantity=Decimal(str(payload["quantity"])),
        limit_price=None if limit_price is None else Decimal(str(limit_price)),
        decision_id=str(payload["decision_id"]),
        created_at=datetime.fromisoformat(str(payload["created_at"])).astimezone(UTC),
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
