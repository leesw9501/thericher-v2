[CmdletBinding()]
param(
    [string]$ProjectRoot = (Join-Path $PSScriptRoot ".."),
    [string]$InvocationReceiptArtifactRoot = ""
)

$ErrorActionPreference = "Stop"

$CollectionBasePagesPerTarget = 4
$CollectionPostClosePagesPerTarget = 8
$CollectionPostCloseEarliestEastern = [TimeSpan]::FromHours(16) + [TimeSpan]::FromMinutes(20)
$CollectionPostCloseLatestEastern = [TimeSpan]::FromHours(20)

function Get-CollectionPagesPerTarget {
    param(
        [Parameter(Mandatory = $true)]
        [datetime]$ObservedAt
    )

    if ($ObservedAt.Kind -eq [System.DateTimeKind]::Unspecified) {
        throw "Collection observation timestamp must be timezone-aware."
    }
    $eastern = [System.TimeZoneInfo]::FindSystemTimeZoneById("Eastern Standard Time")
    $easternObservedAt = [System.TimeZoneInfo]::ConvertTimeFromUtc(
        $ObservedAt.ToUniversalTime(),
        $eastern
    )
    $isRegularEasternWeekday = $easternObservedAt.DayOfWeek -in @(
        [System.DayOfWeek]::Monday,
        [System.DayOfWeek]::Tuesday,
        [System.DayOfWeek]::Wednesday,
        [System.DayOfWeek]::Thursday,
        [System.DayOfWeek]::Friday
    )
    if (
        $isRegularEasternWeekday `
            -and $easternObservedAt.TimeOfDay -ge $CollectionPostCloseEarliestEastern `
            -and $easternObservedAt.TimeOfDay -lt $CollectionPostCloseLatestEastern
    ) {
        return $CollectionPostClosePagesPerTarget
    }
    return $CollectionBasePagesPerTarget
}

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

