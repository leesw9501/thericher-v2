from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "inspect_kis_paper_intraday_head_static_contract.ps1"
)


def _helper_source() -> str:
    source = SCRIPT.read_text(encoding="ascii")
    helpers = source.split("# Runtime entry point.", maxsplit=1)[0]
    return helpers[helpers.index("$TaskName = ") :]


def _write_source_contract_fixture(project_root: Path) -> None:
    scripts = project_root / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "install_kis_paper_schedules.ps1").write_text(
        "\n".join(
            (
                'Name = "thericher-kis-paper-intraday-head"',
                'Profile = "kis-paper-intraday-head"',
                'Service = "kis-paper-intraday-head"',
                'Runner = "run_kis_paper_intraday_head_schedule.ps1"',
                'At = @("00:29", "02:28", "04:24", "06:20")',
                '"Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"',
                "RecoverMissedRun = $true",
                "ExecutionLimitMinutes = 90",
            )
            + ("",),
        ),
        encoding="ascii",
    )
    (scripts / "run_kis_paper_intraday_head_schedule.ps1").write_text(
        "\n".join(
            (
                "docker compose --profile kis-paper-intraday-head",
                ' -Service "kis-paper-intraday-head"',
                '"--mode",',
                '"session-capture",',
                '"--execute",',
                '"--skip-legacy-preparation",',
                '"--pages-per-target",',
                '"4",',
                "if ($collectionExitCode -eq 0) {}",
                "",
            )
        ),
        encoding="ascii",
    )
    (project_root / "docker-compose.yml").write_text(
        "\n".join(
            (
                "services:",
                "  kis-paper-intraday-head:",
                '    profiles: ["kis-paper-intraday-head"]',
                "    command:",
                "      - scripts/backfill_kis_paper_private_intraday.py",
                "      - session-capture",
                "      - --skip-legacy-preparation",
                '      - "4"',
                "    environment:",
                "      THERICHER_MODE: off",
                "      KIS_PAPER_APP_KEY:",
                "      KIS_PAPER_APP_SECRET:",
                "volumes:",
                "",
            )
        ),
        encoding="ascii",
    )


