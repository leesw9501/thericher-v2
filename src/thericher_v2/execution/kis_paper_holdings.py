"""One explicit, counts-only Paper account observation, independent of funds/quotes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from thericher_v2.contracts import require_utc

from .kis_market_data_rate_gate import (
    KisPaperMarketDataTokenStartGate,
    KisPaperTokenStartGateBusy,
)
from .kis_paper_stock_quote import KisPaperStockInstrument
from .kis_paper_stock_readonly import (
    KisPaperStockExitAccountSnapshot,
    KisPaperStockReadOnlyClient,
)
from .kis_readonly import (
    DEFAULT_KIS_PAPER_ARTIFACT_ROOT,
    KIS_PAPER_BALANCE_ENDPOINT,
    KIS_PAPER_OPEN_ORDERS_ENDPOINT,
    KIS_PAPER_TOKEN_PATH,
    KisHttpRequest,
    KisHttpResponse,
    KisHttpTransport,
    KisPaperReadOnlyError,
    UrllibKisHttpTransport,
    load_kis_paper_config_from_environment,
    safe_kis_paper_upstream_code,
    validate_kis_paper_readonly_request,
)

DEFAULT_TOKEN_CONTROL_ROOT = Path(
    "D:/market_data/us_equities/kis_paper_private/collection-control-v1"
)
_AGGREGATE_SECONDS = 120.0
_GET_PATHS = {KIS_PAPER_BALANCE_ENDPOINT.path, KIS_PAPER_OPEN_ORDERS_ENDPOINT.path}
_REFERENCE = KisPaperStockInstrument(
    "QQQ", "ref:" + hashlib.sha256(b"holdings-only-account-reference-v1").hexdigest()
)
_SAFE_REASONS = {
    "config_missing", "config_account_invalid", "config_product_invalid",
    "paper_host_required", "transport_failure", "request_not_allowlisted",
    "auth_rejected", "auth_response_invalid", "response_invalid",
    "balance_rejected", "open_orders_rejected", "balance_response_duplicate",
    "balance_response_incomplete", "open_orders_response_incomplete",
    "balance_pagination_incomplete", "open_orders_pagination_incomplete",
    "stock_exit_pagination_invalid", "stock_exit_snapshot_invalid", "stock_snapshot_stale",
    "stock_account_binding_mismatch", "holdings_deadline_exceeded", "holdings_wire_limit",
}
_PROVIDER_REASONS = {
    "paper_account_expired", "paper_account_user_mismatch", "paper_numeric_unclassified"
}


@dataclass(frozen=True)
class KisPaperHoldingsOutcome:
    status: str
    reason_code: str | None
    observed_at: datetime
    completed_at: datetime
    invocation_id: str
    position_count: int | None = None
    open_order_count: int | None = None
    post_attempts: int = 0
    get_attempts: int = 0
    next_due: datetime | None = None
    evidence_path: Path | None = None
    provider_reason: str | None = None

    def __post_init__(self) -> None:
        if type(self.status) is not str or self.status not in {
            "complete", "unavailable", "deferred"
        }:
            raise ValueError("holdings_outcome_invalid")
        for value in (self.observed_at, self.completed_at):
            if type(value) is not datetime:
                raise ValueError("holdings_outcome_invalid")
            require_utc(value)
        if self.completed_at < self.observed_at or type(self.invocation_id) is not str:
            raise ValueError("holdings_outcome_invalid")
        identifier = UUID(self.invocation_id)
        if identifier.version != 4 or str(identifier) != self.invocation_id:
            raise ValueError("holdings_outcome_invalid")
        if self.status == "complete":
            if self.reason_code is not None or any(
                type(value) is not int or value < 0
                for value in (self.position_count, self.open_order_count)
            ):
                raise ValueError("holdings_outcome_invalid")
        elif self.position_count is not None or self.open_order_count is not None:
            raise ValueError("holdings_outcome_invalid")
        allowed = _SAFE_REASONS | {"account_snapshot_unavailable", "token_request_deferred"}
        if self.status != "complete" and (
            type(self.reason_code) is not str or self.reason_code not in allowed
        ):
            raise ValueError("holdings_outcome_invalid")
        for value, limit in ((self.post_attempts, 1), (self.get_attempts, 40)):
            if type(value) is not int or not 0 <= value <= limit:
                raise ValueError("holdings_outcome_invalid")
        if self.next_due is not None:
            if self.status != "deferred" or type(self.next_due) is not datetime:
                raise ValueError("holdings_outcome_invalid")
            require_utc(self.next_due)
        if self.provider_reason is not None and (
            type(self.provider_reason) is not str or self.provider_reason not in _PROVIDER_REASONS
        ):
            raise ValueError("holdings_outcome_invalid")

    def evidence_payload(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "source": "kis_paper",
            "scope": "configured_account_holdings_only",
            "status": self.status,
            "reason_code": self.reason_code,
            "provider_reason": self.provider_reason,
            "observed_at": self.observed_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "invocation_id": self.invocation_id,
            "position_count": self.position_count,
            "open_order_count": self.open_order_count,
            "post_attempts": self.post_attempts,
            "get_attempts": self.get_attempts,
            "next_due": None if self.next_due is None else self.next_due.isoformat(),
            "read_only": True,
            "paper_only": True,
            "submit_capability": False,
            "sequential_not_atomic": True,
            "account_risk_snapshot_complete": False,
            "owned_inventory_or_fill_proven": False,
        }


class _TokenDeferred(Exception):
    """Escape native parser normalization without exposing any broker payload."""

    def __init__(self, next_due: datetime | None) -> None:
        self.next_due = next_due


class _HoldingsTransport:
    def __init__(self, *, transport, gate, monotonic, deadline, clock) -> None:
        self._delegate = transport
        self._gate = gate
        self._monotonic = monotonic
        self._deadline = deadline
        self._clock = clock
        self.post_attempts = 0
        self.get_attempts = 0
        self.provider_reason = None
        self._real = (
            UrllibKisHttpTransport(before_request=self._before_wire)
            if transport is None else None
        )

    def _validate(self, request: KisHttpRequest) -> None:
        validate_kis_paper_readonly_request(request)
        path = urlsplit(request.url).path
        if not (
            request.method == "POST" and path == KIS_PAPER_TOKEN_PATH
            or request.method == "GET" and path in _GET_PATHS
        ):
            raise KisPaperReadOnlyError("request_not_allowlisted")

    def _before_wire(self, request: KisHttpRequest) -> None:
        self._validate(request)
        remaining = self._deadline - self._monotonic()
        if remaining <= 0:
            raise KisPaperReadOnlyError("holdings_deadline_exceeded")
        if request.method == "POST":
            if self.post_attempts >= 1:
                raise KisPaperReadOnlyError("holdings_wire_limit")
            if self._gate.claim_token_request_start() is not True:
                due = None
                try:
                    value = self._gate.snapshot().next_token_request_not_before_utc
                    if value is not None and require_utc(value) > require_utc(self._clock()):
                        due = value
                except (KisPaperTokenStartGateBusy, ValueError, OSError, AttributeError):
                    pass
                raise _TokenDeferred(due)
        else:
            if self.get_attempts >= 40:
                raise KisPaperReadOnlyError("holdings_wire_limit")
        remaining = self._deadline - self._monotonic()
        if remaining <= 0:
            raise KisPaperReadOnlyError("holdings_deadline_exceeded")
        if request.method == "POST":
            self.post_attempts += 1
        else:
            self.get_attempts += 1
        if self._real is not None:
            # The native hook runs after pacing and immediately before opener.open.
            self._real._timeout_seconds = min(15.0, remaining)

    def request(self, request: KisHttpRequest) -> KisHttpResponse:
        self._validate(request)
        if self._real is not None:
            response = self._real.request(request)
        else:
            self._before_wire(request)
            response = self._delegate.request(request)
        # The native account parser strips diagnostics when normalizing errors.
        # Retain closed categories only, never its raw body, code or free text.
        try:
            payload = response.payload(reject_duplicate_keys=True)
            if response.status_code != 200 or payload.get("rt_cd") != "0":
                category = safe_kis_paper_upstream_code(payload.get("msg_cd"))
                if type(category) is str and category in _PROVIDER_REASONS:
                    self.provider_reason = category
        except (KisPaperReadOnlyError, ValueError, TypeError, AttributeError):
            pass
        return response


def _external_path(path: Path, repository_root: Path) -> Path:
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError("external_path_invalid")
    resolved = path.resolve()
    if (
        resolved.is_relative_to(repository_root.resolve())
        or resolved.exists() and not resolved.is_dir()
    ):
        raise ValueError("external_path_inside_repository")
    return resolved


def run_kis_paper_holdings(
    *,
    environment: Mapping[str, str],
    token_control_root: Path,
    artifact_root: Path,
    repository_root: Path,
    transport: KisHttpTransport | None = None,
    token_gate: KisPaperMarketDataTokenStartGate | None = None,
    access_token: str | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    monotonic: Callable[[], float] = time.monotonic,
    invocation_id: str | None = None,
) -> KisPaperHoldingsOutcome:
    """Observe once; never read execution state, reconcile, or reuse a failed result.

    Actual dispatch also needs an owned bounded launcher. A missing/killed result
    is unknown, not a zero-attempt or zero-position observation.
    """
    root = _external_path(artifact_root, repository_root)
    control = _external_path(token_control_root, repository_root)
    invocation = str(uuid4()) if invocation_id is None else invocation_id
    identifier = UUID(invocation)
    if identifier.version != 4 or str(identifier) != invocation:
        raise ValueError("invocation_invalid")
    directory = root / "execution" / "kis-paper-holdings-readonly"
    _external_path(directory, repository_root)
    destination = directory / f"{invocation}.json"
    if destination.exists():
        raise ValueError("evidence_already_exists")
    started_at, started = require_utc(clock()), monotonic()
    gate = token_gate if token_gate is not None else KisPaperMarketDataTokenStartGate(
        control_root=control, clock=clock
    )
    wire = _HoldingsTransport(
        transport=transport, gate=gate, monotonic=monotonic,
        deadline=started + _AGGREGATE_SECONDS, clock=clock,
    )
    status, reason, positions, orders, next_due = "unavailable", None, None, None, None
    provider_reason = None
    observed_at = started_at
    try:
        config = load_kis_paper_config_from_environment(environment)
        client = KisPaperStockReadOnlyClient(
            config=config, transport=wire, access_token=access_token
        )
        account_ref = hashlib.sha256(json.dumps(
            [config.base_url, config.account_number, config.account_product_code],
            sort_keys=True,
        ).encode("utf-8")).hexdigest()
        # Reference is only required by the native API; no symbol quote/order is sent.
        snapshot = client.stock_exit_account_snapshot(
            instrument=_REFERENCE, expected_account_ref=account_ref, clock=clock
        )
        if type(snapshot) is not KisPaperStockExitAccountSnapshot or replace(snapshot) != snapshot:
            raise KisPaperReadOnlyError("stock_exit_snapshot_invalid")
        if monotonic() - started > _AGGREGATE_SECONDS:
            raise KisPaperReadOnlyError("holdings_deadline_exceeded")
        observed_at = snapshot.captured_at
        positions = sum(row.quantity > 0 for row in snapshot.positions)
        orders = len(snapshot.open_orders.orders)
        status = "complete"
    except _TokenDeferred as error:
        positions, orders = None, None
        status, reason, next_due = "deferred", "token_request_deferred", error.next_due
    except KisPaperReadOnlyError as error:
        positions, orders = None, None
        reason = (
            error.code if type(error.code) is str and error.code in _SAFE_REASONS
            else "account_snapshot_unavailable"
        )
        category = error.diagnostic.get("upstream_code")
        if type(category) is str and category in _PROVIDER_REASONS:
            provider_reason = category
        elif wire.provider_reason is not None:
            provider_reason = wire.provider_reason
    except Exception:
        positions, orders = None, None
        reason = "account_snapshot_unavailable"
    outcome = KisPaperHoldingsOutcome(
        status=status, reason_code=reason, observed_at=observed_at,
        completed_at=require_utc(clock()), invocation_id=invocation,
        position_count=positions, open_order_count=orders,
        post_attempts=wire.post_attempts, get_attempts=wire.get_attempts, next_due=next_due,
        provider_reason=provider_reason,
    )
    directory.mkdir(parents=True, exist_ok=True)
    _external_path(directory, repository_root)
    temporary = directory / f".{invocation}.tmp"
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(outcome.evidence_payload(), stream, sort_keys=True, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        if destination.exists():
            raise ValueError("evidence_already_exists")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return replace(outcome, evidence_path=destination)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Observe Paper holdings without funds or quotes")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_KIS_PAPER_ARTIFACT_ROOT)
    parser.add_argument("--token-control-root", type=Path, default=DEFAULT_TOKEN_CONTROL_ROOT)
    parser.add_argument("--invocation-id")
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status": "inert", "read_only": True, "submit_capability": False}))
        return 0
    try:
        outcome = run_kis_paper_holdings(
            environment=os.environ, token_control_root=args.token_control_root,
            artifact_root=args.artifact_root, repository_root=args.repository_root,
            invocation_id=args.invocation_id,
        )
        print(json.dumps({
            **outcome.evidence_payload(), "evidence_path": str(outcome.evidence_path),
        }, sort_keys=True))
        return 0 if outcome.status == "complete" else 2
    except (OSError, ValueError):
        print(json.dumps({"status": "unavailable", "reason_code": "evidence_unavailable"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
