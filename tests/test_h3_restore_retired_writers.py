import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "read_h3_restore_retired_writers.ps1"
_FIXTURE = r"""
param($Reader, $Profile, $Pin, $Case)
$ErrorActionPreference = 'Stop'
$PSModuleAutoLoadingPreference = 'None'
Import-Module Microsoft.PowerShell.Utility -ErrorAction Stop
$log = [Collections.Generic.List[string]]::new()
$t = [pscustomobject]@{
    Path = '\thericher-inert-a'; State = 1; Enabled = $false
    Xml = "<Task>`r`n<Enabled>false</Enabled></Task>"
    Definition = @{XmlText = '<Task><Settings><Enabled>false</Enabled></Settings></Task>'}
    Case = $Case
}
$t | Add-Member ScriptMethod GetSecurityDescriptor {
    param($flags)
    if ($flags -ne 7) { throw 'UNMOCKED_ACL' }
    if ($this.Case -eq 'acl') { return 'private-synthetic-drift' }
    return 'O:SYG:SYD:(A;;FA;;;SY)'
}
$f = [pscustomobject]@{Path = '\'; Task = $t; Log = $log; Case = $Case; Reads = 0}
$f | Add-Member ScriptMethod GetTask {
    param($name)
    if ($name -cnotin @('thericher-inert-a', 'thericher-inert-b')) { throw 'UNMOCKED_TASK' }
    $this.Log.Add($name)
    $this.Reads++
    $task = $this.Task.psobject.Copy()
    $task.Path = '\' + $name
    switch ($this.Case) {
        'missing' { if ($name.EndsWith('-b')) { throw 'private-synthetic-missing' } }
        'path' { $task.Path = $task.Path.ToUpperInvariant() }
        'enabled' { $task.Enabled = $true }
        'enabled-string' { $task.Enabled = 'False' }
        'queued' { $task.State = 2 }
        'state-string' { $task.State = '1' }
        'export' { $task.Xml = $task.Xml.Replace("`r`n", "`n") }
        'definition' { $task.Definition = @{XmlText = 'private-synthetic-drift'} }
        'late-definition' {
            if ($this.Reads -eq 4) { $task.Definition = @{XmlText = 'private-synthetic-drift'} }
        }
    }
    return $task
}
$s = [pscustomobject]@{
    Connected = $false; TargetServer = [Environment]::MachineName
    ConnectedUser = [Environment]::UserName; ConnectedDomain = [Environment]::UserDomainName
    Folder = $f; Log = $log; Case = $Case; Scans = 0
}
$s | Add-Member ScriptMethod Connect {
    if ($args.Count) { throw 'UNMOCKED_CONNECT' }
    $this.Log.Add('connect')
    $this.Connected = $true
    if ($this.Case -eq 'remote') { $this.TargetServer = 'private-synthetic-remote' }
}
$s | Add-Member ScriptMethod GetFolder {
    param($path)
    if ($path -cne '\') { throw 'UNMOCKED_FOLDER' }
    $this.Log.Add('root')
    if ($this.Case -eq 'root') { $this.Folder.Path = '\not-root' }
    return $this.Folder
}
$s | Add-Member ScriptMethod GetRunningTasks {
    param($flags)
    if ($flags -ne 1) { throw 'UNMOCKED_ENUM' }
    $this.Log.Add('running')
    $this.Scans++
    if ($this.Case -eq 'null-running') { return $null }
    if ($this.Case -eq 'empty-running') {
        return [pscustomobject]@{Count = 0}
    }
    $path = '\Elsewhere\Unrelated writer'
    if ($this.Case -eq 'active' -or ($this.Case -eq 'late-active' -and $this.Scans -eq 3)) {
        $path = '\THERICHER-INERT-B'
    }
    if ($this.Case -eq 'bad-running-path') { $path = 'private-synthetic-no-root' }
    $running = [pscustomobject]@{Count = 1; Path = $path; Case = $this.Case}
    $running | Add-Member ScriptMethod Item {
        param($index)
        if ($index -ne 1) { throw 'UNMOCKED_ITEM' }
        if ($this.Case -eq 'count-drift') { $this.Count = 2 }
        return [pscustomobject]@{Path = $this.Path}
    }
    return $running
}
function New-Object {
    param($ComObject)
    if ($ComObject -cne 'Schedule.Service') { throw 'UNMOCKED_COM' }
    $log.Add('new')
    return $s
}
$LASTEXITCODE = 0
& $Reader -ProfilePath $Profile -ProfileSha256 $Pin
$status = $LASTEXITCODE
$readback = 'root,thericher-inert-a,thericher-inert-b,running'
if ($Case -in @('ok', 'empty-running') -and
    ($log -join ',') -cne "new,connect,running,$readback,$readback") {
    throw 'BAD_READBACK_BRACKET'
}
if ($Case -eq 'profile' -and $log.Count -ne 0) { throw 'SCHEDULER_TOUCHED_FOR_BAD_PROFILE' }
exit $status
"""


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _profile():
    return {
        "schema": "h3-restore-retired-writers-v1",
        "tasks": [
            {
                "path": rf"\thericher-inert-{suffix}",
                "export_sha256": _sha("<Task>\r\n<Enabled>false</Enabled></Task>"),
                "definition_sha256": _sha(
                    "<Task><Settings><Enabled>false</Enabled></Settings></Task>"
                ),
                "api7_sha256": _sha("O:SYG:SYD:(A;;FA;;;SY)"),
            }
            for suffix in ("a", "b")
        ],
    }


