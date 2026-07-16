"""Broker adapter boundary contracts with execution disabled by default."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from thericher_v2.contracts import SCHEMA_VERSION, OrderIntent, require_utc

from .local_paper import LOCAL_PAPER_SOURCE

BrokerAccountMode = Literal["disabled"]
BrokerAction = Literal["submit", "cancel", "status"]
BrokerUnavailableStatus = Literal["unavailable"]

BROKER_DISABLED_SOURCE = "broker_disabled"
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
        if not self.client_order_id:
            raise ValueError("client_order_id is required")
        if not self.reason:
            raise ValueError("reason is required")
        object.__setattr__(self, "created_at", require_utc(self.created_at, "created_at"))


@dataclass(frozen=True)
class OrderStatusQuery:
    client_order_id: str
    created_at: datetime
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.client_order_id:
            raise ValueError("client_order_id is required")
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
        if not self.client_order_id:
            raise ValueError("client_order_id is required")
        if not self.reason:
            raise ValueError("reason is required")
        if self.status != "unavailable":
            raise ValueError("disabled broker result status must be unavailable")
        if self.source != BROKER_DISABLED_SOURCE or self.source == LOCAL_PAPER_SOURCE:
            raise ValueError("disabled broker source must not be local paper")
        object.__setattr__(self, "requested_at", require_utc(self.requested_at, "requested_at"))


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
        return _unavailable(
            action="submit",
            client_order_id=order.client_order_id,
            requested_at=order.created_at,
        )

    def cancel_order(self, intent: CancelIntent) -> BrokerUnavailable:
        return _unavailable(
            action="cancel",
            client_order_id=intent.client_order_id,
            requested_at=intent.created_at,
        )

    def order_status(self, query: OrderStatusQuery) -> BrokerUnavailable:
        return _unavailable(
            action="status",
            client_order_id=query.client_order_id,
            requested_at=query.created_at,
        )


def create_kis_broker_adapter(*, enabled: bool = False) -> BrokerAdapter:
    if enabled or BROKER_EXECUTION_ENABLED:
        raise NotImplementedError("KIS execution is not enabled by this goal")
    return DisabledKISAdapter()


def _unavailable(
    *,
    action: BrokerAction,
    client_order_id: str,
    requested_at: datetime,
) -> BrokerUnavailable:
    return BrokerUnavailable(
        action=action,
        client_order_id=client_order_id,
        requested_at=requested_at,
    )
