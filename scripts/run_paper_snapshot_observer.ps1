[CmdletBinding()]
param(
    [string]$ProjectRoot = (Join-Path $PSScriptRoot "..")
)

$ErrorActionPreference = "Stop"
$RefreshCadenceMinutes = 4
$SnapshotTtlMinutes = 5
$MinimumSessionRemainingMinutes = 4
$ObserverMutexName = "Global\TheRicherPaperSnapshotObserver"

function Get-ObserverUtcNow {
    return (Get-Date).ToUniversalTime()
}

function Write-ObserverOutcome {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet(
            "complete",
            "unavailable",
            "outside_regular_session",
            "session_unavailable",
            "session_closing",
            "observer_busy",
            "observer_unavailable"
        )]
        [string]$Status,
        [Parameter(Mandatory = $true)]
        [datetime]$ObservedAt,
        [string]$ReasonCode = ""
    )

    $payload = [ordered]@{
        kind = "kis_paper_snapshot_observer"
        status = $Status
        observed_at = $ObservedAt.ToUniversalTime().ToString(
            "o",
            [System.Globalization.CultureInfo]::InvariantCulture
        )
        scope = "read_only"
        submit_capability = $false
    }
    if ($ReasonCode) {
        $payload.reason_code = $ReasonCode
    }
    $payload | ConvertTo-Json -Compress
}

