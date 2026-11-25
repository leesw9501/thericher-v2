"""Hand an already joined Dec4 recovery visit to the existing bank finalizer."""

import os
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from thericher_v2.execution import paper_peer_visit as pv
from thericher_v2.execution.net25_pending_reconciliation import Net25TerminalProof
from thericher_v2.ops.h3_dec4_crash_recovery import _terminated
from thericher_v2.ops.h3_dec4_recovery_finalize import _sha, finalize_dec4_reconciled_leg
from thericher_v2.ops.h3_dec4_recovery_guest import (
    Dec4RecoveryPins,
    encode_dec4_recovery_guest,
    parse_dec4_recovery_guest,
    verify_dec4_recovery_outcome,
)
from thericher_v2.ops.h3_dec4_watchdog import HostJobResult

_MAX_EVIDENCE = 1024 * 1024


@dataclass(frozen=True, slots=True, repr=False)
class Dec4RecoveryJoinPins:
    """Prelaunch pins plus separate acknowledged-record and joined-receipt pins."""

    identity_sha256: str
    worker_sha256: str
    spec_sha256: str
    visit: str
    attach_argv_sha256: str
    recovery_record_sha256: str
    joined_sha256: str


def _joined(
    expected, pins, host, recovery_record, joined_receipt, stdout, retained, prepared,
):
    pv._need(
        type(pins) is Dec4RecoveryJoinPins
        and all(pv._hash(p) for p in (
            pins.identity_sha256, pins.worker_sha256, pins.spec_sha256,
            pins.attach_argv_sha256, pins.recovery_record_sha256, pins.joined_sha256,
        ))
        and pv._run(pins.visit)
        and type(host) is HostJobResult
        and host.disposition == "EXITED"
        and type(host.exit_code) is int and host.exit_code == 0
        and type(host.pid) is int and host.pid > 0
        and pv._start(host.native_start) and host.native_start.startswith("win-filetime:")
        and all(type(raw) is bytes and 0 < len(raw) <= _MAX_EVIDENCE
                for raw in (recovery_record, joined_receipt))
        and _sha(recovery_record) == pins.recovery_record_sha256
        and _sha(joined_receipt) == pins.joined_sha256,
        "h3_handoff_join_pin",
    )
    receipt = pv._decode(joined_receipt)
    record = pv._decode(recovery_record)
    pv._record(record, expected.bank_key)
    pv._need(
        pv.digest(record["identity"]) == pins.identity_sha256
        and record["owner"] == {"pid": host.pid, "native_start": host.native_start}
        and len(record["visits"]) == 1
        and type(receipt) is dict
        and type(receipt.get("closure")) is dict,
        "h3_handoff_join_identity",
    )
    (visit,) = record["visits"]
    create = visit["create"]
    children = visit["children"]
    attached = [child for child in children if child["argv_sha256"] == pins.attach_argv_sha256]
    pv._need(
        visit["run"] == pins.visit and visit["status"] == "ACTIVE" and visit["kind"] == "recovery"
        and create["resolution"] == "ACK_EXACT_CID" and create["spec_sha256"] == pins.spec_sha256
        and len(attached) == 1 and attached[0]["status"] == "RUNNING_OR_UNKNOWN"
        and all(pv._start(c["native_start"]) and c["native_start"].startswith("win-filetime:")
                for c in children)
        and pv._hash(receipt["closure"].get("evidence_sha256")),
        "h3_handoff_join_visit",
    )
    attach_exit = receipt.get("attach_exit_code")
    outcome = verify_dec4_recovery_outcome(
        stdout, retained, exit_code=attach_exit, expected=expected
    )
    pv._need(
        outcome["status"] == "reconciled" and outcome["terminal"] is not None,
        "h3_handoff_terminal_missing",
    )
    proof = Net25TerminalProof(**outcome["terminal"])
    proof.validate()
    pv._need(
        type(prepared) is Net25TerminalProof and proof == prepared,
        "h3_handoff_prepared_mismatch",
    )
    closure = dict(
        schema="paper-bank-visit-closure-v1", identity=record["identity"], owner=record["owner"],
        visit=pins.visit, record_sha256=pins.recovery_record_sha256,
        children=[
            {k: c[k] for k in ("token", "argv_sha256", "pid", "native_start")}
            | {"closure": "EXACT_PROCESS_AND_JOB_JOINED"}
            for c in children
        ],
        create_resolution="ACK_EXACT_CID", container=create["cid"],
        container_status="EXACT_CONTAINER_ABSENT_AFTER_JOIN",
        evidence_sha256=receipt["closure"]["evidence_sha256"],
    )
    pv._need(
        pv._same(receipt, dict(
            schema="h3-dec4-joined-recovery-visit-v1",
            recovery_source_sha256=record["identity"]["source"],
            worker_sha256=pins.worker_sha256,
            original_claim_sha256=expected.original_claim_sha256,
            physical_sha256=expected.physical_receipt_sha256,
            frame_sha256=outcome["frame_sha256"],
            outcome_sha256=_sha(retained),
            host=dict(pid=host.pid, native_start=host.native_start, exit_code=host.exit_code,
                      disposition=host.disposition),
            attach_exit_code=attach_exit,
            order_posts=0,
            closure=closure,
        )),
        "h3_handoff_join_unconfirmed",
    )
    return record, outcome["terminal"]


