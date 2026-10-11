"""One history-aware canonical Paper action through injected native adapters.

No model/config/client construction. Whole-book accounting is never replaced by
a cohort segment. The private journal is application custody, not broker proof.
Existing native reserve/execute/observe/cancel retain their locks and schemas.
"""

from __future__ import annotations

import copy
import hashlib
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import ROUND_FLOOR, Context, Decimal, localcontext
from pathlib import Path

from thericher_v2.contracts import TargetExposureProposal, require_utc
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    receipt_from_target_exposure_proposal,
)
from thericher_v2.research.five_session_paper_decision import FiveSessionPaperDecision

from . import kis_paper_budget_strategy as budget
from . import kis_paper_stock_exit_plan as exits
from . import kis_paper_stock_plan as entries
from .kis_paper_canary import (
    KisPaperCanaryReconciliation,
    KisPaperCanaryState,
    KisPaperCanaryStateStore,
    exclusive_kis_paper_canary_state_lock,
)
from .kis_paper_five_session import (
    KisPaperFiveSessionCohort,
    KisPaperFiveSessionCustody,
    cohort_from_paper_decision,
)
from .kis_paper_five_session_history_store import KisPaperFiveSessionHistoryStore
from .kis_paper_five_session_successor import (
    KisPaperFiveSessionHistory,
    _history_rows,
    _segment,
    prepare_five_session_successor,
)
from .kis_paper_portfolio_budget import KisPaperPortfolioStateRef
from .kis_paper_portfolio_plan import _replay_scope
from .kis_paper_stock_execute import KisPaperStockExecutionBinding
from .kis_paper_stock_execute import _scope as _canonical_execution_scope
from .kis_paper_stock_quote import KisPaperStockInstrument
from .kis_paper_stock_session_recovery import plan_stock_session_recovery


@dataclass(frozen=True, slots=True, repr=False)
class SessionClosePolicy:
    session_open: datetime
    session_close: datetime
    exit_start: datetime
    exit_proposal_ref: str


@dataclass(frozen=True, slots=True, repr=False)
class LifecycleScope:
    binding: Mapping
    states: Mapping[str, KisPaperCanaryState]
    state_root: Path
    account_ref: str
    basis_ref: str
    masked_account: str


@dataclass(frozen=True, slots=True, repr=False)
class LifecycleObservation:
    scope: LifecycleScope
    reads: object
    reconciliation: KisPaperCanaryReconciliation | None


@dataclass(frozen=True, slots=True, repr=False)
class LifecycleAdapters:
    load: Callable
    reads: Callable
    reserve: Callable
    execute: Callable
    observe: Callable
    cancel: Callable
    delivery: Callable


@dataclass(frozen=True, slots=True, repr=False)
class RetainedRuntimeMetadata:
    cohort: KisPaperFiveSessionCohort
    decision: FiveSessionPaperDecision | None
    policy: SessionClosePolicy


def load_retained_runtime_metadata(history_store, cohort_ref):
    """Load finite retained metadata before a fresh loader/native constructor.

    Retrospective bootstrap lacks a pre-effect DTO unless supplied separately by
    the caller's original immutable exchange; it is never invented here.
    """
    with history_store.locked():
        journal = history_store.read()
        history = journal.history if journal.pending is None else journal.pending["after"]
        cohort = next(h.cohort for h in history if h.cohort.fingerprint == cohort_ref)
        return RetainedRuntimeMetadata(
            cohort, journal.decisions.get(cohort_ref), horizon_policy(cohort)
        )


class _RuntimeError(ValueError):
    pass


def _check(ok, reason):
    if not ok:
        raise _RuntimeError(reason)


def horizon_policy(cohort: KisPaperFiveSessionCohort) -> SessionClosePolicy:
    return SessionClosePolicy(
        cohort.session_opens[0],
        cohort.session_closes[-1],
        cohort.exit_due,
        "ref:" + cohort.fingerprint[7:],
    )


