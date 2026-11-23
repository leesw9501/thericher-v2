from __future__ import annotations

import base64
import shutil
import subprocess
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "paper_task_registration.psm1"

HARNESS = r"""
$ErrorActionPreference = 'Stop'
$PSModuleAutoLoadingPreference = 'None'
Import-Module -Name Microsoft.PowerShell.Management, Microsoft.PowerShell.Utility
# Trap all Scheduler and process/object entry points. The fake below only stores strings.
foreach ($command in @(
    'Get-ScheduledTask', 'Get-ScheduledTaskInfo', 'Export-ScheduledTask',
    'Register-ScheduledTask', 'Set-ScheduledTask', 'Unregister-ScheduledTask',
    'Enable-ScheduledTask', 'Disable-ScheduledTask', 'Start-ScheduledTask',
    'Stop-ScheduledTask', 'New-ScheduledTask', 'New-ScheduledTaskAction',
    'New-ScheduledTaskTrigger', 'New-ScheduledTaskPrincipal', 'New-ScheduledTaskSettingsSet',
    'schtasks', 'schtasks.exe', 'New-Object', 'Start-Process', 'Open-Scheduler'
)) {
    Set-Item "Function:$command" { throw 'UNEXPECTED_SCHEDULER_CALL' }
}
Import-Module -Name '__MODULE__'

$manifest = @{
    schema = 'PAPER_TASK_REGISTRATION_V1'
    runtime_source_sha256 = 'a' * 64
    runtime_release_sha256 = 'b' * 64
    entry_name = 'invented-entry'
    exit_name = 'invented-exit'
}
$entry = @{
    Manifest = $manifest
    Stage = 'ENABLED'
    Role = 'ENTRY'
    TaskName = 'invented-entry'
}
$baseXml = @'
<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task" version="1.3">
  <RegistrationInfo>
    <Description>Legacy installer description</Description>
    <SecurityDescriptor>opaque</SecurityDescriptor>
  </RegistrationInfo>
  <Triggers><TimeTrigger><StartBoundary>2030-01-02T14:30:00Z</StartBoundary></TimeTrigger></Triggers>
  <Principals><Principal id="owner"><UserId>invented</UserId></Principal></Principals>
  <Settings>
    <Enabled>false</Enabled>
    <AllowDemandStart>false</AllowDemandStart>
    <StartWhenAvailable>false</StartWhenAvailable>
  </Settings>
  <Actions Context="owner">
    <Exec><Command>pythonw.exe</Command><Arguments>-I &amp; invented</Arguments></Exec>
  </Actions>
</Task>
'@
$enabledXml = $baseXml.Replace('<Enabled>false</Enabled>', '<Enabled>true</Enabled>')

function Expect-Rejection([string]$Code, [scriptblock]$Call) {
    try { $null = & $Call } catch {
        if ($_.Exception.Message -ceq $Code) { return }
        throw
    }
    throw "Expected rejection: $Code"
}
"""


