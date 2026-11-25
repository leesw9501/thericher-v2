"""Reconcile one exact retained NET25 request without order-side effects."""

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from thericher_v2.execution import kis_paper_current_stock_cycle as core
from thericher_v2.execution import kis_readonly as readonly
from thericher_v2.execution.paper_account_session import PaperAccountCohort, _snapshot

_PROFILE = core.StockCycleProfile.MODEL_WEIGHTS_US_CASH_NET25_OPEN_ELAPSED3
_READ_PATHS = frozenset(e.path for e in readonly.KIS_PAPER_READ_ONLY_ENDPOINTS)
_PATHS = (
    "state_root",
    "repository_root",
    "artifact_root",
    "runtime_projection_path",
    "paper_account_snapshot_path",
    "emergency_state_path",
    "execution_control_path",
)


@dataclass(frozen=True, slots=True)
class Net25TerminalProof:
    plan_ref: str
    pending_ref: str
    before_journal_ref: str
    after_journal_ref: str
    book_ref: str
    evidence_ref: str
    evidence_kind: str

    def validate(self):
        for pin in (
            self.plan_ref,
            self.pending_ref,
            self.before_journal_ref,
            self.after_journal_ref,
            self.book_ref,
            self.evidence_ref,
        ):
            core._pin(pin)
        core._check(
            self.evidence_kind in {"broker_terminal_retained", "presubmit_proven"}
            and self.before_journal_ref != self.after_journal_ref,
            "cycle_request_changed",
        )


@dataclass(frozen=True, slots=True)
class Net25PendingOutcome:
    status: str
    reason: str
    get_attempts: int = 0
    token_attempts: int = 0
    terminal: Net25TerminalProof | None = None


class _ReadOnlyTransport:
    """Keep order wire authority out of this client, even on parser failure."""

    def __init__(self, transport, guard):
        self._transport = transport
        self._guard = guard
        self.get_attempts = self.token_attempts = 0

    def request(self, request):
        if type(request) is not readonly.KisHttpRequest:
            raise readonly.KisPaperReadOnlyError("request_not_allowlisted")
        path = urlparse(request.url).path
        # The common read-only validator also permits preview quote paths.
        if path not in _READ_PATHS and path != readonly.KIS_PAPER_TOKEN_PATH:
            raise readonly.KisPaperReadOnlyError("request_not_allowlisted")
        readonly.validate_kis_paper_readonly_request(request)
        self._guard()
        if request.method == "POST":
            if self.token_attempts:
                raise readonly.KisPaperReadOnlyError("token_request_not_due")
            self.token_attempts += 1
        else:
            if self.get_attempts >= 32:
                raise readonly.KisPaperReadOnlyError("request_not_allowlisted")
            self.get_attempts += 1
        return self._transport.request(request)


