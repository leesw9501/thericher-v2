"""Pure cohort-local gross/marked PnL and explicitly observed fill-fee coverage.

Sources and historical snapshot clocks are caller-attested custody, not proof
of provider finality, historical freezing or current broker reconciliation.
No initial capital, shared-portfolio cash, settled cash or cohort NAV is inferred.
Fee-adjusted totals cover only the supplied cumulative USD fill fees, not tax,
financing, settlement or every possible account charge.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Context, Decimal, localcontext
from fractions import Fraction
from types import MappingProxyType

from thericher_v2.contracts import require_utc

from .kis_paper_budget_strategy import _stock_identity
from .kis_paper_canary import KisPaperCanaryIntent, KisPaperCanaryState
from .kis_paper_fill_accounting import KisPaperCumulativeFill, KisPaperExecutionObservation
from .kis_paper_five_session import (
    KisPaperFiveSessionCohort,
    KisPaperFiveSessionCustody,
    project_five_session_cohort,
)
from .kis_paper_portfolio_budget import (
    KisPaperPortfolioBudgetBasis,
    KisPaperPortfolioOwnerBinding,
    KisPaperPortfolioStateRef,
)
from .kis_paper_portfolio_pnl import project_kis_paper_portfolio_pnl
from .kis_paper_stock_quote import KisPaperStockInstrument

_HASH = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)


def _hash(value: str) -> None:
    if type(value) is not str or not _HASH.fullmatch(value):
        raise ValueError("cohort_pnl_source_invalid")


def _amount(value: Decimal, *, positive: bool = False) -> None:
    if (
        type(value) is not Decimal
        or not value.is_finite()
        or value < 0
        or (positive and value == 0)
    ):
        raise ValueError("cohort_pnl_amount_invalid")


@dataclass(frozen=True, slots=True, repr=False)
class KisPaperFiveSessionFeeReceipt:
    """One cumulative USD fee total for one exact retained positive fill."""

    cohort_ref: str
    state_ref: KisPaperPortfolioStateRef
    fill_identity_ref: str
    fill_quantity: Decimal
    fill_gross_usd: Decimal
    fee_usd: Decimal
    source_ref: str
    observed_at: datetime

    def __post_init__(self) -> None:
        for value in (self.cohort_ref, self.fill_identity_ref, self.source_ref):
            _hash(value)
        if type(self.state_ref) is not KisPaperPortfolioStateRef:
            raise ValueError("cohort_pnl_fee_binding_invalid")
        replace(self.state_ref)
        _amount(self.fill_quantity, positive=True)
        _amount(self.fill_gross_usd, positive=True)
        _amount(self.fee_usd)
        if self.fill_quantity != self.fill_quantity.to_integral_value():
            raise ValueError("cohort_pnl_fee_quantity_invalid")
        require_utc(self.observed_at)


@dataclass(frozen=True, slots=True, repr=False)
class KisPaperFiveSessionAccountingSnapshot:
    """Independent frozen scope; expected references come from caller custody."""

    cohort_ref: str
    custody: KisPaperFiveSessionCustody
    basis: KisPaperPortfolioBudgetBasis
    expected_basis_ref: str
    owners: tuple[KisPaperPortfolioOwnerBinding, ...]
    expected_owner_refs: Mapping[str, str]
    states: Mapping[str, KisPaperCanaryState]
    as_of: datetime
    source_ref: str
    cancellation_proofs: Mapping[str, KisPaperExecutionObservation] | None = None
    fees: tuple[KisPaperFiveSessionFeeReceipt, ...] | None = None

    def __post_init__(self) -> None:
        for value in (self.cohort_ref, self.expected_basis_ref, self.source_ref):
            _hash(value)
        require_utc(self.as_of)
        if (
            type(self.custody) is not KisPaperFiveSessionCustody
            or type(self.basis) is not KisPaperPortfolioBudgetBasis
            or type(self.owners) is not tuple
            or any(type(owner) is not KisPaperPortfolioOwnerBinding for owner in self.owners)
            or not isinstance(self.states, Mapping)
            or not isinstance(self.expected_owner_refs, Mapping)
            or (
                self.cancellation_proofs is not None
                and not isinstance(self.cancellation_proofs, Mapping)
            )
            or (
                self.fees is not None
                and (
                    type(self.fees) is not tuple
                    or any(type(fee) is not KisPaperFiveSessionFeeReceipt for fee in self.fees)
                )
            )
        ):
            raise ValueError("cohort_pnl_snapshot_invalid")
        # Copy nested frozen DTOs too: neither caller mappings nor object aliases
        # become the arithmetic input after this snapshot is constructed.
        with localcontext(Context(prec=64)):
            object.__setattr__(
                self,
                "custody",
                replace(
                    self.custody,
                    entry=None if self.custody.entry is None else replace(self.custody.entry),
                    exits=tuple(replace(ref) for ref in self.custody.exits),
                ),
            )
            object.__setattr__(self, "basis", replace(self.basis))
            object.__setattr__(
                self,
                "owners",
                tuple(
                    replace(o, state_refs=tuple(replace(ref) for ref in o.state_refs))
                    for o in self.owners
                ),
            )
            states = {}
            for run, state in self.states.items():
                if (
                    type(state) is not KisPaperCanaryState
                    or type(state.intent) is not KisPaperCanaryIntent
                    or (
                        state.cumulative_fill is not None
                        and type(state.cumulative_fill) is not KisPaperCumulativeFill
                    )
                ):
                    raise ValueError("cohort_pnl_state_invalid")
                states[run] = replace(
                    state,
                    intent=replace(state.intent),
                    cumulative_fill=(
                        None if state.cumulative_fill is None else replace(state.cumulative_fill)
                    ),
                )
            if any(
                type(proof) is not KisPaperExecutionObservation
                for proof in (self.cancellation_proofs or {}).values()
            ):
                raise ValueError("cohort_pnl_cancel_proof_invalid")
            proofs = {
                run: replace(proof, fill=None if proof.fill is None else replace(proof.fill))
                for run, proof in (self.cancellation_proofs or {}).items()
            }
            object.__setattr__(self, "states", MappingProxyType(states))
            object.__setattr__(self, "cancellation_proofs", MappingProxyType(proofs))
            object.__setattr__(
                self, "expected_owner_refs", MappingProxyType(dict(self.expected_owner_refs))
            )
            if self.fees is not None:
                object.__setattr__(self, "fees", tuple(replace(fee) for fee in self.fees))


@dataclass(frozen=True, slots=True, repr=False)
class KisPaperFiveSessionCloseMark:
    cohort_ref: str
    calendar_ref: str
    instrument: KisPaperStockInstrument
    close_at: datetime
    price_usd: Decimal
    source_ref: str
    observed_at: datetime

    def __post_init__(self) -> None:
        for value in (self.cohort_ref, self.calendar_ref, self.source_ref):
            _hash(value)
        if type(self.instrument) is not KisPaperStockInstrument:
            raise ValueError("cohort_pnl_mark_instrument_invalid")
        replace(self.instrument)
        _amount(self.price_usd, positive=True)
        require_utc(self.close_at)
        require_utc(self.observed_at)
        if self.observed_at < self.close_at:
            raise ValueError("cohort_pnl_mark_time_invalid")


@dataclass(frozen=True, slots=True, repr=False)
class KisPaperFiveSessionCloseInput:
    close_at: datetime
    snapshot: KisPaperFiveSessionAccountingSnapshot | None = None
    mark: KisPaperFiveSessionCloseMark | None = None

    def __post_init__(self) -> None:
        require_utc(self.close_at)
        if self.snapshot is not None:
            if type(self.snapshot) is not KisPaperFiveSessionAccountingSnapshot:
                raise ValueError("cohort_pnl_close_snapshot_invalid")
            if self.snapshot.as_of > self.close_at:
                raise ValueError("cohort_pnl_snapshot_after_close")
        if self.mark is not None and type(self.mark) is not KisPaperFiveSessionCloseMark:
            raise ValueError("cohort_pnl_close_mark_invalid")


@dataclass(frozen=True, slots=True, repr=False)
class KisPaperFiveSessionPnlPoint:
    accounting_status: str
    valuation_status: str
    fee_status: str
    cohort_status: str
    chronology: str = "unavailable"
    retained_quantity: Fraction | None = None
    gross_realized_usd: Fraction | None = None
    remaining_entry_cost_usd: Fraction | None = None
    marked_value_usd: Fraction | None = None
    gross_unrealized_usd: Fraction | None = None
    gross_total_usd: Fraction | None = None
    fees_usd: Fraction | None = None
    net_pnl_usd: Fraction | None = None
    positive_fill_count: int = 0
    pending_intent_count: int = 0


@dataclass(frozen=True, slots=True, repr=False)
class KisPaperFiveSessionPnlProjection:
    current: KisPaperFiveSessionPnlPoint
    closes: tuple[KisPaperFiveSessionPnlPoint, ...]

    def safe_payload(self) -> dict[str, object]:
        return {
            "kind": "kis_paper_five_session_pnl_v1",
            "accounting": self.current.accounting_status,
            "cohort": self.current.cohort_status,
            "chronology": self.current.chronology,
            "fees": self.current.fee_status,
            "net_pnl": "observed_fill_fee_adjusted"
            if self.current.net_pnl_usd is not None
            else "unavailable",
            "positive_fill_count": self.current.positive_fill_count,
            "pending_intent_count": self.current.pending_intent_count,
            "close_count": len(self.closes),
            "valued_close_count": sum(p.valuation_status == "complete" for p in self.closes),
            "close_valuation": [p.valuation_status for p in self.closes],
            "close_fees": [p.fee_status for p in self.closes],
            "settled_cash": "not_observed",
            "scope": "historical_owned_fills_caller_attested_sources_no_side_effects",
        }


def _scope(cohort, snapshot, expected_custody, *, exact=False):
    if snapshot.cohort_ref != cohort.fingerprint or (
        exact and snapshot.custody != expected_custody
    ):
        raise ValueError("cohort_pnl_custody_mismatch")
    refs = snapshot.custody.state_refs
    if refs != expected_custody.state_refs[: len(refs)]:
        raise ValueError("cohort_pnl_custody_mismatch")
    for index, ref in enumerate(refs):
        state = snapshot.states.get(ref.run_id)
        if state is None:
            raise ValueError("cohort_pnl_state_missing")
        request = (
            cohort.entry_request_id
            if index == 0
            else ("five-exit-" + cohort.fingerprint.removeprefix("sha256:") + "-" + str(index - 1))
        )
        side = "buy" if index == 0 else "sell"
        identity = _stock_identity(
            {
                "account_ref": snapshot.basis.account_ref,
                "basis_ref": snapshot.expected_basis_ref,
                "stocks": {
                    cohort.instrument.symbol: {
                        "exchange": cohort.instrument.order_exchange,
                        "instrument_binding_ref": cohort.instrument.binding_ref,
                    }
                },
            },
            cohort.instrument.symbol,
            request,
            side,
        )
        if (
            state.intent.run_id,
            state.intent.client_order_id,
            state.intent.decision_id,
            state.intent.side,
        ) != ("bk-" + identity, "stock-" + identity, "stock-" + identity, side):
            raise ValueError("cohort_pnl_request_identity_mismatch")


def _advance(previous, current):
    if (
        previous.as_of > current.as_of
        or previous.custody.state_refs
        != (current.custody.state_refs[: len(previous.custody.state_refs)])
    ):
        raise ValueError("cohort_pnl_snapshot_regression")
    for ref in previous.custody.state_refs:
        old, new = previous.states[ref.run_id], current.states[ref.run_id]
        if new.updated_at < old.updated_at or (
            old.cumulative_fill is not None and new.cumulative_fill is None
        ):
            raise ValueError("cohort_pnl_snapshot_regression")
        if new.cumulative_fill is not None:
            new.cumulative_fill.advance(old.cumulative_fill)
    if previous.fees is not None and current.fees is not None:
        old_fees = {fee.state_ref: fee for fee in previous.fees}
        for fee in current.fees:
            old = old_fees.get(fee.state_ref)
            if old is not None and (fee.observed_at < old.observed_at or fee.fee_usd < old.fee_usd):
                raise ValueError("cohort_pnl_fee_regression")


def _fees(cohort, snapshot, complete):
    if snapshot.fees is None:
        return "not_observed", None
    fills = {
        ref: snapshot.states[ref.run_id].cumulative_fill
        for ref in snapshot.custody.state_refs
        if snapshot.states[ref.run_id].cumulative_fill is not None
        and snapshot.states[ref.run_id].cumulative_fill.quantity > 0
    }
    seen, total = set(), Fraction(0)
    for receipt in snapshot.fees:
        fill = fills.get(receipt.state_ref)
        if (
            receipt.state_ref in seen
            or fill is None
            or (
                receipt.cohort_ref != cohort.fingerprint
                or receipt.fill_identity_ref != fill.identity_ref
                or receipt.fill_quantity != fill.quantity
                or receipt.fill_gross_usd != fill.gross_amount
                or not fill.observed_at <= receipt.observed_at <= snapshot.as_of
            )
        ):
            raise ValueError("cohort_pnl_fee_binding_mismatch")
        seen.add(receipt.state_ref)
        total += Fraction(receipt.fee_usd)
    return ("observed", total) if complete and seen == set(fills) else ("incomplete", None)


def _point(cohort, snapshot, mark):
    arguments = dict(
        basis=snapshot.basis,
        expected_basis_ref=snapshot.expected_basis_ref,
        owners=snapshot.owners,
        expected_owner_refs=snapshot.expected_owner_refs,
        states=snapshot.states,
        as_of=snapshot.as_of,
        cancellation_proofs=snapshot.cancellation_proofs,
    )
    with localcontext(Context(prec=64)):
        cadence = project_five_session_cohort(
            cohort=cohort,
            expected_cohort_ref=cohort.fingerprint,
            custody=snapshot.custody,
            input_status="unavailable",
            **arguments,
        )
        gross = project_kis_paper_portfolio_pnl(**arguments)
    row = next((row for row in gross.owners if row.owner_ref == cohort.owner_ref), None)
    bound = cadence.reason not in {
        "cohort_custody_mismatch",
        "entry_contract_mismatch",
        "exit_contract_mismatch",
        "exclusive_instrument_conflict",
    }
    complete = bound and row is not None and not row.reasons
    fee_status, fees = _fees(cohort, snapshot, complete)
    if not complete:
        return KisPaperFiveSessionPnlPoint(
            "incomplete" if bound else "unavailable",
            "unavailable",
            fee_status,
            cadence.status,
            retained_quantity=None
            if cadence.owned_quantity is None
            else Fraction(cadence.owned_quantity),
            positive_fill_count=0 if row is None else row.positive_fill_count,
            pending_intent_count=0 if row is None else row.pending_intent_count,
        )
    value = (
        Fraction(0)
        if row.quantity == 0
        else (None if mark is None else row.quantity * Fraction(mark.price_usd))
    )
    unrealized = None if value is None else value - row.remaining_entry_cost_usd
    total = None if unrealized is None else row.gross_realized_usd + unrealized
    return KisPaperFiveSessionPnlPoint(
        "complete",
        "mark_missing" if value is None else "complete",
        fee_status,
        cadence.status,
        row.chronology,
        row.quantity,
        row.gross_realized_usd,
        row.remaining_entry_cost_usd,
        value,
        unrealized,
        total,
        fees,
        None if total is None or fees is None else total - fees,
        row.positive_fill_count,
        row.pending_intent_count,
    )


def project_five_session_pnl(
    *,
    cohort: KisPaperFiveSessionCohort,
    expected_cohort_ref: str,
    expected_custody: KisPaperFiveSessionCustody,
    snapshot: KisPaperFiveSessionAccountingSnapshot,
    closes: tuple[KisPaperFiveSessionCloseInput, ...],
) -> KisPaperFiveSessionPnlProjection:
    """Project current gross accounting and five independently retained closes.

    A missing close snapshot is never reconstructed from current state. Earlier
    custody must be an ordered prefix of the caller's exact current custody.
    Each snapshot carries its own independently retained owner fingerprints.
    Valued closes require an explicitly close-bound logical snapshot as_of,
    not an older observation carried forward. Marks may be observed after the close,
    but never after current as_of; fees
    must already be observed by their own snapshot clock, never backcast.
    """
    if (
        type(cohort) is not KisPaperFiveSessionCohort
        or type(expected_custody) is not KisPaperFiveSessionCustody
        or type(snapshot) is not KisPaperFiveSessionAccountingSnapshot
        or type(closes) is not tuple
        or len(closes) != 5
        or any(type(slot) is not KisPaperFiveSessionCloseInput for slot in closes)
    ):
        raise ValueError("cohort_pnl_contract_invalid")
    cohort, expected_custody, snapshot = (
        replace(cohort),
        replace(expected_custody),
        replace(snapshot),
    )
    if expected_cohort_ref != cohort.fingerprint:
        raise ValueError("cohort_pnl_cohort_mismatch")
    _scope(cohort, snapshot, expected_custody, exact=True)
    results, previous = [], None
    for slot, closed in zip(closes, cohort.session_closes, strict=True):
        slot = replace(slot)
        if slot.close_at != closed:
            raise ValueError("cohort_pnl_close_clock_mismatch")
        mark = None if slot.mark is None else replace(slot.mark)
        if mark is not None and (
            mark.close_at != closed
            or mark.cohort_ref != cohort.fingerprint
            or mark.calendar_ref != cohort.calendar_ref
            or mark.instrument != cohort.instrument
            or mark.observed_at > snapshot.as_of
        ):
            raise ValueError("cohort_pnl_mark_binding_mismatch")
        if closed > snapshot.as_of:
            if slot.snapshot is not None or mark is not None:
                raise ValueError("cohort_pnl_future_close_facts")
            results.append(
                KisPaperFiveSessionPnlPoint("not_due", "not_due", "not_observed", "unknown")
            )
            continue
        if slot.snapshot is None:
            results.append(
                KisPaperFiveSessionPnlPoint("unavailable", "unavailable", "not_observed", "unknown")
            )
            continue
        retained = replace(slot.snapshot)
        if (
            retained.basis != snapshot.basis
            or retained.expected_basis_ref != snapshot.expected_basis_ref
        ):
            raise ValueError("cohort_pnl_basis_changed")
        _scope(cohort, retained, expected_custody)
        point = _point(cohort, retained, mark)
        known_refs = tuple(
            ref
            for ref in expected_custody.state_refs
            if snapshot.states[ref.run_id].intent.created_at <= closed
        )
        if retained.as_of != closed or retained.custody.state_refs != known_refs:
            results.append(
                KisPaperFiveSessionPnlPoint(
                    "unavailable",
                    "stale_snapshot" if retained.as_of != closed else "custody_incomplete",
                    "not_observed",
                    "unknown",
                )
            )
            continue
        if previous is not None:
            _advance(previous, retained)
        results.append(point)
        previous = retained
    if previous is not None:
        _advance(previous, snapshot)
    return KisPaperFiveSessionPnlProjection(_point(cohort, snapshot, None), tuple(results))
