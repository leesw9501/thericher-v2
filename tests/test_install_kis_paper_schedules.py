from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "install_kis_paper_schedules.ps1"
INTRADAY_HEAD_RUNNER = SCRIPT.parent / "run_kis_paper_intraday_head_schedule.ps1"
QUIET_LAUNCHER_SHA256 = "9fe9750cb432a20dc0b147c32209c859803515324a9aa3c0a1fc14aed716b39c"

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
    return source.split(f'Name = "{task_name}"', maxsplit=1)[1].split("    },", maxsplit=1)[0]


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
        assert 'DaysOfWeek = @("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")' in entry
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
    forward_entry = source.split('Name = "thericher-kis-paper-daily-nas-forward"', maxsplit=1)[
        1
    ].split("    },", maxsplit=1)[0]
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
    broad_entry = source.split('Name = "thericher-kis-paper-daily-broad-backfill"', maxsplit=1)[
        1
    ].split("    },", maxsplit=1)[0]
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
    assert '--project-directory `"$resolvedProjectRoot`"' in source
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
    assert "[System.TimeZoneInfo]::Local" in source
    assert '"Korea Standard Time"' in source
    assert '$selectedSchedules.Name -contains "thericher-kis-paper-daily-nas-forward"' in source
    assert '$selectedSchedules.Name -contains "thericher-kis-paper-quote-session"' in source
    assert '$selectedSchedules.Name -contains "thericher-kis-paper-snapshot-observer"' in source
    assert '$selectedSchedules.Name -contains "thericher-kis-paper-daily-spy-head"' in source
    stability_task = "thericher-kis-paper-daily-spy-stability-observer"
    assert f'$selectedSchedules.Name -contains "{stability_task}"' in source
    assert '$selectedSchedules.Name -contains "thericher-kis-paper-daily-spy-session"' in source
    assert '$selectedSchedules.Name -contains "thericher-kis-paper-daily-broad-backfill"' in source
    assert "return New-ScheduledTaskAction @actionParameters" in source
    assert '$childExecute = Resolve-QuietTaskExecutable -Name "powershell.exe"' in source
    assert '$childExecute = Resolve-QuietTaskExecutable -Name "docker.exe"' in source
    assert '-I -B `"$launcher`" --execute --config' in source
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
        ("thericher-kis-paper-daily-spy-session", False, 25),
        ("thericher-kis-paper-intraday-head", True, 90),
        ("thericher-kis-paper-daily-nas-forward", True, 90),
        ("thericher-kis-paper-daily-pair-forward", True, 10),
        ("thericher-kis-paper-daily-broad-backfill", True, 870),
        ("thericher-kis-paper-daily-backfill", True, 390),
    ):
        entry = source.split(f'Name = "{task_name}"', maxsplit=1)[1].split("    },", maxsplit=1)[0]
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
        "New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited"
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

            assert {value.date() for value in eastern_times} == {kst_date - timedelta(days=1)}
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
    assert not re.search(r"\border\b", source)
    assert "live" not in source
    assert "password" not in source
    assert "secret" not in source


