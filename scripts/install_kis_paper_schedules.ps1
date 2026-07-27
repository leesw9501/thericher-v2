[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "Medium")]
param(
    [string]$ProjectRoot = (Join-Path $PSScriptRoot "..")
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
        Name = "thericher-kis-paper-daily-backfill"
        Profile = "kis-paper-daily-backfill"
        Service = "kis-paper-daily-backfill"
        ImageServices = @("kis-paper-daily-backfill")
        At = "07:00"
        RecoverMissedRun = $true
        ExecutionLimitMinutes = 390
    }
)

Write-Host "Installing local Docker schedules for: $resolvedProjectRoot"

if ($PSCmdlet.ShouldProcess($resolvedProjectRoot, "build scheduled Docker service images")) {
    Build-LocalDockerScheduleImages -ProjectRoot $resolvedProjectRoot -Schedules $schedules
}

foreach ($schedule in $schedules) {
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
