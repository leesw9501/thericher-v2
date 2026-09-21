import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "run_parallel_tests.ps1"


def test_parallel_test_runner_uses_bounded_workers_and_cross_session_safe_temp_root() -> None:
    source = SCRIPT.read_text(encoding="ascii")

    assert "[int]$Workers = [Math]::Min(8, [Environment]::ProcessorCount)" in source
    assert "[switch]$RequireCleanTempRoot" in source
    assert "function Resolve-TestTempParent" in source
    assert '@("C:\\trpy", "D:\\trpy")' in source
    assert "Get-PSDrive -Name $driveName -PSProvider FileSystem" in source
    assert "$drive.DisplayRoot" in source
    assert "$tempParent = Resolve-TestTempParent" in source
    assert '$tempRoot = Join-Path $tempParent "runs"' in source
    assert "$tempParentEntry = Get-Item -LiteralPath $tempParent" in source
    assert "$tempRootEntry = Get-Item -LiteralPath $tempRoot" in source
    assert "$resolvedTempParent = [IO.Path]::GetFullPath($tempParent)" in source
    assert "$resolvedTempRoot = [IO.Path]::GetFullPath($tempRoot)" in source
    assert '$mutexName = "Global\\TheRicherV2ParallelPytest"' in source
    assert "$mutex.WaitOne([TimeSpan]::Zero)" in source
    assert "[System.Threading.AbandonedMutexException]" in source
    assert '$leaseSuffix = ".thericher-pytest-lease"' in source
    assert "Assert-NoActiveParallelPytestRun" in source
    assert 'Assert-NoActiveKnownParallelPytestRuns -TempParents @("C:\\trpy", "D:\\trpy")' in source
    assert "Get-CimInstance -ClassName Win32_Process" in source
    assert "[IO.FileAttributes]::ReparsePoint" in source
    assert "Assert-ManagedTempDirectory" in source
    assert "Assert-SafeTempTreeForRemoval" in source
    assert "pytest -q -n $Workers --dist=loadfile --basetemp $baseTemp" in source
    assert "$exitCode = $LASTEXITCODE" in source
    assert "if ($exitCode -eq 0 -and $null -ne $baseTemp" in source
    assert "Remove-Item -LiteralPath $resolvedBaseTemp -Recurse -Force -ErrorAction Stop" in source
    assert "Parallel pytest passed but could not remove its temp path" in source
    assert "exit $exitCode" in source
    assert "KIS_" not in source
    assert ".env" not in source


