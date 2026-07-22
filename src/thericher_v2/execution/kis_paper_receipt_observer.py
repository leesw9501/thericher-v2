"""Read-only observation for one receipt-linked KIS Paper SPY intent.

The observer deliberately imports only the virtual-paper read-only client. It
cannot construct an order, change an order, or infer a fill or PnL from an
acknowledgement, a daily bar, or an aggregate account position.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, require_utc

from .kis_readonly import (
    DEFAULT_KIS_PAPER_ARTIFACT_ROOT,
    KisHttpTransport,
    KisPaperReadOnlyClient,
    KisPaperReadOnlyError,
    KisPaperReadOnlySnapshot,
    UrllibKisHttpTransport,
    load_kis_paper_config_from_environment,
)

DEFAULT_KIS_PAPER_RECEIPT_OBSERVATION_STATE_ROOT = Path("runtime/private/kis_paper_canary")
KIS_PAPER_RECEIPT_OBSERVATION_MAX_ACCOUNT_FACT_AGE = timedelta(seconds=120)
KIS_PAPER_RECEIPT_OBSERVATION_KIND = "kis_paper_receipt_observation"

_RECEIPT_RUN_ID = re.compile(r"receipt-([0-9a-f]{64})", re.ASCII)
_SHA256_REFERENCE = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)
_RAW_ORDER_ID = re.compile(r"[A-Za-z0-9_-]{1,64}", re.ASCII)
_STATE_PHASES = frozenset(
    {
        "intent_recorded",
        "submission_started",
        "submitted",
        "rejected",
        "outcome_unknown",
        "cancel_started",
        "cancelled",
    }
)
_LIFECYCLE_STATES = frozenset(
    {
        "not_submitted",
        "open",
        "cancelled",
        "filled",
        "outcome_unknown",
        "unavailable",
    }
)
_OBSERVATION_REASONS = frozenset(
    {
        "state_missing",
        "state_invalid",
        "intent_not_submitted",
        "provider_rejected",
        "preview",
        "broker_order_id_missing",
        "account_snapshot_stale",
        "read_only_unavailable",
        "exact_open_order",
        "same_day_order_id_not_terminal",
        "terminal_state_not_supported",
    }
)


class KisPaperReceiptObservationError(ValueError):
    """The private receipt state or its safe projection is malformed."""


@dataclass(frozen=True, repr=False)
class _PrivateReceiptIntentState:
    run_id: str
    intent_ref: str
    decision_ref: str
    receipt_ref: str
    order_side: Literal["buy", "sell"]
    phase: str
    raw_order_id: str | None = field(repr=False)


@dataclass(frozen=True)
class KisPaperReceiptObservation:
    """A fact-minimized lifecycle observation for one immutable receipt."""

    run_id: str
    receipt_ref: str
    intent_ref: str | None
    decision_ref: str | None
    order_side: Literal["buy", "sell"] | None
    state_phase: str | None
    observed_at: datetime
    lifecycle_state: str
    account_fact_status: Literal["not_checked", "current", "unavailable"]
    open_order_observation: Literal[
        "not_checked", "exact_match", "exact_absent", "unavailable"
    ]
    same_day_order_id_observation: Literal[
        "not_checked", "same_day_id_seen", "same_day_id_absent", "unavailable"
    ]
    position_state: Literal["not_observed", "flat", "one_share", "out_of_scope"]
    reconciliation_status: Literal["not_required", "observed", "ambiguous", "unavailable"]
    reason_code: str
    pnl_status: Literal["not_observed"] = "not_observed"
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _receipt_digest(self.run_id)
        if self.receipt_ref != f"sha256:{_receipt_digest(self.run_id)}":
            raise KisPaperReceiptObservationError("receipt reference is invalid")
        if self.intent_ref is not None and _SHA256_REFERENCE.fullmatch(self.intent_ref) is None:
            raise KisPaperReceiptObservationError("intent reference is invalid")
        if self.decision_ref is not None and not _is_decision_reference(self.decision_ref):
            raise KisPaperReceiptObservationError("decision reference is invalid")
        if self.order_side is not None and self.order_side not in {"buy", "sell"}:
            raise KisPaperReceiptObservationError("order side is invalid")
        if self.state_phase is not None and self.state_phase not in _STATE_PHASES:
            raise KisPaperReceiptObservationError("state phase is invalid")
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        if self.lifecycle_state not in _LIFECYCLE_STATES:
            raise KisPaperReceiptObservationError("lifecycle state is invalid")
        if self.account_fact_status not in {"not_checked", "current", "unavailable"}:
            raise KisPaperReceiptObservationError("account fact status is invalid")
        if self.open_order_observation not in {
            "not_checked",
            "exact_match",
            "exact_absent",
            "unavailable",
        }:
            raise KisPaperReceiptObservationError("open-order observation is invalid")
        if self.same_day_order_id_observation not in {
            "not_checked",
            "same_day_id_seen",
            "same_day_id_absent",
            "unavailable",
        }:
            raise KisPaperReceiptObservationError("same-day observation is invalid")
        if self.position_state not in {"not_observed", "flat", "one_share", "out_of_scope"}:
            raise KisPaperReceiptObservationError("position state is invalid")
        if self.reconciliation_status not in {
            "not_required",
            "observed",
            "ambiguous",
            "unavailable",
        }:
            raise KisPaperReceiptObservationError("reconciliation status is invalid")
        if self.reason_code not in _OBSERVATION_REASONS:
            raise KisPaperReceiptObservationError("observation reason is invalid")
        if self.pnl_status != "not_observed":
            raise KisPaperReceiptObservationError("PnL status is invalid")
        _validate_observation_shape(self)

    def safe_payload(self) -> dict[str, object]:
        """Return only categorical receipt-linked evidence safe for persistence."""

        return {
            "schema_version": self.schema_version,
            "kind": KIS_PAPER_RECEIPT_OBSERVATION_KIND,
            "route": "kis_paper",
            "paper_only": True,
            "run_id": self.run_id,
            "receipt_ref": self.receipt_ref,
            "intent_ref": self.intent_ref,
            "decision_ref": self.decision_ref,
            "order_side": self.order_side,
            "state_phase": self.state_phase,
            "observed_at": self.observed_at.isoformat(),
            "lifecycle_state": self.lifecycle_state,
            "account_fact_status": self.account_fact_status,
            "open_order_observation": self.open_order_observation,
            "same_day_order_id_observation": self.same_day_order_id_observation,
            "position_state": self.position_state,
            "reconciliation_status": self.reconciliation_status,
            "reason_code": self.reason_code,
            "pnl_status": self.pnl_status,
        }


@dataclass(frozen=True)
class KisPaperReceiptObservationOutcome:
    observation: KisPaperReceiptObservation
    evidence_path: Path


def observe_kis_paper_receipt(
    *,
    run_id: str,
    environment: Mapping[str, str],
    state_root: Path,
    artifact_root: Path,
    repository_root: Path,
    execute: bool,
    transport: KisHttpTransport | None = None,
    client: KisPaperReadOnlyClient | None = None,
    now: datetime | None = None,
    clock: Callable[[], datetime] | None = None,
    max_account_fact_age: timedelta = KIS_PAPER_RECEIPT_OBSERVATION_MAX_ACCOUNT_FACT_AGE,
) -> KisPaperReceiptObservationOutcome:
    """Observe exactly one durable Paper intent without any broker side effect."""

    observed_at = _observation_now(now=now, clock=clock)
    if max_account_fact_age <= timedelta(0):
        raise ValueError("maximum account fact age must be positive")
    if client is not None and type(client) is not KisPaperReadOnlyClient:
        raise ValueError("observer client must be the exact read-only client")
    _receipt_digest(run_id)
    try:
        private_state = _read_private_receipt_state(state_root / f"{run_id}.json", run_id)
    except KisPaperReceiptObservationError:
        observation = _unavailable_observation(run_id, observed_at, reason_code="state_invalid")
    else:
        observation = _observe_private_state(
            run_id=run_id,
            private_state=private_state,
            environment=environment,
            execute=execute,
            transport=transport,
            client=client,
            observed_at=observed_at,
            now=now,
            clock=clock,
            max_account_fact_age=max_account_fact_age,
        )
    evidence_path = _write_observation_evidence(
        observation,
        artifact_root=artifact_root,
        repository_root=repository_root,
    )
    return KisPaperReceiptObservationOutcome(observation=observation, evidence_path=evidence_path)


def _observe_private_state(
    *,
    run_id: str,
    private_state: _PrivateReceiptIntentState | None,
    environment: Mapping[str, str],
    execute: bool,
    transport: KisHttpTransport | None,
    client: KisPaperReadOnlyClient | None,
    observed_at: datetime,
    now: datetime | None,
    clock: Callable[[], datetime] | None,
    max_account_fact_age: timedelta,
) -> KisPaperReceiptObservation:
    if private_state is None:
        return _not_submitted_observation(run_id, observed_at, reason_code="state_missing")
    if private_state.phase == "intent_recorded":
        return _not_submitted_observation(
            run_id,
            observed_at,
            private_state=private_state,
            reason_code="intent_not_submitted",
        )
    if private_state.phase == "rejected":
        return _not_submitted_observation(
            run_id,
            observed_at,
            private_state=private_state,
            reason_code="provider_rejected",
        )
    if private_state.raw_order_id is None:
        return _state_observation(
            private_state,
            observed_at=observed_at,
            lifecycle_state="outcome_unknown",
            account_fact_status="not_checked",
            open_order_observation="not_checked",
            same_day_order_id_observation="not_checked",
            position_state="not_observed",
            reconciliation_status="ambiguous",
            reason_code="broker_order_id_missing",
        )
    if not execute:
        return _state_observation(
            private_state,
            observed_at=observed_at,
            lifecycle_state="outcome_unknown",
            account_fact_status="not_checked",
            open_order_observation="not_checked",
            same_day_order_id_observation="not_checked",
            position_state="not_observed",
            reconciliation_status="ambiguous",
            reason_code="preview",
        )
    fact_observed_at = observed_at
    try:
        read_only_client = client or KisPaperReadOnlyClient(
            config=load_kis_paper_config_from_environment(environment),
            transport=transport or UrllibKisHttpTransport(),
        )
        snapshot = read_only_client.snapshot()
        fact_observed_at = _observation_now(now=now, clock=clock)
        if not _snapshot_is_current(
            snapshot,
            observed_at=fact_observed_at,
            max_account_fact_age=max_account_fact_age,
        ):
            return _state_observation(
                private_state,
                observed_at=fact_observed_at,
                lifecycle_state="unavailable",
                account_fact_status="unavailable",
                open_order_observation="unavailable",
                same_day_order_id_observation="unavailable",
                position_state="not_observed",
                reconciliation_status="unavailable",
                reason_code="account_snapshot_stale",
            )
        same_day_order = read_only_client.observe_same_day_order_id(
            private_state.raw_order_id,
            as_of=fact_observed_at,
        )
    except KisPaperReadOnlyError:
        return _state_observation(
            private_state,
            observed_at=fact_observed_at,
            lifecycle_state="unavailable",
            account_fact_status="unavailable",
            open_order_observation="unavailable",
            same_day_order_id_observation="unavailable",
            position_state="not_observed",
            reconciliation_status="unavailable",
            reason_code="read_only_unavailable",
        )

    matching_open_order = _matching_open_order(snapshot, private_state.raw_order_id)
    open_order_observation: Literal["exact_match", "exact_absent"] = (
        "exact_match" if matching_open_order else "exact_absent"
    )
    same_day_observation: Literal["same_day_id_seen", "same_day_id_absent"] = (
        "same_day_id_seen" if same_day_order.same_day_order_id_seen else "same_day_id_absent"
    )
    if matching_open_order:
        return _state_observation(
            private_state,
            observed_at=fact_observed_at,
            lifecycle_state="open",
            account_fact_status="current",
            open_order_observation=open_order_observation,
            same_day_order_id_observation=same_day_observation,
            position_state=_spy_position_state(snapshot),
            reconciliation_status="observed",
            reason_code="exact_open_order",
        )
    return _state_observation(
        private_state,
        observed_at=fact_observed_at,
        lifecycle_state="outcome_unknown",
        account_fact_status="current",
        open_order_observation=open_order_observation,
        same_day_order_id_observation=same_day_observation,
        position_state=_spy_position_state(snapshot),
        reconciliation_status="ambiguous",
        reason_code=(
            "same_day_order_id_not_terminal"
            if same_day_order.same_day_order_id_seen
            else "terminal_state_not_supported"
        ),
    )


def _read_private_receipt_state(path: Path, run_id: str) -> _PrivateReceiptIntentState | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise KisPaperReceiptObservationError("private state is invalid") from error
    if not isinstance(payload, Mapping):
        raise KisPaperReceiptObservationError("private state is invalid")
    expected = {
        "schema_version",
        "kind",
        "intent",
        "intent_fingerprint",
        "phase",
        "updated_at",
        "reason_code",
        "broker_order_id",
    }
    optional = {"cancel_after_submit", "submit_upstream_code", "submit_response_category"}
    if not expected <= set(payload) <= expected | optional:
        raise KisPaperReceiptObservationError("private state is invalid")
    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("kind") != "kis_paper_canary_state"
    ):
        raise KisPaperReceiptObservationError("private state is invalid")
    raw_intent = payload.get("intent")
    if not isinstance(raw_intent, Mapping):
        raise KisPaperReceiptObservationError("private state is invalid")
    try:
        side = raw_intent.get("side", "buy")
        if side not in {"buy", "sell"}:
            raise ValueError("side")
        quantity = _positive_decimal(raw_intent.get("quantity"))
        limit_price = _positive_decimal(raw_intent.get("limit_price"))
        created_at = _utc_datetime(raw_intent.get("created_at"))
        valid_until = _utc_datetime(raw_intent.get("valid_until"))
        updated_at = _utc_datetime(payload.get("updated_at"))
        receipt_digest = _receipt_digest(run_id)
        client_order_id = _required_text(raw_intent.get("client_order_id"))
        decision_id = _required_text(raw_intent.get("decision_id"))
        if (
            _required_text(raw_intent.get("run_id")) != run_id
            or client_order_id != f"canary-{run_id}"
            or decision_id != run_id
            or _required_text(raw_intent.get("symbol")) != "SPY"
            or _required_text(raw_intent.get("exchange")) != "AMEX"
            or quantity != Decimal("1")
            or valid_until <= created_at
            or updated_at.tzinfo is None
        ):
            raise ValueError("receipt identity")
        price_contract_ref = raw_intent.get("price_contract_ref")
        if price_contract_ref is not None and (
            not isinstance(price_contract_ref, str)
            or _SHA256_REFERENCE.fullmatch(price_contract_ref) is None
        ):
            raise ValueError("price contract")
        canonical_intent: dict[str, str] = {
            "run_id": run_id,
            "client_order_id": client_order_id,
            "decision_id": decision_id,
            "symbol": "SPY",
            "exchange": "AMEX",
            "quantity": str(quantity),
            "limit_price": str(limit_price),
            "created_at": created_at.isoformat(),
            "valid_until": valid_until.isoformat(),
        }
        if price_contract_ref is not None:
            canonical_intent["price_contract_ref"] = price_contract_ref
        if side == "sell":
            canonical_intent["side"] = side
        intent_ref = "sha256:" + hashlib.sha256(
            json.dumps(canonical_intent, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if (
            payload.get("intent_fingerprint") != intent_ref
            or payload.get("phase") not in _STATE_PHASES
        ):
            raise ValueError("fingerprint or phase")
        raw_order_id = payload.get("broker_order_id")
        if raw_order_id is not None and (
            not isinstance(raw_order_id, str) or _RAW_ORDER_ID.fullmatch(raw_order_id) is None
        ):
            raise ValueError("order id")
        return _PrivateReceiptIntentState(
            run_id=run_id,
            intent_ref=intent_ref,
            decision_ref="decision-" + hashlib.sha256(decision_id.encode("utf-8")).hexdigest()[:16],
            receipt_ref=f"sha256:{receipt_digest}",
            order_side=side,
            phase=payload["phase"],
            raw_order_id=raw_order_id,
        )
    except (InvalidOperation, TypeError, ValueError) as error:
        raise KisPaperReceiptObservationError("private state is invalid") from error


def _not_submitted_observation(
    run_id: str,
    observed_at: datetime,
    *,
    private_state: _PrivateReceiptIntentState | None = None,
    reason_code: Literal["state_missing", "intent_not_submitted", "provider_rejected"],
) -> KisPaperReceiptObservation:
    return KisPaperReceiptObservation(
        run_id=run_id,
        receipt_ref=f"sha256:{_receipt_digest(run_id)}",
        intent_ref=None if private_state is None else private_state.intent_ref,
        decision_ref=None if private_state is None else private_state.decision_ref,
        order_side=None if private_state is None else private_state.order_side,
        state_phase=None if private_state is None else private_state.phase,
        observed_at=observed_at,
        lifecycle_state="not_submitted",
        account_fact_status="not_checked",
        open_order_observation="not_checked",
        same_day_order_id_observation="not_checked",
        position_state="not_observed",
        reconciliation_status="not_required",
        reason_code=reason_code,
    )


def _unavailable_observation(
    run_id: str,
    observed_at: datetime,
    *,
    reason_code: Literal["state_invalid"],
) -> KisPaperReceiptObservation:
    return KisPaperReceiptObservation(
        run_id=run_id,
        receipt_ref=f"sha256:{_receipt_digest(run_id)}",
        intent_ref=None,
        decision_ref=None,
        order_side=None,
        state_phase=None,
        observed_at=observed_at,
        lifecycle_state="unavailable",
        account_fact_status="unavailable",
        open_order_observation="unavailable",
        same_day_order_id_observation="unavailable",
        position_state="not_observed",
        reconciliation_status="unavailable",
        reason_code=reason_code,
    )


def _state_observation(
    private_state: _PrivateReceiptIntentState,
    *,
    observed_at: datetime,
    lifecycle_state: str,
    account_fact_status: Literal["not_checked", "current", "unavailable"],
    open_order_observation: Literal["not_checked", "exact_match", "exact_absent", "unavailable"],
    same_day_order_id_observation: Literal[
        "not_checked", "same_day_id_seen", "same_day_id_absent", "unavailable"
    ],
    position_state: Literal["not_observed", "flat", "one_share", "out_of_scope"],
    reconciliation_status: Literal["not_required", "observed", "ambiguous", "unavailable"],
    reason_code: str,
) -> KisPaperReceiptObservation:
    return KisPaperReceiptObservation(
        run_id=private_state.run_id,
        receipt_ref=private_state.receipt_ref,
        intent_ref=private_state.intent_ref,
        decision_ref=private_state.decision_ref,
        order_side=private_state.order_side,
        state_phase=private_state.phase,
        observed_at=observed_at,
        lifecycle_state=lifecycle_state,
        account_fact_status=account_fact_status,
        open_order_observation=open_order_observation,
        same_day_order_id_observation=same_day_order_id_observation,
        position_state=position_state,
        reconciliation_status=reconciliation_status,
        reason_code=reason_code,
    )


def _matching_open_order(snapshot: KisPaperReadOnlySnapshot, raw_order_id: str) -> bool:
    reference = "open-" + hashlib.sha256(raw_order_id.encode("utf-8")).hexdigest()[:16]
    return any(order.order_reference == reference for order in snapshot.open_orders.orders)


def _spy_position_state(
    snapshot: KisPaperReadOnlySnapshot,
) -> Literal["flat", "one_share", "out_of_scope"]:
    spy_positions = [position for position in snapshot.positions if position.symbol == "SPY"]
    if not spy_positions:
        return "flat"
    if (
        len(spy_positions) == 1
        and spy_positions[0].exchange == "AMEX"
        and spy_positions[0].quantity == 1
    ):
        return "one_share"
    return "out_of_scope"


def _snapshot_is_current(
    snapshot: KisPaperReadOnlySnapshot,
    *,
    observed_at: datetime,
    max_account_fact_age: timedelta,
) -> bool:
    if snapshot.captured_at > observed_at:
        return False
    return observed_at - snapshot.captured_at <= max_account_fact_age


def _write_observation_evidence(
    observation: KisPaperReceiptObservation,
    *,
    artifact_root: Path,
    repository_root: Path,
) -> Path:
    root = Path(artifact_root).resolve()
    repository = _source_repository_root(Path(repository_root))
    if not _is_permitted_artifact_root(root, repository):
        raise KisPaperReceiptObservationError("artifact root must stay outside Git")
    payload = observation.safe_payload()
    encoded = (json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n").encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()[:16]
    destination = (
        root
        / "execution"
        / "kis-paper-receipt-observation"
        / f"receipt-{_receipt_digest(observation.run_id)[:16]}"
        / f"{observation.observed_at.strftime('%Y%m%dT%H%M%S%fZ')}-{digest}.json"
    )
    if not _is_permitted_artifact_destination(destination, root, repository):
        raise KisPaperReceiptObservationError("observation destination must stay outside Git")
    if destination.exists():
        if destination.read_bytes() != encoded:
            raise KisPaperReceiptObservationError("observation evidence conflicts")
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not _is_permitted_artifact_destination(destination, root, repository):
        raise KisPaperReceiptObservationError("observation destination must stay outside Git")
    staging = destination.with_name(f".{digest}.{uuid.uuid4().hex[:8]}.stage")
    try:
        staging.write_bytes(encoded)
        os.replace(staging, destination)
    finally:
        staging.unlink(missing_ok=True)
    return destination


def _is_permitted_artifact_root(artifact_root: Path, repository_root: Path) -> bool:
    if not artifact_root.is_relative_to(repository_root):
        return True
    return artifact_root == repository_root / "model_artifacts" and artifact_root.is_mount()


def _source_repository_root(fallback_repository_root: Path) -> Path:
    """Use the loaded source checkout when it is available over caller input."""

    source_root = Path(__file__).resolve().parents[3]
    if (source_root / "pyproject.toml").is_file():
        return source_root
    return fallback_repository_root.resolve()


def _is_permitted_artifact_destination(
    destination: Path,
    artifact_root: Path,
    repository_root: Path,
) -> bool:
    """Reject a symlink or junction below an external root that points into Git."""

    resolved_destination = destination.resolve()
    try:
        resolved_destination.relative_to(artifact_root)
    except ValueError:
        return False
    if not resolved_destination.is_relative_to(repository_root):
        return True
    return artifact_root == repository_root / "model_artifacts" and artifact_root.is_mount()


def _validate_observation_shape(observation: KisPaperReceiptObservation) -> None:
    if observation.lifecycle_state == "open":
        if (
            observation.account_fact_status != "current"
            or observation.open_order_observation != "exact_match"
            or observation.reconciliation_status != "observed"
            or observation.reason_code != "exact_open_order"
        ):
            raise KisPaperReceiptObservationError("open lifecycle is unsupported")
        return
    if observation.lifecycle_state in {"filled", "cancelled"}:
        raise KisPaperReceiptObservationError("terminal lifecycle is not supported by this source")
    if observation.lifecycle_state == "not_submitted" and observation.state_phase not in {
        None,
        "intent_recorded",
        "rejected",
    }:
        raise KisPaperReceiptObservationError("not-submitted lifecycle is invalid")


def _receipt_digest(run_id: str) -> str:
    match = _RECEIPT_RUN_ID.fullmatch(run_id)
    if match is None:
        raise KisPaperReceiptObservationError("receipt run id is invalid")
    return match.group(1)


def _is_decision_reference(value: str) -> bool:
    return bool(re.fullmatch(r"decision-[0-9a-f]{16}", value, re.ASCII))


def _required_text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("text")
    return value


def _positive_decimal(value: object) -> Decimal:
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("decimal") from error
    if not decimal.is_finite() or decimal <= 0:
        raise ValueError("decimal")
    return decimal


def _utc_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("datetime")
    return require_utc(datetime.fromisoformat(value), "datetime")


def _observation_now(
    *,
    now: datetime | None,
    clock: Callable[[], datetime] | None,
) -> datetime:
    if now is not None and clock is not None:
        raise ValueError("now and clock are mutually exclusive")
    source = now if now is not None else (clock() if clock is not None else datetime.now(UTC))
    return require_utc(source, "now")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Observe one receipt-linked KIS Paper intent")
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--state-root",
        type=Path,
        default=DEFAULT_KIS_PAPER_RECEIPT_OBSERVATION_STATE_ROOT,
    )
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_KIS_PAPER_ARTIFACT_ROOT)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    outcome = observe_kis_paper_receipt(
        run_id=arguments.run_id,
        environment=os.environ,
        state_root=arguments.state_root,
        artifact_root=arguments.artifact_root,
        repository_root=arguments.repository_root,
        execute=arguments.execute,
    )
    print(
        json.dumps(
            {**outcome.observation.safe_payload(), "evidence_path": str(outcome.evidence_path)}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
