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

if ($MyInvocation.InvocationName -ne ".") {
    exit (Invoke-KisPaperDailyBroadContinuation -ProjectRoot $ProjectRoot)
}
