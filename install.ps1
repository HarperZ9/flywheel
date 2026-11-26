# Install the flywheel command for this user on Windows.
#
#   irm https://raw.githubusercontent.com/HarperZ9/flywheel/main/install.ps1 | iex
#
# Fetches the release wheel + SHA256SUMS from GitHub Releases, verifies SHA-256
# fail-closed before installing, and installs via uv tool, pipx, or a private
# virtual environment under %LOCALAPPDATA%\Flywheel\cli (adding Scripts to User PATH
# unless -NoPath or FLYWHEEL_NO_PATH=1 is set). Needs Python 3.11 or newer.
# Settings: FLYWHEEL_VERSION, FLYWHEEL_SOURCE, FLYWHEEL_FROM_DIR, FLYWHEEL_INSTALL_DIR,
#           FLYWHEEL_INSTALL_METHOD (auto|uv|pipx|venv), FLYWHEEL_NO_PATH=1.
param(
  [string]$Version = $(if ($env:FLYWHEEL_VERSION) { $env:FLYWHEEL_VERSION } else { "latest" }),
  [string]$InstallDir = $(if ($env:FLYWHEEL_INSTALL_DIR) { $env:FLYWHEEL_INSTALL_DIR } else { Join-Path $env:LOCALAPPDATA "Flywheel\cli" }),
  [string]$FromDir = $(if ($env:FLYWHEEL_FROM_DIR) { $env:FLYWHEEL_FROM_DIR } else { "" }),
  [ValidateSet("auto", "uv", "pipx", "venv")]
  [string]$Method = $(if ($env:FLYWHEEL_INSTALL_METHOD) { $env:FLYWHEEL_INSTALL_METHOD } else { "auto" }),
  [switch]$FromPyPI,
  [switch]$NoPath,
  [switch]$SelfTest
)

$ErrorActionPreference = "Stop"
$Repo = "HarperZ9/flywheel"
$SkipPath = [bool]$NoPath -or ($env:FLYWHEEL_NO_PATH -eq "1")

function Find-Python311 {
  foreach ($candidate in @(@("py", "-3"), @("python"), @("python3"))) {
    $exe = Get-Command $candidate[0] -ErrorAction SilentlyContinue
    if (-not $exe) { continue }
    $args0 = @($candidate | Select-Object -Skip 1)
    & $exe.Source @args0 -c "import sys; raise SystemExit(sys.version_info < (3, 11))" 2>$null
    if ($LASTEXITCODE -eq 0) { return ,@($exe.Source) + $args0 }
  }
  throw "flywheel needs Python 3.11 or newer; install it and run this again."
}

function Get-Sha256Hex([string]$Path) {
  $sha = [System.Security.Cryptography.SHA256]::Create()
  try {
    $stream = [System.IO.File]::OpenRead($Path)
    try { return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace("-", "").ToLowerInvariant() }
    finally { $stream.Dispose() }
  } finally { $sha.Dispose() }
}

function Parse-Sums([string]$SumsPath) {
  $map = @{}
  foreach ($line in (Get-Content -Path $SumsPath -Encoding UTF8)) {
    if ($line -match '^\s*([0-9a-fA-F]{64})\s+\*?(.+?)\s*$') {
      $map[$Matches[2].Trim()] = $Matches[1].ToLowerInvariant()
    }
  }
  return $map
}

function Assert-Checksum([string]$FilePath, [string]$AssetName, [hashtable]$Sums) {
  if (-not $Sums.ContainsKey($AssetName)) {
    throw "Refusing install: $AssetName is missing from SHA256SUMS."
  }
  $actual = Get-Sha256Hex $FilePath
  $expected = $Sums[$AssetName]
  if ($actual -ne $expected) {
    throw "Refusing install: SHA-256 mismatch for $AssetName (expected $expected, got $actual)."
  }
}

function Add-UserPath([string]$BinDir) {
  $current = [Environment]::GetEnvironmentVariable("Path", "User")
  $parts = @()
  if ($current) { $parts = $current.Split(";") | Where-Object { $_ -ne "" } }
  if ($parts -notcontains $BinDir) {
    $next = ($parts + $BinDir) -join ";"
    [Environment]::SetEnvironmentVariable("Path", $next, "User")
    Write-Host "Added $BinDir to your user PATH; open a new terminal to use it."
  }
  if (($env:Path.Split(";")) -notcontains $BinDir) {
    $env:Path = "$BinDir;$env:Path"
  }
}

