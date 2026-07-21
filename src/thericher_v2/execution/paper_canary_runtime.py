"""Credential-free runtime projection for one KIS virtual-paper canary."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from thericher_v2.contracts import SCHEMA_VERSION, require_utc

PAPER_CANARY_RUNTIME_KIND = "kis_paper_canary_runtime"
PAPER_CANARY_RUNTIME_TTL = timedelta(minutes=15)

PaperCanaryRuntimeStatus = Literal[
    "intent_recorded",
    "submission_started",
    "submitted",
    "rejected",
    "outcome_unknown",
    "cancelled",
    "unavailable",
]
PaperCanaryReconciliationStatus = Literal["not_run", "clean", "unresolved"]
PaperCanaryAccountStatus = Literal["unknown", "available", "unavailable"]

# These are implementation-owned codes, never broker response text.  The
# runtime projection is read by the dashboard, so keep the display surface
# deliberately closed over a small known vocabulary.
PAPER_CANARY_SAFE_RECONCILIATION_REASON_CODES = frozenset(
    {
        "access_token_invalid",
        "auth_rejected",
        "auth_response_invalid",
        "balance_pagination_incomplete",
        "balance_response_duplicate",
        "balance_response_incomplete",
        "ccnl_pagination_incomplete",
        "ccnl_rejected",
        "ccnl_response_incomplete",
        "open_orders_pagination_incomplete",
        "open_orders_response_duplicate",
        "open_orders_response_incomplete",
        "orderable_funds_response_incomplete",
        "paper_host_required",
        "query_not_allowlisted",
        "redirect_rejected",
        "request_not_allowlisted",
        "response_invalid",
        "transport_failure",
    }
)


class PaperCanaryRuntimeError(ValueError):
    """The sanitized runtime projection is malformed or unsafe to render."""


@dataclass(frozen=True)
class PaperCanaryRuntimeSnapshot:
    """A fact-minimized projection that contains no credentials or broker bodies."""

    run_id: str
    status: PaperCanaryRuntimeStatus
    reconciliation_status: PaperCanaryReconciliationStatus
    account_status: PaperCanaryAccountStatus
    position_count: int
    open_order_count: int
    stop_new_orders: bool
    cancel_open_orders_requested: bool
    observed_at: datetime
    expires_at: datetime
    order_reference: str | None = None
    reconciliation_reason_code: str | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required_id(self.run_id, "run_id")
        if self.status not in {
            "intent_recorded",
            "submission_started",
            "submitted",
            "rejected",
            "outcome_unknown",
            "cancelled",
            "unavailable",
        }:
            raise PaperCanaryRuntimeError("runtime_status_invalid")
        if self.reconciliation_status not in {"not_run", "clean", "unresolved"}:
            raise PaperCanaryRuntimeError("runtime_reconciliation_invalid")
        if self.account_status not in {"unknown", "available", "unavailable"}:
            raise PaperCanaryRuntimeError("runtime_account_status_invalid")
        if type(self.position_count) is not int or self.position_count < 0:
            raise PaperCanaryRuntimeError("runtime_position_count_invalid")
        if type(self.open_order_count) is not int or self.open_order_count < 0:
            raise PaperCanaryRuntimeError("runtime_open_order_count_invalid")
        if not isinstance(self.stop_new_orders, bool) or not isinstance(
            self.cancel_open_orders_requested, bool
        ):
            raise PaperCanaryRuntimeError("runtime_emergency_invalid")
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        object.__setattr__(self, "expires_at", require_utc(self.expires_at, "expires_at"))
        if self.expires_at <= self.observed_at:
            raise PaperCanaryRuntimeError("runtime_expiry_invalid")
        if self.order_reference is not None:
            _order_reference(self.order_reference)
        if (
            self.reconciliation_reason_code is not None
            and self.reconciliation_reason_code
            not in PAPER_CANARY_SAFE_RECONCILIATION_REASON_CODES
        ):
            raise PaperCanaryRuntimeError("runtime_reconciliation_reason_invalid")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": PAPER_CANARY_RUNTIME_KIND,
            "source": "kis_paper",
            "paper_only": True,
            "run_id": self.run_id,
            "status": self.status,
            "reconciliation_status": self.reconciliation_status,
            "account_status": self.account_status,
            "position_count": self.position_count,
            "open_order_count": self.open_order_count,
            "stop_new_orders": self.stop_new_orders,
            "cancel_open_orders_requested": self.cancel_open_orders_requested,
            "observed_at": self.observed_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "order_reference": self.order_reference,
            "reconciliation_reason_code": self.reconciliation_reason_code,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> PaperCanaryRuntimeSnapshot:
        if not isinstance(payload, Mapping):
            raise PaperCanaryRuntimeError("runtime_not_object")
        expected = {
            "schema_version",
            "kind",
            "source",
            "paper_only",
            "run_id",
            "status",
            "reconciliation_status",
            "account_status",
            "position_count",
            "open_order_count",
            "stop_new_orders",
            "cancel_open_orders_requested",
            "observed_at",
            "expires_at",
            "order_reference",
        }
        extended_expected = expected | {"reconciliation_reason_code"}
        if frozenset(payload) not in {frozenset(expected), frozenset(extended_expected)}:
            raise PaperCanaryRuntimeError("runtime_keys_invalid")
        if (
            payload["schema_version"] != SCHEMA_VERSION
            or payload["kind"] != PAPER_CANARY_RUNTIME_KIND
            or payload["source"] != "kis_paper"
            or payload["paper_only"] is not True
        ):
            raise PaperCanaryRuntimeError("runtime_envelope_invalid")
        return cls(
            run_id=_text(payload["run_id"], "run_id"),
            status=_text(payload["status"], "status"),  # type: ignore[arg-type]
            reconciliation_status=_text(  # type: ignore[arg-type]
                payload["reconciliation_status"], "reconciliation_status"
            ),
            account_status=_text(payload["account_status"], "account_status"),  # type: ignore[arg-type]
            position_count=_count(payload["position_count"], "position_count"),
            open_order_count=_count(payload["open_order_count"], "open_order_count"),
            stop_new_orders=_bool(payload["stop_new_orders"], "stop_new_orders"),
            cancel_open_orders_requested=_bool(
                payload["cancel_open_orders_requested"], "cancel_open_orders_requested"
            ),
            observed_at=_utc(payload["observed_at"], "observed_at"),
            expires_at=_utc(payload["expires_at"], "expires_at"),
            order_reference=(
                None
                if payload["order_reference"] is None
                else _text(payload["order_reference"], "order_reference")
            ),
            reconciliation_reason_code=(
                None
                if "reconciliation_reason_code" not in payload
                or payload["reconciliation_reason_code"] is None
                else _text(
                    payload["reconciliation_reason_code"],
                    "reconciliation_reason_code",
                )
            ),
            schema_version=SCHEMA_VERSION,
        )


@dataclass(frozen=True)
class PaperCanaryRuntimeRead:
    status: Literal["unknown", "available", "unavailable"]
    snapshot: PaperCanaryRuntimeSnapshot | None = None

    def __post_init__(self) -> None:
        if (self.status == "available") != (self.snapshot is not None):
            raise PaperCanaryRuntimeError("runtime_read_invalid")


def redact_paper_canary_order_reference(raw_order_id: str) -> str:
    """Derive a stable display reference without retaining the broker order id."""

    if not isinstance(raw_order_id, str) or not raw_order_id.strip():
        raise PaperCanaryRuntimeError("runtime_order_id_invalid")
    digest = hashlib.sha256(raw_order_id.encode("utf-8")).hexdigest()[:16]
    return f"canary-{digest}"


def write_paper_canary_runtime(snapshot: PaperCanaryRuntimeSnapshot, path: Path) -> str:
    """Atomically publish a sanitized projection and return its content digest."""

    payload = _runtime_bytes(snapshot)
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with staging.open("wb") as handle:
            handle.write(payload)
            handle.write(b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staging, path)
    finally:
        staging.unlink(missing_ok=True)
    return hashlib.sha256(payload).hexdigest()


def read_paper_canary_runtime(
    path: Path | None,
    *,
    now: datetime | None = None,
) -> PaperCanaryRuntimeRead:
    """Read only a current, fully validated credential-free runtime projection."""

    if path is None or not path.exists():
        return PaperCanaryRuntimeRead(status="unknown")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        snapshot = PaperCanaryRuntimeSnapshot.from_dict(payload)
        current = require_utc(now or datetime.now(UTC), "now")
        if current < snapshot.observed_at or current >= snapshot.expires_at:
            return PaperCanaryRuntimeRead(status="unavailable")
        return PaperCanaryRuntimeRead(status="available", snapshot=snapshot)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return PaperCanaryRuntimeRead(status="unavailable")


def _runtime_bytes(snapshot: PaperCanaryRuntimeSnapshot) -> bytes:
    return json.dumps(snapshot.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")


def _required_id(value: object, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 96
        or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
            for character in value
        )
    ):
        raise PaperCanaryRuntimeError(f"runtime_{field_name}_invalid")


def _order_reference(value: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != len("canary-") + 16
        or not value.startswith("canary-")
        or any(character not in "0123456789abcdef" for character in value.removeprefix("canary-"))
    ):
        raise PaperCanaryRuntimeError("runtime_order_reference_invalid")


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise PaperCanaryRuntimeError(f"runtime_{field_name}_invalid")
    return value


def _count(value: object, field_name: str) -> int:
    if type(value) is not int or value < 0:
        raise PaperCanaryRuntimeError(f"runtime_{field_name}_invalid")
    return value


def _bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise PaperCanaryRuntimeError(f"runtime_{field_name}_invalid")
    return value


def _utc(value: object, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise PaperCanaryRuntimeError(f"runtime_{field_name}_invalid")
    try:
        return require_utc(datetime.fromisoformat(value), field_name)
    except ValueError as error:
        raise PaperCanaryRuntimeError(f"runtime_{field_name}_invalid") from error
