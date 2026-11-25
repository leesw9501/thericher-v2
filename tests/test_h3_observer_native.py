import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

_MODULE = Path(__file__).resolve().parents[1] / "scripts" / "paper_h3_observer_native.psm1"
_BRIDGE = _MODULE.with_name("read_h3_dec4_observer.ps1")
_FIXTURE = r"""
param([string]$Module,[string]$Case)
$ErrorActionPreference='Stop'
$PSModuleAutoLoadingPreference='None'
Import-Module Microsoft.PowerShell.Utility -ErrorAction Stop
$m=Import-Module $Module -Force -PassThru
& $m {
    param($case)
    $script:H3ObserverPath='\test-inert'
    $t=[pscustomobject]@{
        Path=$script:H3ObserverPath;Enabled=$true;Acl='invented-acl';Queued=$false;
        Active=$false;FailOnDisabled=$false;ChangeOnDisabled=$false;Changed=$false;
        LastRunTime=[datetime]::Parse('2026-01-01T00:00:00Z');
        Definition=@{Settings=@{StartWhenAvailable=$false}}
    }
    $t | Add-Member ScriptProperty State {
        if($this.Queued){2}elseif($this.Enabled){3}else{1}
    }
    $t | Add-Member ScriptProperty Xml {
        $enabled=if($this.Enabled){''}else{'<Enabled>false</Enabled>'}
        $name=if($this.Changed){'other'}else{'invented'}
        '<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"><Settings>'+
            $enabled+'</Settings><Actions><Exec><Command>'+$name+'</Command></Exec></Actions></Task>'
    }
    $t | Add-Member ScriptMethod GetSecurityDescriptor {
        param($level)
        if($level -ne 7){throw 'WRONG_ACL_LEVEL'}
        $this.Acl
    }
    $f=[pscustomobject]@{Task=$t}
    $f | Add-Member ScriptMethod GetTask {
        param($name)
        if($name -cne 'test-inert'){throw 'FOREIGN_TASK'}
        $this.Task
    }
    $s=[pscustomobject]@{Task=$t;Folder=$f}
    $s | Add-Member ScriptMethod Connect { }
    $s | Add-Member ScriptMethod GetFolder {
        param($path)
        if($path -cne '\'){throw 'FOREIGN_FOLDER'}
        $this.Folder
    }
    $s | Add-Member ScriptMethod GetRunningTasks {
        param($flag)
        if($flag -ne 1){throw 'NOT_HIDDEN_INCLUSIVE'}
        if($this.Task.Active -or ($this.Task.FailOnDisabled -and -not $this.Task.Enabled)){
            return ,@([pscustomobject]@{Path=$this.Task.Path})
        }
        if($this.Task.ChangeOnDisabled -and -not $this.Task.Enabled){
            $this.Task.LastRunTime=[datetime]::Parse('2026-01-01T00:00:10Z')
        }
        return ,@()
    }
    $script:fake = $s
    function script:New-Object {
        param($ComObject)
        if($ComObject -cne 'Schedule.Service'){throw 'UNMOCKED_COM'}
        $script:fake
    }
    $script:H3ObserverAcl7=Get-H3ObserverTextHash $t.Acl
    $script:H3ObserverXml=Get-H3ObserverTextHash $t.Xml
    $before=Read-H3ObserverNativeSnapshot $s $f $t.Path $script:H3ObserverAcl7 $true
    switch($case){
        'readiness' {
            $r=Get-H3NativeObserverReadiness -PlanSha256 ('a'*64) -RequestId ('b'*32)
            if($r.schema -cne 'DEC4_H3_OBSERVER_READINESS_V1' -or $r.instances -ne 0 -or
                $r.Task_writes -ne 0 -or -not $r.hidden_inclusive -or
                $r.request_id -cne ('b'*32) -or
                $r.ContainsKey('shape_sha256') -or $r.ContainsKey('last_run') -or -not $t.Enabled){
                throw 'BAD_READ_ONLY_REPLY'
            }
        }
        'switch' {
            $off=Set-H3ObserverExactEnabled $s $f $before $false
            $on=Set-H3ObserverExactEnabled $s $f $off $true
            if($off.enabled -or -not $on.enabled -or $before.xml_sha256 -cne $on.xml_sha256){
                throw 'BAD_SWITCH'
            }
        }
        default {
            $failure=switch($case){
                'active' {$t.Active=$true; 'H3_OBSERVER_ACTIVE_INSTANCE'}
                'queued' {$t.Queued=$true; 'H3_OBSERVER_NOT_EXACT_IDLE'}
                'acl' {$t.Acl='different'; 'H3_OBSERVER_NOT_EXACT_IDLE'}
                'definition' {$t.Changed=$true; 'H3_OBSERVER_DRIFT_BEFORE_TRANSITION'}
                'new-instance' {$t.FailOnDisabled=$true; 'H3_OBSERVER_ACTIVE_INSTANCE'}
                'last-run' {$t.ChangeOnDisabled=$true; 'H3_OBSERVER_UNSTABLE'}
                'catchup' {
                    $t.Definition.Settings.StartWhenAvailable=$true
                    'H3_OBSERVER_DRIFT_BEFORE_TRANSITION'
                }
                default {throw 'unknown fixture'}
            }
            $caught=$false
            try { $null=Set-H3ObserverExactEnabled $s $f $before $false }
            catch { if ($_.Exception.Message -cne $failure) {throw}; $caught=$true }
            $writeExpected=$case -in @('new-instance','last-run')
            if(-not $caught -or $t.Enabled -eq $writeExpected) {
                throw 'UNEXPECTED_EFFECT_OR_NO_REFUSAL'
            }
        }
    }
} $Case
[Console]::WriteLine('INERT_PASS')
exit 0
"""


