# Installer readback only. Pin this module and paper_task_registration.psm1.
# The caller authenticates the plan and supplies separately pinned, complete
# XML for each native surface at each stage, plus the expected ACL7 text.
# Neither observed task XML nor the registration SDDL is a source of authority.
Set-StrictMode -Version Latest
Import-Module -Name (Join-Path $PSScriptRoot 'paper_task_registration.psm1') -Scope Local -ErrorAction Stop

function Read-PaperPairXml($Xml) {
    if ($Xml -isnot [string] -or $Xml.Length -eq 0 -or $Xml.Length -gt 262144) {
        throw 'PAPER_PAIR_READBACK_XML'
    }
    $settings = [Xml.XmlReaderSettings]::new()
    $settings.DtdProcessing = [Xml.DtdProcessing]::Prohibit
    $settings.XmlResolver = $null
    $settings.CloseInput = $true
    $reader = [Xml.XmlReader]::Create([IO.StringReader]::new($Xml), $settings)
    try {
        $document = [Xml.XmlDocument]::new()
        $document.PreserveWhitespace = $true
        $document.XmlResolver = $null
        $document.Load($reader)
    } finally {
        $reader.Dispose()
    }
    $root = $document.DocumentElement.psbase
    if ($root.LocalName -cne 'Task' -or $root.NamespaceURI -cne 'http://schemas.microsoft.com/windows/2004/02/mit/task' -or
        $document.SelectSingleNode(('/*' * 33))) {
        throw 'PAPER_PAIR_READBACK_XML'
    }
    return ,$document
}

function ConvertTo-PaperPairCanonical([Xml.XmlDocument]$Document) {
    # Ignore layout only in element-only containers. Never trim a value, drop
    # a node/attribute/default, or translate a clock, principal or action.
    foreach ($parent in $Document.SelectNodes('//*[*]')) {
        $layout = @($parent.psbase.ChildNodes | Where-Object { $_ -is [Xml.XmlWhitespace] })
        if ($layout.Count -eq 0 -or $parent.psbase.ChildNodes.Count -ne
            ($layout.Count + $parent.SelectNodes('*').Count)) { continue }
        foreach ($node in $layout) { $null = $parent.RemoveChild($node) }
    }
    $canonical = [Security.Cryptography.Xml.XmlDsigC14NWithCommentsTransform]::new()
    $canonical.LoadInput($Document)
    $stream = $canonical.GetOutput([IO.Stream])
    try {
        $reader = [IO.StreamReader]::new($stream)
        try { return $reader.ReadToEnd() } finally { $reader.Dispose() }
    } finally {
        $stream.Dispose()
    }
}

function Test-PaperPairStageReadback($Task, $Expected) {
    $ErrorActionPreference = 'Stop'
    try {
        $state = $Task.State
        $enabled = $Task.Enabled
        if ($state -isnot [int] -or $state -ne $Expected.State -or $enabled -isnot [bool] -or
            $enabled -ne $Expected.Enabled -or
            -not [string]::Equals($Task.Name, $Expected.Name, [StringComparison]::Ordinal) -or
            -not [string]::Equals($Task.Path, $Expected.Path, [StringComparison]::Ordinal)) { return $false }

        $export = ConvertTo-PaperPairCanonical (Read-PaperPairXml $Task.Xml)
        $native = ConvertTo-PaperPairCanonical (Read-PaperPairXml $Task.Definition.XmlText)
        if (-not [string]::Equals($export, $Expected.ExportXml, [StringComparison]::Ordinal) -or
            -not [string]::Equals($native, $Expected.DefinitionXml, [StringComparison]::Ordinal)) { return $false }
        $acl = $Task.GetSecurityDescriptor(7)
        if ($acl -isnot [string] -or -not [string]::Equals($acl, $Expected.Acl, [StringComparison]::Ordinal)) {
            return $false
        }
        $instances = $Task.GetInstances(0)
        if ($null -eq $instances -or (-not [Runtime.InteropServices.Marshal]::IsComObject($instances) -and
            $null -eq $instances.PSObject.Properties['Count'])) { return $false }
        $count = $instances.Count
        return ($count -is [int] -and $count -eq 0)
    } catch {
        # Native/parse failures are unknown, never a positive readback. Do not
        # expose native exceptions or observed definition/descriptor contents.
        return $false
    }
}