def _publish(path, raw, unchanged):
    pv.ordinary(path)
    if path.exists():
        pv._need(pv._read(path)[0] == raw, "h3_handoff_native_conflict")
    else:
        staged = path.with_name("NATIVE-RECONCILED-STAGE-" + uuid4().hex + ".tmp")
        staged_snapshot = pv._new(staged, raw)
        unchanged()
        pv._need(pv._read(staged) == staged_snapshot, "h3_handoff_stage_changed")
        pv.ordinary(path)
        pv._need(not path.exists(), "h3_handoff_native_conflict")
        # Same-directory publication; Windows rename refuses an existing target.
        # On POSIX only a publisher holding this same Gate may write the name.
        (os.rename if os.name == "nt" else os.replace)(staged, path)
    pv._need(pv._read(path)[0] == raw, "h3_handoff_native_changed")
    unchanged()


def handoff_dec4_joined_recovery(
    root, *, bank, identity, expected: Dec4RecoveryPins, join_pins: Dec4RecoveryJoinPins,
    host: HostJobResult, recovery_record: bytes, joined_receipt: bytes, stdout: bytes,
    retained: bytes, prepared: Net25TerminalProof, verify_native,
) -> dict:
    """Publish exact joined evidence once and invoke the actual existing finalizer.

    The source-qualified supervisor must supply its live, exact Job result,
    the exact visit record with its acknowledged create and all spawned
    children captured independently of the receipt, and the positive
    daemon/child closure and no-order evidence in its independently retained
    joined receipt. Neither the pins nor retained stdout may come from
    guest-writable evidence alone. The caller keeps those bytes and the
    prepared proof in stable custody and supplies a separate source-qualified
    native read-only verifier. This function starts nothing, does not grant
    effect admission, and does not hold the Gate across finalizer acquisition.
    Interrupted staging files have no authority and are never adopted.

    supervise_host() alone does not emit this receipt or prove daemon closure.
    """
    key = pv.bank_key(bank)
    pv._identity(identity, key)
    pv._need(
        type(expected) is Dec4RecoveryPins and expected.bank_key == key
        and callable(verify_native),
        "h3_handoff_scope",
    )
    identity = pv._decode(pv.encode(identity))
    recovery, terminal = _joined(
        expected, join_pins, host, recovery_record, joined_receipt, stdout, retained, prepared
    )
    run = identity["run"]
    gate_root = Path(root) / ("bank-" + key)
    pv._need(gate_root.is_dir(), "h3_handoff_bank_missing")
    active = gate_root / "ACTIVE-LEG.json"
    physical = gate_root / ("PHYSICAL-CLOSED-" + run + ".json")
    native = gate_root / ("NATIVE-RECONCILED-" + run + ".json")
    with pv.Gate(gate_root) as gate:
        active_snapshot, physical_snapshot = pv._read(active), pv._read(physical)
        parse_dec4_recovery_guest(
            encode_dec4_recovery_guest(expected), expected=expected,
            original_claim=active_snapshot[0], physical_receipt=physical_snapshot[0],
        )
        original = pv._decode(active_snapshot[0])
        aborted = original["visits"][-1]
        visit = recovery["visits"][0]
        originals = {(a["pid"], a["native_start"]) for a in (
            original["owner"], *aborted["children"]
        )}
        actors = (recovery["owner"], *visit["children"])
        recovery_actors = {(a["pid"], a["native_start"]) for a in actors}
        pv._need(
            pv._same(original["identity"], identity)
            and recovery["identity"]["run"] != run
            and len(recovery_actors) == len(actors) and not originals & recovery_actors
            and all(v["run"] != visit["run"] for v in original["visits"])
            and visit["create"]["cid"] != aborted["create"]["cid"],
            "h3_handoff_original_mismatch",
        )
        for actor in actors:
            _terminated(pv.process_start, actor)

        def unchanged():
            gate.check()
            pv._need(
                pv._read(active) == active_snapshot and pv._read(physical) == physical_snapshot,
                "h3_handoff_original_changed",
            )

        raw = pv.encode(dict(
            schema="h3-dec4-native-reconciled-v1",
            source=identity["source"],
            original_claim_sha256=expected.original_claim_sha256,
            physical_sha256=expected.physical_receipt_sha256,
            joined_recovery_visit_sha256=join_pins.joined_sha256,
            order_posts=0,
            terminal=terminal,
        ))
        unchanged()
        _publish(native, raw, unchanged)

    recovery_sha256 = _sha(raw)
    result = finalize_dec4_reconciled_leg(
        root, bank=bank, identity=identity, physical_sha256=expected.physical_receipt_sha256,
        recovery_sha256=recovery_sha256, expected_pending_ref=expected.pending_ref,
        verify_native=verify_native,
    )
    return result | {"recovery_sha256": recovery_sha256}