function Get-UniqueSafeCollectionFailureCategory {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Output,
        [string]$ExpectedScheduleRunId = "",
        [int]$CollectionExitCode = 1,
        [int]$PagesPerTarget = 8
    )

    if ($CollectionExitCode -eq 0) {
        return "reason_unavailable"
    }
    # Accept only an exact error payload or one current bound capture. The
    # immutable capture reader separately verifies bytes before projecting causes.
    $expectedProperties = @(
        "freshness_projection",
        "reason",
        "status"
    ) | Sort-Object
    $dispatcherConfigReasons = @(
        "config_missing",
        "execute_flag_required"
    )
    $collectorProviderReasons = @(
        "auth_rejected",
        "auth_response_invalid",
        "minute_cursor_invalid",
        "minute_cursor_stalled",
        "minute_duplicate_conflict",
        "minute_exchange_timestamp_invalid",
        "minute_korea_timestamp_invalid",
        "minute_ohlc_invalid",
        "minute_page_limit_exceeded",
        "minute_response_empty",
        "minute_response_invalid",
        "minute_response_rejected",
        "paper_host_required",
        "private_intraday_collector_error",
        "rate_limited",
        "redirect_rejected",
        "request_not_allowlisted",
        "response_invalid",
        "token_request_not_due",
        "transport_failure"
    )
    $categories = @()
    foreach ($line in $Output) {
        $text = [string]$line
        if (-not ($text.Trim().StartsWith("{") -and $text.Trim().EndsWith("}"))) {
            continue
        }
        try {
            $payload = $text | ConvertFrom-Json -ErrorAction Stop
        } catch {
            return "reason_unavailable"
        }
        if ($payload.kind -ceq "kis_paper_intraday_session_capture") {
            if ([string]::IsNullOrEmpty($ExpectedScheduleRunId)) {
                return "reason_unavailable"
            }
            $binding = Get-UniqueSafeSessionCaptureTerminalBinding `
                -Output @($text) -ExpectedScheduleRunId $ExpectedScheduleRunId
            if (
                $null -eq $binding `
                    -or $payload.schedule_run_id -cne $ExpectedScheduleRunId `
                    -or $payload.status -cnotin @("complete", "incomplete") `
                    -or $payload.mode -cne "session-capture" `
                    -or $payload.collection_mode -cne "session_capture" `
                    -or $payload.route_class -cne "kis_paper_market_data" `
                    -or $payload.paper_only -isnot [bool] -or -not $payload.paper_only `
                    -or $payload.current_session_cumulative_coverage_digest -cne $binding.current_session_cumulative_coverage_digest `
                    -or $payload.current_session_cumulative_coverage_category -cne $binding.current_session_cumulative_coverage_category
            ) {
                return "reason_unavailable"
            }
            try {
                $captureTime = [datetimeoffset]$payload.observed_at
                $bindingTime = [datetimeoffset]$binding.observed_at
            } catch {
                return "reason_unavailable"
            }
            if ($captureTime -ne $bindingTime) {
                return "reason_unavailable"
            }
            $allowedCaptureProperties = @(
                "schema_version", "kind", "status", "paper_only", "route_class",
                "collection_mode", "capture_target_key", "observed_at", "storage",
                "targets", "coverage", "current_session_cumulative_coverage",
                "schedule_run_id", "current_session_cumulative_coverage_digest",
                "current_session_cumulative_coverage_category", "terminal_receipt_binding",
                "mode", "freshness_projection"
            )
            if (@($payload.PSObject.Properties.Name | Where-Object { $_ -cnotin $allowedCaptureProperties }).Count -ne 0) {
                return "reason_unavailable"
            }
            $targets = @($payload.targets)
            if ($targets.Count -ne 2 -or (@($targets.target_key | Sort-Object) -join "|") -cne "QQQ/NAS/1m|SPY/AMS/1m") {
                return "reason_unavailable"
            }
            $diagnosticCodes = @{
                response_decode = @("envelope_shape_invalid")
                row_parse = @("row_not_mapping", "required_field_invalid", "row_constructor_invalid")
                page_contract = @("row_count_exceeded", "continuation_contract_invalid")
                head_contract = @("response_identity_mismatch", "duplicate_exchange_timestamp", "duplicate_korea_timestamp", "mixed_exchange_dates", "timestamp_order_invalid")
            }
            $failureCount = 0
            foreach ($target in $targets) {
                if (
                    $target.target_key -isnot [string] -or $target.status -isnot [string] `
                        -or ($target.row_count -isnot [long] -and $target.row_count -isnot [int]) `
                        -or ($target.exact_overlap_rows -isnot [long] -and $target.exact_overlap_rows -isnot [int]) `
                        -or $target.row_count -lt 0 -or $target.exact_overlap_rows -lt 0
                ) {
                    return "reason_unavailable"
                }
                $requiredTargetProperties = @("target_key", "status", "row_count", "exact_overlap_rows", "reason", "conflict_origin", "retained_head_conflict_disposition")
                $diagnosticProperties = @("failure_phase", "failure_code", "failure_page_ordinal", "requested_pages_per_target")
                $targetProperties = @($target.PSObject.Properties.Name)
                $diagnosticCount = @($targetProperties | Where-Object { $_ -cin $diagnosticProperties }).Count
                $expectedTargetProperties = @($requiredTargetProperties)
                if ($diagnosticCount -eq 4) {
                    $expectedTargetProperties += $diagnosticProperties
                    if (
                        $target.reason -cne "minute_response_invalid" `
                            -or $target.status -cnotin @("partial", "rejected") `
                            -or $target.failure_phase -isnot [string] `
                            -or $target.failure_code -isnot [string] `
                            -or $target.failure_phase -cnotin @($diagnosticCodes.Keys) `
                            -or $target.failure_code -cnotin $diagnosticCodes[$target.failure_phase] `
                            -or ($target.failure_page_ordinal -isnot [long] -and $target.failure_page_ordinal -isnot [int]) `
                            -or $target.failure_page_ordinal -lt 1 `
                            -or ($target.requested_pages_per_target -isnot [long] -and $target.requested_pages_per_target -isnot [int]) `
                            -or $target.requested_pages_per_target -notin @(4, 8) `
                            -or $target.requested_pages_per_target -ne $PagesPerTarget `
                            -or $target.failure_page_ordinal -gt $target.requested_pages_per_target
                    ) {
                        return "reason_unavailable"
                    }
                } elseif ($diagnosticCount -ne 0) {
                    return "reason_unavailable"
                }
                $tokenProperties = @("token_http_status_class", "token_upstream_code")
                $presentTokenProperties = @($targetProperties | Where-Object { $_ -cin $tokenProperties })
                if ($presentTokenProperties.Count -gt 0) {
                    if (
                        $presentTokenProperties -cnotcontains "token_http_status_class" `
                            -or $target.token_http_status_class -isnot [string] `
                            -or $target.token_http_status_class -cnotin @("1xx", "2xx", "3xx", "4xx", "5xx") `
                            -or $target.status -cnotin @("partial", "rejected")
                    ) {
                        return "reason_unavailable"
                    }
                    $expectedTargetProperties += "token_http_status_class"
                    $hasUpstreamCode = $presentTokenProperties -ccontains "token_upstream_code"
                    if ($hasUpstreamCode) {
                        if ($target.token_upstream_code -isnot [string] -or $target.token_upstream_code -cne "EGW00201") {
                            return "reason_unavailable"
                        }
                        $expectedTargetProperties += "token_upstream_code"
                    }
                    $tokenCombinationValid = switch -CaseSensitive ($target.reason) {
                        "rate_limited" { $true }
                        "auth_rejected" { -not $hasUpstreamCode }
                        "auth_response_invalid" { -not $hasUpstreamCode -and $target.token_http_status_class -ceq "2xx" }
                        "response_invalid" { -not $hasUpstreamCode -and $target.token_http_status_class -ceq "2xx" }
                        default { $false }
                    }
                    if (-not $tokenCombinationValid) {
                        return "reason_unavailable"
                    }
                }
                if ($targetProperties -ccontains "retained_head_conflict_diagnostic") {
                    $expectedTargetProperties += "retained_head_conflict_diagnostic"
                    $retained = $target.retained_head_conflict_diagnostic
                    $retainedProperties = @(
                        "fresh_status", "fresh_reason", "accepted_row_count", "accepted_page_count",
                        "conflicting_chunk_count", "conflicting_minute_count", "failed_predicates",
                        "prospective_active_key_loss_count"
                    )
                    if (
                        $null -eq $retained -or $retained -isnot [pscustomobject] `
                            -or (@($retained.PSObject.Properties.Name | Sort-Object) -join "|") -cne (@($retainedProperties | Sort-Object) -join "|") `
                            -or $retained.fresh_status -isnot [string] `
                            -or $retained.fresh_status -cnotin @("collected", "partial") `
                            -or $retained.failed_predicates -isnot [array] `
                            -or $PagesPerTarget -notin @(4, 8)
                    ) {
                        return "reason_unavailable"
                    }
                    foreach ($count in @("accepted_row_count", "accepted_page_count", "conflicting_chunk_count", "conflicting_minute_count", "prospective_active_key_loss_count")) {
                        $value = $retained.$count
                        if (
                            ($value -isnot [long] -and $value -isnot [int]) `
                                -or $value -lt 0 `
                                -or ($count -cne "prospective_active_key_loss_count" -and $value -eq 0)
                        ) {
                            return "reason_unavailable"
                        }
                    }
                    $allowedPredicates = @(
                        "quarantine_disabled", "fresh_not_collected", "predecessor_not_head",
                        "predecessor_input_cursor_present", "predecessor_output_cursor_present",
                        "predecessor_outcome_reason_ineligible", "predecessor_conflict_origin_present",
                        "predecessor_identity_invalid", "partial_active_key_loss", "boundary_active_key_loss"
                    )
                    foreach ($predicate in $retained.failed_predicates) {
                        if ($predicate -isnot [string] -or $predicate -cnotin $allowedPredicates) {
                            return "reason_unavailable"
                        }
                    }
                    $predicates = @($retained.failed_predicates)
                    if (
                        ($predicates -join "|") -cne (@($predicates | Sort-Object -Unique) -join "|") `
                            -or ($predicates -ccontains "fresh_not_collected" -and $retained.fresh_status -cne "partial") `
                            -or ($retained.fresh_status -ceq "partial" -and $predicates -cnotcontains "fresh_not_collected" -and ($retained.fresh_reason -cne "minute_response_invalid" -or ($retained.prospective_active_key_loss_count -gt 0 -and $predicates -cnotcontains "partial_active_key_loss"))) `
                            -or ($predicates -ccontains "partial_active_key_loss" -and ($retained.fresh_status -cne "partial" -or $retained.prospective_active_key_loss_count -eq 0)) `
                            -or ($predicates -ccontains "boundary_active_key_loss" -and ($retained.fresh_status -cne "collected" -or $retained.prospective_active_key_loss_count -le 0)) `
                            -or ($retained.fresh_status -ceq "collected" -and $null -ne $retained.fresh_reason) `
                            -or ($retained.fresh_status -ceq "partial" -and ($retained.fresh_reason -isnot [string] -or $retained.fresh_reason -cnotin (@($collectorProviderReasons) + @("config_missing")))) `
                            -or $retained.accepted_page_count -gt $PagesPerTarget `
                            -or $retained.accepted_row_count -gt (120 * $retained.accepted_page_count) `
                            -or $retained.conflicting_minute_count -gt $retained.accepted_row_count `
                            -or $target.status -cnotin @("collected", "partial", "recovered", "rejected") `
                            -or (($target.status -ceq "rejected") -ne ($predicates.Count -gt 0))
                    ) {
                        return "reason_unavailable"
                    }
                    if ($target.status -ceq "rejected") {
                        if (
                            $target.reason -cne "minute_duplicate_conflict" `
                                -or $target.conflict_origin -cne "retained_cache" `
                                -or $target.row_count -ne 0 -or $target.exact_overlap_rows -ne 0
                        ) {
                            return "reason_unavailable"
                        }
                    } elseif (
                        $null -ne $target.conflict_origin `
                            -or $target.row_count -ne $retained.accepted_row_count `
                            -or ($target.status -ceq "partial" -and ($retained.fresh_status -cne "partial" -or $target.reason -cne "minute_response_invalid" -or $retained.fresh_reason -cne $target.reason -or $retained.prospective_active_key_loss_count -ne 0)) `
                            -or ($target.status -cne "partial" -and $retained.fresh_status -cne "collected") `
                            -or ($target.status -ceq "collected" -and $null -ne $target.reason) `
                            -or ($target.status -ceq "recovered" -and $target.reason -cnotin @("already_cached", "private_intraday_collector_error"))
                    ) {
                        return "reason_unavailable"
                    }
                }
                if ((@($targetProperties | Sort-Object) -join "|") -cne (@($expectedTargetProperties | Sort-Object) -join "|")) {
                    return "reason_unavailable"
                }
                if ($null -eq $target.conflict_origin) {
                    if ($target.retained_head_conflict_disposition -cne "not_applicable" -or $target.reason -ceq "minute_duplicate_conflict") {
                        return "reason_unavailable"
                    }
                } elseif (
                    $target.status -cne "rejected" -or $target.reason -cne "minute_duplicate_conflict" `
                        -or $target.conflict_origin -cnotin @("candidate_batch", "retained_cache") `
                        -or ($target.conflict_origin -ceq "candidate_batch" -and $target.retained_head_conflict_disposition -cne "not_applicable") `
                        -or ($target.conflict_origin -ceq "retained_cache" -and $target.retained_head_conflict_disposition -cnotin @("preserved", "quarantined"))
                ) {
                    return "reason_unavailable"
                }
                if ($target.status -cin @("partial", "rejected")) {
                    if ($target.reason -isnot [string] -or $target.reason -cnotin $collectorProviderReasons) {
                        return "reason_unavailable"
                    }
                    $failureCount += 1
                } elseif ($target.status -cnotin @("collected", "recovered", "source_exhausted")) {
                    return "reason_unavailable"
                }
            }
            if ($failureCount -eq 0) {
                return "reason_unavailable"
            }
            $categories += "collector_provider"
            continue
        }
        $propertyNames = @($payload.PSObject.Properties.Name | Sort-Object)
        if (
            $propertyNames.Count -ne $expectedProperties.Count `
                -or ($propertyNames -join "|") -ne ($expectedProperties -join "|")
        ) {
            return "reason_unavailable"
        }
        if (
            -not ($payload.freshness_projection -is [string]) `
                -or -not ($payload.reason -is [string]) `
                -or -not ($payload.status -is [string]) `
                -or $payload.freshness_projection -notin @("written", "unavailable") `
                -or $payload.status -ne "not_executed"
        ) {
            return "reason_unavailable"
        }
        if ($payload.reason -in $dispatcherConfigReasons) {
            $categories += "dispatcher_config"
        } elseif ($payload.reason -in $collectorProviderReasons) {
            $categories += "collector_provider"
        } else {
            return "reason_unavailable"
        }
    }
    if ($categories.Count -ne 1) {
        return "reason_unavailable"
    }
    return $categories[0]
}

function Write-HeadInvocationReceipt {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [Parameter(Mandatory = $true)]
        [ValidateSet("started", "terminal")]
        [string]$Phase,
        [Parameter(Mandatory = $true)]
        [string]$RunId,
        [Parameter(Mandatory = $true)]
        [string]$StartedAt,
        [string]$ScheduleObservedAt,
        [string]$CompletedAt,
        [int]$CollectionExitCode,
        [ValidateSet("reason_unavailable", "dispatcher_config", "collector_provider")]
        [string]$CollectionFailureCategory = "reason_unavailable",
        [string]$ScheduleReceiptStatus,
        [int]$TerminalExitCode,
        [string]$ArtifactRoot
    )

    $arguments = @(
        "python",
        "-m",
        "thericher_v2.ops.kis_paper_intraday_head_invocation_receipt",
        $Phase,
        "--run-id",
        $RunId,
        "--started-at",
        $StartedAt,
        "--repository-root",
        $ProjectRoot
    )
    if ($Phase -eq "terminal") {
        $arguments += @(
            "--completed-at",
            $CompletedAt,
            "--schedule-observed-at",
            $ScheduleObservedAt,
            "--collection-exit-code",
            [string]$CollectionExitCode,
            "--collection-failure-category",
            $CollectionFailureCategory,
            "--schedule-receipt-status",
            $ScheduleReceiptStatus,
            "--terminal-exit-code",
            [string]$TerminalExitCode
        )
    }
    if (-not [string]::IsNullOrWhiteSpace($ArtifactRoot)) {
        $arguments += @("--artifact-root", $ArtifactRoot)
    }
    $priorErrorActionPreference = $ErrorActionPreference
    Push-Location $ProjectRoot
    try {
        $ErrorActionPreference = "Continue"
        $null = & uv run @arguments 2>$null
    } catch {
        # Invocation receipts are diagnostic. They cannot defer collection.
    } finally {
        Pop-Location
        $ErrorActionPreference = $priorErrorActionPreference
    }
}

function Get-UniqueSafeAvailabilityPayload {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Output
    )

    $expectedProperties = @(
        "contract_sha256",
        "precommit_sha256",
        "reason",
        "receipt_sha256",
        "receipt_id",
        "status",
        "summary_sha256"
    ) | Sort-Object
    $safePayloads = @()
    foreach ($line in $Output) {
        $text = [string]$line
        if (-not ($text.Trim().StartsWith("{") -and $text.Trim().EndsWith("}"))) {
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
                -or ($propertyNames -join "|") -ne ($expectedProperties -join "|")
        ) {
            continue
        }
        $receiptId = [string]$payload.receipt_id
        $status = [string]$payload.status
        $reason = $payload.reason
        if (
            $receiptId -ne "kis-intraday-mtf-availability-receipt-v1" `
                -or $status -notin @("qualified_for_prospective_input", "input_unavailable") `
                -or [string]$payload.contract_sha256 -notmatch '^sha256:[0-9a-f]{64}$' `
                -or [string]$payload.receipt_sha256 -notmatch '^sha256:[0-9a-f]{64}$' `
                -or [string]$payload.precommit_sha256 -notmatch '^sha256:[0-9a-f]{64}$' `
                -or [string]$payload.summary_sha256 -notmatch '^sha256:[0-9a-f]{64}$'
        ) {
            continue
        }
        if (
            ($status -eq "qualified_for_prospective_input" -and $null -ne $reason) `
                -or ($status -eq "input_unavailable" `
                    -and [string]$reason -ne "insufficient_contiguous_intraday_session_coverage")
        ) {
            continue
        }
        $safePayloads += $payload
    }
    if ($safePayloads.Count -ne 1) {
        return $null
    }
    return $safePayloads[0]
}