def _proposal(dto, policy):
    """Original NativeAdapters constructor compatibility; finite DTOs only."""
    _check(type(dto) is FiveSessionPaperDecision, "input_unavailable")
    replace(dto)
    _check(dto.status == "prepared", "input_unavailable")
    _check(type(policy) is SessionClosePolicy, "input_unavailable")
    _check(
        (policy.session_open, policy.session_close, policy.exit_start)
        == (dto.first_open, dto.fifth_close, dto.fifth_close - timedelta(minutes=10)),
        "input_unavailable",
    )
    return (
        dto.proposal,
        dto.receipt,
        KisPaperStockInstrument(dto.proposal.symbol, dto.instrument_binding_ref),
    )


def _owner_refs(binding):
    return {o.owner_ref: pin for o, pin in budget._owners(binding)}


def _scope(value, *, account, basis, owners, at):
    _check(type(value) is LifecycleScope, "canonical_scope_unavailable")
    _check(value.account_ref == account and value.basis_ref == basis, "canonical_scope_unavailable")
    binding, states = copy.deepcopy(value.binding), copy.deepcopy(value.states)
    projection = budget.project_shared_budget(
        binding=binding,
        states=states,
        expected_account_ref=account,
        expected_basis_ref=basis,
        expected_owner_refs=owners,
        as_of=at,
    )
    return replace(value, binding=binding, states=states), projection


def _row(binding, instrument, request):
    entry = binding.get("stocks", {}).get(instrument.symbol)
    if entry is None:
        return None
    _check(entry["instrument_binding_ref"] == instrument.binding_ref, "history_scope_unavailable")
    matches = [r for r in entry["plans"] if r["request_id"] == request]
    _check(len(matches) <= 1, "history_scope_unavailable")
    return matches[0] if matches else None


def _arguments(
    scope, cohort, request, at, until, *, side, proposal=None, receipt=None, reads=None, row=None
):
    result = dict(
        expected_account_ref=scope.account_ref,
        expected_basis_ref=scope.basis_ref,
        expected_owner_refs=_owner_refs(scope.binding),
        expected_binding_ref=(
            row["parent_binding_ref"] if row else "sha256:" + budget._digest(scope.binding)
        ),
        request_id=request,
        input_ref=cohort.source_ref,
        instrument=cohort.instrument,
        proposal=proposal,
        receipt=receipt,
        reads=reads,
        as_of=at,
        valid_until=until,
    )
    if side == "sell":
        result["expected_masked_account"] = scope.masked_account
    return result


def _build(scope, side, arguments):
    function = (
        entries.build_kis_paper_stock_plan
        if side == "buy"
        else exits.build_kis_paper_stock_exit_plan
    )
    return function(binding=scope.binding, states=scope.states, **arguments)


def _seed(row):
    _check(row is not None and len(row["states"]) == 1, "reservation_unavailable")
    return KisPaperCanaryState.from_dict(next(iter(row["states"].values())))


def _proof(scope, cohort, plan, row):
    seed = _seed(row)
    _check(
        plan.status in {"reserved", "replayed"} and len(plan.intents) == 1,
        "reservation_unavailable",
    )
    _check(
        plan.intents[0] == seed.intent and plan.plan_ref == "sha256:" + budget._digest(row),
        "reservation_unavailable",
    )
    return KisPaperStockExecutionBinding(
        state_root=scope.state_root,
        instrument=cohort.instrument,
        account_ref=scope.account_ref,
        basis_ref=scope.basis_ref,
        owner_refs=tuple(_owner_refs(scope.binding).items()),
        binding_ref="sha256:" + budget._digest(scope.binding),
        request_id=row["request_id"],
        parent_binding_ref=row["parent_binding_ref"],
        input_ref=row["input_ref"],
        plan_ref=plan.plan_ref,
        run_id=seed.intent.run_id,
        intent_ref=seed.intent.fingerprint,
        side=seed.intent.side,
    )


