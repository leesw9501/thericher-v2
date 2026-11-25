# Both successor consumers must pin this module and its sibling before import.
# Inputs come from the authenticated phase plan, never from observed task data.
# This module has no registration, enablement, ACL or owner-admission authority.
Set-StrictMode -Version Latest
Import-Module -Name (Join-Path $PSScriptRoot 'paper_task_registration.psm1') -Scope Local -ErrorAction Stop

function Get-NativePaperTaskExpected($Manifest, [string]$Phase, [string]$Stage, $Item) {
    $role = switch -CaseSensitive ($Phase) {
        'entry' { 'ENTRY' }
        'exit' { 'ORIGINAL_EXIT' }
        default { throw 'PAPER_NATIVE_PHASE' }
    }
    $pair = @(Get-PaperTaskRegistrationPair -Manifest $Manifest -Stage $Stage)
    $registration = if ($role -ceq 'ENTRY') { $pair[1] } else { $pair[0] }
    if ($registration.Role -cne $role -or $Item.role -cne $role -or $Item.name -cne $registration.Name) {
        throw 'PAPER_NATIVE_PLAN_ROLE_NAME'
    }
    $expected = @{
        Role = $role; Name = $registration.Name; Enabled = $registration.Enabled
        Source = $registration.Source; Description = $registration.Description
    }
    foreach ($field in @('executable', 'arguments', 'working_directory', 'start_UTC',
            'last_start_exclusive_UTC', 'execution_time_limit')) {
        $value = $Item.$field
        if ($value -isnot [string] -or [string]::IsNullOrWhiteSpace($value)) { throw 'PAPER_NATIVE_PLAN_FIELD' }
        $expected[$field] = $value
    }
    return $expected
}

function Assert-NativePaperDefinitionApi($Definition, $Expected, [string]$Sid, [scriptblock]$PrincipalIdentity) {
    $info = $Definition.RegistrationInfo
    if ($info.Source -cne $Expected.Source -or $info.Description -cne $Expected.Description) {
        throw 'PAPER_NATIVE_REGISTRATION_API'
    }
    if ($Definition.Actions.Count -ne 1 -or $Definition.Triggers.Count -ne 1) {
        throw 'PAPER_NATIVE_ONE_ACTION_TRIGGER'
    }
    $action = $Definition.Actions.Item(1)
    $trigger = $Definition.Triggers.Item(1)
    if ($action.Type -ne 0 -or $action.Path -cne $Expected.executable -or
        $action.Arguments -cne $Expected.arguments -or $action.WorkingDirectory -cne $Expected.working_directory) {
        throw 'PAPER_NATIVE_ACTION_API'
    }
    try {
        $start = [DateTimeOffset]$trigger.StartBoundary
        $end = [DateTimeOffset]$trigger.EndBoundary
        $windowMatches = ($start -eq [DateTimeOffset]$Expected.start_UTC -and
            $end -eq [DateTimeOffset]$Expected.last_start_exclusive_UTC -and $start -lt $end)
    } catch { throw 'PAPER_NATIVE_TRIGGER_CLOCK' }
    if ($trigger.Type -ne 1 -or $trigger.Enabled -isnot [bool] -or -not $trigger.Enabled -or
        -not $windowMatches -or $null -eq $trigger.Repetition -or
        $trigger.Repetition.Interval -or $trigger.Repetition.Duration) {
        throw 'PAPER_NATIVE_TRIGGER_API'
    }
    $principal = $Definition.Principal
    if ([string]::IsNullOrWhiteSpace($principal.UserId) -or $principal.LogonType -ne 3 -or $principal.RunLevel -ne 0) {
        throw 'PAPER_NATIVE_PRINCIPAL_API'
    }
    # Use the caller's pinned native current/declared SID resolver, not string equality.
    $identity = & $PrincipalIdentity ([string]$principal.UserId) $Sid
    if ($identity -isnot [System.Collections.IDictionary] -or
        $identity['resolved_equals_declared'] -isnot [bool] -or -not $identity['resolved_equals_declared'] -or
        $identity['resolved_equals_current'] -isnot [bool] -or -not $identity['resolved_equals_current']) {
        throw 'PAPER_NATIVE_PRINCIPAL_IDENTITY'
    }
    $settings = $Definition.Settings
    $flags = @{
        Enabled = $Expected.Enabled; AllowDemandStart = $false; StartWhenAvailable = $false
        Hidden = $true; WakeToRun = $false; UseUnifiedSchedulingEngine = $true
    }
    foreach ($field in $flags.Keys) {
        $value = $settings.$field
        if ($value -isnot [bool] -or $value -ne $flags[$field]) { throw 'PAPER_NATIVE_SETTINGS_API' }
    }
    if ($settings.ExecutionTimeLimit -cne $Expected.execution_time_limit -or $settings.MultipleInstances -ne 2) {
        throw 'PAPER_NATIVE_SETTINGS_API'
    }
}