def run_powershell(case: str) -> None:
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        pytest.skip("PowerShell 7 is required for the native registration contract")
    harness = HARNESS.replace("__MODULE__", str(MODULE).replace("'", "''"))
    encoded = base64.b64encode((harness + case).encode("utf-16-le")).decode("ascii")
    result = subprocess.run(
        [pwsh, "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        capture_output=True,
        encoding="utf-8",
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "PASS", result.stdout + result.stderr


def test_pair_install_readback_runtime_handoff() -> None:
    run_powershell(r"""
$fakeTasks = @{}
$manifestJson = ConvertTo-Json -InputObject $manifest -Compress
$installerManifest = ConvertFrom-Json -InputObject $manifestJson -AsHashtable
$runtimeManifest = ConvertFrom-Json -InputObject $manifestJson -AsHashtable
foreach ($stage in @('DISABLED', 'EXIT_ONLY', 'ENABLED')) {
    $pair = @(Get-PaperTaskRegistrationPair -Manifest $installerManifest -Stage $stage)
    if ($pair.Count -ne 2 -or $pair[0].Role -cne 'ORIGINAL_EXIT' -or $pair[1].Role -cne 'ENTRY' -or
        $pair[0].Name -cne 'invented-exit' -or $pair[1].Name -cne 'invented-entry') {
        throw 'Wrong pair'
    }
    $states = @{ DISABLED = 'False,False'; EXIT_ONLY = 'True,False'; ENABLED = 'True,True' }
    if (($pair.Enabled -join ',') -cne $states[$stage]) { throw 'Wrong stage' }

    foreach ($row in $pair) {
        $slot = @{ Stage = $stage; Role = $row.Role; TaskName = $row.Name }
        if ($stage -ceq 'DISABLED') {
            $slot.Manifest = $installerManifest
            $fakeTasks[$row.Name] = Set-PaperTaskRegistrationXml @slot -Xml $baseXml
        } elseif ($row.Enabled) {
            # Mimic enablement, not regeneration of the installed registration fields.
            $fakeTasks[$row.Name] = $fakeTasks[$row.Name].Replace(
                '<Enabled>false</Enabled>', '<Enabled>true</Enabled>'
            )
        }
        $slot.Manifest = $runtimeManifest
        Assert-PaperTaskRegistrationXml @slot -Xml $fakeTasks[$row.Name]
        $expectedSource = 'thericher-paper-owner:' + ('a' * 64) + ':' + ('b' * 64)
        $expectedDescription = "TheRicher finite Paper owner $($row.Role) ($($row.Name)); " +
            'no demand/catchup/repeat'
        $original = if ($row.Enabled) { $enabledXml } else { $baseXml }
        $unchanged = $fakeTasks[$row.Name].Replace(
            "<Description>$expectedDescription</Description>",
            '<Description>Legacy installer description</Description>'
        ).Replace("<Source>$expectedSource</Source>", '')
        if ($unchanged -cne $original) { throw 'Changed base XML or inexact registration metadata' }
    }
}
$installedEntry = $fakeTasks[$entry.TaskName]
Assert-PaperTaskRegistrationXml @entry -Xml $installedEntry
if ((Set-PaperTaskRegistrationXml @entry -Xml $installedEntry) -cne $installedEntry) {
    throw 'Stamping is not idempotent'
}
'PASS'
""")


def test_manifest_and_slot_fail_closed() -> None:
    run_powershell(r"""
foreach ($change in @(
    { $m.Remove('runtime_release_sha256') },
    { $m['unbound_field'] = 'unexpected' },
    { $m.Remove('entry_name'); $m['Entry_Name'] = 'invented-entry' },
    { $m['entry_name'] = @('invented-entry') }
)) {
    $m = $manifest.Clone()
    $null = & $change
    Expect-Rejection 'PAPER_TASK_MANIFEST_FIELDS' { Get-PaperTaskRegistrationPair $m 'DISABLED' }
}
$m = $manifest.Clone()
$m['schema'] = 'paper_task_registration_v1'
Expect-Rejection 'PAPER_TASK_MANIFEST_SCHEMA' { Get-PaperTaskRegistrationPair $m 'DISABLED' }
foreach ($key in @('runtime_source_sha256', 'runtime_release_sha256')) {
    foreach ($bad in @('A' * 64; 'a' * 63; ('a' * 64) + "`n")) {
        $m = $manifest.Clone()
        $m[$key] = $bad
        Expect-Rejection 'PAPER_TASK_MANIFEST_DIGEST' {
            Get-PaperTaskRegistrationPair $m 'DISABLED'
        }
    }
}
foreach ($bad in @('INVENTED-EXIT', '\other-folder\target', 'entry name')) {
    $m = $manifest.Clone()
    $m['entry_name'] = $bad
    Expect-Rejection 'PAPER_TASK_MANIFEST_NAMES' { Get-PaperTaskRegistrationPair $m 'DISABLED' }
}
foreach ($stage in @('entry_only', 'ENTRY_ONLY', 'disabled')) {
    Expect-Rejection 'PAPER_TASK_PAIR_STAGE' { Get-PaperTaskRegistrationPair $manifest $stage }
}
$installed = Set-PaperTaskRegistrationXml @entry -Xml $enabledXml
Expect-Rejection 'PAPER_TASK_ROLE_NAME' {
    Assert-PaperTaskRegistrationXml @entry -TaskName INVENTED-ENTRY -Xml $installed
}
Expect-Rejection 'PAPER_TASK_ROLE_NAME' {
    Assert-PaperTaskRegistrationXml @entry -Role ORIGINAL_EXIT -Xml $installed
}
'PASS'
""")


def test_readback_rejects_legacy_or_drifted_registration() -> None:
    run_powershell(r"""
$installed = Set-PaperTaskRegistrationXml @entry -Xml $enabledXml
$source = '<Source>thericher-paper-owner:' + ('a' * 64) + ':' + ('b' * 64) + '</Source>'
Expect-Rejection 'PAPER_TASK_XML_MISMATCH_Description' {
    Assert-PaperTaskRegistrationXml @entry -Xml $enabledXml
}
Expect-Rejection 'PAPER_TASK_XML_MISSING_Source' {
    Assert-PaperTaskRegistrationXml @entry -Xml ($installed.Replace($source, ''))
}
foreach ($key in @('runtime_source_sha256', 'runtime_release_sha256')) {
    $m = $manifest.Clone()
    $m[$key] = 'c' * 64
    Expect-Rejection 'PAPER_TASK_XML_MISMATCH_Source' {
        Assert-PaperTaskRegistrationXml @entry -Manifest $m -Xml $installed
    }
}
Expect-Rejection 'PAPER_TASK_XML_MISMATCH_Description' {
    Assert-PaperTaskRegistrationXml @entry -Xml ($installed.Replace('finite Paper', 'finite paper'))
}
foreach ($replacement in @(
    ($source + $source),
    $source.Replace('<Source>', '<Source xmlns="urn:foreign">'),
    $source.Replace('Source', 'source'),
    $source.Replace('<Source>', '<Source tag="unexpected">'),
    $source.Replace('</Source>', '<!-- hidden --></Source>')
)) {
    Expect-Rejection 'PAPER_TASK_XML_SHAPE_Source' {
        Assert-PaperTaskRegistrationXml @entry -Xml ($installed.Replace($source, $replacement))
    }
}
Expect-Rejection 'PAPER_TASK_XML_INVALID' {
    Set-PaperTaskRegistrationXml @entry -Xml ('<!DOCTYPE Task []>' + $enabledXml)
}
Expect-Rejection 'PAPER_TASK_STAGE_ENABLED' { Set-PaperTaskRegistrationXml @entry -Xml $baseXml }
Expect-Rejection 'PAPER_TASK_STAGE_ENABLED' {
    Assert-PaperTaskRegistrationXml @entry -Stage EXIT_ONLY -Xml $installed
}
Expect-Rejection 'PAPER_TASK_XML_MISSING_Enabled' {
    Assert-PaperTaskRegistrationXml @entry -Xml ($installed.Replace('<Enabled>true</Enabled>', ''))
}
'PASS'
""")
