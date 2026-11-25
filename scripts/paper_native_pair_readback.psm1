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
                        -TaskName $row.Name -Xml $pin[$field]
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

Export-ModuleMember -Function New-PaperNativePairReadback
