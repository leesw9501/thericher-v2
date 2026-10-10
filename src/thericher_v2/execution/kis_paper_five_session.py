"""Pure cadence for one exclusively owned, frozen five-session Paper cohort.

This neither reserves nor submits orders. Calendar/source references are caller-
verified custody, not proof of provider availability or broker/account state.
The existing stock entry/exit paths still perform call-time sizing and reads.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from thericher_v2.contracts import require_utc
from thericher_v2.research.five_session_paper_decision import FiveSessionPaperDecision

from .kis_paper_budget_strategy import _stock_identity, _stock_owner_id, _terminal
from .kis_paper_canary import KisPaperCanaryState
from .kis_paper_fill_accounting import KisPaperExecutionObservation
from .kis_paper_portfolio_budget import (
    KisPaperPortfolioBudgetBasis,
    KisPaperPortfolioOwnerBinding,
    KisPaperPortfolioStateRef,
    project_kis_paper_portfolio_budget,
)
from .kis_paper_stock_quote import KisPaperStockInstrument

_HASH = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)
_DECISION = re.compile(r"decision:sha256:[0-9a-f]{64}", re.ASCII)
_NY = ZoneInfo("America/New_York")


@dataclass(frozen=True, slots=True, repr=False)
class KisPaperFiveSessionCohort:
    instrument: KisPaperStockInstrument
    entry_decision_id: str
    calendar_ref: str
    source_ref: str
    session_opens: tuple[datetime, ...]
    session_closes: tuple[datetime, ...]
    entry_window_end: datetime
    exit_due: datetime

    def __post_init__(self) -> None:
        if type(self.instrument) is not KisPaperStockInstrument:
            raise ValueError("cohort_instrument_invalid")
        replace(self.instrument)
        if type(self.entry_decision_id) is not str or not _DECISION.fullmatch(
            self.entry_decision_id
        ):
            raise ValueError("cohort_decision_invalid")
        for value in (self.calendar_ref, self.source_ref):
            if type(value) is not str or not _HASH.fullmatch(value):
                raise ValueError("cohort_source_invalid")
        if (
            type(self.session_opens) is not tuple
            or type(self.session_closes) is not tuple
            or len(self.session_opens) != 5
            or len(self.session_closes) != 5
        ):
            raise ValueError("cohort_sessions_invalid")
        previous = None
        for opened, closed in zip(self.session_opens, self.session_closes, strict=True):
            require_utc(opened)
            require_utc(closed)
            local_open, local_close = opened.astimezone(_NY), closed.astimezone(_NY)
            if (
                not opened < closed
                or (previous is not None and not previous < opened)
                or (previous is not None and previous.astimezone(_NY).date() >= local_open.date())
                or local_open.date() != local_close.date()
                or local_open.weekday() > 4
            ):
                raise ValueError("cohort_sessions_invalid")
            previous = closed
        require_utc(self.entry_window_end)
        require_utc(self.exit_due)
        if not self.session_opens[0] < self.entry_window_end <= self.session_closes[0]:
            raise ValueError("cohort_entry_window_invalid")
        if not self.session_opens[-1] <= self.exit_due < self.session_closes[-1]:
            raise ValueError("cohort_exit_window_invalid")
        if self.exit_due != self.session_closes[-1] - timedelta(minutes=10):
            raise ValueError("cohort_exit_clock_invalid")

    @property
    def owner_ref(self) -> str:
        return _stock_owner_id(self.instrument.binding_ref)

    @property
    def entry_request_id(self) -> str:
        return "five-" + self.fingerprint.removeprefix("sha256:")

    @property
    def fingerprint(self) -> str:
        payload = [
            "kis_paper_five_session_cohort_v1",
            self.instrument.symbol,
            self.instrument.binding_ref,
            self.entry_decision_id,
            self.calendar_ref,
            self.source_ref,
            [value.isoformat() for value in self.session_opens],
            [value.isoformat() for value in self.session_closes],
            self.entry_window_end.isoformat(),
            self.exit_due.isoformat(),
        ]
        return (
            "sha256:"
            + hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode("ascii")).hexdigest()
        )


@dataclass(frozen=True, slots=True, repr=False)
class KisPaperFiveSessionCustody:
    """References retained by the caller before effects; never reset on restart."""

    entry: KisPaperPortfolioStateRef | None = None
    exits: tuple[KisPaperPortfolioStateRef, ...] = ()

    def __post_init__(self) -> None:
        if type(self.exits) is not tuple or (self.entry is None and self.exits):
            raise ValueError("cohort_custody_invalid")
        references = (() if self.entry is None else (self.entry,)) + self.exits
        for reference in references:
            if type(reference) is not KisPaperPortfolioStateRef:
                raise ValueError("cohort_custody_invalid")
            replace(reference)
        if len({r.run_id for r in references}) != len(references):
            raise ValueError("cohort_custody_duplicate")

    @property
    def state_refs(self) -> tuple[KisPaperPortfolioStateRef, ...]:
        return (() if self.entry is None else (self.entry,)) + self.exits


@dataclass(frozen=True, slots=True, repr=False)
class KisPaperFiveSessionProjection:
    status: str
    reason: str
    owned_quantity: Decimal | None = None
    pending: KisPaperPortfolioStateRef | None = None

    def safe_payload(self) -> dict[str, str]:
        return {
            "kind": "kis_paper_five_session_projection_v1",
            "status": self.status,
            "reason": self.reason,
            "inventory": "unknown"
            if self.owned_quantity is None
            else ("owned_flat" if self.owned_quantity == 0 else "owned_remaining"),
            "scope": "paper_only_no_side_effects",
        }


def cohort_from_paper_decision(
    decision: FiveSessionPaperDecision, *, calendar_ref: str
) -> KisPaperFiveSessionCohort:
    """Consume finite metadata only, never a teacher or numeric feature frame.

    A later no-intent DTO cannot replace an already persisted owned cohort.
    Source is the exact input-manifest reference; the receipt binds model,
    allocation, proposal and actual inference timing on the Research side.
    """
    if type(decision) is not FiveSessionPaperDecision:
        raise ValueError("cohort_decision_invalid")
    replace(decision)
    if decision.status != "prepared":
        raise ValueError("cohort_no_entry_decision")
    return KisPaperFiveSessionCohort(
        KisPaperStockInstrument(decision.proposal.symbol, decision.instrument_binding_ref),
        decision.receipt.decision_id,
        calendar_ref,
        decision.input_manifest_ref,
        decision.session_opens,
        decision.session_closes,
        decision.entry_valid_until,
        decision.fifth_close - timedelta(minutes=10),
    )


def project_five_session_cohort(
    *,
    cohort: KisPaperFiveSessionCohort,
    expected_cohort_ref: str,
    custody: KisPaperFiveSessionCustody,
    basis: KisPaperPortfolioBudgetBasis,
    expected_basis_ref: str,
    owners: tuple[KisPaperPortfolioOwnerBinding, ...],
    expected_owner_refs: Mapping[str, str],
    states: Mapping[str, KisPaperCanaryState],
    as_of: datetime,
    input_status: str,
    cancellation_proofs: Mapping[str, KisPaperExecutionObservation] | None = None,
) -> KisPaperFiveSessionProjection:
    if (
        type(cohort) is not KisPaperFiveSessionCohort
        or type(custody) is not KisPaperFiveSessionCustody
    ):
        raise ValueError("cohort_contract_invalid")
    replace(cohort)
    replace(custody)
    require_utc(as_of)
    if expected_cohort_ref != cohort.fingerprint:
        raise ValueError("cohort_binding_mismatch")
    if input_status not in {"ready", "unavailable"}:
        raise ValueError("cohort_input_status_invalid")
    projection = project_kis_paper_portfolio_budget(
        basis=basis,
        expected_basis_ref=expected_basis_ref,
        owners=owners,
        expected_owner_refs=expected_owner_refs,
        states=states,
        as_of=as_of,
        cancellation_proofs=cancellation_proofs,
    )
    proofs = cancellation_proofs or {}
    owner = next((row for row in owners if row.owner_ref == cohort.owner_ref), None)
    if (owner is None and custody.state_refs) or (
        owner is not None
        and (
            owner.symbol != cohort.instrument.symbol
            or owner.exchange != cohort.instrument.order_exchange
            or owner.stock_binding_ref != cohort.instrument.binding_ref
            or owner.state_refs != custody.state_refs
        )
    ):
        return KisPaperFiveSessionProjection("no_intent", "cohort_custody_mismatch")
    quantity = (
        Decimal(0)
        if owner is None
        else next(
            row.quantity for row in projection.stocks_by_owner if row.owner_ref == owner.owner_ref
        )
    )
    for other in owners:
        if other.owner_ref == cohort.owner_ref or (other.symbol, other.exchange) != (
            cohort.instrument.symbol,
            cohort.instrument.order_exchange,
        ):
            continue
        other_stock = next(
            row for row in projection.stocks_by_owner if row.owner_ref == other.owner_ref
        )
        if (
            other_stock.quantity
            or other_stock.reserved_buys
            or any(not _terminal(states[r.run_id], proofs.get(r.run_id)) for r in other.state_refs)
        ):
            return KisPaperFiveSessionProjection("reconcile", "exclusive_instrument_conflict")
    if custody.entry is None:
        if as_of < cohort.session_opens[0]:
            return KisPaperFiveSessionProjection("deferred", "awaiting_first_open", quantity)
        if as_of >= cohort.entry_window_end:
            return KisPaperFiveSessionProjection("no_intent", "entry_window_elapsed", quantity)
        if input_status != "ready":
            return KisPaperFiveSessionProjection("no_intent", "input_unavailable", quantity)
        return KisPaperFiveSessionProjection("entry_ready", "entry_due", quantity)

    entry = states[custody.entry.run_id]
    identity = _stock_identity(
        {
            "account_ref": basis.account_ref,
            "basis_ref": basis.fingerprint,
            "stocks": {
                owner.symbol: {
                    "exchange": owner.exchange,
                    "instrument_binding_ref": owner.stock_binding_ref,
                }
            },
        },
        owner.symbol,
        cohort.entry_request_id,
        "buy",
    )
    if (
        entry.intent.side != "buy"
        or (entry.intent.run_id, entry.intent.client_order_id, entry.intent.decision_id)
        != ("bk-" + identity, "stock-" + identity, "stock-" + identity)
        or not cohort.session_opens[0] <= entry.intent.created_at < cohort.entry_window_end
        or entry.intent.valid_until > cohort.entry_window_end
    ):
        return KisPaperFiveSessionProjection("reconcile", "entry_contract_mismatch")
    for reference in custody.exits:
        state = states[reference.run_id]
        if state.intent.side != "sell" or state.intent.created_at < cohort.exit_due:
            return KisPaperFiveSessionProjection("reconcile", "exit_contract_mismatch")
    # Exact pending identity takes precedence over input changes and every timer.
    for reference in custody.state_refs:
        if not _terminal(states[reference.run_id], proofs.get(reference.run_id)):
            phase = "entry" if reference == custody.entry else "exit"
            return KisPaperFiveSessionProjection(
                "reconcile", phase + "_recovery_pending", quantity, reference
            )
    if quantity == 0:
        reason = "entry_terminal_no_fill" if not custody.exits else "owned_flat"
        return KisPaperFiveSessionProjection("closed", reason, quantity)
    if as_of < cohort.exit_due:
        return KisPaperFiveSessionProjection("hold", "owned_holding", quantity)
    return KisPaperFiveSessionProjection("exit_ready", "fifth_session_exit_due", quantity)
