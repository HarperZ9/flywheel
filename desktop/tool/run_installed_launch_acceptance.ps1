param(
  [string]$InstallRoot = "", [string]$Out = "", [string]$PythonPath = "",
  [string]$ValidationDir = "", [string]$RunId = "", [string]$Mode = "preflight",
  [string]$SourceCommitExpected = "", [string]$ExpectedVersion = "",
  [string]$ExpectedAppSha256 = "", [string]$ExpectedEngineSha256 = "",
  [string]$BuildManifest = "", [switch]$ExpectInstallerPayload,
  [switch]$RequireDesktopShortcut, [switch]$StartEngine,
  [switch]$IncludeLocalPaths, [switch]$SelfTest
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptRoot "installed_launch_acceptance_wrapper_contract.ps1")
$desktopRoot = (Resolve-Path (Join-Path $scriptRoot "..")).Path
$repoRoot = (Resolve-Path (Join-Path $desktopRoot "..")).Path

function Resolve-Executable($ExplicitPath, [string[]]$Names, $ParameterName) {
  if (![string]::IsNullOrWhiteSpace($ExplicitPath)) {
    $resolved = @(Resolve-Path -LiteralPath $ExplicitPath -ErrorAction Stop)
    if ($resolved.Count -ne 1) { throw "-$ParameterName resolved to $($resolved.Count) paths" }
    if ((Get-Item -LiteralPath $resolved[0].ProviderPath).PSIsContainer) { throw "-$ParameterName points to a directory: $ExplicitPath" }
    return $resolved[0].ProviderPath
  }
  foreach ($name in $Names) { $cmd = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1; if ($null -ne $cmd) { return $cmd.Source } }
  throw "Unable to locate $($Names -join ' or '); pass -$ParameterName."
}

