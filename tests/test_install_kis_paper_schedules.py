from __future__ import annotations

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
    assert source.count('Profile = "kis-paper-daily-backfill"') == 1
    assert source.count('Profile = "kis-paper-session"') == 1
    assert source.count('Profile = "kis-paper-daily-spy-head"') == 1
    assert source.count('Profile = "kis-paper-daily-spy-session"') == 1
    assert source.count('Profile = "kis-paper-intraday-head"') == 1
    assert source.count('Service = "kis-paper-daily-backfill"') == 1
    assert source.count('Service = "kis-paper-session"') == 1
    assert source.count('Service = "kis-paper-daily-spy-head"') == 1
    assert source.count('Service = "kis-paper-daily-spy-session"') == 1
    assert source.count('Service = "kis-paper-intraday-head"') == 1


def test_kis_paper_schedule_installer_uses_required_windows_schedule_contract() -> None:
    source = SCRIPT.read_text(encoding="ascii")

    assert "[CmdletBinding(SupportsShouldProcess = $true" in source
    assert "$PSCmdlet.ShouldProcess" in source
    assert "Get-Command docker.exe" in source
    assert "docker-compose.yml" in source
    assert '[string]$ProjectRoot = (Join-Path $PSScriptRoot "..")' in source
    assert "Resolve-Path -LiteralPath $ProjectRoot" in source
    assert "--project-directory `\"$resolvedProjectRoot`\"" in source
    assert "run --rm --no-deps --build $($schedule.Service)" in source
    assert (
        "New-ScheduledTaskTrigger -Weekly "
        "-DaysOfWeek Tuesday,Wednesday,Thursday,Friday,Saturday"
    ) in source
    assert 'At = "23:35"' in source
    assert 'At = "22:15"' in source
    assert 'At = "23:50"' in source
    assert 'At = @("00:35", "02:35", "04:35", "06:20")' in source
    assert 'At = "07:00"' in source
    assert "$times = @($schedule.At)" in source
    assert "$times | ForEach-Object" in source
    assert "-Trigger $triggers" in source
    assert (
        "New-ScheduledTaskPrincipal -UserId $currentUser "
        "-LogonType Interactive -RunLevel Limited"
    ) in source
    assert "Register-ScheduledTask" in source
    assert "-Force" in source
    assert "Invokes only the local Docker profile" in source


def test_intraday_head_kst_days_map_to_prior_eastern_weekdays() -> None:
    head_times = ("00:35", "02:35", "04:35", "06:20")
    cases = (
        (date(2026, 1, 6), ("10:35", "12:35", "14:35", "16:20")),
        (date(2026, 7, 7), ("11:35", "13:35", "15:35", "17:20")),
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
    assert "kis_paper_" not in source
    assert "live" not in source
    assert "password" not in source