function Get-SafePairObservationAttemptBinding {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Output
    )

    $bindings = @()
    foreach ($line in $Output) {
        $text = [string]$line
        if (-not ($text.Trim().StartsWith("{") -and $text.Trim().EndsWith("}"))) {
            continue
        }
        try {
            $payload = $text | ConvertFrom-Json -ErrorAction Stop
        } catch {
            continue
        }
        if (
            [string]$payload.kind -ne "kis_qqq_spy_mtf_prospective_observation" `
                -or [string]$payload.store_outcome -notin @("appended", "duplicate") `
                -or $null -eq $payload.attempt
        ) {
            continue
        }
        $stageStatus = [string]$payload.status
        $attemptStatus = [string]$payload.attempt.status
        $attemptSha256 = [string]$payload.attempt.attempt_sha256
        if (
            $attemptStatus -notin @("observed", "not_observed") `
                -or $attemptSha256 -notmatch '^sha256:[0-9a-f]{64}$' `
                -or ($stageStatus -ne $attemptStatus -and $stageStatus -ne "duplicate")
        ) {
            continue
        }
        $bindings += [pscustomobject]@{
            attempt_sha256 = $attemptSha256
            attempt_status = $attemptStatus
            store_outcome = [string]$payload.store_outcome
        }
    }
    if ($bindings.Count -ne 1) {
        return $null
    }
    return $bindings[0]
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
$collectionPagesPerTarget = Get-CollectionPagesPerTarget -ObservedAt $collectionStartedAt
$collectionStartedAtMarker = $collectionStartedAt.ToString(
    "o",
    [System.Globalization.CultureInfo]::InvariantCulture
)
Write-HeadInvocationReceipt `
    -ProjectRoot $resolvedProjectRoot `
    -Phase "started" `
    -RunId $scheduleRunId `
    -StartedAt $collectionStartedAtMarker `
    -ArtifactRoot $InvocationReceiptArtifactRoot
$collectionCommand = @(
    "python",
    "scripts/backfill_kis_paper_private_intraday.py",
    "--execute",
    "--mode",
    "session-capture",
    "--skip-legacy-preparation",
    "--pages-per-target",
    [string]$collectionPagesPerTarget,
    "--explicit-pair-head-continuation",
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
$collectionFailureCategory = "reason_unavailable"
if ($collectionExitCode -ne 0) {
    $collectionFailureCategory = Get-UniqueSafeCollectionFailureCategory `
        -Output $collection.Output -ExpectedScheduleRunId $scheduleRunId `
        -CollectionExitCode $collectionExitCode -PagesPerTarget $collectionPagesPerTarget
}
$scheduleObservedAt = $collectionReturnedAt
$scheduleObservedAtMarker = $scheduleObservedAt.ToString(
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
$expectedProspectiveValidationContract = "runtime-freshness-v5"

$availabilityExitCode = 0
$availabilityStatus = "not_applicable"
$availabilityRunLabel = "task-owned-$scheduleRunId"
$availabilityReceiptBinding = $null
$captureCycleExitCode = 0
$captureCycleStatus = "not_applicable"
$observationExitCode = 0
$observationStatus = "not_applicable"
$observationAttemptBinding = $null
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
        -AllowedStatuses @("preview", "no_intent", "canary_completed")
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

    # This refresh reads only the frozen historical cache. Its receipt is an
    # exact source identity for the pair reader, not a decision-time or finality attestation.
    $availability = Invoke-HeadProfileService `
        -ProjectRoot $resolvedProjectRoot `
        -Service "kis-paper-intraday-pair-observation" `
        -CommandOverride @(
            "python",
            "scripts/run_kis_intraday_mtf_availability_receipt.py",
            "--cache-root",
            "/app/market_data/us_equities/kis_paper_private/intraday",
            "--artifact-root",
            "/app/model_artifacts",
            "--repo-root",
            "/app",
            "--run-label",
            $availabilityRunLabel,
            "--allow-current-source-identities"
        )
    $availabilityExitCode = [int]$availability.ExitCode
    $availabilityPayload = Get-UniqueSafeAvailabilityPayload -Output $availability.Output
    if ($availabilityExitCode -eq 0 -and $null -ne $availabilityPayload) {
        $availabilityStatus = [string]$availabilityPayload.status
        $availabilityReceiptBinding = [pscustomobject]@{
            contract_sha256 = [string]$availabilityPayload.contract_sha256
            receipt_sha256 = [string]$availabilityPayload.receipt_sha256
            precommit_sha256 = [string]$availabilityPayload.precommit_sha256
            summary_sha256 = [string]$availabilityPayload.summary_sha256
        }
    } else {
        $availabilityStatus = "unavailable"
    }

    if ($availabilityStatus -eq "qualified_for_prospective_input") {
        $availabilitySummaryPath = (
            "/app/model_artifacts/data/kis-intraday-mtf-availability-receipt-v1/" +
            "$availabilityRunLabel/summary.json"
        )
        $pairObservation = Invoke-HeadProfileService `
            -ProjectRoot $resolvedProjectRoot `
            -Service "kis-paper-intraday-pair-observation" `
            -CommandOverride @(
                "python",
                "scripts/run_kis_qqq_spy_mtf_prospective_attempt.py",
                "--availability-summary",
                $availabilitySummaryPath,
                "--observed-at",
                $scheduleObservedAtMarker
            )
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
        $observationAttemptBinding = Get-SafePairObservationAttemptBinding `
            -Output $pairObservation.Output
    } elseif ($availabilityStatus -eq "input_unavailable") {
        # A valid local receipt can establish that this exact pair has no
        # historical input without turning the whole dispatch into a recovery.
        $observationStatus = "not_observed"
    } else {
        $observationStatus = "unavailable"
    }
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
    "--availability-exit-code",
    [string]$availabilityExitCode,
    "--availability-status",
    $availabilityStatus,
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
if ($null -ne $availabilityReceiptBinding) {
    $scheduleReceiptCommand += @(
        "--availability-contract-sha256",
        [string]$availabilityReceiptBinding.contract_sha256,
        "--availability-receipt-sha256",
        [string]$availabilityReceiptBinding.receipt_sha256,
        "--availability-precommit-sha256",
        [string]$availabilityReceiptBinding.precommit_sha256,
        "--availability-summary-sha256",
        [string]$availabilityReceiptBinding.summary_sha256
    )
}
if ($null -ne $observationAttemptBinding) {
    $scheduleReceiptCommand += @(
        "--observation-attempt-sha256",
        [string]$observationAttemptBinding.attempt_sha256,
        "--observation-attempt-status",
        [string]$observationAttemptBinding.attempt_status,
        "--observation-store-outcome",
        [string]$observationAttemptBinding.store_outcome
    )
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
$dispatchCompletedAt = (Get-Date).ToUniversalTime()
$dispatchCompletedAtMarker = $dispatchCompletedAt.ToString(
    "o",
    [System.Globalization.CultureInfo]::InvariantCulture
)
Write-HeadInvocationReceipt `
    -ProjectRoot $resolvedProjectRoot `
    -Phase "terminal" `
    -RunId $scheduleRunId `
    -StartedAt $collectionStartedAtMarker `
    -ScheduleObservedAt $scheduleObservedAtMarker `
    -CompletedAt $dispatchCompletedAtMarker `
    -CollectionExitCode $collectionExitCode `
    -CollectionFailureCategory $collectionFailureCategory `
    -ScheduleReceiptStatus $scheduleReceiptStatus `
    -TerminalExitCode $terminalExitCode `
    -ArtifactRoot $InvocationReceiptArtifactRoot

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
    availability_exit_code = $availabilityExitCode
    availability_status = $availabilityStatus
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
