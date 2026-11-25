# ruff: noqa: E501
"""Run the real readback callback through the future pair's in-memory installer."""

import shutil
import subprocess
from pathlib import Path

import pytest

from test_paper_native_future_pair import CREATE, DISABLED, EXIT, FINAL, HARNESS, MODULE

READBACK = MODULE.with_name("paper_native_pair_readback.psm1")

CALLBACK = r"""
Import-Module -Name '__READBACK__'
$scheduler = [pscustomobject]@{
    Connected = $true
    TargetServer = [Environment]::MachineName
    ConnectedUser = [Environment]::UserName
    ConnectedDomain = [Environment]::UserDomainName
    Scenario = $scenario
    EntryPath = '\' + $manifest.entry_name
    Calls = 0
    Folder = $folder
}
if ($scenario -ceq 'remote-scheduler') { $scheduler.TargetServer += '-other' }
if ($scenario -ceq 'foreign-scheduler') { $scheduler.ConnectedUser += '-other' }
$scheduler | Add-Member ScriptMethod GetFolder {
    param($path)
    if ($path -cne '\') { throw 'UNEXPECTED_SCHEDULER_ROOT' }
    return $this.Folder
}
$scheduler | Add-Member ScriptMethod GetRunningTasks {
    param($flags)
    if ($flags -isnot [int] -or $flags -ne 1) { throw 'HIDDEN_RUNNING_FLAGS' }
    $this.Calls++
    switch ($this.Scenario) {
        'running-rpc-error' { throw 'INVENTED_RUNNING_RPC_ERROR' }
        'running-null' { return $null }
        'running-text-count' { return [pscustomobject]@{Count = '0'} }
    }
    $items = @()
    if ($this.Scenario.StartsWith('active-') -and $this.Scenario -cne 'active-absent') {
        $guid = '8ce48d27-67b2-4bcd-97c7-31dc4e8dcaa1'
        if ($this.Scenario -ceq 'active-guid-change' -and $this.Calls -eq 2) {
            $guid = '8ce48d27-67b2-4bcd-97c7-31dc4e8dcaa2'
        }
        $row = [pscustomobject]@{Path = $this.EntryPath; State = 4; EnginePID = [uint32]13; InstanceGuid = $guid}
        if ($this.Scenario -ceq 'active-queued') { $row.State = 2 }
        if ($this.Scenario -ceq 'active-zero-guid') { $row.InstanceGuid = [guid]::Empty.ToString() }
        $items += $row
        if ($this.Scenario -ceq 'active-duplicate') { $items += $row }
    }
    switch ($this.Scenario) {
        'hidden-entry' { $items += [pscustomobject]@{Path = $this.EntryPath} }
        'hidden-case-variant' { $items += [pscustomobject]@{Path = $this.EntryPath.ToUpperInvariant()} }
        'hidden-other' { $items += [pscustomobject]@{Path = '\nested' + $this.EntryPath} }
        'hidden-arrived' {
            if ($this.Calls -eq 4) { $items += [pscustomobject]@{Path = $this.EntryPath} }
        }
        'malformed-running-path' { $items += [pscustomobject]@{Path = 42} }
        'running-changed-count' { $items += [pscustomobject]@{Path = '\unrelated'} }
    }
    $collection = [pscustomobject]@{
        Count = $items.Count; Items = $items; Scenario = $this.Scenario
    }
    $collection | Add-Member ScriptMethod Item {
        param($index)
        if ($index -lt 1 -or $index -gt $this.Items.Count) { throw 'RUNNING_COLLECTION_INDEX' }
        if ($this.Scenario -ceq 'running-changed-count') { $this.Count = 2 }
        return $this.Items[$index - 1]
    }
    return $collection
}
if ($scenario.StartsWith('active-')) {
    $task = [pscustomobject]@{ Path = $scheduler.EntryPath; State = 4; Enabled = $true }
    $expected = if ($scenario -ceq 'active-foreign-pid') { 14 } else { 13 }
    $folder.Tasks[$manifest.entry_name] = $task
    if ($scenario -ceq 'active-task-ready') {
        # The caller's stale object must not override the local readback.
        $folder.Tasks[$manifest.entry_name] = [pscustomobject]@{
            Path = $scheduler.EntryPath; State = 3; Enabled = $true
        }
    }
    try {
        $proof = Get-PaperNativeActiveInstance -Scheduler $scheduler -Task $task `
            -ExpectedPath $scheduler.EntryPath -ExpectedEnginePid $expected
        if ($proof.Claim -cne 'SCHEDULER_INSTANCE_OBSERVED' -or
            $proof.Matches -ne 1 -or $proof.EnginePid -cne 13 -or
            $proof.InstanceGuid -ne [guid]'8ce48d27-67b2-4bcd-97c7-31dc4e8dcaa1' -or $scheduler.Calls -ne 2) {
            throw 'ACTIVE_PROOF_SHAPE'
        }
        'ACTIVE_OK'
    } catch { $_.Exception.Message }
    return
}
if ($scenario.StartsWith('profile-')) {
    $s = "O:${sid}G:${sid}D:P(A;;FA;;;$sid)(A;;FA;;;SY)(A;;FA;;;BA)"
    $drafts = @{}
    foreach ($phase in @('entry','exit')) {
        $xml = $fixtures[$phase].Xml -creplace '<URI>[^<]+</URI>', ''
        $xml = $xml.Replace('</RegistrationInfo>',"<SecurityDescriptor>$s</SecurityDescriptor></RegistrationInfo>")
        $xml = $xml.Replace('</Settings>',('<AllowHardTerminate>true</AllowHardTerminate>' +
            '<RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable><RunOnlyIfIdle>false</RunOnlyIfIdle>' +
            '<DisallowStartOnRemoteAppSession>false</DisallowStartOnRemoteAppSession><Priority>7</Priority>' +
            '<DisallowStartIfOnBatteries>true</DisallowStartIfOnBatteries>' +
            '<StopIfGoingOnBatteries>true</StopIfGoingOnBatteries><IdleSettings /></Settings>'))
        $drafts[$phase] = $xml
    }
    if ($scenario -ceq 'profile-missing-security') {
        $drafts.entry = $drafts.entry -creplace '<SecurityDescriptor>[^<]+</SecurityDescriptor>', ''
    }
    if ($scenario -ceq 'profile-default-drift') {
        $drafts.entry = $drafts.entry.Replace('<Priority>7</Priority>','<Priority>4</Priority>')
    }
    if ($scenario -ceq 'profile-principal-drift') {
        $drafts.entry = $drafts.entry.Replace("<UserId>$sid</UserId>",'<UserId>S-1-5-21-1-2-3-513</UserId>')
    }
    if ($scenario -ceq 'profile-non-utc-draft') {
        $drafts.entry = $drafts.entry.Replace('14:30:00Z','14:30:00')
    }
    try {
        $p = New-PaperNativeProtectedProfile -Manifest $manifest -EntryDraftXml $drafts.entry `
            -ExitDraftXml $drafts.exit -Sid $sid -Scheduler $scheduler
        if ($p.RegistrationSddl -cne $s -or $p.VerifyReadback -isnot [scriptblock]) { throw 'PROFILE_WRONG_RESULT' }
        'PROFILE_OK'
    } catch { $_.Exception.Message }
    return
}
try {
    $pins = @{}
    foreach ($phase in @('entry', 'exit')) {
        foreach ($stage in @('DISABLED', 'EXIT_ONLY', 'ENABLED')) {
            $export = $fixtures[$phase].Xml
            if ($stage -ceq 'ENABLED' -or ($stage -ceq 'EXIT_ONLY' -and $phase -ceq 'exit')) {
                $export = $export.Replace('<Enabled>false</Enabled>', '<Enabled>true</Enabled>')
            }
            $native = $export.Replace('</Settings>', '<Priority>7</Priority></Settings>')
            if ($scenario -ceq 'export-enabled-omits') {
                $export = $export.Replace('<Enabled>true</Enabled><Hidden>', '<Hidden>')
            }
            $pins["${stage}:$phase"] = @{ ExportXml = $export; DefinitionXml = $native }
        }
    }
    if ($scenario -ceq 'missing-stage') { $pins.Remove('ENABLED:entry') }
    if ($scenario -ceq 'missing-surface') { $pins['EXIT_ONLY:exit'].Remove('DefinitionXml') }
    $fixed = New-PaperNativePairReadback -Manifest $manifest `
        -ExpectedStageXml $pins `
        -EntryAcl7 $entryExpectedAcl -ExitAcl7 $sddl -Scheduler $scheduler
} catch {
    $_.Exception.Message
    return
}
if ($scenario -ceq 'scope') {
    foreach ($bad in @(@('EXIT', 'DISABLED'), @('exit', 'disabled'), @('other', 'ENABLED'))) {
        $proof = & $fixed $bad[0] $bad[1] $null
        if ($proof -isnot [bool] -or $proof) { throw 'UNEXPECTED_SCOPE_PROOF' }
    }
}
$params.VerifyReadback = {
    param($phase, $stage, $task)
    $log.Add("read:${stage}:$phase")
    if ($scenario -ceq 'wrong-exit-only-state' -and $stage -ceq 'EXIT_ONLY' -and $phase -ceq 'exit') {
        $task.State = 2
    }
    if ($scenario -ceq 'doctype' -and $phase -ceq 'entry') {
        $task.Xml = '<!DOCTYPE Task [<!ENTITY x "invented">]>' + $task.Xml
    }
    if ($scenario -ceq 'definition-enabled-omits' -and $stage -ceq 'EXIT_ONLY' -and $phase -ceq 'exit') {
        $task.Definition.XmlText = $task.Definition.XmlText.Replace('<Enabled>true</Enabled><Hidden>', '<Hidden>')
    }
    & $fixed $phase $stage $task
}
"""

