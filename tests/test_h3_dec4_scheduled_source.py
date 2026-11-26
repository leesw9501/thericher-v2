from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
from subprocess import list2cmdline

import pytest

from thericher_v2.execution import paper_peer_visit as pv
from thericher_v2.ops.h3_dec4_bank_visit import _TIMES, ROUND, TASKS
from thericher_v2.ops.h3_dec4_pair_release import bind_dec4_scheduled_pair_source


@pytest.fixture
def pair(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    launcher = root / "launch.py"
    launcher.write_bytes(b"# invented launcher\n")
    executable = tmp_path / "pythonw.exe"
    executable.write_bytes(b"invented runtime")
    launcher_pin, exe_pin = (
        sha256(path.read_bytes()).hexdigest() for path in (launcher, executable)
    )
    restore_pins = dict(
        observer_plan_sha256="a" * 64,
        observer_restore_daemon_sha256="b" * 64,
        observer_restore_writer_guard_sha256="c" * 64,
    )
    source = dict(
        restore_native={phase: {"pins": restore_pins} for phase in TASKS},
        restore_bootstrap=dict(executable=str(executable), executable_sha256=exe_pin),
        files={launcher.name: launcher_pin},
    )
    raw = pv.encode(source)
    (root / "SOURCE.json").write_bytes(raw)
    pin = sha256(raw).hexdigest()
    release = pv.encode(
        dict(
            schema="h3-dec4-protected-pair-release-v1",
            source=pin,
            phases={
                phase: dict(phase=phase, allow_execute=True, actual_financial_admission=False)
                for phase in TASKS
            },
        )
    )
    (tmp_path / "RELEASE.json").write_bytes(release)
    release_pin = sha256(release).hexdigest()
    plan = dict(round_id=ROUND, launcher_sha256=launcher_pin, pythonw_sha256=exe_pin, phases={})
    for phase, name in TASKS.items():
        start, end, hard = _TIMES[phase]
        argv = [
            str(executable),
            "-I",
            "-S",
            "-B",
            str(launcher),
            "--phase",
            phase,
            "--source-sha256",
            pin,
            "--release-sha256",
            release_pin,
        ]
        action = pv.encode(
            dict(executable=argv[0], arguments=list2cmdline(argv[1:]), working_directory=str(root))
        ).decode("ascii")
        plan["phases"][phase] = dict(
            slot=dict(
                name=name,
                start_UTC=start.isoformat(),
                end_UTC=end.isoformat(),
                hard_UTC=hard.isoformat(),
            ),
            expected_argv=argv,
            expected_argv_sha256=pv.digest(argv),
            action=action,
            owner_expected=dict(
                dispatcher_source=pin,
                dispatcher_release=release_pin,
                dispatcher_root=str(root),
                task_name=name,
                task_action_sha256=sha256(action.encode()).hexdigest(),
                round_id=ROUND,
            ),
        )
    return root, plan, pin, release_pin


@pytest.mark.parametrize("phase", ("entry", "exit"))
def test_bank_source_derives_action_from_same_plan_and_checks_real_bytes(pair, phase):
    root, plan, pin, release_pin = pair
    actual = bind_dec4_scheduled_pair_source(*pair, phase)
    start, end, _ = _TIMES[phase]
    value = actual.check(pin)
    assert actual.ROOT == root
    assert actual.SLOTS[phase] == plan["phases"][phase]["slot"]
    assert actual.action(pin, release_pin, phase) == plan["phases"][phase]["action"]
    assert actual.window(phase, start) == (start, end)
    assert actual.release(value, pin, release_pin) == dict(
        source=pin, phase=phase, allow_execute=True, actual_financial_admission=False
    )
    for at in (start - timedelta(seconds=1), end, start.replace(tzinfo=None)):
        with pytest.raises(pv.Denied):
            actual.window(phase, at)
    with pytest.raises(pv.Denied):
        actual.action(pin, "0" * 64, phase)


@pytest.mark.parametrize("member", ("source/SOURCE.json", "source/launch.py", "pythonw.exe"))
def test_preflight_rejects_changed_pinned_member(pair, member):
    root, _, pin, _ = pair
    actual = bind_dec4_scheduled_pair_source(*pair, "exit")
    (root.parent / member).write_bytes(b"modified")
    with pytest.raises(pv.Denied):
        actual.check(pin)


def test_crossed_phase_or_drifted_action_is_refused(pair):
    root, plan, pin, release_pin = pair
    plan = deepcopy(plan)
    plan["phases"]["entry"]["action"] = plan["phases"]["exit"]["action"]
    with pytest.raises(ValueError, match="native_plan_mismatch"):
        bind_dec4_scheduled_pair_source(root, plan, pin, release_pin, "entry")


def test_root_cannot_be_selected_by_schedule_action(pair):
    root, plan, pin, release_pin = pair
    with pytest.raises(pv.Denied):
        bind_dec4_scheduled_pair_source(root.parent, plan, pin, release_pin, "exit")