function New-PaperNativeTaskDefinition {
    param(
        [Parameter(Mandatory)]$Service,
        [Parameter(Mandatory)][System.Collections.IDictionary]$Manifest,
        [Parameter(Mandatory)][string]$Phase,
        [Parameter(Mandatory)][string]$Stage,
        [Parameter(Mandatory)]$Item,
        [Parameter(Mandatory)][string]$Sid,
        [Parameter(Mandatory)][scriptblock]$PrincipalIdentity,
        [Parameter(Mandatory)][string]$BaseXml
    )
    # Installer creation uses DISABLED; the owner builds its canonical expected
    # definition at ENABLED. Base XML already includes the unified-engine setting.
    $expected = Get-NativePaperTaskExpected $Manifest $Phase $Stage $Item
    $registration = @{Manifest = $Manifest; Stage = $Stage; Role = $expected.Role; TaskName = $expected.Name}
    $stamped = Set-PaperTaskRegistrationXml @registration -Xml $BaseXml
    $definition = $Service.NewTask(0)
    $definition.XmlText = $stamped
    Assert-PaperTaskRegistrationXml @registration -Xml ([string]$definition.XmlText)
    Assert-NativePaperDefinitionApi $definition $expected $Sid $PrincipalIdentity
    return $definition
}

function Assert-PaperNativeRegisteredTaskDefinition {
    param(
        [Parameter(Mandatory)]$Task,
        [Parameter(Mandatory)][System.Collections.IDictionary]$Manifest,
        [Parameter(Mandatory)][string]$Phase,
        [Parameter(Mandatory)][string]$Stage,
        [Parameter(Mandatory)]$Item,
        [Parameter(Mandatory)][string]$Sid,
        [Parameter(Mandatory)][scriptblock]$PrincipalIdentity
    )
    $expected = Get-NativePaperTaskExpected $Manifest $Phase $Stage $Item
    if ($Task.Name -cne $expected.Name -or $Task.Path -cne ('\' + $expected.Name) -or
        $Task.Enabled -isnot [bool] -or $Task.Enabled -ne $expected.Enabled) {
        throw 'PAPER_NATIVE_REGISTERED_TARGET'
    }
    $registration = @{Manifest = $Manifest; Stage = $Stage; Role = $expected.Role; TaskName = $expected.Name}
    # Read both native surfaces directly. Never stamp or repair observed XML.
    # Registered export omits a true Settings.Enabled on this host. The state
    # above, native definition below and complete readback still have to agree.
    Assert-PaperTaskRegistrationXml @registration -Xml ([string]$Task.Xml) -AllowEnabledExportDefault
    $definition = $Task.Definition
    Assert-PaperTaskRegistrationXml @registration -Xml ([string]$definition.XmlText)
    Assert-NativePaperDefinitionApi $definition $expected $Sid $PrincipalIdentity
    # Callers still enforce full canonical XML, exact native ACL7 and stage-
    # appropriate state/instances (including runtime PID/birth/argv lineage).
}

Export-ModuleMember -Function New-PaperNativeTaskDefinition, Assert-PaperNativeRegisteredTaskDefinition
