"""Recovery-only frame and native terminal projection for the Dec4/9 Paper bank."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from thericher_v2.execution import net25_pending_reconciliation as native
from thericher_v2.execution import paper_peer_visit as bank
from thericher_v2.execution.paper_account_session import PaperAccountCohort
from thericher_v2.ops.h3_dec4_guest import _binding

_REF = re.compile(r"sha256:[0-9a-f]{64}")
_MAX_EVIDENCE = 1024 * 1024
_MAX_OUTCOME = 4096
_PENDING = {
    "unreserved_not_expired",
    "unsubmitted_not_expired",
    "exact_terminal_evidence_missing",
    "native_plan_still_pending",
}
_RECONCILED = {"never_reserved_retired", "exact_native_terminal_retained"}
_TERMINAL_REFS = (
    "plan_ref",
    "pending_ref",
    "before_journal_ref",
    "after_journal_ref",
    "book_ref",
    "evidence_ref",
)


@dataclass(frozen=True, slots=True, repr=False)
class Dec4RecoveryPins:
    original_cohort: PaperAccountCohort
    bank_key: str
    original_claim_sha256: str
    physical_receipt_sha256: str
    pending_ref: str
    account_ref: str
    effect_starts_at: datetime
    effect_ends_at: datetime


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _ref(value):
    return type(value) is str and _REF.fullmatch(value) is not None


def _utc(value):
    return type(value) is datetime and value.utcoffset() == timedelta(0)


def encode_dec4_recovery_guest(pins: Dec4RecoveryPins) -> bytes:
    """Canonical, payload-free frame. Pins must come from trusted host custody."""
    if (
        type(pins) is not Dec4RecoveryPins
        or type(pins.original_cohort) is not PaperAccountCohort
        or not all(
            bank._hash(p)
            for p in (
                pins.bank_key, pins.original_claim_sha256, pins.physical_receipt_sha256,
                pins.account_ref,
            )
        )
        or not _ref(pins.pending_ref)
        or not all(_utc(t) for t in (pins.effect_starts_at, pins.effect_ends_at))
    ):
        raise ValueError("h3_recovery_pins_invalid")
    original = pins.original_cohort
    original.validate()
    slot = original.slot
    _, exact = _binding(
        slot.phase, original.source_ref, original.basis_ref, slot.policy_ref, slot.input_ref[7:]
    )
    if (
        original != exact
        or not all(_utc(t) for t in (slot.starts_at, slot.ends_at))
        or pins.effect_starts_at < slot.ends_at
        or not timedelta(0) < pins.effect_ends_at - pins.effect_starts_at <= timedelta(minutes=5)
    ):
        raise ValueError("h3_recovery_scope_invalid")
    return bank.encode(dict(
        schema="dec4-net25-recovery-guest-v1",
        phase="recovery",
        original_cohort=dict(
            slot=slot.slot, phase=slot.phase, profile=original.profile.value,
            starts_at=slot.starts_at.isoformat(), ends_at=slot.ends_at.isoformat(),
            source_ref=original.source_ref, basis_ref=original.basis_ref,
            policy_ref=slot.policy_ref, input_ref=slot.input_ref,
        ),
        bank_key=pins.bank_key,
        original_claim_sha256=pins.original_claim_sha256,
        physical_receipt_sha256=pins.physical_receipt_sha256,
        pending_ref=pins.pending_ref,
        account_ref=pins.account_ref,
        effect_starts_at=pins.effect_starts_at.isoformat(),
        effect_ends_at=pins.effect_ends_at.isoformat(),
    )) + b"\n"


def _pinned_evidence(raw, digest):
    if type(raw) is not bytes or not 0 < len(raw) <= _MAX_EVIDENCE or _sha(raw) != digest:
        raise ValueError("h3_recovery_evidence_pin")
    return bank._decode(raw)


def parse_dec4_recovery_guest(
    packet: bytes, *, expected: Dec4RecoveryPins, original_claim: bytes, physical_receipt: bytes
) -> PaperAccountCohort:
    """Cross-bind exact retained buffers; this is not present-tense owner admission."""
    if type(packet) is not bytes or packet != encode_dec4_recovery_guest(expected):
        raise ValueError("h3_recovery_frame_invalid")
    try:
        claim = _pinned_evidence(original_claim, expected.original_claim_sha256)
        receipt = _pinned_evidence(physical_receipt, expected.physical_receipt_sha256)
        bank._record(claim, expected.bank_key)
        visit = claim["visits"][-1]
        create = visit["create"]
        closure = receipt["closure"]
        original = expected.original_cohort
        if (
            "sha256:" + claim["identity"]["source"] != original.source_ref
            or claim["identity"]["member"] != "stock-ingress"
            or visit["kind"] != "effect"
            or visit["status"] != "ACTIVE"
            or create["resolution"] != "ACK_EXACT_CID"
            or not bank._hash(closure["evidence_sha256"])
            or type(receipt["host_exit_code"]) is not int
            or receipt["host_disposition"] not in ("DEADLINE", "EXITED_WITH_MEMBERS")
            or not all(
                type(actor["native_start"]) is str
                and actor["native_start"].startswith("win-filetime:")
                and bank._start(actor["native_start"])
                for actor in (claim["owner"], *visit["children"])
            )
        ):
            raise ValueError("h3_recovery_evidence_unbound")
        if not bank._same(receipt, dict(
            schema="h3-dec4-physical-recovery-v1",
            original_claim_sha256=expected.original_claim_sha256,
            host_exit_code=receipt["host_exit_code"],
            host_disposition=receipt["host_disposition"],
            closure=dict(
                schema="paper-bank-visit-closure-v1", identity=claim["identity"],
                owner=claim["owner"], visit=visit["run"],
                record_sha256=expected.original_claim_sha256,
                children=[
                    {k: child[k] for k in ("token", "argv_sha256", "pid", "native_start")}
                    | {"closure": "EXACT_PROCESS_AND_JOB_JOINED"}
                    for child in visit["children"]
                ],
                create_resolution="ACK_EXACT_CID", container=create["cid"],
                container_status="EXACT_CONTAINER_ABSENT_AFTER_JOIN",
                evidence_sha256=closure["evidence_sha256"],
            ),
            same_native_intent_reconciliation_required=True,
            bank_claim_released=False,
            reservation_or_budget_release=False,
        )):
            raise ValueError("h3_recovery_evidence_unbound")
    except (bank.Denied, KeyError, IndexError, TypeError):
        raise ValueError("h3_recovery_evidence_unbound") from None

    # The native recovery ABI uses an exit-shaped slot for its effect clock.
    # The original phase and its clocks remain unchanged in the pinned frame.
    recovery = replace(original, mode="recovery", slot=replace(
        original.slot, phase="exit", starts_at=expected.effect_starts_at,
        ends_at=expected.effect_ends_at,
    ))
    recovery.validate()
    return recovery


def _outcome(expected, status, reason, gets, tokens, terminal):
    if (
        type(status) is not str
        or type(reason) is not str
        or not (
            (status == "pending" and reason in _PENDING)
            or (status == "reconciled" and reason in _RECONCILED)
        )
        or type(gets) is not int or not 0 <= gets <= 32
        or type(tokens) is not int or not 0 <= tokens <= 1
    ):
        raise ValueError("h3_recovery_outcome_unconfirmed")
    if terminal is not None and (
        status != "reconciled"
        or type(terminal) is not dict
        or terminal.keys() != {*_TERMINAL_REFS, "evidence_kind"}
        or not all(_ref(terminal[k]) for k in _TERMINAL_REFS)
        or terminal["pending_ref"] != expected.pending_ref
        or terminal["before_journal_ref"] == terminal["after_journal_ref"]
        or terminal["evidence_kind"] not in ("broker_terminal_retained", "presubmit_proven")
        or (reason == "never_reserved_retired" and terminal["evidence_kind"] != "presubmit_proven")
    ):
        raise ValueError("h3_recovery_outcome_unconfirmed")
    return dict(
        schema="dec4-net25-recovery-outcome-v1",
        frame_sha256=_sha(encode_dec4_recovery_guest(expected)),
        status=status, reason=reason, get_attempts=gets, token_attempts=tokens,
        terminal=terminal,
        bank_claim_released=False,
        reservation_release=False,
        financial_claim="UNKNOWN",
    )


def run_dec4_recovery_guest(
    packet: bytes, *, expected: Dec4RecoveryPins, original_claim: bytes, physical_receipt: bytes,
    paths, owner_ready, clock, make_credentials_and_transport, persist_prepared,
) -> bytes:
    """Run one native reconciliation call; return a canonical terminal line or raise.

    No direct file/network/credential I/O or target loader. The source-pinned
    caller supplies native custody paths and a lazy, Paper-only transport
    factory. Its owner_ready(pins) must reprove the exact current gate, source,
    original claim, physical receipt and writer/observer admission (e.g. over
    the existing OwnerChannel). persist_prepared(proof) must durably retain the
    exact proof under these same pins before returning, or raise. The caller
    owns the hard process deadline.
    """
    cohort = parse_dec4_recovery_guest(
        packet, expected=expected, original_claim=original_claim, physical_receipt=physical_receipt
    )
    if not all(
        callable(f) for f in (owner_ready, clock, make_credentials_and_transport, persist_prepared)
    ):
        raise ValueError("h3_recovery_callbacks_invalid")
    paths = dict(paths)

    def check_window():
        try:
            now = clock()
            if _utc(now) and expected.effect_starts_at <= now < expected.effect_ends_at:
                return
        except Exception:
            pass
        raise ValueError("h3_recovery_window_closed")

    def admit():
        check_window()
        try:
            ready = owner_ready(expected)
        except Exception:
            raise ValueError("h3_recovery_owner_denied") from None
        if ready is not True:
            raise ValueError("h3_recovery_owner_denied")
        check_window()
        return True

    supplied = False

    def make_once(instrument):
        nonlocal supplied
        if supplied:
            raise ValueError("h3_recovery_transport_already_supplied")
        admit()
        supplied = True
        return make_credentials_and_transport(instrument)

    prepared = None

    def prepare(proof):
        nonlocal prepared
        if prepared is not None:
            raise ValueError("h3_recovery_duplicate_prepared")
        terminal = _terminal_payload(proof)
        _outcome(expected, "reconciled", "exact_native_terminal_retained", 0, 0, terminal)
        admit()
        persist_prepared(proof)
        prepared = proof

    admit()
    try:
        result = native.reconcile_net25_pending_request(
            cohort=cohort, paths=paths, account_ref=expected.account_ref,
            expected_pending_ref=expected.pending_ref, admissible=admit, clock=clock,
            make_credentials_and_transport=make_once, persist_prepared=prepare,
        )
    except Exception:
        # Native failure may follow custody or wire effects; do not emit an outcome.
        raise ValueError("h3_recovery_native_unconfirmed") from None
    admit()
    if type(result) is not native.Net25PendingOutcome:
        raise ValueError("h3_recovery_outcome_unconfirmed")
    proof = result.terminal
    if (proof is not None and type(proof) is not native.Net25TerminalProof) or proof != prepared:
        raise ValueError("h3_recovery_outcome_unconfirmed")
    terminal = None if proof is None else _terminal_payload(proof)
    outcome = _outcome(
        expected, result.status, result.reason, result.get_attempts, result.token_attempts, terminal
    )
    if proof is not None:
        try:
            checked = native.verify_net25_reconciled_terminal(
                paths, expected.account_ref, cohort, proof, clock=clock, admitted=admit
            )
        except Exception:
            raise ValueError("h3_recovery_terminal_readback_unconfirmed") from None
        if type(checked) is not native.Net25TerminalProof or checked != proof:
            raise ValueError("h3_recovery_terminal_readback_unconfirmed")
    return bank.encode(outcome) + b"\n"


def _terminal_payload(proof):
    if type(proof) is not native.Net25TerminalProof:
        raise ValueError("h3_recovery_outcome_unconfirmed")
    return {k: getattr(proof, k) for k in (*_TERMINAL_REFS, "evidence_kind")}


def verify_dec4_recovery_outcome(
    stdout: bytes, retained: bytes, *, exit_code: int, expected: Dec4RecoveryPins
) -> dict:
    """Verify exact transport and projection, not OS closure or bank-release authority."""
    if (
        type(exit_code) is not int or exit_code != 0
        or type(stdout) is not bytes or not 1 < len(stdout) <= _MAX_OUTCOME
        or type(retained) is not bytes or retained != stdout
        or not stdout.endswith(b"\n")
    ):
        raise ValueError("h3_recovery_outcome_unconfirmed")
    try:
        value = bank._decode(stdout[:-1])
        exact = _outcome(
            expected, value["status"], value["reason"], value["get_attempts"],
            value["token_attempts"], value["terminal"],
        )
    except (bank.Denied, KeyError, TypeError):
        raise ValueError("h3_recovery_outcome_unconfirmed") from None
    if not bank._same(value, exact):
        raise ValueError("h3_recovery_outcome_unconfirmed")
    return exact
