"""Dec9 Scheduler proof with invented files and a fully mocked COM namespace."""

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
GUID = "d0951119-a4eb-4209-82dc-dee559f709ac"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


probe = _load("probe_h3_dec9_scheduler_owner")
bootstrap = _load("run_h3_dec9_target_owner")
BIRTH = f"win-filetime:{bootstrap._ticks(bootstrap.OPENS)}"
ACTION = bootstrap.NativeAction(
    bootstrap.TASK_PATH,
    r"C:\Invented Root\pythonw.exe",
    r'''-I -S -B "C:\Invented Root\owner's.py"''',
    r"C:\Invented Root",
)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _profile():
    xml = '<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"><Test /></Task>'
    return {
        "schema": "PAPER_NATIVE_OWNER_PROFILE_V1",
        "task_path": ACTION.task_path,
        "action_sha256": probe._action_digest(ACTION),
        "export_xml": xml,
        "definition_xml": xml,
        "acl7": "O:SYG:SYD:(A;;FA;;;SY)",
        **{key: _sha((SCRIPTS / name).read_bytes()) for name, key in probe._MODULES.items()},
    }


@pytest.fixture
def reader(tmp_path, monkeypatch):
    monkeypatch.setattr(probe, "_windows_root", lambda: tmp_path)
    if os.name != "nt":
        monkeypatch.setattr(probe, "_open_locked", lambda path: path.open("rb"))

    def no_spawn(*args, **kwargs):
        pytest.fail("Unexpected subprocess")

    monkeypatch.setattr(probe.subprocess, "run", no_spawn)
    binary = tmp_path / "pwsh.exe"
    binary.write_bytes(b"invented binary")
    for name in (probe._SCRIPT, *probe._MODULES):
        shutil.copyfile(SCRIPTS / name, tmp_path / name)
    script = tmp_path / probe._SCRIPT
    profile = tmp_path / "profile.json"
    profile.write_bytes(json.dumps(_profile()).encode())
    return probe.Dec9SchedulerProbe(
        pwsh_path=binary,
        pwsh_sha256=_sha(binary.read_bytes()),
        script_path=script,
        script_sha256=_sha(script.read_bytes()),
        profile_path=profile,
        profile_sha256=_sha(profile.read_bytes()),
    )


def _reply(reader, **overrides):
    row = {
        "schema": "PAPER_NATIVE_OWNER_READBACK_V1",
        "task_path": ACTION.task_path,
        "action_sha256": probe._action_digest(ACTION),
        "profile_sha256": reader.profile_sha256,
        "engine_pid": os.getpid(),
        "instance_guid": GUID,
    }
    return json.dumps(row | overrides).encode("ascii")


def test_exact_current_process_and_pinned_probe_command(reader, monkeypatch):
    root = reader.script_path.parent

    def run(argv, **options):
        assert argv == [
            str(reader.pwsh_path),
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(reader.script_path),
            "-TaskPath",
            bootstrap.TASK_PATH,
            "-ExpectedEnginePid",
            str(os.getpid()),
            "-ExpectedProfileSha256",
            reader.profile_sha256,
            "-ProfilePath",
            str(reader.profile_path),
        ]
        assert options == dict(
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=root / "System32",
            shell=False,
            check=False,
            timeout=5,
            creationflags=0x08000000,
            env={"SystemRoot": str(root), "TEMP": str(root / "Temp"), "TMP": str(root / "Temp")},
        )
        return subprocess.CompletedProcess(argv, 0, _reply(reader) + b"\r\n")

    monkeypatch.setattr(probe.subprocess, "run", run)
    assert reader.read_current(ACTION) == probe.Dec9SchedulerEvidence(
        bootstrap.TASK_PATH,
        _profile()["action_sha256"],
        reader.profile_sha256,
        UUID(GUID),
        os.getpid(),
    )


@pytest.mark.parametrize("field", ["pwsh_path", "script_path", "profile_path", *probe._MODULES])
def test_pin_drift_cannot_spawn(reader, field):
    path = getattr(reader, field, reader.script_path.with_name(field))
    path.write_bytes(b"substituted bytes")
    with pytest.raises(ValueError, match="^dec9_scheduler_unqualified$"):
        reader.read_current(ACTION)


