from __future__ import annotations

import base64
import shutil
import subprocess
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "paper_task_registration.psm1"

# Literal readback oracle, independent of the module's expected-pair generator.
ENTRY_XML = (
    r"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.3" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Source>thericher-paper-owner:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef:fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210</Source>
    <Author>FixtureOperator</Author>
    <Description>TheRicher finite Paper owner ENTRY (fixture-entry); """
    r"""no demand/catchup/repeat</Description>
    <URI>\FixturePaper\fixture-entry</URI>
  </RegistrationInfo>
  <Triggers>
    <TimeTrigger id="one-shot">
      <StartBoundary>2040-01-03T09:30:00+09:00</StartBoundary>
      <EndBoundary>2040-01-03T09:32:00+09:00</EndBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="PaperOwner">
      <UserId>S-1-5-21-111111111-222222222-333333333-1001</UserId>
      <LogonType>S4U</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>false</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd><RestartOnIdle>false</RestartOnIdle></IdleSettings>
    <AllowStartOnDemand>false</AllowStartOnDemand>
    <Enabled>false</Enabled>
    <Hidden>true</Hidden>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT2M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="PaperOwner">
    <Exec>
      <Command>C:\Fixture Runtime\pythonw.exe</Command>
      <Arguments>-I &quot;owner.py&quot; --phase entry --label &quot;A &amp; B&quot;</Arguments>
      <WorkingDirectory>C:\Fixture Runtime</WorkingDirectory>
    </Exec>
  </Actions>
</Task>"""
)

EXIT_XML = (
    ENTRY_XML.replace(
        "TheRicher finite Paper owner ENTRY (fixture-entry); no demand/catchup/repeat",
        "TheRicher finite Paper owner ORIGINAL_EXIT (fixture-exit); no demand/catchup/repeat",
    )
    .replace(r"\FixturePaper\fixture-entry", r"\FixturePaper\fixture-exit")
    .replace("09:30:00+09:00", "15:20:00+09:00")
    .replace("09:32:00+09:00", "15:22:00+09:00")
    .replace("--phase entry", "--phase exit")
)

HARNESS = r"""
$ErrorActionPreference = 'Stop'
$PSModuleAutoLoadingPreference = 'None'
Import-Module -Name Microsoft.PowerShell.Management
foreach ($name in @(
    'Get-ScheduledTask', 'Get-ScheduledTaskInfo', 'Export-ScheduledTask', 'Register-ScheduledTask',
    'Set-ScheduledTask', 'Unregister-ScheduledTask', 'Enable-ScheduledTask',
    'Disable-ScheduledTask', 'Start-ScheduledTask', 'Stop-ScheduledTask',
    'New-ScheduledTask', 'New-ScheduledTaskAction',
    'New-ScheduledTaskTrigger', 'New-ScheduledTaskPrincipal', 'New-ScheduledTaskSettingsSet',
    'schtasks', 'schtasks.exe', 'New-Object', 'Start-Process', 'Open-Scheduler'
)) {
    Set-Item "Function:$name" { throw 'UNEXPECTED_SCHEDULER_CALL' }
}
Import-Module -Name '__MODULE__'

$manifest = @{
    schema = 'PAPER_TASK_REGISTRATION_V1'
    runtime_source_sha256 = '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef'
    runtime_release_sha256 = 'fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210'
    entry_name = 'fixture-entry'
    exit_name = 'fixture-exit'
}
$fixture = @{
    'fixture-entry' = @'
__ENTRY_XML__
'@
    'fixture-exit' = @'
__EXIT_XML__
'@
}
$roles = @{ 'fixture-entry' = 'ENTRY'; 'fixture-exit' = 'ORIGINAL_EXIT' }
$taskNames = @('fixture-exit', 'fixture-entry')
$store = @{}
$events = [Collections.Generic.List[string]]::new()
$fault = '__FAULT__'

function Find-TaskField([xml]$Document, [string]$Path) {
    $ns = [Xml.XmlNamespaceManager]::new($Document.NameTable)
    $ns.AddNamespace('t', 'http://schemas.microsoft.com/windows/2004/02/mit/task')
    return $Document.SelectSingleNode($Path, $ns)
}

# In-memory API only: XML DOM serialization and 0/1 booleans are fixture normalization,
# not evidence of native Scheduler exports, XML acceptance, ACLs, or runtime admission.
function Register-FakeTask([string]$Name, [string]$Xml) {
    if ($store.ContainsKey($Name)) { throw "Duplicate registration: $Name" }
    $store[$Name] = [xml]$Xml
    $events.Add("register:$Name")
}

function Enable-FakeTask([string]$Name) {
    $enabled = Find-TaskField $store[$Name] '/t:Task/t:Settings/t:Enabled'
    $enabled.InnerText = 'true'
    $events.Add("enable:$Name")
}

function Export-FakeTask([string]$Name, [string]$Stage) {
    $export = [xml]$store[$Name].OuterXml
    $enabled = Find-TaskField $export '/t:Task/t:Settings/t:Enabled'
    $enabled.InnerText = if ($enabled.InnerText -ceq 'true') { '1' } else { '0' }
    if ($Stage -ceq 'EXIT_ONLY' -and $Name -ceq 'fixture-exit') {
        switch -CaseSensitive ($fault) {
            'wrong-description' {
                $description = Find-TaskField $export '/t:Task/t:RegistrationInfo/t:Description'
                $description.InnerText = 'Unexpected fixture owner'
            }
            'missing-source' {
                $source = Find-TaskField $export '/t:Task/t:RegistrationInfo/t:Source'
                $null = $source.ParentNode.RemoveChild($source)
            }
            'disabled-exit' { $enabled.InnerText = '0' }
        }
    }
    $events.Add("read:${Stage}:$Name")
    return $export.OuterXml
}

function Assert-PairReadback([string]$Stage, [string[]]$EnabledNames) {
    foreach ($name in $taskNames) {
        $observed = Export-FakeTask $name $Stage
        Assert-PaperTaskRegistrationXml -Manifest $manifest -Stage $Stage -Role $roles[$name] `
            -TaskName $name -Xml $observed

        # Also detect writer drift in fields outside the registration assertion's scope.
        $expected = [xml]$fixture[$name]
        $enabled = Find-TaskField $expected '/t:Task/t:Settings/t:Enabled'
        $enabled.InnerText = if ($name -cin $EnabledNames) { '1' } else { '0' }
        if (([xml]$observed).DocumentElement.OuterXml -cne $expected.DocumentElement.OuterXml) {
            throw "Unexpected definition: ${Stage}:$name"
        }
    }
}

$expectedError = @{
    'none' = $null
    'wrong-description' = 'PAPER_TASK_XML_MISMATCH_Description'
    'missing-source' = 'PAPER_TASK_XML_MISSING_Source'
    'disabled-exit' = 'PAPER_TASK_STAGE_ENABLED'
}[$fault]
$rejected = $false
try {
    foreach ($name in $taskNames) {
        $base = [xml]$fixture[$name]
        $description = Find-TaskField $base '/t:Task/t:RegistrationInfo/t:Description'
        $description.InnerText = 'Unstamped template'
        $source = Find-TaskField $base '/t:Task/t:RegistrationInfo/t:Source'
        $source.InnerText = 'Unstamped source'
        $stamped = Set-PaperTaskRegistrationXml -Manifest $manifest -Stage DISABLED `
            -Role $roles[$name] -TaskName $name -Xml $base.OuterXml
        Register-FakeTask $name $stamped
    }
    Assert-PairReadback 'DISABLED' @()
    Enable-FakeTask 'fixture-exit'
    Assert-PairReadback 'EXIT_ONLY' @('fixture-exit')
    Enable-FakeTask 'fixture-entry'
    Assert-PairReadback 'ENABLED' @('fixture-exit', 'fixture-entry')
} catch {
    if ($null -eq $expectedError -or $_.Exception.Message -cne $expectedError) { throw }
    $rejected = $true
}
if ($rejected -ne ($null -ne $expectedError)) { throw "Unexpected rejection result: $fault" }

$expectedEvents = @(
    'register:fixture-exit', 'register:fixture-entry',
    'read:DISABLED:fixture-exit', 'read:DISABLED:fixture-entry',
    'enable:fixture-exit', 'read:EXIT_ONLY:fixture-exit'
)
if (-not $rejected) {
    $expectedEvents += @(
        'read:EXIT_ONLY:fixture-entry', 'enable:fixture-entry',
        'read:ENABLED:fixture-exit', 'read:ENABLED:fixture-entry'
    )
}
if (($events -join ',') -cne ($expectedEvents -join ',')) { throw "Unexpected sequence: $events" }
'PASS'
"""


@pytest.mark.parametrize("fault", ["none", "wrong-description", "missing-source", "disabled-exit"])
def test_staged_registration_handoff(fault: str) -> None:
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        pytest.skip("PowerShell 7 is required for the registration handoff fixture")

    script = (
        HARNESS.replace("__MODULE__", str(MODULE).replace("'", "''"))
        .replace("__ENTRY_XML__", ENTRY_XML)
        .replace("__EXIT_XML__", EXIT_XML)
        .replace("__FAULT__", fault)
    )
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    result = subprocess.run(
        [pwsh, "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        capture_output=True,
        encoding="utf-8",
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "PASS", result.stdout + result.stderr
