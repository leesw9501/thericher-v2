[CmdletBinding()]
param(
    [string]$ProjectRoot = (Join-Path $PSScriptRoot ".."),
    [string]$ArtifactRoot = "D:\thericher-v2\model-artifacts"
)

$ErrorActionPreference = "Stop"

$TaskName = "thericher-kis-paper-intraday-head"
$ExpectedTriggerTimes = @("00:29", "02:28", "04:24", "06:20")
$ExpectedDaysOfWeekMask = 124 # Tuesday through Saturday KST for U.S. Monday through Friday.
$ExpectedExecutionLimit = "PT1H30M"
$ArtifactDirectory = "execution/kis-paper-intraday-head-static-contract-v1"

function Get-RelativeArtifactPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root,
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $rootFullPath = ([System.IO.Path]::GetFullPath($Root)).Replace("/", "\").TrimEnd("\")
    $pathFullPath = ([System.IO.Path]::GetFullPath($Path)).Replace("/", "\")
    $prefix = $rootFullPath + "\"
    if (-not $pathFullPath.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Artifact path must stay beneath the artifact root."
    }
    return $pathFullPath.Substring($prefix.Length)
}

function Test-ExternalArtifactRoot {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ArtifactRoot,
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    $artifactFullPath = [System.IO.Path]::GetFullPath($ArtifactRoot).TrimEnd("\")
    $projectFullPath = [System.IO.Path]::GetFullPath($ProjectRoot).TrimEnd("\")
    if (
        $artifactFullPath.Equals($projectFullPath, [System.StringComparison]::OrdinalIgnoreCase) `
            -or $artifactFullPath.StartsWith(
                $projectFullPath + "\",
                [System.StringComparison]::OrdinalIgnoreCase
            )
    ) {
        throw "Artifact root must be outside the Git workspace."
    }
    return $artifactFullPath
}

function Get-SourceSha256 {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $stream = [System.IO.File]::Open(
        $Path,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read,
        [System.IO.FileShare]::Read
    )
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        $digest = $hasher.ComputeHash($stream)
    } finally {
        $hasher.Dispose()
        $stream.Dispose()
    }
    return "sha256:" + ([BitConverter]::ToString($digest).Replace("-", "")).ToLowerInvariant()
}

function Get-StaticSourceContract {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    $paths = [ordered]@{
        installer = Join-Path $ProjectRoot "scripts\install_kis_paper_schedules.ps1"
        runner = Join-Path $ProjectRoot "scripts\run_kis_paper_intraday_head_schedule.ps1"
        compose = Join-Path $ProjectRoot "docker-compose.yml"
    }
    $hashes = [ordered]@{}
    $contents = [ordered]@{}
    foreach ($entry in $paths.GetEnumerator()) {
        if (-not (Test-Path -LiteralPath $entry.Value -PathType Leaf)) {
            return [pscustomobject]@{
                status = "unavailable"
                hashes = [ordered]@{}
            }
        }
        try {
            $contents[$entry.Key] = (Get-Content -LiteralPath $entry.Value -Raw).Replace("`r`n", "`n")
            $hashes[$entry.Key] = Get-SourceSha256 -Path $entry.Value
        } catch {
            return [pscustomobject]@{
                status = "unavailable"
                hashes = [ordered]@{}
            }
        }
    }

    $installerRequired = @(
        'Name = "thericher-kis-paper-intraday-head"',
        'Profile = "kis-paper-intraday-head"',
        'Service = "kis-paper-intraday-head"',
        'Runner = "run_kis_paper_intraday_head_schedule.ps1"',
        'At = @("00:29", "02:28", "04:24", "06:20")',
        '"Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"',
        'RecoverMissedRun = $true',
        'ExecutionLimitMinutes = 90'
    )
    $runnerRequired = @(
        '--profile kis-paper-intraday-head',
        ' -Service "kis-paper-intraday-head"',
        '"--mode",',
        '"session-capture",',
        '"--execute",',
        '"--skip-legacy-preparation",',
        '$CollectionBasePagesPerTarget = 4',
        '$CollectionPostClosePagesPerTarget = 8',
        '$CollectionPostCloseEarliestEastern = [TimeSpan]::FromHours(16) + [TimeSpan]::FromMinutes(20)',
        '$CollectionPostCloseLatestEastern = [TimeSpan]::FromHours(20)',
        'function Get-CollectionPagesPerTarget',
        '$collectionPagesPerTarget = Get-CollectionPagesPerTarget -ObservedAt $collectionStartedAt',
        '"--pages-per-target",',
        '[string]$collectionPagesPerTarget,'
    )
    $composeRequired = @(
        '  kis-paper-intraday-head:',
        'profiles: ["kis-paper-intraday-head"]',
        'scripts/backfill_kis_paper_private_intraday.py',
        '- session-capture',
        '- --skip-legacy-preparation',
        '- "4"',
        'THERICHER_MODE: off',
        'KIS_PAPER_APP_KEY:',
        'KIS_PAPER_APP_SECRET:'
    )
    $composeForbidden = @("KIS_LIVE", "KIS_PAPER_ACCOUNT")

    $runnerCollectionIndex = $contents.runner.IndexOf(' -Service "kis-paper-intraday-head"')
    $runnerGuardIndex = $contents.runner.IndexOf("if (`$collectionExitCode -eq 0)")
    $composeStart = $contents.compose.IndexOf("`n  kis-paper-intraday-head:`n")
    $composeEnd = $contents.compose.IndexOf("`nvolumes:", $composeStart)
    $composeSection = ""
    if ($composeStart -ge 0 -and $composeEnd -gt $composeStart) {
        $composeSection = $contents.compose.Substring($composeStart, $composeEnd - $composeStart)
    }

    $installerMatches = $installerRequired | ForEach-Object {
        $contents.installer.Contains($_)
    } | Where-Object { -not $_ }
    $runnerMatches = $runnerRequired | ForEach-Object {
        $contents.runner.Contains($_)
    } | Where-Object { -not $_ }
    $composeMatches = $composeRequired | ForEach-Object {
        $composeSection.Contains($_)
    } | Where-Object { -not $_ }
    $composeHasForbidden = $composeForbidden | Where-Object {
        $composeSection.Contains($_)
    }

    $status = "matches"
    if (
        $installerMatches.Count -gt 0 `
            -or $runnerMatches.Count -gt 0 `
            -or $composeMatches.Count -gt 0 `
            -or $composeHasForbidden.Count -gt 0 `
            -or $runnerCollectionIndex -lt 0 `
            -or $runnerGuardIndex -le $runnerCollectionIndex
    ) {
        $status = "mismatch"
    }
    return [pscustomobject]@{
        status = $status
        hashes = $hashes
    }
}

function ConvertTo-StaticTaskState {
    param([object]$State)

    if ($null -eq $State) {
        return "unavailable"
    }
    switch ([string]$State) {
        "Ready" { return "ready" }
        "Running" { return "running" }
        default { return "other" }
    }
}

function ConvertTo-NormalizedTaskArgument {
    param([object]$Value)

    if ($null -eq $Value) {
        return ""
    }
    return ([regex]::Replace(([string]$Value).Replace("/", "\\"), "\\s+", " ")).Trim()
}

function Test-ExpectedTaskAction {
    param(
        [object[]]$Actions,
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    if ($Actions.Count -ne 1) {
        return "mismatch"
    }
    $action = $Actions[0]
    if ($null -eq $action -or [string]::IsNullOrWhiteSpace([string]$action.Execute)) {
        return "unavailable"
    }
    if (-not ([System.IO.Path]::GetFileName([string]$action.Execute).Equals(
        "powershell.exe",
        [System.StringComparison]::OrdinalIgnoreCase
    ))) {
        return "mismatch"
    }
    $runnerPath = [System.IO.Path]::GetFullPath(
        (Join-Path $ProjectRoot "scripts\run_kis_paper_intraday_head_schedule.ps1")
    )
    $expectedArgument = "-NoProfile -ExecutionPolicy Bypass -File `"$runnerPath`" -ProjectRoot `"$ProjectRoot`""
    if (
        (ConvertTo-NormalizedTaskArgument $action.Arguments) -ne
        (ConvertTo-NormalizedTaskArgument $expectedArgument)
    ) {
        return "mismatch"
    }
    return "matches"
}

function Test-ExpectedTaskTriggers {
    param([object[]]$Triggers)

    if ($Triggers.Count -ne $ExpectedTriggerTimes.Count) {
        return "mismatch"
    }
    $times = @()
    foreach ($trigger in $Triggers) {
        if ($null -eq $trigger) {
            return "unavailable"
        }
        $boundary = [string]$trigger.StartBoundary
        if ($boundary -notmatch "T(?<time>[0-9]{2}:[0-9]{2}):[0-9]{2}") {
            return "unavailable"
        }
        try {
            $daysOfWeek = [int]$trigger.DaysOfWeek
        } catch {
            return "unavailable"
        }
        $repetition = $trigger.Repetition
        if ($null -ne $repetition) {
            $hasConfiguredRepetition = `
                -not [string]::IsNullOrWhiteSpace([string]$repetition.Interval) `
                -or -not [string]::IsNullOrWhiteSpace([string]$repetition.Duration) `
                -or [bool]$repetition.StopAtDurationEnd
        } else {
            $hasConfiguredRepetition = $false
        }
        if ($daysOfWeek -ne $ExpectedDaysOfWeekMask -or $hasConfiguredRepetition) {
            return "mismatch"
        }
        $times += $Matches.time
    }
    if ((@($times | Sort-Object) -join ",") -ne (@($ExpectedTriggerTimes | Sort-Object) -join ",")) {
        return "mismatch"
    }
    return "matches"
}

function Test-ExpectedTaskSettings {
    param([object]$Settings)

    if ($null -eq $Settings) {
        return "unavailable"
    }
    try {
        $executionLimit = [string]$Settings.ExecutionTimeLimit
        $startWhenAvailable = [bool]$Settings.StartWhenAvailable
        $multipleInstances = [string]$Settings.MultipleInstances
        $restartCount = [int]$Settings.RestartCount
    } catch {
        return "unavailable"
    }
    if (
        $executionLimit -notin @($ExpectedExecutionLimit, "01:30:00") `
            -or -not $startWhenAvailable `
            -or -not $multipleInstances.Equals("IgnoreNew", [System.StringComparison]::OrdinalIgnoreCase) `
            -or $restartCount -ne 0
    ) {
        return "mismatch"
    }
    return "matches"
}

function Get-InstalledStaticTaskContract {
    param(
        [object]$Task,
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [Parameter(Mandatory = $true)]
        [ValidateSet("matches", "mismatch", "unavailable")]
        [string]$SourceStatus,
        [Parameter(Mandatory = $true)]
        [hashtable]$SourceHashes
    )

    if ($null -eq $Task) {
        return [pscustomobject]@{
            status = "unavailable"
            task_state = "unavailable"
            enabled = "unavailable"
            action = "unavailable"
            triggers = "unavailable"
            settings = "unavailable"
            source = $SourceStatus
            source_hashes = $SourceHashes
        }
    }
    $enabled = "unavailable"
    try {
        $enabled = if ([bool]$Task.Settings.Enabled) { "matches" } else { "mismatch" }
    } catch {
        $enabled = "unavailable"
    }
    $action = Test-ExpectedTaskAction -Actions @($Task.Actions) -ProjectRoot $ProjectRoot
    $triggers = Test-ExpectedTaskTriggers -Triggers @($Task.Triggers)
    $settings = Test-ExpectedTaskSettings -Settings $Task.Settings
    $components = @($enabled, $action, $triggers, $settings, $SourceStatus)
    $status = if ($components -contains "unavailable") {
        "unavailable"
    } elseif ($components -contains "mismatch") {
        "mismatch"
    } else {
        "matches"
    }
    return [pscustomobject]@{
        status = $status
        task_state = ConvertTo-StaticTaskState $Task.State
        enabled = $enabled
        action = $action
        triggers = $triggers
        settings = $settings
        source = $SourceStatus
        source_hashes = $SourceHashes
    }
}

function Write-StaticTaskContractReceipt {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Fact,
        [Parameter(Mandatory = $true)]
        [string]$ArtifactRoot,
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [datetime]$ObservedAt = (Get-Date).ToUniversalTime()
    )

    $artifactFullPath = Test-ExternalArtifactRoot `
        -ArtifactRoot $ArtifactRoot `
        -ProjectRoot $ProjectRoot
    $directory = Join-Path $artifactFullPath $ArtifactDirectory
    [System.IO.Directory]::CreateDirectory($directory) | Out-Null
    $observedAtUtc = $ObservedAt.ToUniversalTime()
    $fileName = "static-contract-" + $observedAtUtc.ToString("yyyyMMddTHHmmssfffffffZ") + "-" + [guid]::NewGuid().ToString("N").Substring(0, 12) + ".json"
    $path = Join-Path $directory $fileName
    $payload = [ordered]@{
        schema_version = 1
        kind = "kis_paper_intraday_head_static_task_contract"
        observed_at = $observedAtUtc.ToString("o")
        task_name = $TaskName
        status = $Fact.status
        task_state = $Fact.task_state
        enabled = $Fact.enabled
        action = $Fact.action
        triggers = $Fact.triggers
        settings = $Fact.settings
        source = $Fact.source
        source_hashes = $Fact.source_hashes
        task_invoked = $false
        docker_invoked = $false
        kis_called = $false
        paper_only = $true
        claim = "static task-contract evidence only; not task execution, scheduler-origin proof, provider diagnosis, market-data qualification, model evidence, PnL, or broker activity"
    }
    $encoded = [System.Text.Encoding]::ASCII.GetBytes((ConvertTo-Json $payload -Depth 5 -Compress) + "`n")
    $stream = [System.IO.File]::Open($path, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    try {
        $stream.Write($encoded, 0, $encoded.Length)
    } finally {
        $stream.Dispose()
    }
    $safePayload = [ordered]@{}
    foreach ($entry in $payload.GetEnumerator()) {
        $safePayload[$entry.Key] = $entry.Value
    }
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        $digest = $hasher.ComputeHash($encoded)
    } finally {
        $hasher.Dispose()
    }
    $safePayload.evidence_path = Get-RelativeArtifactPath -Root $artifactFullPath -Path $path
    $safePayload.evidence_sha256 = "sha256:" + ([BitConverter]::ToString($digest).Replace("-", "")).ToLowerInvariant()
    return [pscustomobject]$safePayload
}

# Runtime entry point. The helpers above are pure categorization and receipt code.
$resolvedProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$sourceFact = Get-StaticSourceContract -ProjectRoot $resolvedProjectRoot
$task = $null
try {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
} catch {
    $task = $null
}
$fact = Get-InstalledStaticTaskContract `
    -Task $task `
    -ProjectRoot $resolvedProjectRoot `
    -SourceStatus $sourceFact.status `
    -SourceHashes $sourceFact.hashes
$receipt = Write-StaticTaskContractReceipt `
    -Fact $fact `
    -ArtifactRoot $ArtifactRoot `
    -ProjectRoot $resolvedProjectRoot
$receipt | ConvertTo-Json -Depth 5 -Compress
