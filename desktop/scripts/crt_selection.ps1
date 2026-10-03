# Select one coherent x64 redistributable set compatible with the generated build toolset.
$ErrorActionPreference = "Stop"
$script:CrtNames = @("msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll")

function Assert-CrtUnlinkedPath([string]$Path) {
    $current = [IO.Path]::GetFullPath($Path)
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            if ((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "CRT path may not contain reparse points"
            }
        }
        $parent = [IO.Directory]::GetParent($current)
        $current = if ($parent) { $parent.FullName } else { $null }
    }
}

function Get-CrtBuildRequirement([string]$BuildRoot) {
    $records = @()
    foreach ($file in @(Get-ChildItem -Path (Join-Path $BuildRoot "CMakeFiles\*\CMakeCXXCompiler.cmake") -File)) {
        $text = Get-Content -LiteralPath $file.FullName -Raw
        if ($text -notmatch 'set\(CMAKE_CXX_COMPILER_ID "MSVC"\)') { throw "unsupported compiler binding" }
        $pathMatch = [regex]::Match($text, 'set\(CMAKE_CXX_COMPILER "([^"\r\n]+)"\)')
        $versionMatch = [regex]::Match($text, 'set\(CMAKE_CXX_COMPILER_VERSION "([0-9.]+)"\)')
        $toolset = [regex]::Match($pathMatch.Groups[1].Value.Replace('\', '/'), '/VC/Tools/MSVC/(14\.[0-9]+\.[0-9]+)/bin/Host[^/]+/x64/cl\.exe$')
        if (-not $pathMatch.Success -or -not $versionMatch.Success -or -not $toolset.Success) { throw "missing x64 MSVC compiler binding" }
        $records += "$($toolset.Groups[1].Value)|$($versionMatch.Groups[1].Value)"
    }
    $unique = @($records | Select-Object -Unique)
    if ($unique.Count -ne 1) { throw "missing or ambiguous compiler binding; use a clean native build" }
    $parts = $unique[0].Split('|')
    $toolVersion = [version]$parts[0]
    $compilerVersion = [version]$parts[1]
    if ($compilerVersion.Major -ne 19 -or $compilerVersion.Minor -ne $toolVersion.Minor) { throw "inconsistent MSVC compiler binding" }
    return [pscustomobject]@{ toolset_version=$parts[0]; compiler_version=$parts[1] }
}

function Get-CrtFileRecord([string]$Directory, [string]$Name) {
    $path = Join-Path $Directory $Name
    Assert-CrtUnlinkedPath $path
    $file = Get-Item -LiteralPath $path
    $reader = [IO.BinaryReader]::new([IO.File]::OpenRead($path))
    try {
        if ($reader.ReadUInt16() -ne 0x5a4d) { throw "CRT DLL is not PE" }
        $reader.BaseStream.Position = 60
        $offset = $reader.ReadUInt32()
        if ($offset -gt ($reader.BaseStream.Length - 6)) { throw "CRT DLL PE header is outside file" }
        $reader.BaseStream.Position = $offset
        if ($reader.ReadUInt32() -ne 0x4550 -or $reader.ReadUInt16() -ne 0x8664) { throw "CRT DLL is not x64" }
    } finally { $reader.Dispose() }
    $info = $file.VersionInfo
    $version = [version]::new($info.FileMajorPart, $info.FileMinorPart, $info.FileBuildPart, $info.FilePrivatePart)
    if ($version.Major -ne 14) { throw "CRT DLL has no supported v14 file version" }
    return [pscustomobject]@{ name=$Name; version=$version.ToString(); machine="x64";
        sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() }
}

function Select-CompatibleCrt([string[]]$Directories, [version]$Minimum) {
    $candidates = @()
    foreach ($directory in $Directories) {
        try {
            $files = @($script:CrtNames | ForEach-Object { Get-CrtFileRecord $directory $_ })
            # Microsoft may service individual DLL patch revisions differently.
            # Coherence means one Redist directory; every DLL must satisfy the floor.
            $versions = @($files.version | ForEach-Object { [version]$_ } | Sort-Object)
            if (@($versions | Where-Object { $_.Major -ne 14 -or $_ -lt $Minimum }).Count) { continue }
            $candidates += [pscustomobject]@{ directory=$directory; version=$versions[0].ToString(); files=$files }
        } catch { continue } # Missing, mixed or invalid sets never enter selection.
    }
    $selected = $candidates | Sort-Object -Property @{Expression={[version]$_.version}; Descending=$true}, directory | Select-Object -First 1
    if (-not $selected) { throw "no compatible coherent x64 CRT set at or above MSVC toolset $Minimum" }
    return $selected
}

function Stage-CrtSet($Selection, [string]$BuildRoot) {
    $build = [IO.Path]::GetFullPath($BuildRoot).TrimEnd('\', '/')
    Assert-CrtUnlinkedPath $build
    $target = Join-Path $build "crt"
    $stage = Join-Path $build ("crt-stage-" + [guid]::NewGuid().ToString('N'))
    $backup = Join-Path $build ("crt-previous-" + [guid]::NewGuid().ToString('N'))
    foreach ($path in @($target, $stage, $backup)) {
        if (-not [IO.Path]::GetFullPath($path).StartsWith($build + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw "CRT stage escaped owned build directory" }
        Assert-CrtUnlinkedPath $path
    }
    if (Test-Path -LiteralPath $target) {
        foreach ($entry in @(Get-ChildItem -LiteralPath $target -Force)) {
            if ($entry.PSIsContainer -or $entry.Name -notin $script:CrtNames) { throw "existing CRT stage contains unexpected files" }
        }
    }
    New-Item -ItemType Directory -Path $stage | Out-Null
    foreach ($file in $Selection.files) {
        $source = Join-Path $Selection.directory $file.name
        Assert-CrtUnlinkedPath $source
        Copy-Item -LiteralPath $source -Destination (Join-Path $stage $file.name)
        $observed = (Get-FileHash -LiteralPath (Join-Path $stage $file.name) -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($observed -cne $file.sha256) { throw "CRT source changed during staging" }
    }
    # Promote the complete verified directory, preserving any prior stage for diagnosis.
    if (Test-Path -LiteralPath $target) { Move-Item -LiteralPath $target -Destination $backup }
    Move-Item -LiteralPath $stage -Destination $target
}
