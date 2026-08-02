from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "install_kis_paper_schedules.ps1"
)


def test_kis_paper_schedule_installer_has_exact_task_surface() -> None:
    source = SCRIPT.read_text(encoding="ascii")

    assert source.count("thericher-kis-paper-daily-backfill") == 1
    assert source.count("thericher-kis-paper-quote-session") == 1
    assert source.count("thericher-kis-paper-daily-spy-head") == 1
    assert source.count("thericher-kis-paper-daily-spy-session") == 1
    assert source.count("thericher-kis-paper-intraday-head") == 1
    assert source.count('Name = "thericher-kis-paper-daily-nas-forward"') == 1
    assert source.count('Name = "thericher-kis-paper-daily-pair-forward"') == 1
    assert source.count('Name = "thericher-kis-paper-daily-broad-backfill"') == 1
    assert source.count('Profile = "kis-paper-daily-backfill"') == 1
    assert source.count('Profile = "kis-paper-session"') == 1
    assert source.count('Profile = "kis-paper-daily-spy-head"') == 1
    assert source.count('Profile = "kis-paper-daily-spy-session"') == 1
    assert source.count('Profile = "kis-paper-intraday-head"') == 1
    assert source.count('Profile = "kis-paper-daily-nas-forward"') == 1
    assert source.count('Profile = "kis-paper-daily-pair-forward"') == 1
    assert source.count('Profile = "kis-paper-daily-broad-backfill"') == 1
    assert source.count('Service = "kis-paper-daily-backfill"') == 1
    assert source.count('Service = "kis-paper-session"') == 1
    assert source.count('Service = "kis-paper-daily-spy-head"') == 1
    assert source.count('Service = "kis-paper-daily-spy-session"') == 1
    assert source.count('Service = "kis-paper-intraday-head"') == 1
    assert source.count('Service = "kis-paper-daily-nas-forward"') == 1
    assert source.count('Service = "kis-paper-daily-pair-forward"') == 1
    assert source.count('Service = "kis-paper-daily-broad-backfill"') == 1
    assert source.count('Runner = "run_kis_paper_intraday_head_schedule.ps1"') == 1
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
    assert 'Profile = "kis-paper-daily-pair-forward"' in pair_forward_entry
    assert 'Service = "kis-paper-daily-pair-forward"' in pair_forward_entry
    assert 'Runner = "run_kis_paper_daily_pair_forward_schedule.ps1"' in pair_forward_entry
    assert '"kis-paper-daily-pair-forward-preflight"' in pair_forward_entry
    assert '"kis-paper-daily-pair-forward"' in pair_forward_entry
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
    assert broad_times == tuple(
        f"{hour:02d}:{minute:02d}"
        for hour in range(24)
        for minute in (15, 45)
    )
    assert "RecoverMissedRun = $false" in broad_entry
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
    assert "kis-paper-prospective-qqq-session" not in source
    assert "kis-paper-prospective-qqq-validation" not in source
    assert "kis-paper-intraday-head-receipt" in source
    assert "Assert-KoreaStandardTime" in source
    assert '[System.TimeZoneInfo]::Local' in source
    assert '"Korea Standard Time"' in source
    assert '$selectedSchedules.Name -contains "thericher-kis-paper-daily-nas-forward"' in source
    assert 'New-ScheduledTaskAction -Execute "powershell.exe"' in source
    assert "-NoProfile -ExecutionPolicy Bypass -File" in source
    assert '$schedule.ContainsKey("Runner")' in source
    assert (
        "New-ScheduledTaskTrigger -Weekly "
        "-DaysOfWeek Tuesday,Wednesday,Thursday,Friday,Saturday"
    ) in source
    assert 'At = "23:35"' in source
    assert 'At = "22:15"' in source
    assert 'At = "23:50"' in source
    assert 'At = @("00:31", "02:31", "04:31", "06:20")' in source
    assert 'At = "07:00"' in source
    assert 'At = "06:40"' in source
    assert 'At = "06:55"' in source
    for task_name, recover_missed_run, execution_limit_minutes in (
        ("thericher-kis-paper-quote-session", False, 90),
        ("thericher-kis-paper-daily-spy-head", True, 90),
        ("thericher-kis-paper-daily-spy-session", False, 90),
        ("thericher-kis-paper-intraday-head", True, 90),
        ("thericher-kis-paper-daily-nas-forward", True, 90),
        ("thericher-kis-paper-daily-pair-forward", True, 10),
        ("thericher-kis-paper-daily-broad-backfill", False, 870),
        ("thericher-kis-paper-daily-backfill", True, 390),
    ):
        entry = source.split(f'Name = "{task_name}"', maxsplit=1)[1].split(
            "    },", maxsplit=1
        )[0]
        assert f"RecoverMissedRun = ${str(recover_missed_run).lower()}" in entry
        assert f"ExecutionLimitMinutes = {execution_limit_minutes}" in entry
    assert "$times = @($schedule.At)" in source
    assert "$times | ForEach-Object" in source
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
    assert '$settingsArguments["StartWhenAvailable"] = $true' in source
    assert "-Settings $settings" in source
    assert "Register-ScheduledTask" in source
    assert "-Force" in source
    assert "Start-ScheduledTask" not in source
    assert "Start-Process" not in source
    assert "Invokes only the local Docker profile" in source


def test_intraday_head_kst_days_map_to_prior_eastern_weekdays() -> None:
    head_times = ("00:31", "02:31", "04:31", "06:20")
    cases = (
        (date(2026, 1, 6), ("10:31", "12:31", "14:31", "16:20")),
        (date(2026, 7, 7), ("11:31", "13:31", "15:31", "17:20")),
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
