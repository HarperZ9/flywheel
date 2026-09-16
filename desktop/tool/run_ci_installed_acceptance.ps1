param([switch]$DefineOnly)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktopRoot = (Resolve-Path (Join-Path $scriptRoot "..")).Path
$repoRoot = (Resolve-Path (Join-Path $desktopRoot "..")).Path
$installerDir = Join-Path $desktopRoot "build\installer"
$acceptanceDir = Join-Path $installerDir "installed-acceptance"
$appId = "ecf4cc9b-8a7a-4de2-8e70-0f1ea0f17e5c"
function Invoke-Checked([string]$Label, [string]$FilePath, [string[]]$Arguments, [string]$WorkingDirectory = $repoRoot) {
  Push-Location $WorkingDirectory
  try {
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Label failed with exit $LASTEXITCODE" }
  } finally {
    Pop-Location
  }
}
function Assert-ExactCommit([string]$Value) {
  if ([string]::IsNullOrWhiteSpace($Value)) { throw "ACCEPTANCE_COMMIT is required" }
  if ($Value -cnotmatch "^[0-9a-f]{40}$") {
    throw "ACCEPTANCE_COMMIT must be an exact lowercase 40-hex commit"
  }
}
function Assert-Repository() {
  $expected = if ([string]::IsNullOrWhiteSpace($env:EXPECTED_REPOSITORY)) { "HarperZ9/flywheel" } else { $env:EXPECTED_REPOSITORY }
  if ($env:GITHUB_REPOSITORY -and $env:GITHUB_REPOSITORY -ne $expected) {
    throw "refusing installed acceptance outside $expected"
  }
  $origin = (& git -C $repoRoot remote get-url origin).Trim()
  if ($LASTEXITCODE -ne 0) { throw "could not read origin remote" }
  if ($origin -notmatch "github\.com[:/]HarperZ9/flywheel(\.git)?$") {
    throw "unexpected origin remote: $origin"
  }
}
function Checkout-ExactCommit([string]$targetCommit) {
  Invoke-Checked "fetch branch history" "git" @("fetch", "--no-tags", "--prune", "origin", "+refs/heads/*:refs/remotes/origin/*")
  Invoke-Checked "verify commit object" "git" @("cat-file", "-e", "$targetCommit^{commit}")
  $branchOutput = & git -C $repoRoot branch --remotes --contains $targetCommit --format "%(refname:short)"
  if ($LASTEXITCODE -ne 0) { throw "could not test branch reachability" }
  $containing = @($branchOutput | Where-Object { $_ -and $_ -ne "origin/HEAD" })
  if ($containing.Count -eq 0) { throw "commit is not reachable from an origin branch" }
  Invoke-Checked "checkout target commit" "git" @("checkout", "--detach", $targetCommit)
  $head = (& git -C $repoRoot rev-parse HEAD).Trim()
  if ($LASTEXITCODE -ne 0 -or $head -cne $targetCommit) {
    throw "checked-out HEAD does not match ACCEPTANCE_COMMIT"
  }
}
function Assert-WorkflowSource([string]$targetCommit) {
  $workflowSha = [string]$env:GITHUB_SHA
  if ([string]::IsNullOrWhiteSpace($workflowSha)) { throw "GITHUB_SHA is required" }
  if ($workflowSha -cne $targetCommit) {
    throw "GITHUB_SHA must exactly match ACCEPTANCE_COMMIT; dispatch the workflow from the commit being accepted"
  }
}
function Assert-RequiredTargetFiles() {
  $required = @(
    "desktop\tool\run_installed_launch_acceptance.ps1",
    "desktop\tool\installed_payload_binding.py",
    "desktop\scripts\build_installer.ps1",
    "scripts\studio_runtime_packaging.py",
    "scripts\check_frozen_gateway.py",
    "packaging\flywheel-gateway.spec",
    "tests\fixtures\inspect\v1\single-success.fixture.json"
  )
  foreach ($relative in $required) {
    if (-not (Test-Path -LiteralPath (Join-Path $repoRoot $relative))) {
      throw "target commit is missing required installed-acceptance file: $relative"
    }
  }
}
function Assert-CleanWorkspaceNoUntracked([string]$Label, [string]$Root = $repoRoot) {
  $status = @(& git -C $Root status --porcelain=v1 --untracked-files=all --ignore-submodules=none)
  if ($LASTEXITCODE -ne 0) { throw "$Label could not read git status" }
  if ($status.Count -ne 0) { throw "$Label workspace is not clean before build" }
}
function Assert-TrackedAndSubmodulesUnchanged([string]$Label, [string]$Root = $repoRoot) {
  & git -C $Root diff --quiet --ignore-submodules
  if ($LASTEXITCODE -ne 0) { throw "$Label changed tracked source files" }
  & git -C $Root diff --cached --quiet --ignore-submodules
  if ($LASTEXITCODE -ne 0) { throw "$Label changed staged source files" }
  $status = @(& git -C $Root status --porcelain=v1 --untracked-files=no --ignore-submodules=none)
  if ($LASTEXITCODE -ne 0) { throw "$Label could not read git status" }
  if ($status.Count -ne 0) { throw "$Label changed tracked source or submodule state" }
  $submodules = @(& git -C $Root submodule status --recursive)
  if ($LASTEXITCODE -ne 0) { throw "$Label could not read submodule status" }
  foreach ($line in $submodules) {
    if ($line -match '^[+\\-U]') { throw "$Label changed submodule checkout: $line" }
  }
}
function Quote-WindowsArgument([string]$Value) {
  if ($null -eq $Value) { $Value = "" }
  if ($Value.Length -gt 0 -and $Value -notmatch '[\s"]') { return $Value }
  return '"' + (($Value -replace '(\\*)"', '$1$1\"') -replace '(\\+)$', '$1$1') + '"'
}
function Join-WindowsCommandLine([string[]]$Arguments) {
  return (@($Arguments | ForEach-Object { Quote-WindowsArgument ([string]$_) }) -join " ")
}
function Find-InnoSetup() {
  $iscc = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
  ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
  if (-not $iscc) {
    Invoke-Checked "install Inno Setup" "choco" @("install", "innosetup", "-y", "--no-progress")
    $iscc = @(
      "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
      "C:\Program Files\Inno Setup 6\ISCC.exe"
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
  }
  if (-not $iscc) { throw "ISCC.exe not found after Inno Setup step" }
}
function Get-PropertyText($Object, [string]$Name) {
  if ($null -eq $Object) { return "" }
  $property = $Object.PSObject.Properties[$Name]
  if ($null -eq $property -or $null -eq $property.Value) { return "" }
  return [string]$property.Value
}
function RegistryEntryMatchesFlywheel($Entry) {
  $child = (Get-PropertyText $Entry "PSChildName").ToLowerInvariant()
  $name = Get-PropertyText $Entry "DisplayName"
  $location = Get-PropertyText $Entry "InstallLocation"
  return $child.Contains($appId) -or $name.StartsWith("Flywheel") -or $location.EndsWith("\Flywheel\")
}
function Get-FlywheelRegistryEntries() {
  $roots = @(
    "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
    "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
    "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
  )
  @(Get-ItemProperty $roots -ErrorAction SilentlyContinue | Where-Object { RegistryEntryMatchesFlywheel $_ })
}
function Assert-CleanFlywheelHost() {
  $entries = @(Get-FlywheelRegistryEntries)
  if ($entries.Count -ne 0) { throw "existing Flywheel uninstall registry entry found" }
  $paths = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Flywheel"),
    (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Flywheel"),
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "Flywheel.lnk"),
    (Join-Path $env:PUBLIC "Desktop\Flywheel.lnk")
  )
  if ($env:ProgramFiles) { $paths += Join-Path $env:ProgramFiles "Flywheel" }
  $x86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
  if ($x86) { $paths += Join-Path $x86 "Flywheel" }
  foreach ($path in $paths) {
    if ($path -and (Test-Path -LiteralPath $path)) { throw "existing Flywheel path found before install: $path" }
  }
}
function Normalize-WindowsPath([string]$Path) {
  if ([string]::IsNullOrWhiteSpace($Path)) { return "" }
  return [System.IO.Path]::GetFullPath($Path).TrimEnd("\", "/")
}
function Assert-RegistryInstallLocation($Entry, [string]$ExpectedRoot) {
  $value = Get-PropertyText $Entry "InstallLocation"
  if ([string]::IsNullOrWhiteSpace($value)) { throw "Flywheel registry entry is missing InstallLocation" }
  $observed = Normalize-WindowsPath $value
  $expected = Normalize-WindowsPath $ExpectedRoot
  if (-not $observed.Equals($expected, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Flywheel registry InstallLocation does not match requested per-user install root"
  }
}
function New-InstalledAcceptanceCommandArgs(
  [string]$Runner, [string[]]$Common, [string]$ValidationDir,
  [string]$Out, [string]$Mode, [switch]$StartEngine,
  [switch]$InspectImport, [string]$InspectFixture = ""
) {
  $args = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $Runner) +
    $Common + @("-ValidationDir", $ValidationDir, "-Out", $Out, "-Mode", $Mode)
  if ($StartEngine) { $args += "-StartEngine" }
  if ($InspectImport) { $args += "-InspectImport" }
  if (![string]::IsNullOrWhiteSpace($InspectFixture)) { $args += @("-InspectFixture", $InspectFixture) }
  return [string[]]$args
}
function Read-Version() {
  $line = Get-Content -LiteralPath (Join-Path $desktopRoot "pubspec.yaml") | Where-Object { $_ -match '^version:' } | Select-Object -First 1
  if ($null -eq $line) { throw "could not read desktop pubspec version" }
  return (($line -replace 'version:\s*', '') -split '\+')[0].Trim()
}
function Assert-Sha256([string]$Name, [string]$Value) {
  if ($Value -notmatch '^[0-9a-f]{64}$') { throw "$Name is not a lowercase SHA-256" }
}
if ($DefineOnly) { return }
$targetCommit = [string]$env:ACCEPTANCE_COMMIT
Assert-ExactCommit $targetCommit
Set-Location $repoRoot
Assert-Repository
Assert-WorkflowSource $targetCommit
Checkout-ExactCommit $targetCommit
Assert-RequiredTargetFiles
$version = Read-Version
Invoke-Checked "submodule update" "git" @("submodule", "update", "--init", "--recursive")
Invoke-Checked "Relay descriptor gate" "python" @("scripts/check_bundled_lane_descriptors.py", "--lane", "relay", "--strict")
Invoke-Checked "install freeze dependencies" "python" @("-m", "pip", "install", "pyinstaller==6.21.0", ".[signing]")
$runtimeSources = Join-Path $repoRoot "packaging\studio-runtime-sources.json"
$runtimeWork = Join-Path $env:RUNNER_TEMP "flywheel-studio-runtime-sources"
$runtimeManifest = Join-Path $env:RUNNER_TEMP "studio-body-runtime-manifest.json"
$runtimePayload = Join-Path $env:RUNNER_TEMP "flywheel-studio-runtime-payload"
Invoke-Checked "stage pinned Studio runtime" "python" @("-m", "scripts.studio_runtime_packaging", "stage-pinned-payload", "--sources", $runtimeSources, "--work-root", $runtimeWork, "--manifest", $runtimeManifest, "--payload-root", $runtimePayload)
$env:FLYWHEEL_STUDIO_BODY_RUNTIME_MANIFEST = $runtimeManifest
$env:FLYWHEEL_STUDIO_BODY_RUNTIME_PAYLOAD = $runtimePayload
Find-InnoSetup
Assert-CleanWorkspaceNoUntracked "before build"
New-Item -ItemType Directory -Force -Path $installerDir, $acceptanceDir | Out-Null
$frozenSmoke = Join-Path $installerDir "frozen-gateway-smoke.json"
Invoke-Checked "freeze gateway" "python" @("-m", "PyInstaller", "packaging/flywheel-gateway.spec", "--noconfirm")
Invoke-Checked "frozen gateway smoke" "python" @("scripts/check_frozen_gateway.py", "--executable", "dist/flywheel-gateway/flywheel-gateway.exe", "--expected-version", $version, "--receipt", $frozenSmoke)
$engineStage = Join-Path $desktopRoot "build\engine\flywheel-gateway"
if (Test-Path -LiteralPath $engineStage) { throw "engine staging destination already exists" }
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $engineStage) | Out-Null
Copy-Item -LiteralPath (Join-Path $repoRoot "dist\flywheel-gateway") -Destination $engineStage -Recurse
Invoke-Checked "build installer" "powershell" @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "scripts\build_installer.ps1", "-SkipEngine") $desktopRoot
$buildManifest = Join-Path $installerDir "installed-build-manifest.json"
Invoke-Checked "build installed payload manifest" "python" @("-m", "desktop.tool.installed_payload_binding", "build", "--payload-root", "desktop/build/windows/x64/runner/Release", "--payload-root", "desktop/build/engine/flywheel-gateway=engine", "--payload-root", "desktop/build/crt", "--installer-generated", "unins000.exe", "--installer-generated", "unins000.dat", "--source-commit", $targetCommit, "--version", $version, "--out", $buildManifest)
$installer = @(Get-ChildItem -LiteralPath $installerDir -Filter "Flywheel-Setup-*.exe" | Sort-Object Name)
if ($installer.Count -ne 1) { throw "expected one installer, found $($installer.Count)" }
$installer = $installer[0]
$installerHash = (Get-FileHash -LiteralPath $installer.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
Assert-Sha256 "installer_sha256" $installerHash
"$installerHash  $($installer.Name)" | Out-File -Encoding ascii (Join-Path $installerDir "SHA256SUMS.txt")
$manifestDoc = Get-Content -LiteralPath $buildManifest -Raw | ConvertFrom-Json
$appHash = [string]$manifestDoc.artifacts.app_sha256
$engineHash = [string]$manifestDoc.artifacts.engine_sha256
$payloadHash = [string]$manifestDoc.payload.payload_sha256
Assert-Sha256 "artifacts.app_sha256" $appHash
Assert-Sha256 "artifacts.engine_sha256" $engineHash
Assert-Sha256 "payload.payload_sha256" $payloadHash
Assert-TrackedAndSubmodulesUnchanged "after build"
Assert-CleanFlywheelHost
$installerHashBeforeInstall = (Get-FileHash -LiteralPath $installer.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
if ($installerHashBeforeInstall -cne $installerHash) {
  throw "installer hash changed before installation"
}
$requestedInstallRoot = Normalize-WindowsPath (Join-Path $env:LOCALAPPDATA "Programs\Flywheel")
$installArgs = @("/CURRENTUSER", "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/DIR=$requestedInstallRoot")
$install = Start-Process -FilePath $installer.FullName -ArgumentList (Join-WindowsCommandLine $installArgs) -WindowStyle Hidden -Wait -PassThru
if ($install.ExitCode -ne 0) { throw "installer exited $($install.ExitCode)" }
$entries = @(Get-FlywheelRegistryEntries)
if ($entries.Count -ne 1) { throw "expected one Flywheel uninstall registry entry after install, found $($entries.Count)" }
Assert-RegistryInstallLocation $entries[0] $requestedInstallRoot
if (-not (Test-Path -LiteralPath $requestedInstallRoot)) { throw "requested per-user install root missing after install" }
$fullDir = Join-Path $acceptanceDir "full"
$inspectDir = Join-Path $acceptanceDir "inspect"
New-Item -ItemType Directory -Force -Path $fullDir, $inspectDir | Out-Null
$runner = Join-Path $desktopRoot "tool\run_installed_launch_acceptance.ps1"
$fullReceipt = Join-Path $acceptanceDir "installed-launch-full.json"
$inspectReceipt = Join-Path $acceptanceDir "installed-launch-inspect.json"
$inspectFixture = Join-Path $repoRoot "tests\fixtures\inspect\v1\single-success.fixture.json"
$common = @("-InstallRoot", $requestedInstallRoot, "-BuildManifest", $buildManifest, "-SourceCommitExpected", $targetCommit, "-ExpectedVersion", $version, "-ExpectedAppSha256", $appHash, "-ExpectedEngineSha256", $engineHash, "-ExpectInstallerPayload")
$fullArgs = New-InstalledAcceptanceCommandArgs $runner $common $fullDir $fullReceipt "full" -StartEngine
$inspectArgs = New-InstalledAcceptanceCommandArgs $runner $common $inspectDir $inspectReceipt "inspect" -InspectImport -InspectFixture $inspectFixture
Invoke-Checked "full installed acceptance" "powershell" $fullArgs
Invoke-Checked "inspect installed acceptance" "powershell" $inspectArgs
Assert-TrackedAndSubmodulesUnchanged "after acceptance"
$summary = [ordered]@{
  schema = "flywheel.windows-installed-acceptance-ci/v1"
  source_commit = $targetCommit
  workflow_source = [ordered]@{ repository = $env:GITHUB_REPOSITORY; ref = $env:GITHUB_REF; sha = $env:GITHUB_SHA }
  version = $version
  installer = [ordered]@{ name = $installer.Name; sha256 = $installerHash; size = $installer.Length }
  app_sha256 = $appHash
  engine_sha256 = $engineHash
  payload_sha256 = $payloadHash
  receipts = [ordered]@{ full = "installed-acceptance/installed-launch-full.json"; inspect = "installed-acceptance/installed-launch-inspect.json" }
  limits = @("rebuilt CI candidate only", "native UI not launched", "device, signing, provider, and publication acceptance not claimed")
}
$summary | ConvertTo-Json -Depth 12 | Out-File -LiteralPath (Join-Path $installerDir "ci-installed-acceptance-summary.json") -Encoding utf8
