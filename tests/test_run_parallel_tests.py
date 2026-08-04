from pathlib import Path

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