XML_AND_STATE_CASES = r"""
            'registered-xml-drift' { $task.Xml = $task.Xml.Replace('<Author>', '<Author>foreign-') }
            'matched-bad' { $task.Xml = $task.Definition.XmlText }
            'native-default-drift' { $task.Definition.XmlText = $task.Definition.XmlText.Replace('<Priority>7</Priority>', '<Priority>4</Priority>') }
            'extra-setting' { $task.Xml = $task.Xml.Replace('</Settings>', '<Priority>4</Priority></Settings>') }
            'text-space' { $task.Xml = $task.Xml.Replace('--phase entry', '--phase  entry') }
            'extra-trigger' { $task.Xml = $task.Xml.Replace('</Triggers>', '<BootTrigger /></Triggers>') }
            'processing-instruction' { $task.Xml = '<?invented data?>' + $task.Xml }
            'xml-comment' { $task.Xml = $task.Xml.Replace('</Settings>', '<!-- drift --></Settings>') }
            'deserializer-option' { $task.Xml = $task.Xml.Replace('<Actions ', '<Actions xml:space="preserve" ') }
            'unsafe-state' { $task.State = '1' }
            'layout-only' {
                $task.Xml = '<?xml version="1.0"?>' + $task.Xml.Replace('><', ">`n<")
            }
            'different-expected-acl' { $task.Acl = 'O:SYG:BAD:(A;;FA;;;SY)' }
            'acl-ordinal' { $task.Acl = $task.Acl.ToLowerInvariant() }
"""