def _run_powershell(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def _task_contract_command(
    *,
    project_root: Path,
    runner_path: Path,
    state: str,
    mutation: str = "",
) -> str:
    arguments = (
        f'-NoProfile -ExecutionPolicy Bypass -File "{runner_path}" '
        f'-ProjectRoot "{project_root}"'
    )
    return "\n".join(
        (
            "$ErrorActionPreference = 'Stop'",
            _helper_source(),
            f"$projectRoot = '{project_root}'",
            f"$arguments = '{arguments}'",
            "$settings = [pscustomobject]@{",
            "  Enabled = $true",
            "  ExecutionTimeLimit = 'PT1H30M'",
            "  StartWhenAvailable = $true",
            "  MultipleInstances = 'IgnoreNew'",
            "  RestartCount = 0",
            "}",
            "$action = [pscustomobject]@{",
            "  Execute = 'powershell.exe'",
            "  Arguments = $arguments",
            "}",
            "$repetition = [pscustomobject]@{",
            "  Interval = ''",
            "  Duration = ''",
            "  StopAtDurationEnd = $false",
            "}",
            "$triggers = @( ",
            "  [pscustomobject]@{",
            "    StartBoundary = '2026-01-06T00:29:00'",
            "    DaysOfWeek = 124",
            "    Repetition = $repetition",
            "  },",
            "  [pscustomobject]@{",
            "    StartBoundary = '2026-01-06T02:28:00'",
            "    DaysOfWeek = 124",
            "    Repetition = $repetition",
            "  },",
            "  [pscustomobject]@{",
            "    StartBoundary = '2026-01-06T04:24:00'",
            "    DaysOfWeek = 124",
            "    Repetition = $repetition",
            "  },",
            "  [pscustomobject]@{",
            "    StartBoundary = '2026-01-06T06:20:00'",
            "    DaysOfWeek = 124",
            "    Repetition = $repetition",
            "  }",
            ")",
            "$task = [pscustomobject]@{",
            f"  State = '{state}'",
            "  Settings = $settings",
            "  Actions = @($action)",
            "  Triggers = $triggers",
            "}",
            "$sourceStatus = 'matches'",
            mutation,
            "$sourceHashes = @{",
            "  installer = 'sha256:' + ('a' * 64)",
            "  runner = 'sha256:' + ('b' * 64)",
            "  compose = 'sha256:' + ('c' * 64)",
            "}",
            "$fact = Get-InstalledStaticTaskContract `",
            "  -Task $task `",
            "  -ProjectRoot $projectRoot `",
            "  -SourceStatus $sourceStatus `",
            "  -SourceHashes $sourceHashes",
            "$fact | ConvertTo-Json -Depth 5 -Compress",
        )
    )


@pytest.mark.skipif(os.name != "nt", reason="Task Scheduler metadata is a Windows surface")
def test_static_task_contract_helpers_classify_matching_running_task_without_paths(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    runner_path = project_root / "scripts" / "run_kis_paper_intraday_head_schedule.ps1"
    runner_path.parent.mkdir()
    runner_path.write_text("# test", encoding="ascii")
    result = _run_powershell(
        _task_contract_command(
            project_root=project_root,
            runner_path=runner_path,
            state="Running",
        )
    )

    assert result.returncode == 0, result.stderr
    fact = json.loads(result.stdout)
    assert fact["status"] == "matches"
    assert fact["task_state"] == "running"
    assert {fact[name] for name in ("enabled", "action", "triggers", "settings", "source")} == {
        "matches"
    }
    assert str(project_root) not in result.stdout
    assert str(runner_path) not in result.stdout


@pytest.mark.skipif(os.name != "nt", reason="Task Scheduler metadata is a Windows surface")
@pytest.mark.parametrize(
    ("mutation", "expected_component"),
    (
        ("$task.Settings.Enabled = $false", "enabled"),
        ("$task.Actions[0].Arguments = '-NoProfile'", "action"),
        ("$task.Actions = @()", "action"),
        (
            "$task.Actions = @($task.Actions[0], "
            "[pscustomobject]@{ Execute = 'powershell.exe'; Arguments = $arguments })",
            "action",
        ),
        ("$task.Triggers[0].DaysOfWeek = 1", "triggers"),
        ("$task.Triggers[0].StartBoundary = '2026-01-06T01:00:00'", "triggers"),
        ("$task.Triggers[0].Repetition.Interval = 'PT5M'", "triggers"),
        ("$task.Settings.ExecutionTimeLimit = 'PT1H00M'", "settings"),
        ("$sourceStatus = 'mismatch'", "source"),
    ),
)
def test_static_task_contract_rejects_each_critical_mismatch(
    tmp_path: Path,
    mutation: str,
    expected_component: str,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    runner_path = project_root / "scripts" / "run_kis_paper_intraday_head_schedule.ps1"
    runner_path.parent.mkdir()
    runner_path.write_text("# test", encoding="ascii")
    result = _run_powershell(
        _task_contract_command(
            project_root=project_root,
            runner_path=runner_path,
            state="Ready",
            mutation=mutation,
        )
    )

    assert result.returncode == 0, result.stderr
    fact = json.loads(result.stdout)
    assert fact["status"] == "mismatch"
    assert fact[expected_component] == "mismatch"


@pytest.mark.skipif(os.name != "nt", reason="Task Scheduler metadata is a Windows surface")
@pytest.mark.parametrize(
    ("relative_path", "expected", "replacement"),
    (
        (
            "scripts/install_kis_paper_schedules.ps1",
            'Name = "thericher-kis-paper-intraday-head"',
            'Name = "other-task"',
        ),
        (
            "scripts/run_kis_paper_intraday_head_schedule.ps1",
            '"session-capture",',
            '"other-mode",',
        ),
        (
            "docker-compose.yml",
            'profiles: ["kis-paper-intraday-head"]',
            'profiles: ["other-profile"]',
        ),
        (
            "docker-compose.yml",
            "KIS_PAPER_APP_SECRET:",
            "KIS_LIVE_APP_SECRET:",
        ),
    ),
)
def test_static_task_contract_source_rejects_changed_collection_route(
    tmp_path: Path,
    relative_path: str,
    expected: str,
    replacement: str,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    _write_source_contract_fixture(project_root)
    source_path = project_root / relative_path
    source_path.write_text(
        source_path.read_text(encoding="ascii").replace(expected, replacement),
        encoding="ascii",
    )
    command = "\n".join(
        (
            "$ErrorActionPreference = 'Stop'",
            _helper_source(),
            f"$projectRoot = '{project_root}'",
            "$fact = Get-StaticSourceContract -ProjectRoot $projectRoot",
            "$fact | ConvertTo-Json -Depth 5 -Compress",
        )
    )
    result = _run_powershell(command)

    assert result.returncode == 0, result.stderr
    fact = json.loads(result.stdout)
    assert fact["status"] == "mismatch"
    assert str(project_root) not in result.stdout


@pytest.mark.skipif(os.name != "nt", reason="Task Scheduler metadata is a Windows surface")
def test_static_task_contract_missing_task_is_unavailable(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    command = "\n".join(
        (
            "$ErrorActionPreference = 'Stop'",
            _helper_source(),
            f"$projectRoot = '{project_root}'",
            "$sourceHashes = @{ installer = 'sha256:' + ('a' * 64) }",
            "$fact = Get-InstalledStaticTaskContract `",
            "  -Task $null `",
            "  -ProjectRoot $projectRoot `",
            "  -SourceStatus 'matches' `",
            "  -SourceHashes $sourceHashes",
            "$fact | ConvertTo-Json -Depth 5 -Compress",
        )
    )
    result = _run_powershell(command)

    assert result.returncode == 0, result.stderr
    fact = json.loads(result.stdout)
    assert fact["status"] == "unavailable"
    assert fact["task_state"] == "unavailable"
    assert fact["action"] == "unavailable"
    assert str(project_root) not in result.stdout


@pytest.mark.skipif(os.name != "nt", reason="Task Scheduler metadata is a Windows surface")
def test_static_task_contract_receipt_is_external_and_hides_roots(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    artifact_root = tmp_path / "artifacts"
    project_root.mkdir()
    command = "\n".join(
        (
            "$ErrorActionPreference = 'Stop'",
            _helper_source(),
            f"$projectRoot = '{project_root}'",
            f"$artifactRoot = '{artifact_root}'",
            "$fact = [pscustomobject]@{",
            "  status = 'matches'",
            "  task_state = 'ready'",
            "  enabled = 'matches'",
            "  action = 'matches'",
            "  triggers = 'matches'",
            "  settings = 'matches'",
            "  source = 'matches'",
            "  source_hashes = @{ installer = 'sha256:' + ('a' * 64) }",
            "}",
            "$receipt = Write-StaticTaskContractReceipt `",
            "  -Fact $fact `",
            "  -ArtifactRoot $artifactRoot `",
            "  -ProjectRoot $projectRoot `",
            "  -ObservedAt ([datetime]'2026-08-19T12:00:00Z')",
            "$receipt | ConvertTo-Json -Depth 5 -Compress",
        )
    )
    result = _run_powershell(command)

    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["status"] == "matches"
    assert receipt["evidence_path"].startswith(
        "execution\\kis-paper-intraday-head-static-contract-v1\\"
    )
    assert not receipt["evidence_path"].startswith("..")
    assert receipt["evidence_sha256"].startswith("sha256:")
    assert str(project_root) not in result.stdout
    assert str(artifact_root) not in result.stdout
    evidence_path = artifact_root / receipt["evidence_path"]
    assert evidence_path.is_file()
    evidence = evidence_path.read_text(encoding="ascii")
    assert str(project_root) not in evidence
    assert str(artifact_root) not in evidence


def test_static_task_contract_inspector_never_starts_task_or_docker() -> None:
    source = SCRIPT.read_text(encoding="ascii")

    assert "Get-ScheduledTask -TaskName $TaskName" in source
    assert "Get-ScheduledTaskInfo" not in source
    assert "Start-ScheduledTask" not in source
    assert "Register-ScheduledTask" not in source
    assert "docker.exe" not in source
    assert "$env:" not in source
    assert "task_invoked = $false" in source
    assert "docker_invoked = $false" in source
    assert "kis_called = $false" in source
