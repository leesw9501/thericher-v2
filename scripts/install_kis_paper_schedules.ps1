[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "Medium")]
param(
    [string]$ProjectRoot = (Join-Path $PSScriptRoot ".."),
    [string[]]$ScheduleName = @(),
    [switch]$RequireExisting,
    [switch]$SkipImageBuild
)

$ErrorActionPreference = "Stop"

function New-LocalDockerTaskDescription {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Profile
    )

    return "Invokes only the local Docker profile '$Profile' for TheRicher KIS Paper automation."
}

function New-LocalDockerTaskSettings {
    param(
        [Parameter(Mandatory = $true)]
        [int]$ExecutionLimitMinutes,
        [Parameter(Mandatory = $true)]
        [bool]$RecoverMissedRun
    )

    $settingsArguments = @{
        AllowStartIfOnBatteries = $true
        DontStopIfGoingOnBatteries = $true
        ExecutionTimeLimit = (New-TimeSpan -Minutes $ExecutionLimitMinutes)
        MultipleInstances = "IgnoreNew"
    }
    if ($RecoverMissedRun) {
        $settingsArguments["StartWhenAvailable"] = $true
    }
    return New-ScheduledTaskSettingsSet @settingsArguments
}

function Assert-KoreaStandardTime {
    $localTimeZone = [System.TimeZoneInfo]::Local
    if (
        $localTimeZone.Id -ne "Korea Standard Time" `
            -or $localTimeZone.BaseUtcOffset -ne [TimeSpan]::FromHours(9)
    ) {
        throw "The NAS D1 forward schedule requires the host time zone Korea Standard Time."
    }
}

function Build-LocalDockerScheduleImages {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [Parameter(Mandatory = $true)]
        [hashtable[]]$Schedules
    )

    foreach ($schedule in $Schedules) {
        $services = @($schedule.ImageServices)
        if ($services.Count -eq 0) {
            continue
        }
        Write-Host "Building $($schedule.Name) schedule images."
        & docker.exe compose --project-directory $ProjectRoot --profile $schedule.Profile `
            build @services
        if ($LASTEXITCODE -ne 0) {
            throw "Docker image build failed for scheduled task: $($schedule.Name)"
        }
    }
}

