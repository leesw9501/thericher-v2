"""Broker-neutral lifecycle contracts with external execution disabled."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Protocol, TypeVar

from thericher_v2.contracts import (
    SCHEMA_VERSION,
    OrderIntent,
    Side,
    decimal_value,
    non_negative,
    positive,
    require_utc,
)

from .local_paper import LOCAL_PAPER_SOURCE

BrokerAccountMode = Literal["disabled"]
BrokerAction = Literal["submit", "cancel", "status"]
BrokerUnavailableStatus = Literal["unavailable"]
BrokerOrderState = Literal[
    "recorded",
    "submitted",
    "partially_filled",
    "filled",
    "cancelled",
    "outcome_unknown",
]
BrokerAckState = Literal["accepted", "rejected"]
CancelState = Literal["cancelled", "not_found", "not_open", "outcome_unknown"]

BROKER_DISABLED_SOURCE = "broker_disabled"
BROKER_FAKE_SOURCE = "in_memory_broker"
BROKER_EXECUTION_ENABLED = False

if BROKER_DISABLED_SOURCE == LOCAL_PAPER_SOURCE:
    raise RuntimeError("disabled broker source must remain distinct from local paper")


@dataclass(frozen=True)
class BrokerCapabilities:
    broker: Literal["kis"] = "kis"
    account_mode: BrokerAccountMode = "disabled"
    can_submit: bool = False
    can_cancel: bool = False
    can_check_status: bool = False
    supports_paper: bool = False
    supports_live: bool = False
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.account_mode != "disabled":
            raise ValueError("broker account mode must be disabled")
        if any(
            (
                self.can_submit,
                self.can_cancel,
                self.can_check_status,
                self.supports_paper,
                self.supports_live,
            )
        ):
            raise ValueError("disabled broker capabilities cannot enable execution")


@dataclass(frozen=True)
class CancelIntent:
    client_order_id: str
    created_at: datetime
    reason: str = "operator_cancel_request"
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required(self.client_order_id, "client_order_id")
        _required(self.reason, "reason")
        object.__setattr__(self, "created_at", require_utc(self.created_at, "created_at"))


@dataclass(frozen=True)
class OrderStatusQuery:
    client_order_id: str
    created_at: datetime
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required(self.client_order_id, "client_order_id")
        object.__setattr__(self, "created_at", require_utc(self.created_at, "created_at"))


@dataclass(frozen=True)
class BrokerUnavailable:
    action: BrokerAction
    client_order_id: str
    requested_at: datetime
    reason: str = "broker_execution_disabled"
    status: BrokerUnavailableStatus = "unavailable"
    source: str = BROKER_DISABLED_SOURCE
    broker: Literal["kis"] = "kis"
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required(self.client_order_id, "client_order_id")
        _required(self.reason, "reason")
        if self.status != "unavailable":
            raise ValueError("disabled broker result status must be unavailable")
        if self.source != BROKER_DISABLED_SOURCE or self.source == LOCAL_PAPER_SOURCE:
            raise ValueError("disabled broker source must not be local paper")
        object.__setattr__(self, "requested_at", require_utc(self.requested_at, "requested_at"))


@dataclass(frozen=True)
class AccountSnapshot:
    currency: str
    settled_cash: Decimal
    total_equity: Decimal
    gross_exposure: Decimal
    captured_at: datetime
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", _required(self.currency, "currency").upper())
        object.__setattr__(self, "settled_cash", decimal_value(self.settled_cash, "settled_cash"))
        object.__setattr__(self, "total_equity", decimal_value(self.total_equity, "total_equity"))
        object.__setattr__(
            self, "gross_exposure", non_negative(self.gross_exposure, "gross_exposure")
        )
        object.__setattr__(self, "captured_at", require_utc(self.captured_at, "captured_at"))


@dataclass(frozen=True)
class BuyingPowerSnapshot:
    currency: str
    available_cash: Decimal
    max_order_notional: Decimal
    captured_at: datetime
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", _required(self.currency, "currency").upper())
        object.__setattr__(
            self, "available_cash", non_negative(self.available_cash, "available_cash")
        )
        object.__setattr__(
            self,
            "max_order_notional",
            non_negative(self.max_order_notional, "max_order_notional"),
        )
        object.__setattr__(self, "captured_at", require_utc(self.captured_at, "captured_at"))


@dataclass(frozen=True)
class BrokerOrderRequest:
    client_order_id: str
    symbol: str
    market: str
    side: Side
    quantity: Decimal
    limit_price: Decimal | None
    decision_id: str
    created_at: datetime
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required(self.client_order_id, "client_order_id")
        object.__setattr__(self, "symbol", _required(self.symbol, "symbol").upper())
        object.__setattr__(self, "market", _required(self.market, "market").upper())
        if self.side not in ("buy", "sell"):
            raise ValueError("side must be buy or sell")
        object.__setattr__(self, "quantity", positive(self.quantity, "quantity"))
        if self.limit_price is not None:
            object.__setattr__(self, "limit_price", positive(self.limit_price, "limit_price"))
        _required(self.decision_id, "decision_id")
        object.__setattr__(self, "created_at", require_utc(self.created_at, "created_at"))


@dataclass(frozen=True)
class BrokerOrderAck:
    client_order_id: str
    broker_order_id: str | None
    status: BrokerAckState
    acknowledged_at: datetime
    reason: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required(self.client_order_id, "client_order_id")
        _required(self.reason, "reason")
        if (self.status == "accepted") != bool(self.broker_order_id):
            raise ValueError("accepted acknowledgement requires exactly one broker_order_id")
        object.__setattr__(
            self,
            "acknowledged_at",
            require_utc(self.acknowledged_at, "acknowledged_at"),
        )

    @property
    def accepted(self) -> bool:
        return self.status == "accepted"


@dataclass(frozen=True)
class BrokerOrderStatus:
    client_order_id: str
    broker_order_id: str | None
    status: BrokerOrderState
    requested_quantity: Decimal
    filled_quantity: Decimal
    remaining_quantity: Decimal
    average_fill_price: Decimal | None
    updated_at: datetime
    reason: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required(self.client_order_id, "client_order_id")
        _required(self.reason, "reason")
        object.__setattr__(
            self, "requested_quantity", positive(self.requested_quantity, "requested_quantity")
        )
        object.__setattr__(
            self, "filled_quantity", non_negative(self.filled_quantity, "filled_quantity")
        )
        object.__setattr__(
            self, "remaining_quantity", non_negative(self.remaining_quantity, "remaining_quantity")
        )
        if self.filled_quantity + self.remaining_quantity != self.requested_quantity:
            raise ValueError("filled and remaining quantities must equal requested quantity")
        if (self.filled_quantity > 0) != (self.average_fill_price is not None):
            raise ValueError("average_fill_price must match whether fills exist")
        if self.average_fill_price is not None:
            object.__setattr__(
                self, "average_fill_price", positive(self.average_fill_price, "average_fill_price")
            )
        object.__setattr__(self, "updated_at", require_utc(self.updated_at, "updated_at"))


@dataclass(frozen=True)
class BrokerFill:
    fill_id: str
    client_order_id: str
    broker_order_id: str
    quantity: Decimal
    price: Decimal
    fee: Decimal
    filled_at: datetime
    source: str = BROKER_FAKE_SOURCE
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required(self.fill_id, "fill_id")
        _required(self.client_order_id, "client_order_id")
        _required(self.broker_order_id, "broker_order_id")
        _required(self.source, "source")
        object.__setattr__(self, "quantity", positive(self.quantity, "quantity"))
        object.__setattr__(self, "price", positive(self.price, "price"))
        object.__setattr__(self, "fee", non_negative(self.fee, "fee"))
        object.__setattr__(self, "filled_at", require_utc(self.filled_at, "filled_at"))


@dataclass(frozen=True)
class CancelResult:
    client_order_id: str
    broker_order_id: str | None
    status: CancelState
    cancelled_quantity: Decimal
    cancelled_at: datetime
    reason: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required(self.client_order_id, "client_order_id")
        _required(self.reason, "reason")
        object.__setattr__(
            self, "cancelled_quantity", non_negative(self.cancelled_quantity, "cancelled_quantity")
        )
        object.__setattr__(self, "cancelled_at", require_utc(self.cancelled_at, "cancelled_at"))


@dataclass(frozen=True)
class OpenOrderSnapshot:
    orders: tuple[BrokerOrderStatus, ...]
    captured_at: datetime
    complete: bool = True
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "orders", tuple(self.orders))
        object.__setattr__(self, "captured_at", require_utc(self.captured_at, "captured_at"))


@dataclass(frozen=True)
class ReconciliationResult:
    reconciled_at: datetime
    safe_to_submit: bool
    duplicates: tuple[str, ...] = ()
    mismatches: tuple[str, ...] = ()
    stale_snapshots: tuple[str, ...] = ()
    outcome_unknown_ids: tuple[str, ...] = ()
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "reconciled_at", require_utc(self.reconciled_at, "reconciled_at"))


class InMemoryBrokerTransport:
    """Deterministic lifecycle fake with optional explicit local state persistence."""

    def __init__(self, *, state_path: Path | None = None) -> None:
        self._state_path = state_path
        self._durable_intents: set[str] = set()
        self._intents: dict[str, BrokerOrderRequest] = {}
        self._acks: dict[str, BrokerOrderAck] = {}
        self._statuses: dict[str, BrokerOrderStatus] = {}
        self._fills: dict[str, BrokerFill] = {}

    @property
    def fills(self) -> tuple[BrokerFill, ...]:
        return tuple(self._fills[key] for key in sorted(self._fills))

    def is_intent_durable(self, request: BrokerOrderRequest) -> bool:
        return (
            self._intents.get(request.client_order_id) == request
            and request.client_order_id in self._durable_intents
        )

    def record_intent(self, request: BrokerOrderRequest) -> BrokerOrderRequest:
        existing = self._intents.get(request.client_order_id)
        if existing is not None:
            if existing != request:
                raise ValueError("client_order_id already records a different intent")
            return existing
        self._intents[request.client_order_id] = request
        self._statuses[request.client_order_id] = _status(request, "recorded")
        try:
            self._persist_state()
        except Exception:
            self._intents.pop(request.client_order_id)
            self._statuses.pop(request.client_order_id)
            raise
        if self._state_path is not None:
            self._durable_intents.add(request.client_order_id)
        return request

    def submit(
        self,
        request: BrokerOrderRequest,
        *,
        submitted_at: datetime | None = None,
    ) -> BrokerOrderAck:
        submitted_at = require_utc(submitted_at or request.created_at, "submitted_at")
        recorded = self._intents.get(request.client_order_id)
        if recorded != request:
            return BrokerOrderAck(
                request.client_order_id,
                None,
                "rejected",
                submitted_at,
                "intent_not_recorded" if recorded is None else "recorded_intent_mismatch",
            )
        current = self._statuses[request.client_order_id]
        if current.status == "outcome_unknown":
            return BrokerOrderAck(
                request.client_order_id,
                None,
                "rejected",
                submitted_at,
                "outcome_unknown_requires_reconciliation",
            )
        if request.client_order_id not in self._durable_intents:
            return BrokerOrderAck(
                request.client_order_id,
                None,
                "rejected",
                submitted_at,
                "intent_not_durable",
            )
        if request.client_order_id in self._acks:
            return self._acks[request.client_order_id]
        _not_before(submitted_at, request.created_at, "submitted_at")
        broker_order_id = f"MEM-{len(self._acks) + 1:08d}"
        ack = BrokerOrderAck(
            request.client_order_id,
            broker_order_id,
            "accepted",
            submitted_at,
            "accepted_by_in_memory_transport",
        )
        self._acks[request.client_order_id] = ack
        self._statuses[request.client_order_id] = _status(
            request,
            "submitted",
            broker_order_id=broker_order_id,
            updated_at=submitted_at,
        )
        try:
            self._persist_state()
        except Exception:
            self._acks.pop(request.client_order_id)
            self._statuses[request.client_order_id] = current
            raise
        return ack

    def order_status(self, client_order_id: str) -> BrokerOrderStatus:
        if client_order_id not in self._statuses:
            raise KeyError(f"unknown client_order_id: {client_order_id}")
        return self._statuses[client_order_id]

    def simulate_next_fill(
        self,
        client_order_id: str,
        *,
        price: Decimal,
        filled_at: datetime,
        fee: Decimal = Decimal("0"),
    ) -> BrokerFill:
        current = self.order_status(client_order_id)
        if current.status not in {"submitted", "partially_filled"}:
            raise ValueError("order is not open for filling")
        filled_at = require_utc(filled_at, "filled_at")
        _not_before(filled_at, current.updated_at, "filled_at")
        quantity = current.remaining_quantity
        if current.status == "submitted":
            quantity /= Decimal("2")
        if current.broker_order_id is None:
            raise RuntimeError("open order is missing broker_order_id")
        fill = BrokerFill(
            f"MEM-FILL-{len(self._fills) + 1:08d}",
            client_order_id,
            current.broker_order_id,
            quantity,
            price,
            fee,
            filled_at,
        )
        self._fills[fill.fill_id] = fill
        total_quantity = current.filled_quantity + quantity
        total_notional = (
            current.average_fill_price or Decimal("0")
        ) * current.filled_quantity + fill.price * quantity
        remaining = current.requested_quantity - total_quantity
        self._statuses[client_order_id] = replace(
            current,
            status="filled" if remaining == 0 else "partially_filled",
            filled_quantity=total_quantity,
            remaining_quantity=remaining,
            average_fill_price=total_notional / total_quantity,
            updated_at=filled_at,
            reason="fill_complete" if remaining == 0 else "partial_fill_recorded",
        )
        try:
            self._persist_state()
        except Exception:
            self._fills.pop(fill.fill_id)
            self._statuses[client_order_id] = current
            raise
        return fill

    def cancel(self, client_order_id: str, *, cancelled_at: datetime) -> CancelResult:
        cancelled_at = require_utc(cancelled_at, "cancelled_at")
        current = self._statuses.get(client_order_id)
        if current is None:
            return CancelResult(
                client_order_id, None, "not_found", Decimal("0"), cancelled_at, "order_not_found"
            )
        _not_before(cancelled_at, current.updated_at, "cancelled_at")
        if current.status == "outcome_unknown":
            return CancelResult(
                client_order_id,
                current.broker_order_id,
                "outcome_unknown",
                Decimal("0"),
                cancelled_at,
                "reconciliation_required",
            )
        if current.status not in {"submitted", "partially_filled"}:
            return CancelResult(
                client_order_id,
                current.broker_order_id,
                "not_open",
                Decimal("0"),
                cancelled_at,
                f"order_is_{current.status}",
            )
        self._statuses[client_order_id] = replace(
            current,
            status="cancelled",
            updated_at=cancelled_at,
            reason="open_quantity_cancelled",
        )
        try:
            self._persist_state()
        except Exception:
            self._statuses[client_order_id] = current
            raise
        return CancelResult(
            client_order_id,
            current.broker_order_id,
            "cancelled",
            current.remaining_quantity,
            cancelled_at,
            "open_quantity_cancelled",
        )

    def mark_outcome_unknown(
        self,
        client_order_id: str,
        *,
        observed_at: datetime,
    ) -> BrokerOrderStatus:
        current = self.order_status(client_order_id)
        if current.status in {"filled", "cancelled"}:
            raise ValueError("terminal order cannot become outcome_unknown")
        observed_at = require_utc(observed_at, "observed_at")
        _not_before(observed_at, current.updated_at, "observed_at")
        unknown = replace(
            current,
            status="outcome_unknown",
            updated_at=observed_at,
            reason="transport_outcome_unknown",
        )
        self._statuses[client_order_id] = unknown
        try:
            self._persist_state()
        except Exception:
            self._statuses[client_order_id] = current
            raise
        return unknown

    def resolve_outcome_unknown(
        self,
        authoritative_status: BrokerOrderStatus,
        *,
        fills: Sequence[BrokerFill] = (),
    ) -> BrokerOrderStatus:
        current = self.order_status(authoritative_status.client_order_id)
        if current.status != "outcome_unknown":
            raise ValueError("order is not outcome_unknown")
        if authoritative_status.status not in {
            "submitted",
            "partially_filled",
            "filled",
            "cancelled",
        }:
            raise ValueError("authoritative status must resolve the unknown outcome")
        if (
            not current.broker_order_id
            or authoritative_status.broker_order_id != current.broker_order_id
            or authoritative_status.requested_quantity != current.requested_quantity
        ):
            raise ValueError("authoritative status must preserve stable ids and requested quantity")
        _not_before(authoritative_status.updated_at, current.updated_at, "updated_at")
        newly_filled = authoritative_status.filled_quantity - current.filled_quantity
        if newly_filled < 0 or authoritative_status.remaining_quantity > current.remaining_quantity:
            raise ValueError("authoritative fill quantities cannot regress")

        evidence = tuple(fills)
        if newly_filled == 0:
            if evidence:
                raise ValueError("unchanged status cannot include new fill evidence")
            if (
                authoritative_status.remaining_quantity != current.remaining_quantity
                or authoritative_status.average_fill_price != current.average_fill_price
            ):
                raise ValueError("unchanged status must preserve fill quantities and average")
        else:
            expected_status = (
                "filled" if authoritative_status.remaining_quantity == 0 else "partially_filled"
            )
            if authoritative_status.status != expected_status:
                raise ValueError("fill progress requires a consistent partial or filled status")
            evidence_quantity = Decimal("0")
            evidence_notional = Decimal("0")
            seen_fill_ids: set[str] = set()
            for fill in sorted(evidence, key=lambda item: (item.filled_at, item.fill_id)):
                if fill.fill_id in seen_fill_ids:
                    raise ValueError("authoritative fill ids must be unique")
                if fill.fill_id in self._fills:
                    raise ValueError("authoritative fill id conflicts with persisted state")
                seen_fill_ids.add(fill.fill_id)
                if (
                    fill.client_order_id != current.client_order_id
                    or fill.broker_order_id != current.broker_order_id
                    or fill.source != BROKER_FAKE_SOURCE
                ):
                    raise ValueError("authoritative fills must preserve stable ids and source")
                _not_before(fill.filled_at, current.updated_at, "filled_at")
                if fill.filled_at > authoritative_status.updated_at:
                    raise ValueError("authoritative fill cannot follow its status timestamp")
                evidence_quantity += fill.quantity
                evidence_notional += fill.quantity * fill.price
            if evidence_quantity != newly_filled:
                raise ValueError("fill evidence quantity must equal newly observed quantity")
            prior_notional = (current.average_fill_price or Decimal("0")) * current.filled_quantity
            expected_average = (
                prior_notional + evidence_notional
            ) / authoritative_status.filled_quantity
            if authoritative_status.average_fill_price != expected_average:
                raise ValueError("fill evidence weighted price must equal authoritative average")

        self._statuses[current.client_order_id] = authoritative_status
        for fill in evidence:
            self._fills[fill.fill_id] = fill
        try:
            self._persist_state()
        except Exception:
            self._statuses[current.client_order_id] = current
            for fill in evidence:
                self._fills.pop(fill.fill_id, None)
            raise
        return authoritative_status

    def open_order_snapshot(self, *, captured_at: datetime) -> OpenOrderSnapshot:
        orders = tuple(
            status
            for _, status in sorted(self._statuses.items())
            if status.status in {"submitted", "partially_filled", "outcome_unknown"}
        )
        return OpenOrderSnapshot(orders, captured_at)

    def reconcile(
        self,
        *,
        account: AccountSnapshot,
        buying_power: BuyingPowerSnapshot,
        open_orders: OpenOrderSnapshot,
        fills: Sequence[BrokerFill],
        reconciled_at: datetime,
        max_age: timedelta = timedelta(minutes=5),
    ) -> ReconciliationResult:
        reconciled_at = require_utc(reconciled_at, "reconciled_at")
        if max_age <= timedelta(0):
            raise ValueError("max_age must be positive")
        stale = tuple(
            name
            for name, timestamp in (
                ("account", account.captured_at),
                ("buying_power", buying_power.captured_at),
                ("open_orders", open_orders.captured_at),
            )
            if timestamp > reconciled_at or reconciled_at - timestamp > max_age
        )
        duplicates = tuple(
            [
                f"client:{value}"
                for value in _duplicates(o.client_order_id for o in open_orders.orders)
            ]
            + [
                f"broker:{value}"
                for value in _duplicates(
                    o.broker_order_id for o in open_orders.orders if o.broker_order_id
                )
            ]
            + [f"fill:{value}" for value in _duplicates(fill.fill_id for fill in fills)]
        )
        mismatches: list[str] = []
        if account.currency != buying_power.currency:
            mismatches.append("account_currency")
        if not open_orders.complete:
            mismatches.append("open_orders_incomplete")
        local_open = {
            key: value
            for key, value in self._statuses.items()
            if value.status in {"submitted", "partially_filled", "outcome_unknown"}
        }
        external_open = {value.client_order_id: value for value in open_orders.orders}
        for key in local_open.keys() | external_open.keys():
            if _status_identity(local_open.get(key)) != _status_identity(external_open.get(key)):
                mismatches.append(f"open_order:{key}")
        external_fills = {fill.fill_id: fill for fill in fills}
        for key in self._fills.keys() | external_fills.keys():
            if self._fills.get(key) != external_fills.get(key):
                mismatches.append(f"fill:{key}")
        unknown = tuple(
            sorted(
                key for key, value in self._statuses.items() if value.status == "outcome_unknown"
            )
        )
        mismatches_tuple = tuple(sorted(set(mismatches)))
        return ReconciliationResult(
            reconciled_at,
            not any((duplicates, mismatches_tuple, stale, unknown)),
            duplicates,
            mismatches_tuple,
            stale,
            unknown,
        )

    def export_state(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "intents": [_contract_payload(self._intents[key]) for key in sorted(self._intents)],
            "acks": [_contract_payload(self._acks[key]) for key in sorted(self._acks)],
            "statuses": [_contract_payload(self._statuses[key]) for key in sorted(self._statuses)],
            "fills": [_contract_payload(self._fills[key]) for key in sorted(self._fills)],
        }

    @classmethod
    def from_state(
        cls,
        state: Mapping[str, Any],
        *,
        state_path: Path | None = None,
    ) -> InMemoryBrokerTransport:
        if state.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("unsupported in-memory broker state schema")
        if state_path is not None:
            if not state_path.is_file():
                raise ValueError("state_path must contain the persisted broker snapshot")
            persisted = json.loads(state_path.read_text(encoding="utf-8"))
            if persisted != state:
                raise ValueError("state does not match persisted broker snapshot")
        transport = cls(state_path=state_path)
        transport._intents = _restore(
            state,
            "intents",
            BrokerOrderRequest,
            "client_order_id",
            decimals=("quantity", "limit_price"),
            datetimes=("created_at",),
        )
        transport._acks = _restore(
            state,
            "acks",
            BrokerOrderAck,
            "client_order_id",
            datetimes=("acknowledged_at",),
        )
        transport._statuses = _restore(
            state,
            "statuses",
            BrokerOrderStatus,
            "client_order_id",
            decimals=(
                "requested_quantity",
                "filled_quantity",
                "remaining_quantity",
                "average_fill_price",
            ),
            datetimes=("updated_at",),
        )
        transport._fills = _restore(
            state,
            "fills",
            BrokerFill,
            "fill_id",
            decimals=("quantity", "price", "fee"),
            datetimes=("filled_at",),
        )
        if transport._intents.keys() != transport._statuses.keys():
            raise ValueError("restart state requires one status per intent")
        if not transport._acks.keys() <= transport._intents.keys():
            raise ValueError("restart state contains acknowledgement without intent")
        if any(
            fill.client_order_id not in transport._intents for fill in transport._fills.values()
        ):
            raise ValueError("restart state contains fill without intent")
        if state_path is not None:
            transport._durable_intents = set(transport._intents)
        return transport

    def _persist_state(self) -> None:
        if self._state_path is None:
            return
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self._state_path.with_name(f".{self._state_path.name}.tmp")
        try:
            with temporary_path.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(self.export_state(), handle, sort_keys=True, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self._state_path)
        finally:
            temporary_path.unlink(missing_ok=True)


class BrokerAdapter(Protocol):
    @property
    def capabilities(self) -> BrokerCapabilities: ...

    def submit_order(self, order: OrderIntent) -> BrokerUnavailable: ...

    def cancel_order(self, intent: CancelIntent) -> BrokerUnavailable: ...

    def order_status(self, query: OrderStatusQuery) -> BrokerUnavailable: ...


class DisabledKISAdapter:
    """Disabled KIS boundary that performs no network, credential, or event I/O."""

    def __init__(self, *, capabilities: BrokerCapabilities | None = None) -> None:
        self._capabilities = capabilities or BrokerCapabilities()

    @property
    def capabilities(self) -> BrokerCapabilities:
        return self._capabilities

    def submit_order(self, order: OrderIntent) -> BrokerUnavailable:
        return _unavailable("submit", order.client_order_id, order.created_at)

    def cancel_order(self, intent: CancelIntent) -> BrokerUnavailable:
        return _unavailable("cancel", intent.client_order_id, intent.created_at)

    def order_status(self, query: OrderStatusQuery) -> BrokerUnavailable:
        return _unavailable("status", query.client_order_id, query.created_at)


def create_kis_broker_adapter(*, enabled: bool = False) -> BrokerAdapter:
    if enabled or BROKER_EXECUTION_ENABLED:
        raise NotImplementedError("KIS execution is not enabled by this goal")
    return DisabledKISAdapter()


def _unavailable(
    action: BrokerAction,
    client_order_id: str,
    requested_at: datetime,
) -> BrokerUnavailable:
    return BrokerUnavailable(action, client_order_id, requested_at)


def _required(value: str, field_name: str) -> str:
    if not value:
        raise ValueError(f"{field_name} is required")
    return value


def _not_before(value: datetime, earlier: datetime, field_name: str) -> None:
    if value < earlier:
        raise ValueError(f"{field_name} cannot precede current state")


def _status(
    request: BrokerOrderRequest,
    state: BrokerOrderState,
    *,
    broker_order_id: str | None = None,
    updated_at: datetime | None = None,
) -> BrokerOrderStatus:
    return BrokerOrderStatus(
        request.client_order_id,
        broker_order_id,
        state,
        request.quantity,
        Decimal("0"),
        request.quantity,
        None,
        updated_at or request.created_at,
        "intent_recorded_before_submit" if state == "recorded" else "submitted",
    )


def _status_identity(value: BrokerOrderStatus | None) -> tuple[Any, ...] | None:
    if value is None:
        return None
    return (
        value.broker_order_id,
        value.status,
        value.requested_quantity,
        value.filled_quantity,
        value.remaining_quantity,
        value.average_fill_price,
    )


def _duplicates(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        duplicates.add(value) if value in seen else seen.add(value)
    return tuple(sorted(duplicates))


T = TypeVar("T")


def _contract_payload(contract: Any) -> dict[str, Any]:
    payload = asdict(contract)
    for field_name, value in payload.items():
        if isinstance(value, Decimal):
            payload[field_name] = str(value)
        elif isinstance(value, datetime):
            payload[field_name] = value.isoformat()
    return payload


def _restore(
    state: Mapping[str, Any],
    field_name: str,
    contract: type[T],
    key_field: str,
    *,
    decimals: tuple[str, ...] = (),
    datetimes: tuple[str, ...] = (),
) -> dict[str, T]:
    values = state.get(field_name)
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise ValueError(f"{field_name} must be a sequence")
    restored: dict[str, T] = {}
    for raw_value in values:
        if not isinstance(raw_value, Mapping):
            raise ValueError(f"{field_name} contains an invalid payload")
        payload = dict(raw_value)
        for decimal_field in decimals:
            if payload.get(decimal_field) is not None:
                payload[decimal_field] = Decimal(str(payload[decimal_field]))
        for datetime_field in datetimes:
            raw_datetime = payload.get(datetime_field)
            if not isinstance(raw_datetime, str):
                raise ValueError(f"{datetime_field} must be an ISO datetime")
            payload[datetime_field] = datetime.fromisoformat(raw_datetime)
        value = contract(**payload)
        key = getattr(value, key_field)
        if key in restored:
            raise ValueError(f"{field_name} contains a duplicate id")
        restored[key] = value
    return restored