def test_foreign_action_and_profile_cannot_spawn(reader):
    for action in (
        ACTION._replace(task_path=ACTION.task_path.upper()),
        ACTION._replace(arguments=ACTION.arguments + " extra"),
    ):
        with pytest.raises(ValueError, match="^dec9_scheduler_unqualified$"):
            reader.read_current(action)
    raw = json.dumps(_profile() | {"task_path": r"\other"}).encode()
    reader.profile_path.write_bytes(raw)
    with pytest.raises(ValueError, match="^dec9_scheduler_unqualified$"):
        replace(reader, profile_sha256=_sha(raw)).read_current(ACTION)


@pytest.mark.skipif(os.name != "nt", reason="Windows file sharing semantics")
def test_read_lock_denies_in_place_write_and_delete(reader, monkeypatch):
    def run(argv, **options):
        for path in (
            reader.pwsh_path,
            reader.script_path,
            reader.profile_path,
            *(reader.script_path.with_name(name) for name in probe._MODULES),
        ):
            with pytest.raises(PermissionError):
                path.open("r+b").close()
            with pytest.raises(PermissionError):
                path.unlink()
        return subprocess.CompletedProcess(argv, 0, _reply(reader))

    monkeypatch.setattr(probe.subprocess, "run", run)
    assert reader.read_current(ACTION).pid == os.getpid()


@pytest.mark.parametrize(
    "changes",
    [
        {"engine_pid": True},
        {"engine_pid": -1},
        {"task_path": r"\other"},
        {"action_sha256": "a" * 64},
        {"profile_sha256": "a" * 64},
        {"instance_guid": str(UUID(int=0))},
        {"unknown": "not evidence"},
    ],
)
def test_wrong_reply_is_not_evidence(reader, monkeypatch, changes):
    monkeypatch.setattr(
        probe.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess([], 0, _reply(reader, **changes)),
    )
    with pytest.raises(ValueError, match="^dec9_scheduler_unqualified$"):
        reader.read_current(ACTION)


@pytest.mark.parametrize("fault", ["duplicate", "extra-line", "oversize", "status", "timeout"])
def test_process_and_transport_fail_closed(reader, monkeypatch, fault):
    def run(argv, **options):
        raw = _reply(reader)
        if fault == "timeout":
            raise subprocess.TimeoutExpired(argv, options["timeout"], output=b"not for export")
        if fault == "duplicate":
            raw = raw[:-1] + b',"engine_pid":17}'
        if fault == "extra-line":
            raw += b"\nnot a reply"
        if fault == "oversize":
            raw += b" " * 1024
        return subprocess.CompletedProcess(argv, int(fault == "status"), raw)

    monkeypatch.setattr(probe.subprocess, "run", run)
    category = fault if fault == "timeout" else "unqualified"
    with pytest.raises(ValueError, match=f"^dec9_scheduler_{category}$") as exc:
        reader.read_current(ACTION)
    assert exc.value.__context__ is None


@pytest.fixture
def process_sample(monkeypatch):
    argv = (ACTION.executable, "-I", "-S", "-B", r"C:\Invented Root\owner's.py")

    def split(command):
        assert command == f'"{ACTION.executable}" {ACTION.arguments}'
        return argv

    monkeypatch.setattr(probe, "_windows_argv", split)
    return probe._ProcessSample(os.getpid(), BIRTH, ACTION.executable, argv)


