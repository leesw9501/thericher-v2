[CmdletBinding()]
param(
    [string]$ProjectRoot = (Join-Path $PSScriptRoot "..")
)

$ErrorActionPreference = "Stop"

function Invoke-HeadProfileService {
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
        if ($CommandOverride.Count -eq 0) {
            $output = @(
                & docker.exe compose --project-directory $ProjectRoot --profile kis-paper-intraday-head `
                    run --rm --no-deps --pull never $Service 2>&1
            )
        } else {
            $output = @(
                & docker.exe compose --project-directory $ProjectRoot --profile kis-paper-intraday-head `
                    run --rm --no-deps --pull never $Service @CommandOverride 2>&1
            )
        }
        $exitCode = [int]$LASTEXITCODE
    } finally {
        $ErrorActionPreference = $priorErrorActionPreference
    }
    return [pscustomobject]@{
        ExitCode = $exitCode
        Output = $output
    }
}

function Get-ProfilePayload {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Output,
        [Parameter(Mandatory = $true)]
        [string]$Kind
    )

    $jsonLines = @(
        $Output |
            ForEach-Object { [string]$_ } |
            Where-Object { $_.Trim().StartsWith("{") -and $_.Trim().EndsWith("}") }
    )
    for ($index = $jsonLines.Count - 1; $index -ge 0; $index--) {
        $line = $jsonLines[$index]
        try {
            $payload = $line | ConvertFrom-Json -ErrorAction Stop
        } catch {
            continue
        }
        if ($payload.kind -eq $Kind) {
            return $payload
        }
    }
    return $null
}

function Get-UniqueSafeProfileSessionPayload {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Output,
        [Parameter(Mandatory = $true)]
        [string]$Kind,
        [Parameter(Mandatory = $true)]
        [string[]]$AllowedStatuses
    )

    $jsonLines = @(
        $Output |
            ForEach-Object { [string]$_ } |
            Where-Object { $_.Trim().StartsWith("{") -and $_.Trim().EndsWith("}") }
    )
    $safePayloads = @()
    for ($index = $jsonLines.Count - 1; $index -ge 0; $index--) {
        try {
            $payload = $jsonLines[$index] | ConvertFrom-Json -ErrorAction Stop
        } catch {
            continue
        }
        if ($payload.kind -ne $Kind -or $payload.status -notin $AllowedStatuses) {
            continue
        }
        $sessionId = [string]$payload.session_id
        if ($sessionId -match '^[A-Za-z0-9._-]{1,160}$') {
            $safePayloads += $payload
        }
    }
    if ($safePayloads.Count -eq 0) {
        return $null
    }
    $sessionIds = @(
        $safePayloads |
            ForEach-Object { [string]$_.session_id } |
            Sort-Object -Unique
    )
    $statuses = @(
        $safePayloads |
            ForEach-Object { [string]$_.status } |
            Sort-Object -Unique
    )
    if ($sessionIds.Count -ne 1 -or $statuses.Count -ne 1) {
        return $null
    }
    return $safePayloads[0]
}

function Get-ProfileStatus {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Output,
        [Parameter(Mandatory = $true)]
        [string]$Kind,
        [Parameter(Mandatory = $true)]
        [string[]]$AllowedStatuses
    )

    $payload = Get-ProfilePayload -Output $Output -Kind $Kind
    if ($null -ne $payload -and $payload.status -in $AllowedStatuses) {
        return [string]$payload.status
    }
    return "unavailable"
}

function Get-SafeProfileSessionId {
    param(
        [object]$Payload
    )

    if ($null -eq $Payload) {
        return $null
    }
    $candidate = [string]$Payload.session_id
    if ($candidate -match '^[A-Za-z0-9._-]{1,160}$') {
        return $candidate
    }
    return $null
}

