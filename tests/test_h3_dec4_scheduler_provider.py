import hashlib
import json
import os
import subprocess
from dataclasses import replace
from datetime import datetime
from uuid import UUID

import pytest

from test_h3_dec4_schedule_plan import ARGS
from thericher_v2.ops import h3_dec4_scheduler_provider as provider
from thericher_v2.ops.h3_dec4_bank_visit import TASKS
from thericher_v2.ops.h3_dec4_native_host import (
    NativeProcessIdentity,
    QualifiedSchedulerInstance,
    _ticks,
)
from thericher_v2.ops.h3_dec4_schedule_plan import build_dec4_schedule_plan

_GUID = "d0951119-a4eb-4209-82dc-dee559f709ac"


@pytest.fixture
def probe(tmp_path, monkeypatch):
    monkeypatch.setattr(provider, "_windows_root", lambda: tmp_path)
    if os.name != "nt":
        monkeypatch.setattr(provider, "_open_locked", lambda path: path.open("rb"))

    def fake_only(*args, **kwargs):
        pytest.fail("subprocess must be mocked in every test")

    monkeypatch.setattr(provider.subprocess, "run", fake_only)
    paths = [tmp_path / name for name in ("pwsh.exe", "probe script.ps1", "profile file.json")]
    for path in paths:
        path.write_bytes(path.name.encode("ascii"))
    return provider.Dec4SchedulerProvider(
        task_path="\\" + TASKS["entry"],
        action_sha256="a" * 64,
        pwsh_path=paths[0],
        pwsh_sha256=hashlib.sha256(paths[0].read_bytes()).hexdigest(),
        script_path=paths[1],
        script_sha256=hashlib.sha256(paths[1].read_bytes()).hexdigest(),
        profile_path=paths[2],
        profile_sha256=hashlib.sha256(paths[2].read_bytes()).hexdigest(),
    )


def reply(probe, **override):
    row = {
        "schema": "PAPER_NATIVE_OWNER_READBACK_V1",
        "task_path": probe.task_path,
        "action_sha256": probe.action_sha256,
        "instance_guid": "{" + _GUID.upper() + "}",
        "engine_pid": 173,
        "profile_sha256": probe.profile_sha256,
    }
    return json.dumps(row | override, separators=(",", ":")).encode("ascii")


def fake_run(monkeypatch, output, returncode=0):
    monkeypatch.setattr(
        provider.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess([], returncode, output),
    )


def test_windows_factory_binds_phase_provider_and_native_reader(probe, monkeypatch):
    plan = build_dec4_schedule_plan(**ARGS)
    providers = {}
    for phase, leg in plan["phases"].items():
        providers[phase] = replace(
            probe,
            task_path="\\" + TASKS[phase],
            action_sha256=leg["owner_expected"]["task_action_sha256"],
        )
    entry = plan["phases"]["entry"]
    argv = tuple(entry["expected_argv"])
    ticks = str(_ticks(datetime.fromisoformat(entry["slot"]["start_UTC"])))
    pid = os.getpid()
    monkeypatch.setattr(
        provider,
        "read_current_dec4_process",
        lambda pid: NativeProcessIdentity(pid, argv[0], ticks, argv),
    )
    monkeypatch.setattr(
        provider.Dec4SchedulerProvider,
        "_read",
        lambda self, pid: self._parse(reply(self, engine_pid=pid), pid),
    )
    with pytest.raises(ValueError, match="scheduler_plan_mismatch"):
        provider.make_dec4_windows_owner_factory(plan, {"entry": providers["entry"]})
    factory = provider.make_dec4_windows_owner_factory(plan, providers)
    owner = factory(ARGS["source_sha256"], "entry", ARGS["release_sha256"])
    proof = owner.prove()
    assert proof["pid"] == pid and proof["start_ticks"] == ticks
    assert proof["task_action_sha256"] == providers["entry"].action_sha256
    wrong = provider.make_dec4_windows_owner_factory(
        plan, providers | {"entry": replace(providers["entry"], action_sha256="f" * 64)}
    )
    with pytest.raises(ValueError, match="scheduler_plan_mismatch"):
        wrong(ARGS["source_sha256"], "entry", ARGS["release_sha256"])


def test_uses_exact_hidden_noninteractive_abi_without_inheriting_environment(probe, monkeypatch):
    root = probe.pwsh_path.parent
    calls = []
    monkeypatch.setenv("PATH", "untrusted")
    monkeypatch.setenv("SystemRoot", "untrusted")
    monkeypatch.setenv("PSModulePath", "untrusted")
    monkeypatch.setenv("DOTNET_STARTUP_HOOKS", "untrusted")

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        guid = "{" + _GUID.upper() + "}" if len(calls) == 1 else _GUID.replace("d", "c")
        return subprocess.CompletedProcess([], 0, reply(probe, instance_guid=guid) + b"\r\n")

    monkeypatch.setattr(provider.subprocess, "run", run)
    assert probe(probe.task_path, 173) == QualifiedSchedulerInstance(
        probe.task_path,
        probe.action_sha256,
        {
            "Claim": "SCHEDULER_INSTANCE_OBSERVED",
            "Matches": 1,
            "EnginePid": 173,
            "InstanceGuid": UUID(_GUID),
        },
    )
    assert probe(probe.task_path, 173).readback["InstanceGuid"] == UUID(_GUID.replace("d", "c"))
    assert len(calls) == 2
    argv, options = calls[0]
    assert argv == [
        str(probe.pwsh_path),
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-File",
        str(probe.script_path),
        "-TaskPath",
        probe.task_path,
        "-ExpectedEnginePid",
        "173",
        "-ExpectedProfileSha256",
        probe.profile_sha256,
        "-ProfilePath",
        str(probe.profile_path),
    ]
    assert options == dict(
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        cwd=root / "System32",
        env={"SystemRoot": str(root), "TEMP": str(root / "Temp"), "TMP": str(root / "Temp")},
        creationflags=0x08000000,
        timeout=5,
        check=False,
        shell=False,
    )