function New-PaperNativePairReadback {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][System.Collections.IDictionary]$Manifest,
        [Parameter(Mandatory)][System.Collections.IDictionary]$ExpectedStageXml,
        [Parameter(Mandatory)][string]$EntryAcl7,
        [Parameter(Mandatory)][string]$ExitAcl7
    )

    $ErrorActionPreference = 'Stop'
    $expectedByStage = @{}
    try {
        $aclByPhase = @{ entry = $EntryAcl7; exit = $ExitAcl7 }
        $stageNames = @('DISABLED', 'EXIT_ONLY', 'ENABLED')
        $phases = @('entry', 'exit')
        $keys = @($ExpectedStageXml.psbase.Keys)
        $requiredKeys = @(foreach ($stage in $stageNames) { foreach ($phase in $phases) { "${stage}:$phase" } })
        if ($keys.Count -ne $requiredKeys.Count -or @($keys | Where-Object { $_ -cnotin $requiredKeys }).Count) {
            throw 'PAPER_PAIR_READBACK_STAGES'
        }
        foreach ($phase in $phases) {
            $acl = [Security.AccessControl.RawSecurityDescriptor]::new($aclByPhase[$phase])
            if ($null -eq $acl.Owner -or $null -eq $acl.Group -or $null -eq $acl.DiscretionaryAcl) {
                throw 'PAPER_PAIR_READBACK_ACL7'
            }
        }
        foreach ($stage in $stageNames) {
            foreach ($row in (Get-PaperTaskRegistrationPair -Manifest $Manifest -Stage $stage)) {
                $phase = if ($row.Role -ceq 'ENTRY') { 'entry' } else { 'exit' }
                $pin = $ExpectedStageXml["${stage}:$phase"]
                $fields = @('ExportXml', 'DefinitionXml')
                if ($pin -isnot [System.Collections.IDictionary] -or $pin.psbase.Keys.Count -ne 2 -or
                    @($pin.psbase.Keys | Where-Object { $_ -cnotin $fields }).Count) {
                    throw 'PAPER_PAIR_READBACK_SURFACES'
                }
                $xml = @{}
                foreach ($field in $fields) {
                    $document = Read-PaperPairXml $pin[$field]
                    Assert-PaperTaskRegistrationXml -Manifest $Manifest -Stage $stage -Role $row.Role `
                        -TaskName $row.Name -Xml $pin[$field] -AllowEnabledExportDefault:($row.Enabled -and $field -ceq 'ExportXml')
                    $xml[$field] = ConvertTo-PaperPairCanonical $document
                }
                $expectedByStage["${stage}:$phase"] = @{
                    Name = $row.Name; Path = '\' + $row.Name; Enabled = $row.Enabled
                    State = $(if ($row.Enabled) { 3 } else { 1 })  # Ready / Disabled
                    ExportXml = $xml.ExportXml; DefinitionXml = $xml.DefinitionXml; Acl = $aclByPhase[$phase]
                }
            }
        }
    } catch {
        throw 'PAPER_PAIR_READBACK_EXPECTATION'
    }

    # Capture the frozen expectations and module-bound verifier; the returned
    # block implements Install-PaperNativeFuturePair's (phase, stage, task) ABI.
    $verify = ${function:Test-PaperPairStageReadback}
    return {
        param($phase, $stage, $task)
        if ($phase -isnot [string] -or $phase -cnotin @('entry', 'exit') -or
            $stage -isnot [string] -or $stage -cnotin @('DISABLED', 'EXIT_ONLY', 'ENABLED')) { return $false }
        & $verify $task $expectedByStage["${stage}:$phase"]
    }.GetNewClosure()
}

function New-PaperNativeProtectedProfile {
    # This profile is qualified against local Scheduler 1.4 inert tasks only.
    # Inputs are unregistered COM definitions. The installer still resolves
    # the same SID against the current principal with its native API check.
    param(
        [Parameter(Mandatory)][System.Collections.IDictionary]$Manifest,
        [Parameter(Mandatory)][string]$EntryDraftXml,
        [Parameter(Mandatory)][string]$ExitDraftXml,
        [Parameter(Mandatory)][string]$Sid
    )
    if ($Sid -cnotmatch '\AS-1-5-21-(?:[0-9]+-){3}[0-9]+\z') { throw 'PAPER_PROFILE_OWNER_SID' }
    $aclTail = "(A;;FA;;;$Sid)(A;;FA;;;SY)(A;;FA;;;BA)"
    $registrationSddl = "O:${Sid}G:${Sid}D:P$aclTail"
    $acl7 = "O:${Sid}G:${Sid}D:PAI$aclTail"
    $draftByPhase = @{ entry = $EntryDraftXml; exit = $ExitDraftXml }
    $defaults = [ordered]@{
        'Triggers/TimeTrigger/Enabled' = 'true'
        'Principals/Principal/RunLevel' = 'LeastPrivilege'
        'Settings/AllowHardTerminate' = 'true'
        'Settings/StartWhenAvailable' = 'false'
        'Settings/RunOnlyIfNetworkAvailable' = 'false'
        'Settings/RunOnlyIfIdle' = 'false'
        'Settings/DisallowStartOnRemoteAppSession' = 'false'
        'Settings/WakeToRun' = 'false'
        'Settings/Priority' = '7'
    }
    $stageXml = @{}
    foreach ($stage in @('DISABLED', 'EXIT_ONLY', 'ENABLED')) {
        foreach ($row in (Get-PaperTaskRegistrationPair -Manifest $Manifest -Stage $stage)) {
            $phase = if ($row.Role -ceq 'ENTRY') { 'entry' } else { 'exit' }
            $doc = Read-PaperPairXml $draftByPhase[$phase]
            $root = $doc.DocumentElement.psbase
            if ($root.GetAttribute('version') -cne '1.4') { throw 'PAPER_PROFILE_SCHEMA_VERSION' }
            $ns = [Xml.XmlNamespaceManager]::new($doc.NameTable)
            $ns.AddNamespace('t', $root.NamespaceURI)
            $principals = $doc.SelectNodes('/t:Task/t:Principals/t:Principal', $ns)
            if ($principals.Count -ne 1) { throw 'PAPER_PROFILE_OWNER_PRINCIPAL' }
            $userIds = $principals[0].SelectNodes('t:UserId', $ns)
            if ($userIds.Count -ne 1 -or $userIds[0].psbase.InnerText -cne $Sid -or
                $principals[0].SelectNodes('t:GroupId', $ns).Count) { throw 'PAPER_PROFILE_OWNER_PRINCIPAL' }
            $info = $doc.SelectSingleNode('/t:Task/t:RegistrationInfo', $ns)
            if ($info.SelectSingleNode('t:URI', $ns)) { throw 'PAPER_PROFILE_NOT_A_DRAFT' }
            $securityNodes = $info.SelectNodes('t:SecurityDescriptor', $ns)
            if ($securityNodes.Count -ne 1 -or $securityNodes[0].psbase.InnerText -cne $registrationSddl) {
                throw 'PAPER_PROFILE_EXPLICIT_DRAFT_SECURITY_REQUIRED'
            }
            $security = $securityNodes[0]
            $uri = $doc.CreateElement('URI', $root.NamespaceURI)
            $uri.InnerText = '\' + $row.Name
            $null = $info.InsertBefore($uri, $security)
            $enabled = $doc.SelectSingleNode('/t:Task/t:Settings/t:Enabled', $ns)
            if ($enabled.psbase.InnerText -cne 'false') { throw 'PAPER_PROFILE_NOT_DISABLED_DRAFT' }
            foreach ($field in @('StartBoundary', 'EndBoundary')) {
                $boundary = $doc.SelectSingleNode("/t:Task/t:Triggers/t:TimeTrigger/t:$field", $ns).psbase
                if ($boundary.InnerText -cnotmatch '\A[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(Z|\+00:00)\z') {
                    throw 'PAPER_PROFILE_DRAFT_CLOCK'
                }
                $local = [TimeZoneInfo]::ConvertTime([DateTimeOffset]$boundary.InnerText, [TimeZoneInfo]::Local)
                $boundary.InnerText = $local.ToString('yyyy-MM-ddTHH:mm:sszzz', [Globalization.CultureInfo]::InvariantCulture)
            }
            if ($row.Enabled) { $enabled.psbase.InnerText = 'true' }
            $definitionXml = $doc.OuterXml
            foreach ($leaf in $defaults.Keys) {
                $xpath = '/t:Task/t:' + $leaf.Replace('/', '/t:')
                $nodes = $doc.SelectNodes($xpath, $ns)
                if ($nodes.Count -ne 1 -or $nodes[0].psbase.InnerText -cne $defaults[$leaf]) {
                    throw 'PAPER_PROFILE_UNEXPECTED_DEFAULT'
                }
                $null = $nodes[0].psbase.ParentNode.RemoveChild($nodes[0])
            }
            if ($row.Enabled) { $null = $enabled.psbase.ParentNode.RemoveChild($enabled) }
            $security = $info.SelectSingleNode('t:SecurityDescriptor', $ns)
            $null = $info.PrependChild($security)
            $settings = $doc.SelectSingleNode('/t:Task/t:Settings', $ns)
            $exportOrder = @('AllowStartOnDemand', 'DisallowStartIfOnBatteries', 'StopIfGoingOnBatteries')
            if (-not $row.Enabled) { $exportOrder += 'Enabled' }
            $exportOrder += @('ExecutionTimeLimit', 'Hidden', 'MultipleInstancesPolicy', 'IdleSettings', 'UseUnifiedSchedulingEngine')
            if ($settings.SelectNodes('*').Count -ne $exportOrder.Count) { throw 'PAPER_PROFILE_EXPORT_SHAPE' }
            foreach ($field in $exportOrder) {
                $nodes = $settings.SelectNodes("t:$field", $ns)
                if ($nodes.Count -ne 1) { throw 'PAPER_PROFILE_EXPORT_SHAPE' }
                $null = $settings.AppendChild($nodes[0])
            }
            $documentOrder = @('RegistrationInfo', 'Principals', 'Settings', 'Triggers', 'Actions')
            if ($root.SelectNodes('*').Count -ne $documentOrder.Count) { throw 'PAPER_PROFILE_EXPORT_SHAPE' }
            foreach ($field in $documentOrder) {
                $nodes = $root.SelectNodes("t:$field", $ns)
                if ($nodes.Count -ne 1) { throw 'PAPER_PROFILE_EXPORT_SHAPE' }
                $null = $root.AppendChild($nodes[0])
            }
            $stageXml["${stage}:$phase"] = @{ ExportXml = $doc.OuterXml; DefinitionXml = $definitionXml }
        }
    }
    $readback = New-PaperNativePairReadback -Manifest $Manifest -ExpectedStageXml $stageXml `
        -EntryAcl7 $acl7 -ExitAcl7 $acl7
    return @{ RegistrationSddl = $registrationSddl; VerifyReadback = $readback }
}

Export-ModuleMember -Function New-PaperNativePairReadback, New-PaperNativeProtectedProfile
