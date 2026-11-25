[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidatePattern('\A\\[^\\/]+\z')][string]$TaskPath,
    [Parameter(Mandatory)][ValidateRange(1, 2147483647)][int]$ExpectedEnginePid,
    [Parameter(Mandatory)][ValidatePattern('\A[0-9a-f]{64}\z')][string]$ExpectedProfileSha256,
    [Parameter(Mandatory)][string]$ProfilePath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$WarningPreference = 'Stop'

function Read-PinnedText([string]$Path, [string]$Sha256, [int]$Limit) {
    if (-not [IO.Path]::IsPathFullyQualified($Path) -or [IO.Path]::GetFullPath($Path) -cne $Path -or
        $Sha256 -cnotmatch '\A[0-9a-f]{64}\z') { throw 'NATIVE_OWNER_MEMBER_PATH' }
    for ($name = $Path; $null -ne $name; $name = [IO.Path]::GetDirectoryName($name)) {
        $item = Get-Item -LiteralPath $name -Force
        if ($item.LinkType -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
            ($name -ceq $Path -and $item.PSIsContainer) -or
            ($name -cne $Path -and -not $item.PSIsContainer)) { throw 'NATIVE_OWNER_MEMBER_LINK' }
    }
    $stream = [IO.File]::Open($Path, 'Open', 'Read', 'Read')
    try {
        if ($stream.Length -lt 1 -or $stream.Length -gt $Limit) { throw 'NATIVE_OWNER_MEMBER_LENGTH' }
        $bytes = [byte[]]::new([int]$stream.Length)
        $stream.ReadExactly($bytes)
        if ([Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant() -cne $Sha256) {
            throw 'NATIVE_OWNER_MEMBER_HASH'
        }
        return [Text.UTF8Encoding]::new($false, $true).GetString($bytes)
    } finally { $stream.Dispose() }
}

try {
    $profile = ConvertFrom-Json -AsHashtable -InputObject (
        Read-PinnedText $ProfilePath $ExpectedProfileSha256 1048576
    )
    $required = @('schema', 'task_path', 'action_sha256', 'export_xml', 'definition_xml', 'acl7',
        'readback_module_sha256', 'registration_module_sha256')
    if ($profile -isnot [Collections.IDictionary] -or $profile.psbase.Count -ne $required.Count -or
        @($profile.psbase.Keys | Where-Object { $_ -cnotin $required }).Count -ne 0 -or
        $profile.schema -cne 'PAPER_NATIVE_OWNER_PROFILE_V1' -or $profile.task_path -cne $TaskPath -or
        $profile.action_sha256 -cnotmatch '\A[0-9a-f]{64}\z' -or
        $profile.acl7 -isnot [string] -or $profile.acl7.Length -lt 1) {
        throw 'NATIVE_OWNER_PROFILE_SCHEMA'
    }
    $registration = Join-Path $PSScriptRoot 'paper_task_registration.psm1'
    $readback = Join-Path $PSScriptRoot 'paper_native_pair_readback.psm1'
    $null = Read-PinnedText $registration $profile.registration_module_sha256 262144
    $null = Read-PinnedText $readback $profile.readback_module_sha256 262144
    $module = Import-Module -Name $readback -Force -PassThru
    $service = New-Object -ComObject 'Schedule.Service'
    $service.Connect()

    $evidence = & $module {
        param($scheduler, $expected, $pidPin, $profilePin)

        $path = $expected.task_path
        $expectedExport = ConvertTo-PaperPairCanonical (Read-PaperPairXml $expected.export_xml)
        $expectedNative = ConvertTo-PaperPairCanonical (Read-PaperPairXml $expected.definition_xml)
        function Read-ExactActiveDefinition {
            $task = Get-PaperLocalRegisteredTask $scheduler $path ${function:Test-PaperLocalScheduler}
            $definition = $task.Definition
            if ($task.State -ne 4 -or $task.Enabled -isnot [bool] -or -not $task.Enabled -or
                (ConvertTo-PaperPairCanonical (Read-PaperPairXml $task.Xml)) -cne $expectedExport -or
                (ConvertTo-PaperPairCanonical (Read-PaperPairXml $definition.XmlText)) -cne $expectedNative -or
                $task.GetSecurityDescriptor(7) -cne $expected.acl7 -or $definition.Actions.Count -ne 1) {
                throw 'NATIVE_OWNER_DEFINITION'
            }
            $action = $definition.Actions.Item(1)
            if ($action.Type -ne 0) { throw 'NATIVE_OWNER_ACTION' }
            $fields = [ordered]@{
                arguments = $action.Arguments
                executable = $action.Path
                working_directory = $action.WorkingDirectory
            }
            foreach ($value in $fields.Values) {
                if ($value -isnot [string] -or $value -cnotmatch '\A[ -~]+\z') { throw 'NATIVE_OWNER_ACTION' }
            }
            $actionJson = ConvertTo-Json -Compress -InputObject $fields
            $actualAction = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData(
                [Text.Encoding]::ASCII.GetBytes($actionJson)
            )).ToLowerInvariant()
            if ($actualAction -cne $expected.action_sha256) { throw 'NATIVE_OWNER_ACTION_HASH' }
            return @{ Task = $task; ActionSha256 = $actualAction }
        }

        $first = Read-ExactActiveDefinition
        $instance = Get-PaperNativeActiveInstance -Scheduler $scheduler -Task $first.Task `
            -ExpectedPath $path -ExpectedEnginePid $pidPin
        $last = Read-ExactActiveDefinition
        if ($instance.Claim -cne 'SCHEDULER_INSTANCE_OBSERVED' -or
            $last.ActionSha256 -cne $first.ActionSha256) { throw 'NATIVE_OWNER_CHANGED' }
        return [ordered]@{
            schema = 'PAPER_NATIVE_OWNER_READBACK_V1'
            task_path = $path
            action_sha256 = $first.ActionSha256
            instance_guid = $instance.InstanceGuid.ToString('D')
            engine_pid = $instance.EnginePid
            profile_sha256 = $profilePin
        }
    } $service $profile $ExpectedEnginePid $ExpectedProfileSha256
    ConvertTo-Json -Compress -InputObject $evidence
} catch {
    # Unknown is not absence. Never emit observed Task XML or native errors.
    exit 20
}
