# build_installer.ps1 - build the Flywheel Windows installer end to end.
#
# Stages: flutter release build -> frozen engine (PyInstaller, from the
# engine repo) -> VC++ CRT DLLs (from the VS Redist tree) -> ISCC compile.
# Output: build\installer\Flywheel-Setup-<version>-x64.exe
#
# Usage (from the repo root):
#   powershell -File scripts\build_installer.ps1
#   powershell -File scripts\build_installer.ps1 -EngineRepo ..\local-model -SkipFlutter
#
# Nothing here is machine-specific: the engine repo defaults to the sibling
# checkout, ISCC is found via PATH, standard dirs, or the registry, and the
# CRT comes from whatever VS/BuildTools Redist tree is present.

param(
    [string]$EngineRepo = "..\local-model",
    [string]$Iscc = "",
    [switch]$SkipFlutter,
    [switch]$SkipEngine
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

# The single source of version truth is pubspec.yaml.
$versionLine = (Get-Content "pubspec.yaml" | Where-Object { $_ -match '^version:' } | Select-Object -First 1)
$version = ($versionLine -replace 'version:\s*', '' -split '\+')[0].Trim()
if (-not $version) { throw "could not read version from pubspec.yaml" }
Write-Output "== Flywheel installer build, version $version =="

# 1. Flutter release bundle.
if (-not $SkipFlutter) {
    Write-Output "-- flutter build windows --release"
    flutter build windows --release
    if ($LASTEXITCODE -ne 0) { throw "flutter build failed" }
}
$appDir = Join-Path $repo "build\windows\x64\runner\Release"
if (-not (Test-Path (Join-Path $appDir "flywheel_desktop.exe"))) {
    throw "app payload missing: $appDir (run without -SkipFlutter)"
}

# 2. Frozen engine.
$engineOut = Join-Path $repo "build\engine\flywheel-gateway"
if (-not $SkipEngine) {
    $engineRepoFull = Resolve-Path $EngineRepo
    Write-Output "-- freezing engine from $engineRepoFull"
    Push-Location $engineRepoFull
    try {
        python -m PyInstaller packaging\flywheel-gateway.spec --noconfirm
        if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
    } finally { Pop-Location }
    if (Test-Path $engineOut) { Remove-Item -Recurse -Force $engineOut }
    New-Item -ItemType Directory -Force (Split-Path $engineOut) | Out-Null
    Copy-Item -Recurse (Join-Path $engineRepoFull "dist\flywheel-gateway") $engineOut
}
if (-not (Test-Path (Join-Path $engineOut "flywheel-gateway.exe"))) {
    throw "engine payload missing: $engineOut (run without -SkipEngine)"
}

# 3. VC++ CRT from a Redist tree (redistributable copies, never System32).
# Discovery is vswhere-first: VS installs move roots across major versions
# (2022 lives under \2022\, VS 18 under \18\), and hardcoding a year broke
# the first CI release run. vswhere is shipped with every VS install and on
# every GitHub runner image; a broad directory glob stays as the fallback.
$crtDir = Join-Path $repo "build\crt"
New-Item -ItemType Directory -Force $crtDir | Out-Null
$vsRoots = @()
$vswhere = "C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe"
if (Test-Path $vswhere) {
    $vsRoots += & $vswhere -latest -products * -property installationPath 2>$null
    $vsRoots += & $vswhere -products * -property installationPath 2>$null
}
$vsRoots += Get-ChildItem -Directory -ErrorAction SilentlyContinue `
    "C:\Program Files\Microsoft Visual Studio\*\*",
    "C:\Program Files (x86)\Microsoft Visual Studio\*\*" |
    Select-Object -ExpandProperty FullName
$crtSource = $vsRoots | Where-Object { $_ } | Select-Object -Unique |
    ForEach-Object {
        Get-ChildItem -Directory -ErrorAction SilentlyContinue `
            (Join-Path $_ "VC\Redist\MSVC\*\x64\Microsoft.VC14*.CRT")
    } | Select-Object -First 1
if (-not $crtSource) {
    throw "no VC14x x64 CRT Redist tree found (searched: $($vsRoots -join '; '))"
}
foreach ($dll in "msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll") {
    Copy-Item (Join-Path $crtSource.FullName $dll) $crtDir -Force
}
Write-Output "-- CRT staged from $($crtSource.FullName)"

# 4. Find ISCC: parameter, PATH, standard dirs, then the registry entry.
if (-not $Iscc) {
    $cmd = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($cmd) { $Iscc = $cmd.Source }
}
if (-not $Iscc) {
    $Iscc = @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $Iscc) {
    $entry = Get-ItemProperty `
        'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*' `
        -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -like 'Inno Setup*' } | Select-Object -First 1
    if ($entry -and $entry.InstallLocation) {
        $candidate = Join-Path $entry.InstallLocation "ISCC.exe"
        if (Test-Path $candidate) { $Iscc = $candidate }
    }
}
if (-not $Iscc) { throw "ISCC.exe not found; install Inno Setup 6 or pass -Iscc" }
Write-Output "-- ISCC: $Iscc"

# 5. Compile.
& $Iscc "installer\flywheel.iss" `
    "/DAppVersion=$version" `
    "/DAppDir=$appDir" `
    "/DEngineDir=$engineOut" `
    "/DCrtDir=$crtDir"
if ($LASTEXITCODE -ne 0) { throw "ISCC failed" }

$artifact = Join-Path $repo "build\installer\Flywheel-Setup-$version-x64.exe"
if (-not (Test-Path $artifact)) { throw "expected artifact missing: $artifact" }
$size = [math]::Round((Get-Item $artifact).Length / 1MB, 1)
Write-Output "== built: $artifact ($size MB) =="
