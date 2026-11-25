import hashlib
import os
import sys
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from functools import partial
from pathlib import Path, PureWindowsPath
from uuid import UUID

import pytest

from test_h3_dec4_bank_visit import PIN, RELEASE, Source, no_effect, run
from test_h3_dec4_schedule_plan import ARGS
from thericher_v2.execution.paper_peer_visit import process_start
from thericher_v2.ops.h3_dec4_native_host import (
    NativeProcessIdentity,
    QualifiedSchedulerInstance,
    _ticks,
    bind_dec4_native_owner,
    read_current_dec4_process,
)
from thericher_v2.ops.h3_dec4_schedule_plan import build_dec4_schedule_plan

GUID = UUID("8ce48d27-67b2-4bcd-97c7-31dc4e8dcaa1")
OTHER_GUID = UUID(int=1)


def test_current_native_reader_never_resolves_another_pid():
    with pytest.raises(ValueError, match="current_native_process_required"):
        read_current_dec4_process(os.getpid() + 1)


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows process APIs")
def test_current_native_reader_observes_windows_image_and_birth():
    pid = os.getpid()
    proof = read_current_dec4_process(pid)
    assert proof.pid == pid and proof.start_ticks == process_start(pid).split(":")[1]
    assert Path(proof.image).resolve() == Path(sys._base_executable).resolve()
    assert proof.argv[1:] == tuple(sys.orig_argv[1:])


class Samples:
    def __init__(self, phase):
        self.plan = build_dec4_schedule_plan(**ARGS)
        self.leg = self.plan["phases"][phase]
        self.argv = tuple(self.leg["expected_argv"])
        self.path = "\\" + self.leg["slot"]["name"]
        self.action_sha = hashlib.sha256(self.leg["action"].encode()).hexdigest()
        self.row = dict(
            Claim="SCHEDULER_INSTANCE_OBSERVED", Matches=1, EnginePid=os.getpid(), InstanceGuid=GUID
        )
        self.process = NativeProcessIdentity(
            os.getpid(),
            self.argv[0],
            str(_ticks(datetime.fromisoformat(self.leg["slot"]["start_UTC"]))),
            self.argv,
        )
        self.calls = []
        self.make_owner = partial(
            bind_dec4_native_owner,
            self.plan,
            read_scheduler=self.scheduler,
            read_process=self.native,
        )

    def scheduler(self, path, pid):
        assert path == self.path and pid == os.getpid()
        self.calls.append("scheduler")
        return QualifiedSchedulerInstance(self.path, self.action_sha, self.row)

    def native(self, pid):
        assert pid == os.getpid()
        self.calls.append("native")
        return self.process


@pytest.mark.parametrize("phase,day,minute", [("entry", 4, 31), ("exit", 9, 30)])
def test_exact_native_owner_reaches_existing_bank_guard(tmp_path, phase, day, minute):
    samples = Samples(phase)
    source = Source(tmp_path)
    source.ROOT = PureWindowsPath(ARGS["dispatcher_root"])
    source.action = lambda *_: samples.leg["action"]

    def guard(_leg, ready):
        proof = ready.owner.prove()
        assert proof["pid"] == os.getpid()
        assert proof["start_ticks"] == samples.process.start_ticks
        assert proof["argv_sha256"] == samples.leg["expected_argv_sha256"]
        return False

    with pytest.raises(ValueError, match="writer_admission_denied"):
        run(
            tmp_path,
            source,
            phase=phase,
            make_owner=samples.make_owner,
            writer_and_observer_ready=guard,
            prepare_phase_input=no_effect,
            invoke_capsule_once=no_effect,
            fixture_clock=lambda: datetime(2026, 12, day, 14, minute, tzinfo=UTC),
        )
    assert samples.calls == ["scheduler", "native", "scheduler"] * 4
    assert not list(source.gate.glob("*/ACTIVE-LEG.json"))


@pytest.mark.parametrize(
    "change",
    [
        {"EnginePid": os.getpid() + 1},
        {"EnginePid": str(os.getpid())},
        {"Matches": 2},
        {"Claim": "UNKNOWN"},
        {"InstanceGuid": str(UUID(int=0))},
        {"InstanceGuid": "not-a-guid"},
    ],
)
def test_unqualified_scheduler_instance_never_probes_native_process(change):
    samples = Samples("entry")
    samples.row.update(change)
    with pytest.raises(ValueError, match="^h3_bank_owner_changed$"):
        samples.make_owner(PIN, "entry", RELEASE).prove()
    assert samples.calls == ["scheduler"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("task_path", r"\other-task"),
        ("action_sha256", "f" * 64),
    ],
)
def test_readback_must_bind_exact_registered_path_and_action(field, value):
    samples = Samples("entry")
    reader = samples.scheduler

    def wrong_definition(path, pid):
        sample = reader(path, pid)
        return replace(sample, **{field: value})

    owner = bind_dec4_native_owner(
        samples.plan, PIN, "entry", RELEASE, read_scheduler=wrong_definition, read_process=no_effect
    )
    with pytest.raises(ValueError, match="^h3_bank_owner_changed$"):
        owner.prove()


