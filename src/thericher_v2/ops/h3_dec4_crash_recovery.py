"""Recover an acknowledged Dec4 daemon visit without adopting financial state."""

import hashlib
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from thericher_v2.execution import paper_peer_visit as pv
from thericher_v2.ops.h3_dec4_capsule_adapter import _load_visit
from thericher_v2.ops.h3_dec4_watchdog import HostJobResult


def _terminated(process_probe, child):
    native = child["native_start"]
    if not pv._start(native) or not native.startswith("win-filetime:"):
        raise pv.Held("h3_recovery_child_birth_unknown")
    current = process_probe(child["pid"])
    if current is not None and (
        not pv._start(current) or not current.startswith("win-filetime:") or current == native
    ):
        raise pv.Held("h3_recovery_process_live_or_unknown")


def recover_dec4_aborted_leg(root, *, bank, identity, spec, host):
    """Close one exact physical visit after the original contained Job abort.

    Call only with the live supervisor's native result and the prebound
    original identity/spec. The container must be positively identified
    before removal. The active bank claim stays unchanged and prevents other
    writers from bypassing the pending financial reconciliation.
    """
    return _recover(root, bank, identity, spec, host, pv.process_start, _remove_exact)


def _remove_exact(bank, source_pin, spec, record, visit):
    capsule = _load_visit()(
        SimpleNamespace(
            bank=bank, source_pin=source_pin, writer_guard=SimpleNamespace(check=lambda *_: False)
        ),
        deepcopy(spec),
    )
    capsule.run = visit["run"]
    capsule.name = "thericher-single-owner-" + capsule.run
    capsule.labels["thericher.single_owner.visit"] = capsule.run
    try:
        # An empty listing could be a different daemon or interrupted cleanup.
        # Positive initial identity is required even when the create was ACKed.
        obj = capsule.inspect(visit["create"]["cid"])
        if obj is None:
            raise pv.Held("h3_recovery_original_container_not_observed")
        capsule.exact(obj)
        return capsule._close_probe(record)
    finally:
        for job in capsule.jobs:
            if job.joined:
                job.close_job()


def _recover(root, bank, identity, spec, host, process_probe, remove_exact):
    key = pv.bank_key(bank)
    pv._identity(identity, key)
    if (
        type(host) is not HostJobResult
        or host.disposition not in {"DEADLINE", "EXITED_WITH_MEMBERS"}
        or type(host.pid) is not int
        or host.pid <= 0
        or not pv._start(host.native_start)
        or not host.native_start.startswith("win-filetime:")
        or type(host.exit_code) is not int
        or type(spec) is not dict
        or spec.get("kind") != "effect"
        or spec.get("phase") not in {"entry", "exit"}
    ):
        raise pv.Held("h3_recovery_scope")
    gate_root = Path(root) / ("bank-" + key)
    active = gate_root / "ACTIVE-LEG.json"
    closed = gate_root / ("PHYSICAL-CLOSED-" + identity["run"] + ".json")
    if not gate_root.is_dir():
        raise pv.Held("h3_recovery_claim_missing")
    with pv.Gate(gate_root) as gate:
        pv.ordinary(closed)
        if closed.exists():
            raise pv.Held("h3_recovery_terminal_exists")
        raw, signature = pv._read(active)
        snapshot = raw, signature
        record = pv._decode(raw)
        pv._record(record, key)
        if record["identity"] != identity or record["owner"] != {
            "pid": host.pid,
            "native_start": host.native_start,
        }:
            raise pv.Held("h3_recovery_original_owner_mismatch")
        visits = record["visits"]
        if not visits or visits[-1]["status"] != "ACTIVE" or visits[-1]["kind"] != "effect":
            raise pv.Held("h3_recovery_visit_missing")
        visit = visits[-1]
        create = visit["create"]
        if create["resolution"] != "ACK_EXACT_CID" or create["spec_sha256"] != pv.digest(spec):
            raise pv.Held("h3_recovery_create_unknown")

        def still_owned():
            gate.check()
            if pv._read(active) != snapshot:
                raise pv.Held("h3_recovery_claim_changed")
            for child in (record["owner"], *visit["children"]):
                _terminated(process_probe, child)

        still_owned()
        result = remove_exact(bank, identity["source"], spec, deepcopy(record), deepcopy(visit))
        still_owned()
        children = [
            {k: c[k] for k in ("token", "argv_sha256", "pid", "native_start")}
            | {"closure": "EXACT_PROCESS_AND_JOB_JOINED"}
            for c in visit["children"]
        ]
        if not isinstance(result, dict) or not pv._hash(result.get("evidence_sha256")):
            raise pv.Held("h3_recovery_daemon_unconfirmed")
        expected = dict(
            schema="paper-bank-visit-closure-v1",
            identity=identity,
            owner=record["owner"],
            visit=visit["run"],
            record_sha256=pv.digest(record),
            children=children,
            create_resolution="ACK_EXACT_CID",
            container=create["cid"],
            container_status="EXACT_CONTAINER_ABSENT_AFTER_JOIN",
            evidence_sha256=result["evidence_sha256"],
        )
        if not pv._same(result, expected):
            raise pv.Held("h3_recovery_daemon_unconfirmed")
        original = hashlib.sha256(raw).hexdigest()
        receipt = dict(
            schema="h3-dec4-physical-recovery-v1",
            original_claim_sha256=original,
            host_exit_code=host.exit_code,
            host_disposition=host.disposition,
            closure=expected,
            same_native_intent_reconciliation_required=True,
            bank_claim_released=False,
            reservation_or_budget_release=False,
        )
        pv._new(closed, pv.encode(receipt))
        still_owned()
        return {
            "status": "PHYSICAL_VISIT_CLOSED",
            "bank_claim_released": False,
            "same_native_intent_reconciliation_required": True,
            "reservation_or_budget_release": False,
        }
