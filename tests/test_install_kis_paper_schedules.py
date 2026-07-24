from __future__ import annotations

from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "install_kis_paper_schedules.ps1"
)


def test_kis_paper_schedule_installer_has_exact_task_surface() -> None:
    source = SCRIPT.read_text(encoding="ascii")

    assert source.count("thericher-kis-paper-daily-backfill") == 1
    assert source.count("thericher-kis-paper-quote-session") == 1
    assert source.count("thericher-kis-paper-intraday-head") == 1
    assert source.count('Profile = "kis-paper-daily-backfill"') == 1
    assert source.count('Profile = "kis-paper-session"') == 1
    assert source.count('Profile = "kis-paper-intraday-head"') == 1
    assert source.count('Service = "kis-paper-daily-backfill"') == 1
    assert source.count('Service = "kis-paper-session"') == 1
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


def test_kis_paper_schedule_installer_has_no_secret_or_unapproved_route_surface() -> None:
    source = SCRIPT.read_text(encoding="ascii").lower()

    assert ".env" not in source
    assert "kis_paper_" not in source
    assert "live" not in source
    assert "password" not in source
