# The protected caller pins this module and owns the leg's durable receipts.
Set-StrictMode -Version Latest

$script:H3ObserverPath = '\thericher-kis-paper-snapshot-observer'
$script:H3ObserverXml = 'e2cbf12f821dd447ecf4a1f3f65498795363a52ecb7a9654e45360498d94d827'
$script:H3ObserverAcl7 = 'fab150776db7652ebf7fe24828069e0637db567357437cf6f93bbb1141f28a04'

function Get-H3ObserverTextHash([string]$Value) {
    return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData(
        [Text.Encoding]::UTF8.GetBytes($Value))).ToLowerInvariant()
}

function Get-H3ObserverSettingsShape([string]$TaskXml, [bool]$Enabled) {
    $settings = [Xml.XmlReaderSettings]::new()
    $settings.DtdProcessing = [Xml.DtdProcessing]::Prohibit
    $settings.XmlResolver = $null
    $settings.MaxCharactersInDocument = 262144
    $document = [Xml.XmlDocument]::new()
    $document.PreserveWhitespace = $true
    $reader = [Xml.XmlReader]::Create([IO.StringReader]::new($TaskXml), $settings)
    try { $document.Load($reader) } finally { $reader.Dispose() }
    $ns = [Xml.XmlNamespaceManager]::new($document.NameTable)
    $ns.AddNamespace('t', 'http://schemas.microsoft.com/windows/2004/02/mit/task')
    $st = $document.SelectNodes('/t:Task/t:Settings', $ns)
    $nodes = $document.SelectNodes('/t:Task/t:Settings/t:Enabled', $ns)
    if ($st.Count -ne 1 -or $nodes.Count -gt 1 -or ($nodes.Count -eq 0 -and -not $Enabled)) {
        throw 'H3_OBSERVER_XML_ENABLED'
    }
    if ($nodes.Count -eq 1) {
        $node = $nodes.Item(0)
        $expected = if ($Enabled) { 'true' } else { 'false' }
        if ($node.Attributes.Count -ne 0 -or $node.ChildNodes.Count -ne 1 -or
            $node.FirstChild.NodeType -ne [Xml.XmlNodeType]::Text -or $node.InnerText -cne $expected) {
            throw 'H3_OBSERVER_XML_ENABLED'
        }
        # Task Scheduler suppresses the default true and inserts false. Drop
        # only that leaf and formatting whitespace between settings elements.
        [void]$st.Item(0).RemoveChild($node)
    }
    foreach ($child in @($st.Item(0).ChildNodes)) {
        if ($child.NodeType -eq [Xml.XmlNodeType]::Whitespace) { [void]$st.Item(0).RemoveChild($child) }
    }
    return Get-H3ObserverTextHash $document.OuterXml
}

function Read-H3ObserverNativeSnapshot($Service, $Folder, [string]$TaskPath, [string]$Acl7, [bool]$ExpectedEnabled) {
    if ($TaskPath -cnotmatch '^\\[A-Za-z0-9-]+$' -or $Acl7 -cnotmatch '^[0-9a-f]{64}$') {
        throw 'H3_OBSERVER_IDENTITY'
    }
    $snapshot = $null
    for ($i = 0; $i -lt 2; $i++) {
        $task = $Folder.GetTask($TaskPath.Substring(1))
        $xml = [string]$task.Xml
        $acl = Get-H3ObserverTextHash ([string]$task.GetSecurityDescriptor(7))
        $last = ([datetime]$task.LastRunTime).ToFileTimeUtc()
        $state = if ($ExpectedEnabled) { 3 } else { 1 }
        if ($TaskPath -cne [string]$task.Path -or $task.Enabled -isnot [bool] -or
            $task.Enabled -ne $ExpectedEnabled -or [int]$task.State -ne $state -or $acl -cne $Acl7) {
            throw 'H3_OBSERVER_NOT_EXACT_IDLE'
        }
        $running = $Service.GetRunningTasks(1)
        if ($null -eq $running) { throw 'H3_OBSERVER_INSTANCES_UNKNOWN' }
        foreach ($instance in $running) {
            if ([string]::IsNullOrWhiteSpace([string]$instance.Path)) { throw 'H3_OBSERVER_INSTANCES_UNKNOWN' }
            if ([string]$instance.Path -ieq $TaskPath) { throw 'H3_OBSERVER_ACTIVE_INSTANCE' }
        }
        $hash = Get-H3ObserverTextHash $xml
        if (($null -ne $snapshot -and ($snapshot.xml_sha256 -cne $hash -or $snapshot.last_run -ne $last)) -or
            $task.Enabled -ne $ExpectedEnabled -or [int]$task.State -ne $state -or
            ([datetime]$task.LastRunTime).ToFileTimeUtc() -ne $last -or
            [string]$task.Xml -cne $xml -or
            (Get-H3ObserverTextHash ([string]$task.GetSecurityDescriptor(7))) -cne $Acl7) {
            throw 'H3_OBSERVER_UNSTABLE'
        }
        $snapshot = @{ task_path=$TaskPath; enabled=$ExpectedEnabled; hidden_inclusive=$true;
            instances=0; xml_sha256=$hash; api7_sha256=$acl;
            shape_sha256=(Get-H3ObserverSettingsShape $xml $ExpectedEnabled); last_run=$last }
    }
    return $snapshot
}

