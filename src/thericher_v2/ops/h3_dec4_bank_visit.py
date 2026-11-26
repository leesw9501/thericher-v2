"""Finite Dec4/9 Windows owner to existing single-bank CapsuleVisit handoff."""

import hashlib
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from thericher_v2.execution.paper_peer_visit import BankLeg, Held, bank_key, ordinary
from thericher_v2.ops.h3_dec4_guest import DEC4_ROUND, encode_dec4_guest_visit
from thericher_v2.ops.h3_dec4_retained_input import (
    Dec4H3RetainedRef,
    publish_dec4_entry_reference,
    read_dec4_entry_reference,
    restore_dec4_h3_input,
)
from thericher_v2.ops.paper_scheduled_native import (
    NativeScheduledSource,
    run_native_scheduled_preflight,
)
from thericher_v2.ops.paper_startup import Phase
from thericher_v2.research.model_paper_weights import serialize_model_paper_weights_input

ROUND = DEC4_ROUND
TASKS = {
    "entry": "thericher-kis-paper-dec4-h3-entry-20261204-v1",
    "exit": "thericher-kis-paper-dec9-h3-owned-exit-20261209-v1",
}
_TIMES = {
    "entry": tuple(datetime(2026, 12, 4, 14, minute, tzinfo=UTC) for minute in (31, 35, 37)),
    "exit": tuple(datetime(2026, 12, 9, 14, minute, tzinfo=UTC) for minute in (30, 35, 37)),
}


