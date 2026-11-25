"""Retain the accepted native Job/container receipt for normal observer restore."""

from copy import deepcopy
from pathlib import Path

from thericher_v2.execution import paper_peer_visit as pv


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


def retain_dec4_normal_job_close(leg, before, receipt):
    """Publish only after the exact Visit has consumed the receipt successfully."""
    leg.check()
    final = leg.record
    _check(before, receipt, final)
    path = _path(leg.root, final)
    snapshot = pv._new(path, pv.encode({"before": before, "receipt": receipt}))
    leg.check()
    pv._need(pv._read(path) == snapshot, "h3_normal_job_receipt_changed")


def read_dec4_normal_job_close(root, record):
    """Read original evidence joined to the independently held final bank record."""
    path = _path(root, record)
    snapshot = pv._read(path)
    value = pv._decode(snapshot[0])
    pv._need(set(value) == {"before", "receipt"}, "h3_normal_job_receipt_schema")
    _check(value["before"], value["receipt"], record)
    pv._need(pv._read(path) == snapshot, "h3_normal_job_receipt_changed")
    return snapshot