function Get-UniqueSafeSessionCaptureTerminalBinding {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Output,
        [Parameter(Mandatory = $true)]
        [string]$ExpectedScheduleRunId
    )

    $jsonLines = @(
        $Output |
            ForEach-Object { [string]$_ } |
            Where-Object { $_.Trim().StartsWith("{") -and $_.Trim().EndsWith("}") }
    )
    $bindings = @()
    $expectedProperties = @(
        "schedule_run_id",
        "observed_at",
        "receipt_sha256",
        "current_session_cumulative_coverage_digest",
        "current_session_cumulative_coverage_category"
    ) | Sort-Object
    foreach ($line in $jsonLines) {
        try {
            $payload = $line | ConvertFrom-Json -ErrorAction Stop
        } catch {
            continue
        }
        if ($payload.kind -ne "kis_paper_intraday_session_capture") {
            continue
        }
        $binding = $payload.terminal_receipt_binding
        if ($null -eq $binding) {
            continue
        }
        $propertyNames = @($binding.PSObject.Properties.Name | Sort-Object)
        if (
            $propertyNames.Count -ne $expectedProperties.Count `
                -or ($propertyNames -join "|") -ne ($expectedProperties -join "|")
        ) {
            continue
        }
        $scheduleRunId = [string]$binding.schedule_run_id
        $observedAtValue = $binding.observed_at
        if ($observedAtValue -is [datetime]) {
            if ($observedAtValue.Kind -eq [System.DateTimeKind]::Unspecified) {
                continue
            }
            $observedAt = $observedAtValue.ToUniversalTime().ToString(
                "yyyy-MM-ddTHH:mm:ss.ffffffZ",
                [System.Globalization.CultureInfo]::InvariantCulture
            )
        } elseif ($observedAtValue -is [datetimeoffset]) {
            $observedAt = $observedAtValue.UtcDateTime.ToString(
                "yyyy-MM-ddTHH:mm:ss.ffffffZ",
                [System.Globalization.CultureInfo]::InvariantCulture
            )
        } else {
            $observedAt = [string]$observedAtValue
        }
        $receiptSha256 = [string]$binding.receipt_sha256
        $coverageDigest = [string]$binding.current_session_cumulative_coverage_digest
        $coverageCategory = [string]$binding.current_session_cumulative_coverage_category
        if (
            $scheduleRunId -ne $ExpectedScheduleRunId `
                -or $scheduleRunId -notmatch '^[A-Za-z0-9._-]{1,160}$' `
                -or $observedAt -notmatch '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$' `
                -or $receiptSha256 -notmatch '^sha256:[0-9a-f]{64}$' `
                -or $coverageDigest -notmatch '^sha256:[0-9a-f]{64}$' `
                -or $coverageCategory -notin @("complete", "incomplete")
        ) {
            continue
        }
        $bindings += [pscustomobject]@{
            schedule_run_id = $scheduleRunId
            observed_at = $observedAt
            receipt_sha256 = $receiptSha256
            current_session_cumulative_coverage_digest = $coverageDigest
            current_session_cumulative_coverage_category = $coverageCategory
        }
    }
    if ($bindings.Count -eq 0) {
        return $null
    }
    $identities = @(
        $bindings |
            ForEach-Object {
                "$($_.schedule_run_id)|$($_.observed_at)|$($_.receipt_sha256)|$($_.current_session_cumulative_coverage_digest)|$($_.current_session_cumulative_coverage_category)"
            } |
            Sort-Object -Unique
    )
    if ($identities.Count -ne 1) {
        return $null
    }
    return $bindings[0]
}

function New-ScheduleRunId {
    param(
        [Parameter(Mandatory = $true)]
        [datetime]$ObservedAt
    )

    $stamp = $ObservedAt.ToUniversalTime().ToString(
        "yyyyMMddTHHmmssfffffffZ",
        [System.Globalization.CultureInfo]::InvariantCulture
    )
    return "intraday-head-$stamp"
}

function Get-DispatchTerminalExitCode {
    param(
        [Parameter(Mandatory = $true)]
        [int]$CollectionExitCode,
        [Parameter(Mandatory = $true)]
        [int]$ScheduleReceiptExitCode,
        [object]$ScheduleReceiptPayload
    )

    if ($CollectionExitCode -ne 0) {
        return $CollectionExitCode
    }
    if ($ScheduleReceiptExitCode -ne 0 -or $null -eq $ScheduleReceiptPayload) {
        return 21
    }
    $terminal = $ScheduleReceiptPayload.terminal
    if ($null -eq $terminal) {
        return 21
    }
    $terminalStatus = [string]$terminal.status
    if ($terminalStatus -notin @("complete", "recovery")) {
        return 21
    }
    $rawTerminalExitCode = $terminal.scheduler_exit_code
    if ($null -eq $rawTerminalExitCode) {
        return 21
    }
    try {
        $terminalExitCode = [int]$rawTerminalExitCode
    } catch {
        return 21
    }
    if ($terminalExitCode -lt 0) {
        return 21
    }
    if ($terminalStatus -eq "complete" -and $terminalExitCode -ne 0) {
        return 21
    }
    if ($terminalStatus -eq "recovery" -and $terminalExitCode -eq 0) {
        return 21
    }
    return $terminalExitCode
}

