[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(Mandatory)][string]$ProfilePath,
    [Parameter(Mandatory)][string]$ProfileSha256
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$PSModuleAutoLoadingPreference = 'None'

function Get-ExactJsonFields($Element, [string[]]$Names) {
    if ($Element.ValueKind -ne [Text.Json.JsonValueKind]::Object) { throw 'PROFILE_OBJECT' }
    $fields = [Collections.Generic.Dictionary[string, Text.Json.JsonElement]]::new([StringComparer]::Ordinal)
    foreach ($property in $Element.EnumerateObject()) {
        $fields.Add($property.Name, $property.Value)  # Also rejects duplicate JSON keys.
    }
    if ($fields.Count -ne $Names.Count) { throw 'PROFILE_FIELDS' }
    foreach ($name in $Names) {
        if (-not $fields.ContainsKey($name)) { throw 'PROFILE_FIELD' }
    }
    return $fields
}

function Get-JsonString($Field) {
    if ($Field.ValueKind -ne [Text.Json.JsonValueKind]::String) { throw 'PROFILE_STRING' }
    return $Field.GetString()
}

function Test-LocalConnection($Service) {
    $comparison = [StringComparison]::OrdinalIgnoreCase
    return ($Service.Connected -is [bool] -and $Service.Connected -and
        [string]::Equals($Service.TargetServer, [Environment]::MachineName, $comparison) -and
        [string]::Equals($Service.ConnectedUser, [Environment]::UserName, $comparison) -and
        [string]::Equals($Service.ConnectedDomain, [Environment]::UserDomainName, $comparison))
}

function Assert-NoRunningWriters($Service, $Paths) {
    if (-not (Test-LocalConnection $Service)) { throw 'SCHEDULER_CONNECTION' }
    $running = $Service.GetRunningTasks(1)  # TASK_ENUM_HIDDEN
    if ($null -eq $running -or (-not [Runtime.InteropServices.Marshal]::IsComObject($running) -and
        $null -eq $running.PSObject.Properties['Count'])) { throw 'SCHEDULER_COLLECTION' }
    $count = $running.Count
    if ($count -isnot [int] -or $count -lt 0 -or $count -gt 4096) { throw 'SCHEDULER_COUNT' }
    for ($i = 1; $i -le $count; $i++) {
        $path = $running.Item($i).Path
        if ($path -isnot [string] -or $path -cnotmatch '\A(?:\\[^\\/\x00-\x1f]+)+\z' -or
            $Paths.Contains($path)) { throw 'SCHEDULER_MEMBERSHIP' }
    }
    $after = $running.Count
    if ($after -isnot [int] -or $after -ne $count -or -not (Test-LocalConnection $Service)) {
        throw 'SCHEDULER_MEMBERSHIP_CHANGED'
    }
}

function Assert-ExactDisabledTasks($Service, $Rows, [Text.UTF8Encoding]$Encoding) {
    if (-not (Test-LocalConnection $Service)) { throw 'SCHEDULER_CONNECTION' }
    $folder = $Service.GetFolder('\')
    if (-not [string]::Equals($folder.Path, '\', [StringComparison]::Ordinal)) { throw 'SCHEDULER_ROOT' }
    foreach ($row in $Rows) {
        $task = $folder.GetTask($row.Path.Substring(1))
        $state = $task.State
        $enabled = $task.Enabled
        if (-not [string]::Equals($task.Path, $row.Path, [StringComparison]::Ordinal) -or
            $state -isnot [int] -or $state -ne 1 -or $enabled -isnot [bool] -or $enabled) {
            throw 'SCHEDULER_DISABLED_TASK'
        }
        # Hash the exact COM strings as UTF-8, without a BOM or XML normalization.
        $surfaces = @($task.Xml, $task.Definition.XmlText, $task.GetSecurityDescriptor(7))
        for ($i = 0; $i -lt $surfaces.Count; $i++) {
            $value = $surfaces[$i]
            if ($value -isnot [string] -or [string]::IsNullOrWhiteSpace($value) -or
                [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($Encoding.GetBytes($value))).ToLowerInvariant() `
                    -cne $row.Hashes[$i]) { throw 'SCHEDULER_READBACK' }
        }
    }
}

try {
    Import-Module Microsoft.PowerShell.Utility -ErrorAction Stop
    if ($ProfileSha256 -cnotmatch '\A[0-9a-f]{64}\z' -or -not [IO.Path]::IsPathFullyQualified($ProfilePath) -or
        -not [string]::Equals([IO.Path]::GetFullPath($ProfilePath), $ProfilePath, [StringComparison]::Ordinal)) {
        throw 'PROFILE_IDENTITY'
    }
    $profileFile = [IO.File]::Open($ProfilePath, 'Open', 'Read', 'Read')
    try {
        if ($profileFile.Length -lt 1 -or $profileFile.Length -gt 1048576) { throw 'PROFILE_LENGTH' }
        $bytes = [byte[]]::new([int]$profileFile.Length)
        $profileFile.ReadExactly($bytes)
        if ([Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant() -cne $ProfileSha256) {
            throw 'PROFILE_HASH'
        }
        $utf8 = [Text.UTF8Encoding]::new($false, $true)
        $document = [Text.Json.JsonDocument]::Parse($utf8.GetString($bytes), [Text.Json.JsonDocumentOptions]::new())
        $paths = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        $rows = [Collections.Generic.List[object]]::new()
        try {
            $fields = Get-ExactJsonFields $document.RootElement @('schema', 'tasks')
            if (-not [string]::Equals((Get-JsonString $fields['schema']), 'h3-restore-retired-writers-v1', [StringComparison]::Ordinal) -or
                $fields['tasks'].ValueKind -ne [Text.Json.JsonValueKind]::Array -or $fields['tasks'].GetArrayLength() -eq 0) {
                throw 'PROFILE_SCHEMA'
            }
            foreach ($element in $fields['tasks'].EnumerateArray()) {
                $row = Get-ExactJsonFields $element @('path', 'export_sha256', 'definition_sha256', 'api7_sha256')
                $path = Get-JsonString $row['path']
                if ($path -cnotmatch '\A\\thericher-[A-Za-z0-9][A-Za-z0-9_-]*\z' -or -not $paths.Add($path)) {
                    throw 'PROFILE_TASK_PATH'
                }
                $hashes = @(foreach ($key in @('export_sha256', 'definition_sha256', 'api7_sha256')) {
                    $hash = Get-JsonString $row[$key]
                    if ($hash -cnotmatch '\A[0-9a-f]{64}\z') { throw 'PROFILE_TASK_HASH' }
                    $hash
                })
                $rows.Add(@{ Path = $path; Hashes = $hashes })
            }
        } finally { $document.Dispose() }

        $service = New-Object -ComObject 'Schedule.Service'
        $null = $service.Connect()
        # Bracket both exact registered readbacks. Samples do not hold exclusion.
        Assert-NoRunningWriters $service $paths
        for ($i = 0; $i -lt 2; $i++) {
            Assert-ExactDisabledTasks $service $rows $utf8
            Assert-NoRunningWriters $service $paths
        }
    } finally { $profileFile.Dispose() }

    [Console]::WriteLine(('{{"schema":"h3-restore-retired-writers-proof-v1","profile_sha256":"{0}","retired":true}}' -f $ProfileSha256))
} catch {
    [Console]::Error.WriteLine('H3_RESTORE_RETIRED_WRITERS_UNAVAILABLE')
    exit 1
}
