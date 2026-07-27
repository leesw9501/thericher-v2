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
                    run --rm --no-deps --build $Service 2>&1
            )
        } else {
            $output = @(
                & docker.exe compose --project-directory $ProjectRoot --profile kis-paper-intraday-head `
                    run --rm --no-deps --build $Service @CommandOverride 2>&1
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

# The loop has no network or credentials. It records the exact local-paper
# replay before the separately owned Paper session decides whether KIS is needed.
$prospectiveLoop = Invoke-HeadProfileService `
    -ProjectRoot $resolvedProjectRoot `
    -Service "kis-paper-prospective-loop"
$prospectiveLoopExitCode = [int]$prospectiveLoop.ExitCode
$prospectiveLoopStatus = Get-ProfileStatus `
    -Output $prospectiveLoop.Output `
    -Kind "kis_paper_prospective_qqq_session" `
    -AllowedStatuses @("preview", "no_intent")

# This service opens the virtual-only execution route only for its own current
# eligible receipt. Its no-intent result never changes collection recovery.
$prospectiveSession = Invoke-HeadProfileService `
    -ProjectRoot $resolvedProjectRoot `
    -Service "kis-paper-prospective-qqq-session"
$prospectiveSessionExitCode = [int]$prospectiveSession.ExitCode
$prospectiveSessionPayload = Get-ProfilePayload `
    -Output $prospectiveSession.Output `
    -Kind "kis_paper_prospective_qqq_session"
$prospectiveSessionStatus = Get-ProfileStatus `
    -Output $prospectiveSession.Output `
    -Kind "kis_paper_prospective_qqq_session" `
    -AllowedStatuses @("preview", "no_intent", "canary_completed")

# Validation re-loads the exact retained cache for the execution session. It has
# no network or KIS environment values and cannot create a Paper side effect.
$prospectiveValidationExitCode = 0
$prospectiveValidationStatus = "not_run"
if ($prospectiveSessionExitCode -eq 0 -and $null -ne $prospectiveSessionPayload) {
    $sessionId = [string]$prospectiveSessionPayload.session_id
    if ($sessionId -match '^[A-Za-z0-9._-]{1,160}$') {
        $prospectiveValidation = Invoke-HeadProfileService `
            -ProjectRoot $resolvedProjectRoot `
            -Service "kis-paper-prospective-qqq-validation" `
            -CommandOverride @(
                "python",
                "-m",
                "thericher_v2.ops.kis_paper_prospective_qqq_validation",
                "--session-id",
                $sessionId,
                "--cache-root",
                "/app/market_data/us_equities/kis_paper_private/intraday-head",
                "--artifact-root",
                "/app/model_artifacts",
                "--repository-root",
                "/app"
            )
        $prospectiveValidationExitCode = [int]$prospectiveValidation.ExitCode
        $prospectiveValidationStatus = Get-ProfileStatus `
            -Output $prospectiveValidation.Output `
            -Kind "kis_paper_prospective_qqq_validation" `
            -AllowedStatuses @("validated")
    } else {
        $prospectiveValidationStatus = "unavailable"
    }
}

# The observer is an isolated no-op until a verified pair exists. Its result
# must never overwrite the collection task's independent recovery signal.
$observation = Invoke-HeadProfileService `
    -ProjectRoot $resolvedProjectRoot `
    -Service "kis-paper-intraday-observation"
$observationExitCode = [int]$observation.ExitCode
$observationStatus = Get-ProfileStatus `
    -Output $observation.Output `
    -Kind "kis_intraday_prospective_observation" `
    -AllowedStatuses @("pending", "unavailable", "complete")

[ordered]@{
    kind = "kis_paper_intraday_head_schedule"
    collection_exit_code = $collectionExitCode
    prospective_loop_exit_code = $prospectiveLoopExitCode
    prospective_loop_status = $prospectiveLoopStatus
    prospective_session_exit_code = $prospectiveSessionExitCode
    prospective_session_status = $prospectiveSessionStatus
    prospective_validation_exit_code = $prospectiveValidationExitCode
    prospective_validation_status = $prospectiveValidationStatus
    observation_exit_code = $observationExitCode
    observation_status = $observationStatus
} | ConvertTo-Json -Compress

exit $collectionExitCode