function Find-SumsFile([string]$StageDir) {
  foreach ($name in @("SHA256SUMS", "python-SHA256SUMS.txt", "SHA256SUMS.txt")) {
    $p = Join-Path $StageDir $name
    if (Test-Path $p) { return $p }
  }
  throw "Refusing install: SHA256SUMS not found in $StageDir."
}

function Install-Venv([string]$Spec, [string]$DestDir, [bool]$OfflineWheel, [bool]$NoPathFlag) {
  $py = Find-Python311
  $pyExe = $py[0]
  $pyArgs = @($py | Select-Object -Skip 1)
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $DestDir) | Out-Null
  & $pyExe @pyArgs -m venv $DestDir
  if ($LASTEXITCODE -ne 0) { throw "Could not create virtual environment at $DestDir." }
  $venvPy = Join-Path $DestDir "Scripts\python.exe"
  if ($OfflineWheel) {
    & $venvPy -m pip install --quiet --disable-pip-version-check --no-deps --no-index --force-reinstall $Spec
  } else {
    & $venvPy -m pip install --quiet --disable-pip-version-check --upgrade $Spec
  }
  if ($LASTEXITCODE -ne 0) { throw "pip install failed with exit code $LASTEXITCODE." }
  $scripts = Join-Path $DestDir "Scripts"
  if (-not $NoPathFlag) { Add-UserPath $scripts }
  return $scripts
}

function Install-Wheel([string]$WheelPath, [string]$DestDir, [string]$ChosenMethod, [bool]$NoPathFlag) {
  $mode = $ChosenMethod
  if ($mode -eq "auto") {
    if (Get-Command uv -ErrorAction SilentlyContinue) { $mode = "uv" }
    elseif (Get-Command pipx -ErrorAction SilentlyContinue) { $mode = "pipx" }
    else { $mode = "venv" }
  }
  if ($mode -eq "uv") {
    & uv tool install --force $WheelPath
    if ($LASTEXITCODE -ne 0) { throw "uv tool install failed with exit code $LASTEXITCODE." }
    return "uv tool"
  }
  if ($mode -eq "pipx") {
    & pipx install --force $WheelPath
    if ($LASTEXITCODE -ne 0) { throw "pipx install failed with exit code $LASTEXITCODE." }
    return "pipx"
  }
  return (Install-Venv $WheelPath $DestDir $true $NoPathFlag)
}

function Install-FromStage([string]$StageDir, [string]$DestDir, [string]$ChosenMethod, [bool]$NoPathFlag) {
  $sumsFile = Find-SumsFile $StageDir
  $sums = Parse-Sums $sumsFile
  $wheel = Get-ChildItem -Path $StageDir -File | Where-Object { $_.Name -match '^flywheel_verify-.+\.whl$' } | Select-Object -First 1
  if (-not $wheel) { throw "Refusing install: no flywheel_verify wheel found in $StageDir." }
  Assert-Checksum $wheel.FullName $wheel.Name $sums
  $where = Install-Wheel $wheel.FullName $DestDir $ChosenMethod $NoPathFlag
  New-Item -ItemType Directory -Force -Path $DestDir | Out-Null
  Copy-Item -Path $sumsFile -Destination (Join-Path $DestDir "SHA256SUMS") -Force
  Write-Output "Flywheel verified (SHA256SUMS OK) and installed via $where."
}

