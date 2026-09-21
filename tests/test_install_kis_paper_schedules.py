from __future__ import annotations

import json
import re
import subprocess
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "install_kis_paper_schedules.ps1"
)
INTRADAY_HEAD_RUNNER = SCRIPT.parent / "run_kis_paper_intraday_head_schedule.ps1"

SAME_DATE_KST_SCHEDULES = {
    "thericher-kis-paper-quote-session": "23:35",
    "thericher-kis-paper-snapshot-observer": "21:20",
    "thericher-kis-paper-daily-spy-head": "22:15",
    "thericher-kis-paper-daily-spy-stability-observer": "23:15",
    "thericher-kis-paper-daily-spy-session": "23:50",
}
LEGACY_OVERNIGHT_SCHEDULES = (
    "thericher-kis-paper-intraday-head",
    "thericher-kis-paper-daily-nas-forward",
    "thericher-kis-paper-daily-pair-forward",
    "thericher-kis-paper-daily-broad-backfill",
    "thericher-kis-paper-daily-backfill",
)


def _schedule_entry(source: str, task_name: str) -> str:
    return source.split(f'Name = "{task_name}"', maxsplit=1)[1].split(
        "    },", maxsplit=1
    )[0]


def test_kis_paper_schedule_installer_has_exact_task_surface() -> None:
    source = SCRIPT.read_text(encoding="ascii")

    assert source.count("thericher-kis-paper-daily-backfill") == 1
    assert source.count('Name = "thericher-kis-paper-quote-session"') == 1
    assert source.count('Name = "thericher-kis-paper-snapshot-observer"') == 1
    assert source.count('Name = "thericher-kis-paper-daily-spy-head"') == 1
    assert source.count('Name = "thericher-kis-paper-daily-spy-stability-observer"') == 1
    assert source.count('Name = "thericher-kis-paper-daily-spy-session"') == 1
    assert source.count("thericher-kis-paper-intraday-head") == 1
    assert source.count('Name = "thericher-kis-paper-daily-nas-forward"') == 1
    assert source.count('Name = "thericher-kis-paper-daily-pair-forward"') == 1
    assert source.count('Name = "thericher-kis-paper-daily-broad-backfill"') == 1
    assert source.count('Profile = "kis-paper-daily-backfill"') == 1
    assert source.count('Profile = "kis-paper-session"') == 1
    assert source.count('Profile = "kis-readonly"') == 1
    assert source.count('Profile = "kis-paper-daily-spy-head"') == 1
    assert source.count('Profile = "kis-paper-daily-spy-stability-observer"') == 1
    assert source.count('Profile = "kis-paper-daily-spy-session"') == 1
    assert source.count('Profile = "kis-paper-intraday-head"') == 1
    assert source.count('Profile = "kis-paper-daily-nas-forward"') == 1
    assert source.count('Profile = "kis-paper-daily-pair-forward-v2"') == 1
    assert source.count('Profile = "kis-paper-daily-broad-backfill"') == 1
    assert source.count('Service = "kis-paper-daily-backfill"') == 1
    assert source.count('Service = "kis-paper-session"') == 1
    assert source.count('Service = "kis-readonly"') == 1
    assert source.count('Service = "kis-paper-daily-spy-head"') == 1
    assert source.count('Service = "kis-paper-daily-spy-stability-observer"') == 1
    assert source.count('Service = "kis-paper-daily-spy-session"') == 1
    assert source.count('Service = "kis-paper-intraday-head"') == 1
    assert source.count('Service = "kis-paper-daily-nas-forward"') == 1
    assert source.count('Service = "kis-paper-daily-pair-forward-v2"') == 1
    assert source.count('Service = "kis-paper-daily-broad-backfill"') == 1
    assert source.count('Runner = "run_kis_paper_intraday_head_schedule.ps1"') == 1
    observer_entry = _schedule_entry(source, "thericher-kis-paper-snapshot-observer")
    assert 'Profile = "kis-readonly"' in observer_entry
    assert 'Service = "kis-readonly"' in observer_entry
    assert 'Runner = "run_paper_snapshot_observer.ps1"' in observer_entry
    assert 'ImageServices = @("kis-readonly")' in observer_entry
    assert 'At = "21:20"' in observer_entry
    assert "RepetitionIntervalMinutes = 4" in observer_entry
    assert "RepetitionDurationMinutes = 600" in observer_entry
    assert "RecoverMissedRun = $false" in observer_entry
    assert "ExecutionLimitMinutes = 4" in observer_entry
    assert source.count("DaysOfWeek = @(") == len(SAME_DATE_KST_SCHEDULES)
    for task_name, schedule_time in SAME_DATE_KST_SCHEDULES.items():
        entry = _schedule_entry(source, task_name)
        assert f'At = "{schedule_time}"' in entry
        assert (
            'DaysOfWeek = @("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")'
            in entry
        )
    for task_name in LEGACY_OVERNIGHT_SCHEDULES:
        assert "DaysOfWeek =" not in _schedule_entry(source, task_name)
    intraday_head_entry = _schedule_entry(source, "thericher-kis-paper-intraday-head")
    image_services = set(
        re.findall(
            r'"([a-z0-9-]+)"',
            intraday_head_entry.split("ImageServices = @(", maxsplit=1)[1].split(
                "        )", maxsplit=1
            )[0],
        )
    )
    dispatcher_services = set(
        re.findall(
            r'-Service "([a-z0-9-]+)"',
            INTRADAY_HEAD_RUNNER.read_text(encoding="ascii"),
        )
    )
    assert image_services == dispatcher_services
    forward_entry = source.split(
        'Name = "thericher-kis-paper-daily-nas-forward"', maxsplit=1
    )[1].split("    },", maxsplit=1)[0]
    assert 'Profile = "kis-paper-daily-nas-forward"' in forward_entry
    assert 'Service = "kis-paper-daily-nas-forward"' in forward_entry
    assert 'Runner = "run_kis_paper_daily_nas_forward_schedule.ps1"' in forward_entry
    assert '"kis-paper-daily-nas-forward-preflight"' in forward_entry
    assert '"kis-paper-daily-nas-forward"' in forward_entry
    assert '"kis-paper-daily-nas-forward-observation"' in forward_entry
    assert 'At = "06:40"' in forward_entry
    assert "RecoverMissedRun = $true" in forward_entry
    assert "ExecutionLimitMinutes = 90" in forward_entry
    pair_forward_entry = source.split(
        'Name = "thericher-kis-paper-daily-pair-forward"', maxsplit=1
    )[1].split("    },", maxsplit=1)[0]
    assert 'Profile = "kis-paper-daily-pair-forward-v2"' in pair_forward_entry
    assert 'Service = "kis-paper-daily-pair-forward-v2"' in pair_forward_entry
    assert 'Runner = "run_kis_paper_daily_pair_forward_schedule.ps1"' in pair_forward_entry
    assert '"kis-paper-daily-pair-forward-v2-preflight"' in pair_forward_entry
    assert '"kis-paper-daily-pair-forward-v2"' in pair_forward_entry
    assert 'At = "06:55"' in pair_forward_entry
    assert "RecoverMissedRun = $true" in pair_forward_entry
    assert "ExecutionLimitMinutes = 10" in pair_forward_entry
    broad_entry = source.split(
        'Name = "thericher-kis-paper-daily-broad-backfill"', maxsplit=1
    )[1].split("    },", maxsplit=1)[0]
    assert 'Profile = "kis-paper-daily-broad-backfill"' in broad_entry
    assert 'Service = "kis-paper-daily-broad-backfill"' in broad_entry
    assert 'Runner = "run_kis_paper_daily_broad_schedule.ps1"' in broad_entry
    broad_times = tuple(re.findall(r'"(\d{2}:\d{2})"', broad_entry))
    assert broad_times == ("00:15",)
    assert "RecoverMissedRun = $true" in broad_entry
    assert "ExecutionLimitMinutes = 870" in broad_entry
    assert source.index('Name = "thericher-kis-paper-daily-nas-forward"') < source.index(
        'Name = "thericher-kis-paper-daily-pair-forward"'
    )
    assert source.index('Name = "thericher-kis-paper-daily-pair-forward"') < source.index(
        'Name = "thericher-kis-paper-daily-broad-backfill"'
    )
    assert source.index('Name = "thericher-kis-paper-daily-broad-backfill"') < source.index(
        'Name = "thericher-kis-paper-daily-backfill"'
    )