def _ps_string(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


@pytest.fixture
def installer_sandbox(tmp_path: Path) -> dict[str, Path]:
    if sys.platform != "win32":
        pytest.skip("Native mocked installer requires Windows PowerShell")
    project = tmp_path / "paper project's root"
    scripts = project / "scripts"
    scripts.mkdir(parents=True)
    source = SCRIPT.read_text(encoding="ascii")
    for runner in re.findall(r'(?:Runner|PythonRunner) = "([^"]+)"', source):
        (scripts / runner).write_text("# Synthetic; must never execute.\n", encoding="ascii")
    (scripts / "run_owned_task_quiet.py").write_bytes(
        (SCRIPT.parent / "run_owned_task_quiet.py").read_bytes()
    )
    (project / "docker-compose.yml").write_text("services: {}\n", encoding="ascii")
    base = tmp_path / "base python"
    base.mkdir()
    for name in ("python.exe", "pythonw.exe"):
        (base / name).write_bytes(b"synthetic executable; never launched")
    venv = project / ".venv"
    (venv / "Scripts").mkdir(parents=True)
    (venv / "Scripts" / "pythonw.exe").write_bytes(b"must not use venv launcher")
    (venv / "pyvenv.cfg").write_text(f"home = {base}\nimplementation = CPython\n", encoding="ascii")
    binary = tmp_path / "synthetic bin"
    binary.mkdir()
    paths = {
        "project": project,
        "base": base,
        "artifacts": tmp_path / "quiet artifacts",
        "harness": tmp_path / "installer-synthetic.ps1",
        "docker": binary / "docker.exe",
        "powershell": binary / "powershell.exe",
        "uv": binary / "uv's tool.exe",
    }
    for name in ("docker", "powershell", "uv"):
        paths[name].write_bytes(b"synthetic executable; never launched")
    return paths


def _installer_call(paths: dict[str, Path], selection: str = "", options: str = "") -> str:
    return (
        f"& {_ps_string(SCRIPT)} -ProjectRoot {_ps_string(paths['project'])} "
        f"-QuietArtifactRoot {_ps_string(paths['artifacts'])} "
        + (f"-ScheduleName {_ps_string(selection)} " if selection else "")
        + options
    )


def _run_mocked_installer(
    paths: dict[str, Path],
    body: str,
    *,
    existing: str = "absent",
    reparse: Path | None = None,
    confirmation: str | None = None,
) -> dict:
    # Autoload is off; every Scheduler entry point is mocked or fails closed.
    harness = r"""
$ErrorActionPreference = 'Stop'
$PSModuleAutoLoadingPreference = 'None'
Import-Module Microsoft.PowerShell.Management, Microsoft.PowerShell.Utility
$global:registered = @()
$global:actions = @()
$global:buildCalls = 0
$global:taskReads = 0
function docker.exe {
    if ($args -contains 'build') { $global:buildCalls += 1 }
    else { throw 'Unexpected synthetic Docker invocation' }
    $global:LASTEXITCODE = 0
}
function powershell.exe { throw 'Child must not launch in installer tests' }
function uv { throw 'Child must not launch in installer tests' }
function Get-Command {
    param($Name, $CommandType, $ErrorAction)
    if (-not $global:commands.ContainsKey($Name)) { throw 'Unexpected command lookup' }
    [pscustomobject]@{Source=$global:commands[$Name]}
}
function Get-Item {
    [CmdletBinding()]
    param($LiteralPath, [switch]$Force)
    if ($LiteralPath -eq $global:reparse) {
        return [pscustomobject]@{Attributes=[System.IO.FileAttributes]::ReparsePoint}
    }
    Microsoft.PowerShell.Management\Get-Item @PSBoundParameters
}
function New-ScheduledTaskPrincipal {
    param($UserId, $LogonType, $RunLevel)
    [pscustomobject]@{
        SameUser=($UserId -eq [System.Security.Principal.WindowsIdentity]::GetCurrent().Name)
        LogonType=$LogonType; RunLevel=$RunLevel
    }
}
function New-ScheduledTaskAction {
    param($Execute, $Argument, $WorkingDirectory)
    $action = [pscustomobject]@{
        Execute=$Execute; Arguments=$Argument; WorkingDirectory=$WorkingDirectory
        CwdBound=$PSBoundParameters.ContainsKey('WorkingDirectory')
    }
    $global:actions += $action
    $action
}
function New-ScheduledTaskTrigger {
    param([switch]$Weekly, $DaysOfWeek, $At)
    [pscustomobject]@{
        Repetition=$null; EndBoundary=''; Enabled=$true; StartBoundary="2030-01-01T${At}:00+09:00"
        Weekly=[bool]$Weekly; DaysOfWeek=@($DaysOfWeek); At=$At
    }
}
function New-CimInstance { param([switch]$ClientOnly, $Namespace, $ClassName, $Property) $Property }
function New-ScheduledTaskSettingsSet {
    param([switch]$AllowStartIfOnBatteries, [switch]$DontStopIfGoingOnBatteries,
          $ExecutionTimeLimit, $MultipleInstances, $RestartCount,
          [switch]$StartWhenAvailable, [switch]$Disable)
    [pscustomobject]@{
        Enabled=(-not $Disable); ExecutionSeconds=$ExecutionTimeLimit.TotalSeconds
        MultipleInstances=$MultipleInstances; RestartCount=$RestartCount
        StartWhenAvailable=[bool]$StartWhenAvailable
        AllowStartIfOnBatteries=[bool]$AllowStartIfOnBatteries
        DontStopIfGoingOnBatteries=[bool]$DontStopIfGoingOnBatteries
    }
}
function Get-ScheduledTask {
    param($TaskName, $ErrorAction)
    $global:taskReads += 1
    if ($global:existing -eq 'absent') { return $null }
    $running = $global:existing -eq 'running' -or (
        $global:existing -eq 'late_running' -and $global:taskReads -ge 3
    )
    [pscustomobject]@{
        State=$(if ($running) {'Running'} else {'Ready'})
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
        Action=$Action; Principal=$Principal; Settings=$Settings; Triggers=@($Trigger)
        Description=$Description; Force=[bool]$Force
    }
}
foreach ($name in @('Start-ScheduledTask','Stop-ScheduledTask','Set-ScheduledTask',
    'Enable-ScheduledTask','Disable-ScheduledTask','Unregister-ScheduledTask',
    'Export-ScheduledTask','Get-ScheduledTaskInfo','New-ScheduledTask')) {
    Set-Item -Path "Function:global:$name" -Value { throw 'Unexpected Scheduler entry point' }
}
"""
    harness += (
        f"\n$global:existing = {_ps_string(existing)}\n"
        f"$global:reparse = {_ps_string(reparse or '')}\n"
        "$global:commands = @{"
        + ";".join(
            f"'{name}'={_ps_string(paths[key])}"
            for name, key in (
                ("docker.exe", "docker"),
                ("powershell.exe", "powershell"),
                ("uv", "uv"),
            )
        )
        + "}\n$failure = $null\ntry {\n"
        + body
        + "\n} catch { $failure = $_.Exception.Message }\n"
        + "@{registered=@($global:registered); actions=@($global:actions); "
        + "failure=$failure; builds=$global:buildCalls; autoload=$PSModuleAutoLoadingPreference} "
        + "| ConvertTo-Json -Depth 12 -Compress\n"
    )
    paths["harness"].write_text(harness, encoding="ascii")
    result = subprocess.run(
        ["powershell.exe", "-NoProfile"]
        + (["-NonInteractive"] if confirmation is None else [])
        + ["-ExecutionPolicy", "Bypass", "-File", str(paths["harness"])],
        capture_output=True,
        text=True,
        input=confirmation,
        check=False,
        timeout=40,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["autoload"] == "None"
    return payload


def _quiet_config(paths: dict[str, Path], action: dict) -> dict:
    assert Path(action["Execute"]) == paths["base"] / "pythonw.exe"
    match = re.fullmatch(
        r'-I -B "([^"]+)" --execute --config "([^"]+)" --sha256 ([a-f0-9]{64})',
        action["Arguments"],
    )
    assert match is not None
    launcher, config_path, digest = match.groups()
    assert Path(launcher).parent == paths["artifacts"]
    assert Path(launcher).read_bytes() == (SCRIPT.parent / "run_owned_task_quiet.py").read_bytes()
    assert hashlib.sha256(Path(launcher).read_bytes()).hexdigest() == QUIET_LAUNCHER_SHA256
    config_bytes = Path(config_path).read_bytes()
    assert hashlib.sha256(config_bytes).hexdigest() == digest
    assert Path(config_path).stem == digest
    config = json.loads(config_bytes)
    assert set(config) == {"task", "execute", "arguments", "working_directory", "receipt_root"}
    assert Path(config["receipt_root"]) == paths["artifacts"] / config["task"] / "launches"
    assert "run_owned_task_quiet.py" not in config["arguments"]
    assert "launcher-" not in config["arguments"]
    return config


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
    installer_sandbox: dict[str, Path],
    selection: str,
    existing: str,
    expected_count: int,
    expected_enabled: bool,
    expires: bool,
    blocked: bool,
) -> None:
    payload = _run_mocked_installer(
        installer_sandbox, _installer_call(installer_sandbox, selection), existing=existing
    )
    if blocked:
        assert payload["failure"].startswith("Cannot replace an active scheduled task:")
        assert not installer_sandbox["artifacts"].exists()
    else:
        assert payload["failure"] is None
    assert payload["builds"] == (0 if blocked else expected_count)
    registered = payload["registered"]
    assert len(registered) == expected_count
    for entry in registered:
        config = _quiet_config(installer_sandbox, entry["Action"])
        assert config["task"] == entry["Name"]
        assert config["working_directory"] is None
        assert entry["Action"]["CwdBound"] is False
        assert entry["Enabled"] is expected_enabled
        assert all(bool(value) is expires for value in entry["Ends"])
        if existing in {"expired", "trigger_disabled"}:
            assert entry["Starts"] == ["2020-01-01T08:15:00+09:00", "2020-01-01T23:20:00+09:00"]
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


@pytest.mark.parametrize("branch", ["docker", "runner", "python"])
def test_installer_quiet_actions_preserve_canonical_argv_and_metadata(
    installer_sandbox: dict[str, Path], branch: str
) -> None:
    paths = installer_sandbox
    project = str(paths["project"])
    if branch == "docker":
        name = "thericher-kis-paper-quote-session"
        profile = "kis-paper-session"
        expected = (
            f'compose --project-directory "{project}" --profile {profile} '
            f"run --rm --no-deps --pull never {profile}"
        )
        child = paths["docker"]
        minutes, times, monday = 90, ["23:35"], True
    elif branch == "runner":
        name = "thericher-kis-paper-spy-prefix-negative-control"
        profile = "kis-spy-paginated-prefix-capability"
        runner = (
            paths["project"] / "scripts" / "run_kis_spy_paginated_prefix_capability_schedule.ps1"
        )
        expected = (
            f'-NoProfile -ExecutionPolicy Bypass -File "{runner}" '
            f'-ProjectRoot "{project}" -Stage "negative-control"'
        )
        child = paths["powershell"]
        minutes, times, monday = 10, ["04:29:30", "05:29:30"], False
    else:
        name = "thericher-kis-paper-daily-spy-session"
        profile = "kis-paper-daily-spy-session"
        runner = paths["project"] / "scripts" / "run_kis_paper_budget_strategy.py"
        command = (
            f"& {_ps_string(paths['uv'])} run --no-sync --project {_ps_string(project)} "
            f"python {_ps_string(runner)} --execute --visits 24; exit $LASTEXITCODE"
        )
        expected = (
            "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass "
            f'-Command "{command}"'
        )
        child = paths["powershell"]
        minutes, times, monday = 25, ["23:50"], True
    payload = _run_mocked_installer(paths, _installer_call(paths, name))
    assert payload["failure"] is None
    assert len(payload["registered"]) == 1
    entry = payload["registered"][0]
    config = _quiet_config(paths, entry["Action"])
    assert config["execute"] == str(child)
    assert config["arguments"] == expected
    assert config["working_directory"] is None
    assert entry["Action"]["CwdBound"] is False
    assert entry["Principal"] == {
        "SameUser": True,
        "LogonType": "Interactive",
        "RunLevel": "Limited",
    }
    assert entry["Settings"] == {
        "Enabled": True,
        "ExecutionSeconds": minutes * 60,
        "MultipleInstances": "IgnoreNew",
        "RestartCount": 0,
        "StartWhenAvailable": False,
        "AllowStartIfOnBatteries": True,
        "DontStopIfGoingOnBatteries": True,
    }
    assert entry["Description"] == (
        f"Invokes only the local Docker profile '{profile}' for TheRicher KIS Paper automation."
    )
    assert entry["Force"] is True
    days = (
        ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        if monday
        else ["Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    )
    assert [trigger["At"] for trigger in entry["Triggers"]] == times
    assert all(trigger["DaysOfWeek"] == days for trigger in entry["Triggers"])
    assert all(trigger["Weekly"] and trigger["Enabled"] for trigger in entry["Triggers"])


def test_installer_quiet_action_preserves_observer_repetition(
    installer_sandbox: dict[str, Path],
) -> None:
    paths = installer_sandbox
    payload = _run_mocked_installer(
        paths, _installer_call(paths, "thericher-kis-paper-snapshot-observer")
    )
    assert payload["failure"] is None
    entry = payload["registered"][0]
    _quiet_config(paths, entry["Action"])
    assert entry["Triggers"][0]["Repetition"] == {
        "Interval": "PT4M",
        "Duration": "PT600M",
        "StopAtDurationEnd": True,
    }
    assert entry["Settings"]["ExecutionSeconds"] == 240


@pytest.mark.parametrize("preview", ["whatif", "declined"])
def test_installer_quiet_preview_never_publishes_or_registers(
    installer_sandbox: dict[str, Path], preview: str
) -> None:
    paths = installer_sandbox
    payload = _run_mocked_installer(
        paths,
        _installer_call(
            paths,
            "thericher-kis-paper-quote-session",
            "-WhatIf" if preview == "whatif" else "-Confirm",
        ),
        confirmation="n\nn\n" if preview == "declined" else None,
    )
    assert payload["failure"] is None
    assert payload["builds"] == 0
    assert payload["registered"] == payload["actions"] == []
    assert not paths["artifacts"].exists()


def test_installer_quiet_active_recheck_precedes_publication(
    installer_sandbox: dict[str, Path],
) -> None:
    paths = installer_sandbox
    payload = _run_mocked_installer(
        paths, _installer_call(paths, "thericher-kis-paper-quote-session"), existing="late_running"
    )
    assert payload["failure"].startswith("Cannot replace an active scheduled task:")
    assert payload["builds"] == 1
    assert payload["registered"] == payload["actions"] == []
    assert not paths["artifacts"].exists()


@pytest.mark.parametrize(
    "fault",
    [
        "missing_cfg",
        "relative_home",
        "duplicate_home",
        "missing_pythonw",
        "missing_launcher",
        "source_mismatch",
        "reparse",
    ],
)
def test_installer_quiet_invalid_launch_source_has_no_visible_fallback(
    installer_sandbox: dict[str, Path], fault: str
) -> None:
    paths = installer_sandbox
    cfg = paths["project"] / ".venv" / "pyvenv.cfg"
    launcher = paths["project"] / "scripts" / "run_owned_task_quiet.py"
    if fault == "missing_cfg":
        cfg.unlink()
    elif fault == "relative_home":
        cfg.write_text("home = C:relative\n", encoding="ascii")
    elif fault == "duplicate_home":
        cfg.write_text(f"home = {paths['base']}\nhome = {paths['base']}\n", encoding="ascii")
    elif fault == "missing_pythonw":
        (paths["base"] / "pythonw.exe").unlink()
    elif fault == "missing_launcher":
        launcher.unlink()
    elif fault == "source_mismatch":
        launcher.write_bytes(launcher.read_bytes() + b"\n# changed source\n")
    payload = _run_mocked_installer(
        paths,
        _installer_call(paths, "thericher-kis-paper-quote-session"),
        reparse=paths["artifacts"] if fault == "reparse" else None,
    )
    assert payload["failure"] is not None
    if fault == "source_mismatch":
        assert payload["failure"] == "Quiet task launcher source mismatch."
    if fault == "reparse":
        assert payload["failure"] == "Quiet task path must not contain a reparse point."
    assert payload["registered"] == payload["actions"] == []
    assert not paths["artifacts"].exists()


def test_installer_quiet_reinstall_is_immutable_and_not_nested(
    installer_sandbox: dict[str, Path],
) -> None:
    paths = installer_sandbox
    call = _installer_call(paths, "thericher-kis-paper-daily-spy-session")
    first = _run_mocked_installer(paths, call)
    assert first["failure"] is None
    config = _quiet_config(paths, first["registered"][0]["Action"])
    files = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in paths["artifacts"].rglob("*")
        if path.is_file()
    }
    second = _run_mocked_installer(paths, call, existing="ready")
    assert second["failure"] is None
    assert second["registered"][0]["Action"] == first["registered"][0]["Action"]
    assert _quiet_config(paths, second["registered"][0]["Action"]) == config
    assert {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in paths["artifacts"].rglob("*")
        if path.is_file()
    } == files


@pytest.mark.parametrize("target", ["launcher", "config"])
def test_installer_quiet_frozen_byte_mismatch_is_not_overwritten(
    installer_sandbox: dict[str, Path], target: str
) -> None:
    paths = installer_sandbox
    call = _installer_call(paths, "thericher-kis-paper-quote-session")
    assert _run_mocked_installer(paths, call)["failure"] is None
    selected = (
        next(paths["artifacts"].glob("launcher-*.py"))
        if target == "launcher"
        else next(paths["artifacts"].rglob("*.json"))
    )
    selected.write_bytes(b"synthetic corrupted frozen bytes")
    before = {path: path.read_bytes() for path in paths["artifacts"].rglob("*") if path.is_file()}
    payload = _run_mocked_installer(paths, call)
    assert payload["failure"] == "Quiet task immutable file differs from its source."
    assert payload["registered"] == payload["actions"] == []
    assert {
        path: path.read_bytes() for path in paths["artifacts"].rglob("*") if path.is_file()
    } == before


@pytest.mark.parametrize("explicit_cwd", [False, True])
def test_installer_quiet_factory_preserves_raw_arguments_and_nullable_cwd(
    installer_sandbox: dict[str, Path], explicit_cwd: bool
) -> None:
    paths = installer_sandbox
    raw = '"space value" "" "quote\\"value" plain --tail="two words"'
    # Load only function ASTs: no installer entry point or Scheduler interaction.
    body = (
        "$tokens = $null; $errors = $null\n"
        "$ast = [System.Management.Automation.Language.Parser]::ParseFile("
        f"{_ps_string(SCRIPT)}, [ref]$tokens, [ref]$errors)\n"
        "if ($errors.Count -ne 0) { throw 'Installer parse failure' }\n"
        "foreach ($node in $ast.FindAll({ param($node) $node -is "
        "[System.Management.Automation.Language.FunctionDefinitionAst] }, $false)) {\n"
        "    . ([scriptblock]::Create($node.Extent.Text))\n}\n"
        f"$null = New-QuietLocalDockerTaskAction -ProjectRoot {_ps_string(paths['project'])} "
        f"-ArtifactRoot {_ps_string(paths['artifacts'])} -TaskName synthetic-argv "
        f"-Execute {_ps_string(paths['powershell'])} -Arguments {_ps_string(raw)} "
        + (
            f"-WorkingDirectory {_ps_string(paths['project'])}"
            if explicit_cwd
            else "-WorkingDirectory $null"
        )
    )
    payload = _run_mocked_installer(paths, body)
    assert payload["failure"] is None
    assert payload["registered"] == []
    assert len(payload["actions"]) == 1
    action = payload["actions"][0]
    config = _quiet_config(paths, action)
    assert config["arguments"] == raw
    assert config["working_directory"] == (str(paths["project"]) if explicit_cwd else None)
    assert action["CwdBound"] is explicit_cwd
    assert action["WorkingDirectory"] == (str(paths["project"]) if explicit_cwd else None)
