Set-StrictMode -Version Latest
Import-Module -Name (Join-Path $PSScriptRoot 'paper_native_task_definition.psm1') -Scope Local -ErrorAction Stop

function Copy-PaperFuturePairMapping([System.Collections.IDictionary]$InputMapping) {
    $copy = [Collections.Specialized.OrderedDictionary]::new([StringComparer]::Ordinal)
    foreach ($key in $InputMapping.psbase.Keys) { $copy.Add($key, $InputMapping[$key]) }
    return $copy
}

function Convert-PaperFuturePairUtc($Value) {
    $parsed = [DateTimeOffset]::MinValue
    if ($Value -isnot [string] -or
        $Value -cnotmatch '\A[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,7})?(Z|\+00:00)\z' -or
        -not [DateTimeOffset]::TryParse($Value, [Globalization.CultureInfo]::InvariantCulture,
            [Globalization.DateTimeStyles]::None, [ref]$parsed)) {
        throw 'PAPER_FUTURE_PAIR_UTC'
    }
    return $parsed
}

function Get-PaperFuturePairUtcNow { [DateTimeOffset]::UtcNow }

function Assert-PaperFuturePairDeadline([DateTimeOffset]$Deadline) {
    if ((Get-PaperFuturePairUtcNow) -ge $Deadline) { throw 'PAPER_FUTURE_PAIR_DEADLINE' }
}

function Assert-PaperFuturePairAbsent($Folder, [string]$Name) {
    try { $null = $Folder.GetTask($Name) } catch {
        $cause = $_.Exception.GetBaseException()
        # Exact native file-not-found only; access denied, missing folder and null are not absence.
        if ($cause.HResult -eq -2147024894 -and
            ($cause -is [Runtime.InteropServices.COMException] -or $cause -is [IO.FileNotFoundException])) {
            return
        }
        throw 'PAPER_FUTURE_PAIR_ABSENCE_UNKNOWN'
    }
    throw 'PAPER_FUTURE_PAIR_TARGET_PRESENT'
}

function Read-PaperFuturePairStage($Folder, $Items, $Common, [string]$Stage, [scriptblock]$VerifyReadback) {
    $tasks = @{}
    foreach ($phase in @('exit', 'entry')) {
        $item = $Items[$phase]
        $task = $Folder.GetTask($item.name)
        Assert-PaperNativeRegisteredTaskDefinition @Common -Phase $phase -Stage $Stage -Item $item -Task $task
        $proof = & $VerifyReadback $phase $Stage $task
        if ($proof -isnot [bool] -or -not $proof) { throw 'PAPER_FUTURE_PAIR_FULL_READBACK' }
        $tasks[$phase] = $task
    }
    return $tasks
}

function Install-PaperNativeFuturePair {
    # The caller pins this module and both dependencies, authenticates the exact
    # plan/XML/SDDL/attempt and connected local Scheduler/current SID, and holds
    # exclusive writer ownership of both names through the final readback.
    # The caller qualifies an install deadline with lead for native RPCs before
    # either trigger. The core checks the deadline but cannot time out a COM call.
    # ClaimInstallAttempt atomically consumes only this install identity. It and
    # VerifyReadback must return one Boolean, with no broker/runtime side effects.
    # VerifyReadback(phase, stage, task) checks both complete native XML surfaces,
    # full native API policy, exact GetSecurityDescriptor(7), state and no instances.
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]$Service,
        [Parameter(Mandatory)][System.Collections.IDictionary]$Manifest,
        [Parameter(Mandatory)][System.Collections.IDictionary]$Entry,
        [Parameter(Mandatory)][System.Collections.IDictionary]$Exit,
        [Parameter(Mandatory)][string]$EntryDisabledXml,
        [Parameter(Mandatory)][string]$ExitDisabledXml,
        [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$Sid,
        [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$Sddl,
        [Parameter(Mandatory)][DateTimeOffset]$InstallDeadlineUtc,
        [Parameter(Mandatory)][scriptblock]$PrincipalIdentity,
        [Parameter(Mandatory)][scriptblock]$ClaimInstallAttempt,
        [Parameter(Mandatory)][scriptblock]$VerifyReadback
    )

    $ErrorActionPreference = 'Stop'
    # Keep callback-visible caller maps from changing the names or definition intent mid-install.
    $Manifest = Copy-PaperFuturePairMapping $Manifest
    $Entry = Copy-PaperFuturePairMapping $Entry
    $Exit = Copy-PaperFuturePairMapping $Exit
    $entryStart = Convert-PaperFuturePairUtc $Entry.start_UTC
    $entryEnd = Convert-PaperFuturePairUtc $Entry.last_start_exclusive_UTC
    $exitStart = Convert-PaperFuturePairUtc $Exit.start_UTC
    $exitEnd = Convert-PaperFuturePairUtc $Exit.last_start_exclusive_UTC
    if ($InstallDeadlineUtc.Offset -ne [TimeSpan]::Zero -or $InstallDeadlineUtc -ge $entryStart -or
        $entryStart -ge $entryEnd -or $entryEnd -gt $exitStart -or $exitStart -ge $exitEnd) {
        throw 'PAPER_FUTURE_PAIR_WINDOW'
    }
    Assert-PaperFuturePairDeadline $InstallDeadlineUtc

    $common = @{Manifest = $Manifest; Sid = $Sid; PrincipalIdentity = $PrincipalIdentity}
    $items = @{exit = $Exit; entry = $Entry}
    $templates = @{exit = $ExitDisabledXml; entry = $EntryDisabledXml}
    $definitions = @{}
    foreach ($phase in @('exit', 'entry')) {
        $definitions[$phase] = New-PaperNativeTaskDefinition @common -Phase $phase -Stage 'DISABLED' `
            -Item $items[$phase] -Service $Service -BaseXml $templates[$phase]
    }
    $folder = $Service.GetFolder('\')
    if ($folder.Path -cne '\') { throw 'PAPER_FUTURE_PAIR_ROOT' }
    Assert-PaperFuturePairAbsent $folder $Exit.name
    Assert-PaperFuturePairAbsent $folder $Entry.name
    Assert-PaperFuturePairDeadline $InstallDeadlineUtc
    $claimed = & $ClaimInstallAttempt
    if ($claimed -isnot [bool] -or -not $claimed) { throw 'PAPER_FUTURE_PAIR_ATTEMPT' }

    # CREATE | DISABLE | DONT_ADD_PRINCIPAL_ACE | IGNORE_REGISTRATION_TRIGGERS.
    # No update, delete, rollback or retry, including after an unknown result.
    foreach ($phase in @('exit', 'entry')) {
        Assert-PaperFuturePairDeadline $InstallDeadlineUtc
        $null = $folder.RegisterTaskDefinition($items[$phase].name, $definitions[$phase], 0x3A, $Sid, $null, 3, $Sddl)
    }
    $tasks = Read-PaperFuturePairStage $folder $items $common 'DISABLED' $VerifyReadback
    Assert-PaperFuturePairDeadline $InstallDeadlineUtc
    $tasks['exit'].Enabled = $true

    $tasks = Read-PaperFuturePairStage $folder $items $common 'EXIT_ONLY' $VerifyReadback
    Assert-PaperFuturePairDeadline $InstallDeadlineUtc
    $tasks['entry'].Enabled = $true

    $null = Read-PaperFuturePairStage $folder $items $common 'ENABLED' $VerifyReadback
    Assert-PaperFuturePairDeadline $InstallDeadlineUtc
    return 'PAPER_FUTURE_PAIR_INSTALLED'
}

Export-ModuleMember -Function Install-PaperNativeFuturePair