def test_kis_paper_schedule_installer_uses_required_windows_schedule_contract() -> None:
    source = SCRIPT.read_text(encoding="ascii")

    assert "[CmdletBinding(SupportsShouldProcess = $true" in source
    assert "$PSCmdlet.ShouldProcess" in source
    assert "Get-Command docker.exe" in source
    assert "docker-compose.yml" in source
    assert '[string]$ProjectRoot = ""' in source
    assert "if ([string]::IsNullOrWhiteSpace($ProjectRoot))" in source
    assert '$ProjectRoot = Join-Path $PSScriptRoot ".."' in source
    assert "Resolve-Path -LiteralPath $ProjectRoot" in source
    assert "[string[]]$ScheduleName = @()" in source
    assert "[switch]$RequireExisting" in source
    assert "[switch]$SkipImageBuild" in source
    assert "$requestedNames = @($ScheduleName | Select-Object -Unique)" in source
    assert "Unknown local Docker schedule name(s)" in source
    assert "$selectedSchedules = @(\n        $schedules | Where-Object" in source
    assert "Get-ScheduledTask -TaskName $_.Name -ErrorAction SilentlyContinue" in source
    assert "Required existing scheduled task is missing" in source
    assert source.index("Required existing scheduled task is missing") < source.index(
        "Build-LocalDockerScheduleImages -ProjectRoot $resolvedProjectRoot"
    )
    assert "-Schedules $selectedSchedules" in source
    assert "foreach ($schedule in $selectedSchedules)" in source
    assert "--project-directory `\"$resolvedProjectRoot`\"" in source
    assert "run --rm --no-deps --pull never $($schedule.Service)" in source
    assert "Build-LocalDockerScheduleImages" in source
    assert "Assert-LocalDockerScheduleImages" in source
    assert "build @services" in source
    assert "config --images @services" in source
    assert "Docker image build failed for scheduled task" in source
    assert "Required scheduled Docker image is missing for task" in source
    assert "build scheduled Docker service images" in source
    assert "Using verified existing schedule images." in source
    assert "kis-paper-intraday-pair-observation" in source
    assert "profiled-mtf-forward-capture-cycle" in source
    assert "kis-paper-prospective-spy-cycle" in source
    assert "kis-paper-prospective-spy-timing-probe" in source
    assert "kis-paper-prospective-qqq-session" in source
    assert "kis-paper-prospective-qqq-validation" in source
    assert "kis-paper-intraday-head-receipt" in source
    assert "Assert-KoreaStandardTime" in source
    assert '[System.TimeZoneInfo]::Local' in source
    assert '"Korea Standard Time"' in source
    assert '$selectedSchedules.Name -contains "thericher-kis-paper-daily-nas-forward"' in source
    assert '$selectedSchedules.Name -contains "thericher-kis-paper-quote-session"' in source
    assert '$selectedSchedules.Name -contains "thericher-kis-paper-snapshot-observer"' in source
    assert '$selectedSchedules.Name -contains "thericher-kis-paper-daily-spy-head"' in source
    stability_task = "thericher-kis-paper-daily-spy-stability-observer"
    assert f'$selectedSchedules.Name -contains "{stability_task}"' in source
    assert '$selectedSchedules.Name -contains "thericher-kis-paper-daily-spy-session"' in source
    assert '$selectedSchedules.Name -contains "thericher-kis-paper-daily-broad-backfill"' in source
    assert 'New-ScheduledTaskAction -Execute "powershell.exe"' in source
    assert "-NoProfile -ExecutionPolicy Bypass -File" in source
    assert '$schedule.ContainsKey("Runner")' in source
    assert '$schedule.ContainsKey("DaysOfWeek")' in source
    assert '"Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"' in source
    assert "New-ScheduledTaskTrigger -Weekly -DaysOfWeek $DaysOfWeek -At $_" in source
    assert 'At = "23:35"' in source
    assert 'At = "22:15"' in source
    assert 'At = "23:15"' in source
    assert 'At = "23:50"' in source
    assert 'At = @("00:29", "02:28", "04:24", "06:20")' in source
    assert 'At = "07:00"' in source
    assert 'At = "06:40"' in source
    assert 'At = "06:55"' in source
    for task_name, recover_missed_run, execution_limit_minutes in (
        ("thericher-kis-paper-quote-session", False, 90),
        ("thericher-kis-paper-snapshot-observer", False, 4),
        ("thericher-kis-paper-daily-spy-head", True, 90),
        ("thericher-kis-paper-daily-spy-stability-observer", False, 5),
        ("thericher-kis-paper-daily-spy-session", False, 90),
        ("thericher-kis-paper-intraday-head", True, 90),
        ("thericher-kis-paper-daily-nas-forward", True, 90),
        ("thericher-kis-paper-daily-pair-forward", True, 10),
        ("thericher-kis-paper-daily-broad-backfill", True, 870),
        ("thericher-kis-paper-daily-backfill", True, 390),
    ):
        entry = source.split(f'Name = "{task_name}"', maxsplit=1)[1].split(
            "    },", maxsplit=1
        )[0]
        assert f"RecoverMissedRun = ${str(recover_missed_run).lower()}" in entry
        assert f"ExecutionLimitMinutes = {execution_limit_minutes}" in entry
    assert "$times = @($schedule.At)" in source
    assert "function New-LocalDockerScheduleTriggers" in source
    assert "$hasRepetitionInterval -ne $hasRepetitionDuration" in source
    assert "MSFT_TaskRepetitionPattern" in source
    assert "StopAtDurationEnd = $true" in source
    assert "New-LocalDockerScheduleTriggers -Schedule $schedule -DaysOfWeek $daysOfWeek" in source
    assert "-Trigger $triggers" in source
    assert (
        "New-ScheduledTaskPrincipal -UserId $currentUser "
        "-LogonType Interactive -RunLevel Limited"
    ) in source
    assert "New-LocalDockerTaskSettings" in source
    assert "AllowStartIfOnBatteries = $true" in source
    assert "DontStopIfGoingOnBatteries = $true" in source
    assert "New-TimeSpan -Minutes $ExecutionLimitMinutes" in source
    assert 'MultipleInstances = "IgnoreNew"' in source
    assert "RestartCount = 0" in source
    assert '$settingsArguments["StartWhenAvailable"] = $true' in source
    assert "-Settings $settings" in source
    assert "Register-ScheduledTask" in source
    assert "-Force" in source
    assert "Start-ScheduledTask" not in source
    assert "Start-Process" not in source
    assert "Invokes only the local Docker profile" in source