if (-not (Get-Command docker.exe -ErrorAction SilentlyContinue)) {
    throw "docker.exe is required to run the intraday head schedule."
}

$resolvedProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$composePath = Join-Path $resolvedProjectRoot "docker-compose.yml"
if (-not (Test-Path -LiteralPath $composePath -PathType Leaf)) {
    throw "Project root must contain docker-compose.yml: $resolvedProjectRoot"
}

$collectionStartedAt = (Get-Date).ToUniversalTime()
$scheduleRunId = New-ScheduleRunId -ObservedAt $collectionStartedAt
$collectionCommand = @(
    "python",
    "scripts/backfill_kis_paper_private_intraday.py",
    "--execute",
    "--mode",
    "session-capture",
    "--skip-legacy-preparation",
    "--pages-per-target",
    "4",
    "--preparation-artifact-root",
    "/app/model_artifacts",
    "--runtime-projection",
    "/app/runtime/state/kis_paper_intraday_freshness.json",
    "--schedule-run-id",
    $scheduleRunId
)
$collection = Invoke-HeadProfileService `
    -ProjectRoot $resolvedProjectRoot `
    -Service "kis-paper-intraday-head" `
    -CommandOverride $collectionCommand
$collectionReturnedAt = (Get-Date).ToUniversalTime()
$collectionExitCode = [int]$collection.ExitCode
$scheduleObservedAt = $collectionReturnedAt
$scheduleObservedAtMarker = $scheduleObservedAt.ToString(
    "o",
    [System.Globalization.CultureInfo]::InvariantCulture
)
$collectionStartedAtMarker = $collectionStartedAt.ToString(
    "o",
    [System.Globalization.CultureInfo]::InvariantCulture
)
$collectionReturnedAtMarker = $collectionReturnedAt.ToString(
    "o",
    [System.Globalization.CultureInfo]::InvariantCulture
)

# The current QQQ route consumes the just-collected local cache before slower,
# independent observations can exhaust its two-minute freshness budget. It owns
# local replay and the existing virtual-Paper boundary; a no-intent result never
# changes collection recovery.
$prospectiveSpyCycleExitCode = 0
$prospectiveSpyCycleStatus = "not_applicable"
$prospectiveSpyCycleId = $null
$prospectiveSpyCanaryRunId = $null
$prospectiveLoopExitCode = 0
$prospectiveLoopStatus = "not_applicable"
$prospectiveSessionExitCode = 0
$prospectiveSessionStatus = "not_applicable"
$prospectiveSessionId = $null
$prospectiveValidationExitCode = 0
$prospectiveValidationStatus = "not_applicable"
$prospectiveValidationSessionId = $null
$prospectiveValidationContract = $null
$expectedProspectiveValidationContract = "runtime-freshness-v4"

$captureCycleExitCode = 0
$captureCycleStatus = "not_applicable"
$observationExitCode = 0
$observationStatus = "not_applicable"
$sessionCaptureBinding = Get-UniqueSafeSessionCaptureTerminalBinding `
    -Output $collection.Output `
    -ExpectedScheduleRunId $scheduleRunId
if ($collectionExitCode -eq 0) {
    $prospectiveLoopStatus = "embedded"
    $prospectiveSession = Invoke-HeadProfileService `
        -ProjectRoot $resolvedProjectRoot `
        -Service "kis-paper-prospective-qqq-session"
    $prospectiveSessionExitCode = [int]$prospectiveSession.ExitCode
    $prospectiveSessionPayload = Get-UniqueSafeProfileSessionPayload `
        -Output $prospectiveSession.Output `
        -Kind "kis_paper_prospective_qqq_session" `
        -AllowedStatuses @("no_intent", "canary_completed")
    $prospectiveSessionId = Get-SafeProfileSessionId -Payload $prospectiveSessionPayload
    if ($null -ne $prospectiveSessionPayload) {
        $prospectiveSessionStatus = [string]$prospectiveSessionPayload.status
    } else {
        $prospectiveSessionStatus = "unavailable"
    }

    # Validation reloads the exact retained cache after the execution session.
    # Its network-disabled service cannot create another Paper side effect.
    if (
        $prospectiveSessionExitCode -eq 0 `
            -and $prospectiveSessionStatus -in @("no_intent", "canary_completed") `
            -and $null -ne $prospectiveSessionId
    ) {
        $prospectiveValidation = Invoke-HeadProfileService `
            -ProjectRoot $resolvedProjectRoot `
            -Service "kis-paper-prospective-qqq-validation" `
            -CommandOverride @(
                "python",
                "-m",
                "thericher_v2.ops.kis_paper_prospective_qqq_validation",
                "--session-id",
                $prospectiveSessionId,
                "--cache-root",
                "/app/market_data/us_equities/kis_paper_private/intraday-head",
                "--artifact-root",
                "/app/model_artifacts",
                "--repository-root",
                "/app"
            )
        $prospectiveValidationExitCode = [int]$prospectiveValidation.ExitCode
        $prospectiveValidationPayload = Get-UniqueSafeProfileSessionPayload `
            -Output $prospectiveValidation.Output `
            -Kind "kis_paper_prospective_qqq_validation" `
            -AllowedStatuses @("validated")
        if (
            $prospectiveValidationExitCode -eq 0 `
                -and $null -ne $prospectiveValidationPayload `
                -and [string]$prospectiveValidationPayload.validation_contract `
                    -eq $expectedProspectiveValidationContract
        ) {
            $prospectiveValidationStatus = "validated"
            $prospectiveValidationSessionId = Get-SafeProfileSessionId `
                -Payload $prospectiveValidationPayload
            $prospectiveValidationContract = $expectedProspectiveValidationContract
        } else {
            $prospectiveValidationStatus = "unavailable"
        }
    }

    # This independent receipt cannot affect the scheduled task terminal status.
    $spyCollectionStatus = "unavailable"
    $spyRowCount = 0
    $spyExactOverlapRows = 0
    $spyCollectionReason = $null
    $collectionPayload = Get-ProfilePayload `
        -Output $collection.Output `
        -Kind "kis_paper_intraday_session_capture"
    if ($null -ne $collectionPayload) {
        $spyTargets = @(
            $collectionPayload.targets |
                Where-Object { $_.target_key -eq "SPY/AMS/1m" }
        )
        if ($spyTargets.Count -eq 1) {
            $spyTarget = $spyTargets[0]
            $spyCollectionStatus = [string]$spyTarget.status
            $spyRowCount = [int]$spyTarget.row_count
            $spyExactOverlapRows = [int]$spyTarget.exact_overlap_rows
            if ($null -ne $spyTarget.reason) {
                $spyCollectionReason = [string]$spyTarget.reason
            }
        }
    }
    $timingProbeCommand = @(
        "python",
        "-m",
        "thericher_v2.ops.kis_paper_prospective_spy_timing_probe",
        "--scheduler-started-at",
        $collectionStartedAtMarker,
        "--collector-returned-at",
        $collectionReturnedAtMarker,
        "--collection-exit-code",
        [string]$collectionExitCode,
        "--spy-collection-status",
        $spyCollectionStatus,
        "--spy-row-count",
        [string]$spyRowCount,
        "--spy-exact-overlap-rows",
        [string]$spyExactOverlapRows,
        "--cache-root",
        "/app/market_data/us_equities/kis_paper_private/intraday-head",
        "--artifact-root",
        "/app/model_artifacts",
        "--repository-root",
        "/app"
    )
    if ($null -ne $spyCollectionReason) {
        $timingProbeCommand += @("--spy-reason", $spyCollectionReason)
    }
    $null = Invoke-HeadProfileService `
        -ProjectRoot $resolvedProjectRoot `
        -Service "kis-paper-prospective-spy-timing-probe" `
        -CommandOverride $timingProbeCommand
    $prospectiveSpyCycle = Invoke-HeadProfileService `
        -ProjectRoot $resolvedProjectRoot `
        -Service "kis-paper-prospective-spy-cycle"
    $prospectiveSpyCycleExitCode = [int]$prospectiveSpyCycle.ExitCode
    $prospectiveSpyCycleStatus = Get-ProfileStatus `
        -Output $prospectiveSpyCycle.Output `
        -Kind "kis_paper_prospective_spy_cycle" `
        -AllowedStatuses @("preview", "no_intent", "canary_completed")
    $prospectiveSpyCyclePayload = Get-ProfilePayload `
        -Output $prospectiveSpyCycle.Output `
        -Kind "kis_paper_prospective_spy_cycle"
    if ($null -ne $prospectiveSpyCyclePayload) {
        $prospectiveSpyCycleId = $prospectiveSpyCyclePayload.cycle_id
        $prospectiveSpyCanaryRunId = $prospectiveSpyCyclePayload.execution.canary_run_id
    }
    $qqqReadinessObserverCommand = @(
        "python",
        "scripts/observe_kis_paper_qqq_intraday_head_readiness.py",
        "--collection-started-at",
        $collectionStartedAtMarker,
        "--collector-returned-at",
        $collectionReturnedAtMarker,
        "--cache-root",
        "/app/market_data",
        "--artifact-root",
        "/app/model_artifacts",
        "--repository-root",
        "/app"
    )
    # This data-only receipt runs after SPY dispatch and cannot affect terminal receipt or task exit.
    $null = Invoke-HeadProfileService `
        -ProjectRoot $resolvedProjectRoot `
        -Service "kis-paper-qqq-intraday-head-readiness" `
        -CommandOverride $qqqReadinessObserverCommand
    $captureCycle = Invoke-HeadProfileService `
        -ProjectRoot $resolvedProjectRoot `
        -Service "profiled-mtf-forward-capture-cycle" `
        -CommandOverride @(
            "python",
            "scripts/run_profiled_mtf_forward_capture_cycle.py",
            "--observed-at",
            $scheduleObservedAtMarker
        )
    $captureCycleExitCode = [int]$captureCycle.ExitCode
    $captureCycleStatus = Get-ProfileStatus `
        -Output $captureCycle.Output `
        -Kind "profiled-mtf-forward-capture-cycle-v1" `
        -AllowedStatuses @(
            "outside_cycle_slot",
            "observed",
            "duplicate",
            "conflict",
            "input_unavailable",
            "outcome_unavailable",
            "input_mutated",
            "appended",
            "busy"
        )
    $pairObservation = Invoke-HeadProfileService `
        -ProjectRoot $resolvedProjectRoot `
        -Service "kis-paper-intraday-pair-observation"
    $observationExitCode = [int]$pairObservation.ExitCode
    $observationStatus = Get-ProfileStatus `
        -Output $pairObservation.Output `
        -Kind "kis_qqq_spy_mtf_prospective_observation" `
        -AllowedStatuses @(
            "pending",
            "unavailable",
            "observed",
            "not_observed",
            "duplicate",
            "conflict",
            "cap_reached",
            "busy"
        )
}
$scheduleReceiptCommand = @(
    "python",
    "-m",
    "thericher_v2.ops.kis_paper_intraday_head_schedule_receipt",
    "--run-id",
    $scheduleRunId,
    "--observed-at",
    $scheduleObservedAtMarker,
    "--collection-exit-code",
    [string]$collectionExitCode,
    "--prospective-spy-cycle-exit-code",
    [string]$prospectiveSpyCycleExitCode,
    "--prospective-spy-cycle-status",
    $prospectiveSpyCycleStatus,
    "--prospective-loop-exit-code",
    [string]$prospectiveLoopExitCode,
    "--prospective-loop-status",
    $prospectiveLoopStatus,
    "--prospective-session-exit-code",
    [string]$prospectiveSessionExitCode,
    "--prospective-session-status",
    $prospectiveSessionStatus,
    "--prospective-validation-exit-code",
    [string]$prospectiveValidationExitCode,
    "--prospective-validation-status",
    $prospectiveValidationStatus,
    "--observation-exit-code",
    [string]$observationExitCode,
    "--observation-status",
    $observationStatus,
    "--capture-cycle-exit-code",
    [string]$captureCycleExitCode,
    "--capture-cycle-status",
    $captureCycleStatus,
    "--require-session-capture-binding",
    "--artifact-root",
    "/app/model_artifacts",
    "--repository-root",
    "/app"
)
if ($null -ne $prospectiveSessionId) {
    $scheduleReceiptCommand += @("--prospective-session-id", [string]$prospectiveSessionId)
}
if ($null -ne $prospectiveValidationSessionId) {
    $scheduleReceiptCommand += @(
        "--prospective-validation-session-id",
        [string]$prospectiveValidationSessionId
    )
}
if ($null -ne $prospectiveValidationContract) {
    $scheduleReceiptCommand += @(
        "--prospective-validation-contract",
        [string]$prospectiveValidationContract
    )
}
if ($null -ne $prospectiveSpyCycleId) {
    $scheduleReceiptCommand += @("--prospective-spy-cycle-id", [string]$prospectiveSpyCycleId)
}
if ($null -ne $prospectiveSpyCanaryRunId) {
    $scheduleReceiptCommand += @("--prospective-spy-canary-run-id", [string]$prospectiveSpyCanaryRunId)
}
if ($null -ne $sessionCaptureBinding) {
    $scheduleReceiptCommand += @(
        "--session-capture-run-id",
        [string]$sessionCaptureBinding.schedule_run_id,
        "--session-capture-observed-at",
        [string]$sessionCaptureBinding.observed_at,
        "--session-capture-receipt-sha256",
        [string]$sessionCaptureBinding.receipt_sha256,
        "--session-capture-coverage-digest",
        [string]$sessionCaptureBinding.current_session_cumulative_coverage_digest,
        "--session-capture-coverage-category",
        [string]$sessionCaptureBinding.current_session_cumulative_coverage_category
    )
}
$scheduleReceipt = Invoke-HeadProfileService `
    -ProjectRoot $resolvedProjectRoot `
    -Service "kis-paper-intraday-head-receipt" `
    -CommandOverride $scheduleReceiptCommand
$scheduleReceiptExitCode = [int]$scheduleReceipt.ExitCode
$scheduleReceiptPayload = Get-ProfilePayload `
    -Output $scheduleReceipt.Output `
    -Kind "kis_paper_intraday_head_schedule_receipt"
$scheduleReceiptStatus = Get-ProfileStatus `
    -Output $scheduleReceipt.Output `
    -Kind "kis_paper_intraday_head_schedule_receipt" `
    -AllowedStatuses @("complete", "recovery")
