import os
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace

import pytest

from thericher_v2.execution import paper_peer_visit as pv
from thericher_v2.ops.h3_dec4_bank_visit import _TIMES, ROUND, TASKS
from thericher_v2.ops.h3_dec4_native_host import _ticks
from thericher_v2.ops.h3_dec4_observer_lease import Dec4ObserverLease, ObserverSnapshot
from thericher_v2.ops.h3_dec4_observer_plan import (
    OBSERVER_API7_SHA256,
    OBSERVER_TASK_PATH,
    OBSERVER_XML_SHA256,
    Dec4ObserverPlan,
)
from thericher_v2.ops.h3_dec4_observer_restore import (
    Dec4ObserverRestorePins,
    read_dec4_restore_owner,
    restore_dec4_observer_once,
    retain_dec4_restore_owner,
)
from thericher_v2.ops.paper_scheduled_preflight import ScheduledPaperPlan
from thericher_v2.ops.paper_startup import STAGES, run_startup

_OPEN, _CLOSE, _HARD = _TIMES["entry"]
_START = _OPEN + timedelta(seconds=5)
_OWNER_START = f"win-filetime:{_ticks(_OPEN)}"
_CHILD_START = f"win-filetime:{_ticks(_START)}"
_OWNER_PID = os.getpid()
_CHILD_PID = _OWNER_PID + 1
_BANK = dict(engine="npipe:////./pipe/dockerdesktoplinuxengine", volume="invented-bank")
_ORIGINAL = ObserverSnapshot(
    OBSERVER_TASK_PATH, True, True, 0, OBSERVER_XML_SHA256, OBSERVER_API7_SHA256, "b" * 64, 19
)
_OFF = replace(_ORIGINAL, enabled=False, xml_sha256="c" * 64)


def test_startup_handoff_retains_separate_authority_before_observer_attempt(tmp_path):
    evidence = tmp_path / "startup"
    evidence.mkdir()
    gate = tmp_path / "gate"
    gate.mkdir()
    plan = ScheduledPaperPlan(
        ROUND, "entry", TASKS["entry"], "0" * 64, "a" * 64, "b" * 64, _OPEN, _CLOSE, _HARD
    )
    observer = Dec4ObserverPlan("entry", r"D:\invented\dispatcher", "1" * 64, "2" * 64)
    bank_key = pv.bank_key(_BANK)
    identity = dict(
        source="a" * 64,
        release="b" * 64,
        group="a" * 64,
        member="stock-ingress",
        run="1" * 32,
        argv_sha256="c" * 64,
        bank=bank_key,
    )

    def one():
        return True

    run_startup(
        evidence,
        opportunity=plan.opportunity,
        source=plan.source_sha256,
        phase="entry",
        checks=dict.fromkeys(STAGES, one),
        prepare=one,
        claim_after_checks=True,
    )
    ready = SimpleNamespace(
        plan=plan,
        source=dict(
            original_owner=dict(bank=_BANK),
            original_gate_root=str(gate),
            observer_plan_sha256=observer.sha256,
        ),
        owner=SimpleNamespace(
            prove=lambda: dict(
                pid=os.getpid(), argv_sha256="c" * 64, start_ticks=_OWNER_START.split(":")[1]
            )
        ),
    )
    with pv.BankLeg(
        gate, bank=_BANK, identity=identity, process_probe=lambda _: _OWNER_START
    ) as leg:
        digest = retain_dec4_restore_owner(evidence, ready=ready, leg=leg, observer_plan=observer)
        with pytest.raises(FileExistsError):
            retain_dec4_restore_owner(evidence, ready=ready, leg=leg, observer_plan=observer)
        assert not leg.record["visits"]
        leg.close()
    row = read_dec4_restore_owner(
        evidence, plan=plan, observer_plan=observer, handoff_sha256=digest
    )
    assert row.run == identity["run"] and row.owner_native_start == _OWNER_START
    assert row.gate_root == gate and row.observer_plan_sha256 == observer.sha256
    with pytest.raises(pv.Denied, match="h3_observer_restore_handoff_changed"):
        read_dec4_restore_owner(
            evidence, plan=plan, observer_plan=observer, handoff_sha256="e" * 64
        )


class _Transport:
    def __init__(self):
        self.snapshot = _ORIGINAL
        self.switches = []
        self.sample_hook = lambda: None
        self.restore_hook = lambda: None

    def sample(self, *, enabled):
        assert self.snapshot.enabled is enabled
        self.sample_hook()
        return self.snapshot

    def switch(self, before, *, enabled, attempt, attempt_sha256):
        assert before == self.snapshot
        assert pv.digest(pv._decode(attempt.read_bytes())) == attempt_sha256
        if enabled:
            self.restore_hook()
        self.switches.append(enabled)
        self.snapshot = _ORIGINAL if enabled else _OFF
        return self.snapshot