def _exit_proposal(cohort, request, at, until):
    ref = "ref:" + hashlib.sha256((cohort.fingerprint + request).encode()).hexdigest()
    proposal = TargetExposureProposal(
        proposal_id=ref,
        symbol=cohort.instrument.symbol,
        market="US",
        action="exit",
        target_exposure=Decimal(0),
        confidence=Decimal(0),
        feature_schema_id="kis_stock_five_session_owned_exit_v1",
        input_status="ready",
        decided_at=at,
        valid_until=until,
        feature_window_end=None,
        reason="frozen_fifth_session_owned_exit",
    )
    receipt = receipt_from_target_exposure_proposal(
        proposal,
        references=DecisionReceiptReferences(
            "ref:" + cohort.fingerprint[7:], "ref:" + cohort.fingerprint[7:], cohort.source_ref, ref
        ),
    )
    return proposal, receipt


def _transition(history, after, side, arguments, plan, cohort, decision=None):
    row = _row(plan.binding, cohort.instrument, arguments["request_id"])
    return dict(
        before=history,
        after=after,
        side=side,
        arguments=arguments,
        row=row,
        plan_ref=plan.plan_ref,
        decision=decision,
    )


def _expire_unsubmitted(proof, history_store, clock):
    """Persist only exact no-attempt expiry using canonical locks/state/replay.

    Original NativeAdapters.observe refuses intent_recorded, including expired
    seeds. This local transition has no client/order endpoint and never renews
    TTL; an attempted or filled state cannot enter it.
    """
    root = proof.state_root
    with exclusive_kis_paper_canary_state_lock(root / ".session_execution"):
        with exclusive_kis_paper_canary_state_lock(root / ".canary_execution"):
            at = clock()
            _, _, state, _ = _canonical_execution_scope(root, proof, at)
            _check(
                state.phase == "intent_recorded"
                and state.submission_started_at is None
                and state.submitted_at is None
                and state.cumulative_fill is None
                and at >= state.intent.valid_until,
                "reservation_unavailable",
            )
            store = KisPaperCanaryStateStore(root / (proof.run_id + ".json"))
            store.record_intent(state.intent, cancel_after_submit=False, now=at)
            store.transition(
                state.intent,
                expected=frozenset({"intent_recorded"}),
                phase="intent_recorded",
                reason_code="intent_expired",
                now=at,
            )
    reconcile = (
        entries.reconcile_kis_paper_stock_plan
        if proof.side == "buy"
        else exits.reconcile_kis_paper_stock_exit_plan
    )
    reconcile(
        state_root=root,
        repository_root=history_store.repository_root,
        artifact_root=history_store.artifact_root,
        expected_account_ref=proof.account_ref,
        expected_basis_ref=proof.basis_ref,
        expected_owner_refs=dict(proof.owner_refs),
        expected_binding_ref=proof.parent_binding_ref,
        request_id=proof.request_id,
        input_ref=proof.input_ref,
        instrument=proof.instrument,
        expected_plan_ref=proof.plan_ref,
        as_of=clock(),
    )


