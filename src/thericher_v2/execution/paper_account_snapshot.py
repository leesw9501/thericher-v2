"""Strict local runtime contract for a read-only paper-account console view."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from thericher_v2.contracts import require_utc

PAPER_ACCOUNT_SNAPSHOT_KIND = "paper_reconciliation_snapshot"
PAPER_ACCOUNT_SNAPSHOT_SOURCE = "kis_paper"
PAPER_ACCOUNT_SNAPSHOT_TTL = timedelta(minutes=5)
PAPER_ACCOUNT_SNAPSHOT_SCHEMA_VERSION = 3
PAPER_ACCOUNT_ORDERABLE_FOREIGN_FUNDS_SOURCE_FIELD = "ord_psbl_frcr_amt"


class PaperAccountSnapshotError(ValueError):
    """A snapshot is malformed, incomplete, or unsafe to render."""


@dataclass(frozen=True)
class PaperAccountOrderableForeignFunds:
    """Exact KIS orderable-foreign-funds field, not settled cash or account equity."""

    currency: str
    amount: Decimal
    source_field: Literal["ord_psbl_frcr_amt"] = PAPER_ACCOUNT_ORDERABLE_FOREIGN_FUNDS_SOURCE_FIELD

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", _currency(self.currency))
        object.__setattr__(self, "amount", _nonnegative_decimal(self.amount))
        if self.source_field != PAPER_ACCOUNT_ORDERABLE_FOREIGN_FUNDS_SOURCE_FIELD:
            raise PaperAccountSnapshotError("orderable_foreign_funds_source_invalid")


@dataclass(frozen=True)
class PaperAccountReferenceOrderability:
    """Orderability for one explicit reference instrument, not general buying power."""

    currency: str
    orderable_funds: Decimal
    reference_exchange: str
    reference_symbol: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", _currency(self.currency))
        object.__setattr__(self, "orderable_funds", _nonnegative_decimal(self.orderable_funds))
        object.__setattr__(self, "reference_exchange", _required_text(self.reference_exchange))
        object.__setattr__(self, "reference_symbol", _required_text(self.reference_symbol))


@dataclass(frozen=True)
class PaperAccountPosition:
    exchange: str
    symbol: str
    currency: str
    quantity: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "exchange", _required_text(self.exchange))
        object.__setattr__(self, "symbol", _required_text(self.symbol))
        object.__setattr__(self, "currency", _currency(self.currency))
        object.__setattr__(self, "quantity", _positive_decimal(self.quantity))


@dataclass(frozen=True)
class PaperAccountOpenOrder:
    exchange: str
    symbol: str
    currency: str
    side: Literal["buy", "sell"]
    requested_quantity: Decimal
    filled_quantity: Decimal
    remaining_quantity: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "exchange", _required_text(self.exchange))
        object.__setattr__(self, "symbol", _required_text(self.symbol))
        object.__setattr__(self, "currency", _currency(self.currency))
        if self.side not in {"buy", "sell"}:
            raise PaperAccountSnapshotError("open_order_side_invalid")
        object.__setattr__(self, "requested_quantity", _positive_decimal(self.requested_quantity))
        object.__setattr__(self, "filled_quantity", _nonnegative_decimal(self.filled_quantity))
        object.__setattr__(self, "remaining_quantity", _positive_decimal(self.remaining_quantity))
        if self.filled_quantity + self.remaining_quantity != self.requested_quantity:
            raise PaperAccountSnapshotError("open_order_quantities_invalid")


@dataclass(frozen=True)
class PaperAccountSnapshot:
    """A complete account view or an intentionally fact-free unavailable marker."""

    status: Literal["complete", "unavailable"]
    observed_at: datetime
    expires_at: datetime
    orderable_foreign_funds: PaperAccountOrderableForeignFunds | None = None
    reference_orderability: PaperAccountReferenceOrderability | None = None
    positions: tuple[PaperAccountPosition, ...] = ()
    open_orders: tuple[PaperAccountOpenOrder, ...] = ()
    reason_code: str | None = None
    schema_version: int = PAPER_ACCOUNT_SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        object.__setattr__(self, "expires_at", require_utc(self.expires_at, "expires_at"))
        object.__setattr__(self, "positions", tuple(self.positions))
        object.__setattr__(self, "open_orders", tuple(self.open_orders))
        age = self.expires_at - self.observed_at
        if age <= timedelta(0) or age > PAPER_ACCOUNT_SNAPSHOT_TTL:
            raise PaperAccountSnapshotError("snapshot_expiry_invalid")
        if self.status == "complete":
            if (
                self.orderable_foreign_funds is None
                or self.reference_orderability is None
                or self.reason_code is not None
            ):
                raise PaperAccountSnapshotError("complete_snapshot_facts_invalid")
            position_keys = {(item.exchange, item.symbol) for item in self.positions}
            if len(position_keys) != len(self.positions):
                raise PaperAccountSnapshotError("position_duplicate")
        elif self.status == "unavailable":
            if (
                self.orderable_foreign_funds is not None
                or self.reference_orderability is not None
                or self.positions
                or self.open_orders
            ):
                raise PaperAccountSnapshotError("unavailable_snapshot_has_facts")
            _reason_code(self.reason_code)
        else:
            raise PaperAccountSnapshotError("snapshot_status_invalid")

    @classmethod
    def unavailable(cls, *, observed_at: datetime, reason_code: str) -> PaperAccountSnapshot:
        observed_at = require_utc(observed_at, "observed_at")
        return cls(
            status="unavailable",
            observed_at=observed_at,
            expires_at=observed_at + PAPER_ACCOUNT_SNAPSHOT_TTL,
            reason_code=reason_code,
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "kind": PAPER_ACCOUNT_SNAPSHOT_KIND,
            "source": PAPER_ACCOUNT_SNAPSHOT_SOURCE,
            "read_only": True,
            "submission_capability": False,
            "status": self.status,
            "observed_at": self.observed_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }
        if self.status == "unavailable":
            payload["reason_code"] = self.reason_code
            return payload
        assert self.orderable_foreign_funds is not None
        assert self.reference_orderability is not None
        payload["facts"] = {
            "orderable_foreign_funds": {
                "currency": self.orderable_foreign_funds.currency,
                "amount": str(self.orderable_foreign_funds.amount),
                "source_field": self.orderable_foreign_funds.source_field,
            },
            "reference_orderability": {
                "currency": self.reference_orderability.currency,
                "orderable_funds": str(self.reference_orderability.orderable_funds),
                "reference_exchange": self.reference_orderability.reference_exchange,
                "reference_symbol": self.reference_orderability.reference_symbol,
            },
            "positions": [
                {
                    "exchange": item.exchange,
                    "symbol": item.symbol,
                    "currency": item.currency,
                    "quantity": str(item.quantity),
                }
                for item in self.positions
            ],
            "open_orders": [
                {
                    "exchange": item.exchange,
                    "symbol": item.symbol,
                    "currency": item.currency,
                    "side": item.side,
                    "requested_quantity": str(item.requested_quantity),
                    "filled_quantity": str(item.filled_quantity),
                    "remaining_quantity": str(item.remaining_quantity),
                }
                for item in self.open_orders
            ],
        }
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> PaperAccountSnapshot:
        if not isinstance(payload, Mapping):
            raise PaperAccountSnapshotError("snapshot_not_object")
        status = payload.get("status")
        if status == "unavailable":
            _require_exact_keys(
                payload,
                {
                    "schema_version",
                    "kind",
                    "source",
                    "read_only",
                    "submission_capability",
                    "status",
                    "observed_at",
                    "expires_at",
                    "reason_code",
                },
            )
            _validate_envelope(payload)
            return cls(
                status="unavailable",
                observed_at=_utc_datetime(payload["observed_at"], "observed_at"),
                expires_at=_utc_datetime(payload["expires_at"], "expires_at"),
                reason_code=_reason_code(payload["reason_code"]),
            )
        if status != "complete":
            raise PaperAccountSnapshotError("snapshot_status_invalid")
        _require_exact_keys(
            payload,
            {
                "schema_version",
                "kind",
                "source",
                "read_only",
                "submission_capability",
                "status",
                "observed_at",
                "expires_at",
                "facts",
            },
        )
        _validate_envelope(payload)
        facts = payload["facts"]
        if not isinstance(facts, Mapping):
            raise PaperAccountSnapshotError("snapshot_facts_invalid")
        _require_exact_keys(
            facts,
            {"orderable_foreign_funds", "reference_orderability", "positions", "open_orders"},
        )
        return cls(
            status="complete",
            observed_at=_utc_datetime(payload["observed_at"], "observed_at"),
            expires_at=_utc_datetime(payload["expires_at"], "expires_at"),
            orderable_foreign_funds=_orderable_foreign_funds_from_dict(
                facts["orderable_foreign_funds"]
            ),
            reference_orderability=_reference_orderability_from_dict(
                facts["reference_orderability"]
            ),
            positions=_positions_from_list(facts["positions"]),
            open_orders=_open_orders_from_list(facts["open_orders"]),
        )


@dataclass(frozen=True)
class PaperAccountSnapshotRead:
    status: Literal["unknown", "available", "unavailable"]
    snapshot: PaperAccountSnapshot | None = None

    def __post_init__(self) -> None:
        if self.status == "available" and (
            self.snapshot is None or self.snapshot.status != "complete"
        ):
            raise PaperAccountSnapshotError("available_snapshot_missing")
        if self.status != "available" and self.snapshot is not None:
            raise PaperAccountSnapshotError("nonavailable_snapshot_present")


def write_paper_account_snapshot(snapshot: PaperAccountSnapshot, path: Path) -> str:
    """Atomically publish a fully validated snapshot and return its SHA-256."""

    encoded = _snapshot_bytes(snapshot)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(encoded)
            handle.write(b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return hashlib.sha256(encoded).hexdigest()


def paper_account_snapshot_digest(snapshot: PaperAccountSnapshot) -> str:
    """Return the digest of the canonical runtime payload without rewriting it."""

    return hashlib.sha256(_snapshot_bytes(snapshot)).hexdigest()


def read_paper_account_snapshot(
    path: Path | None,
    *,
    now: datetime | None = None,
) -> PaperAccountSnapshotRead:
    """Return only a complete, current snapshot; all unsafe states are unavailable."""

    if path is None:
        return PaperAccountSnapshotRead(status="unknown")
    try:
        if not path.exists():
            return PaperAccountSnapshotRead(status="unknown")
        payload = json.loads(path.read_text(encoding="utf-8"))
        snapshot = PaperAccountSnapshot.from_dict(payload)
        current = require_utc(now or datetime.now(UTC), "now")
        if (
            snapshot.status != "complete"
            or current < snapshot.observed_at
            or current >= snapshot.expires_at
        ):
            return PaperAccountSnapshotRead(status="unavailable")
        return PaperAccountSnapshotRead(status="available", snapshot=snapshot)
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return PaperAccountSnapshotRead(status="unavailable")


def _orderable_foreign_funds_from_dict(value: object) -> PaperAccountOrderableForeignFunds:
    if not isinstance(value, Mapping):
        raise PaperAccountSnapshotError("orderable_foreign_funds_invalid")
    _require_exact_keys(value, {"currency", "amount", "source_field"})
    return PaperAccountOrderableForeignFunds(
        currency=_text(value["currency"], "orderable_foreign_funds_currency"),
        amount=_decimal(value["amount"], "orderable_foreign_funds_amount"),
        source_field=_text(value["source_field"], "orderable_foreign_funds_source"),
    )


def _reference_orderability_from_dict(value: object) -> PaperAccountReferenceOrderability:
    if not isinstance(value, Mapping):
        raise PaperAccountSnapshotError("reference_orderability_invalid")
    _require_exact_keys(
        value,
        {
            "currency",
            "orderable_funds",
            "reference_exchange",
            "reference_symbol",
        },
    )
    return PaperAccountReferenceOrderability(
        currency=_text(value["currency"], "reference_currency"),
        orderable_funds=_decimal(value["orderable_funds"], "orderable_funds"),
        reference_exchange=_text(value["reference_exchange"], "reference_exchange"),
        reference_symbol=_text(value["reference_symbol"], "reference_symbol"),
    )


def _positions_from_list(value: object) -> tuple[PaperAccountPosition, ...]:
    if not isinstance(value, list):
        raise PaperAccountSnapshotError("positions_invalid")
    positions: list[PaperAccountPosition] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise PaperAccountSnapshotError("position_invalid")
        _require_exact_keys(item, {"exchange", "symbol", "currency", "quantity"})
        positions.append(
            PaperAccountPosition(
                exchange=_text(item["exchange"], "position_exchange"),
                symbol=_text(item["symbol"], "position_symbol"),
                currency=_text(item["currency"], "position_currency"),
                quantity=_decimal(item["quantity"], "position_quantity"),
            )
        )
    return tuple(positions)


def _open_orders_from_list(value: object) -> tuple[PaperAccountOpenOrder, ...]:
    if not isinstance(value, list):
        raise PaperAccountSnapshotError("open_orders_invalid")
    orders: list[PaperAccountOpenOrder] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise PaperAccountSnapshotError("open_order_invalid")
        _require_exact_keys(
            item,
            {
                "exchange",
                "symbol",
                "currency",
                "side",
                "requested_quantity",
                "filled_quantity",
                "remaining_quantity",
            },
        )
        orders.append(
            PaperAccountOpenOrder(
                exchange=_text(item["exchange"], "open_order_exchange"),
                symbol=_text(item["symbol"], "open_order_symbol"),
                currency=_text(item["currency"], "open_order_currency"),
                side=_text(item["side"], "open_order_side").lower(),
                requested_quantity=_decimal(item["requested_quantity"], "requested_quantity"),
                filled_quantity=_decimal(item["filled_quantity"], "filled_quantity"),
                remaining_quantity=_decimal(item["remaining_quantity"], "remaining_quantity"),
            )
        )
    return tuple(orders)


def _validate_envelope(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != PAPER_ACCOUNT_SNAPSHOT_SCHEMA_VERSION:
        raise PaperAccountSnapshotError("snapshot_schema_invalid")
    if payload.get("kind") != PAPER_ACCOUNT_SNAPSHOT_KIND:
        raise PaperAccountSnapshotError("snapshot_kind_invalid")
    if payload.get("source") != PAPER_ACCOUNT_SNAPSHOT_SOURCE:
        raise PaperAccountSnapshotError("snapshot_source_invalid")
    if payload.get("read_only") is not True or payload.get("submission_capability") is not False:
        raise PaperAccountSnapshotError("snapshot_capability_invalid")


def _require_exact_keys(value: Mapping[str, Any], expected: set[str]) -> None:
    if set(value) != expected:
        raise PaperAccountSnapshotError("snapshot_keys_invalid")


def _utc_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise PaperAccountSnapshotError(f"{field_name}_invalid")
    try:
        return require_utc(datetime.fromisoformat(value.replace("Z", "+00:00")), field_name)
    except ValueError as error:
        raise PaperAccountSnapshotError(f"{field_name}_invalid") from error


def _decimal(value: object, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise PaperAccountSnapshotError(f"{field_name}_invalid") from error


def _nonnegative_decimal(value: Decimal) -> Decimal:
    if not value.is_finite() or value < 0:
        raise PaperAccountSnapshotError("decimal_invalid")
    return value


def _positive_decimal(value: Decimal) -> Decimal:
    value = _nonnegative_decimal(value)
    if value <= 0:
        raise PaperAccountSnapshotError("decimal_invalid")
    return value


def _required_text(value: str) -> str:
    result = value.strip().upper() if isinstance(value, str) else ""
    if not result:
        raise PaperAccountSnapshotError("text_invalid")
    return result


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise PaperAccountSnapshotError(f"{field_name}_invalid")
    return value


def _currency(value: str) -> str:
    result = _required_text(value)
    if len(result) != 3 or not result.isalpha():
        raise PaperAccountSnapshotError("currency_invalid")
    return result


def _reason_code(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 64:
        raise PaperAccountSnapshotError("reason_code_invalid")
    if any(character not in "abcdefghijklmnopqrstuvwxyz0123456789_" for character in value):
        raise PaperAccountSnapshotError("reason_code_invalid")
    return value


def _snapshot_bytes(snapshot: PaperAccountSnapshot) -> bytes:
    return json.dumps(snapshot.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