def _visit_closure(record):
    (visit,) = record["visits"]
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
        container="e" * 64,
        container_status="EXACT_CONTAINER_ABSENT_AFTER_JOIN",
        evidence_sha256="f" * 64,
    )


@pytest.fixture
def restore_case(tmp_path, monkeypatch):
    output = tmp_path / "observer"
    output.mkdir()
    monkeypatch.setattr(Dec4ObserverPlan, "output_root", property(lambda _: output))
    plan = Dec4ObserverPlan("entry", r"D:\invented\dispatcher", "1" * 64, "2" * 64)
    transport = _Transport()
    pins = Dec4ObserverRestorePins(
        "3" * 64,
        "4" * 64,
        plan.sha256,
        tmp_path,
        pv.bank_key(_BANK),
        "5" * 32,
        "6" * 64,
        _OWNER_PID,
        _OWNER_START,
    )
    identity = dict(
        source=pins.source_sha256,
        release=pins.release_sha256,
        group=pins.source_sha256,
        member="stock-ingress",
        run=pins.run,
        argv_sha256=pins.argv_sha256,
        bank=pins.bank_key,
    )
    processes = {_OWNER_PID: _OWNER_START, _CHILD_PID: _CHILD_START}

    def process_start(pid):
        current = processes.get(pid)
        if isinstance(current, Exception):
            raise current
        return current

    monkeypatch.setattr(pv, "process_start", process_start)
    source_value = dict(
        synthetic_only=True,
        observer_plan_sha256=plan.sha256,
        original_gate_root=str(tmp_path),
        original_owner={"bank": dict(_BANK)},
    )

    def check(pin):
        assert pin == "3" * 64
        return source_value

    def release(value, pin, release_pin):
        assert value is source_value and pin == "3" * 64 and release_pin == "4" * 64
        return dict(source=pin, allow_execute=True, actual_financial_admission=False)

    source = SimpleNamespace(
        ROOT=tmp_path,
        ROUND=ROUND,
        SLOTS={
            "entry": dict(
                name=TASKS["entry"],
                start_UTC=_OPEN.isoformat(),
                end_UTC=_CLOSE.isoformat(),
                hard_UTC=_HARD.isoformat(),
            )
        },
        check=check,
        release=release,
    )
    leg = pv.BankLeg(tmp_path, bank=_BANK, identity=identity, process_probe=process_start)
    with leg:
        Dec4ObserverLease(plan, output, transport).begin(
            leg,
            SimpleNamespace(
                plan=SimpleNamespace(
                    phase="entry",
                    source_sha256=pins.source_sha256,
                    release_sha256=pins.release_sha256,
                ),
                source=source_value,
            ),
            clock=lambda: _START,
        )
        with leg.visit("7" * 32, kind="effect") as visit:
            visit.create_attempt("d" * 64)
            visit.create_ack("e" * 64)
            visit.spawn(["invented"], factory=lambda _: SimpleNamespace(pid=_CHILD_PID))
            del processes[_CHILD_PID]
            visit.close(_visit_closure)
        leg.close()
    del processes[_OWNER_PID]

    case = SimpleNamespace(
        output=output,
        closed=leg.root / ("CLOSED-" + pins.run + ".json"),
        guard_checks=0,
        held=False,
        native=lambda: True,
        transport=transport,
        source_value=source_value,
        processes=processes,
    )

    @contextmanager
    def hold_native(record):
        assert record == leg.record and record["owner"]["pid"] == _OWNER_PID
        case.held = True

        def check():
            assert case.held
            case.guard_checks += 1
            return case.native()

        try:
            yield check
        finally:
            case.held = False

    def restore(**kwargs):
        restore_dec4_observer_once(
            Dec4ObserverLease(plan, output, transport),
            **(
                dict(
                    source=source,
                    pins=pins,
                    hold_native_closure=hold_native,
                    fixture_clock=lambda: _HARD,
                )
                | kwargs
            ),
        )

    case.restore = restore
    case.pins = pins
    return case


def test_restores_exact_normal_owner_once_under_held_guard(restore_case):
    case = restore_case

    def switch_check():
        assert case.held and case.guard_checks == 2

    case.transport.restore_hook = switch_check
    case.restore()
    assert case.guard_checks == 3 and not case.held
    assert case.transport.switches == [False, True]
    assert (case.output / "RESTORED.json").is_file()
    with pytest.raises(pv.Held, match="stale_marker"):
        case.restore()
    assert case.transport.switches == [False, True]


