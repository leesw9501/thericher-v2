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
try {
    $pins = @{}
    foreach ($phase in @('entry', 'exit')) {
        foreach ($stage in @('DISABLED', 'EXIT_ONLY', 'ENABLED')) {
            $export = $fixtures[$phase].Xml
            if ($stage -ceq 'ENABLED' -or ($stage -ceq 'EXIT_ONLY' -and $phase -ceq 'exit')) {
                $export = $export.Replace('<Enabled>false</Enabled>', '<Enabled>true</Enabled>')
            }
            $native = $export.Replace('</Settings>', '<Priority>7</Priority></Settings>')
            $pins["${stage}:$phase"] = @{ ExportXml = $export; DefinitionXml = $native }
        }
    }
    if ($scenario -ceq 'missing-stage') { $pins.Remove('ENABLED:entry') }
    if ($scenario -ceq 'missing-surface') { $pins['EXIT_ONLY:exit'].Remove('DefinitionXml') }
    $fixed = New-PaperNativePairReadback -Manifest $manifest `
        -ExpectedStageXml $pins `
        -EntryAcl7 $entryExpectedAcl -ExitAcl7 $sddl
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
        .replace("__MODULE__", str(MODULE).replace("'", "''"))
        .replace("__READBACK__", str(READBACK).replace("'", "''"))
        .replace("__SCENARIO__", scenario)
    )


@pytest.mark.parametrize(
    ("scenario", "lines"),
    [
        *[(case, ["PAPER_FUTURE_PAIR_INSTALLED", FINAL]) for case in (
            "success", "scope", "layout-only", "different-expected-acl", "claim-input-drift"
        )],
        *[(case, ["PAPER_PAIR_READBACK_EXPECTATION"]) for case in (
            "bad-expectation-xml", "bad-expectation-acl", "missing-stage", "missing-surface"
        )],
        *[(case, ["PAPER_FUTURE_PAIR_FULL_READBACK", DISABLED]) for case in (
            "registered-xml-drift", "matched-bad", "native-default-drift", "xml-drift", "extra-setting", "text-space", "extra-trigger",
            "doctype", "processing-instruction", "xml-comment", "deserializer-option", "unsafe-state",
            "acl-drift", "acl-ordinal", "instance", "null-instances", "unknown-count", "missing-count", "text-count",
            "instance-error",
        )],
        ("wrong-exit-only-state", ["PAPER_FUTURE_PAIR_FULL_READBACK", EXIT + ",read:EXIT_ONLY:exit"]),
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
