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

$collection = Invoke-HeadProfileService `
    -ProjectRoot $resolvedProjectRoot `
    -Service "kis-paper-intraday-head"
$collectionExitCode = [int]$collection.ExitCode
$scheduleObservedAt = (Get-Date).ToUniversalTime()
$scheduleRunId = New-ScheduleRunId -ObservedAt $scheduleObservedAt
$scheduleObservedAtMarker = $scheduleObservedAt.ToString(
    "o",
    [System.Globalization.CultureInfo]::InvariantCulture
)

# The collector is independent from the SPY cycle. The SPY service is dispatched
# only after collection returns, while the legacy QQQ route remains inactive.
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

$captureCycleExitCode = 0
$captureCycleStatus = "not_applicable"
$observationExitCode = 0
$observationStatus = "not_applicable"
if ($collectionExitCode -eq 0) {
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
    "--artifact-root",
    "/app/model_artifacts",
    "--repository-root",
    "/app"
)
if ($null -ne $prospectiveSpyCycleId) {
    $scheduleReceiptCommand += @("--prospective-spy-cycle-id", [string]$prospectiveSpyCycleId)
}
if ($null -ne $prospectiveSpyCanaryRunId) {
    $scheduleReceiptCommand += @("--prospective-spy-canary-run-id", [string]$prospectiveSpyCanaryRunId)
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
