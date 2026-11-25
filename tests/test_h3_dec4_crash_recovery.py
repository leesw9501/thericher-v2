"""The original bank claim is never released by physical crash recovery."""

import json
from dataclasses import replace

import pytest

from thericher_v2.execution import paper_peer_visit as pv
from thericher_v2.ops.h3_dec4_crash_recovery import _recover
from thericher_v2.ops.h3_dec4_watchdog import HostJobResult

_BANK = dict(engine="npipe:////./pipe/dockerdesktoplinuxengine", volume="invented")
_SPEC = dict(kind="effect", phase="entry", network="none")
_OWNER = HostJobResult(11, "win-filetime:100", 20, "DEADLINE")


@pytest.fixture
def active(tmp_path):
    key = pv.bank_key(_BANK)
    identity = dict(
        bank=key,
        source="a" * 64,
        release="b" * 64,
        group="c" * 64,
        member="stock-ingress",
        run="d" * 32,
        argv_sha256="e" * 64,
    )
    root = tmp_path / ("bank-" + key)
    root.mkdir()
    path = root / "ACTIVE-LEG.json"
    record = dict(
        schema="paper-bank-leg-v1",
        identity=identity,
        reservation_release=False,
        sequence=5,
        owner=dict(pid=_OWNER.pid, native_start=_OWNER.native_start),
        visits=[
            dict(
                run="1" * 32,
                kind="effect",
                status="ACTIVE",
                closure=None,
                create=dict(resolution="ACK_EXACT_CID", spec_sha256=pv.digest(_SPEC), cid="9" * 64),
                children=[
                    dict(
                        token="2" * 32,
                        argv_sha256="f" * 64,
                        pid=12,
                        native_start="win-filetime:101",
                        status="RUNNING_OR_UNKNOWN",
                    )
                ],
            )
        ],
    )
    path.write_bytes(pv.encode(record))
    return path, identity, record


def _evidence(bank, source, spec, record, visit):
    assert bank == _BANK and source == record["identity"]["source"] and spec == _SPEC
    return dict(
        schema="paper-bank-visit-closure-v1",
        identity=record["identity"],
        owner=record["owner"],
        visit=visit["run"],
        record_sha256=pv.digest(record),
        children=[
            {k: c[k] for k in ("token", "argv_sha256", "pid", "native_start")}
            | {"closure": "EXACT_PROCESS_AND_JOB_JOINED"}
            for c in visit["children"]
        ],
        create_resolution="ACK_EXACT_CID",
        container=visit["create"]["cid"],
        container_status="EXACT_CONTAINER_ABSENT_AFTER_JOIN",
        evidence_sha256="3" * 64,
    )


def _run(active, *, host=_OWNER, spec=_SPEC, probe=lambda _: None, remove=_evidence):
    path, identity, _ = active
    return _recover(path.parent.parent, _BANK, identity, spec, host, probe, remove)


def test_physical_close_leaves_bank_held_and_refuses_repeat(active):
    path, identity, record = active
    raw = path.read_bytes()
    result = _run(active, probe=lambda _: "win-filetime:200")  # different, newer process birth
    assert result == dict(
        status="PHYSICAL_VISIT_CLOSED",
        bank_claim_released=False,
        same_native_intent_reconciliation_required=True,
        reservation_or_budget_release=False,
    )
    assert path.read_bytes() == raw
    receipt = json.loads(
        (path.parent / ("PHYSICAL-CLOSED-" + identity["run"] + ".json")).read_bytes()
    )
    assert receipt["original_claim_sha256"] == pv.digest(record)
    assert receipt["closure"]["container"] == record["visits"][0]["create"]["cid"]
    with pytest.raises(pv.Held, match="durable_bank_leg_held"):
        with pv.BankLeg(path.parent.parent, bank=_BANK, identity=identity | {"run": "8" * 32}):
            pytest.fail("a different writer entered before financial reconciliation")
    with pytest.raises(pv.Held, match="terminal_exists"):
        _run(active, remove=lambda *_: pytest.fail("must not repeat daemon effects"))


@pytest.mark.parametrize(
    "bad",
    [
        "owner",
        "visit",
        "spec",
        "ambiguous_create",
        "pid_gap",
        "alive",
        "foreign_namespace",
        "unknown_probe",
    ],
)
def test_bad_binding_never_reaches_daemon(active, bad):
    path, _, record = active
    host = _OWNER
    spec = _SPEC
    current = None
    if bad == "owner":
        host = replace(host, native_start="win-filetime:999")
    elif bad == "spec":
        spec = _SPEC | {"phase": "exit"}
    elif bad == "ambiguous_create":
        record["visits"][0]["create"].update(resolution="ATTEMPTED_UNRESOLVED", cid=None)
    elif bad == "visit":
        record["visits"][0]["kind"] = "recovery"
    elif bad == "pid_gap":
        record["visits"][0]["children"][0].update(
            status="SPAWNING_PID_UNKNOWN", pid=None, native_start=None
        )
    elif bad == "alive":
        current = "win-filetime:100"
    elif bad == "foreign_namespace":
        current = "linux-startticks:100"
    elif bad == "unknown_probe":
        current = False
    path.write_bytes(pv.encode(record))
    raw = path.read_bytes()
    with pytest.raises(pv.Held):
        _run(
            active,
            host=host,
            spec=spec,
            probe=lambda _: current,
            remove=lambda *_: pytest.fail("unconfirmed scope reached the daemon"),
        )
    assert path.read_bytes() == raw and not list(path.parent.glob("PHYSICAL-CLOSED-*.json"))


@pytest.mark.parametrize("case", ["wrong_cid", "changed_claim"])
def test_malformed_daemon_evidence_does_not_close(active, case):
    path, _, record = active

    def remove(*args):
        if case == "changed_claim":
            path.write_bytes(pv.encode(record | {"sequence": 6}))
        return _evidence(*args) | {"container": "4" * 64}

    with pytest.raises(pv.Held, match="daemon_unconfirmed|claim_changed"):
        _run(active, remove=remove)
    assert path.exists() and not list(path.parent.glob("PHYSICAL-CLOSED-*.json"))
