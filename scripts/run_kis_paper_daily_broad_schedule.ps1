[CmdletBinding()]
param(
    [string]$ProjectRoot = (Join-Path $PSScriptRoot "..")
)

$ErrorActionPreference = "Stop"

function Invoke-KisPaperDailyBroadContinuation {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    $collectionExitCode = Invoke-KisPaperDailyBroadCollector -ProjectRoot $ProjectRoot
    if ($collectionExitCode -ne 0) {
        return $collectionExitCode
    }

    $postprocess = Invoke-KisPaperDailyBroadPanelPostprocess -ProjectRoot $ProjectRoot
    if ($postprocess.ExitCode -ne 0) {
        return $postprocess.ExitCode
    }
    if ([string]::IsNullOrWhiteSpace($postprocess.PostrunReceiptPath)) {
        Write-Warning "Broad KIS Paper postprocess succeeded without a usable receipt path."
        return $postprocess.ExitCode
    }

    $chronologyExitCode = Invoke-KisPaperDailyBroadChronologyObservation -ProjectRoot $ProjectRoot -PostrunReceiptPath $postprocess.PostrunReceiptPath
    if ($chronologyExitCode -ne 0) {
        Write-Warning "Broad KIS Paper chronology observation needs recovery: $chronologyExitCode"
    }
    return $postprocess.ExitCode
}

function Invoke-KisPaperDailyBroadCollector {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    if (-not (Get-Command docker.exe -ErrorAction SilentlyContinue)) {
        throw "docker.exe is required to run the broad KIS Paper daily continuation."
    }

    $resolvedProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
    $composePath = Join-Path $resolvedProjectRoot "docker-compose.yml"
    if (-not (Test-Path -LiteralPath $composePath -PathType Leaf)) {
        throw "Project root must contain docker-compose.yml: $resolvedProjectRoot"
    }

    $priorErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & docker.exe compose --project-directory $resolvedProjectRoot `
            --profile kis-paper-daily-broad-backfill run --rm --no-deps --pull never `
            kis-paper-daily-broad-backfill `
            python scripts/backfill_kis_paper_daily_broad.py `
            --execute --continuation `
            --cache-root /app/market_data `
            --control-root /app/collection_control `
            --artifact-root /app/model_artifacts `
            --repository-root /app `
            --symbol-directory-root /app/symbol_directory `
            --max-chunks 24000 `
            --max-runtime-seconds 50400
        $exitCode = [int]$LASTEXITCODE
    } finally {
        $ErrorActionPreference = $priorErrorActionPreference
    }
    return $exitCode
}

function Invoke-KisPaperDailyBroadPanelPostprocess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    if (-not (Get-Command uv.exe -ErrorAction SilentlyContinue)) {
        throw "uv.exe is required to run the offline broad KIS Paper panel postprocess."
    }

    $resolvedProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
    $postprocessPath = Join-Path $resolvedProjectRoot "scripts\postprocess_kis_paper_daily_broad_panel.py"
    if (-not (Test-Path -LiteralPath $postprocessPath -PathType Leaf)) {
        throw "Broad KIS Paper panel postprocess is missing: $postprocessPath"
    }

    $outputLines = @()
    $priorErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $arguments = @(
            "run",
            "--offline",
            "python",
            $postprocessPath,
            "--repository-root",
            $resolvedProjectRoot
        )
        $outputLines = @(& uv.exe @arguments)
        $exitCode = [int]$LASTEXITCODE
    } finally {
        $ErrorActionPreference = $priorErrorActionPreference
    }
    foreach ($line in $outputLines) {
        Write-Host $line
    }

    $postrunReceiptPath = $null
    if ($exitCode -eq 0) {
        try {
            $postrunReceiptPath = Resolve-KisPaperDailyBroadPostrunReceiptPath -OutputLines $outputLines -PostrunArtifactRoot "D:\thericher-v2\model-artifacts\data\kis-paper-daily-nas-broad-panel-postrun-v1"
        } catch {
            Write-Warning "Broad KIS Paper postprocess receipt could not be resolved: $($_.Exception.Message)"
        }
    }
    return [pscustomobject]@{
        ExitCode = $exitCode
        PostrunReceiptPath = $postrunReceiptPath
    }
}

function Resolve-KisPaperDailyBroadPostrunReceiptPath {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$OutputLines,
        [Parameter(Mandatory = $true)]
        [string]$PostrunArtifactRoot
    )

    $jsonLines = @(
        $OutputLines |
            ForEach-Object { ([string]$_).Trim() } |
            Where-Object { $_.StartsWith("{") }
    )
    if ($jsonLines.Count -ne 1) {
        throw "Broad KIS Paper postprocess output is ambiguous."
    }
    try {
        $payload = $jsonLines[0] | ConvertFrom-Json -ErrorAction Stop
    } catch {
        throw "Broad KIS Paper postprocess output is invalid."
    }
    if (
        $payload.kind -ne "kis_paper_daily_broad_panel_postrun" -or
        $payload.status -ne "complete" -or
        $payload.reason -ne "stable_full_breadth_panel"
    ) {
        throw "Broad KIS Paper postprocess output is not complete."
    }

    $receiptSha256 = [string]$payload.receipt_sha256
    if ($receiptSha256 -notmatch "^sha256:[0-9a-f]{64}$") {
        throw "Broad KIS Paper postprocess receipt digest is invalid."
    }
    $receiptPath = Join-Path $PostrunArtifactRoot ("postrun-" + $receiptSha256.Substring(7, 24) + ".json")
    if (-not (Test-Path -LiteralPath $receiptPath -PathType Leaf)) {
        throw "Broad KIS Paper postprocess receipt is missing."
    }
    $item = Get-Item -LiteralPath $receiptPath -Force
    if ($item.LinkType) {
        throw "Broad KIS Paper postprocess receipt is invalid."
    }
    return $item.FullName
}

function Invoke-KisPaperDailyBroadChronologyObservation {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [Parameter(Mandatory = $true)]
        [string]$PostrunReceiptPath
    )

    if (-not (Get-Command uv.exe -ErrorAction SilentlyContinue)) {
        throw "uv.exe is required to run the offline broad KIS Paper chronology observation."
    }

    $resolvedProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
    $chronologyPath = Join-Path $resolvedProjectRoot "scripts\observe_kis_paper_daily_broad_panel_chronology.py"
    if (-not (Test-Path -LiteralPath $chronologyPath -PathType Leaf)) {
        throw "Broad KIS Paper chronology observer is missing: $chronologyPath"
    }

    $priorErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $arguments = @(
            "run",
            "--offline",
            "python",
            $chronologyPath,
            "--postrun-receipt",
            $PostrunReceiptPath,
            "--repository-root",
            $resolvedProjectRoot
        )
        & uv.exe @arguments
        $exitCode = [int]$LASTEXITCODE
    } finally {
        $ErrorActionPreference = $priorErrorActionPreference
    }
    return $exitCode
}

if ($MyInvocation.InvocationName -ne ".") {
    exit (Invoke-KisPaperDailyBroadContinuation -ProjectRoot $ProjectRoot)
}
