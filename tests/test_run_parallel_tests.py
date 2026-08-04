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
    assert '$tempParent = "C:\\trpy"' in source
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

    if (
        completed.returncode == 1
        and "test mutex could not be acquired" in completed.stderr
    ):
        # The enclosing parallel helper already owns the same global mutex.
        return

    assert completed.returncode == 0, completed.stderr
    assert "global mutex contention rejected helper" in completed.stdout