def test_intraday_head_kst_days_map_to_prior_eastern_weekdays() -> None:
    head_times = ("00:29", "02:28", "04:24", "06:20")
    cases = (
        (date(2026, 1, 6), ("10:29", "12:28", "14:24", "16:20")),
        (date(2026, 7, 7), ("11:29", "13:28", "15:24", "17:20")),
    )

    for first_tuesday, expected_eastern_times in cases:
        for offset in range(5):
            kst_date = first_tuesday + timedelta(days=offset)
            eastern_times = tuple(
                datetime.combine(kst_date, time.fromisoformat(head_time))
                .replace(tzinfo=ZoneInfo("Asia/Seoul"))
                .astimezone(ZoneInfo("America/New_York"))
                for head_time in head_times
            )

            assert {value.date() for value in eastern_times} == {
                kst_date - timedelta(days=1)
            }
            assert all(value.weekday() < 5 for value in eastern_times)
            assert tuple(value.strftime("%H:%M") for value in eastern_times) == (
                expected_eastern_times
            )


def test_intraday_head_trigger_leaves_static_margin_before_prefix_workers() -> None:
    kst_day = date(2026, 8, 5)
    head = datetime.combine(kst_day, time.fromisoformat("04:24"))
    negative_control = datetime.combine(kst_day, time.fromisoformat("04:29:30"))
    feasibility = datetime.combine(kst_day, time.fromisoformat("04:30"))

    assert negative_control - head >= timedelta(minutes=5, seconds=30)
    assert feasibility - head >= timedelta(minutes=6)


