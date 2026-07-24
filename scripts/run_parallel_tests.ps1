param(
    [ValidateRange(1, 64)]
    [int]$Workers = 4,
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
try {
    # File-level distribution preserves most test-local fixture assumptions.
    & uv run --extra dev pytest -q -n $Workers --dist=loadfile --basetemp $baseTemp @PytestArgs
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