def reconcile_net25_pending_request(
    *,
    cohort,
    paths,
    account_ref,
    expected_pending_ref,
    admissible,
    clock,
    make_credentials_and_transport,
    persist_prepared=None,
):
    """Use the existing policy lock and native journal, never reserve or place an order.

    The caller must already own a reconciliation-only visit bound to the same
    original bank claim and physical closure. The callable supplies scoped
    Paper configuration and the existing paced, token-gated wire transport
    only if broker evidence is needed. The production caller must persist
    the exact prepared proof before the native journal advances. Its
    result is not account admission.
    """
    core._check(
        type(cohort) is PaperAccountCohort
        and cohort.profile is _PROFILE
        and cohort.mode == "recovery"
        and set(paths) == set(_PATHS)
        and (persist_prepared is None or callable(persist_prepared)),
        "cycle_configuration_invalid",
    )
    cohort.validate()
    core._pin(expected_pending_ref)
    core._check(
        type(account_ref) is str and re.fullmatch("[0-9a-f]{64}", account_ref) is not None,
        "cycle_account_changed",
    )

    def guard():
        now = readonly.require_utc(clock())
        core._check(cohort.slot.starts_at <= now < cohort.slot.ends_at, "outside_declared_session")
        core._check(admissible() is True, "cycle_configuration_invalid")
        now = readonly.require_utc(clock())
        core._check(cohort.slot.starts_at <= now < cohort.slot.ends_at, "outside_declared_session")
        return now

    guard()
    paths = {k: Path(v) for k, v in paths.items()}
    for path in paths.values():
        core._unlinked(path)
    root = paths["state_root"].resolve()
    paths["state_root"] = root
    core.budget._validate_paths(*(paths[k] for k in _PATHS))
    policy = cohort.slot.policy_ref
    pointer = root / core.model_paper_pointer(policy)
    lock = root / (".model_paper_nas_" + policy[7:])
    for path in (pointer, lock.with_name("." + lock.name + ".lock")):
        core._unlinked(path)
    with core.canary.exclusive_kis_paper_canary_state_lock(lock):
        with core._shared(root):
            at = guard()
            binding, record, _, _ = _snapshot(paths, account_ref, cohort)
            pending = None if record is None else record["pending"]
            core._check(
                pending is not None
                and "sha256:" + core.budget._digest(pending) == expected_pending_ref,
                "cycle_request_changed",
            )
            args = core._unpack(pending["arguments"])
            plans = binding.get("stocks", {}).get(pending["symbol"], {}).get("plans", [])
            reserved = any(p["request_id"] == args["request_id"] for p in plans)
            proof = seed = state = None
            if reserved:
                proof, seed = core._proof(root, binding, pending)
                _, _, state, _ = core.execution._scope(root, proof, at)
        if not reserved:
            guard()
            if core._retire_never_reserved(root, record, guard, pointer):
                return Net25PendingOutcome("reconciled", "never_reserved_retired")
            return Net25PendingOutcome("pending", "unreserved_not_expired")

        wire = None
        observation = None
        core._check(state.intent == seed.intent, "cycle_request_changed")
        with core._shared(root):
            at = guard()
            _, _, state, _ = core.execution._scope(root, proof, at)
            store = core.canary.KisPaperCanaryStateStore(root / (proof.run_id + ".json"))
            if state.phase == "intent_recorded" and not core.budget._terminal(state):
                if at < state.intent.valid_until:
                    return Net25PendingOutcome("pending", "unsubmitted_not_expired")
                core._check(
                    state.submission_started_at is None
                    and state.submitted_at is None
                    and state.broker_order_id is None
                    and state.cumulative_fill is None,
                    "cycle_request_changed",
                )
                store.record_intent(seed.intent, cancel_after_submit=False, now=at)
                state = store.transition(
                    seed.intent,
                    expected=frozenset({"intent_recorded"}),
                    phase="intent_recorded",
                    reason_code="intent_expired",
                    now=at,
                )
            elif not core.budget._terminal(state):
                guard()
                config, transport = make_credentials_and_transport(proof.instrument)
                wire = _ReadOnlyTransport(transport, guard)
                core._check(type(config) is readonly.KisPaperConfig, "cycle_client_invalid")
                client = core.KisPaperStockCanaryClient(
                    config=config,
                    transport=wire,
                    instrument=proof.instrument,
                )
                core.execution._client_account(client, proof)
                rec = client.reconcile(state, now=guard())
                at = guard()
                if rec.account_status == "available" and rec.execution is not None:
                    state = core.canary._record_reconciliation_fill(
                        store, state, rec, observed_at=at
                    )
                    observation = rec.execution

        gets, posts = (0, 0) if wire is None else (wire.get_attempts, wire.token_attempts)
        if not core.budget._terminal(state, observation):
            return Net25PendingOutcome("pending", "exact_terminal_evidence_missing", gets, posts)
        reconcile = (
            core.entries.reconcile_kis_paper_stock_plan
            if proof.side == "buy"
            else core.exits.reconcile_kis_paper_stock_exit_plan
        )
        result = reconcile(
            **{k: paths[k] for k in ("state_root", "repository_root", "artifact_root")},
            expected_account_ref=proof.account_ref,
            expected_basis_ref=proof.basis_ref,
            expected_owner_refs=dict(proof.owner_refs),
            expected_binding_ref=proof.parent_binding_ref,
            input_ref=proof.input_ref,
            instrument=proof.instrument,
            request_id=proof.request_id,
            expected_plan_ref=proof.plan_ref,
            as_of=guard(),
            cancellation_proofs={} if observation is None else {proof.run_id: observation},
        )
        if result.status != "reconciled":
            return Net25PendingOutcome("pending", "native_plan_still_pending", gets, posts)
        guard()
        suffix = "sha256:"
        book = core._book(root, account_ref, cohort.basis_ref)
        evidence = book["terminal_evidence"].get(proof.run_id)
        core._check(type(evidence) is dict, "cycle_request_changed")
        before_ref = record["ref"]
        if proof.side == "buy":
            record["active"]["entries_done"].append(pending["symbol"])
        record["pending"] = None
        final_ref = suffix + core.budget._digest({k: v for k, v in record.items() if k != "ref"})
        terminal = Net25TerminalProof(
            plan_ref=proof.plan_ref,
            pending_ref=expected_pending_ref,
            before_journal_ref=before_ref,
            after_journal_ref=final_ref,
            book_ref=suffix + core.budget._digest(book),
            evidence_ref=suffix + core.budget._digest(evidence),
            evidence_kind=(
                "presubmit_proven"
                if state.phase == "intent_recorded"
                else "broker_terminal_retained"
            ),
        )
        terminal.validate()
        if persist_prepared is not None:
            persist_prepared(terminal)
        guard()
        core._save(pointer, record)
        core._check(record["ref"] == final_ref, "cycle_checkpoint_invalid")
        return Net25PendingOutcome(
            "reconciled", "exact_native_terminal_retained", gets, posts, terminal
        )


