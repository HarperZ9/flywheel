param([switch]$DefineOnly)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktopRoot = (Resolve-Path (Join-Path $scriptRoot "..")).Path
$repoRoot = (Resolve-Path (Join-Path $desktopRoot "..")).Path
$installerDir = Join-Path $desktopRoot "build\installer"
$acceptanceDir = Join-Path $installerDir "installed-acceptance"
$appId = "ecf4cc9b-8a7a-4de2-8e70-0f1ea0f17e5c"
. (Join-Path $scriptRoot "installed_acceptance_commands.ps1")
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
    "desktop\tool\installed_acceptance_commands.ps1",
    "desktop\scripts\build_installer.ps1",
    "scripts\studio_runtime_packaging.py",
    "scripts\stage_python_lane_sources.py",
    "scripts\stage_node_lanes.py",
    "scripts\check_frozen_gateway.py",
    "scripts\check_installed_canon_context.py",
    "scripts\installed_app_lane_acceptance.py",
    "desktop\tool\run_installed_lane_acceptance.ps1",
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
function Write-SourceDriftDiagnostics([string]$Label, [string]$Root = $repoRoot) {
  $status = @(& git -C $Root status --porcelain=v1 --untracked-files=no --ignore-submodules=none)
  if ($LASTEXITCODE -eq 0 -and $status.Count -ne 0) {
    Write-Output "$Label git status porcelain: $($status -join '; ')"
    $paths = @()
    foreach ($line in $status) {
      if ($line.Length -ge 4) {
        $path = $line.Substring(3)
        if ($path -match ' -> ') { $path = ($path -split ' -> ', 2)[1] }
        if ($path -and -not $path.Contains('"')) { $paths += $path }
      }
    }
    if ($paths.Count -ne 0) {
      $eol = @(& git -C $Root ls-files --eol -- $paths)
      if ($LASTEXITCODE -eq 0 -and $eol.Count -ne 0) { Write-Output "$Label git ls-files --eol: $($eol -join '; ')" }
      foreach ($path in $paths) {
        if (-not (Test-Path -LiteralPath (Join-Path $Root $path))) { continue }
        $headHash = (& git -C $Root rev-parse "HEAD:$path" 2>$null)
        $workHash = (& git -C $Root hash-object --no-filters -- $path 2>$null)
        if ($headHash -and $workHash) { Write-Output "$Label byte hash $path head=$($headHash.Trim()) worktree=$($workHash.Trim())" }
      }
    }
  }
  $diff = @(& git -C $Root diff --name-status --ignore-submodules)
  if ($LASTEXITCODE -eq 0 -and $diff.Count -ne 0) { Write-Output "$Label git diff --name-status: $($diff -join '; ')" }
  $cached = @(& git -C $Root diff --cached --name-status --ignore-submodules)
  if ($LASTEXITCODE -eq 0 -and $cached.Count -ne 0) { Write-Output "$Label git diff --cached --name-status: $($cached -join '; ')" }
}
function Assert-TrackedAndSubmodulesUnchanged([string]$Label, [string]$Root = $repoRoot) {
  & git -C $Root diff --quiet --ignore-submodules
  if ($LASTEXITCODE -ne 0) { Write-SourceDriftDiagnostics $Label $Root; throw "$Label changed tracked source files" }
  & git -C $Root diff --cached --quiet --ignore-submodules
  if ($LASTEXITCODE -ne 0) { Write-SourceDriftDiagnostics $Label $Root; throw "$Label changed staged source files" }
  $status = @(& git -C $Root status --porcelain=v1 --untracked-files=no --ignore-submodules=none)
  if ($LASTEXITCODE -ne 0) { throw "$Label could not read git status" }
  if ($status.Count -ne 0) { Write-SourceDriftDiagnostics $Label $Root; throw "$Label changed tracked source or submodule state" }
  $submodules = @(& git -C $Root submodule status --recursive)
  if ($LASTEXITCODE -ne 0) { throw "$Label could not read submodule status" }
  foreach ($line in $submodules) {
    if ($line -match '^[-+U]') { throw "$Label changed submodule checkout: $line" }
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
$pythonLaneSourceRoot = Join-Path $env:RUNNER_TEMP "flywheel-python-lane-sources"
$pythonLaneStageReceipt = Join-Path $env:RUNNER_TEMP "python-lane-source-stage.full.json"
$pythonLaneBoundedReceipt = Join-Path $installerDir "python-lane-source-stage.json"
New-Item -ItemType Directory -Force -Path $installerDir | Out-Null
# Stage the full manifest used by scripts/python_lane_freeze.py, as desktop-release does.
Invoke-Checked "stage Python lane sources" "python" @("scripts/stage_python_lane_sources.py", "--all", "--source-root", $pythonLaneSourceRoot, "--receipt", $pythonLaneStageReceipt, "--bounded-receipt", $pythonLaneBoundedReceipt)
$env:FLYWHEEL_PYTHON_LANE_SOURCE_ROOT = $pythonLaneSourceRoot
# The freeze also refuses to run without the staged Node lanes (scripts/frozen_payload_datas.py).
$nodeLaneStageRoot = Join-Path $env:RUNNER_TEMP "flywheel-node-lanes"
Invoke-Checked "stage Node lanes" "python" @("scripts/stage_node_lanes.py", "--stage-root", $nodeLaneStageRoot)
$env:FLYWHEEL_NODE_LANE_STAGE_ROOT = $nodeLaneStageRoot
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
. (Join-Path $scriptRoot "installed_acceptance_phase.ps1")
