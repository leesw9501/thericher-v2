"""Synthetic joined evidence into the real gated publication and bank finalizer."""

from dataclasses import asdict, replace
from datetime import timedelta

import pytest

import test_h3_dec4_crash_recovery as crash
from thericher_v2.execution import paper_peer_visit as pv
from thericher_v2.execution.net25_pending_reconciliation import Net25TerminalProof
from thericher_v2.ops import h3_dec4_recovery_handoff as handoff
from thericher_v2.ops.h3_dec4_guest import _binding
from thericher_v2.ops.h3_dec4_recovery_guest import Dec4RecoveryPins, _outcome
from thericher_v2.ops.h3_dec4_watchdog import HostJobResult


def _ref(char):
    return "sha256:" + char * 64


@pytest.fixture
def case(tmp_path, monkeypatch):
    path, identity, original = active = crash.active.__wrapped__(tmp_path)
    crash._run(active)
    physical = path.with_name("PHYSICAL-CLOSED-" + identity["run"] + ".json")
    _, cohort = _binding("entry", _ref("a"), _ref("b"), _ref("c"), "d" * 64)
    start = cohort.slot.ends_at + timedelta(days=1)
    expected = Dec4RecoveryPins(
        cohort, identity["bank"], handoff._sha(path.read_bytes()),
        handoff._sha(physical.read_bytes()), _ref("1"), "2" * 64,
        start, start + timedelta(minutes=3),
    )
    proof = Net25TerminalProof(
        _ref("0"), expected.pending_ref, _ref("2"), _ref("3"), _ref("4"), _ref("5"),
        "broker_terminal_retained",
    )
    terminal = _outcome(
        expected, "reconciled", "exact_native_terminal_retained", 3, 1, asdict(proof)
    )
    stdout = pv.encode(terminal) + b"\n"
    host = HostJobResult(41, "win-filetime:501", 0, "EXITED")
    owner = dict(pid=host.pid, native_start=host.native_start)
    child = dict(
        token="a" * 32, argv_sha256="b" * 64, pid=42, native_start="win-filetime:502",
        status="RUNNING_OR_UNKNOWN",
    )
    recovery_identity = identity | {"source": "e" * 64, "run": "f" * 32}
    create = dict(resolution="ACK_EXACT_CID", spec_sha256="c" * 64, cid="d" * 64)
    visit = dict(
        run="a" * 32, kind="recovery", status="ACTIVE", closure=None, create=create,
        children=[child],
    )
    record = original | {"identity": recovery_identity, "owner": owner, "visits": [visit]}
    closure = dict(
        schema="paper-bank-visit-closure-v1", identity=recovery_identity, owner=owner,
        visit=visit["run"], record_sha256=pv.digest(record),
        children=[
            {k: child[k] for k in ("token", "argv_sha256", "pid", "native_start")}
            | {"closure": "EXACT_PROCESS_AND_JOB_JOINED"}
        ],
        create_resolution="ACK_EXACT_CID", container=create["cid"],
        container_status="EXACT_CONTAINER_ABSENT_AFTER_JOIN", evidence_sha256="3" * 64,
    )
    receipt = dict(
        schema="h3-dec4-joined-recovery-visit-v1",
        recovery_source_sha256=recovery_identity["source"],
        worker_sha256="4" * 64, original_claim_sha256=expected.original_claim_sha256,
        physical_sha256=expected.physical_receipt_sha256, frame_sha256=terminal["frame_sha256"],
        outcome_sha256=handoff._sha(stdout), host=asdict(host), attach_exit_code=0, order_posts=0,
        closure=closure,
    )
    pins = handoff.Dec4RecoveryJoinPins(
        pv.digest(recovery_identity), receipt["worker_sha256"], create["spec_sha256"],
        visit["run"], child["argv_sha256"], pv.digest(record), pv.digest(receipt),
    )
    monkeypatch.setattr(pv, "process_start", lambda _: None)
    return path, physical, dict(
        root=tmp_path, bank=crash._BANK, identity=identity, expected=expected, join_pins=pins,
        host=host, recovery_record=pv.encode(record), joined_receipt=pv.encode(receipt),
        stdout=stdout, retained=stdout, prepared=proof, verify_native=lambda proof: proof,
    )


def _native_path(case):
    return case[0].with_name("NATIVE-RECONCILED-" + case[2]["identity"]["run"] + ".json")


def _run(case, **kwargs):
    return handoff.handoff_dec4_joined_recovery(**(case[2] | kwargs))


def _receipt_override(args, value):
    return dict(
        joined_receipt=pv.encode(value),
        join_pins=replace(args["join_pins"], joined_sha256=pv.digest(value)),
    )


def test_joined_bridge_publishes_receipt_and_calls_existing_finalizer(case):
    path, physical, args = case
    native = _native_path(case)
    seen = []

    def readback(proof):
        assert path.is_file() and native.is_file()
        assert proof == args["prepared"]
        seen.append(proof)
        return proof

    result = _run(case, verify_native=readback)
    assert not path.exists() and len(seen) == 1
    assert result == dict(
        status="CLOSED_OPERATIONAL_ONLY", reservation_or_budget_release=False,
        recovery_sha256=handoff._sha(native.read_bytes()),
    )
    assert pv._decode(native.read_bytes()) == dict(
        schema="h3-dec4-native-reconciled-v1", source=args["identity"]["source"],
        original_claim_sha256=args["expected"].original_claim_sha256,
        physical_sha256=handoff._sha(physical.read_bytes()),
        joined_recovery_visit_sha256=args["join_pins"].joined_sha256, order_posts=0,
        terminal=asdict(args["prepared"]),
    )


