# ruff: noqa: E501
"""Future pair installer tests with a fake Scheduler service and no runtime imports."""

import base64
import shutil
import subprocess
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "paper_native_future_pair.psm1"

HARNESS = r"""
$ErrorActionPreference = 'Stop'
$PSModuleAutoLoadingPreference = 'None'
Import-Module Microsoft.PowerShell.Management,Microsoft.PowerShell.Utility
foreach ($name in @(
    'Get-ScheduledTask', 'Get-ScheduledTaskInfo', 'Export-ScheduledTask', 'Register-ScheduledTask',
    'Set-ScheduledTask', 'Unregister-ScheduledTask', 'Enable-ScheduledTask',
    'Disable-ScheduledTask', 'Start-ScheduledTask', 'Stop-ScheduledTask',
    'New-ScheduledTask', 'New-ScheduledTaskAction', 'New-ScheduledTaskTrigger',
    'New-ScheduledTaskPrincipal', 'New-ScheduledTaskSettingsSet',
    'schtasks', 'schtasks.exe', 'New-Object', 'Start-Process', 'Open-Scheduler', 'Get-CimInstance'
)) { Set-Item "Function:$name" { throw 'UNEXPECTED_NATIVE_CALL' } }
$module = Import-Module -Name '__MODULE__' -PassThru
$scenario = '__SCENARIO__'
$sid = 'S-1-5-21-111111111-222222222-333333333-1001'
$sddl = 'O:SYG:SYD:(A;;FA;;;SY)'
$manifest = @{
    schema = 'PAPER_TASK_REGISTRATION_V1'; runtime_source_sha256 = ('a' * 64)
    runtime_release_sha256 = ('b' * 64); entry_name = 'fixture-entry'; exit_name = 'fixture-exit'
}
$log = [Collections.Generic.List[string]]::new()
$deadline = [DateTimeOffset]'2040-01-01T00:00:00Z'
$clock = @{ Now = $deadline.AddMinutes(-1) }
& $module {
    param($fixtureClock)
    $script:fixtureClock = $fixtureClock
    function script:Get-PaperFuturePairUtcNow { $script:fixtureClock.Now }
} $clock

function New-Fixture([string]$phase, [string]$date, [string]$role) {
    $name = "fixture-$phase"
    $start = "${date}T14:30:00Z"
    $end = "${date}T14:32:00Z"
    $item = @{
        name = $name; role = $role; executable = 'C:\fixture\pythonw.exe'
        arguments = "--phase $phase"; working_directory = 'C:\fixture'
        start_UTC = $start; last_start_exclusive_UTC = $end; execution_time_limit = 'PT2M'
    }
    $source = 'thericher-paper-owner:' + ('a' * 64) + ':' + ('b' * 64)
    $description = "TheRicher finite Paper owner $role ($name); no demand/catchup/repeat"
    $xml = @"
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
 <RegistrationInfo><Author>$sid</Author><URI>\$name</URI><Description>$description</Description><Source>$source</Source></RegistrationInfo>
 <Triggers><TimeTrigger><StartBoundary>$start</StartBoundary><EndBoundary>$end</EndBoundary><Enabled>true</Enabled></TimeTrigger></Triggers>
 <Principals><Principal id="Owner"><UserId>$sid</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
 <Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><StartWhenAvailable>false</StartWhenAvailable><AllowStartOnDemand>false</AllowStartOnDemand><Enabled>false</Enabled><Hidden>true</Hidden><WakeToRun>false</WakeToRun><ExecutionTimeLimit>PT2M</ExecutionTimeLimit><UseUnifiedSchedulingEngine>true</UseUnifiedSchedulingEngine></Settings>
 <Actions Context="Owner"><Exec><Command>$($item.executable)</Command><Arguments>$($item.arguments)</Arguments><WorkingDirectory>$($item.working_directory)</WorkingDirectory></Exec></Actions>
</Task>
"@
    $action = @{Type = 0; Path = $item.executable; Arguments = $item.arguments; WorkingDirectory = $item.working_directory}
    $trigger = @{Type = 1; Enabled = $true; StartBoundary = $start; EndBoundary = $end; Repetition = @{Interval = ''; Duration = ''}}
    $collections = foreach ($value in @($action, $trigger)) {
        $collection = [pscustomobject]@{Count = 1; Value = $value}
        $collection | Add-Member ScriptMethod Item { param($i) if ($i -ne 1) { throw 'INDEX' }; $this.Value }
        $collection
    }
    $definition = [pscustomobject]@{
        XmlText = ''; RegistrationInfo = @{Source = $source; Description = $description}
        Actions = $collections[0]; Triggers = $collections[1]
        Principal = @{UserId = $sid; LogonType = 3; RunLevel = 0}
        Settings = @{Enabled = $false; AllowDemandStart = $false; StartWhenAvailable = $false;
            Hidden = $true; WakeToRun = $false; UseUnifiedSchedulingEngine = $true;
            ExecutionTimeLimit = 'PT2M'; MultipleInstances = 2}
    }
    $document = [xml]::new()
    $document.PreserveWhitespace = $true
    $document.LoadXml($xml)
    @{
        Item = $item; Xml = $document.DocumentElement.OuterXml; Definition = $definition
        Base = $xml.Replace($description, 'unstamped').Replace("<Source>$source</Source>", '')
    }
}

$fixtures = @{
    entry = New-Fixture entry '2040-01-02' ENTRY
    exit = New-Fixture exit '2040-01-03' ORIGINAL_EXIT
}
$folder = [pscustomobject]@{Path = '\'; Tasks = @{}; Log = $log; Scenario = $scenario; Fixtures = $fixtures; Sid = $sid; Sddl = $sddl}
$folder | Add-Member ScriptMethod GetTask {
    param($name)
    if ($this.Tasks.ContainsKey($name)) { return $this.Tasks[$name] }
    if ($name -ceq 'fixture-entry' -and $this.Scenario -ceq 'absence-unknown') {
        throw [Runtime.InteropServices.COMException]::new('invented denied', -2147024891)
    }
    if ($name -ceq 'fixture-entry' -and $this.Scenario -ceq 'absence-null') { return }
    if ($this.Scenario -ceq 'native-absence') { throw [IO.FileNotFoundException]::new('invented missing') }
    throw [Runtime.InteropServices.COMException]::new('invented missing', -2147024894)
}
$folder | Add-Member ScriptMethod RegisterTaskDefinition {
    param($name, $definition, $flags, $user, $password, $logon, $acl)
    $phase = $name.Substring(8)
    if ($this.Tasks.ContainsKey($name) -or $flags -ne 58 -or $user -cne $this.Sid -or
        $null -ne $password -or $logon -ne 3 -or $acl -cne $this.Sddl -or
        $definition.XmlText -cne $this.Fixtures[$phase].Xml -or $definition.Settings.Enabled) {
        throw 'UNSAFE_NATIVE_CREATE'
    }
    $this.Log.Add("create:$phase")
    $task = [pscustomobject]@{
        Name = $name; Path = "\$name"; Xml = $definition.XmlText; Definition = $definition
        On = $false; Phase = $phase; Log = $this.Log; Scenario = $this.Scenario; Acl = $acl; State = 1
    }
    $task | Add-Member ScriptProperty Enabled { $this.On } {
        param($value)
        if ($value -isnot [bool] -or -not $value -or $this.On) { throw 'UNSAFE_ENABLE' }
        $this.Log.Add("enable:$($this.Phase)")
        $this.On = $true
        $this.State = 3
        $this.Xml = $this.Xml.Replace('<Enabled>false</Enabled>', '<Enabled>true</Enabled>')
        $this.Definition.XmlText = $this.Xml
        $this.Definition.Settings.Enabled = $true
        if ($this.Scenario -ceq "$($this.Phase)-enable-unknown") { throw 'INVENTED_LOST_ENABLE_RESPONSE' }
    }
    $task | Add-Member ScriptMethod GetSecurityDescriptor { param($mask) if ($mask -ne 7) { throw 'ACL_MASK' }; $this.Acl }
    $task | Add-Member ScriptMethod GetInstances { param($flags) if ($flags -ne 0) { throw 'INSTANCE_FLAGS' }; @{Count = 0} }
    foreach ($method in @('Run', 'RunEx', 'Stop', 'SetSecurityDescriptor')) {
        $task | Add-Member ScriptMethod $method { throw 'UNEXPECTED_TASK_EFFECT' }
    }
    if ($phase -ceq 'entry') {
        switch ($this.Scenario) {
            'xml-drift' { $task.Definition.XmlText = $task.Xml.Replace('<Author>', '<Author>foreign-') }
            'api-drift' { $task.Definition.Settings.AllowDemandStart = $true }
            'acl-drift' { $task.Acl = 'D:' }
        }
    }
    $this.Tasks[$name] = $task
    if ($this.Scenario -ceq "$phase-create-unknown") { throw 'INVENTED_LOST_CREATE_RESPONSE' }
    return 'REGISTRATION_RETURN_IS_NOT_READBACK'
}
$folder | Add-Member ScriptMethod DeleteTask { throw 'UNEXPECTED_DELETE' }
$service = [pscustomobject]@{Folder = $folder; Definitions = @($fixtures.exit.Definition, $fixtures.entry.Definition); Calls = 0}
$service | Add-Member ScriptMethod NewTask { param($flags) if ($flags -ne 0) { throw 'NEW_FLAGS' }; $this.Definitions[$this.Calls++] }
$service | Add-Member ScriptMethod GetFolder { param($root) if ($root -cne '\') { throw 'NOT_ROOT' }; $this.Folder }
$service | Add-Member ScriptMethod Connect { throw 'UNEXPECTED_CONNECT' }

$params = @{
    Service = $service; Manifest = $manifest; Entry = $fixtures.entry.Item; Exit = $fixtures.exit.Item
    EntryDisabledXml = $fixtures.entry.Base; ExitDisabledXml = $fixtures.exit.Base
    Sid = $sid; Sddl = $sddl; InstallDeadlineUtc = $deadline
    PrincipalIdentity = {
        param($native, $declared)
        if ($native -cne $sid -or $declared -cne $sid) { throw 'WRONG_IDENTITY' }
        @{resolved_equals_declared = $true; resolved_equals_current = $true}
    }
    ClaimInstallAttempt = {
        $log.Add('claim')
        if ($scenario -ceq 'claim-input-drift') {
            $manifest.entry_name = 'foreign-entry'
            $fixtures.entry.Item.name = 'foreign-entry'
            $fixtures.entry.Item.start_UTC = '2040-01-05T14:30:00Z'
        }
        $scenario -cne 'claim-denied'
    }
    VerifyReadback = {
        param($phase, $stage, $task)
        $log.Add("read:${stage}:$phase")
        $on = $stage -ceq 'ENABLED' -or ($stage -ceq 'EXIT_ONLY' -and $phase -ceq 'exit')
        $xml = $fixtures[$phase].Xml
        if ($on) { $xml = $xml.Replace('<Enabled>false</Enabled>', '<Enabled>true</Enabled>') }
        if ($scenario -ceq 'exit-only-denied' -and $stage -ceq 'EXIT_ONLY') { return $false }
        if ($scenario -ceq 'deadline-before-entry' -and $stage -ceq 'EXIT_ONLY') { $clock.Now = $deadline }
        if ($scenario -ceq 'final-denied' -and $stage -ceq 'ENABLED' -and $phase -ceq 'entry') { return 'true' }
        $task.Xml -ceq $xml -and $task.Definition.XmlText -ceq $xml -and
            $task.GetSecurityDescriptor(7) -ceq $sddl -and $task.GetInstances(0).Count -eq 0 -and
            $task.State -eq $(if ($on) { 3 } else { 1 })
    }
}
switch ($scenario) {
    'existing-entry' { $folder.Tasks['FIXTURE-ENTRY'] = [pscustomobject]@{Foreign = $true} }
    'expired' { $clock.Now = $deadline }
    'bad-utc' { $params.Entry.start_UTC = '2040-01-02T14:30:00' }
    'overlap' { $params.Entry.last_start_exclusive_UTC = '2040-01-03T14:30:01Z' }
    'start-at-deadline' { $params.InstallDeadlineUtc = [DateTimeOffset]$params.Entry.start_UTC }
    'enabled-template' { $params.EntryDisabledXml = $params.EntryDisabledXml.Replace('<Enabled>false</Enabled>', '<Enabled>true</Enabled>') }
}
$result = $null
$denial = ''
try { $result = Install-PaperNativeFuturePair @params } catch { $denial = $_.Exception.GetBaseException().Message }
if ($null -ne $result) { $result }
if ($denial) { $denial }
if ($scenario -clike '*-create-unknown' -or $scenario -clike '*-enable-unknown' -or $scenario -ceq 'final-denied') {
    $expected = switch ($scenario) {
        'exit-create-unknown' { @{ 'fixture-exit' = $false } }
        'entry-create-unknown' { @{ 'fixture-exit' = $false; 'fixture-entry' = $false } }
        'exit-enable-unknown' { @{ 'fixture-exit' = $true; 'fixture-entry' = $false } }
        default { @{ 'fixture-exit' = $true; 'fixture-entry' = $true } }
    }
    $checkRetained = {
        if ($folder.Tasks.Count -ne $expected.Count) { throw 'UNEXPECTED_RETAINED_COUNT' }
        foreach ($name in $expected.Keys) {
            if (-not $folder.Tasks.ContainsKey($name) -or $folder.Tasks[$name].Enabled -ne $expected[$name]) {
                throw 'UNEXPECTED_RETAINED_STATE'
            }
        }
    }
    & $checkRetained
    # Same authenticated plan, fresh constructor objects, same retained native state.
    $service.Definitions = @((New-Fixture exit '2040-01-03' ORIGINAL_EXIT).Definition,
        (New-Fixture entry '2040-01-02' ENTRY).Definition)
    $service.Calls = 0
    $retryDenial = ''
    try { $null = Install-PaperNativeFuturePair @params } catch { $retryDenial = $_.Exception.Message }
    if ($retryDenial -cne 'PAPER_FUTURE_PAIR_TARGET_PRESENT') { throw "UNEXPECTED_RETRY: $retryDenial" }
    & $checkRetained
}
$log -join ','
"""

