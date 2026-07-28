[CmdletBinding()]
param(
    [string]$ProjectRoot = (Join-Path $PSScriptRoot "..")
)

$ErrorActionPreference = "Stop"
$CacheCurrentExitCode = 0
$CollectionRequiredExitCode = 10
$TimingRecoveryExitCode = 20

function Test-KoreaStandardTime {
    $localTimeZone = [System.TimeZoneInfo]::Local
    return (
        $localTimeZone.Id -eq "Korea Standard Time" `
            -and $localTimeZone.BaseUtcOffset -eq [TimeSpan]::FromHours(9)
    )
}

function Invoke-NasForwardProfileService {
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
            "kis-paper-daily-nas-forward",
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

function Invoke-NasForwardTimingGuardReceipt {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    $commandOverride = @(
        "scripts/collect_kis_paper_daily_nas_forward.py",
        "--preflight",
        "--cache-root",
        "/app/market_data",
        "--artifact-root",
        "/app/model_artifacts",
        "--repository-root",
        "/app",
        "--schedule-guard-failed",
        "host_timezone_not_kst"
    )
    return Invoke-NasForwardProfileService `
        -ProjectRoot $ProjectRoot `
        -Service "kis-paper-daily-nas-forward-preflight" `
        -CommandOverride $commandOverride
}

function New-NasForwardObservationRunLabel {
    $stamp = [DateTime]::UtcNow.ToString(
        "yyyyMMddTHHmmssfffZ",
        [System.Globalization.CultureInfo]::InvariantCulture
    )
    $nonce = [Guid]::NewGuid().ToString("N")
    return "nas-forward-observation-$stamp-$nonce"
}

function Invoke-NasForwardObservation {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    $runLabel = New-NasForwardObservationRunLabel
    $commandOverride = @(
        "scripts/run_kis_nas_d1_volatility_trend_prospective_observation.py",
        "--run-label",
        $runLabel,
        "--market-data-root",
        "/app/market_data",
        "--forward-cache-root",
        "/app/market_data/us_equities/kis_paper_private/daily-nas-forward/v1",
        "--artifact-root",
        "/app/model_artifacts",
        "--review-status",
        "review_unavailable"
    )
    return Invoke-NasForwardProfileService `
        -ProjectRoot $ProjectRoot `
        -Service "kis-paper-daily-nas-forward-observation" `
        -CommandOverride $commandOverride
}

function Invoke-NasForwardSchedule {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    if (-not (Get-Command docker.exe -ErrorAction SilentlyContinue)) {
        throw "docker.exe is required to run the NAS D1 forward schedule."
    }

    $resolvedProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
    $composePath = Join-Path $resolvedProjectRoot "docker-compose.yml"
    if (-not (Test-Path -LiteralPath $composePath -PathType Leaf)) {
        throw "Project root must contain docker-compose.yml: $resolvedProjectRoot"
    }

    if (-not (Test-KoreaStandardTime)) {
        $timingGuard = Invoke-NasForwardTimingGuardReceipt -ProjectRoot $resolvedProjectRoot
        $timingGuardExitCode = [int]$timingGuard.ExitCode
        if ($timingGuardExitCode -ne 0) {
            return $timingGuardExitCode
        }
        return $TimingRecoveryExitCode
    }

    $preflight = Invoke-NasForwardProfileService `
        -ProjectRoot $resolvedProjectRoot `
        -Service "kis-paper-daily-nas-forward-preflight"
    $preflightExitCode = [int]$preflight.ExitCode

    $runObservation = $false
    if ($preflightExitCode -eq $CacheCurrentExitCode) {
        $runObservation = $true
    } elseif ($preflightExitCode -ne $CollectionRequiredExitCode) {
        return $preflightExitCode
    } else {
        $collection = Invoke-NasForwardProfileService `
            -ProjectRoot $resolvedProjectRoot `
            -Service "kis-paper-daily-nas-forward"
        $collectionExitCode = [int]$collection.ExitCode
        if ($collectionExitCode -ne 0) {
            return $collectionExitCode
        }
        $runObservation = $true
    }

    if ($runObservation) {
        $observation = Invoke-NasForwardObservation -ProjectRoot $resolvedProjectRoot
        return [int]$observation.ExitCode
    }

    return 0
}

if ($MyInvocation.InvocationName -ne ".") {
    exit (Invoke-NasForwardSchedule -ProjectRoot $ProjectRoot)
}
