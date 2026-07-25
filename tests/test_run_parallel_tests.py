from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "run_parallel_tests.ps1"


def test_parallel_test_runner_uses_bounded_workers_and_short_isolated_temp_root() -> None:
    source = SCRIPT.read_text(encoding="ascii")

    assert "[int]$Workers = [Math]::Min(8, [Environment]::ProcessorCount)" in source
    assert '$tempRoot = "C:\\trpy"' in source
    assert "pytest -q -n $Workers --dist=loadfile --basetemp $baseTemp" in source
    assert "if ($exitCode -eq 0 -and (Test-Path -LiteralPath $baseTemp))" in source
    assert "Remove-Item -LiteralPath $baseTemp -Recurse -Force -ErrorAction Stop" in source
    assert "Parallel pytest passed but could not remove its temp path" in source
    assert "KIS_" not in source
    assert ".env" not in source