def test_failed_finalizer_readback_reuses_exact_publication_without_rerunning_guest(case):
    path, _, _ = case
    native = _native_path(case)
    with pytest.raises(pv.Denied, match="native_unconfirmed"):
        _run(case, verify_native=lambda _: None)
    snapshot = pv._read(native)
    assert path.is_file()
    assert _run(case)["status"] == "CLOSED_OPERATIONAL_ONLY"
    assert pv._read(native) == snapshot


def test_interrupted_rename_never_publishes_and_stage_is_not_used(case, monkeypatch):
    path, _, _ = case
    native = _native_path(case)

    def interrupt(src, dst):
        assert src.read_bytes() and dst == native and not dst.exists()
        raise OSError("invented publish interruption")

    with monkeypatch.context() as patch:
        patch.setattr(handoff.os, "rename" if handoff.os.name == "nt" else "replace", interrupt)
        with pytest.raises(OSError, match="publish interruption"):
            _run(case)
    abandoned, = path.parent.glob("NATIVE-RECONCILED-STAGE-*.tmp")
    assert not native.exists() and path.is_file()
    raw = abandoned.read_bytes()
    _run(case)
    assert abandoned.read_bytes() == raw


def test_gate_recheck_catches_original_mutation_during_stage(case, monkeypatch):
    path, physical, _ = case
    new = pv._new

    def stage(member, data):
        result = new(member, data)
        if member.name.startswith("NATIVE-RECONCILED-STAGE-"):
            physical.write_bytes(physical.read_bytes() + b" ")
        return result

    monkeypatch.setattr(pv, "_new", stage)
    with pytest.raises(pv.Denied, match="original_changed"):
        _run(case)
    assert path.is_file() and not _native_path(case).exists()


def test_preexisting_conflict_is_not_overwritten(case):
    native = _native_path(case)
    native.write_bytes(b"conflict")
    with pytest.raises(pv.Denied, match="native_conflict"):
        _run(case)
    assert case[0].is_file() and native.read_bytes() == b"conflict"


def test_actual_finalizer_rechecks_claim_after_gate_handoff(case, monkeypatch):
    path, _, _ = case
    finalize = handoff.finalize_dec4_reconciled_leg

    def changed(root, **kwargs):
        assert _native_path(case).is_file()
        claim = pv._decode(path.read_bytes())
        path.write_bytes(pv.encode(claim | {"sequence": claim["sequence"] + 1}))
        return finalize(root, **kwargs)

    monkeypatch.setattr(handoff, "finalize_dec4_reconciled_leg", changed)
    with pytest.raises(pv.Denied, match="physical_unconfirmed"):
        _run(case)
    assert path.is_file() and not list(path.parent.glob("CLOSED-*.json"))


@pytest.mark.parametrize(
    "bad",
    ["host_abort", "host_birth", "attach_exit", "attach_pin", "record_pin", "worker", "source",
     "live_attach", "bad_docker", "other_cid", "order_posts", "retained", "prepared", "no_proof"],
)
def test_unconfirmed_join_or_projection_keeps_bank_held(case, monkeypatch, bad):
    path, _, args = case
    overrides = {}
    receipt = pv._decode(args["joined_receipt"])
    if bad in ("host_abort", "host_birth"):
        overrides["host"] = replace(args["host"], **(
            {"disposition": "EXITED_WITH_MEMBERS"} if bad == "host_abort"
            else {"native_start": "win-filetime:999"}
        ))
    elif bad in ("attach_pin", "record_pin"):
        key = "attach_argv_sha256" if bad == "attach_pin" else "recovery_record_sha256"
        overrides["join_pins"] = replace(args["join_pins"], **{key: "0" * 64})
    elif bad == "live_attach":
        monkeypatch.setattr(pv, "process_start", lambda k: "win-filetime:502" if k == 42 else None)
    elif bad == "retained":
        overrides["retained"] = b"{}\n"
    elif bad == "prepared":
        overrides["prepared"] = replace(args["prepared"], evidence_ref=_ref("6"))
    elif bad == "no_proof":
        raw = pv.encode(_outcome(args["expected"], "reconciled", "never_reserved_retired",
                                 0, 0, None)) + b"\n"
        receipt["outcome_sha256"] = handoff._sha(raw)
        overrides.update(stdout=raw, retained=raw, **_receipt_override(args, receipt))
    else:
        if bad == "attach_exit":
            receipt["attach_exit_code"] = 1
        elif bad == "worker":
            receipt["worker_sha256"] = "0" * 64
        elif bad == "source":
            receipt["recovery_source_sha256"] = "0" * 64
        elif bad == "bad_docker":
            receipt["closure"]["container_status"] = "NAME_NOT_FOUND"
        elif bad == "other_cid":
            receipt["closure"]["container"] = "0" * 64
        elif bad == "order_posts":
            receipt["order_posts"] = False
        overrides.update(_receipt_override(args, receipt))
    with pytest.raises((pv.Denied, ValueError), match="h3_"):
        _run(case, **overrides)
    assert path.is_file() and not _native_path(case).exists()