function Convert-SummaryPath($Path, $Base, $Label) {
  if ($IncludeLocalPaths) { return $Path }
  $full = [IO.Path]::GetFullPath($Path); $root = [IO.Path]::GetFullPath($Base).TrimEnd("\", "/")
  if ($full.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) {
    $rel = $full.Substring($root.Length).TrimStart("\", "/") -replace "\\", "/"
    return "<$Label>/$rel"
  }
  return "<redacted-local-path>"
}

function Quote-WindowsArgument([string]$Value) {
  if ($null -eq $Value) { $Value = "" }
  if ($Value.Length -gt 0 -and $Value -notmatch '[\s"]') { return $Value }
  return '"' + (($Value -replace '(\\*)"', '$1$1\"') -replace '(\\+)$', '$1$1') + '"'
}
function Join-WindowsCommandLine([string[]]$Arguments) { return (@($Arguments | ForEach-Object { Quote-WindowsArgument ([string]$_) }) -join " ") }

function Convert-LocalError($Message) {
  if ($IncludeLocalPaths) { return $Message }
  $known = @($InstallRoot, $ValidationDir, $Out, $BuildManifest, $PythonPath)
  foreach ($name in @("repoRoot", "desktopRoot", "scriptRoot", "validationRoot", "resolvedInstallRoot", "outPath")) {
    $var = Get-Variable -Name $name -Scope Script -ErrorAction SilentlyContinue
    if ($null -ne $var) { $known += @([string]$var.Value) }
  }
  foreach ($value in $known | Sort-Object Length -Descending) {
    if (![string]::IsNullOrWhiteSpace([string]$value)) { $Message = ([string]$Message).Replace([string]$value, "<redacted-local-path>") }
  }
  return ([string]$Message) -replace '[A-Za-z]:[\\/][^\r\n]+', '<redacted-local-path>'
}

function Invoke-HiddenProcess($FilePath, [string[]]$Arguments, $WorkingDirectory, $Stdout, $Stderr) {
  $process = Start-Process -FilePath $FilePath -ArgumentList (Join-WindowsCommandLine $Arguments) -WorkingDirectory $WorkingDirectory -PassThru -Wait -WindowStyle Hidden -RedirectStandardOutput $Stdout -RedirectStandardError $Stderr
  return [int]$process.ExitCode
}
function Get-CurrentCommit { $out = & git -C $repoRoot rev-parse HEAD 2>$null; if ($LASTEXITCODE -eq 0) { return ([string]$out).Trim() }; return "" }
function Get-ExpectedVersion {
  $line = Get-Content -LiteralPath (Join-Path $desktopRoot "pubspec.yaml") | Where-Object { $_ -match '^version:' } | Select-Object -First 1
  if ($null -eq $line) { return "" }
  return (($line -replace 'version:\s*', '') -split '\+')[0].Trim()
}

try {
if ($SelfTest) { Invoke-SelfTest; exit 0 }
if ([string]::IsNullOrWhiteSpace($InstallRoot)) { throw "-InstallRoot is required unless -SelfTest is set." }
$resolvedInstallRoot = (Resolve-Path -LiteralPath $InstallRoot -ErrorAction Stop).Path
$python = Resolve-Executable $PythonPath @("python", "python3") "PythonPath"
$runIdValue = if ([string]::IsNullOrWhiteSpace($RunId)) { New-LaunchRunId } else { $RunId }
if ([string]::IsNullOrWhiteSpace($ValidationDir)) { $validationRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("flywheel-installed-launch-" + $runIdValue) }
else { New-Item -ItemType Directory -Force -Path $ValidationDir | Out-Null; $validationRoot = (Resolve-Path -LiteralPath $ValidationDir).Path }
New-Item -ItemType Directory -Force -Path $validationRoot | Out-Null
$outPath = if ([string]::IsNullOrWhiteSpace($Out)) { Join-Path $validationRoot "installed-launch-acceptance.json" } else { $Out }
$source = if ([string]::IsNullOrWhiteSpace($SourceCommitExpected)) { Get-CurrentCommit } else { $SourceCommitExpected }
$version = if ([string]::IsNullOrWhiteSpace($ExpectedVersion)) { Get-ExpectedVersion } else { $ExpectedVersion }
$stdout = Join-Path $validationRoot "installed-launch-acceptance.stdout.log"; $stderr = Join-Path $validationRoot "installed-launch-acceptance.stderr.log"
$pythonArgs = @("-m", "desktop.tool.installed_launch_acceptance", "--install-root", $resolvedInstallRoot, "--out", $outPath, "--run-id", $runIdValue, "--mode", $Mode, "--artifact-root", $validationRoot, "--source-commit-expected", $source, "--expected-version", $version)
if (![string]::IsNullOrWhiteSpace($ExpectedAppSha256)) { $pythonArgs += @("--expected-app-sha256", $ExpectedAppSha256) }
if (![string]::IsNullOrWhiteSpace($ExpectedEngineSha256)) { $pythonArgs += @("--expected-engine-sha256", $ExpectedEngineSha256) }
if (![string]::IsNullOrWhiteSpace($BuildManifest)) { $pythonArgs += @("--build-manifest", (Resolve-Path -LiteralPath $BuildManifest).Path) }
if ($ExpectInstallerPayload) { $pythonArgs += "--expect-installer-payload" }; if ($RequireDesktopShortcut) { $pythonArgs += "--require-desktop-shortcut" }
if ($StartEngine) { $pythonArgs += "--start-engine" }; if ($IncludeLocalPaths) { $pythonArgs += "--include-local-paths" }
$exitCode = Invoke-HiddenProcess $python ([string[]]$pythonArgs) $repoRoot $stdout $stderr
if ($exitCode -ne 0) { throw "Installed-launch harness failed with exit $exitCode. See $(Convert-SummaryPath $stderr $validationRoot 'validation_root')" }
$receipt = Test-InstalledLaunchReceipt $outPath $runIdValue $source
$summaryRoot = if ($IncludeLocalPaths) { $validationRoot } else { "<validation_root>" }
@{ schema = "flywheel.installed-launch-run/v1"; complete = $true; run_id = $runIdValue; validation_root = $summaryRoot; receipt_path = Convert-SummaryPath $outPath $validationRoot "validation_root"; stdout_log = Convert-SummaryPath $stdout $validationRoot "validation_root"; stderr_log = Convert-SummaryPath $stderr $validationRoot "validation_root"; proof = $receipt } | ConvertTo-Json -Depth 32
} catch {
  [Console]::Error.WriteLine((Convert-LocalError ([string]$_.Exception.Message)))
  exit 1
}