# This primitive does not grant authority. It is intentionally module-private
# until its production caller provides the durable attempt/closure boundary.
function Set-H3ObserverExactEnabled($Service, $Folder, $Previous, [bool]$Enabled, $NotAfter = $null) {
    if ($Previous.enabled -isnot [bool] -or $Previous.enabled -eq $Enabled) {
        throw 'H3_OBSERVER_TRANSITION'
    }
    $current = Read-H3ObserverNativeSnapshot $Service $Folder $Previous.task_path $Previous.api7_sha256 $Previous.enabled
    if ($current.xml_sha256 -cne $Previous.xml_sha256 -or
        $current.shape_sha256 -cne $Previous.shape_sha256 -or $current.last_run -ne $Previous.last_run) {
        throw 'H3_OBSERVER_DRIFT_BEFORE_TRANSITION'
    }
    $task = $Folder.GetTask($Previous.task_path.Substring(1))
    $state = if ($Previous.enabled) { 3 } else { 1 }
    if ([string]$task.Path -cne $Previous.task_path -or $task.Enabled -ne $Previous.enabled -or
        [int]$task.State -ne $state -or ([datetime]$task.LastRunTime).ToFileTimeUtc() -ne $Previous.last_run -or
        $task.Definition.Settings.StartWhenAvailable -isnot [bool] -or $task.Definition.Settings.StartWhenAvailable -or
        (Get-H3ObserverTextHash ([string]$task.Xml)) -cne $Previous.xml_sha256 -or
        (Get-H3ObserverTextHash ([string]$task.GetSecurityDescriptor(7))) -cne $Previous.api7_sha256) {
        throw 'H3_OBSERVER_DRIFT_BEFORE_TRANSITION'
    }
    if ($null -ne $NotAfter -and [DateTimeOffset]::UtcNow -ge $NotAfter) { throw 'H3_OBSERVER_CLOCK' }
    $task.Enabled = $Enabled
    $after = Read-H3ObserverNativeSnapshot $Service $Folder $Previous.task_path $Previous.api7_sha256 $Enabled
    if ($after.shape_sha256 -cne $Previous.shape_sha256 -or $after.last_run -ne $Previous.last_run) {
        throw 'H3_OBSERVER_DRIFT_AFTER_TRANSITION'
    }
    return $after
}

function Get-H3NativeObserverReadiness {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{64}$')][string]$PlanSha256,
        [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{32}$')][string]$RequestId
    )
    $service = New-Object -ComObject 'Schedule.Service'
    $service.Connect()
    $folder = $service.GetFolder('\')
    $sample = Read-H3ObserverNativeSnapshot $service $folder $script:H3ObserverPath $script:H3ObserverAcl7 $true
    if ($sample.xml_sha256 -cne $script:H3ObserverXml) { throw 'H3_OBSERVER_XML_DRIFT' }
    [void]$sample.Remove('shape_sha256')
    [void]$sample.Remove('last_run')
    $sample['schema'] = 'DEC4_H3_OBSERVER_READINESS_V1'
    $sample['status'] = 'EXACT_ORIGINAL_OBSERVER_READINESS'
    $sample['plan_sha256'] = $PlanSha256
    $sample['request_id'] = $RequestId
    $sample['Task_writes'] = 0
    return $sample
}

Export-ModuleMember -Function Get-H3NativeObserverReadiness