INSTANCE_METHOD = r"""
    $task | Add-Member ScriptMethod GetInstances {
        param($flags)
        if ($flags -ne 0) { throw 'INSTANCE_FLAGS' }
        if ($this.Phase -ceq 'entry') {
            switch ($this.Scenario) {
                'instance' { return [pscustomobject]@{Count = 1} }
                'null-instances' { return $null }
                'unknown-count' { return [pscustomobject]@{Count = $null} }
                'missing-count' { return [pscustomobject]@{} }
                'text-count' { return [pscustomobject]@{Count = '0'} }
                'instance-error' { throw 'INVENTED_RPC_FAILURE' }
            }
        }
        return [pscustomobject]@{Count = 0}
    }
"""


def fixture_script(scenario: str) -> str:
    setup, rest = HARNESS.split("    VerifyReadback = {\n", 1)
    _, execute = rest.split("\n}\nswitch ($scenario)", 1)
    inputs = r"""
$entryExpectedAcl = $sddl
switch ($scenario) {
    'bad-expectation-xml' { $fixtures.entry.Xml = $fixtures.exit.Xml }
    'bad-expectation-acl' { $entryExpectedAcl = 'D:(A;;FA;;;SY)' }
    'different-expected-acl' { $entryExpectedAcl = 'O:SYG:BAD:(A;;FA;;;SY)' }
}
"""
    return (
        (setup + "}\n" + inputs + CALLBACK + "\nswitch ($scenario)" + execute)
        .replace(
            "    $task | Add-Member ScriptMethod GetInstances "
            "{ param($flags) if ($flags -ne 0) { throw 'INSTANCE_FLAGS' }; @{Count = 0} }",
            INSTANCE_METHOD,
        )
        .replace("        switch ($this.Scenario) {\n            'xml-drift'", "        switch ($this.Scenario) {\n"
                 + XML_AND_STATE_CASES + "            'xml-drift'")
        .replace(
            "    $task | Add-Member ScriptProperty Enabled",
            "    $task.Definition.XmlText = $task.Xml.Replace('</Settings>', '<Priority>7</Priority></Settings>')\n"
            "    $task | Add-Member ScriptProperty Enabled",
        )
        .replace(
            "$this.Definition.XmlText = $this.Xml",
            "$this.Definition.XmlText = $this.Definition.XmlText.Replace('<Enabled>false</Enabled>', '<Enabled>true</Enabled>')",
        )
        .replace(
            "        $this.Definition.Settings.Enabled = $true",
            "        if ($this.Scenario -ceq 'export-enabled-omits') {\n"
            "            $this.Xml = $this.Xml.Replace('<Enabled>true</Enabled><Hidden>', '<Hidden>')\n"
            "        }\n"
            "        $this.Definition.Settings.Enabled = $true",
        )
        .replace("__MODULE__", str(MODULE).replace("'", "''"))
        .replace("__READBACK__", str(READBACK).replace("'", "''"))
        .replace("__SCENARIO__", scenario)
    )


