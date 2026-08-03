[CmdletBinding()]
param(
    [ValidateSet("negative-control", "feasibility")]
    [string]$Stage,
    [string]$ProjectRoot = (Join-Path $PSScriptRoot "..")
)

$ErrorActionPreference = "Stop"

function Invoke-PrefixCapabilityService {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [Parameter(Mandatory = $true)]
        [string]$Service,
        [Parameter(Mandatory = $true)]
        [string[]]$CommandOverride
    )

    $priorErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = @(
            & docker.exe compose --project-directory $ProjectRoot `
                --profile kis-spy-paginated-prefix-capability `
                run --rm --no-deps --pull never $Service @CommandOverride 2>&1
        )
        $exitCode = [int]$LASTEXITCODE
    } finally {
        $ErrorActionPreference = $priorErrorActionPreference
    }
    return [pscustomobject]@{
        ExitCode = $exitCode
        Output = $output
    }
}

function Get-PrefixPayload {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Output
    )

    $jsonLines = @(
        $Output |
            ForEach-Object { [string]$_ } |
            Where-Object { $_.Trim().StartsWith("{") -and $_.Trim().EndsWith("}") }
    )
    for ($index = $jsonLines.Count - 1; $index -ge 0; $index--) {
        try {
            return ($jsonLines[$index] | ConvertFrom-Json -ErrorAction Stop)
        } catch {
            continue
        }
    }
    return $null
}

function ConvertTo-UtcMarker {
    param(
        [Parameter(Mandatory = $true)]
        [datetime]$Value
    )

    return $Value.ToUniversalTime().ToString(
        "o",
        [System.Globalization.CultureInfo]::InvariantCulture
    )
}

function Get-EasternNow {
    param(
        [Parameter(Mandatory = $true)]
        [datetime]$UtcNow
    )

    $timeZone = [System.TimeZoneInfo]::FindSystemTimeZoneById("Eastern Standard Time")
    return [System.TimeZoneInfo]::ConvertTimeFromUtc($UtcNow.ToUniversalTime(), $timeZone)
}

function Test-PrefixStageWindow {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Stage,
        [Parameter(Mandatory = $true)]
        [datetime]$EasternNow
    )

    if ($EasternNow.DayOfWeek -in @([DayOfWeek]::Saturday, [DayOfWeek]::Sunday)) {
        return $false
    }
    $negativeStart = $EasternNow.Date.AddHours(15).AddMinutes(29).AddSeconds(30)
    $cutoff = $EasternNow.Date.AddHours(15).AddMinutes(30)
    if ($Stage -eq "negative-control") {
        return $EasternNow -ge $negativeStart -and $EasternNow -lt $cutoff
    }
    return $EasternNow -ge $cutoff -and $EasternNow -lt $cutoff.AddMinutes(1)
}

function Write-PrefixSchedulePayload {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Stage,
        [Parameter(Mandatory = $true)]
        [string]$Status,
        [Parameter(Mandatory = $true)]
        [datetime]$ObservedAt,
        [object]$ControlStatus = $null,
        [object]$CollectionExitCode = $null,
        [object]$ObservationStatus = $null
    )

    [ordered]@{
        kind = "kis_spy_paginated_prefix_capability_schedule"
        stage = $Stage
        status = $Status
        observed_at_utc = ConvertTo-UtcMarker -Value $ObservedAt
        control_status = $ControlStatus
        collection_exit_code = $CollectionExitCode
        observation_status = $ObservationStatus
    } | ConvertTo-Json -Compress
}

if (-not (Get-Command docker.exe -ErrorAction SilentlyContinue)) {
    throw "docker.exe is required to run the SPY paginated-prefix capability schedule."
}

$resolvedProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$composePath = Join-Path $resolvedProjectRoot "docker-compose.yml"
if (-not (Test-Path -LiteralPath $composePath -PathType Leaf)) {
    throw "Project root must contain docker-compose.yml: $resolvedProjectRoot"
}

$startedAt = (Get-Date).ToUniversalTime()
$easternNow = Get-EasternNow -UtcNow $startedAt
if (-not (Test-PrefixStageWindow -Stage $Stage -EasternNow $easternNow)) {
    Write-PrefixSchedulePayload -Stage $Stage -Status "no_network_noop" -ObservedAt $startedAt
    exit 0
}

$sessionDate = $easternNow.ToString("yyyy-MM-dd", [System.Globalization.CultureInfo]::InvariantCulture)
$runId = "spy-prefix-" + $easternNow.ToString("yyyyMMdd", [System.Globalization.CultureInfo]::InvariantCulture) + "-v1"
$observerBase = @(
    "python",
    "scripts/observe_kis_paper_spy_paginated_prefix_capability.py",
    "--run-id",
    $runId,
    "--session-date",
    $sessionDate,
    "--cache-root",
    "/app/market_data",
    "--artifact-root",
    "/app/model_artifacts",
    "--repository-root",
    "/app"
)

