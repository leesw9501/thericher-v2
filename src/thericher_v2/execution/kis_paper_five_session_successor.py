"""Pure successor preparation over the unchanged complete canonical Paper book.

History pins and closure capture clocks are caller-attested input custody, not
broker finality or OS proofs. Segment facts serve cadence only: budget, cash and
reservations always replay the complete original binding. No I/O or SELL builder.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import ROUND_FLOOR, Context, DecimalException, localcontext
from fractions import Fraction

from thericher_v2.contracts import TargetExposureProposal, require_utc
from thericher_v2.research.decision_receipt import ResearchDecisionReceipt

from . import kis_paper_budget_strategy as budget
from .kis_paper_canary import KisPaperCanaryState
from .kis_paper_five_session import KisPaperFiveSessionCohort, KisPaperFiveSessionCustody
from .kis_paper_portfolio_budget import (
    KisPaperPortfolioBudgetError,
    KisPaperPortfolioBudgetProjection,
    KisPaperPortfolioStateRef,
)
from .kis_paper_portfolio_plan import _replay_scope
from .kis_paper_spy_fill_cycle import _RecoveryRequired
from .kis_paper_stock_plan import KisPaperStockPlan, build_kis_paper_stock_plan
from .kis_paper_stock_readonly import KisPaperStockPreviewReads

_HASH = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)


def _check(condition: bool, reason: str) -> None:
    if not condition:
        raise _HistoryError(reason)


class _HistoryError(ValueError):
    pass


@dataclass(frozen=True, slots=True, repr=False)
class KisPaperFiveSessionHistory:
    """Complete ordered custody and seed-plan pins frozen before broker effects."""

    cohort: KisPaperFiveSessionCohort
    custody: KisPaperFiveSessionCustody
    input_ref: str
    plan_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _check(type(self.cohort) is KisPaperFiveSessionCohort, "history_invalid")
        _check(type(self.custody) is KisPaperFiveSessionCustody, "history_invalid")
        replace(self.cohort)
        replace(self.custody)
        _check(
            self.custody.entry is not None
            and self.input_ref == self.cohort.source_ref
            and type(self.plan_refs) is tuple
            and len(self.plan_refs) == len(self.custody.state_refs)
            and all(type(p) is str and _HASH.fullmatch(p) for p in self.plan_refs),
            "history_invalid",
        )

    @property
    def fingerprint(self) -> str:
        return "sha256:" + budget._digest(
            [
                "kis_paper_five_session_history_v1",
                self.cohort.fingerprint,
                self.input_ref,
                [[r.run_id, r.intent_ref] for r in self.custody.state_refs],
                self.plan_refs,
            ]
        )


@dataclass(frozen=True, slots=True, repr=False)
class KisPaperFiveSessionSuccessor:
    """Projection is the full pre-plan book; plan.binding retains the new seed."""

    status: str
    reason: str
    history: tuple[KisPaperFiveSessionHistory, ...] = ()
    custody: KisPaperFiveSessionCustody = KisPaperFiveSessionCustody()
    pending: KisPaperPortfolioStateRef | None = None
    pending_cohort: KisPaperFiveSessionCohort | None = None
    plan: KisPaperStockPlan | None = None
    projection: KisPaperPortfolioBudgetProjection | None = None

    def safe_payload(self) -> dict[str, object]:
        return {
            "kind": "kis_paper_five_session_successor_v1",
            "status": self.status,
            "reason": self.reason,
            "cohort_count": len(self.history),
            "request_count": sum(len(h.custody.state_refs) for h in self.history),
            "pending_request_count": int(self.pending is not None),
            "scope": "pure_paper_preparation_not_submission_or_broker_proof",
        }


def _history_rows(binding, cohort, history, expected_refs):
    _check(type(history) is tuple and type(expected_refs) is tuple, "history_invalid")
    _check(len(history) == len(expected_refs), "history_binding_mismatch")
    entry = binding.get("stocks", {}).get(cohort.instrument.symbol)
    rows = [] if entry is None else entry["plans"]
    _check(
        entry is None or entry["instrument_binding_ref"] == cohort.instrument.binding_ref,
        "history_instrument_mismatch",
    )
    offset, previous, seen = 0, None, set()
    for item, pin in zip(history, expected_refs, strict=True):
        _check(type(item) is KisPaperFiveSessionHistory, "history_invalid")
        replace(item)
        _check(item.fingerprint == pin, "history_binding_mismatch")
        _check(item.cohort.instrument == cohort.instrument, "history_instrument_mismatch")
        _check(item.cohort.fingerprint not in seen, "history_duplicate_cohort")
        seen.add(item.cohort.fingerprint)
        _check(
            previous is None or previous.session_closes[-1] < item.cohort.session_opens[0],
            "history_order_mismatch",
        )
        previous = item.cohort
        for index, (reference, plan_ref) in enumerate(
            zip(item.custody.state_refs, item.plan_refs, strict=True)
        ):
            _check(offset < len(rows), "history_scope_mismatch")
            row = rows[offset]
            request = (
                item.cohort.entry_request_id
                if index == 0
                else "five-exit-"
                + item.cohort.fingerprint.removeprefix("sha256:")
                + f"-{index - 1}"
            )
            _check(
                row["request_id"] == request
                and row["input_ref"] == item.input_ref
                and tuple(row["states"]) == (reference.run_id,)
                and "sha256:" + budget._digest(row) == plan_ref,
                "history_plan_mismatch",
            )
            seed = KisPaperCanaryState.from_dict(row["states"][reference.run_id])
            _check(seed.intent.fingerprint == reference.intent_ref, "history_intent_mismatch")
            offset += 1
    _check(offset == len(rows), "history_scope_mismatch")
    _check(
        not history
        or history[-1].cohort == cohort
        or history[-1].cohort.session_closes[-1] < cohort.session_opens[0],
        "history_order_mismatch",
    )
    return rows


def _segment(item, states, proofs):
    # Quantity/pending facts only; no owner replacement or cash/cost replay.
    quantity, pending = Fraction(0), None
    for index, reference in enumerate(item.custody.state_refs):
        state = states[reference.run_id]
        intent = state.intent
        _check(intent.side == ("buy" if index == 0 else "sell"), "history_side_mismatch")
        if index == 0:
            _check(
                item.cohort.session_opens[0] <= intent.created_at < item.cohort.entry_window_end
                and intent.valid_until <= item.cohort.entry_window_end,
                "history_entry_clock_mismatch",
            )
        else:
            _check(intent.created_at >= item.cohort.exit_due, "history_exit_clock_mismatch")
            _check(pending is None, "history_exit_before_reconciliation")
            _check(Fraction(intent.quantity) <= quantity, "history_foreign_sale")
        fill = (
            Fraction(0)
            if state.cumulative_fill is None
            else Fraction(state.cumulative_fill.quantity)
        )
        quantity += fill if index == 0 else -fill
        if not budget._terminal(state, proofs.get(reference.run_id)) and pending is None:
            pending = reference
    return quantity, pending


def prepare_five_session_successor(
    *,
    cohort: KisPaperFiveSessionCohort,
    expected_cohort_ref: str,
    history: tuple[KisPaperFiveSessionHistory, ...],
    expected_history_refs: tuple[str, ...],
    binding: Mapping[str, object],
    states: Mapping[str, KisPaperCanaryState],
    expected_account_ref: str,
    expected_basis_ref: str,
    expected_owner_refs: Mapping[str, str],
    expected_binding_ref: str,
    input_ref: str,
    as_of: datetime,
    closure_as_of: datetime | None,
    proposal: TargetExposureProposal | None = None,
    receipt: ResearchDecisionReceipt | None = None,
    reads: KisPaperStockPreviewReads | None = None,
    valid_until: datetime | None = None,
) -> KisPaperFiveSessionSuccessor:
    """Prepare one fresh BUY, or recover the exact retained request without inputs.

    History includes every selected-stock cohort, including this cohort if its
    request was already retained. Expected history/owner pins are independently
    frozen by the caller, never regenerated here to forgive omission. A fresh
    closure clock binds the supplied read completion and covers all known
    selected-history updates; unchanged older fills need not be rewritten.
    Read freshness uses only size_kis_paper_stock_target's existing 120-second
    contract, not an additional successor clock limit. Empty history needs no
    prior-closure capture. Returned new history
    can be frozen before effects; nothing is persisted by this function.
    """
    projection = None
    try:
        with localcontext(Context(prec=64, rounding=ROUND_FLOOR)):
            _check(type(cohort) is KisPaperFiveSessionCohort, "cohort_invalid")
            replace(cohort)
            at = require_utc(as_of)
            _check(cohort.fingerprint == expected_cohort_ref, "cohort_binding_mismatch")
            _check(input_ref == cohort.source_ref, "cohort_input_mismatch")
            projection = budget.project_shared_budget(
                binding=binding,
                states=states,
                expected_account_ref=expected_account_ref,
                expected_basis_ref=expected_basis_ref,
                expected_owner_refs=expected_owner_refs,
                as_of=at,
            )
            rows = _history_rows(binding, cohort, history, expected_history_refs)
            replayed, proofs = _replay_scope(binding, states)
            current = history[-1] if history and history[-1].cohort == cohort else None
            prior = history[:-1] if current is not None else history
            for item in prior:
                quantity, pending = _segment(item, replayed, proofs)
                if pending is not None:
                    return KisPaperFiveSessionSuccessor(
                        "reconcile",
                        "prior_recovery_pending",
                        history,
                        pending=pending,
                        pending_cohort=item.cohort,
                        projection=projection,
                    )
                if quantity:
                    return KisPaperFiveSessionSuccessor(
                        "reconcile",
                        "prior_owned_quantity_remaining",
                        history,
                        pending_cohort=item.cohort,
                        projection=projection,
                    )
                if any(
                    r.run_id not in binding["terminal_evidence"] for r in item.custody.state_refs
                ):
                    return KisPaperFiveSessionSuccessor(
                        "reconcile",
                        "prior_terminal_evidence_missing",
                        history,
                        pending_cohort=item.cohort,
                        projection=projection,
                    )
            if current is not None:
                _, pending = _segment(current, replayed, proofs)
                row = rows[len(rows) - len(current.custody.state_refs)]
                plan = build_kis_paper_stock_plan(
                    binding=binding,
                    states=states,
                    expected_account_ref=expected_account_ref,
                    expected_basis_ref=expected_basis_ref,
                    expected_owner_refs=expected_owner_refs,
                    expected_binding_ref=row["parent_binding_ref"],
                    request_id=cohort.entry_request_id,
                    input_ref=input_ref,
                    instrument=cohort.instrument,
                    proposal=None,
                    receipt=None,
                    reads=None,
                    as_of=at,
                    valid_until=at,
                )
                return KisPaperFiveSessionSuccessor(
                    "reconcile" if pending is not None else "replayed",
                    "current_recovery_pending" if pending is not None else "exact_request_retained",
                    history,
                    current.custody,
                    pending,
                    cohort if pending is not None else None,
                    plan,
                    projection,
                )
            if at < cohort.session_opens[0]:
                return KisPaperFiveSessionSuccessor(
                    "deferred", "awaiting_first_open", history, projection=projection
                )
            if at >= cohort.entry_window_end:
                return KisPaperFiveSessionSuccessor(
                    "no_intent", "entry_window_elapsed", history, projection=projection
                )
            if proposal is None or receipt is None or reads is None:
                return KisPaperFiveSessionSuccessor(
                    "no_intent", "input_unavailable", history, projection=projection
                )
            if history:
                _check(
                    closure_as_of is not None
                    and require_utc(closure_as_of) == reads.completed_at <= at,
                    "closure_capture_unavailable",
                )
                _check(
                    all(
                        max(states[r.run_id].updated_at, replayed[r.run_id].updated_at)
                        <= closure_as_of
                        for h in history
                        for r in h.custody.state_refs
                    ),
                    "closure_capture_before_update",
                )
            _check(
                type(proposal) is TargetExposureProposal
                and type(receipt) is ResearchDecisionReceipt
                and receipt.decision_id == cohort.entry_decision_id
                and receipt.input_manifest_ref == input_ref
                and proposal.valid_until == cohort.entry_window_end,
                "cohort_proposal_mismatch",
            )
            plan = build_kis_paper_stock_plan(
                binding=binding,
                states=states,
                expected_account_ref=expected_account_ref,
                expected_basis_ref=expected_basis_ref,
                expected_owner_refs=expected_owner_refs,
                expected_binding_ref=expected_binding_ref,
                request_id=cohort.entry_request_id,
                input_ref=input_ref,
                instrument=cohort.instrument,
                proposal=proposal,
                receipt=receipt,
                reads=reads,
                as_of=at,
                valid_until=valid_until,
            )
            if plan.status != "prepared":
                return KisPaperFiveSessionSuccessor(
                    "no_intent",
                    "entry_sizing_unavailable",
                    history,
                    plan=plan,
                    projection=projection,
                )
            intent = plan.intents[0]
            custody = KisPaperFiveSessionCustody(
                KisPaperPortfolioStateRef(intent.run_id, intent.fingerprint)
            )
            retained = KisPaperFiveSessionHistory(cohort, custody, input_ref, (plan.plan_ref,))
            return KisPaperFiveSessionSuccessor(
                "prepared",
                "successor_plan_prepared",
                (*history, retained),
                custody,
                plan=plan,
                projection=projection,
            )
    except _HistoryError as error:
        reason = str(error)
    except (KisPaperPortfolioBudgetError, _RecoveryRequired):
        reason = "canonical_custody_invalid"
    except (ValueError, TypeError, AttributeError, KeyError, DecimalException):
        reason = "typed_input_invalid"
    return KisPaperFiveSessionSuccessor("no_intent", reason, projection=projection)
