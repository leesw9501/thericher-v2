from __future__ import annotations

import subprocess
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "run_kis_paper_daily_pair_forward_schedule.ps1"
)


def test_pair_forward_schedule_uses_guarded_preflight_then_collection() -> None:
    source = SCRIPT.read_text(encoding="ascii")

    preflight = ' -Service "kis-paper-daily-pair-forward-preflight"'
    collection = ' -Service "kis-paper-daily-pair-forward"'
    assert '"kis-paper-daily-pair-forward",' in source
    assert '"--profile",' in source
    assert '"--rm",' in source
    assert '"--no-deps",' in source
    assert '"--pull",' in source
    assert '"never"' in source
    assert preflight in source
    assert collection in source
    assert source.index(preflight) < source.index(collection)
    assert '$CacheCurrentExitCode = 0' in source
    assert '$CollectionRequiredExitCode = 10' in source
    assert '$RecoveryExitCode = 20' in source
    assert 'if ($preflightExitCode -eq $CacheCurrentExitCode)' in source
    assert 'if ($preflightExitCode -ne $CollectionRequiredExitCode)' in source
    assert "ConvertFrom-Json" not in source
    assert "Start-Sleep" not in source


def test_pair_forward_schedule_defers_for_timezone_or_running_data_worker() -> None:
    source = SCRIPT.read_text(encoding="ascii").lower()

    assert "test-koreastandardtime" in source
    assert "host_timezone_not_kst" in source
    assert "test-shareddatadispatcheridle" in source
    assert "shared_dispatcher_busy" in source
    assert "get-scheduledtask" in source
    assert "thericher-kis-paper-daily-nas-forward" in source
    assert "thericher-kis-paper-daily-broad-backfill" in source
    assert "--schedule-guard-failed" in source
    assert "kis-paper-daily-pair-forward-preflight" in source
    assert ".env" not in source
    assert "kis_paper_app_key" not in source
    assert "kis_paper_app_secret" not in source
    assert "kis_paper_account" not in source
    assert "kis_live" not in source
    assert "submit" not in source
    assert "cancel" not in source


def test_pair_forward_schedule_collects_only_after_required_preflight(tmp_path: Path) -> None:
    project_root = SCRIPT.parents[1]
    harness = tmp_path / "pair_forward_schedule.ps1"
    escaped_script = str(SCRIPT).replace("'", "''")
    escaped_project_root = str(project_root).replace("'", "''")
    harness.write_text(
        "\n".join(
            (
                "$ErrorActionPreference = 'Stop'",
                f". '{escaped_script}'",
                "$resolvedDefaultProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path",
                f"if ($resolvedDefaultProjectRoot -ne '{escaped_project_root}') {{ exit 92 }}",
                "$script:collectionCalls = 0",
                "function Test-KoreaStandardTime { return $true }",
                "function Test-SharedDataDispatcherIdle { return $true }",
                "function Invoke-PairForwardProfileService {",
                "    param(",
                "        [string]$ProjectRoot,",
                "        [string]$Service,",
                "        [string[]]$CommandOverride = @()",
                "    )",
                "    if ($Service -eq 'kis-paper-daily-pair-forward-preflight') {",
                "        return [pscustomobject]@{ ExitCode = 10; Output = @() }",
                "    }",
                "    if ($Service -eq 'kis-paper-daily-pair-forward') {",
                "        $script:collectionCalls += 1",
                "        return [pscustomobject]@{ ExitCode = 0; Output = @() }",
                "    }",
                "    throw 'unexpected service'",
                "}",
                f"$exitCode = Invoke-PairForwardSchedule -ProjectRoot '{escaped_project_root}'",
                "if ($script:collectionCalls -ne 1) { exit 91 }",
                "exit $exitCode",
            )
        )
        + "\n",
        encoding="ascii",
    )

    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(harness)],
        cwd=project_root,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