function Assert-LocalDockerScheduleImages {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [Parameter(Mandatory = $true)]
        [hashtable[]]$Schedules
    )

    foreach ($schedule in $Schedules) {
        $services = @($schedule.ImageServices)
        if ($services.Count -eq 0) {
            continue
        }
        $images = @(
            & docker.exe compose --project-directory $ProjectRoot --profile $schedule.Profile `
                config --images @services
        )
        $imageExitCode = [int]$LASTEXITCODE
        if ($imageExitCode -ne 0 -or $images.Count -ne $services.Count) {
            throw "Unable to verify scheduled Docker images for task: $($schedule.Name)"
        }
        foreach ($image in $images) {
            & docker.exe image inspect $image | Out-Null
            if ($LASTEXITCODE -ne 0) {
                throw "Required scheduled Docker image is missing for task: $($schedule.Name)"
            }
        }
    }
}

if (-not (Get-Command docker.exe -ErrorAction SilentlyContinue)) {
    throw "docker.exe is required to install these local scheduled tasks."
}

$resolvedProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$composePath = Join-Path $resolvedProjectRoot "docker-compose.yml"
if (-not (Test-Path -LiteralPath $composePath -PathType Leaf)) {
    throw "Project root must contain docker-compose.yml: $resolvedProjectRoot"
}

$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited

$schedules = @(
    @{
        Name = "thericher-kis-paper-quote-session"
        Profile = "kis-paper-session"
        Service = "kis-paper-session"
        ImageServices = @("kis-paper-session")
        At = "23:35"
        RecoverMissedRun = $false
        ExecutionLimitMinutes = 90
    },
    @{
        Name = "thericher-kis-paper-daily-spy-head"
        Profile = "kis-paper-daily-spy-head"
        Service = "kis-paper-daily-spy-head"
        ImageServices = @("kis-paper-daily-spy-head")
        At = "22:15"
        RecoverMissedRun = $true
        ExecutionLimitMinutes = 90
    },
    @{
        Name = "thericher-kis-paper-daily-spy-session"
        Profile = "kis-paper-daily-spy-session"
        Service = "kis-paper-daily-spy-session"
        ImageServices = @("kis-paper-daily-spy-session")
        At = "23:50"
        RecoverMissedRun = $false
        ExecutionLimitMinutes = 90
    },
    @{
        Name = "thericher-kis-paper-intraday-head"
        Profile = "kis-paper-intraday-head"
        Service = "kis-paper-intraday-head"
        Runner = "run_kis_paper_intraday_head_schedule.ps1"
        ImageServices = @(
            "kis-paper-intraday-head",
            "kis-paper-prospective-qqq-session",
            "kis-paper-prospective-qqq-validation",
            "kis-paper-intraday-observation",
            "kis-paper-intraday-head-receipt"
        )
        At = @("00:31", "02:31", "04:31", "06:20")
        RecoverMissedRun = $true
        ExecutionLimitMinutes = 90
    },
    @{
        Name = "thericher-kis-paper-daily-nas-forward"
        Profile = "kis-paper-daily-nas-forward"
        Service = "kis-paper-daily-nas-forward"
        Runner = "run_kis_paper_daily_nas_forward_schedule.ps1"
        ImageServices = @(
            "kis-paper-daily-nas-forward-preflight",
            "kis-paper-daily-nas-forward",
            "kis-paper-daily-nas-forward-observation"
        )
        At = "06:40"
        RecoverMissedRun = $true
        ExecutionLimitMinutes = 90
    },
    @{
        Name = "thericher-kis-paper-daily-broad-backfill"
        Profile = "kis-paper-daily-broad-backfill"
        Service = "kis-paper-daily-broad-backfill"
        Runner = "run_kis_paper_daily_broad_schedule.ps1"
        ImageServices = @("kis-paper-daily-broad-backfill")
        At = @(
            "07:15", "07:45", "08:15", "08:45", "09:15", "09:45", "10:15", "10:45",
            "11:15", "11:45", "12:15", "12:45", "13:15", "13:45", "14:15", "14:45",
            "15:15", "15:45", "16:15", "16:45", "17:15", "17:45", "18:15", "18:45",
            "19:15", "19:45", "20:15", "20:45"
        )
        RecoverMissedRun = $false
        ExecutionLimitMinutes = 870
    },
    @{
        Name = "thericher-kis-paper-daily-backfill"
        Profile = "kis-paper-daily-backfill"
        Service = "kis-paper-daily-backfill"
        ImageServices = @("kis-paper-daily-backfill")
        At = "07:00"
        RecoverMissedRun = $true
        ExecutionLimitMinutes = 390
    }
)

$selectedSchedules = @($schedules)
if ($ScheduleName.Count -gt 0) {
    $requestedNames = @($ScheduleName | Select-Object -Unique)
    $knownNames = @($schedules | ForEach-Object { [string]$_.Name })
    $unknownNames = @($requestedNames | Where-Object { $_ -notin $knownNames })
    if ($unknownNames.Count -gt 0) {
        throw "Unknown local Docker schedule name(s): $($unknownNames -join ', ')"
    }
    $selectedSchedules = @(
        $schedules | Where-Object { $_.Name -in $requestedNames }
    )
}

if ($RequireExisting) {
    $missingNames = @(
        $selectedSchedules |
            Where-Object {
                $null -eq (Get-ScheduledTask -TaskName $_.Name -ErrorAction SilentlyContinue)
            } |
            ForEach-Object { [string]$_.Name }
    )
    if ($missingNames.Count -gt 0) {
        throw "Required existing scheduled task is missing: $($missingNames -join ', ')"
    }
}

if ($selectedSchedules.Name -contains "thericher-kis-paper-daily-nas-forward") {
    Assert-KoreaStandardTime
}

Write-Host "Installing local Docker schedules for: $($selectedSchedules.Name -join ', ')"

if ($SkipImageBuild) {
    Assert-LocalDockerScheduleImages -ProjectRoot $resolvedProjectRoot -Schedules $selectedSchedules
    Write-Host "Using verified existing schedule images."
} elseif ($PSCmdlet.ShouldProcess($resolvedProjectRoot, "build scheduled Docker service images")) {
    Build-LocalDockerScheduleImages -ProjectRoot $resolvedProjectRoot -Schedules $selectedSchedules
}

foreach ($schedule in $selectedSchedules) {
    if ($schedule.ContainsKey("Runner")) {
        $runnerPath = Join-Path $resolvedProjectRoot "scripts\$($schedule.Runner)"
        if (-not (Test-Path -LiteralPath $runnerPath -PathType Leaf)) {
            throw "Scheduled task runner is missing: $runnerPath"
        }
        $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$runnerPath`" -ProjectRoot `"$resolvedProjectRoot`""
        $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments
    } else {
        $arguments = "compose --project-directory `"$resolvedProjectRoot`" --profile $($schedule.Profile) run --rm --no-deps --pull never $($schedule.Service)"
        $action = New-ScheduledTaskAction -Execute "docker.exe" -Argument $arguments
    }
    $times = @($schedule.At)
    $triggers = @(
        $times | ForEach-Object {
            New-ScheduledTaskTrigger -Weekly -DaysOfWeek Tuesday,Wednesday,Thursday,Friday,Saturday -At $_
        }
    )
    $description = New-LocalDockerTaskDescription -Profile $schedule.Profile
    $settings = New-LocalDockerTaskSettings `
        -ExecutionLimitMinutes $schedule.ExecutionLimitMinutes `
        -RecoverMissedRun $schedule.RecoverMissedRun

    if ($PSCmdlet.ShouldProcess($schedule.Name, "create or update local Docker scheduled task")) {
        Register-ScheduledTask `
            -TaskName $schedule.Name `
            -Action $action `
            -Trigger $triggers `
            -Principal $principal `
            -Settings $settings `
            -Description $description `
            -Force | Out-Null
        Write-Host "Installed $($schedule.Name) at $($times -join ', ') KST."
    } else {
        Write-Host "WhatIf: would install $($schedule.Name) at $($times -join ', ') KST."
    }
}