def test_native_process_join_uses_fresh_exact_readback(reader, monkeypatch, process_sample):
    calls = []
    other_guid = str(UUID(int=2))

    def sample():
        calls.append("process")
        return process_sample

    def run(argv, **options):
        calls.append("scheduler")
        guid = GUID if calls.count("scheduler") == 1 else other_guid
        return subprocess.CompletedProcess(argv, 0, _reply(reader, instance_guid=guid))

    monkeypatch.setattr(probe, "_read_native_process", sample)
    monkeypatch.setattr(probe.subprocess, "run", run)
    first = reader.read_current_process(ACTION)
    second = reader.read_current_process(ACTION)
    assert calls == ["process", "scheduler", "process"] * 2
    assert (first.pid, first.instance, first.birth) == (os.getpid(), UUID(GUID), BIRTH)
    assert (first.image, first.argv) == (ACTION.executable, process_sample.argv)
    assert first.scheduler.action_sha256 == probe._action_digest(ACTION)
    assert first.scheduler.profile_sha256 == reader.profile_sha256
    assert second.instance == UUID(other_guid)  # The ABI, not this reader, latches loss.
    assert ACTION.executable not in repr(first)


@pytest.mark.parametrize("field", ["image", "argv", "pid", "birth"])
@pytest.mark.parametrize("when", ["before", "after"])
def test_process_mismatch_withholds_evidence(reader, monkeypatch, process_sample, field, when):
    other_birth = f"win-filetime:{bootstrap._ticks(bootstrap.OPENS) + 1}"
    changes = {
        "image": ACTION.executable.upper(),
        "argv": process_sample.argv + ("unexpected",),
        "pid": process_sample.pid + 1,
        "birth": "win-filetime:1" if when == "before" else other_birth,
    }
    changed = process_sample._replace(**{field: changes[field]})
    samples = iter((changed,) if when == "before" else (process_sample, changed))
    monkeypatch.setattr(probe, "_read_native_process", lambda: next(samples))
    if when == "after":
        monkeypatch.setattr(
            probe.subprocess,
            "run",
            lambda *a, **kw: subprocess.CompletedProcess([], 0, _reply(reader)),
        )
    with pytest.raises(ValueError, match="^dec9_process_unqualified$"):
        reader.read_current_process(ACTION)


def test_valid_process_cannot_rescue_invalid_scheduler_reply(reader, monkeypatch, process_sample):
    monkeypatch.setattr(probe, "_read_native_process", lambda: process_sample)
    monkeypatch.setattr(
        probe.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess([], 0, _reply(reader, engine_pid=0)),
    )
    with pytest.raises(ValueError, match="^dec9_scheduler_unqualified$"):
        reader.read_current_process(ACTION)