@pytest.mark.parametrize(
    ("scenario", "lines"),
    [
        *[(case, ["PAPER_FUTURE_PAIR_INSTALLED", FINAL]) for case in (
            "success", "scope", "layout-only", "different-expected-acl", "claim-input-drift", "export-enabled-omits",
            "hidden-other",
        )],
        *[(case, ["PAPER_PAIR_READBACK_EXPECTATION"]) for case in (
            "bad-expectation-xml", "bad-expectation-acl", "missing-stage", "missing-surface"
        )],
        *[(case, ["PAPER_FUTURE_PAIR_FULL_READBACK", DISABLED]) for case in (
            "registered-xml-drift", "matched-bad", "native-default-drift", "xml-drift", "extra-setting", "text-space", "extra-trigger",
            "doctype", "processing-instruction", "xml-comment", "deserializer-option", "unsafe-state",
            "acl-drift", "acl-ordinal", "instance", "null-instances", "unknown-count", "missing-count", "text-count",
            "instance-error",
            "hidden-entry", "hidden-case-variant", "hidden-arrived",
        )],
        *[(case, ["PAPER_FUTURE_PAIR_FULL_READBACK", CREATE + ",read:DISABLED:exit"]) for case in (
            "running-rpc-error", "running-null", "running-text-count", "running-changed-count",
            "malformed-running-path", "remote-scheduler", "foreign-scheduler",
        )],
        ("wrong-exit-only-state", ["PAPER_FUTURE_PAIR_FULL_READBACK", EXIT + ",read:EXIT_ONLY:exit"]),
        ("definition-enabled-omits", ["PAPER_FUTURE_PAIR_FULL_READBACK", EXIT + ",read:EXIT_ONLY:exit"]),
        ("profile-success", ["PROFILE_OK"]),
        ("profile-missing-security", ["PAPER_PROFILE_EXPLICIT_DRAFT_SECURITY_REQUIRED"]),
        ("profile-default-drift", ["PAPER_PROFILE_UNEXPECTED_DEFAULT"]),
        ("profile-principal-drift", ["PAPER_PROFILE_OWNER_PRINCIPAL"]),
        ("profile-non-utc-draft", ["PAPER_PROFILE_DRAFT_CLOCK"]),
        ("active-success", ["ACTIVE_OK"]),
        *[(case, ["PAPER_NATIVE_ACTIVE_INSTANCE_UNCONFIRMED"]) for case in (
            "active-absent", "active-guid-change", "active-duplicate", "active-queued",
            "active-foreign-pid", "active-task-ready", "active-zero-guid",
        )],
        ("api-drift", ["PAPER_NATIVE_SETTINGS_API", CREATE + ",read:DISABLED:exit"]),
    ],
)
def test_future_pair_readback(tmp_path: Path, scenario: str, lines: list[str]) -> None:
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        pytest.skip("PowerShell 7 is required for the mocked readback")
    script = tmp_path / "readback.ps1"
    script.write_text(fixture_script(scenario), encoding="utf-8", newline="\n")
    result = subprocess.run(
        [pwsh, "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(script)],
        capture_output=True,
        encoding="utf-8",
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr == ""
    assert result.stdout.splitlines() == lines
