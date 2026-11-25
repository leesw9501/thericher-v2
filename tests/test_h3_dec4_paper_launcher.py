"""The scheduled BankLeg owns the exact preparation and one capsule dispatch."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_h3_dec4_bank_visit import PIN, Source, capsule, run
from thericher_v2.ops import h3_dec4_paper_launcher as launcher
from thericher_v2.ops.h3_dec4_capsule import inspect_dec4_capsule


@pytest.fixture
def staged(tmp_path, monkeypatch):
    source = Source(tmp_path)
    workspace = tmp_path / "capsules"
    workspace.mkdir()
    pins = dict(
        image="sha256:" + "6" * 64,
        network="none",
        mounts=[
            {
                "type": "volume",
                "source": "invented-bank",
                "target": "/app/private",
                "rw": True,
            }
        ],
        workspace=str(workspace),
        account_ref="7" * 64,
        worker_sha256="8" * 64,
    )
    original = source.check
    monkeypatch.setattr(source, "check", lambda pin: original(pin) | {"capsule": pins})
    return source, workspace, pins


def _prepare(clock, guard, packet_loader):
    return lambda leg, ready, retained, frame, admit: launcher._prepare_capsule(
        leg,
        ready,
        retained,
        frame,
        admit,
        writer_guard=guard,
        load_paper_packet=packet_loader,
        clock=clock,
    )


def _never(*_args, **_kwargs):
    pytest.fail("unexpected credential or effect callback")


def _entry_clock():
    return datetime(2026, 12, 4, 14, 31, tzinfo=UTC)


def test_same_leg_watchdog_arms_once_and_is_checked_after_slow_admission(monkeypatch):
    events = []
    live = True

    def check_lease():
        events.append("watchdog")
        return live

    def arm(**pins):
        events.append(pins)
        return SimpleNamespace(check=check_lease, actor="invented-watchdog")

    def live_guard(ctx, *, stage, visit):
        nonlocal live
        events.append((ctx.leg, stage, visit))
        live = False
        return True

    monkeypatch.setattr(launcher, "arm_root_watchdog", arm)
    root = Path("C:/authorized/pythonw.exe")
    leg = SimpleNamespace(record={"owner": {"native_start": "win-filetime:123", "pid": 2}})
    plan = SimpleNamespace(source={}, plan=SimpleNamespace(hard_stop=_entry_clock()))
    guard = SimpleNamespace(check=live_guard)
    def readiness(_leg, _plan, actor):
        assert actor == "invented-watchdog"
        events.append("observer")
        return True

    gate = launcher._WatchdogGate(root, readiness, guard)
    assert gate.ready(leg, plan) and gate.ready(leg, plan)
    assert events[0] == dict(executable=root, pid=2, start_ticks="123", hard_cutoff=_entry_clock())
    assert events[1:] == ["watchdog", "observer", "watchdog"] * 2
    with pytest.raises(ValueError, match="h3_root_watchdog_unavailable"):
        gate.check(SimpleNamespace(leg=object()), stage="GUEST_ADMISSION", visit=None)
    with pytest.raises(ValueError, match="h3_root_watchdog_unavailable"):
        gate.check(SimpleNamespace(leg=leg), stage="GUEST_ADMISSION", visit="invented")
    assert events[-3:] == ["watchdog", (leg, "GUEST_ADMISSION", "invented"), "watchdog"]


@pytest.mark.parametrize("phase,day,minute", [("entry", 4, 31), ("exit", 9, 30)])
def test_each_leg_stages_exact_native_frame_and_uses_one_capsule(
    staged, tmp_path, monkeypatch, phase, day, minute
):
    source, workspace, _ = staged
    guard = SimpleNamespace(check=lambda *_a, **_k: True)
    bindings = []

    def clock():
        return datetime(2026, 12, day, 14, minute, tzinfo=UTC)

    prepare = _prepare(clock, guard, _never)

    def staged_dispatch(leg, ready, retained, frame, admit):
        assert not leg.record["visits"]
        bindings.append((leg, ready, frame, admit))
        return prepare(leg, ready, retained, frame, admit)

    def verify_adapter(ctx, spec, *, guest, load_packet, read_retained, exchange_deadline):
        ((leg, ready, frame, admit),) = bindings
        assert ctx.leg is leg and ctx.writer_guard is guard and ctx.source_pin == PIN
        assert ctx.readiness is ready and ctx.owner is ready.owner
        assert ctx.admission() is True and type(exchange_deadline) is float
        assert load_packet is _never
        mounts = {m["target"]: m for m in spec["mounts"]}
        assert not mounts["/admission"]["rw"] and mounts["/out"]["rw"]
        folder = Path(mounts["/admission"]["source"])
        assert folder.parent.parent == workspace and folder.parent.name == leg.identity["run"]
        binding, packet = folder / "CAPSULE-BINDING.json", folder / "NET25.frame"
        raw = binding.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == spec["args"][2]
        _, typed = inspect_dec4_capsule(raw, packet.read_bytes(), binding_sha256=spec["args"][2])
        assert typed.cohort == guest.cohort and packet.read_bytes() == frame
        assert bool(frame.partition(b"\n")[2]) == (phase == "entry")
        output = Path(mounts["/out"]["source"]) / "RAW-PRODUCER.json"
        with pytest.raises(FileNotFoundError):
            read_retained()
        output.write_bytes(b"invented terminal bytes")
        assert read_retained() == b"invented terminal bytes"
        return capsule(leg, ready, frame, admit)

    monkeypatch.setattr(launcher, "run_dec4_capsule_visit", verify_adapter)
    result = run(
        tmp_path,
        source,
        phase=phase,
        fixture_clock=clock,
        invoke_capsule_once=None,
        prepare_capsule_once=staged_dispatch,
    )
    assert result["native_visits"] == 1
    assert result["financial_claim"] == "UNKNOWN" and result["reservation_release"] is False
    assert not list(source.gate.glob("*/ACTIVE-LEG.json"))


@pytest.mark.parametrize("fault", ["volume", "reserved_mount", "scope", "missing_root"])
def test_invalid_preparation_never_calls_capsule_and_closes_untouched_leg(
    staged, tmp_path, monkeypatch, fault
):
    source, workspace, pins = staged
    if fault == "volume":
        pins["mounts"][0]["source"] = "other-volume"
    elif fault == "reserved_mount":
        pins["mounts"][0]["target"] = "/admission/child"
    elif fault == "scope":
        pins["network"] = "host"
    else:
        pins["workspace"] = str(workspace / "absent")
    monkeypatch.setattr(launcher, "run_dec4_capsule_visit", _never)
    guard = SimpleNamespace(check=_never)
    with pytest.raises(ValueError, match="dec4_launcher_"):
        run(
            tmp_path,
            source,
            invoke_capsule_once=None,
            prepare_capsule_once=_prepare(_entry_clock, guard, _never),
        )
    assert not list(workspace.iterdir())
    assert not list(source.gate.glob("*/ACTIVE-LEG.json"))


@pytest.mark.parametrize(
    "relative,error",
    [("admission/NET25.frame", "admission_changed"), ("out/RAW-PRODUCER.json", "output_not_empty")],
)
def test_admission_change_after_dispatch_selection_holds_for_exact_recovery(
    staged, tmp_path, monkeypatch, relative, error
):
    source, workspace, _ = staged
    monkeypatch.setattr(launcher, "run_dec4_capsule_visit", _never)
    guard = SimpleNamespace(check=_never)
    prepare = _prepare(_entry_clock, guard, _never)

    def changed(leg, ready, retained, frame, admit):
        dispatch = prepare(leg, ready, retained, frame, admit)
        (workspace / leg.identity["run"] / relative).write_bytes(b"changed")
        return dispatch

    with pytest.raises(ValueError, match=error):
        run(tmp_path, source, invoke_capsule_once=None, prepare_capsule_once=changed)
    assert len(list(source.gate.glob("*/ACTIVE-LEG.json"))) == 1
