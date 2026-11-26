"""Retain the accepted native Job/container receipt for normal observer restore."""

from copy import deepcopy
from hashlib import sha256
from pathlib import Path

from thericher_v2.execution import paper_peer_visit as pv
from thericher_v2.ops.h3_dec4_capsule import verify_dec4_capsule_outcome

_ACCEPTED = {
    "schema", "phase", "source_ref", "basis_ref", "input_ref", "policy_ref",
    "binding_sha256", "spec_sha256", "stdout_sha256", "exit_code",
}


def _check_accepted(value, record):
    pv._need(
        type(value) is dict
        and value.keys() == _ACCEPTED
        and value["schema"] == "h3-dec4-accepted-capsule-stdout-v1"
        and value["phase"] in ("entry", "exit")
        and value["source_ref"] == "sha256:" + record["identity"]["source"]
        and all(
            type(value[key]) is str and value[key].startswith("sha256:")
            and pv._hash(value[key][7:])
            for key in ("basis_ref", "input_ref", "policy_ref")
        )
        and all(pv._hash(value[key]) for key in ("binding_sha256", "spec_sha256", "stdout_sha256"))
        and type(value["exit_code"]) is int
        and value["exit_code"] == 0
        and value["spec_sha256"] == record["visits"][0]["create"]["spec_sha256"],
        "h3_accepted_capsule_stdout_unbound",
    )


def _check(before, receipt, final):
    """Replay exactly Visit.close's durable transition, without replaying any effect."""
    key = final["identity"]["bank"]
    pv._record(before, key)
    pv._record(final, key)
    (active,) = before["visits"]
    (closed,) = final["visits"]
    children = [
        {k: row[k] for k in ("token", "argv_sha256", "pid", "native_start")}
        | {"closure": "EXACT_PROCESS_AND_JOB_JOINED"}
        for row in active["children"]
    ]
    resolution, cid = active["create"]["resolution"], active["create"]["cid"]
    pv._need(
        active["kind"] == "effect"
        and active["status"] == "ACTIVE"
        and resolution == "ACK_EXACT_CID"
        and children
        and type(receipt) is dict
        and pv._hash(receipt.get("evidence_sha256"))
        and pv._same(
            receipt,
            dict(
                schema="paper-bank-visit-closure-v1",
                identity=before["identity"],
                owner=before["owner"],
                visit=active["run"],
                record_sha256=pv.digest(before),
                children=children,
                create_resolution=resolution,
                container=cid,
                container_status="EXACT_CONTAINER_ABSENT_AFTER_JOIN",
                evidence_sha256=receipt["evidence_sha256"],
            ),
        ),
        "h3_normal_job_receipt_unbound",
    )
    expected = deepcopy(before)
    expected["sequence"] += 1
    row = expected["visits"][0]
    row.update(status="CLOSED", closure=pv.digest(receipt))
    for child in row["children"]:
        child["status"] = "JOINED"
    pv._need(
        closed["closure"] == pv.digest(receipt) and pv._same(expected, final),
        "h3_normal_job_transition_unbound",
    )


def _path(root, record):
    run = record["identity"]["run"]
    pv._need(pv._run(run), "h3_normal_job_run_unbound")
    return Path(root) / ("JOB-CLOSED-" + run + ".json")


def retain_dec4_normal_job_close(leg, before, receipt, *, accepted):
    """Publish only after the exact Visit has consumed the receipt successfully."""
    leg.check()
    final = leg.record
    _check(before, receipt, final)
    _check_accepted(accepted, final)
    path = _path(leg.root, final)
    value = {"before": before, "receipt": receipt, "accepted": accepted}
    snapshot = pv._new(path, pv.encode(value))
    leg.check()
    pv._need(pv._read(path) == snapshot, "h3_normal_job_receipt_changed")


def read_dec4_normal_job_close(root, record):
    """Read original evidence joined to the independently held final bank record."""
    path = _path(root, record)
    snapshot = pv._read(path)
    value = pv._decode(snapshot[0])
    pv._need(
        type(value) is dict
        and set(value) in ({"before", "receipt"}, {"before", "receipt", "accepted"}),
        "h3_normal_job_receipt_schema",
    )
    _check(value["before"], value["receipt"], record)
    if "accepted" in value:
        _check_accepted(value["accepted"], record)
    pv._need(pv._read(path) == snapshot, "h3_normal_job_receipt_changed")
    return snapshot


def read_dec4_accepted_capsule_summary(root, record, *, retained, guest, binding_sha256):
    """Join a protected closed visit and exact binding to accepted transport, never fills."""
    witness = pv._decode(read_dec4_normal_job_close(root, record)[0]).get("accepted")
    if witness is None:
        return None
    cohort = guest.cohort
    pv._need(
        (witness["phase"], witness["source_ref"], witness["basis_ref"],
         witness["input_ref"], witness["policy_ref"], witness["binding_sha256"])
        == (cohort.slot.phase, cohort.source_ref, cohort.basis_ref,
            cohort.slot.input_ref, cohort.slot.policy_ref, binding_sha256)
        and type(retained) is bytes
        and sha256(retained).hexdigest() == witness["stdout_sha256"],
        "h3_accepted_capsule_stdout_unbound",
    )
    return verify_dec4_capsule_outcome(
        retained, retained, exit_code=witness["exit_code"], guest=guest
    )
