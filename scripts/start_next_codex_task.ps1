param(
    [string]$RepoRoot = "C:\Users\Public\Documents\thericher-v2",
    [string]$ModelArtifactRoot = "D:\thericher-v2\model-artifacts"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $RepoRoot)) {
    throw "Repo root not found: $RepoRoot"
}

Set-Location -LiteralPath $RepoRoot

Write-Host "== TheRicher v2 next Codex task preflight =="
Write-Host "Repo: $RepoRoot"
Write-Host ""

Write-Host "== Git status =="
git status --short --branch
Write-Host ""

Write-Host "== Latest commit =="
git log -1 --oneline --decorate
Write-Host ""

Write-Host "== Required first-read files =="
$required = @(
    "HANDOFF.md",
    "NEXT_CODEX_GOAL.md",
    "VISION.md",
    "ARCHITECTURE.md",
    "AGENTS.md",
    "DECISIONS.md",
    "RUNBOOK.md",
    "INTERIM_GOAL_SCRIPT.md"
)

foreach ($file in $required) {
    if (-not (Test-Path -LiteralPath $file)) {
        throw "Missing required file: $file"
    }
    Write-Host "ok $file"
}
Write-Host ""

Write-Host "== Model artifact root =="
$driveName = Split-Path -Qualifier $ModelArtifactRoot
if ($driveName) {
    $driveLetter = $driveName.TrimEnd(":")
    if (-not (Get-PSDrive -Name $driveLetter -ErrorAction SilentlyContinue)) {
        throw "Model artifact drive is not available: $driveName"
    }
}
if (-not (Test-Path -LiteralPath $ModelArtifactRoot)) {
    New-Item -ItemType Directory -Force -Path $ModelArtifactRoot | Out-Null
}
Write-Host "ok $ModelArtifactRoot"
Write-Host "Set THERICHER_HOST_MODEL_ARTIFACT_ROOT=D:/thericher-v2/model-artifacts for Docker."
Write-Host ""

Write-Host "== Verification commands =="
Write-Host "uv run --extra dev pytest -q"
Write-Host "uv run --extra dev ruff check ."
Write-Host "docker compose config --quiet"
Write-Host ""

Write-Host "== Completion handoff rule =="
Write-Host "Before ending a long task, refresh NEXT_CODEX_GOAL.md with the next single objective."
Write-Host ""

Write-Host "== Active next Codex objective =="
Get-Content -LiteralPath "NEXT_CODEX_GOAL.md" -Raw