function Invoke-SelfTest {
  $py = Find-Python311
  $pyExe = $py[0]
  $pyArgs = @($py | Select-Object -Skip 1)
  $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("flywheel-install-selftest-" + [Guid]::NewGuid().ToString("N"))
  try {
    $stage = Join-Path $tmp "stage"
    $destOk = Join-Path $tmp "dest-ok"
    $destBad = Join-Path $tmp "dest-bad"
    New-Item -ItemType Directory -Force -Path $stage | Out-Null
    $whl = Join-Path $stage "flywheel_verify-0.0.1-py3-none-any.whl"

    $pyScript = @'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1], "w") as z:
    z.writestr("flywheel_selftest/__init__.py", "VERSION = '0.0.1'\n")
    z.writestr("flywheel_selftest/cli.py", "def main():\n    print('flywheel selftest ok')\n")
    z.writestr("flywheel_verify-0.0.1.dist-info/METADATA", "Metadata-Version: 2.1\nName: flywheel-verify\nVersion: 0.0.1\n")
    z.writestr("flywheel_verify-0.0.1.dist-info/WHEEL", "Wheel-Version: 1.0\nGenerator: selftest\nRoot-Is-Purelib: true\nTag: py3-none-any\n")
    z.writestr("flywheel_verify-0.0.1.dist-info/entry_points.txt", "[console_scripts]\nflywheel = flywheel_selftest.cli:main\n")
    z.writestr("flywheel_verify-0.0.1.dist-info/RECORD", "")
'@
    $pyScript | & $pyExe @pyArgs - $whl
    if ($LASTEXITCODE -ne 0) { throw "Self-test failed: could not build synthetic wheel." }

    $sumsText = "$(Get-Sha256Hex $whl)  flywheel_verify-0.0.1-py3-none-any.whl`n"
    Set-Content -Path (Join-Path $stage "SHA256SUMS") -Value $sumsText -NoNewline -Encoding UTF8

    Install-FromStage $stage $destOk "venv" $true
    $exe = Join-Path $destOk "Scripts\flywheel.exe"
    if (-not (Test-Path $exe)) { throw "Self-test failed: flywheel.exe missing after valid install." }
    $out = & $exe
    if ($out -notmatch "flywheel selftest ok") { throw "Self-test failed: unexpected CLI output: $out" }

    # Planted 1-byte tamper control: installer must refuse before installing.
    $bytes = [System.IO.File]::ReadAllBytes($whl)
    $bytes[$bytes.Length - 1] = $bytes[$bytes.Length - 1] -bxor 0x01
    [System.IO.File]::WriteAllBytes($whl, $bytes)

    $refused = $false
    try { Install-FromStage $stage $destBad "venv" $true } catch { if ($_.Exception.Message -match "SHA-256 mismatch") { $refused = $true } else { throw } }
    if (-not $refused) { throw "Self-test failed: tampered wheel was not refused." }
    if (Test-Path (Join-Path $destBad "Scripts\flywheel.exe")) { throw "Self-test failed: tampered wheel was installed." }
    Write-Output "SELFTEST PASS: valid wheel install verified and planted 1-byte tamper refused."
  } finally {
    Remove-Item -Path $tmp -Recurse -Force -ErrorAction SilentlyContinue
  }
}

if ($SelfTest) {
  Invoke-SelfTest
  exit 0
}

if ($env:FLYWHEEL_SOURCE) {
  $scripts = Install-Venv $env:FLYWHEEL_SOURCE $InstallDir $false $SkipPath
  & (Join-Path $scripts "flywheel.exe") --version
  exit 0
}

if ($FromPyPI -or $env:FLYWHEEL_FROM_PYPI -eq "1") {
  $req = if ($Version -ne "latest") { "flywheel-verify==$($Version.TrimStart('v'))" } else { "flywheel-verify" }
  $scripts = Install-Venv $req $InstallDir $false $SkipPath
  & (Join-Path $scripts "flywheel.exe") --version
  exit 0
}

if ($FromDir) {
  Install-FromStage (Resolve-Path $FromDir).Path $InstallDir $Method $SkipPath
  exit 0
}

$api = if ($Version -eq "latest") {
  "https://api.github.com/repos/$Repo/releases/latest"
} else {
  $tag = if ($Version.StartsWith("v")) { $Version } else { "v$Version" }
  "https://api.github.com/repos/$Repo/releases/tags/$tag"
}
$headers = @{ "User-Agent" = "flywheel-installer"; "Accept" = "application/vnd.github+json" }
$rel = Invoke-RestMethod -Uri $api -Headers $headers
$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("flywheel-install-" + [Guid]::NewGuid().ToString("N"))
try {
  New-Item -ItemType Directory -Force -Path $tmp | Out-Null
  $assets = @($rel.assets)
  $sumsAsset = $assets | Where-Object { $_.name -in @("SHA256SUMS", "python-SHA256SUMS.txt", "SHA256SUMS.txt") } | Select-Object -First 1
  if (-not $sumsAsset) { throw "Refusing install: release $($rel.tag_name) has no SHA256SUMS asset." }
  $whlAsset = $assets | Where-Object { $_.name -match '^flywheel_verify-.+\.whl$' } | Select-Object -First 1
  if (-not $whlAsset) { throw "Refusing install: release $($rel.tag_name) has no flywheel_verify wheel asset." }
  foreach ($a in @($sumsAsset, $whlAsset)) {
    Invoke-WebRequest -Uri $a.browser_download_url -OutFile (Join-Path $tmp $a.name)
  }
  Install-FromStage $tmp $InstallDir $Method $SkipPath
} finally {
  Remove-Item -Path $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
