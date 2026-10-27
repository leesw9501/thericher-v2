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
            "--env-file",
            (Join-Path $ProjectRoot ".env.example"),
            "--project-directory",
            $ProjectRoot,
            "--profile",
            "kis-paper-daily-pair-forward-v2",
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
        $bootstrapResult = Invoke-PairForwardBootstrap `
            -ProjectRoot $ProjectRoot -ComposeArguments $arguments
        if ($null -eq $bootstrapResult -or @($bootstrapResult).Count -ne 1 `
                -or $bootstrapResult.ExitCode -isnot [int] `
                -or $null -eq $bootstrapResult.PSObject.Properties["Output"]) {
            throw "Pair forward bootstrap result is unavailable."
        }
        $output = @($bootstrapResult.Output)
        $exitCode = $bootstrapResult.ExitCode
    } finally {
        $ErrorActionPreference = $priorErrorActionPreference
    }
    return [pscustomobject]@{
        ExitCode = $exitCode
        Output = $output
    }
}

function ConvertTo-PairForwardNativeArgument {
    param([AllowEmptyString()][string]$Value)
    # Windows CommandLineToArgv convention; ProcessStartInfo never uses a shell.
    $builder = New-Object System.Text.StringBuilder
    [void]$builder.Append('"')
    $slashes = 0
    foreach ($character in $Value.ToCharArray()) {
        if ($character -eq '\') { $slashes++; continue }
        if ($character -eq '"') {
            [void]$builder.Append(('\' * (2 * $slashes + 1)))
        } else {
            [void]$builder.Append(('\' * $slashes))
        }
        [void]$builder.Append($character)
        $slashes = 0
    }
    [void]$builder.Append(('\' * (2 * $slashes)))
    [void]$builder.Append('"')
    return $builder.ToString()
}

function Invoke-PairForwardBootstrap {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [Parameter(Mandatory = $true)]
        [string[]]$ComposeArguments
    )

    $python = Join-Path $ProjectRoot ".venv/Scripts/python.exe"
    $bootstrap = Join-Path $ProjectRoot "scripts/run_kis_paper_daily_pair_forward_bootstrap.py"
    if (-not (Test-Path -LiteralPath $python -PathType Leaf) `
            -or -not (Test-Path -LiteralPath $bootstrap -PathType Leaf)) {
        throw "Pair forward bootstrap is unavailable."
    }
    $nativeArguments = @('-I', '-S', '-B', $bootstrap, '--execute', '--compose',
        '--project-root', $ProjectRoot, '--') + $ComposeArguments
    $start = New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName = $python
    $start.Arguments = (($nativeArguments | ForEach-Object {
        ConvertTo-PairForwardNativeArgument -Value $_
    }) -join ' ')
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $start
    $started = $false
    try {
        $started = $process.Start()
        if (-not $started) { throw 'Pair forward bootstrap did not start.' }
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        $process.WaitForExit()
        $exitCode = [int]$process.ExitCode
        $output = @($stdout.GetAwaiter().GetResult(), $stderr.GetAwaiter().GetResult())
        return [pscustomobject]@{ ExitCode = $exitCode; Output = $output }
    } finally {
        if ($started -and -not $process.HasExited) {
            $process.Kill()
            $process.WaitForExit()
        }
        $process.Dispose()
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
        "--cache-lineage",
        "v2",
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
        -Service "kis-paper-daily-pair-forward-v2-preflight" `
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
        -Service "kis-paper-daily-pair-forward-v2-preflight"
    $preflightExitCode = [int]$preflight.ExitCode
    if ($preflightExitCode -eq $CacheCurrentExitCode) {
        return 0
    }
    if ($preflightExitCode -ne $CollectionRequiredExitCode) {
        return $preflightExitCode
    }
    $collection = Invoke-PairForwardProfileService `
        -ProjectRoot $resolvedProjectRoot `
        -Service "kis-paper-daily-pair-forward-v2"
    return [int]$collection.ExitCode
}

if ($MyInvocation.InvocationName -ne ".") {
    exit (Invoke-PairForwardSchedule -ProjectRoot $ProjectRoot)
}
