from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "run_kis_paper_daily_pair_forward_schedule.ps1"
)


def test_pair_forward_schedule_uses_guarded_preflight_then_collection() -> None:
    source = SCRIPT.read_text(encoding="ascii")

    preflight = ' -Service "kis-paper-daily-pair-forward-v2-preflight"'
    collection = ' -Service "kis-paper-daily-pair-forward-v2"'
    assert '"kis-paper-daily-pair-forward-v2",' in source
    assert '"kis-paper-daily-pair-forward"' not in source
    assert '"kis-paper-daily-pair-forward-preflight"' not in source
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
    assert "thericher-kis-paper-daily-backfill" in source
    assert "kis-paper-daily-pair-forward-v2-preflight" in source
    assert ".env" not in source
    assert "kis_paper_app_key" not in source
    assert "kis_paper_app_secret" not in source
    assert "kis_paper_account" not in source
    assert "kis_live" not in source
    assert "submit" not in source
    assert "cancel" not in source


def _run_schedule(
    tmp_path: Path,
    *,
    timezone_kst: bool = True,
    running_task: str = "",
    preflight_exit: int = 10,
    collection_exit: int = 0,
    guard_exit: int = 20,
) -> dict:
    project_root = tmp_path / "project with spaces"
    project_root.mkdir()
    (project_root / "docker-compose.yml").write_text("services: {}\n", encoding="ascii")
    harness = tmp_path / "pair_forward_schedule.ps1"
    escaped_script = str(SCRIPT).replace("'", "''")
    escaped_project_root = str(project_root).replace("'", "''")
    escaped_default_root = str(SCRIPT.parents[1]).replace("'", "''")
    harness.write_text(
        "\n".join(
            (
                "$ErrorActionPreference = 'Stop'",
                f". '{escaped_script}'",
                "$resolvedDefaultProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path",
                f"if ($resolvedDefaultProjectRoot -ne '{escaped_default_root}') {{ exit 92 }}",
                "$script:calls = @()",
                "$script:taskChecks = @()",
                f"function Test-KoreaStandardTime {{ return ${str(timezone_kst).lower()} }}",
                "function Get-ScheduledTask {",
                "    param([string]$TaskName, [string]$ErrorAction)",
                "    $script:taskChecks += $TaskName",
                f"    if ($TaskName -eq '{running_task}') {{",
                "        return [pscustomobject]@{ State = 'Running' }",
                "    }",
                "    return $null",
                "}",
                # Shadow the executable itself, keeping the real runner's argument handling.
                "function docker.exe {",
                "    $script:calls += ,@($args)",
                "    if ($args -contains '--schedule-guard-failed') {",
                f"        $global:LASTEXITCODE = {guard_exit}",
                "    } elseif ($args[-1] -eq 'kis-paper-daily-pair-forward-v2-preflight') {",
                f"        $global:LASTEXITCODE = {preflight_exit}",
                "    } elseif ($args[-1] -eq 'kis-paper-daily-pair-forward-v2') {",
                f"        $global:LASTEXITCODE = {collection_exit}",
                "    } else {",
                "        throw 'unexpected service'",
                "    }",
                "    Write-Output 'synthetic-private-service-stdout'",
                "    Write-Error 'synthetic-private-service-stderr' -ErrorAction Continue",
                "}",
                f"$exitCode = Invoke-PairForwardSchedule -ProjectRoot '{escaped_project_root}'",
                "[pscustomobject]@{",
                "    ExitCode = $exitCode",
                "    Calls = @($script:calls)",
                "    TaskChecks = @($script:taskChecks)",
                "} | ConvertTo-Json -Depth 5 -Compress",
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
        timeout=30,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stderr == ""
    assert "synthetic-private-service" not in completed.stdout
    return json.loads(completed.stdout)


def _compose_prefix(tmp_path: Path) -> list[str]:
    return [
        "compose",
        "--project-directory",
        str(tmp_path / "project with spaces"),
        "--profile",
        "kis-paper-daily-pair-forward-v2",
        "run",
        "--rm",
        "--no-deps",
        "--pull",
        "never",
    ]


@pytest.mark.parametrize(
    ("preflight_exit", "collection_exit", "expected_exit"),
    [(0, 0, 0), (10, 0, 0), (10, 20, 20), (10, 7, 7), (20, 0, 20), (2, 0, 2), (7, 0, 7)],
)
def test_pair_forward_schedule_collects_only_after_required_preflight(
    tmp_path: Path, preflight_exit: int, collection_exit: int, expected_exit: int
) -> None:
    result = _run_schedule(
        tmp_path, preflight_exit=preflight_exit, collection_exit=collection_exit
    )

    expected_calls = [_compose_prefix(tmp_path) + ["kis-paper-daily-pair-forward-v2-preflight"]]
    if preflight_exit == 10:
        expected_calls.append(_compose_prefix(tmp_path) + ["kis-paper-daily-pair-forward-v2"])
    assert result["ExitCode"] == expected_exit
    assert result["Calls"] == expected_calls
    assert result["TaskChecks"] == [
        "thericher-kis-paper-daily-nas-forward",
        "thericher-kis-paper-daily-broad-backfill",
        "thericher-kis-paper-daily-backfill",
    ]


@pytest.mark.parametrize(
    ("timezone_kst", "running_task", "reason"),
    [
        (False, "", "host_timezone_not_kst"),
        (True, "thericher-kis-paper-daily-nas-forward", "shared_dispatcher_busy"),
        (True, "thericher-kis-paper-daily-broad-backfill", "shared_dispatcher_busy"),
        (True, "thericher-kis-paper-daily-backfill", "shared_dispatcher_busy"),
    ],
)
@pytest.mark.parametrize(("guard_exit", "expected_exit"), [(0, 20), (20, 20), (7, 7)])
def test_pair_forward_schedule_guard_receipt_uses_v2_and_canonical_roots(
    tmp_path: Path,
    timezone_kst: bool,
    running_task: str,
    reason: str,
    guard_exit: int,
    expected_exit: int,
) -> None:
    result = _run_schedule(
        tmp_path, timezone_kst=timezone_kst, running_task=running_task, guard_exit=guard_exit
    )

    assert result["ExitCode"] == expected_exit
    assert result["Calls"] == [
        _compose_prefix(tmp_path)
        + [
            "--entrypoint",
            "python",
            "kis-paper-daily-pair-forward-v2-preflight",
            "scripts/collect_kis_paper_daily_pair_forward.py",
            "--preflight",
            "--cache-lineage",
            "v2",
            "--cache-root",
            "/app/market_data",
            "--artifact-root",
            "/app/model_artifacts",
            "--repository-root",
            "/app",
            "--schedule-guard-failed",
            reason,
        ]
    ]
    if timezone_kst:
        assert result["TaskChecks"][-1] == running_task
    else:
        assert result["TaskChecks"] == []
