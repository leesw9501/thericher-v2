# Successor Paper pair only. Both consumers must source-pin this module and
# authenticate the manifest and its runtime source/release and pair-name joins
# before use. Pass the dedicated five-field mapping, not the enclosing manifest.
# Parse it without collapsing duplicate keys before validating this mapping.
# This is not a Scheduler client or a substitute for full XML/API/ACL proof.

function Get-PaperTaskRegistrationPair {
    param(
        [Parameter(Mandatory)][System.Collections.IDictionary]$Manifest,
        [Parameter(Mandatory)][string]$Stage
    )

    $keys = @('schema', 'runtime_source_sha256', 'runtime_release_sha256', 'entry_name', 'exit_name')
    $actualKeys = @($Manifest.psbase.Keys)
    if ($actualKeys.Count -ne $keys.Count) { throw 'PAPER_TASK_MANIFEST_FIELDS' }
    foreach ($key in $actualKeys) {
        if ($key -isnot [string] -or $key -cnotin $keys -or $Manifest[$key] -isnot [string]) {
            throw 'PAPER_TASK_MANIFEST_FIELDS'
        }
    }
    if ($Manifest['schema'] -cne 'PAPER_TASK_REGISTRATION_V1') { throw 'PAPER_TASK_MANIFEST_SCHEMA' }
    foreach ($key in @('runtime_source_sha256', 'runtime_release_sha256')) {
        if ($Manifest[$key] -cnotmatch '\A[0-9a-f]{64}\z') { throw 'PAPER_TASK_MANIFEST_DIGEST' }
    }
    $entry = $Manifest['entry_name']
    $exit = $Manifest['exit_name']
    if ($entry -cnotmatch '\A[A-Za-z0-9_-]{1,160}\z' -or $exit -cnotmatch '\A[A-Za-z0-9_-]{1,160}\z' -or
        [string]::Equals($entry, $exit, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'PAPER_TASK_MANIFEST_NAMES'
    }
    if ($Stage -cnotin @('DISABLED', 'EXIT_ONLY', 'ENABLED')) { throw 'PAPER_TASK_PAIR_STAGE' }

    $source = 'thericher-paper-owner:{0}:{1}' -f $Manifest['runtime_source_sha256'], $Manifest['runtime_release_sha256']
    foreach ($role in @('ORIGINAL_EXIT', 'ENTRY')) {
        $name = if ($role -ceq 'ENTRY') { $entry } else { $exit }
        [pscustomobject]@{
            Role = $role
            Name = $name
            Enabled = ($Stage -ceq 'ENABLED' -or ($Stage -ceq 'EXIT_ONLY' -and $role -ceq 'ORIGINAL_EXIT'))
            Description = "TheRicher finite Paper owner $role ($name); no demand/catchup/repeat"
            Source = $source
        }
    }
}

function Get-PaperTaskRegistrationExpected($Manifest, [string]$Stage, [string]$Role, [string]$TaskName) {
    $pair = @(Get-PaperTaskRegistrationPair -Manifest $Manifest -Stage $Stage)
    foreach ($row in $pair) {
        if ($row.Role -ceq $Role -and $row.Name -ceq $TaskName) { return $row }
    }
    throw 'PAPER_TASK_ROLE_NAME'
}

function Get-PaperTaskXmlChild([Xml.XmlElement]$Parent, [string]$Name, [bool]$Required) {
    $found = $null
    foreach ($child in $Parent.ChildNodes) {
        if ($child -isnot [Xml.XmlElement] -or $child.LocalName -ine $Name) { continue }
        if ($null -ne $found -or $child.LocalName -cne $Name -or $child.NamespaceURI -cne $Parent.NamespaceURI) {
            throw "PAPER_TASK_XML_SHAPE_${Name}"
        }
        $found = $child
    }
    if ($Required -and $null -eq $found) { throw "PAPER_TASK_XML_MISSING_${Name}" }
    return $found
}

function Assert-PaperTaskXmlText([Xml.XmlElement]$Node, [string]$Name) {
    if ($Node.HasAttributes -or $Node.ChildNodes.Count -ne 1 -or
        $Node.FirstChild.NodeType -ne [Xml.XmlNodeType]::Text) {
        throw "PAPER_TASK_XML_SHAPE_${Name}"
    }
}

function Read-PaperTaskRegistrationXml([string]$Xml, [bool]$Enabled) {
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
    } catch {
        throw 'PAPER_TASK_XML_INVALID'
    } finally {
        $reader.Dispose()
    }
    $task = $document.DocumentElement
    if ($task.LocalName -cne 'Task' -or $task.NamespaceURI -cne 'http://schemas.microsoft.com/windows/2004/02/mit/task') {
        throw 'PAPER_TASK_XML_ROOT'
    }
    $taskSettings = Get-PaperTaskXmlChild $task 'Settings' $true
    $enabledNode = Get-PaperTaskXmlChild $taskSettings 'Enabled' $true
    Assert-PaperTaskXmlText $enabledNode 'Enabled'
    $allowed = if ($Enabled) { @('true', '1') } else { @('false', '0') }
    if ($enabledNode.InnerText -cnotin $allowed) { throw 'PAPER_TASK_STAGE_ENABLED' }
    return (Get-PaperTaskXmlChild $task 'RegistrationInfo' $true)
}

function Set-PaperTaskRegistrationXml {
    # Installer: stamp the base XML before handing it to the definition API.
    # The caller owns all other fields, including explicit Settings.Enabled.
    param(
        [Parameter(Mandatory)][System.Collections.IDictionary]$Manifest,
        [Parameter(Mandatory)][string]$Stage,
        [Parameter(Mandatory)][string]$Role,
        [Parameter(Mandatory)][string]$TaskName,
        [Parameter(Mandatory)][string]$Xml
    )
    $expected = Get-PaperTaskRegistrationExpected $Manifest $Stage $Role $TaskName
    $info = Read-PaperTaskRegistrationXml $Xml $expected.Enabled
    foreach ($field in @('Description', 'Source')) {
        $node = Get-PaperTaskXmlChild $info $field $false
        if ($null -eq $node) {
            $node = $info.OwnerDocument.CreateElement($info.Prefix, $field, $info.NamespaceURI)
            $null = $info.AppendChild($node)
        } else {
            Assert-PaperTaskXmlText $node $field
        }
        $node.InnerText = $expected.$field
    }
    return $info.OwnerDocument.DocumentElement.OuterXml
}

function Assert-PaperTaskRegistrationXml {
    # Runtime and installer readback: check the real name and unmodified XML.
    # Never stamp observed XML before validating it or use a pass as admission.
    param(
        [Parameter(Mandatory)][System.Collections.IDictionary]$Manifest,
        [Parameter(Mandatory)][string]$Stage,
        [Parameter(Mandatory)][string]$Role,
        [Parameter(Mandatory)][string]$TaskName,
        [Parameter(Mandatory)][string]$Xml
    )
    $expected = Get-PaperTaskRegistrationExpected $Manifest $Stage $Role $TaskName
    $info = Read-PaperTaskRegistrationXml $Xml $expected.Enabled
    foreach ($field in @('Description', 'Source')) {
        $node = Get-PaperTaskXmlChild $info $field $true
        Assert-PaperTaskXmlText $node $field
        if ($node.InnerText -cne $expected.$field) { throw "PAPER_TASK_XML_MISMATCH_${field}" }
    }
}

Export-ModuleMember -Function Get-PaperTaskRegistrationPair, Set-PaperTaskRegistrationXml, Assert-PaperTaskRegistrationXml
