param(
    [Parameter(Mandatory)][ValidateSet('SampleEnabled','SampleDisabled','Disable','Restore')][string]$Mode,
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{64}$')][string]$PlanSha256,
    [ValidatePattern('^[0-9a-f]{64}$')][string]$AttemptSha256,
    [switch]$BoundedNormalRestore
)
$ErrorActionPreference = 'Stop'
$PSModuleAutoLoadingPreference = 'None'
Import-Module Microsoft.PowerShell.Utility -ErrorAction Stop
Set-StrictMode -Version Latest
$held = [Collections.Generic.List[IDisposable]]::new()

function Read-Exact([string]$Path, [string]$Pin) {
    $file = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    $held.Add($file)
    if ($file.Length -le 0 -or $file.Length -gt 131072) { throw 'OBSERVER_SOURCE_SIZE' }
    $bytes = [byte[]]::new($file.Length)
    $file.ReadExactly($bytes)
    $actual = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()
    if ($actual -cne $Pin) { throw 'OBSERVER_SOURCE_PIN' }
    return [Text.Encoding]::UTF8.GetString($bytes)
}

try {
    if ($BoundedNormalRestore -and $Mode -cne 'Restore') { throw 'OBSERVER_MODE' }
    $plan = Read-Exact ([IO.Path]::Combine($PSScriptRoot, 'OBSERVER-PLAN.json')) $PlanSha256 |
        ConvertFrom-Json -AsHashtable -DateKind String
    $core = [IO.Path]::Combine($PSScriptRoot, 'paper_h3_observer_native.psm1')
    $out = [IO.Path]::Combine($PSScriptRoot, 'owned-output')
    if ($plan.schema -cne 'DEC4_H3_OBSERVER_PLAN_V1' -or
        $plan.observer_task_path -cne '\thericher-kis-paper-snapshot-observer' -or
        $plan.phase -cnotin @('entry','exit') -or
        $plan.helper_root -ine $PSScriptRoot -or $plan.output_root -ine $out -or
        $plan.bridge_path -ine $PSCommandPath -or $plan.core_path -ine $core -or
        -not [IO.Directory]::Exists($out)) { throw 'OBSERVER_SOURCE_SCOPE' }
    # The frozen plan and the actual sibling source are held through native readback.
    $null = Read-Exact $PSCommandPath $plan.bridge_sha256
    $null = Read-Exact $core $plan.core_sha256
    $m = Import-Module $core -Force -PassThru -ErrorAction Stop
    $notAfter = if ($Mode -ceq 'Disable') { [DateTimeOffset]$plan.closes_utc } elseif ($BoundedNormalRestore) {
        ([DateTimeOffset]$plan.hard_utc).AddSeconds(30)
    } else { $null }
    if ($Mode -ceq 'SampleEnabled' -or $Mode -ceq 'SampleDisabled') {
        if ($AttemptSha256) { throw 'OBSERVER_READ_ONLY_SCOPE' }
        $before = $null
    } else {
        $name = if ($Mode -ceq 'Disable') { 'STARTED' } elseif ($Mode -ceq 'Restore') {
            'RESTORE_STARTED'
        } else { throw 'OBSERVER_MODE' }
        $now = [DateTimeOffset]::UtcNow
        if ($now -lt [DateTimeOffset]$plan.opens_utc -or
            ($null -ne $notAfter -and $now -ge $notAfter)) {
            throw 'OBSERVER_CLOCK'
        }
        $execRoot = 'D:\thericher-v2\model-artifacts\execution\'
        if (-not [IO.Path]::GetFullPath($PSScriptRoot).StartsWith(
            $execRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'OBSERVER_WRITE_ROOT' }
        $attempt = Read-Exact ([IO.Path]::Combine($out, $name + '.json')) $AttemptSha256 |
            ConvertFrom-Json -AsHashtable -DateKind String
        if ($attempt.plan -cne $PlanSha256) { throw 'OBSERVER_ATTEMPT_SCOPE' }
        if ($Mode -ceq 'Disable') {
            if ($attempt.schema -cne 'h3-dec4-observer-disable-v1') { throw 'OBSERVER_ATTEMPT_SCOPE' }
            $before = $attempt.before
        } else {
            if ($attempt.schema -cne 'h3-dec4-observer-restore-v1') { throw 'OBSERVER_ATTEMPT_SCOPE' }
            $disabled = Read-Exact ([IO.Path]::Combine($out, 'DISABLED.json')) $attempt.disabled_sha256 |
                ConvertFrom-Json -AsHashtable -DateKind String
            $before = $disabled.observed
        }
        if ($before.task_path -cne $plan.observer_task_path -or $before.hidden_inclusive -isnot [bool] -or
            -not $before.hidden_inclusive -or $before.instances -ne 0) { throw 'OBSERVER_SWITCH_SCOPE' }
        # A second invocation of a consumed native attempt must never write.
        $native = [IO.File]::Open([IO.Path]::Combine($out, $name + '-NATIVE'),
            [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try {
            $bytes = [Text.Encoding]::ASCII.GetBytes($AttemptSha256)
            $native.Write($bytes, 0, $bytes.Length)
            $native.Flush($true)
        } finally { $native.Dispose() }
    }
    $reply = & $m {
        param($operation,$previous,$nativePlan,$mutationNotAfter)
        $service = New-Object -ComObject 'Schedule.Service'
        $service.Connect()
        $folder = $service.GetFolder('\')
        if ($operation -cin @('SampleEnabled','SampleDisabled')) {
            return Read-H3ObserverNativeSnapshot $service $folder $script:H3ObserverPath $script:H3ObserverAcl7 `
                ($operation -ceq 'SampleEnabled')
        }
        if ($previous.api7_sha256 -cne $script:H3ObserverAcl7) { throw 'OBSERVER_SWITCH_SCOPE' }
        if ($operation -ceq 'Disable' -and $previous.xml_sha256 -cne $script:H3ObserverXml) {
            throw 'OBSERVER_SWITCH_SCOPE'
        }
        $now = [DateTimeOffset]::UtcNow
        if ($now -lt [DateTimeOffset]$nativePlan.opens_utc -or
            ($null -ne $mutationNotAfter -and $now -ge $mutationNotAfter)) {
            throw 'OBSERVER_CLOCK'
        }
        return Set-H3ObserverExactEnabled $service $folder $previous ($operation -ceq 'Restore') $mutationNotAfter
    } $Mode $before $plan $notAfter
    [Console]::WriteLine(($reply | ConvertTo-Json -Compress))
} catch {
    [Console]::Error.WriteLine('H3_OBSERVER_LEASE_TRANSPORT_UNAVAILABLE')
    exit 1
} finally {
    foreach ($item in $held) { $item.Dispose() }
}
