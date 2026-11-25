param(
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{64}$')][string]$ModuleSha256,
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{64}$')][string]$PlanSha256,
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{32}$')][string]$RequestId
)
$ErrorActionPreference = 'Stop'
$PSModuleAutoLoadingPreference = 'None'
Import-Module Microsoft.PowerShell.Utility -ErrorAction Stop
try {
    $module = [IO.Path]::Combine($PSScriptRoot, 'paper_h3_observer_native.psm1')
    $file = [IO.File]::Open($module, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    try {
        $actual = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($file)).ToLowerInvariant()
        if ($actual -cne $ModuleSha256) { throw 'H3_OBSERVER_TRANSPORT_PIN' }
        Import-Module $module -Force -ErrorAction Stop
        $reply = Get-H3NativeObserverReadiness -PlanSha256 $PlanSha256 -RequestId $RequestId
        [Console]::WriteLine(($reply | ConvertTo-Json -Compress))
    } finally { $file.Dispose() }
} catch {
    [Console]::Error.WriteLine('H3_OBSERVER_READINESS_UNAVAILABLE')
    exit 1
}
