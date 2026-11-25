import hashlib
import os
import subprocess
import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest

from thericher_v2.execution.paper_peer_visit import digest
from thericher_v2.ops.h3_dec4_restore_process import RestoreProcessActor
from thericher_v2.ops.h3_dec4_root_watchdog import RootWatchdogActor
from thericher_v2.ops.h3_dec4_writer_identity import (
    CapsuleProcess,
    CapsuleProcessInventory,
    WindowsActor,
    join_dec4_writer_actors,
    read_windows_actor,
    require_dec4_capsule_processes,
)

_EPOCH = 504911232000000000
_CID = "a" * 64


def _sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


@pytest.fixture
def cohort():
    root_args = ["C:/runtime/pythonw.exe", "-I", "C:/synthetic/launcher.py"]
    root_raw = '"C:/runtime/pythonw.exe"  -I C:/synthetic/launcher.py'
    attach_args = [
        "C:/Program Files/Docker/Docker/resources/bin/docker.exe",
        "--host",
        "npipe:////./pipe/dockerDesktopLinuxEngine",
        "start",
        "--attach",
        "--interactive",
        _CID,
    ]
    actors = {
        10: WindowsActor(10, "123", _sha(root_raw), digest(root_args), root_args[0]),
        20: WindowsActor(20, "147", _sha("watch command"), "a" * 64, root_args[0]),
        30: WindowsActor(
            30,
            "159",
            _sha(subprocess.list2cmdline(attach_args)),
            digest(attach_args),
            attach_args[0],
        ),
    }
    rows = [
        dict(
            pid=pid,
            parent_pid=10 if pid != 10 else 5,
            start_ticks=str((int(actor.filetime) + _EPOCH) // 10 * 10),
            argv_sha256=actor.raw_command_sha256,
            children=[20, 30, 60] if pid == 10 else [],
        )
        for pid, actor in actors.items()
    ]
    rows.append(dict(pid=60, parent_pid=10, children=[]))
    spec = {"kind": "effect"}
    record = dict(
        schema="paper-bank-leg-v1",
        identity={"argv_sha256": digest(root_args)},
        owner={"pid": 10, "native_start": "win-filetime:123"},
        visits=[
            dict(
                run="c" * 32,
                kind="effect",
                status="ACTIVE",
                create=dict(resolution="ACK_EXACT_CID", cid=_CID, spec_sha256=digest(spec)),
                children=[
                    dict(pid=29, native_start="win-filetime:151"),
                    dict(
                        pid=30,
                        native_start="win-filetime:159",
                        status="RUNNING_OR_UNKNOWN",
                        argv_sha256=digest(attach_args),
                    ),
                ],
            )
        ],
    )
    owner = dict(
        schema="paper-stock-ingress-owner-v1",
        status="PASS_STOCK_INGRESS_SCHEDULED_OWNER",
        origin="ACTUAL_STOCK_INGRESS_TASK_SOURCE_ABI",
        no_old_model_self_rows=True,
        pid=10,
        start_ticks="123",
        argv_sha256=digest(root_args),
    )
    attach = SimpleNamespace(
        pid=30,
        native_start="win-filetime:159",
        args=attach_args,
        joined=False,
        job=42,
        poll=lambda: None,
        active=lambda: 1,
    )
    visit = SimpleNamespace(
        cid=_CID,
        run="c" * 32,
        spec=spec,
        jobs=[
            SimpleNamespace(joined=True, pid=29, native_start="win-filetime:151", poll=lambda: 0),
            attach,
        ],
    )
    return SimpleNamespace(
        facts=dict(complete=True, actors=rows),
        owner=owner,
        record=record,
        actors=actors,
        attach=attach,
        visit=visit,
        watch=RootWatchdogActor(20, "147", actors[20].raw_command_sha256),
    )


def _join(cohort, *, attached=False):
    return join_dec4_writer_actors(
        cohort.facts,
        owner=cohort.owner,
        bank_record=cohort.record,
        watchdog=cohort.watch,
        attached_visit=cohort.visit if attached else None,
        read_actor=cohort.actors.__getitem__,
    )


@pytest.mark.parametrize("attached,ids", [(False, {10, 20}), (True, {10, 20, 30})])
def test_emits_only_exact_r8_census_keys(cohort, attached, ids):
    assert _join(cohort, attached=attached) == frozenset(
        (row["pid"], row["start_ticks"], row["argv_sha256"])
        for row in cohort.facts["actors"]
        if row["pid"] in ids
    )


def test_exact_restore_child_join_never_adopts_wrong_lineage(cohort):
    child = WindowsActor(60, "188", "d" * 64, "e" * 64, cohort.actors[10].image)
    cohort.actors[60] = child
    row = cohort.facts["actors"][-1]
    row.update(start_ticks=str(_EPOCH + 188), argv_sha256=child.raw_command_sha256)
    options = dict(
        owner=cohort.owner,
        bank_record=cohort.record,
        watchdog=cohort.watch,
        restore=RestoreProcessActor(60, child.filetime, child.raw_command_sha256),
        read_actor=cohort.actors.__getitem__,
    )
    assert {key[0] for key in join_dec4_writer_actors(cohort.facts, **options)} == {10, 20, 60}
    row["parent_pid"] = 5
    with pytest.raises(ValueError, match="actor_lineage"):
        join_dec4_writer_actors(cohort.facts, **options)


@pytest.mark.parametrize("index", [0, 2])
def test_parsed_argv_digest_is_not_raw_command_digest(cohort, index):
    row = cohort.facts["actors"][index]
    row["argv_sha256"] = cohort.actors[row["pid"]].parsed_argv_sha256
    with pytest.raises(ValueError, match="h3_writer_actor_identity"):
        _join(cohort, attached=True)


def test_accepts_exact_native_dotnet_ticks_too(cohort):
    cohort.facts["actors"][0]["start_ticks"] = _EPOCH + 123
    assert (10, str(_EPOCH + 123), cohort.actors[10].raw_command_sha256) in _join(cohort)


@pytest.mark.parametrize("pid", [10, 20, 30])
def test_pid_reuse_inside_same_cim_microsecond_is_not_owned(cohort, pid):
    actor = cohort.actors[pid]
    cohort.actors[pid] = replace(actor, filetime=str(int(actor.filetime) - 1))
    with pytest.raises(ValueError, match="h3_writer_actor_identity"):
        _join(cohort, attached=True)


def test_wrong_noncanonical_census_ticks_are_not_owned(cohort):
    cohort.facts["actors"][0]["start_ticks"] = str(_EPOCH + 124)
    with pytest.raises(ValueError, match="h3_writer_actor_identity"):
        _join(cohort)


def test_missing_and_duplicate_census_actor_deny(cohort):
    row = cohort.facts["actors"].pop(1)
    with pytest.raises(ValueError, match="h3_writer_actor_not_inventoried"):
        _join(cohort)
    cohort.facts["actors"].extend((row, row.copy()))
    with pytest.raises(ValueError, match="h3_writer_census_actor_ambiguous"):
        _join(cohort)


def test_incomplete_census_and_broken_parent_edge_deny(cohort):
    cohort.facts["complete"] = False
    with pytest.raises(ValueError, match="h3_writer_census_incomplete"):
        _join(cohort)
    cohort.facts["complete"] = True
    cohort.facts["actors"][1]["parent_pid"] = 0
    with pytest.raises(ValueError, match="h3_writer_actor_lineage"):
        _join(cohort)


def test_attach_requires_exact_acknowledged_cid(cohort):
    cohort.record["visits"][0]["create"]["cid"] = "b" * 64
    with pytest.raises(ValueError, match="h3_writer_attach_unacknowledged"):
        _join(cohort, attached=True)


def test_attach_requires_bound_job_and_argv(cohort):
    cohort.attach.args[4] = "--detach"
    with pytest.raises(ValueError, match="h3_writer_attach_identity"):
        _join(cohort, attached=True)


def test_joined_inspect_jobs_may_follow_the_acknowledged_attach(cohort):
    cohort.visit.jobs.append(
        SimpleNamespace(pid=30, native_start="win-filetime:180", joined=True, poll=lambda: 0)
    )
    cohort.visit.jobs.append(
        SimpleNamespace(pid=31, native_start="win-filetime:190", joined=True, poll=lambda: 0)
    )
    assert {key[0] for key in _join(cohort, attached=True)} == {10, 20, 30}


@pytest.mark.parametrize("joined,exit_code", [(False, 0), (True, None), (False, None)])
def test_any_other_job_must_be_joined_and_non_live(cohort, joined, exit_code):
    cohort.visit.jobs.append(
        SimpleNamespace(
            pid=31, native_start="win-filetime:190", joined=joined, poll=lambda: exit_code
        )
    )
    with pytest.raises(ValueError, match="h3_writer_attach_identity"):
        _join(cohort, attached=True)


def test_duplicate_exact_attach_identity_is_ambiguous(cohort):
    cohort.visit.jobs.append(
        SimpleNamespace(pid=30, native_start="win-filetime:159", joined=True, poll=lambda: 0)
    )
    with pytest.raises(ValueError, match="h3_writer_attach_identity"):
        _join(cohort, attached=True)


@pytest.mark.parametrize("counts", [(2,), (1, 2), (True,)])
def test_attach_rejects_extra_or_unknown_job_members(cohort, counts):
    samples = iter(counts)
    cohort.attach.active = lambda: next(samples)
    with pytest.raises(ValueError, match="h3_writer_attach_job_membership"):
        _join(cohort, attached=True)


def test_exited_create_row_does_not_inherit_attach_ownership(cohort):
    cohort.facts["actors"].append(dict(pid=29, parent_pid=10, children=[]))
    assert {key[0] for key in _join(cohort, attached=True)} == {10, 20, 30}


def test_independent_capsule_guest_role_and_same_cid_extra_process():
    guest = CapsuleProcess(1, 100, "a" * 64)
    inventory = CapsuleProcessInventory(_CID, True, (guest,))
    assert require_dec4_capsule_processes(_CID, inventory, guest=guest) is None
    extra = replace(guest, namespace_pid=43)
    with pytest.raises(ValueError, match="h3_writer_container_extra_process"):
        require_dec4_capsule_processes(
            _CID, replace(inventory, processes=(guest, extra)), guest=guest
        )
    with pytest.raises(ValueError, match="h3_writer_container_guest_unbound"):
        require_dec4_capsule_processes(_CID, inventory, guest=replace(guest, start_ticks=101))


@pytest.mark.parametrize("inventory", [None, CapsuleProcessInventory(_CID, False, ())])
def test_cid_alone_or_unavailable_process_inventory_does_not_exempt(inventory):
    with pytest.raises(ValueError, match="h3_writer_container_processes_unknown"):
        require_dec4_capsule_processes(_CID, inventory, guest=CapsuleProcess(1, 100, "a" * 64))


@pytest.mark.skipif(os.name != "nt", reason="Windows native process ABI")
def test_native_reader_observes_live_inline_child_raw_command_and_exact_filetime():
    from thericher_v2.execution.paper_peer_visit import process_start

    args = [sys._base_executable, "-I", "-S", "-c", "import time; time.sleep(30)"]
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR") if key in os.environ}
    child = subprocess.Popen(args, env=env, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        actor = read_windows_actor(child.pid)
        assert actor.pid == child.pid
        assert f"win-filetime:{actor.filetime}" == process_start(child.pid)
        assert actor.raw_command_sha256 == _sha(subprocess.list2cmdline(args))
        assert actor.parsed_argv_sha256 == digest(args)
    finally:
        child.terminate()
        child.wait(timeout=5)
    with pytest.raises(ValueError, match="h3_writer_native_actor_unavailable"):
        read_windows_actor(child.pid)