@pytest.mark.skipif(os.name != "nt", reason="Windows native process APIs")
def test_native_windows_current_process_uses_os_image_argv_and_filetime():
    code = r"""
import ctypes
import importlib.util
import os
import re
import sys
from ctypes import wintypes
from pathlib import Path

spec = importlib.util.spec_from_file_location("probe", sys.argv[1])
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
sample = probe._read_native_process()
assert sample.pid == os.getpid()
assert Path(sample.image).samefile(sys.argv[2])
assert sample.argv[1:4] == ("-I", "-S", "-B")
assert sample.argv[-4:] == ("two words", 'literal"quote', "C:\\trailing space\\", "")
assert sample == probe._read_native_process()

kernel = ctypes.WinDLL("kernel32")
now = wintypes.FILETIME()
kernel.GetSystemTimeAsFileTime(ctypes.byref(now))
ticks = (now.dwHighDateTime << 32) | now.dwLowDateTime
assert re.fullmatch(r"win-filetime:[0-9]{18}", sample.birth)
assert 0 <= ticks - int(sample.birth.split(":")[1]) < 30 * 10_000_000
"""
    image = sys._base_executable
    result = subprocess.run(
        [
            image,
            "-I",
            "-S",
            "-B",
            "-c",
            code,
            str(SCRIPTS / f"{probe.__name__}.py"),
            image,
            "two words",
            'literal"quote',
            "C:\\trailing space\\",
            "",
        ],
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")


def _ps(value):
    return "'" + str(value).replace("'", "''") + "'"


@pytest.mark.parametrize("fault", ["none", "acl", "definition", "wrong-pid", "duplicate"])
def test_existing_powershell_reader_against_invented_com(tmp_path, fault):
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        pytest.skip("PowerShell 7 required for synthetic COM readback")
    profile = _profile()
    raw = json.dumps(profile).encode()
    path = tmp_path / "profile.json"
    path.write_bytes(raw)
    script = tmp_path / "synthetic.ps1"
    script.write_text(
        f"""
$PSModuleAutoLoadingPreference = 'None'
Import-Module Microsoft.PowerShell.Management, Microsoft.PowerShell.Utility
$ErrorActionPreference = 'Stop'
$path = {_ps(ACTION.task_path)}
$fixture = ConvertFrom-Json -AsHashtable -InputObject {_ps(raw.decode())}
$exec = [pscustomobject]@{{ Type = 0; Path = {_ps(ACTION.executable)};
    Arguments = {_ps(ACTION.arguments)}; WorkingDirectory = {_ps(ACTION.working_directory)} }}
$actions = [pscustomobject]@{{ Count = 1; Exec = $exec }}
$actions | Add-Member ScriptMethod Item {{ param($i)
    if ($i -ne 1) {{ throw 'index' }}; $this.Exec }}
$task = [pscustomobject]@{{ Path = $path; State = 4; Enabled = $true; Xml = $fixture.export_xml;
    Acl = $fixture.acl7; Definition = [pscustomobject]@{{ XmlText = $fixture.definition_xml;
    Actions = $actions }} }}
$task | Add-Member ScriptMethod GetSecurityDescriptor {{ param($i)
    if ($i -ne 7) {{ throw 'scope' }}; $this.Acl }}
$folder = [pscustomobject]@{{ Path = '\\'; Task = $task }}
$folder | Add-Member ScriptMethod GetTask {{ param($name)
    if ('\\' + $name -cne $this.Task.Path) {{ throw 'scope' }}; $this.Task }}
$instance = [pscustomobject]@{{ Path = $path; State = 4; EnginePID = 17;
    InstanceGuid = {_ps(GUID)} }}
$running = [pscustomobject]@{{ Count = 1; Instance = $instance }}
$running | Add-Member ScriptMethod Item {{ param($i) $this.Instance }}
$service = [pscustomobject]@{{ Connected = $false; TargetServer = [Environment]::MachineName;
    ConnectedUser = [Environment]::UserName; ConnectedDomain = [Environment]::UserDomainName;
    Folder = $folder; Running = $running }}
$service | Add-Member ScriptMethod Connect {{ $this.Connected = $true }}
$service | Add-Member ScriptMethod GetFolder {{ param($name)
    if ($name -cne '\\') {{ throw 'scope' }}; $this.Folder }}
$service | Add-Member ScriptMethod GetRunningTasks {{ param($flags)
    if ($flags -ne 1) {{ throw 'scope' }}; $this.Running }}
function New-Object {{ param($ComObject)
    if ($ComObject -cne 'Schedule.Service') {{ throw 'unexpected mock' }}; $service }}
switch ({_ps(fault)}) {{
    'acl' {{ $task.Acl += 'invented drift' }}
    'definition' {{ $task.Definition.XmlText = $task.Xml.Replace('Test', 'Changed') }}
    'wrong-pid' {{ $instance.EnginePID = 18 }}
    'duplicate' {{ $running.Count = 2 }}
}}
& {_ps(SCRIPTS / probe._SCRIPT)} -TaskPath $path -ExpectedEnginePid 17 `
    -ExpectedProfileSha256 {_sha(raw)} -ProfilePath {_ps(path)}
exit $LASTEXITCODE
""",
        encoding="utf-8",
    )
    out = subprocess.run(
        [pwsh, "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(script)],
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert out.stderr == b""
    if fault == "none":
        assert out.returncode == 0
        reader = probe.Dec9SchedulerProbe(
            pwsh_path=Path(pwsh).absolute(),
            pwsh_sha256="a" * 64,
            script_path=SCRIPTS / probe._SCRIPT,
            script_sha256="b" * 64,
            profile_path=path,
            profile_sha256=_sha(raw),
        )
        assert reader._parse(out.stdout, profile["action_sha256"], 17).instance == UUID(GUID)
    else:
        assert out.returncode == 20
        assert out.stdout == b""