function Get-SafeSessionStatus {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [Parameter(Mandatory = $true)]
        [datetime]$ObservedAt
    )

    $inspectorPath = Join-Path $ProjectRoot "scripts\inspect_kis_paper_account_snapshot_observer_session.py"
    if (
        -not (Get-Command uv.exe -ErrorAction SilentlyContinue) `
            -or -not (Test-Path -LiteralPath $inspectorPath -PathType Leaf)
    ) {
        return [pscustomobject]@{ Status = "session_unavailable"; EligibleUntil = $null }
    }

    $priorErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = @(
            & uv.exe run --no-sync --project $ProjectRoot python $inspectorPath `
                --observed-at $ObservedAt.ToString("o", [System.Globalization.CultureInfo]::InvariantCulture) 2>&1
        )
        $exitCode = [int]$LASTEXITCODE
    } finally {
        $ErrorActionPreference = $priorErrorActionPreference
    }
    if ($exitCode -ne 0) {
        return [pscustomobject]@{ Status = "session_unavailable"; EligibleUntil = $null }
    }

    $expectedProperties = @("eligible_until", "kind", "observed_at", "status") | Sort-Object
    $validPayloads = @()
    foreach ($line in $output) {
        $text = ([string]$line).Trim()
        if (-not ($text.StartsWith("{") -and $text.EndsWith("}"))) {
            continue
        }
        try {
            $payload = $text | ConvertFrom-Json -ErrorAction Stop
        } catch {
            continue
        }
        $propertyNames = @($payload.PSObject.Properties.Name | Sort-Object)
        $status = [string]$payload.status
        $hasEligibleUntil = $null -ne $payload.eligible_until `
            -and [string]$payload.eligible_until -match "^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$"
        if (
            $propertyNames.Count -ne $expectedProperties.Count `
                -or ($propertyNames -join "|") -ne ($expectedProperties -join "|") `
                -or [string]$payload.kind -ne "kis_paper_snapshot_observer_session" `
                -or $status -notin @(
                    "eligible",
                    "outside_regular_session",
                    "session_unavailable"
                ) `
                -or [string]$payload.observed_at -notmatch "^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$" `
                -or ($status -eq "eligible" -and -not $hasEligibleUntil) `
                -or ($status -ne "eligible" -and $null -ne $payload.eligible_until)
        ) {
            continue
        }
        $validPayloads += $payload
    }
    if ($validPayloads.Count -ne 1) {
        return [pscustomobject]@{ Status = "session_unavailable"; EligibleUntil = $null }
    }
    return [pscustomobject]@{
        Status = [string]$validPayloads[0].status
        EligibleUntil = $validPayloads[0].eligible_until
    }
}

function Get-SafeBridgeOutcome {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [Parameter(Mandatory = $true)]
        [datetime]$EligibleUntil,
        [Parameter(Mandatory = $true)]
        [string]$ObserverInvocationId
    )

    $bridgeLaunchAt = Get-ObserverUtcNow
    if (($EligibleUntil - $bridgeLaunchAt) -le [TimeSpan]::FromMinutes($MinimumSessionRemainingMinutes)) {
        return [pscustomobject]@{
            Status = "session_closing"
            ExitCode = 0
            ObservedAt = $bridgeLaunchAt
            ReasonCode = ""
        }
    }

    $priorErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = @(
            & docker.exe compose --project-directory $ProjectRoot --profile kis-readonly `
                run --rm --no-deps --pull never `
                -e "THERICHER_KIS_PAPER_SNAPSHOT_OBSERVER_INVOCATION_ID=$ObserverInvocationId" `
                kis-readonly 2>&1
        )
        $exitCode = [int]$LASTEXITCODE
    } finally {
        $ErrorActionPreference = $priorErrorActionPreference
    }

    $expectedProperties = @(
        "account_snapshot_complete",
        "evidence_path",
        "observed_at",
        "observer_evidence_path",
        "observer_invocation_id",
        "reason_code",
        "scope",
        "status"
    ) | Sort-Object
    $validPayloads = @()
    foreach ($line in $output) {
        $text = ([string]$line).Trim()
        if (-not ($text.StartsWith("{") -and $text.EndsWith("}"))) {
            continue
        }
        try {
            $payload = $text | ConvertFrom-Json -ErrorAction Stop
        } catch {
            continue
        }
        $propertyNames = @($payload.PSObject.Properties.Name | Sort-Object)
        if (
            $propertyNames.Count -ne $expectedProperties.Count `
                -or ($propertyNames -join "|") -ne ($expectedProperties -join "|") `
                -or [string]$payload.status -notin @("complete", "unavailable", "busy") `
                -or [string]$payload.scope -ne "read_only" `
                -or [string]$payload.observed_at -notmatch "^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$" `
                -or [string]$payload.reason_code -notmatch "^(|[a-z0-9_]{1,64})$" `
                -or (
                    [string]$payload.status -eq "busy" `
                        -and (
                            $payload.account_snapshot_complete -ne $false `
                                -or [string]$payload.reason_code -ne "refresh_busy" `
                                -or $null -ne $payload.evidence_path `
                                -or $null -ne $payload.observer_evidence_path `
                                -or $null -ne $payload.observer_invocation_id
                        )
                ) `
                -or (
                    [string]$payload.status -ne "busy" `
                        -and (
                            [string]$payload.evidence_path -notmatch "^/app/model_artifacts/execution/kis-paper-console-bridge/" `
                                -or [string]$payload.observer_evidence_path -notmatch "^/app/model_artifacts/execution/kis-paper-snapshot-observer/" `
                                -or [string]$payload.observer_invocation_id -ne $ObserverInvocationId
                        )
                )
        ) {
            continue
        }
        if (
            ([string]$payload.status -eq "complete" -and $payload.account_snapshot_complete -ne $true) `
                -or ([string]$payload.status -eq "unavailable" -and $payload.account_snapshot_complete -ne $false)
        ) {
            continue
        }
        $validPayloads += $payload
    }
    if ($validPayloads.Count -ne 1) {
        return [pscustomobject]@{
            Status = "observer_unavailable"
            ExitCode = $exitCode
            ObservedAt = $null
            ReasonCode = ""
        }
    }
    return [pscustomobject]@{
        Status = [string]$validPayloads[0].status
        ExitCode = $exitCode
        ObservedAt = [string]$validPayloads[0].observed_at
        ReasonCode = [string]$validPayloads[0].reason_code
    }
}

$mutex = $null
$hasMutex = $false
$exitCode = 3
$observedAt = (Get-Date).ToUniversalTime()
try {
    $observedAt = Get-ObserverUtcNow
    if ($RefreshCadenceMinutes -ge $SnapshotTtlMinutes) {
        throw "Observer cadence must remain inside the snapshot TTL."
    }
    if (-not (Get-Command docker.exe -ErrorAction SilentlyContinue)) {
        throw "docker.exe is required to run the paper snapshot observer."
    }
    $resolvedProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
    if (-not (Test-Path -LiteralPath (Join-Path $resolvedProjectRoot "docker-compose.yml") -PathType Leaf)) {
        throw "Project root must contain docker-compose.yml."
    }

    $mutex = New-Object System.Threading.Mutex($false, $ObserverMutexName)
    try {
        $hasMutex = $mutex.WaitOne(0)
    } catch [System.Threading.AbandonedMutexException] {
        $hasMutex = $true
    }
    if (-not $hasMutex) {
        Write-ObserverOutcome -Status "observer_busy" -ObservedAt $observedAt
        $exitCode = 0
    } else {
        $sessionStatus = Get-SafeSessionStatus `
            -ProjectRoot $resolvedProjectRoot `
            -ObservedAt $observedAt
        if ($sessionStatus.Status -ne "eligible") {
            Write-ObserverOutcome -Status $sessionStatus.Status -ObservedAt $observedAt
            $exitCode = 0
        } else {
            $eligibleUntil = [datetimeoffset]::Parse(
                [string]$sessionStatus.EligibleUntil,
                [System.Globalization.CultureInfo]::InvariantCulture,
                [System.Globalization.DateTimeStyles]::AdjustToUniversal
            ).UtcDateTime
            if (($eligibleUntil - $observedAt) -le [TimeSpan]::FromMinutes($MinimumSessionRemainingMinutes)) {
                Write-ObserverOutcome -Status "session_closing" -ObservedAt $observedAt
                $exitCode = 0
            } else {
                $observerInvocationId = [guid]::NewGuid().ToString("D")
                $bridge = Get-SafeBridgeOutcome `
                    -ProjectRoot $resolvedProjectRoot `
                    -EligibleUntil $eligibleUntil `
                    -ObserverInvocationId $observerInvocationId
                if ($bridge.Status -eq "session_closing") {
                    Write-ObserverOutcome -Status "session_closing" -ObservedAt $bridge.ObservedAt
                    $exitCode = 0
                } elseif ($bridge.Status -eq "complete" -and $bridge.ExitCode -eq 0) {
                    $bridgeObservedAt = [datetimeoffset]::Parse(
                        $bridge.ObservedAt,
                        [System.Globalization.CultureInfo]::InvariantCulture,
                        [System.Globalization.DateTimeStyles]::AdjustToUniversal
                    ).UtcDateTime
                    Write-ObserverOutcome -Status "complete" -ObservedAt $bridgeObservedAt
                    $exitCode = 0
                } elseif ($bridge.Status -eq "busy" -and $bridge.ExitCode -eq 0) {
                    $bridgeObservedAt = [datetimeoffset]::Parse(
                        $bridge.ObservedAt,
                        [System.Globalization.CultureInfo]::InvariantCulture,
                        [System.Globalization.DateTimeStyles]::AdjustToUniversal
                    ).UtcDateTime
                    Write-ObserverOutcome -Status "observer_busy" -ObservedAt $bridgeObservedAt
                    $exitCode = 0
                } elseif ($bridge.Status -eq "unavailable") {
                    $bridgeObservedAt = [datetimeoffset]::Parse(
                        $bridge.ObservedAt,
                        [System.Globalization.CultureInfo]::InvariantCulture,
                        [System.Globalization.DateTimeStyles]::AdjustToUniversal
                    ).UtcDateTime
                    Write-ObserverOutcome `
                        -Status "unavailable" `
                        -ObservedAt $bridgeObservedAt `
                        -ReasonCode $bridge.ReasonCode
                    $exitCode = 2
                } else {
                    Write-ObserverOutcome -Status "observer_unavailable" -ObservedAt $observedAt
                    $exitCode = 3
                }
            }
        }
    }
} catch {
    Write-ObserverOutcome -Status "observer_unavailable" -ObservedAt $observedAt
    $exitCode = 3
} finally {
    if ($hasMutex -and $null -ne $mutex) {
        $mutex.ReleaseMutex()
    }
    if ($null -ne $mutex) {
        $mutex.Dispose()
    }
}

exit $exitCode
