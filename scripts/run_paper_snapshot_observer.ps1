[CmdletBinding()]
param(
    [string]$ProjectRoot = (Join-Path $PSScriptRoot "..")
)

$ErrorActionPreference = "Stop"
$RefreshCadenceMinutes = 4
$SnapshotTtlMinutes = 5
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
        return "session_unavailable"
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
        return "session_unavailable"
    }

    $expectedProperties = @("kind", "observed_at", "status") | Sort-Object
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
                -or [string]$payload.kind -ne "kis_paper_snapshot_observer_session" `
                -or [string]$payload.status -notin @(
                    "eligible",
                    "outside_regular_session",
                    "session_unavailable"
                ) `
                -or [string]$payload.observed_at -notmatch "^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$"
        ) {
            continue
        }
        $validPayloads += $payload
    }
    if ($validPayloads.Count -ne 1) {
        return "session_unavailable"
    }
    return [string]$validPayloads[0].status
}

function Get-SafeBridgeOutcome {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    $priorErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = @(
            & docker.exe compose --project-directory $ProjectRoot --profile kis-readonly `
                run --rm --no-deps --pull never kis-readonly 2>&1
        )
        $exitCode = [int]$LASTEXITCODE
    } finally {
        $ErrorActionPreference = $priorErrorActionPreference
    }

    $expectedProperties = @(
        "account_snapshot_complete",
        "evidence_path",
        "observed_at",
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
                -or [string]$payload.status -notin @("complete", "unavailable") `
                -or [string]$payload.scope -ne "read_only" `
                -or [string]$payload.observed_at -notmatch "^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$" `
                -or [string]$payload.reason_code -notmatch "^(|[a-z0-9_]{1,64})$" `
                -or [string]$payload.evidence_path -notmatch "^/app/model_artifacts/"
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
        return [pscustomobject]@{ Status = "observer_unavailable"; ExitCode = $exitCode }
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
        if ($sessionStatus -ne "eligible") {
            Write-ObserverOutcome -Status $sessionStatus -ObservedAt $observedAt
            $exitCode = 0
        } else {
            $bridge = Get-SafeBridgeOutcome -ProjectRoot $resolvedProjectRoot
            if ($bridge.Status -eq "complete" -and $bridge.ExitCode -eq 0) {
                Write-ObserverOutcome -Status "complete" -ObservedAt $observedAt
                $exitCode = 0
            } elseif ($bridge.Status -eq "unavailable") {
                Write-ObserverOutcome `
                    -Status "unavailable" `
                    -ObservedAt $observedAt `
                    -ReasonCode $bridge.ReasonCode
                $exitCode = 2
            } else {
                Write-ObserverOutcome -Status "observer_unavailable" -ObservedAt $observedAt
                $exitCode = 3
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