def _run(tmp_path, case, profile, *, pin=None, absolute=True):
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        pytest.skip("PowerShell 7 unavailable")
    probe = tmp_path / "inert-retired-writers.ps1"
    probe.write_text(_FIXTURE, encoding="ascii")
    profile_path = tmp_path / "profile.json"
    profile_path.write_bytes(profile.encode("utf-8"))
    return subprocess.run(
        [
            pwsh, "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(probe),
            str(_SCRIPT), str(profile_path if absolute else profile_path.name),
            pin or _sha(profile), case,
        ],
        cwd=tmp_path,
        env={k: os.environ[k] for k in ("SystemRoot", "WINDIR", "PATH") if k in os.environ},
        capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        timeout=20,
        check=False,
    )


@pytest.mark.parametrize("case", ["ok", "empty-running"])
def test_exact_compact_retirement_proof(tmp_path, case):
    profile = json.dumps(_profile())
    result = _run(tmp_path, case, profile)
    assert result.returncode == 0, result.stderr
    assert result.stderr == b""
    assert result.stdout.splitlines() == [json.dumps(
        {"schema": "h3-restore-retired-writers-proof-v1",
         "profile_sha256": _sha(profile), "retired": True},
        separators=(",", ":"),
    ).encode("ascii")]


def _assert_denied(result):
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert result.stdout == b""
    assert result.stderr.splitlines() == [b"H3_RESTORE_RETIRED_WRITERS_UNAVAILABLE"]


@pytest.mark.parametrize("case", [
    "remote", "root", "missing", "path", "enabled", "enabled-string", "queued", "state-string",
    "export", "definition", "late-definition", "acl", "active", "late-active",
    "null-running", "bad-running-path", "count-drift",
])
def test_scheduler_evidence_denies_on_drift_or_unknown(tmp_path, case):
    _assert_denied(_run(tmp_path, case, json.dumps(_profile())))


@pytest.mark.parametrize("case", [
    "empty", "object-instead-of-array", "extra-key", "wrong-case-key",
    "duplicate-key", "duplicate-row-key",
    "duplicate-path", "subfolder", "foreign", "path-array", "hash-array", "upper-hash",
    "wrong-pin", "upper-pin", "relative",
])
def test_bad_profile_denied_before_scheduler(tmp_path, case):
    profile = _profile()
    task = profile["tasks"][0]
    pin = None
    if case == "empty":
        profile["tasks"] = []
    elif case == "object-instead-of-array":
        profile["tasks"] = task
    elif case == "extra-key":
        task["extra"] = "extra"
    elif case == "wrong-case-key":
        task["Path"] = task.pop("path")
    elif case == "duplicate-path":
        profile["tasks"][1]["path"] = r"\thericher-inert-A"
    elif case == "subfolder":
        task["path"] = r"\folder\thericher-inert-a"
    elif case == "foreign":
        task["path"] = r"\other-inert"
    elif case == "path-array":
        task["path"] = [task["path"]]
    elif case == "hash-array":
        task["api7_sha256"] = [task["api7_sha256"]]
    elif case == "upper-hash":
        task["api7_sha256"] = task["api7_sha256"].upper()
    elif case == "wrong-pin":
        pin = "a" * 64
    elif case == "upper-pin":
        pin = _sha(json.dumps(profile)).upper()
    text = json.dumps(profile)
    if case == "duplicate-key":
        text = '{"schema": "h3-restore-retired-writers-v1",' + text[1:]
    elif case == "duplicate-row-key":
        text = text.replace('"path":', '"p\\u0061th": null, "path":', 1)
    _assert_denied(_run(tmp_path, "profile", text, pin=pin, absolute=case != "relative"))