def verify_net25_reconciled_terminal(paths, account_ref, cohort, terminal, *, clock, admitted):
    """Re-read the committed exact native terminal; no wire, locks or writes."""
    core._check(
        type(terminal) is Net25TerminalProof
        and type(cohort) is PaperAccountCohort
        and cohort.profile is _PROFILE
        and cohort.mode == "recovery"
        and set(paths) == set(_PATHS),
        "cycle_configuration_invalid",
    )
    terminal.validate()
    cohort.validate()
    core._check(admitted() is True, "cycle_configuration_invalid")
    paths = {k: Path(v) for k, v in paths.items()}
    for path in paths.values():
        core._unlinked(path)
    core.budget._validate_paths(*(paths[k] for k in _PATHS))
    root = paths["state_root"]
    pointer = root / core.model_paper_pointer(cohort.slot.policy_ref)
    core._unlinked(pointer)
    before = _snapshot(paths, account_ref, cohort)
    book, record, _, _ = before
    core._check(
        record is not None
        and record["pending"] is None
        and record["ref"] == terminal.after_journal_ref
        and "sha256:" + core.budget._digest(book) == terminal.book_ref,
        "cycle_checkpoint_invalid",
    )
    plans = [
        plan
        for stock in book.get("stocks", {}).values()
        for plan in stock["plans"]
        if "sha256:" + core.budget._digest(plan) == terminal.plan_ref
        and plan["input_ref"] == cohort.slot.input_ref
    ]
    core._check(len(plans) == 1 and len(plans[0]["states"]) == 1, "cycle_request_changed")
    (run_id,) = plans[0]["states"]
    evidence = book["terminal_evidence"].get(run_id)
    core._check(
        type(evidence) is dict
        and "sha256:" + core.budget._digest(evidence) == terminal.evidence_ref,
        "cycle_request_changed",
    )
    state = core.canary.KisPaperCanaryState.from_dict(evidence["state"])
    core._check(
        terminal.evidence_kind
        == ("presubmit_proven" if state.phase == "intent_recorded" else "broker_terminal_retained"),
        "cycle_request_changed",
    )
    core._projection(root, book, readonly.require_utc(clock()))
    core._check(
        _snapshot(paths, account_ref, cohort) == before and admitted() is True,
        "cycle_checkpoint_invalid",
    )
    return terminal
