from __future__ import annotations

import subprocess
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "run_kis_paper_daily_broad_schedule.ps1"
)


def test_broad_schedule_runs_offline_postprocess_only_after_collection_success() -> None:
    source = SCRIPT.read_text(encoding="ascii")

    assert "Invoke-KisPaperDailyBroadCollector" in source
    assert "Invoke-KisPaperDailyBroadPanelPostprocess" in source
    assert source.index("Invoke-KisPaperDailyBroadCollector") < source.index(
        "Invoke-KisPaperDailyBroadPanelPostprocess"
    )
    assert "$collectionExitCode -ne 0" in source
    assert "uv.exe run --offline python" in source
    assert "postprocess_kis_paper_daily_broad_panel.py" in source
    assert "Start-Sleep" not in source
    for forbidden in (".env", "KIS_PAPER_ACCOUNT", "KIS_LIVE", "submit", "cancel"):
        assert forbidden.lower() not in source.lower()


def test_broad_schedule_invokes_postprocess_after_a_successful_collector(tmp_path: Path) -> None:
    completed = _run_harness(tmp_path, collector_exit=0, postprocess_exit=0)

    assert completed.returncode == 0, completed.stderr


def test_broad_schedule_does_not_postprocess_after_collector_recovery(tmp_path: Path) -> None:
    completed = _run_harness(tmp_path, collector_exit=20, postprocess_exit=0)

    assert completed.returncode == 20, completed.stderr


def _run_harness(
    tmp_path: Path,
    *,
    collector_exit: int,
    postprocess_exit: int,
) -> subprocess.CompletedProcess[str]:
    escaped_script = str(SCRIPT).replace("'", "''")
    harness = tmp_path / "broad_schedule.ps1"
    expected_postprocess_calls = 1 if collector_exit == 0 else 0
    harness.write_text(
        "\n".join(
            (
                "$ErrorActionPreference = 'Stop'",
                f". '{escaped_script}'",
                "$script:collectorCalls = 0",
                "$script:postprocessCalls = 0",
                "function Invoke-KisPaperDailyBroadCollector {",
                "    param([string]$ProjectRoot)",
                "    $script:collectorCalls += 1",
                f"    return {collector_exit}",
                "}",
                "function Invoke-KisPaperDailyBroadPanelPostprocess {",
                "    param([string]$ProjectRoot)",
                "    $script:postprocessCalls += 1",
                f"    return {postprocess_exit}",
                "}",
                "$exitCode = Invoke-KisPaperDailyBroadContinuation -ProjectRoot 'C:\\fixture'",
                "if ($script:collectorCalls -ne 1) { exit 91 }",
                f"if ($script:postprocessCalls -ne {expected_postprocess_calls}) {{ exit 92 }}",
                "exit $exitCode",
            )
        )
        + "\n",
        encoding="ascii",
    )
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(harness)],
        cwd=SCRIPT.parents[1],
        capture_output=True,
        check=False,
        text=True,
    )
