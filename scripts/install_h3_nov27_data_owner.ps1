[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('\A[0-9a-f]{64}\z')]
    [string]$SourceSha256,
    [switch]$Install
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$name = 'thericher-h3-nov27-modp1-owner-20261127-v1'
$source = 'D:\thericher-v2\model-artifacts\data\h3-nov27-modp1-owner-20261127-v1\source'
$launcher = Join-Path $source 'scripts\run_h3_nov27_data_owner.py'
$python = 'C:\Users\Public\Documents\thericher-v2\.venv\Scripts\pythonw.exe'
$arguments = '-I -S -B "{0}" --source-sha256 {1}' -f $launcher, $SourceSha256
$start = [DateTimeOffset]'2026-11-27T18:30:00+00:00'
$end = $start.AddMinutes(1)
$installBy = $start.AddMinutes(-5)
$contractSource = "TheRicher/H3-Nov27-Data/$SourceSha256"
$description = 'TheRicher Nov27 read-only MODP1 capture, one opportunity, no orders.'

function Assert-FutureWindow {
    if ([DateTimeOffset]::UtcNow -ge $installBy) { throw 'NOV27_INSTALL_WINDOW_CLOSED' }
}

function Assert-Definition($Task, [bool]$Enabled) {
    $d = $Task.Definition
    $s = $d.Settings
    $acl = [Security.AccessControl.RawSecurityDescriptor]::new($Task.GetSecurityDescriptor(7))
    $desiredAcl = [Security.AccessControl.RawSecurityDescriptor]::new($sddl)
    try {
        $principal = [Security.Principal.SecurityIdentifier]::new($d.Principal.UserId)
    } catch {
        $principal = [Security.Principal.NTAccount]::new($d.Principal.UserId).
            Translate([Security.Principal.SecurityIdentifier])
    }
    if ($Task.Name -cne $name -or $Task.Enabled -ne $Enabled -or $s.Enabled -ne $Enabled -or
        $Task.GetInstances(0).Count -ne 0 -or $d.RegistrationInfo.Source -cne $contractSource -or
        $acl.Owner -ne $desiredAcl.Owner -or $acl.Group -ne $desiredAcl.Group -or
        -not ($acl.ControlFlags -band [Security.AccessControl.ControlFlags]::DiscretionaryAclProtected) -or
        $acl.DiscretionaryAcl.Count -ne $desiredAcl.DiscretionaryAcl.Count -or
        $d.RegistrationInfo.Description -cne $description -or $principal.Value -ne $sid -or
        $d.Principal.LogonType -ne 3 -or $d.Principal.RunLevel -ne 0 -or
        $s.StartWhenAvailable -or $s.AllowDemandStart -or -not $s.Hidden -or
        -not $s.AllowHardTerminate -or $s.WakeToRun -or $s.MultipleInstances -ne 2 -or
        $s.ExecutionTimeLimit -ne 'PT14M' -or $d.Triggers.Count -ne 1 -or $d.Actions.Count -ne 1) {
        throw 'NOV27_DEFINITION_READBACK_FAILED'
    }
    for ($i = 0; $i -lt $desiredAcl.DiscretionaryAcl.Count; $i++) {
        $observedAce = $acl.DiscretionaryAcl[$i]
        $expectedAce = $desiredAcl.DiscretionaryAcl[$i]
        if (-not $observedAce.Equals($expectedAce)) { throw 'NOV27_ACL_READBACK_FAILED' }
    }
    $t = $d.Triggers.Item(1)
    $a = $d.Actions.Item(1)
    if ($t.Type -ne 1 -or -not $t.Enabled -or [DateTimeOffset]$t.StartBoundary -ne $start -or
        [DateTimeOffset]$t.EndBoundary -ne $end -or $t.RandomDelay -notin @('', 'PT0S', $null) -or
        $t.Repetition.Interval -or $t.Repetition.Duration -or $a.Type -ne 0 -or $a.Path -cne $python -or
        $a.Arguments -cne $arguments -or $a.WorkingDirectory -cne $source) {
        throw 'NOV27_ACTION_READBACK_FAILED'
    }
}

Assert-FutureWindow
$manifest = Join-Path $source 'SOURCE.json'
if (-not (Test-Path -LiteralPath $python -PathType Leaf) -or
    -not (Test-Path -LiteralPath $launcher -PathType Leaf) -or
    (Get-FileHash -LiteralPath $manifest -Algorithm SHA256).Hash -ine $SourceSha256 -or
    (Test-Path -LiteralPath (Join-Path (Split-Path $source) 'run'))) {
    throw 'NOV27_SOURCE_UNAVAILABLE'
}

$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$sddl = "O:${sid}G:${sid}D:P(A;;FA;;;${sid})(A;;FA;;;SY)(A;;FA;;;BA)"
$service = New-Object -ComObject 'Schedule.Service'
$service.Connect()
$folder = $service.GetFolder('\')
$definition = $service.NewTask(0)
$definition.RegistrationInfo.Source = $contractSource
$definition.RegistrationInfo.Description = $description
$definition.RegistrationInfo.SecurityDescriptor = $sddl
$definition.Principal.UserId = $sid
$definition.Principal.LogonType = 3
$definition.Principal.RunLevel = 0

$settings = $definition.Settings
$settings.Enabled = $false
$settings.Hidden = $true
$settings.StartWhenAvailable = $false
$settings.AllowDemandStart = $false
$settings.AllowHardTerminate = $true
$settings.WakeToRun = $false
$settings.MultipleInstances = 2
$settings.ExecutionTimeLimit = 'PT14M'
$trigger = $definition.Triggers.Create(1)
$trigger.StartBoundary = $start.ToString('yyyy-MM-ddTHH:mm:sszzz')
$trigger.EndBoundary = $end.ToString('yyyy-MM-ddTHH:mm:sszzz')
$trigger.Enabled = $true
$action = $definition.Actions.Create(0)
$action.Path = $python
$action.Arguments = $arguments
$action.WorkingDirectory = $source

if (-not $Install) {
    # TASK_VALIDATE_ONLY does not register or run anything.
    $null = $folder.RegisterTaskDefinition($name, $definition, 1, $sid, $null, 3, $sddl)
    [pscustomobject]@{ status = 'validated_only'; task = $name; starts_utc = $start.UtcDateTime }
    exit 0
}

Assert-FutureWindow
# TASK_CREATE refuses every existing definition; do not add another principal ACE.
$null = $folder.RegisterTaskDefinition($name, $definition, 18, $sid, $null, 3, $sddl)
$created = $folder.GetTask($name)
Assert-Definition $created $false
Assert-FutureWindow
try {
    $created.Enabled = $true
    $armed = $folder.GetTask($name)
    Assert-Definition $armed $true
    if (([DateTimeOffset]$armed.NextRunTime).ToUniversalTime() -ne $start) {
        throw 'NOV27_NEXT_RUN_MISMATCH'
    }
} catch {
    $current = $folder.GetTask($name)
    if ($current.Definition.RegistrationInfo.Source -ceq $contractSource -and
        $current.GetInstances(0).Count -eq 0 -and [DateTimeOffset]::UtcNow -lt $installBy) {
        $current.Enabled = $false
    }
    throw
}
[pscustomobject]@{ status = 'installed_future'; task = $name; starts_utc = $start.UtcDateTime }
