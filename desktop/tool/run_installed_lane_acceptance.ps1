# run_installed_lane_acceptance.ps1 - the lane step of the pre-tag installed
# acceptance (PLAN WP11). run_ci_installed_acceptance.ps1 calls it after the
# per-user install passed its launch and Canon checks.
#
# 1. Lane acceptance on the per-user install (scripts/installed_app_lane_acceptance.py).
# 2. Uninstall the per-user install.
# 3. Install the same installer for all users into Program Files (/ALLUSERS),
#    run the lane acceptance again, then uninstall it (O-15: lane writes must
#    stay out of the install folder in both modes).
#
# Receipts go to -AcceptanceDir (uploaded). Throwaway homes and the detail
# files stay under -WorkRoot (the runner's temp folder, never uploaded).
param(
  [string]$InstallRoot = "",
  [string]$Installer = "",
  [string]$AcceptanceDir = "",
  [string]$SourceCommit = "",
  [string]$EngineSha256 = "",
  [string]$InstallerSha256 = "",
  [string]$WorkRoot = $env:RUNNER_TEMP,
  [switch]$SkipAllUsers,
  [switch]$DefineOnly
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$repoRoot = (Resolve-Path (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "..\..")).Path

function Get-LaneAcceptanceArgs([string]$Root, [string]$Mode, [string]$AcceptanceDir,
                                [string]$WorkRoot, [string]$SourceCommit, [string]$EngineSha256) {
  return [string[]]@(
    "scripts/installed_app_lane_acceptance.py",
    "--install-root", $Root,
    "--work", [System.IO.Path]::Combine($WorkRoot, "flywheel-lane-acceptance-$Mode"),
    "--receipt", [System.IO.Path]::Combine($AcceptanceDir, "installed-lanes-$Mode.json"),
    "--detail", [System.IO.Path]::Combine($WorkRoot, "installed-lanes-$Mode.detail.json"),
    "--install-mode", $Mode,
    "--meta", "source_commit=$SourceCommit",
    "--meta", "engine_sha256=$EngineSha256")
}

function Invoke-LaneAcceptance([string]$Root, [string]$Mode) {
  $argv = Get-LaneAcceptanceArgs $Root $Mode $AcceptanceDir $WorkRoot $SourceCommit $EngineSha256
  & python @argv
  if ($LASTEXITCODE -ne 0) { throw "installed lane acceptance ($Mode) failed with exit $LASTEXITCODE" }
}

function Uninstall-Flywheel([string]$Root) {
  $uninstaller = Join-Path $Root "unins000.exe"
  if (-not (Test-Path -LiteralPath $uninstaller)) { throw "no uninstaller at $uninstaller" }
  $p = Start-Process -FilePath $uninstaller -ArgumentList "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART" `
    -Wait -PassThru -WindowStyle Hidden
  if ($p.ExitCode -ne 0) { throw "uninstaller exited $($p.ExitCode)" }
  # The Inno uninstaller hands off to a copy in the temp folder and returns early.
  $engine = Join-Path $Root "engine\flywheel-gateway.exe"
  for ($i = 0; $i -lt 120 -and (Test-Path -LiteralPath $engine); $i++) { Start-Sleep -Seconds 1 }
  if (Test-Path -LiteralPath $engine) { throw "uninstall left the engine at $engine" }
}

function Install-AllUsers([string]$Installer) {
  $actualHash = (Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($InstallerSha256 -cnotmatch '^[0-9a-f]{64}$' -or $actualHash -cne $InstallerSha256) { throw "all-users installer checksum mismatch" }
  $root = Join-Path $env:ProgramFiles "Flywheel"
  if (Test-Path -LiteralPath $root) { throw "all-users install root already exists: $root" }
  $argList = @("/ALLUSERS", "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/DIR=`"$root`"")
  $p = Start-Process -FilePath $Installer -ArgumentList ($argList -join " ") -Wait -PassThru -WindowStyle Hidden
  if ($p.ExitCode -ne 0) { throw "all-users installer exited $($p.ExitCode)" }
  if (-not (Test-Path -LiteralPath (Join-Path $root "engine\flywheel-gateway.exe"))) {
    throw "all-users install has no engine"
  }
  return $root
}

if ($DefineOnly) { return }
foreach ($name in "InstallRoot", "Installer", "AcceptanceDir", "SourceCommit", "EngineSha256", "InstallerSha256", "WorkRoot") {
  if ([string]::IsNullOrWhiteSpace((Get-Variable -Name $name -ValueOnly))) { throw "-$name is required" }
}
New-Item -ItemType Directory -Force -Path $AcceptanceDir | Out-Null
Push-Location $repoRoot
try {
  Invoke-LaneAcceptance $InstallRoot "per-user"
  if (-not $SkipAllUsers) {
    Uninstall-Flywheel $InstallRoot
    $allUsersRoot = Install-AllUsers $Installer
    Invoke-LaneAcceptance $allUsersRoot "all-users"
    Uninstall-Flywheel $allUsersRoot
  }
} finally {
  Pop-Location
}