def test_fixture_cannot_admit_a_native_daemon_probe(restore_case, tmp_path):
    from thericher_v2.ops.h3_dec4_restore_daemon import Dec4RestoreDaemon

    profile = Dec4RestoreDaemon("1" * 64, "2" * 64, tmp_path)
    with pytest.raises(pv.Denied, match="h3_observer_restore_scope"):
        restore_case.restore(daemon=profile)
    assert restore_case.transport.switches == [False]


@pytest.mark.parametrize(
    ("actor", "start", "error"),
    [
        (_OWNER_PID, _OWNER_START, "owner_not_closed"),
        (_CHILD_PID, _CHILD_START, "process_live_or_unknown"),
        (_OWNER_PID, pv.Denied("process_identity_unknown"), "process_identity_unknown"),
        (_CHILD_PID, "linux-startticks:12", "process_live_or_unknown"),
    ],
    ids=("owner-live", "child-live", "owner-unknown", "child-clock-mismatch"),
)
def test_refuses_live_or_unknown_original_actor(restore_case, actor, start, error):
    restore_case.processes[actor] = start
    with pytest.raises((pv.Denied, ValueError), match=error):
        restore_case.restore()
    assert restore_case.transport.switches == [False]


def test_refuses_writer_unknown_after_disabled_readback(restore_case):
    case = restore_case

    def writer_unknown():
        case.native = lambda: None

    case.transport.sample_hook = writer_unknown
    with pytest.raises(pv.Denied, match="native_unknown"):
        case.restore()
    assert case.guard_checks == 2
    assert case.transport.switches == [False]
    assert not (case.output / "RESTORE_STARTED.json").exists()


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("source_sha256", "a" * 64, "source_or_release"),
        ("release_sha256", "a" * 64, "source_or_release"),
        ("bank_key", "a" * 64, "source_or_release"),
        ("argv_sha256", "a" * 64, "original_mismatch"),
        ("owner_pid", _OWNER_PID + 2, "original_mismatch"),
    ],
    ids=("source", "release", "bank", "argv", "owner"),
)
def test_refuses_wrong_independent_binding(restore_case, field, value, reason):
    case = restore_case
    with pytest.raises(pv.Denied, match=reason):
        case.restore(pins=replace(case.pins, **{field: value}))
    assert case.transport.switches == [False]


@pytest.mark.parametrize("marker", ["RESTORE_STARTED.json", "RESTORED.json"])
def test_refuses_stale_restore_marker_even_without_matching_result(restore_case, marker):
    case = restore_case
    (case.output / marker).write_bytes(b"{}")
    with pytest.raises(pv.Held, match="stale_marker"):
        case.restore()
    assert case.guard_checks == 0 and case.transport.switches == [False]


def test_refuses_abnormal_or_unclosed_leg(restore_case):
    case = restore_case
    active = case.closed.with_name("ACTIVE-LEG.json")
    active.write_bytes(b"{}")
    with pytest.raises(pv.Held, match="bank_active"):
        case.restore()
    active.unlink()
    receipt = pv._decode(case.closed.read_bytes()) | {"physical_recovery_sha256": "a" * 64}
    case.closed.write_bytes(pv.encode(receipt))
    with pytest.raises(pv.Denied, match="not_normal_closure"):
        case.restore()
    assert case.transport.switches == [False]


def test_refuses_started_evidence_changed_during_native_check(restore_case):
    case = restore_case
    started = case.output / "STARTED.json"

    def change_started():
        started.write_bytes(pv.encode(pv._decode(started.read_bytes()) | {"at": _OPEN.isoformat()}))
        return True

    case.native = change_started
    with pytest.raises(pv.Denied, match="evidence_changed"):
        case.restore()
    assert case.transport.switches == [False]


def test_interrupted_switch_consumes_attempt_without_retry(restore_case):
    case = restore_case

    def interrupt():
        raise OSError("invented transport interruption")

    case.transport.restore_hook = interrupt
    with pytest.raises(OSError, match="invented"):
        case.restore()
    assert (case.output / "RESTORE_STARTED.json").is_file()
    assert not (case.output / "RESTORED.json").exists()
    with pytest.raises(pv.Held, match="stale_marker"):
        case.restore()
    assert case.guard_checks == 2


def test_suppressed_guard_failure_is_not_reported_as_restored(restore_case):
    @contextmanager
    def suppress_unknown(_):
        try:
            yield lambda: False
        except pv.Denied:
            pass

    with pytest.raises(pv.Denied, match="result_unknown"):
        restore_case.restore(hold_native_closure=suppress_unknown)
    assert restore_case.transport.switches == [False]