$terminalExitCode = Get-DispatchTerminalExitCode `
    -CollectionExitCode $collectionExitCode `
    -ScheduleReceiptExitCode $scheduleReceiptExitCode `
    -ScheduleReceiptPayload $scheduleReceiptPayload

[ordered]@{
    kind = "kis_paper_intraday_head_schedule"
    collection_exit_code = $collectionExitCode
    prospective_spy_cycle_exit_code = $prospectiveSpyCycleExitCode
    prospective_spy_cycle_status = $prospectiveSpyCycleStatus
    prospective_loop_exit_code = $prospectiveLoopExitCode
    prospective_loop_status = $prospectiveLoopStatus
    prospective_session_exit_code = $prospectiveSessionExitCode
    prospective_session_status = $prospectiveSessionStatus
    prospective_validation_exit_code = $prospectiveValidationExitCode
    prospective_validation_status = $prospectiveValidationStatus
    prospective_validation_contract = $prospectiveValidationContract
    observation_exit_code = $observationExitCode
    observation_status = $observationStatus
    capture_cycle_exit_code = $captureCycleExitCode
    capture_cycle_status = $captureCycleStatus
    schedule_receipt_exit_code = $scheduleReceiptExitCode
    schedule_receipt_status = $scheduleReceiptStatus
    terminal_exit_code = $terminalExitCode
} | ConvertTo-Json -Compress

# Collection keeps its own recovery code. Otherwise the source-safe terminal
# receipt exposes a required prospective-stage fault to Task Scheduler.
exit $terminalExitCode