@pytest.mark.parametrize(
    "change",
    [
        {"pid": os.getpid() + 1},
        {"image": r"C:\other\pythonw.exe"},
        {"start_ticks": "0"},
        {"start_ticks": "134000000000000000"},
        {"start_ticks": 134405226600000000},
        {"start_ticks": "0134405226600000000"},
        {"argv": ()},
    ],
)
def test_exact_native_process_is_required(change):
    samples = Samples("entry")
    samples.process = replace(samples.process, **change)
    with pytest.raises(ValueError, match="^h3_bank_owner_changed$"):
        samples.make_owner(PIN, "entry", RELEASE).prove()


@pytest.mark.parametrize("arg_index", [-3, -1])
def test_native_argv_rejects_changed_source_or_release(arg_index):
    samples = Samples("entry")
    argv = list(samples.argv)
    argv[arg_index] = "f" * 64
    samples.process = replace(samples.process, argv=tuple(argv))
    with pytest.raises(ValueError, match="^h3_bank_owner_changed$"):
        samples.make_owner(PIN, "entry", RELEASE).prove()


def test_plan_must_match_runtime_source_release_and_action():
    samples = Samples("entry")
    for pin, release in (("f" * 64, RELEASE), (PIN, "f" * 64)):
        with pytest.raises(ValueError, match="^h3_bank_native_plan_mismatch$"):
            samples.make_owner(pin, "entry", release)
    bad_plan = deepcopy(samples.plan)
    bad_plan["phases"]["entry"]["action"] += " "
    with pytest.raises(ValueError, match="^h3_bank_native_plan_mismatch$"):
        bind_dec4_native_owner(
            bad_plan, PIN, "entry", RELEASE, read_scheduler=no_effect, read_process=no_effect
        )
    assert not samples.calls


def test_preflight_rejects_a_plan_for_a_different_source_action(tmp_path):
    samples = Samples("entry")
    source = Source(tmp_path)
    source.ROOT = PureWindowsPath(ARGS["dispatcher_root"])
    with pytest.raises(ValueError, match="Native scheduled owner expectation mismatch"):
        run(tmp_path, source, make_owner=samples.make_owner, invoke_capsule_once=no_effect)
    assert not samples.calls


def test_instance_must_be_stable_across_native_read():
    samples = Samples("entry")

    def native(pid):
        process = samples.native(pid)
        samples.row["InstanceGuid"] = OTHER_GUID
        return process

    owner = bind_dec4_native_owner(
        samples.plan, PIN, "entry", RELEASE, read_scheduler=samples.scheduler, read_process=native
    )
    with pytest.raises(ValueError, match="^h3_bank_owner_changed$"):
        owner.prove()
    assert samples.calls == ["scheduler", "native", "scheduler"]


@pytest.mark.parametrize("replacement", ["birth", "instance"])
def test_effect_read_checks_original_birth_and_instance(tmp_path, replacement):
    samples = Samples("entry")
    source = Source(tmp_path)
    source.ROOT = PureWindowsPath(ARGS["dispatcher_root"])
    source.action = lambda *_: samples.leg["action"]

    def replace_owner(*_):
        if replacement == "birth":
            samples.process = replace(
                samples.process, start_ticks=str(int(samples.process.start_ticks) + 1)
            )
        else:
            samples.row["InstanceGuid"] = OTHER_GUID
        return source.retained

    with pytest.raises(ValueError, match="^h3_bank_owner_changed$"):
        run(
            tmp_path,
            source,
            make_owner=samples.make_owner,
            prepare_phase_input=replace_owner,
            invoke_capsule_once=no_effect,
        )
    assert not list(source.gate.glob("*/ACTIVE-LEG.json"))


def test_equivalent_guid_text_keeps_same_instance():
    samples = Samples("entry")
    owner = samples.make_owner(PIN, "entry", RELEASE)
    first = owner.prove()
    samples.row["InstanceGuid"] = "{" + str(GUID).upper() + "}"
    assert owner.prove() == first


def test_reader_failure_is_unknown_without_native_error_text():
    samples = Samples("entry")

    def failed(_pid):
        raise OSError("raw process details")

    owner = bind_dec4_native_owner(
        samples.plan, PIN, "entry", RELEASE, read_scheduler=samples.scheduler, read_process=failed
    )
    with pytest.raises(ValueError, match="^h3_bank_owner_changed$") as error:
        owner.prove()
    assert error.value.__suppress_context__
