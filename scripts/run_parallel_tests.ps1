param(
    [ValidateRange(1, 64)]
    [int]$Workers = [Math]::Min(8, [Environment]::ProcessorCount),
    [switch]$RequireCleanTempRoot,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs
)

$ErrorActionPreference = "Stop"

function Resolve-TestTempParent {
    # This host's NVMe C: avoids the measured SATA D: durable-write bottleneck.
    foreach ($candidate in @("C:\trpy", "D:\trpy")) {
        $qualifier = Split-Path -Qualifier $candidate
        if ([string]::IsNullOrWhiteSpace($qualifier)) {
            continue
        }
        $driveName = $qualifier.TrimEnd([char[]]@(':', '\', '/'))
        $drive = Get-PSDrive -Name $driveName -PSProvider FileSystem -ErrorAction SilentlyContinue
        if ($null -eq $drive -or -not [string]::IsNullOrWhiteSpace([string]$drive.DisplayRoot)) {
            continue
        }
        $root = Get-Item -LiteralPath $qualifier -Force -ErrorAction SilentlyContinue
        if (
            $null -eq $root -or
            $root.LinkType -or
            ($root.Attributes -band [IO.FileAttributes]::ReparsePoint)
        ) {
            continue
        }
        return [IO.Path]::GetFullPath($candidate).TrimEnd([char[]]@('\', '/'))
    }

    throw "No local non-reparse drive is available for parallel pytest temporary files"
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$tempParent = Resolve-TestTempParent
$tempRoot = Join-Path $tempParent "runs"
$mutexName = "Global\TheRicherV2ParallelPytest"
$leaseSuffix = ".thericher-pytest-lease"

function Test-ReparsePoint {
    param([System.IO.FileSystemInfo]$Entry)

    return [bool](
        $Entry.LinkType -or
        ($Entry.Attributes -band [IO.FileAttributes]::ReparsePoint)
    )
}

function Assert-ManagedTempDirectory {
    param(
        [string]$Path,
        [string]$ExpectedParent,
        [string]$Label,
        [switch]$RequireEmpty
    )

    $entry = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    $resolved = [IO.Path]::GetFullPath($entry.FullName).TrimEnd([char[]]@('\', '/'))
    if (
        -not $entry.PSIsContainer -or
        (Test-ReparsePoint $entry) -or
        -not [string]::Equals(
            [IO.Path]::GetDirectoryName($resolved),
            $ExpectedParent,
            [StringComparison]::OrdinalIgnoreCase
        )
    ) {
        throw "Refusing to use an unmanaged parallel pytest ${Label}: $Path"
    }
    if ($RequireEmpty -and @(Get-ChildItem -LiteralPath $resolved -Force).Count -ne 0) {
        throw "Parallel pytest temp child is not empty: $resolved"
    }
    return $resolved
}

function Assert-SafeTempTreeForRemoval {
    param(
        [string]$Path,
        [string]$ExpectedParent,
        [string]$Label
    )

    $resolved = Assert-ManagedTempDirectory `
        -Path $Path `
        -ExpectedParent $ExpectedParent `
        -Label $Label
    $linkedEntries = @(
        Get-ChildItem -LiteralPath $resolved -Force -Recurse -ErrorAction Stop |
            Where-Object { Test-ReparsePoint $_ }
    )
    if ($linkedEntries.Count -gt 0) {
        throw "Refusing to remove a linked parallel pytest temp tree: $resolved"
    }
    return $resolved
}

function Assert-NoActiveParallelPytestRun {
    param([string]$ResolvedTempRoot)

    $candidateRoots = @(
        Get-ChildItem -LiteralPath $ResolvedTempRoot -Directory -Force -Filter "r-*" -ErrorAction Stop
    )
    $leaseFiles = @(
        Get-ChildItem `
            -LiteralPath $ResolvedTempRoot `
            -File `
            -Force `
            -Filter ".r-*$leaseSuffix" `
            -ErrorAction Stop
    )
    foreach ($lease in $leaseFiles) {
        $resolvedLease = [IO.Path]::GetFullPath($lease.FullName)
        if (
            (Test-ReparsePoint $lease) -or
            -not [string]::Equals(
                [IO.Path]::GetDirectoryName($resolvedLease),
                $ResolvedTempRoot,
                [StringComparison]::OrdinalIgnoreCase
            )
        ) {
            throw "Refusing to inspect an unmanaged parallel pytest lease: $($lease.FullName)"
        }
        $leaseHandle = $null
        try {
            $leaseHandle = [IO.File]::Open(
                $resolvedLease,
                [IO.FileMode]::Open,
                [IO.FileAccess]::ReadWrite,
                [IO.FileShare]::None
            )
        }
        catch [IO.IOException] {
            throw "Parallel pytest authority found an active helper lease: $($lease.Name)"
        }
        finally {
            if ($null -ne $leaseHandle) {
                $leaseHandle.Dispose()
            }
        }
    }

    try {
        $pythonProcesses = @(
            Get-CimInstance -ClassName Win32_Process -ErrorAction Stop |
                Where-Object { $_.Name -match '^(python|pythonw|pytest)(\.exe)?$' }
        )
    }
    catch {
        throw "Parallel pytest authority cannot inspect active Python processes"
    }
    foreach ($candidate in $candidateRoots) {
        $resolvedCandidate = Assert-ManagedTempDirectory `
            -Path $candidate.FullName `
            -ExpectedParent $ResolvedTempRoot `
            -Label "temp child"
        foreach ($process in $pythonProcesses) {
            if ([string]::IsNullOrWhiteSpace([string]$process.CommandLine)) {
                throw "Parallel pytest authority cannot inspect an active Python command line"
            }
            if ($process.CommandLine.IndexOf($resolvedCandidate, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
                throw "Parallel pytest authority found an active worker for: $resolvedCandidate"
            }
        }
    }
}

function Assert-NoActiveKnownParallelPytestRuns {
    param([string[]]$TempParents)

    # A dead helper may leave workers on the previously selected drive.
    foreach ($parent in $TempParents) {
        if (-not (Test-Path -LiteralPath $parent -ErrorAction Stop)) {
            continue
        }
        $fullParent = [IO.Path]::GetFullPath($parent).TrimEnd([char[]]@('\', '/'))
        $qualifier = Split-Path -Qualifier $fullParent
        $driveName = $qualifier.TrimEnd([char[]]@(':', '\', '/'))
        $drive = Get-PSDrive -Name $driveName -PSProvider FileSystem -ErrorAction Stop
        $driveRoot = Get-Item -LiteralPath $qualifier -Force -ErrorAction Stop
        if (
            -not [string]::IsNullOrWhiteSpace([string]$drive.DisplayRoot) -or
            (Test-ReparsePoint $driveRoot)
        ) {
            throw "Refusing to inspect a nonlocal or linked parallel pytest drive: $qualifier"
        }
        $checkedParent = Assert-ManagedTempDirectory `
            -Path $fullParent `
            -ExpectedParent ([IO.Path]::GetDirectoryName($fullParent)) `
            -Label "temp parent"
        $knownRoot = Join-Path $checkedParent "runs"
        if (-not (Test-Path -LiteralPath $knownRoot -ErrorAction Stop)) {
            continue
        }
        $checkedRoot = Assert-ManagedTempDirectory `
            -Path $knownRoot `
            -ExpectedParent $checkedParent `
            -Label "temp root"
        Assert-NoActiveParallelPytestRun -ResolvedTempRoot $checkedRoot
    }
}

New-Item -ItemType Directory -Force -Path $tempParent | Out-Null
$tempParentEntry = Get-Item -LiteralPath $tempParent -Force -ErrorAction Stop
if (Test-ReparsePoint $tempParentEntry) {
    throw "Refusing to use a linked parallel pytest temp parent: $tempParent"
}
$resolvedTempParent = [IO.Path]::GetFullPath($tempParent).TrimEnd([char[]]@('\', '/'))

New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
$tempRootEntry = Get-Item -LiteralPath $tempRoot -Force -ErrorAction Stop
$resolvedTempRoot = [IO.Path]::GetFullPath($tempRoot).TrimEnd([char[]]@('\', '/'))
if (
    (Test-ReparsePoint $tempRootEntry) -or
    -not [string]::Equals(
        [IO.Path]::GetDirectoryName($resolvedTempRoot),
        $resolvedTempParent,
        [StringComparison]::OrdinalIgnoreCase
    )
) {
    throw "Refusing to use an unmanaged parallel pytest temp root: $tempRoot"
}

$exitCode = 1
$baseTemp = $null
$leasePath = $null
$leaseHandle = $null
$mutex = $null
$mutexAcquired = $false
$locationPushed = $false
try {
    $mutex = [System.Threading.Mutex]::new($false, $mutexName)
    try {
        $mutexAcquired = $mutex.WaitOne([TimeSpan]::Zero)
    }
    catch [System.Threading.AbandonedMutexException] {
        $mutexAcquired = $true
    }
    if (-not $mutexAcquired) {
        throw "Parallel pytest helper is already active; authority verification will not wait"
    }
    if ($RequireCleanTempRoot) {
        Assert-NoActiveKnownParallelPytestRuns -TempParents @("C:\trpy", "D:\trpy")
    }

    do {
        $baseTemp = Join-Path $resolvedTempRoot ("r-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
    } while (Test-Path -LiteralPath $baseTemp)
    New-Item -ItemType Directory -Path $baseTemp -ErrorAction Stop | Out-Null
    $baseTemp = Assert-ManagedTempDirectory `
        -Path $baseTemp `
        -ExpectedParent $resolvedTempRoot `
        -Label "active temp child" `
        -RequireEmpty
    $leasePath = Join-Path $resolvedTempRoot ("." + (Split-Path -Leaf $baseTemp) + $leaseSuffix)
    $leaseHandle = [IO.File]::Open(
        $leasePath,
        [IO.FileMode]::CreateNew,
        [IO.FileAccess]::ReadWrite,
        [IO.FileShare]::None
    )

    Push-Location $repoRoot
    $locationPushed = $true
    # File-level distribution preserves most test-local fixture assumptions.
    & uv run --extra dev pytest -q -n $Workers --dist=loadfile --basetemp $baseTemp @PytestArgs
    $exitCode = $LASTEXITCODE
}
finally {
    if ($locationPushed) {
        Pop-Location
    }
    if ($null -ne $leaseHandle) {
        $leaseHandle.Dispose()
    }
    if ($exitCode -eq 0 -and $null -ne $baseTemp -and (Test-Path -LiteralPath $baseTemp)) {
        try {
            $resolvedBaseTemp = Assert-SafeTempTreeForRemoval `
                -Path $baseTemp `
                -ExpectedParent $resolvedTempRoot `
                -Label "active temp child"
            Remove-Item -LiteralPath $resolvedBaseTemp -Recurse -Force -ErrorAction Stop
        }
        catch {
            Write-Warning "Parallel pytest passed but could not remove its temp path: $baseTemp"
            $exitCode = 1
        }
    }
    if ($null -ne $leasePath -and (Test-Path -LiteralPath $leasePath)) {
        try {
            Remove-Item -LiteralPath $leasePath -Force -ErrorAction Stop
        }
        catch {
            Write-Warning "Parallel pytest could not remove its lease path: $leasePath"
            $exitCode = 1
        }
    }
    if ($mutexAcquired) {
        $mutex.ReleaseMutex()
    }
    if ($null -ne $mutex) {
        $mutex.Dispose()
    }
}

exit $exitCode