CREATE = "claim,create:exit,create:entry"
DISABLED = CREATE + ",read:DISABLED:exit,read:DISABLED:entry"
EXIT = DISABLED + ",enable:exit"
EXIT_ONLY = EXIT + ",read:EXIT_ONLY:exit,read:EXIT_ONLY:entry"
FINAL = EXIT_ONLY + ",enable:entry,read:ENABLED:exit,read:ENABLED:entry"


@pytest.mark.parametrize(
    ("scenario", "outcome", "effects"),
    [
        ("success", "PAPER_FUTURE_PAIR_INSTALLED", FINAL),
        ("native-absence", "PAPER_FUTURE_PAIR_INSTALLED", FINAL),
        ("expired", "PAPER_FUTURE_PAIR_DEADLINE", ""),
        ("bad-utc", "PAPER_FUTURE_PAIR_UTC", ""),
        ("overlap", "PAPER_FUTURE_PAIR_WINDOW", ""),
        ("start-at-deadline", "PAPER_FUTURE_PAIR_WINDOW", ""),
        ("enabled-template", "PAPER_TASK_STAGE_ENABLED", ""),
        ("existing-entry", "PAPER_FUTURE_PAIR_TARGET_PRESENT", ""),
        ("absence-unknown", "PAPER_FUTURE_PAIR_ABSENCE_UNKNOWN", ""),
        ("absence-null", "PAPER_FUTURE_PAIR_TARGET_PRESENT", ""),
        ("claim-denied", "PAPER_FUTURE_PAIR_ATTEMPT", "claim"),
        ("claim-input-drift", "PAPER_FUTURE_PAIR_INSTALLED", FINAL),
        ("exit-create-unknown", "INVENTED_LOST_CREATE_RESPONSE", "claim,create:exit"),
        ("entry-create-unknown", "INVENTED_LOST_CREATE_RESPONSE", CREATE),
        ("xml-drift", "PAPER_FUTURE_PAIR_FULL_READBACK", DISABLED),
        ("acl-drift", "PAPER_FUTURE_PAIR_FULL_READBACK", DISABLED),
        ("api-drift", "PAPER_NATIVE_SETTINGS_API", CREATE + ",read:DISABLED:exit"),
        ("exit-enable-unknown", "INVENTED_LOST_ENABLE_RESPONSE", EXIT),
        ("entry-enable-unknown", "INVENTED_LOST_ENABLE_RESPONSE", EXIT_ONLY + ",enable:entry"),
        ("exit-only-denied", "PAPER_FUTURE_PAIR_FULL_READBACK", EXIT + ",read:EXIT_ONLY:exit"),
        ("deadline-before-entry", "PAPER_FUTURE_PAIR_DEADLINE", EXIT_ONLY),
        ("final-denied", "PAPER_FUTURE_PAIR_FULL_READBACK", FINAL),
    ],
)
def test_future_native_pair(scenario: str, outcome: str, effects: str) -> None:
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        pytest.skip("PowerShell 7 is required for the mocked installer")
    script = HARNESS.replace("__MODULE__", str(MODULE).replace("'", "''")).replace("__SCENARIO__", scenario)
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    result = subprocess.run(
        [pwsh, "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        capture_output=True,
        encoding="utf-8",
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr == ""
    assert result.stdout.splitlines() == [outcome, effects]
