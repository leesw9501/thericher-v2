"""Finalize only a positively reconciled, exact original Dec4 bank claim."""

import hashlib
from dataclasses import asdict
from pathlib import Path

from thericher_v2.execution import paper_peer_visit as pv
from thericher_v2.execution.net25_pending_reconciliation import Net25TerminalProof
from thericher_v2.ops.h3_dec4_crash_recovery import _terminated


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _read_pinned(path, pin):
    raw, signature = pv._read(path)
    pv._need(pv._hash(pin) and _sha(raw) == pin, "h3_recovery_receipt_changed")
    return pv._decode(raw), (raw, signature)


def finalize_dec4_reconciled_leg(
    root,
    *,
    bank,
    identity,
    physical_sha256,
    recovery_sha256,
    expected_pending_ref,
    verify_native,
):
    """Close only an exact physically-closed claim and completed recovery visit.

    The owned supervisor supplies independent receipt digests after its exact
    no-order child exited and joined. Its native verifier reads the same
    journal/book through a source-pinned read-only path; no live calls.
    Neither receipt grants new financial authority or releases reservations.
    """
    return _finalize(
        root,
        bank,
        identity,
        physical_sha256,
        recovery_sha256,
        expected_pending_ref,
        pv.process_start,
        verify_native,
    )


def _finalize(root, bank, identity, physical_sha, recovery_sha, pending_ref, probe, verify):
    key = pv.bank_key(bank)
    pv._identity(identity, key)
    run = identity["run"]
    gate_root = Path(root) / ("bank-" + key)
    pv._need(gate_root.is_dir(), "h3_recovery_claim_missing")
    active = gate_root / "ACTIVE-LEG.json"
    physical_path = gate_root / ("PHYSICAL-CLOSED-" + run + ".json")
    recovery_path = gate_root / ("NATIVE-RECONCILED-" + run + ".json")
    closed = gate_root / ("CLOSED-" + run + ".json")
    with pv.Gate(gate_root) as gate:
        original = pv._read(active)
        record = pv._decode(original[0])
        pv._record(record, key)
        pv._need(record["identity"] == identity, "h3_recovery_claim_changed")
        visit = record["visits"][-1] if record["visits"] else None
        pv._need(
            visit is not None
            and visit["status"] == "ACTIVE"
            and visit["kind"] == "effect"
            and visit["create"]["resolution"] == "ACK_EXACT_CID",
            "h3_recovery_visit_missing",
        )
        physical, physical_bytes = _read_pinned(physical_path, physical_sha)
        raw_hash = _sha(original[0])
        facts = physical.get("closure", {})
        pv._need(
            physical.get("schema") == "h3-dec4-physical-recovery-v1"
            and physical.get("original_claim_sha256") == raw_hash
            and physical.get("same_native_intent_reconciliation_required") is True
            and physical.get("bank_claim_released") is False
            and physical.get("reservation_or_budget_release") is False
            and facts.get("identity") == identity
            and facts.get("owner") == record["owner"]
            and facts.get("record_sha256") == pv.digest(record)
            and facts.get("visit") == visit["run"]
            and facts.get("create_resolution") == "ACK_EXACT_CID"
            and facts.get("container") == visit["create"]["cid"]
            and facts.get("container_status") == "EXACT_CONTAINER_ABSENT_AFTER_JOIN"
            and facts.get("children")
            == [
                {k: c[k] for k in ("token", "argv_sha256", "pid", "native_start")}
                | {"closure": "EXACT_PROCESS_AND_JOB_JOINED"}
                for c in visit["children"]
            ],
            "h3_recovery_physical_unconfirmed",
        )
        native, native_bytes = _read_pinned(recovery_path, recovery_sha)
        proof = Net25TerminalProof(**native["terminal"])
        proof.validate()
        pv._need(
            set(native)
            == {
                "schema",
                "source",
                "original_claim_sha256",
                "physical_sha256",
                "joined_recovery_visit_sha256",
                "order_posts",
                "terminal",
            }
            and native["schema"] == "h3-dec4-native-reconciled-v1"
            and native["source"] == identity["source"]
            and native["original_claim_sha256"] == raw_hash
            and native["physical_sha256"] == physical_sha
            and pv._hash(native["joined_recovery_visit_sha256"])
            and type(native["order_posts"]) is int
            and native["order_posts"] == 0
            and proof.pending_ref == pending_ref,
            "h3_recovery_native_unconfirmed",
        )

        def unchanged():
            gate.check()
            pv._need(
                pv._read(active) == original
                and pv._read(physical_path) == physical_bytes
                and pv._read(recovery_path) == native_bytes,
                "h3_recovery_receipt_changed",
            )

        for child in (record["owner"], *visit["children"]):
            _terminated(probe, child)
        unchanged()
        result = verify(proof)
        pv._need(
            type(result) is Net25TerminalProof and result == proof, "h3_recovery_native_unconfirmed"
        )
        unchanged()
        for child in visit["children"]:
            child["status"] = "JOINED"
        visit.update(status="CLOSED", closure=pv.digest(facts))
        record["sequence"] += 1
        pv._record(record, key)
        terminal = pv.encode(
            dict(
                status="CLOSED_OPERATIONAL_ONLY",
                record=record,
                same_native_intent_reconciliation_required=True,
                reservation_or_budget_release=False,
                physical_recovery_sha256=physical_sha,
                native_recovery_sha256=recovery_sha,
                native_terminal=asdict(proof),
            )
        )
        pv.ordinary(closed)
        if closed.exists():
            pv._need(pv._read(closed)[0] == terminal, "h3_recovery_closed_conflict")
        else:
            pv._new(closed, terminal)
        unchanged()
        active.unlink()
        return {"status": "CLOSED_OPERATIONAL_ONLY", "reservation_or_budget_release": False}