@pytest.mark.parametrize("field", ["pwsh_path", "script_path", "profile_path"])
def test_pin_mismatch_stops_before_spawn(probe, field):
    getattr(probe, field).write_bytes(b"mismatched bytes")
    with pytest.raises(ValueError, match="^h3_bank_scheduler_readback_unqualified$"):
        probe(probe.task_path, 173)


@pytest.mark.parametrize("field", ["pwsh_path", "script_path", "profile_path"])
def test_relative_paths_are_rejected(probe, field):
    with pytest.raises(ValueError, match="^h3_bank_scheduler_pin_invalid$"):
        replace(probe, **{field: getattr(probe, field).relative_to(probe.pwsh_path.parent)})


def test_wrong_scope_stops_before_spawn(probe):
    for task in (TASKS["entry"], "\\" + TASKS["entry"].upper(), "\\" + TASKS["exit"]):
        with pytest.raises(ValueError, match="^h3_bank_scheduler_scope_mismatch$"):
            probe(task, 173)
    for pid in (0, -1, True, "173", 2**31):
        with pytest.raises(ValueError, match="^h3_bank_scheduler_scope_mismatch$"):
            probe(probe.task_path, pid)
    with pytest.raises(ValueError, match="^h3_bank_scheduler_pin_invalid$"):
        replace(probe, task_path="\\Unrelated")


@pytest.mark.parametrize(
    "override",
    [
        {"schema": "OTHER"},
        {"task_path": "\\" + TASKS["exit"]},
        {"action_sha256": "b" * 64},
        {"profile_sha256": "0" * 64},
        {"engine_pid": 174},
        {"engine_pid": True},
        {"engine_pid": 173.0},
        {"engine_pid": "173"},
        {"instance_guid": 42},
        {"instance_guid": str(UUID(int=0))},
        {"instance_guid": _GUID.replace("-", "")},
        {"private_echo": "must not escape"},
    ],
)
def test_rejects_mismatched_or_unqualified_fields(probe, monkeypatch, override):
    fake_run(monkeypatch, reply(probe, **override))
    with pytest.raises(ValueError, match="^h3_bank_scheduler_readback_unqualified$"):
        probe(probe.task_path, 173)


@pytest.mark.parametrize(
    "corrupt",
    [
        lambda body: b"",
        lambda body: b"noise\n" + body,
        lambda body: body + b"\nnoise",
        lambda body: body + b"\n\n",
        lambda body: body + body,
        lambda body: body[:-1] + b',"engine_pid":173}',
        lambda body: body.replace(b',"engine_pid":173', b""),
        lambda body: b"\xef\xbb\xbf" + body,
        lambda body: body[:-1] + b",\xff}",
        lambda body: body[:-1] + b" " * 1024 + b"}",
    ],
)
def test_stdout_requires_exactly_one_bounded_json_object(probe, monkeypatch, corrupt):
    fake_run(monkeypatch, corrupt(reply(probe)))
    with pytest.raises(ValueError, match="^h3_bank_scheduler_readback_unqualified$"):
        probe(probe.task_path, 173)


def test_nonzero_with_valid_reply_is_not_evidence(probe, monkeypatch):
    fake_run(monkeypatch, reply(probe), returncode=1)
    with pytest.raises(ValueError, match="^h3_bank_scheduler_readback_unqualified$"):
        probe(probe.task_path, 173)


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        (subprocess.TimeoutExpired(["private"], 5, output=b"private"), "timeout"),
        (OSError("private"), "readback_unqualified"),
    ],
)
def test_spawn_failures_drop_private_exception_details(probe, monkeypatch, failure, message):
    def run(*args, **kwargs):
        raise failure

    monkeypatch.setattr(provider.subprocess, "run", run)
    with pytest.raises(ValueError, match=f"^h3_bank_scheduler_{message}$") as error:
        probe(probe.task_path, 173)
    assert error.value.__cause__ is None
    assert error.value.__context__ is None


@pytest.mark.skipif(os.name != "nt", reason="Windows file sharing semantics")
def test_all_pins_stay_readable_but_write_and_delete_locked_until_child_exits(probe, monkeypatch):
    paths = probe.pwsh_path, probe.script_path, probe.profile_path

    def run(*args, **kwargs):
        for path in paths:
            assert path.read_bytes()
            with pytest.raises(PermissionError):
                path.write_bytes(b"swap")
            with pytest.raises(PermissionError):
                path.unlink()
        return subprocess.CompletedProcess([], 0, reply(probe))

    monkeypatch.setattr(provider.subprocess, "run", run)
    probe(probe.task_path, 173)
    for path in paths:
        path.write_bytes(b"released")
