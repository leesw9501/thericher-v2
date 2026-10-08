"""Pure owner-local average-cost gross PnL from retained KIS Paper fills.

The native budget replay validates custody and amounts first. Its rounded
outputs are not used. Average-cost attribution requires owner-local opposite-
side blocks to be serialized: every earlier block's final amount observation
must precede or equal the next opposite-side intent's creation (a stricter
boundary than submission start). Same-side order totals may overlap. A full
requested-quantity fill is quantity-final; a phase name alone is not proof.
Observation times are not execution timestamps, so a late re-read can exclude
a correctly ordered history. An entirely known, closed-flat owner's total
SELL-BUY cashflow is sequence-independent, but gives no per-sale attribution.
Pending/conflicting amounts otherwise yield incomplete, never zero profit.

This is historical supplied-scope accounting, not current broker inventory,
FIFO/tax basis, fees, settlement, net PnL, or an execution permission check.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Context, localcontext
from fractions import Fraction

from .kis_paper_canary import KisPaperCanaryState
from .kis_paper_fill_accounting import KisPaperExecutionObservation
from .kis_paper_portfolio_budget import (
    KisPaperPortfolioBudgetBasis,
    KisPaperPortfolioOwnerBinding,
    project_kis_paper_portfolio_budget,
)

_REASONS = frozenset({"pending_amounts", "fill_conflict", "ambiguous_fill_chronology"})
_CONFLICTS = frozenset({"ambiguous", "identity_mismatch", "fields_invalid", "conflict"})
_CHRONOLOGY = frozenset({"serialized_opposite_side_blocks", "closed_flat_cashflow", "unavailable"})
_ZERO = Fraction(0)


@dataclass(frozen=True, repr=False)
class KisPaperOwnerGrossPnl:
    owner_ref: str
    reasons: tuple[str, ...]
    intent_count: int
    positive_fill_count: int
    sell_fill_count: int
    pending_intent_count: int
    chronology: str
    quantity: Fraction | None
    buy_gross_usd: Fraction | None
    sell_gross_usd: Fraction | None
    remaining_entry_cost_usd: Fraction | None
    gross_realized_usd: Fraction | None

    def __post_init__(self) -> None:
        counts = (
            self.intent_count,
            self.positive_fill_count,
            self.sell_fill_count,
            self.pending_intent_count,
        )
        if (
            type(self.reasons) is not tuple
            or any(reason not in _REASONS for reason in self.reasons)
            or self.reasons != tuple(sorted(set(self.reasons)))
            or any(type(count) is not int or count < 0 for count in counts)
            or not self.sell_fill_count <= self.positive_fill_count <= self.intent_count
            or self.pending_intent_count > self.intent_count
        ):
            raise ValueError("owner_pnl_facts_invalid")
        if self.chronology not in _CHRONOLOGY or bool(self.reasons) != (
            self.chronology == "unavailable"
        ):
            raise ValueError("owner_pnl_chronology_invalid")
        values = (
            self.quantity,
            self.buy_gross_usd,
            self.sell_gross_usd,
            self.remaining_entry_cost_usd,
            self.gross_realized_usd,
        )
        if self.reasons:
            if any(value is not None for value in values):
                raise ValueError("incomplete_owner_pnl_has_amounts")
        elif (
            any(type(value) is not Fraction for value in values)
            or any(value < 0 for value in values[:-1])
            or self.pending_intent_count
            or self.gross_realized_usd
            != self.sell_gross_usd - self.buy_gross_usd + self.remaining_entry_cost_usd
            or (not self.sell_fill_count and self.gross_realized_usd != 0)
            or (
                self.chronology == "closed_flat_cashflow"
                and (
                    self.quantity != 0
                    or self.remaining_entry_cost_usd != 0
                    or self.sell_fill_count == 0
                )
            )
        ):
            raise ValueError("owner_pnl_identity_invalid")

    @property
    def status(self) -> str:
        if self.reasons:
            return "incomplete"
        return "gross_realized_observed" if self.sell_fill_count else "no_realized_fills"


@dataclass(frozen=True, repr=False)
class KisPaperPortfolioPnlProjection:
    owners: tuple[KisPaperOwnerGrossPnl, ...]
    allocated_usd: Fraction
    gross_cash_usd: Fraction | None
    remaining_entry_cost_usd: Fraction | None
    gross_realized_usd: Fraction | None

    def __post_init__(self) -> None:
        if (
            type(self.owners) is not tuple
            or any(type(owner) is not KisPaperOwnerGrossPnl for owner in self.owners)
            or type(self.allocated_usd) is not Fraction
            or self.allocated_usd <= 0
        ):
            raise ValueError("portfolio_pnl_facts_invalid")
        values = (self.gross_cash_usd, self.remaining_entry_cost_usd, self.gross_realized_usd)
        if self.status == "incomplete":
            if any(value is not None for value in values):
                raise ValueError("incomplete_portfolio_pnl_has_amounts")
        elif (
            any(type(value) is not Fraction for value in values)
            or self.remaining_entry_cost_usd
            != sum((owner.remaining_entry_cost_usd for owner in self.owners), _ZERO)
            or self.gross_realized_usd
            != sum((owner.gross_realized_usd for owner in self.owners), _ZERO)
            or self.gross_cash_usd
            != self.allocated_usd
            + sum((owner.sell_gross_usd - owner.buy_gross_usd for owner in self.owners), _ZERO)
            or self.gross_cash_usd + self.remaining_entry_cost_usd - self.allocated_usd
            != self.gross_realized_usd
        ):
            raise ValueError("portfolio_pnl_identity_invalid")

    @property
    def status(self) -> str:
        if any(owner.reasons for owner in self.owners):
            return "incomplete"
        return (
            "gross_realized_observed"
            if any(owner.sell_fill_count for owner in self.owners)
            else "no_realized_fills"
        )

    def safe_payload(self) -> dict[str, object]:
        sign = "not_observed"
        if self.status == "gross_realized_observed":
            sign = (
                "positive"
                if self.gross_realized_usd > 0
                else "negative"
                if self.gross_realized_usd < 0
                else "zero"
            )
        return dict(
            kind="kis_paper_portfolio_gross_pnl_v1",
            source="kis_paper",
            status=self.status,
            reasons=sorted({reason for owner in self.owners for reason in owner.reasons}),
            owner_count=len(self.owners),
            incomplete_owner_count=sum(bool(owner.reasons) for owner in self.owners),
            serialized_owner_count=sum(
                owner.chronology == "serialized_opposite_side_blocks" for owner in self.owners
            ),
            flat_cashflow_owner_count=sum(
                owner.chronology == "closed_flat_cashflow" for owner in self.owners
            ),
            intent_count=sum(owner.intent_count for owner in self.owners),
            positive_fill_count=sum(owner.positive_fill_count for owner in self.owners),
            sell_fill_count=sum(owner.sell_fill_count for owner in self.owners),
            pending_intent_count=sum(owner.pending_intent_count for owner in self.owners),
            gross_pnl_sign=sign,
            accounting="owner_local_average_cost_or_closed_flat_gross_cashflow",
            chronology="owner_scoped_opposite_side_serialization_or_closed_flat_cashflow",
            fees="not_observed",
            settled_cash="not_observed",
            net_pnl="not_observed",
            limitation="retained_owned_fills_not_current_account_tax_basis_or_net_profit",
        )


def _amount_final(state: KisPaperCanaryState, proved_cancel: bool) -> bool:
    fill = state.cumulative_fill
    return (
        (fill is not None and fill.quantity == state.intent.quantity)
        or proved_cancel
        or (state.phase == "intent_recorded" and state.updated_at >= state.intent.valid_until)
        or (state.phase == "rejected" and state.submit_response_category == "provider_rejected")
    )


def project_kis_paper_portfolio_pnl(
    *,
    basis: KisPaperPortfolioBudgetBasis,
    expected_basis_ref: str,
    owners: tuple[KisPaperPortfolioOwnerBinding, ...],
    expected_owner_refs: Mapping[str, str],
    states: Mapping[str, KisPaperCanaryState],
    as_of: datetime,
    cancellation_proofs: Mapping[str, KisPaperExecutionObservation] | None = None,
) -> KisPaperPortfolioPnlProjection:
    """Validate one frozen scope and project exact average-cost realized gross.

    Incomplete owners have no numeric PnL/basis output; independently complete
    owners remain available. The aggregate sign is withheld if any owner is
    incomplete. Full retained fills survive later absent/unavailable reads, but
    conflicting reads do not support a realized sign. A closed-flat owner with
    all amounts final may report SELL-BUY without claiming sale-level average
    cost attribution. Budget conservation is not chronology proof. No I/O or
    state mutation.
    """
    # Bind the same supplied mapping entries for validation and arithmetic.
    supplied = dict(states) if isinstance(states, Mapping) else states
    refs = (
        dict(expected_owner_refs)
        if isinstance(expected_owner_refs, Mapping)
        else expected_owner_refs
    )
    proofs = (
        dict(cancellation_proofs)
        if isinstance(cancellation_proofs, Mapping)
        else cancellation_proofs
    )
    # Native validation includes rounded display values; isolate their context
    # from the caller's traps. Only exact Fraction inputs are used below.
    with localcontext(Context(prec=64)):
        project_kis_paper_portfolio_budget(
            basis=basis,
            expected_basis_ref=expected_basis_ref,
            owners=owners,
            expected_owner_refs=refs,
            states=supplied,
            as_of=as_of,
            cancellation_proofs=proofs,
        )
    proofs = {} if proofs is None else proofs
    rows = []
    for owner in owners:
        reasons = set()
        positive = sells = pending = 0
        quantity = cost = buys = proceeds = realized = _ZERO
        previous_side = None
        block_final_at = None
        serialized = True
        for reference in owner.state_refs:
            state = supplied[reference.run_id]
            if state.fill_observation_status in _CONFLICTS:
                reasons.add("fill_conflict")
            final = _amount_final(state, reference.run_id in proofs)
            if not final:
                reasons.add("pending_amounts")
                pending += 1
            fill = state.cumulative_fill
            if previous_side is not None and previous_side != state.intent.side:
                if block_final_at is not None and block_final_at > state.intent.created_at:
                    serialized = False
                block_final_at = None
            previous_side = state.intent.side
            if final:
                # Use the retained final fill's time, not a later unavailable
                # read; exact zero cancellation proof has its own bound time.
                final_at = fill.observed_at if fill is not None else state.updated_at
                block_final_at = (
                    final_at if block_final_at is None else max(block_final_at, final_at)
                )
            if fill is None or fill.quantity == 0:
                continue
            positive += 1
            filled, amount = Fraction(fill.quantity), Fraction(fill.gross_amount)
            if state.intent.side == "buy":
                quantity += filled
                cost += amount
                buys += amount
            else:
                released = cost * filled / quantity
                quantity -= filled
                cost -= released
                proceeds += amount
                realized += amount - released
                sells += 1
        # Flat total cashflow is independent of the ambiguous sequence, unlike
        # an open owner's realized/basis split. Never extend this to partial or
        # unknown amounts, and never expose per-sale attribution for this case.
        flat_cashflow = not reasons and quantity == 0 and sells > 0
        if not serialized and not flat_cashflow:
            reasons.add("ambiguous_fill_chronology")
        chronology = (
            "unavailable"
            if reasons
            else "closed_flat_cashflow"
            if flat_cashflow
            else "serialized_opposite_side_blocks"
        )
        amounts = (None,) * 5 if reasons else (quantity, buys, proceeds, cost, realized)
        rows.append(
            KisPaperOwnerGrossPnl(
                owner.owner_ref,
                tuple(sorted(reasons)),
                len(owner.state_refs),
                positive,
                sells,
                pending,
                chronology,
                *amounts,
            )
        )
    frozen_rows = tuple(rows)
    allocated = Fraction(basis.allocated_usd)
    if any(row.reasons for row in frozen_rows):
        return KisPaperPortfolioPnlProjection(frozen_rows, allocated, None, None, None)
    cash = allocated + sum((row.sell_gross_usd - row.buy_gross_usd for row in frozen_rows), _ZERO)
    cost = sum((row.remaining_entry_cost_usd for row in frozen_rows), _ZERO)
    realized = sum((row.gross_realized_usd for row in frozen_rows), _ZERO)
    return KisPaperPortfolioPnlProjection(frozen_rows, allocated, cash, cost, realized)