@pytest.mark.parametrize(
    "case",
    [
        "readiness", "switch", "active", "queued", "acl", "definition", "new-instance",
        "last-run", "catchup",
    ],
)
def test_observer_native_transport_with_all_scheduler_calls_mocked(tmp_path, case):
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        pytest.skip("PowerShell 7 unavailable")
    probe = tmp_path / "inert-observer.ps1"
    probe.write_text(_FIXTURE, encoding="ascii")
    result = subprocess.run(
        [pwsh, "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(probe), str(_MODULE), case],
        env={k: os.environ[k] for k in ("SystemRoot", "WINDIR", "PATH") if k in os.environ},
        capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert result.stdout.strip() == b"INERT_PASS"


@pytest.mark.parametrize("matches", [True, False])
def test_bridge_runs_in_clean_powershell_only_with_exact_module_pin(tmp_path, matches):
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        pytest.skip("PowerShell 7 unavailable")
    bridge = tmp_path / _BRIDGE.name
    bridge.write_bytes(_BRIDGE.read_bytes())
    module = b"""
function Get-H3NativeObserverReadiness($PlanSha256, $RequestId) {
    return @{plan_sha256=$PlanSha256; request_id=$RequestId; Task_writes=0}
}
Export-ModuleMember -Function Get-H3NativeObserverReadiness
"""
    bridge.with_name(_MODULE.name).write_bytes(module)
    pin = hashlib.sha256(module).hexdigest() if matches else "c" * 64
    result = subprocess.run(
        [
            pwsh, "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(bridge),
            "-ModuleSha256", pin, "-PlanSha256", "a" * 64, "-RequestId", "b" * 32,
        ],
        env={k: os.environ[k] for k in ("SystemRoot", "WINDIR") if k in os.environ},
        capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        timeout=15,
        check=False,
    )
    if matches:
        assert result.returncode == 0
        assert json.loads(result.stdout) == dict(
            plan_sha256="a" * 64, request_id="b" * 32, Task_writes=0
        )
    else:
        assert result.returncode == 1 and result.stdout == b""
        assert result.stderr.strip() == b"H3_OBSERVER_READINESS_UNAVAILABLE"