def run_dec4_owned_bank_visit(
    evidence_root: Path,
    *,
    source: NativeScheduledSource,
    pin: str,
    release_pin: str,
    phase: Phase,
    make_owner: Callable,
    writer_and_observer_ready: Callable,
    prepare_phase_input: Callable,
    invoke_capsule_once: Callable | None = None,
    prepare_capsule_once: Callable | None = None,
    fixture_clock: Callable[[], datetime] | None = None,
) -> dict:
    """Own one finite leg, but leave quote/order/risk and closure to the native capsule.

    Source authentication precedes selection of the original bank/gate. Only a
    separately pinned launcher may supply the callbacks; no model can select a
    bank, path, credential loader, or broker. The capsule must use this exact
    BankLeg's durable Visit and re-run admission at its own effect boundaries.
    The native writer/observer guard is mandatory throughout, not a fallback.
    """
    if phase not in _TIMES or source.ROUND != ROUND:
        raise ValueError("h3_bank_round_mismatch")
    if (invoke_capsule_once is None) == (prepare_capsule_once is None):
        raise ValueError("h3_bank_capsule_binding")
    slot = source.SLOTS[phase]
    times = tuple(datetime.fromisoformat(slot[k]) for k in ("start_UTC", "end_UTC", "hard_UTC"))
    if (
        slot["name"] != TASKS[phase]
        or any(t.utcoffset() != timedelta(0) for t in times)
        or times != _TIMES[phase]
    ):
        raise ValueError("h3_bank_phase_mismatch")
    opens, closes, _ = times
    clock = fixture_clock or (lambda: datetime.now(UTC))
    if fixture_clock is not None and source.check(pin).get("synthetic_only") is not True:
        raise ValueError("h3_bank_fixture_mode")

    def check_time():
        now = clock()
        if now.utcoffset() != timedelta(0) or not opens <= now < closes:
            raise ValueError("h3_bank_window_closed")

    ready = run_native_scheduled_preflight(
        evidence_root,
        source=source,
        pin=pin,
        release_pin=release_pin,
        phase=phase,
        clock=clock,
        make_owner=make_owner,
    )
    if ready.source.get("synthetic_only", False) is not (fixture_clock is not None):
        raise ValueError("h3_bank_fixture_mode")
    bank = dict(ready.source["original_owner"]["bank"])
    key = bank_key(bank)
    root = Path(ready.source["original_gate_root"])
    ordinary(root)
    if not root.is_dir():
        raise ValueError("h3_bank_existing_gate_root_required")
    initial = ready.owner.prove()
    identity_fields = (
        "pid",
        "start_ticks",
        "argv_sha256",
        "schema",
        "status",
        "origin",
        "no_old_model_self_rows",
    )
    verified = ready.owner.expected | {k: initial.get(k) for k in identity_fields}
    if (initial.get("pid"), initial.get("status"), initial.get("no_old_model_self_rows")) != (
        os.getpid(),
        "PASS_STOCK_INGRESS_SCHEDULED_OWNER",
        True,
    ) or any(initial.get(k) != v for k, v in ready.owner.expected.items()):
        raise ValueError("h3_bank_owner_changed")
    identity = dict(
        source=pin,
        release=release_pin,
        group=pin,
        member="stock-ingress",
        run=uuid4().hex,
        argv_sha256=initial["argv_sha256"],
        bank=key,
    )
    leg = BankLeg(root, bank=bank, identity=identity)
    check_time()
    try:
        leg.__enter__()
    except Held:
        return {
            "status": "DEFER_SHARED_BANK_HELD",
            "native_visits": 0,
            "reservation_release": False,
        }

    stable_entry_reference = None

    def admit():
        leg.check(identity)
        check_time()
        current = ready.owner.prove()
        if any(current.get(k) != v for k, v in verified.items()):
            raise ValueError("h3_bank_owner_changed")
        if writer_and_observer_ready(leg, ready) is not True:
            raise ValueError("h3_bank_writer_admission_denied")
        if stable_entry_reference is not None:
            stable_entry_reference()
        leg.check(identity)
        check_time()
        return True

    invoked = False
    try:
        admit()
        basis = ready.source["original_basis_ref"]
        policy = ready.source["execution_policy_ref"]
        retained_path = Path(ready.source["retained_input_path"])
        if phase == "entry":
            retained = prepare_phase_input(ready, phase)
        else:
            retained, stable_entry_reference = read_dec4_entry_reference(
                leg,
                retained_path,
                basis=basis,
                policy=policy,
                synthetic=fixture_clock is not None,
            )
        if (
            type(retained) is not Dec4H3RetainedRef
            or retained.source_sha256 != pin
            or retained.policy_ref != policy
            or retained.path != retained_path
        ):
            raise ValueError("h3_bank_retained_binding_mismatch")
        value = restore_dec4_h3_input(retained, synthetic_fixture=fixture_clock is not None)
        payload = serialize_model_paper_weights_input(value) if phase == "entry" else None
        if payload is not None and hashlib.sha256(payload).hexdigest() != retained.payload_sha256:
            raise ValueError("h3_bank_retained_bytes_changed")
        if phase == "entry":
            stable_entry_reference = publish_dec4_entry_reference(leg, retained, basis=basis)
        frame = encode_dec4_guest_visit(
            phase=phase,
            source_ref="sha256:" + pin,
            basis_ref=basis,
            policy_ref=retained.policy_ref,
            payload_sha256=retained.payload_sha256,
            payload=payload,
        )
        if prepare_capsule_once is None:
            assert invoke_capsule_once is not None

            def dispatch():
                return invoke_capsule_once(leg, ready, frame, admit)
        else:
            # Stage exact source-owned files and the nonfinancial observer lease.
            # Credentials and daemon calls belong to the returned dispatch.
            dispatch = prepare_capsule_once(leg, ready, retained, frame, admit)
            if not callable(dispatch) or leg.record["visits"]:
                raise ValueError("h3_bank_capsule_binding")
        admit()
        invoked = True
        outcome = dispatch()
        visits = leg.record["visits"]
        if (
            type(outcome) is not dict
            or type(outcome.get("pending")) is not bool
            or len(visits) != 1
            or visits[0]["kind"] != "effect"
            or visits[0]["status"] != "CLOSED"
            or not visits[0]["children"]
            or any(child["status"] != "JOINED" for child in visits[0]["children"])
            or visits[0]["create"]["resolution"] not in {"ACK_EXACT_CID", "DISCOVERED_EXACT_SCOPE"}
        ):
            raise ValueError("h3_bank_positive_capsule_closure_required")
        leg.close()
        # Closing the physical visit never settles the native journal. A later
        # owner must still reconcile the retained identity before fresh effects.
        return {
            "status": "CLOSED_OPERATIONAL_FINANCIAL_PENDING"
            if outcome["pending"]
            else "CLOSED_OPERATIONAL_ONLY",
            "native_visits": 1,
            "financial_claim": "UNKNOWN",
            "reservation_release": False,
        }
    except Exception:
        # Before the capsule is invoked these callbacks cannot touch the broker.
        # Do not strand the shared bank on a verified pre-dispatch refusal.
        if not invoked and not leg.record["visits"]:
            leg.close()
        raise
    finally:
        leg.__exit__()
