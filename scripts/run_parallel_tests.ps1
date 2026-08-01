param(
    [ValidateRange(1, 64)]
    [int]$Workers = [Math]::Min(8, [Environment]::ProcessorCount),
    [switch]$RequireCleanTempRoot,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$tempRoot = "C:\trpy"

New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
$existingTempRoots = @(
    Get-ChildItem -LiteralPath $tempRoot -Directory -Force -Filter "r-*" -ErrorAction Stop
)
if ($RequireCleanTempRoot) {
    $resolvedTempRoot = [IO.Path]::GetFullPath($tempRoot).TrimEnd([char[]]@('\', '/'))
    $staleTempRootCutoff = [DateTime]::UtcNow.AddHours(-24)
    foreach ($candidate in $existingTempRoots) {
        if ($candidate.LastWriteTimeUtc -ge $staleTempRootCutoff) {
            continue
        }
        $resolvedCandidate = [IO.Path]::GetFullPath($candidate.FullName)
        $isReparsePoint = [bool](
            $candidate.Attributes -band [IO.FileAttributes]::ReparsePoint
        )
        if (
            $candidate.LinkType -or
            $isReparsePoint -or
            $candidate.Name -notlike "r-*" -or
            -not [string]::Equals(
                [IO.Path]::GetDirectoryName($resolvedCandidate),
                $resolvedTempRoot,
                [StringComparison]::OrdinalIgnoreCase
            )
        ) {
            throw "Refusing to remove an unmanaged parallel pytest temp root: $($candidate.FullName)"
        }
        Remove-Item -LiteralPath $resolvedCandidate -Recurse -Force -ErrorAction Stop
    }
    $existingTempRoots = @(
        Get-ChildItem -LiteralPath $tempRoot -Directory -Force -Filter "r-*" -ErrorAction Stop
    )
    if ($existingTempRoots.Count -gt 0) {
        Write-Error "Parallel pytest requires a clean temp root; found $($existingTempRoots.Count) recent run root(s)."
        exit 1
    }
}

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
