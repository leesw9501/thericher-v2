from __future__ import annotations

import subprocess
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "run_kis_paper_daily_broad_schedule.ps1"
)


def test_broad_schedule_runs_offline_finalization_only_after_collection_success() -> None:
    source = SCRIPT.read_text(encoding="ascii")

    assert "Invoke-KisPaperDailyBroadCollector" in source
    assert "Invoke-KisPaperDailyBroadPanelPostprocess" in source
    assert "Invoke-KisPaperDailyBroadChronologyObservation" in source
    assert source.index("Invoke-KisPaperDailyBroadCollector") < source.index(
        "Invoke-KisPaperDailyBroadPanelPostprocess"
    )
    assert source.index("Invoke-KisPaperDailyBroadPanelPostprocess") < source.index(
        "Invoke-KisPaperDailyBroadChronologyObservation"
    )
    assert "$collectionExitCode -ne 0" in source
    assert '"--offline"' in source
    assert "& uv.exe @arguments" in source
    assert "postprocess_kis_paper_daily_broad_panel.py" in source
    assert "observe_kis_paper_daily_broad_panel_chronology.py" in source
    assert "Resolve-KisPaperDailyBroadPostrunReceiptPath" in source
    assert "PostrunReceiptPath" in source
    assert "[int]$CollectorMaxRuntimeSeconds = 28800" in source
    assert "--max-runtime-seconds $MaxRuntimeSeconds" in source
    assert "Start-Sleep" not in source
    for forbidden in (".env", "KIS_PAPER_ACCOUNT", "KIS_LIVE", "submit", "cancel"):
        assert forbidden.lower() not in source.lower()


def test_broad_schedule_invokes_all_offline_stages_after_a_successful_collector(
    tmp_path: Path,
) -> None:
    completed = _run_harness(
        tmp_path,
        collector_exit=0,
        postprocess_exit=0,
        chronology_exit=0,
    )

    assert completed.returncode == 0, completed.stderr


def test_broad_schedule_does_not_finalize_after_collector_recovery(tmp_path: Path) -> None:
    completed = _run_harness(tmp_path, collector_exit=20, postprocess_exit=0)

    assert completed.returncode == 20, completed.stderr


def test_broad_schedule_does_not_observe_after_postprocess_recovery(tmp_path: Path) -> None:
    completed = _run_harness(tmp_path, collector_exit=0, postprocess_exit=20)

    assert completed.returncode == 20, completed.stderr


def test_broad_schedule_preserves_data_success_when_observer_needs_recovery(
    tmp_path: Path,
) -> None:
    completed = _run_harness(
        tmp_path,
        collector_exit=0,
        postprocess_exit=0,
        chronology_exit=20,
    )

    assert completed.returncode == 0, completed.stderr


def test_broad_schedule_resolves_only_the_digest_named_complete_postrun_receipt(
    tmp_path: Path,
) -> None:
    digest = "a" * 64
    postrun_root = tmp_path / "postruns"
    postrun_root.mkdir()
    receipt_path = postrun_root / f"postrun-{digest[:24]}.json"
    receipt_path.write_text("{}\n", encoding="ascii")
    output = (
        '{"kind":"kis_paper_daily_broad_panel_postrun","status":"complete",'
        '"reason":"stable_full_breadth_panel","receipt_sha256":"sha256:'
        f"{digest}"
        '"}'
    )
    escaped_script = str(SCRIPT).replace("'", "''")
    escaped_root = str(postrun_root).replace("'", "''")
    escaped_receipt = str(receipt_path).replace("'", "''")
    harness = tmp_path / "resolve_postrun.ps1"
    harness.write_text(
        "\n".join(
            (
                "$ErrorActionPreference = 'Stop'",
                f". '{escaped_script}'",
                (
                    "$resolved = Resolve-KisPaperDailyBroadPostrunReceiptPath "
                    f"-OutputLines @('{output}') -PostrunArtifactRoot '{escaped_root}'"
                ),
                f"if ($resolved -ne '{escaped_receipt}') {{ exit 93 }}",
            )
        )
        + "\n",
        encoding="ascii",
    )

    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(harness)],
        cwd=SCRIPT.parents[1],
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def _run_harness(
    tmp_path: Path,
    *,
    collector_exit: int,
    postprocess_exit: int,
    chronology_exit: int = 0,
) -> subprocess.CompletedProcess[str]:
    escaped_script = str(SCRIPT).replace("'", "''")
    harness = tmp_path / "broad_schedule.ps1"
    expected_postprocess_calls = 1 if collector_exit == 0 else 0
    expected_chronology_calls = (
        1 if collector_exit == 0 and postprocess_exit == 0 else 0
    )
    harness.write_text(
        "\n".join(
            (
                "$ErrorActionPreference = 'Stop'",
                f". '{escaped_script}'",
                "$script:collectorCalls = 0",
                "$script:postprocessCalls = 0",
                "$script:chronologyCalls = 0",
                "function Invoke-KisPaperDailyBroadCollector {",
                "    param([string]$ProjectRoot, [int]$MaxRuntimeSeconds)",
                "    $script:collectorCalls += 1",
                "    $script:collectorMaxRuntimeSeconds = $MaxRuntimeSeconds",
                f"    return {collector_exit}",
                "}",
                "function Invoke-KisPaperDailyBroadPanelPostprocess {",
                "    param([string]$ProjectRoot)",
                "    $script:postprocessCalls += 1",
                "    return [pscustomobject]@{",
                f"        ExitCode = {postprocess_exit}",
                (
                    "        PostrunReceiptPath = if ("
                    + str(postprocess_exit)
                    + " -eq 0) { 'D:\\fixture\\postrun.json' } else { $null }"
                ),
                "    }",
                "}",
                "function Invoke-KisPaperDailyBroadChronologyObservation {",
                "    param([string]$ProjectRoot, [string]$PostrunReceiptPath)",
                "    $script:chronologyCalls += 1",
                f"    return {chronology_exit}",
                "}",
                "$exitCode = Invoke-KisPaperDailyBroadContinuation -ProjectRoot 'C:\\fixture'",
                "if ($script:collectorCalls -ne 1) { exit 91 }",
                f"if ($script:postprocessCalls -ne {expected_postprocess_calls}) {{ exit 92 }}",
                f"if ($script:chronologyCalls -ne {expected_chronology_calls}) {{ exit 93 }}",
                "if ($script:collectorMaxRuntimeSeconds -ne 28800) { exit 94 }",
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