@pytest.mark.skipif(
    sys.platform != "win32" or shutil.which("pwsh") is None,
    reason="requires Windows PowerShell 7 filesystem support",
)
@pytest.mark.parametrize(
    ("case", "expected", "probes"),
    [
        ("preferred_worker", "active worker for:", 1),
        ("alternate_worker", "active worker for:", 2),
        ("alternate_lease", "active helper lease:", 1),
        ("missing_alternate", "clear", 1),
        ("missing_alternate_runs", "clear", 1),
        ("inactive_retained", "clear", 2),
        ("alternate_root_file", "unmanaged parallel pytest temp root:", 1),
        ("process_probe_failure", "cannot inspect active Python processes", 1),
        ("unreadable_process", "cannot inspect an active Python command line", 1),
    ],
)
def test_parallel_test_authority_checks_both_managed_roots(
    tmp_path: Path, case: str, expected: str, probes: int
) -> None:
    preferred, alternate = tmp_path / "preferred", tmp_path / "alternate"
    for parent in (preferred, alternate):
        if parent == alternate and case == "missing_alternate":
            continue
        parent.mkdir()
        if parent == alternate and case == "missing_alternate_runs":
            continue
        if parent == alternate and case == "alternate_root_file":
            (parent / "runs").write_text("not a directory", encoding="ascii")
            continue
        child = parent / "runs" / "r-retained"
        child.mkdir(parents=True)
        (child / "retained.txt").write_text("unchanged", encoding="ascii")
        (parent / "runs" / ".r-retained.thericher-pytest-lease").write_bytes(b"")

    def snapshot():
        return {
            str(path.relative_to(tmp_path)): path.read_bytes() if path.is_file() else None
            for path in tmp_path.rglob("*")
        }

    before = snapshot()
    script_path, preferred_path, alternate_path = (
        str(path).replace("'", "''") for path in (SCRIPT, preferred, alternate)
    )
    # Parse only function definitions: never execute the helper, mutex, or real process probe.
    command = rf"""
$ErrorActionPreference = 'Stop'
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    '{script_path}', [ref]$tokens, [ref]$parseErrors
)
if ($parseErrors.Count -ne 0) {{ throw 'helper parse failed' }}
foreach ($statement in $ast.EndBlock.Statements) {{
    if ($statement -is [System.Management.Automation.Language.FunctionDefinitionAst]) {{
        . ([scriptblock]::Create($statement.Extent.Text))
    }}
}}
$leaseSuffix = '.thericher-pytest-lease'
$preferred = '{preferred_path}'
$alternate = '{alternate_path}'
$case = '{case}'
$script:processProbes = 0
function Get-CimInstance {{
    [CmdletBinding()]
    param([string]$ClassName)
    if ($ClassName -ne 'Win32_Process') {{ throw 'unexpected process probe' }}
    $script:processProbes++
    if ($case -eq 'process_probe_failure') {{ throw 'synthetic probe failure' }}
    if ($case -eq 'unreadable_process') {{
        [pscustomobject]@{{Name='python.exe'; CommandLine=$null}}
    }}
    elseif ($case -in @('preferred_worker', 'alternate_worker')) {{
        $parent = if ($case -eq 'preferred_worker') {{ $preferred }} else {{ $alternate }}
        $child = Join-Path $parent 'runs\r-retained'
        [pscustomobject]@{{Name='python.exe'; CommandLine="python -m pytest --basetemp $child"}}
    }}
}}
function New-Item {{ throw 'authority must not allocate a directory' }}
function Remove-Item {{ throw 'authority must not remove retained content' }}
$heldLease = $null
$outcome = 'clear'
try {{
    if ($case -eq 'alternate_lease') {{
        $heldLease = [IO.File]::Open(
            (Join-Path $alternate 'runs\.r-retained.thericher-pytest-lease'),
            [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None
        )
    }}
    try {{
        Assert-NoActiveKnownParallelPytestRuns -TempParents @($preferred, $alternate)
    }}
    catch {{ $outcome = $_.Exception.Message }}
}}
finally {{
    if ($null -ne $heldLease) {{ $heldLease.Dispose() }}
}}
[pscustomobject]@{{outcome=$outcome; process_probes=$script:processProbes}} |
    ConvertTo-Json -Compress
"""
    completed = subprocess.run(
        ["pwsh", "-NoProfile", "-NonInteractive", "-Command", command],
        cwd=tmp_path,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        text=True,
        timeout=15,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert expected in result["outcome"]
    assert result["process_probes"] == probes
    if case in {"preferred_worker", "alternate_worker"}:
        parent = preferred if case == "preferred_worker" else alternate
        assert str(parent / "runs" / "r-retained") in result["outcome"]
    assert snapshot() == before


@pytest.mark.skipif(
    sys.platform != "win32" or shutil.which("pwsh") is None,
    reason="requires Windows PowerShell 7 mutex support",
)
def test_parallel_test_runner_refuses_another_process_global_mutex() -> None:
    command = rf"""
$mutex = [System.Threading.Mutex]::new($false, 'Global\TheRicherV2ParallelPytest')
$acquired = $false
try {{
  $acquired = $mutex.WaitOne([TimeSpan]::Zero)
  if (-not $acquired) {{ throw 'test mutex could not be acquired' }}
  $testPath = 'tests\test_run_parallel_tests.py'
  & pwsh -NoProfile -File '{SCRIPT}' -RequireCleanTempRoot -Workers 1 $testPath
  if ($LASTEXITCODE -eq 0) {{ throw 'parallel helper accepted an active mutex' }}
  'global mutex contention rejected helper'
}}
finally {{
  if ($acquired) {{ $mutex.ReleaseMutex() }}
  $mutex.Dispose()
}}
"""

    completed = subprocess.run(
        ["pwsh", "-NoProfile", "-Command", command],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
        encoding="utf-8",
        errors="replace",
        text=True,
        timeout=15,
    )

    if completed.returncode == 1 and "test mutex could not be acquired" in completed.stderr:
        # The enclosing parallel helper already owns the same global mutex.
        return

    assert completed.returncode == 0, completed.stderr
    assert "global mutex contention rejected helper" in completed.stdout
