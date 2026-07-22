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
        At = "23:35"
    },
    @{
        Name = "thericher-kis-paper-intraday-head"
        Profile = "kis-paper-intraday-head"
        Service = "kis-paper-intraday-head"
        At = "02:35"
    }
)

Write-Host "Installing local Docker schedules for: $resolvedProjectRoot"

foreach ($schedule in $schedules) {
    $arguments = "compose --project-directory `"$resolvedProjectRoot`" --profile $($schedule.Profile) run --rm --no-deps $($schedule.Service)"
    $action = New-ScheduledTaskAction -Execute "docker.exe" -Argument $arguments
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Tuesday,Wednesday,Thursday,Friday,Saturday -At $schedule.At
    $description = New-LocalDockerTaskDescription -Profile $schedule.Profile

    if ($PSCmdlet.ShouldProcess($schedule.Name, "create or update local Docker scheduled task")) {
        Register-ScheduledTask `
            -TaskName $schedule.Name `
            -Action $action `
            -Trigger $trigger `
            -Principal $principal `
            -Description $description `
            -Force | Out-Null
        Write-Host "Installed $($schedule.Name) at $($schedule.At) KST."
    } else {
        Write-Host "WhatIf: would install $($schedule.Name) at $($schedule.At) KST."
    }
}