def test_same_date_kst_schedules_map_to_same_eastern_weekdays() -> None:
    kst_weekdays = tuple(range(5))
    for first_monday in (date(2026, 1, 5), date(2026, 7, 6)):
        for offset in kst_weekdays:
            kst_date = first_monday + timedelta(days=offset)
            for schedule_time in SAME_DATE_KST_SCHEDULES.values():
                eastern = (
                    datetime.combine(kst_date, time.fromisoformat(schedule_time))
                    .replace(tzinfo=ZoneInfo("Asia/Seoul"))
                    .astimezone(ZoneInfo("America/New_York"))
                )

                assert eastern.date() == kst_date
                assert eastern.weekday() == kst_date.weekday()
                assert eastern.weekday() < 5


def test_kis_paper_schedule_installer_has_no_secret_or_unapproved_route_surface() -> None:
    source = SCRIPT.read_text(encoding="ascii").lower()

    assert ".env" not in source
    assert "kis_paper_app_key" not in source
    assert "kis_paper_app_secret" not in source
    assert "kis_paper_account" not in source
    assert "account" not in source
    assert "order" not in source
    assert "live" not in source
    assert "password" not in source
    assert "secret" not in source


@pytest.mark.parametrize(
    ("selection", "existing", "expected_count", "expected_enabled", "expires", "blocked"),
    [
        ("", "absent", 6, True, False, False),
        ("thericher-kis-paper-quote-session", "absent", 1, True, False, False),
        ("thericher-kis-paper-quote-session", "disabled", 1, False, False, False),
        ("thericher-kis-paper-quote-session", "trigger_disabled", 1, True, False, False),
        ("thericher-kis-paper-d1-prospective-observation-pairing", "expired", 1, True, True, False),
        ("thericher-kis-paper-daily-pair-forward", "running", 0, True, False, True),
    ],
)
def test_installer_preserves_retirement_with_mocked_windows_tasks(
    tmp_path: Path,
    selection: str,
    existing: str,
    expected_count: int,
    expected_enabled: bool,
    expires: bool,
    blocked: bool,
) -> None:
    script_path = str(SCRIPT).replace("'", "''")
    project_path = str(SCRIPT.parents[1]).replace("'", "''")
    harness = tmp_path / "installer.ps1"
    # Every external command is replaced; this exercises the real installer flow.
    harness.write_text(
        r"""
$ErrorActionPreference = 'Stop'
Import-Module Microsoft.PowerShell.Management, Microsoft.PowerShell.Utility
$PSModuleAutoLoadingPreference = 'None'
$global:registered = @()
$global:buildCalls = 0
function docker.exe { $global:buildCalls += 1; $global:LASTEXITCODE = 0 }
function New-ScheduledTaskPrincipal { param($UserId, $LogonType, $RunLevel) @{} }
function New-ScheduledTaskAction { param($Execute, $Argument) @{} }
function New-ScheduledTaskTrigger {
    param([switch]$Weekly, $DaysOfWeek, $At)
    [pscustomobject]@{
        Repetition=$null; EndBoundary=''; Enabled=$true; StartBoundary="2030-01-01T${At}:00+09:00"
    }
}
function New-CimInstance { param([switch]$ClientOnly, $Namespace, $ClassName, $Property) $Property }
function New-ScheduledTaskSettingsSet {
    param([switch]$AllowStartIfOnBatteries, [switch]$DontStopIfGoingOnBatteries,
          $ExecutionTimeLimit, $MultipleInstances, $RestartCount,
          [switch]$StartWhenAvailable, [switch]$Disable)
    [pscustomobject]@{Enabled=(-not $Disable)}
}
function Get-ScheduledTask {
    param($TaskName, $ErrorAction)
    if ($global:existing -eq 'absent') { return $null }
    [pscustomobject]@{
        State=$(if ($global:existing -eq 'running') {'Running'} else {'Ready'})
        Settings=[pscustomobject]@{Enabled=($global:existing -ne 'disabled')}
        Triggers=@(foreach ($at in @('08:15','23:20')) {
            [pscustomobject]@{
                Enabled=($global:existing -ne 'trigger_disabled')
                StartBoundary="2020-01-01T${at}:00+09:00"
                EndBoundary=$(if ($global:existing -eq 'expired') {
                    '2020-01-02T00:00:00+09:00'
                } else {''})
            }
        })
    }
}
function Register-ScheduledTask {
    param($TaskName, $Action, $Trigger, $Principal, $Settings, $Description, [switch]$Force)
    $global:registered += [pscustomobject]@{
        Name=$TaskName; Enabled=$Settings.Enabled; Ends=@($Trigger.EndBoundary)
        Starts=@($Trigger.StartBoundary); TriggerEnabled=@($Trigger.Enabled)
    }
}
"""
        + f"\n$global:existing = '{existing}'\n"
        + "try {\n"
        + f"    & '{script_path}' -ProjectRoot '{project_path}'"
        + (f" -ScheduleName '{selection}'" if selection else "")
        + "\n    $blocked = $false\n"
        + "} catch {\n"
        + "    if ($_.Exception.Message -notlike 'Cannot replace an active scheduled task:*') "
        + "{ throw }\n"
        + "    $blocked = $true\n}\n"
        + "@{registered=@($global:registered); blocked=$blocked; builds=$global:buildCalls} "
        + "| ConvertTo-Json -Depth 5 -Compress\n",
        encoding="ascii",
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(harness)],
        capture_output=True,
        text=True,
        check=False,
        timeout=40,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["blocked"] is blocked
    assert payload["builds"] == (0 if blocked else expected_count)
    registered = payload["registered"]
    assert len(registered) == expected_count
    for entry in registered:
        assert entry["Enabled"] is expected_enabled
        assert all(bool(value) is expires for value in entry["Ends"])
        if existing in {"expired", "trigger_disabled"}:
            assert entry["Starts"] == [
                "2020-01-01T08:15:00+09:00", "2020-01-01T23:20:00+09:00"
            ]
            assert entry["TriggerEnabled"] == [existing != "trigger_disabled"] * 2
        if expires:
            assert entry["Ends"] == ["2020-01-02T00:00:00+09:00"] * 2
    if not selection:
        assert {entry["Name"] for entry in registered} == {
            "thericher-kis-paper-snapshot-observer",
            "thericher-kis-paper-daily-spy-head",
            "thericher-kis-paper-daily-spy-session",
            "thericher-kis-paper-intraday-head",
            "thericher-kis-paper-daily-nas-forward",
            "thericher-kis-paper-daily-pair-forward",
        }
