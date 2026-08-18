[CmdletBinding()]
param(
    [string]$ProjectRoot = (Join-Path $PSScriptRoot "..")
)

$ErrorActionPreference = "Stop"
$taskName = "thericher-kis-paper-intraday-head"
$resolvedProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
$info = Get-ScheduledTaskInfo -TaskName $taskName -ErrorAction Stop

$operationalLogState = "unavailable"
if (Get-Command wevtutil.exe -ErrorAction SilentlyContinue) {
    $logDefinition = @(& wevtutil.exe gl Microsoft-Windows-TaskScheduler/Operational 2>$null)
    if ($logDefinition -match '^enabled:\s+true$') {
        $operationalLogState = "enabled"
    } elseif ($logDefinition -match '^enabled:\s+false$') {
        $operationalLogState = "disabled"
    }
}

$arguments = @(
    (Join-Path $resolvedProjectRoot "scripts\project_kis_paper_intraday_invocation_reattachment.py"),
    "--task-name",
    $taskName,
    "--task-state",
    [string]$task.State,
    "--task-enabled",
    ([bool]$task.Settings.Enabled).ToString().ToLowerInvariant(),
    "--task-action-count",
    [string]@($task.Actions).Count,
    "--last-task-result",
    [string][int]$info.LastTaskResult,
    "--missed-run-count",
    [string][int]$info.NumberOfMissedRuns,
    "--operational-log-state",
    $operationalLogState
)
foreach ($trigger in @($task.Triggers)) {
    $boundary = [string]$trigger.StartBoundary
    if (-not [string]::IsNullOrWhiteSpace($boundary)) {
        $arguments += @("--trigger-start-boundary", $boundary)
    }
}
if ($info.LastRunTime -and $info.LastRunTime.Year -gt 2000) {
    $arguments += @("--last-run-at", $info.LastRunTime.ToUniversalTime().ToString("o"))
}
if ($info.NextRunTime -and $info.NextRunTime.Year -gt 2000) {
    $arguments += @("--next-run-at", $info.NextRunTime.ToUniversalTime().ToString("o"))
}

Push-Location $resolvedProjectRoot
try {
    & uv run python @arguments
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
