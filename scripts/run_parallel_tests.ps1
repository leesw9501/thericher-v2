param(
    [ValidateRange(1, 64)]
    [int]$Workers = [Math]::Min(8, [Environment]::ProcessorCount),
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$tempRoot = "C:\trpy"

New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null

do {
    $baseTemp = Join-Path $tempRoot ("r-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
} while (Test-Path -LiteralPath $baseTemp)

Push-Location $repoRoot
$exitCode = 1
try {
    # File-level distribution preserves most test-local fixture assumptions.
    & uv run --extra dev pytest -q -n $Workers --dist=loadfile --basetemp $baseTemp @PytestArgs
    $exitCode = $LASTEXITCODE
}
finally {
    Pop-Location
    if ($exitCode -eq 0 -and (Test-Path -LiteralPath $baseTemp)) {
        try {
            Remove-Item -LiteralPath $baseTemp -Recurse -Force -ErrorAction Stop
        }
        catch {
            Write-Warning "Parallel pytest passed but could not remove its temp path: $baseTemp"
            $exitCode = 1
        }
    }
}

exit $exitCode
