[CmdletBinding()]
param(
    [string]$ProjectRoot = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = Join-Path $PSScriptRoot ".."
}

$CacheCurrentExitCode = 0
$CollectionRequiredExitCode = 10
$RecoveryExitCode = 20
$ConflictingDataTasks = @(
    "thericher-kis-paper-daily-nas-forward",
    "thericher-kis-paper-daily-broad-backfill",
    "thericher-kis-paper-daily-backfill"
)

function Test-KoreaStandardTime {
    $localTimeZone = [System.TimeZoneInfo]::Local
    return (
        $localTimeZone.Id -eq "Korea Standard Time" `
            -and $localTimeZone.BaseUtcOffset -eq [TimeSpan]::FromHours(9)
    )
}

function Test-SharedDataDispatcherIdle {
    foreach ($taskName in $ConflictingDataTasks) {
        $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if ($null -ne $task -and $task.State -eq "Running") {
            return $false
        }
    }
    return $true
}

function Invoke-PairForwardProfileService {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [Parameter(Mandatory = $true)]
        [string]$Service,
        [string[]]$CommandOverride = @()
    )

    $priorErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $arguments = @(
            "compose",
            "--project-directory",
            $ProjectRoot,
            "--profile",
            "kis-paper-daily-pair-forward",
            "run",
            "--rm",
            "--no-deps",
            "--pull",
            "never"
        )
        if ($CommandOverride.Count -gt 0) {
            $arguments += @("--entrypoint", "python", $Service)
            $arguments += $CommandOverride
        } else {
            $arguments += $Service
        }
        $output = @(& docker.exe @arguments 2>&1)
        $exitCode = [int]$LASTEXITCODE
    } finally {
        $ErrorActionPreference = $priorErrorActionPreference
    }
    return [pscustomobject]@{
        ExitCode = $exitCode
        Output = $output
    }
}

function Invoke-PairForwardGuardReceipt {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [Parameter(Mandatory = $true)]
        [ValidateSet("host_timezone_not_kst", "shared_dispatcher_busy")]
        [string]$Reason
    )

    $commandOverride = @(
        "scripts/collect_kis_paper_daily_pair_forward.py",
        "--preflight",
        "--cache-root",
        "/app/market_data",
        "--artifact-root",
        "/app/model_artifacts",
        "--repository-root",
        "/app",
        "--schedule-guard-failed",
        $Reason
    )
    return Invoke-PairForwardProfileService `
        -ProjectRoot $ProjectRoot `
        -Service "kis-paper-daily-pair-forward-preflight" `
        -CommandOverride $commandOverride
}

function Invoke-PairForwardSchedule {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    if (-not (Get-Command docker.exe -ErrorAction SilentlyContinue)) {
        throw "docker.exe is required to run the QQQ/SPY D1 forward schedule."
    }
    $resolvedProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
    $composePath = Join-Path $resolvedProjectRoot "docker-compose.yml"
    if (-not (Test-Path -LiteralPath $composePath -PathType Leaf)) {
        throw "Project root must contain docker-compose.yml: $resolvedProjectRoot"
    }
    if (-not (Test-KoreaStandardTime)) {
        $receipt = Invoke-PairForwardGuardReceipt `
            -ProjectRoot $resolvedProjectRoot `
            -Reason "host_timezone_not_kst"
        return $(if ([int]$receipt.ExitCode -eq 0) { $RecoveryExitCode } else { [int]$receipt.ExitCode })
    }
    if (-not (Test-SharedDataDispatcherIdle)) {
        $receipt = Invoke-PairForwardGuardReceipt `
            -ProjectRoot $resolvedProjectRoot `
            -Reason "shared_dispatcher_busy"
        return $(if ([int]$receipt.ExitCode -eq 0) { $RecoveryExitCode } else { [int]$receipt.ExitCode })
    }

    $preflight = Invoke-PairForwardProfileService `
        -ProjectRoot $resolvedProjectRoot `
        -Service "kis-paper-daily-pair-forward-preflight"
    $preflightExitCode = [int]$preflight.ExitCode
    if ($preflightExitCode -eq $CacheCurrentExitCode) {
        return 0
    }
    if ($preflightExitCode -ne $CollectionRequiredExitCode) {
        return $preflightExitCode
    }
    $collection = Invoke-PairForwardProfileService `
        -ProjectRoot $resolvedProjectRoot `
        -Service "kis-paper-daily-pair-forward"
    return [int]$collection.ExitCode
}

if ($MyInvocation.InvocationName -ne ".") {
    exit (Invoke-PairForwardSchedule -ProjectRoot $ProjectRoot)
}