if ($Stage -eq "negative-control") {
    $control = Invoke-PrefixCapabilityService `
        -ProjectRoot $resolvedProjectRoot `
        -Service "kis-spy-paginated-prefix-observer" `
        -CommandOverride ($observerBase + @(
            "--phase",
            "negative-control"
        ))
    $payload = Get-PrefixPayload -Output $control.Output
    if ($control.ExitCode -ne 0 -or $null -eq $payload) {
        Write-PrefixSchedulePayload `
            -Stage $Stage `
            -Status "observer_unavailable" `
            -ObservedAt $startedAt
        exit 21
    }
    Write-PrefixSchedulePayload `
        -Stage $Stage `
        -Status "negative_control_recorded" `
        -ObservedAt $startedAt `
        -ControlStatus $payload.status
    exit 0
}

$preflightStartedAt = (Get-Date).ToUniversalTime()
if (-not (Test-PrefixStageWindow -Stage $Stage -EasternNow (Get-EasternNow -UtcNow $preflightStartedAt))) {
    Write-PrefixSchedulePayload -Stage $Stage -Status "no_network_noop" -ObservedAt $preflightStartedAt
    exit 0
}
$preflight = Invoke-PrefixCapabilityService `
    -ProjectRoot $resolvedProjectRoot `
    -Service "kis-spy-paginated-prefix-observer" `
    -CommandOverride ($observerBase + @(
        "--phase",
        "positive-preflight"
    ))
$preflightPayload = Get-PrefixPayload -Output $preflight.Output
if ($preflight.ExitCode -ne 0 -or $null -eq $preflightPayload) {
    Write-PrefixSchedulePayload -Stage $Stage -Status "preflight_unavailable" -ObservedAt $preflightStartedAt
    exit 21
}
if ([string]$preflightPayload.status -ne "ready") {
    Write-PrefixSchedulePayload `
        -Stage $Stage `
        -Status "preflight_not_ready" `
        -ObservedAt $preflightStartedAt `
        -ControlStatus $preflightPayload.negative_control_status
    exit 0
}

$collectorDispatchAt = (Get-Date).ToUniversalTime()
if (-not (Test-PrefixStageWindow -Stage $Stage -EasternNow (Get-EasternNow -UtcNow $collectorDispatchAt))) {
    Write-PrefixSchedulePayload `
        -Stage $Stage `
        -Status "no_network_noop" `
        -ObservedAt $collectorDispatchAt `
        -ControlStatus $preflightPayload.negative_control_status
    exit 0
}
$collection = Invoke-PrefixCapabilityService `
    -ProjectRoot $resolvedProjectRoot `
    -Service "kis-spy-paginated-prefix-collector" `
    -CommandOverride @(
        "python",
        "scripts/collect_kis_paper_spy_paginated_prefix_capability.py",
        "--execute",
        "--run-id",
        $runId,
        "--session-date",
        $sessionDate,
        "--cache-root",
        "/app/market_data",
        "--control-root",
        "/app/collection_control",
        "--repository-root",
        "/app"
    )
$collectionReturnedAt = (Get-Date).ToUniversalTime()
$collectionPayload = Get-PrefixPayload -Output $collection.Output
$collectionStartedMarker = if (
    $null -ne $collectionPayload -and
    $null -ne $collectionPayload.collection_started_at -and
    -not [string]::IsNullOrWhiteSpace([string]$collectionPayload.collection_started_at.utc)
) {
    [string]$collectionPayload.collection_started_at.utc
} elseif (
    $null -ne $collectionPayload -and
    -not [string]::IsNullOrWhiteSpace([string]$collectionPayload.collection_started_at)
) {
    [string]$collectionPayload.collection_started_at
} else {
    ConvertTo-UtcMarker -Value $collectorDispatchAt
}
$observationStartedAt = (Get-Date).ToUniversalTime()
$observation = Invoke-PrefixCapabilityService `
    -ProjectRoot $resolvedProjectRoot `
    -Service "kis-spy-paginated-prefix-observer" `
    -CommandOverride ($observerBase + @(
        "--phase",
        "positive-observation",
        "--collection-started-at",
        $collectionStartedMarker,
        "--collector-returned-at",
        (ConvertTo-UtcMarker -Value $collectionReturnedAt),
        "--collection-exit-code",
        [string]([int]$collection.ExitCode)
    ))
$observationPayload = Get-PrefixPayload -Output $observation.Output
if ($observation.ExitCode -ne 0 -or $null -eq $observationPayload) {
    Write-PrefixSchedulePayload `
        -Stage $Stage `
        -Status "observer_unavailable" `
        -ObservedAt $observationStartedAt `
        -ControlStatus $preflightPayload.negative_control_status `
        -CollectionExitCode $collection.ExitCode
    exit 21
}
Write-PrefixSchedulePayload `
    -Stage $Stage `
    -Status "observation_recorded" `
    -ObservedAt $observationStartedAt `
    -ControlStatus $preflightPayload.negative_control_status `
    -CollectionExitCode $collection.ExitCode `
    -ObservationStatus $observationPayload.status
exit 0