def run_five_session_runtime(
    decision: FiveSessionPaperDecision | None,
    *,
    cohort: KisPaperFiveSessionCohort,
    expected_cohort_ref: str,
    history_store: KisPaperFiveSessionHistoryStore,
    history: tuple[KisPaperFiveSessionHistory, ...] = (),
    expected_history_refs: tuple[str, ...] = (),
    expected_account_ref: str,
    expected_basis_ref: str,
    expected_owner_refs: Mapping[str, str],
    adapters: LifecycleAdapters | None,
    phase: str,
    clock: Callable[[], datetime],
    deadline: float,
    execute: bool = False,
    adapter_factory: Callable[[RetainedRuntimeMetadata], LifecycleAdapters] | None = None,
) -> dict[str, object]:
    """Dispatch at most one exact submit/cancel; retained custody precedes input.

    ``history`` and its pins bootstrap the private journal once. Subsequent
    append-only journal transitions extend that independently supplied history.
    Current all-owner pins are caller-frozen, not inferred from observed states.
    A retained native adapter must be constructed from retained finite metadata
    before a fresh loader is consulted (its original constructor requires a DTO).
    This API itself does not invoke a loader or instantiate any native adapter.
    """
    result = dict(
        kind="kis_paper_five_session_runtime_v1",
        status="inert",
        reason="default_inert",
        action="none",
        execute_calls=0,
        cancel_calls=0,
        observe_calls=0,
        reservation_calls=0,
        local_expiry_calls=0,
        history_records=0,
        outcome_unknown=None,
        owned_current_flat=None,
    )
    if execute is not True:
        return result
    last_at = None

    def now():
        nonlocal last_at
        _check(time.monotonic() < deadline, "deadline_elapsed")
        at = require_utc(clock())
        _check(last_at is None or at >= last_at, "clock_unavailable")
        last_at = at
        return at

    try:
        with localcontext(Context(prec=64, rounding=ROUND_FLOOR)):
            _check(
                type(cohort) is KisPaperFiveSessionCohort
                and cohort.fingerprint == expected_cohort_ref,
                "history_scope_unavailable",
            )
            replace(cohort)
            _check(phase in {"enter", "close", "recover"}, "phase_unavailable")
            _check(type(adapters) is LifecycleAdapters, "canonical_scope_unavailable")
            _check(
                type(history) is tuple
                and type(expected_history_refs) is tuple
                and tuple(h.fingerprint for h in history) == expected_history_refs,
                "history_scope_unavailable",
            )
            at = now()
            scope, _ = _scope(
                adapters.load(),
                account=expected_account_ref,
                basis=expected_basis_ref,
                owners=expected_owner_refs,
                at=at,
            )
            _check(adapters.delivery(scope) is True, "delivery_unavailable")
            initial_root = scope.state_root
            anchor = dict(
                account_ref=expected_account_ref,
                basis_ref=expected_basis_ref,
                instrument=cohort.instrument,
                bootstrap_refs=expected_history_refs,
            )
            with history_store.locked():
                journal = history_store.bootstrap(anchor, history)
                result["history_records"] = journal.record_count
                active, selected, row, plan = cohort, None, None, None

                def select_adapters(selected_cohort):
                    nonlocal adapters
                    if adapter_factory is None:
                        return
                    retained = journal.decisions.get(selected_cohort.fingerprint)
                    if retained is None and decision is not None:
                        candidate = cohort_from_paper_decision(
                            decision, calendar_ref=selected_cohort.calendar_ref
                        )
                        if candidate == selected_cohort:
                            retained = decision
                    adapters = adapter_factory(
                        RetainedRuntimeMetadata(
                            selected_cohort, retained, horizon_policy(selected_cohort)
                        )
                    )
                    _check(type(adapters) is LifecycleAdapters, "canonical_scope_unavailable")
                    checked, _ = _scope(
                        adapters.load(),
                        account=expected_account_ref,
                        basis=expected_basis_ref,
                        owners=expected_owner_refs,
                        at=now(),
                    )
                    _check(
                        checked.state_root == initial_root
                        and checked.binding == scope.binding
                        and checked.states == scope.states,
                        "canonical_scope_unavailable",
                    )

                if journal.pending is not None:
                    # Crash before reserve or after reserve/before journal commit:
                    # restore exactly the old arguments/seed, never renew its TTL.
                    staged = journal.pending
                    selected = next(
                        h
                        for h in staged["after"]
                        if h.cohort.entry_request_id == staged["arguments"]["request_id"]
                        or any(r.run_id in staged["row"]["states"] for r in h.custody.exits)
                    )
                    active = selected.cohort
                    select_adapters(active)
                    row = _row(scope.binding, active.instrument, staged["arguments"]["request_id"])
                    if row is None:
                        _history_rows(
                            scope.binding,
                            cohort,
                            journal.history,
                            tuple(h.fingerprint for h in journal.history),
                        )
                        staged_seed = _seed(staged["row"])
                        if at >= staged_seed.intent.valid_until:
                            _check(
                                staged_seed.intent.run_id not in scope.states,
                                "reservation_unavailable",
                            )
                            # No uncommitted seed can execute through this API.
                            # Exact full history and absent canonical row/state
                            # are application custody, not broker/OS no-wire proof.
                            journal = history_store.abort_unreserved(
                                journal.head_ref,
                                binding_ref="sha256:" + budget._digest(scope.binding),
                                as_of=at,
                            )
                            result.update(
                                status="no_intent",
                                reason="unreserved_seed_expired",
                                history_records=journal.record_count,
                            )
                            return result
                        result["reservation_calls"] += 1
                        plan = adapters.reserve(staged["side"], copy.deepcopy(staged["arguments"]))
                    else:
                        _check(row == staged["row"], "reservation_unavailable")
                        arguments = _arguments(
                            scope, active, row["request_id"], at, at, side=staged["side"], row=row
                        )
                        plan = _build(scope, staged["side"], arguments)
                else:
                    _history_rows(
                        scope.binding,
                        cohort,
                        journal.history,
                        tuple(h.fingerprint for h in journal.history),
                    )
                    prepared = prepare_five_session_successor(
                        cohort=cohort,
                        expected_cohort_ref=expected_cohort_ref,
                        history=journal.history,
                        expected_history_refs=tuple(h.fingerprint for h in journal.history),
                        binding=scope.binding,
                        states=scope.states,
                        expected_account_ref=expected_account_ref,
                        expected_basis_ref=expected_basis_ref,
                        expected_owner_refs=expected_owner_refs,
                        expected_binding_ref="sha256:" + budget._digest(scope.binding),
                        input_ref=cohort.source_ref,
                        as_of=at,
                        closure_as_of=None,
                    )
                    _check(
                        prepared.reason
                        not in {
                            "canonical_custody_invalid",
                            "typed_input_invalid",
                        }
                        and prepared.projection is not None,
                        "history_scope_unavailable",
                    )
                    if prepared.pending_cohort is not None:
                        active = prepared.pending_cohort
                    elif prepared.reason == "prior_terminal_evidence_missing":
                        active = next(
                            h.cohort
                            for h in journal.history
                            if any(
                                r.run_id not in scope.binding["terminal_evidence"]
                                for r in h.custody.state_refs
                            )
                        )
                    selected = next((h for h in journal.history if h.cohort == active), None)
                    select_adapters(active)
                    if selected is not None:
                        replayed, proofs = _replay_scope(scope.binding, scope.states)
                        quantity, pending = _segment(selected, replayed, proofs)
                        if pending is not None:
                            row = next(
                                r
                                for r in scope.binding["stocks"][active.instrument.symbol]["plans"]
                                if pending.run_id in r["states"]
                            )
                        elif quantity:
                            if at < active.exit_due or phase == "enter":
                                result.update(status="hold", reason="before_fifth_exit")
                                return result
                            _check(selected == journal.history[-1], "history_scope_unavailable")
                            request = (
                                "five-exit-"
                                + active.fingerprint[7:]
                                + f"-{len(selected.custody.exits)}"
                            )
                            until = at + budget._ORDER_LIFETIME
                            if at < active.session_closes[-1]:
                                until = min(until, active.session_closes[-1])
                            proposal, receipt = _exit_proposal(active, request, at, until)
                            reads = adapters.reads("sell", active.instrument, now)
                            at = now()
                            arguments = _arguments(
                                scope,
                                active,
                                request,
                                at,
                                until,
                                side="sell",
                                proposal=proposal,
                                receipt=receipt,
                                reads=reads,
                            )
                            plan = _build(scope, "sell", arguments)
                            _check(
                                plan.status == "prepared"
                                and len(plan.intents) == 1
                                and plan.intents[0].quantity == quantity,
                                "owned_exit_unavailable",
                            )
                            reference = KisPaperPortfolioStateRef(
                                plan.intents[0].run_id, plan.intents[0].fingerprint
                            )
                            updated = replace(
                                selected,
                                custody=KisPaperFiveSessionCustody(
                                    selected.custody.entry, (*selected.custody.exits, reference)
                                ),
                                plan_refs=(*selected.plan_refs, plan.plan_ref),
                            )
                            staged = _transition(
                                journal.history,
                                (*journal.history[:-1], updated),
                                "sell",
                                arguments,
                                plan,
                                active,
                            )
                            journal = history_store.prepare(staged)
                            result["reservation_calls"] += 1
                            plan = adapters.reserve("sell", copy.deepcopy(arguments))
                        else:
                            if prepared.reason == "prior_terminal_evidence_missing":
                                missing = next(
                                    r
                                    for r in selected.custody.state_refs
                                    if r.run_id not in scope.binding["terminal_evidence"]
                                )
                                row = next(
                                    r
                                    for r in scope.binding["stocks"][active.instrument.symbol][
                                        "plans"
                                    ]
                                    if missing.run_id in r["states"]
                                )
                            else:
                                result.update(
                                    status="complete",
                                    reason="canonical_segment_closed",
                                    owned_current_flat=None,
                                )
                                return result
                    else:
                        if phase != "enter":
                            result.update(status="no_intent", reason="entry_not_requested")
                            return result
                        if at < cohort.session_opens[0] or at >= cohort.entry_window_end:
                            result.update(status="no_intent", reason="entry_window_unavailable")
                            return result
                        proposal, receipt, instrument = _proposal(decision, horizon_policy(cohort))
                        _check(
                            instrument == cohort.instrument
                            and cohort_from_paper_decision(
                                decision, calendar_ref=cohort.calendar_ref
                            )
                            == cohort,
                            "input_unavailable",
                        )
                        reads = adapters.reads("buy", instrument, now)
                        at = now()
                        until = min(cohort.entry_window_end, at + budget._ORDER_LIFETIME)
                        prepared = prepare_five_session_successor(
                            cohort=cohort,
                            expected_cohort_ref=expected_cohort_ref,
                            history=journal.history,
                            expected_history_refs=tuple(h.fingerprint for h in journal.history),
                            binding=scope.binding,
                            states=scope.states,
                            expected_account_ref=expected_account_ref,
                            expected_basis_ref=expected_basis_ref,
                            expected_owner_refs=expected_owner_refs,
                            expected_binding_ref="sha256:" + budget._digest(scope.binding),
                            input_ref=cohort.source_ref,
                            as_of=at,
                            closure_as_of=reads.completed_at,
                            proposal=proposal,
                            receipt=receipt,
                            reads=reads,
                            valid_until=until,
                        )
                        _check(prepared.status == "prepared", "entry_preparation_unavailable")
                        arguments = _arguments(
                            scope,
                            cohort,
                            cohort.entry_request_id,
                            at,
                            until,
                            side="buy",
                            proposal=proposal,
                            receipt=receipt,
                            reads=reads,
                        )
                        staged = _transition(
                            journal.history,
                            prepared.history,
                            "buy",
                            arguments,
                            prepared.plan,
                            cohort,
                            decision,
                        )
                        journal = history_store.prepare(staged)
                        result["reservation_calls"] += 1
                        plan = adapters.reserve("buy", copy.deepcopy(arguments))
                    if row is not None:
                        side = _seed(row).intent.side
                        arguments = _arguments(
                            scope, active, row["request_id"], at, at, side=side, row=row
                        )
                        plan = _build(scope, side, arguments)

                # Check canonical custody, then durably commit before any observe
                # (which may cancel) or execute. No success-return assumption.
                at = now()
                current = adapters.load()
                _check(current.state_root == initial_root, "canonical_scope_unavailable")
                owners = (
                    _owner_refs(plan.binding)
                    if journal.pending is not None
                    else expected_owner_refs
                )
                scope, projection = _scope(
                    current,
                    account=expected_account_ref,
                    basis=expected_basis_ref,
                    owners=owners,
                    at=at,
                )
                request = (
                    journal.pending["row"]["request_id"]
                    if journal.pending is not None
                    else row["request_id"]
                )
                row = _row(scope.binding, active.instrument, request)
                if journal.pending is not None:
                    _check(
                        row == journal.pending["row"]
                        and plan.plan_ref == journal.pending["plan_ref"],
                        "reservation_unavailable",
                    )
                    _history_rows(
                        scope.binding,
                        cohort,
                        journal.pending["after"],
                        tuple(h.fingerprint for h in journal.pending["after"]),
                    )
                    journal = history_store.commit(journal.head_ref)
                _history_rows(
                    scope.binding,
                    cohort,
                    journal.history,
                    tuple(h.fingerprint for h in journal.history),
                )
                result["history_records"] = journal.record_count
                proof = _proof(scope, active, plan, row)
                seed = _seed(row)
                state = scope.states[seed.intent.run_id]
                observation = None

                def observe():
                    nonlocal scope, projection, state, observation
                    now()
                    result["observe_calls"] += 1
                    observation = adapters.observe(proof, now)
                    _check(type(observation) is LifecycleObservation, "canonical_scope_unavailable")
                    _check(
                        observation.scope.state_root == initial_root, "canonical_scope_unavailable"
                    )
                    scope, projection = _scope(
                        observation.scope,
                        account=expected_account_ref,
                        basis=expected_basis_ref,
                        owners=dict(proof.owner_refs),
                        at=now(),
                    )
                    _history_rows(
                        scope.binding,
                        cohort,
                        journal.history,
                        tuple(h.fingerprint for h in journal.history),
                    )
                    state = scope.states[seed.intent.run_id]

                def route():
                    # Native confirmed_cancel_state must use this same call-time
                    # max(close, original TTL) horizon for late EXIT type proof.
                    # Neither this nor the bridge renews the original TTL.
                    return plan_stock_session_recovery(
                        proof=proof,
                        seed=seed,
                        state=state,
                        session_open=active.session_opens[0],
                        session_close=max(active.session_closes[-1], seed.intent.valid_until),
                        as_of=now(),
                        projection=projection,
                        reads=None if observation is None else observation.reads,
                        reconciliation=None if observation is None else observation.reconciliation,
                    )

                if state.phase != "intent_recorded":
                    observe()
                directive = route()
                result["action"] = directive.action
                if directive.action == "expired_unsubmitted":
                    result["local_expiry_calls"] += 1
                    _expire_unsubmitted(proof, history_store, now)
                    result.update(
                        status="no_intent", reason="original_ttl_elapsed", outcome_unknown=False
                    )
                    return result
                if directive.action == "submit_exact_seed":
                    now()
                    _check(adapters.delivery(scope) is True, "delivery_unavailable")
                    result["execute_calls"] += 1
                    result["outcome_unknown"] = True
                    adapters.execute(proof, now)
                    observe()
                    directive = route()
                elif directive.action == "cancel_exact_expired":
                    now()
                    _check(adapters.delivery(scope) is True, "delivery_unavailable")
                    result["cancel_calls"] += 1
                    result["outcome_unknown"] = True
                    adapters.cancel(directive, now)
                    observe()
                    directive = route()
                result.update(status="recovery", reason="exact_request_retained")
                if directive.action == "terminal_owned_flat":
                    result.update(
                        status="complete",
                        reason="exact_owned_flat",
                        owned_current_flat=True,
                        outcome_unknown=False,
                    )
                elif directive.action == "remaining_owned_exit" and now() < active.exit_due:
                    result.update(status="hold", reason="before_fifth_exit", outcome_unknown=False)
                elif directive.action == "expired_unsubmitted":
                    result.update(
                        status="no_intent", reason="original_ttl_elapsed", outcome_unknown=False
                    )
                else:
                    result["outcome_unknown"] = directive.action in {
                        "reconcile_unknown",
                        "reconcile_open",
                        "cancel_exact_expired",
                    }
                return result
    except _RuntimeError as error:
        result.update(status="recovery", reason=error.args[0])
    except Exception:
        # Native exceptions can contain account/order/provider bodies. Never
        # return str(error), or manufacture zero effects after an uncertain call.
        result.update(status="recovery", reason="runtime_input_unavailable")
    return result
