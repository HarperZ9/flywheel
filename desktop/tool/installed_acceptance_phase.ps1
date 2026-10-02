param([string]$ExpectedInstallerSha256 = "", [string]$SourceKind = "rebuilt-ci")
# Shared acceptance for already-built bytes. Caller supplies bound source/version and helpers.
if ($env:GITHUB_ACTIONS -ne "true" -or $env:RUNNER_ENVIRONMENT -ne "github-hosted" -or $env:RUNNER_OS -ne "Windows") {
  throw "installed acceptance requires disposable GitHub-hosted Windows"
}
Assert-ExactCommit $targetCommit
New-Item -ItemType Directory -Force -Path $acceptanceDir | Out-Null
$buildManifest = Join-Path $installerDir "installed-build-manifest.json"
Invoke-Checked "build installed payload manifest" "python" @("-m", "desktop.tool.installed_payload_binding", "build", "--payload-root", "desktop/build/windows/x64/runner/Release", "--payload-root", "desktop/build/engine/flywheel-gateway=engine", "--payload-root", "desktop/build/crt", "--installer-generated", "unins000.exe", "--installer-generated", "unins000.dat", "--source-commit", $targetCommit, "--version", $version, "--out", $buildManifest)
$installer = @(Get-ChildItem -LiteralPath $installerDir -Filter "Flywheel-Setup-*.exe" | Sort-Object Name)
if ($installer.Count -ne 1) { throw "expected one installer, found $($installer.Count)" }
$installer = $installer[0]
$installerHash = (Get-FileHash -LiteralPath $installer.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
Assert-Sha256 "installer_sha256" $installerHash
if ($ExpectedInstallerSha256 -and $installerHash -cne $ExpectedInstallerSha256) { throw "candidate installer checksum mismatch" }
if ($SourceKind -eq "tag-candidate" -and -not $ExpectedInstallerSha256) { throw "tag candidate requires installer checksum" }
# One LF-terminated row: GNU sha256sum -c reads a CRLF line ending as part of the file name.
[System.IO.File]::WriteAllText((Join-Path $installerDir "SHA256SUMS.txt"), "$installerHash  $($installer.Name)`n", [System.Text.Encoding]::ASCII)
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
$canonReceipt = Join-Path $acceptanceDir "installed-canon-context.json"
$inspectFixture = Join-Path $repoRoot "tests\fixtures\inspect\v1\single-success.fixture.json"
$common = @("-InstallRoot", $requestedInstallRoot, "-BuildManifest", $buildManifest, "-SourceCommitExpected", $targetCommit, "-ExpectedVersion", $version, "-ExpectedAppSha256", $appHash, "-ExpectedEngineSha256", $engineHash, "-ExpectInstallerPayload")
$fullArgs = New-InstalledAcceptanceCommandArgs $runner $common $fullDir $fullReceipt "full" -StartEngine
$inspectArgs = New-InstalledAcceptanceCommandArgs $runner $common $inspectDir $inspectReceipt "inspect" -InspectImport -InspectFixture $inspectFixture
Invoke-Checked "full installed acceptance" "powershell" $fullArgs
Invoke-Checked "inspect installed acceptance" "powershell" $inspectArgs
Invoke-Checked "installed Canon context acceptance" "python" @("scripts/check_installed_canon_context.py", "--install-root", $requestedInstallRoot, "--expected-engine-sha256", $engineHash, "--expected-version", $version, "--source-commit", $targetCommit, "--receipt", $canonReceipt)
Invoke-Checked "installed tool profile acceptance" "python" @("scripts/check_installed_tool_profiles.py", "--install-root", $requestedInstallRoot, "--expected-engine-sha256", $engineHash, "--expected-version", $version, "--source-commit", $targetCommit, "--receipt", (Join-Path $acceptanceDir "installed-tool-profiles.json"))
Invoke-Checked "installed native UI acceptance" "python" @("scripts/check_installed_native_ui.py", "--install-root", $requestedInstallRoot, "--expected-app-sha256", $appHash, "--expected-engine-sha256", $engineHash, "--expected-version", $version, "--source-commit", $targetCommit, "--receipt", (Join-Path $acceptanceDir "installed-native-ui.json"))
Invoke-Checked "installed lane acceptance" "powershell" @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $scriptRoot "run_installed_lane_acceptance.ps1"), "-InstallRoot", $requestedInstallRoot, "-Installer", $installer.FullName, "-AcceptanceDir", $acceptanceDir, "-SourceCommit", $targetCommit, "-EngineSha256", $engineHash, "-InstallerSha256", $installerHash)
Assert-TrackedAndSubmodulesUnchanged "after acceptance"
$installerHashAfterAcceptance = (Get-FileHash -LiteralPath $installer.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
if ($installerHashAfterAcceptance -cne $installerHash) { throw "installer hash changed during acceptance" }
$summary = [ordered]@{
  schema = "flywheel.windows-installed-acceptance-ci/v1"
  verdict = "PASS"
  installer_unchanged = $true
  source_commit = $targetCommit
  source_kind = $SourceKind
  workflow_source = [ordered]@{ repository = $env:GITHUB_REPOSITORY; ref = $env:GITHUB_REF; sha = $env:GITHUB_SHA }
  version = $version
  installer = [ordered]@{ name = $installer.Name; sha256 = $installerHash; size = $installer.Length }
  app_sha256 = $appHash
  engine_sha256 = $engineHash
  payload_sha256 = $payloadHash
  receipts = [ordered]@{ full = "installed-acceptance/installed-launch-full.json"; inspect = "installed-acceptance/installed-launch-inspect.json"; canon_context = "installed-acceptance/installed-canon-context.json"; tool_profiles = "installed-acceptance/installed-tool-profiles.json"; native_ui = "installed-acceptance/installed-native-ui.json"; lanes_per_user = "installed-acceptance/installed-lanes-per-user.json"; lanes_all_users = "installed-acceptance/installed-lanes-all-users.json" }
  limits = @("exact candidate installer bytes only", "native window and owned-child close checked; rendered content and interaction not checked", "device, signing, provider, and publication acceptance not claimed")
}
$receiptHashes = [ordered]@{}
$receiptFiles = @($summary.receipts.Values) + @("installed-build-manifest.json", "crt-selection.json")
foreach ($relative in $receiptFiles) {
  $receiptHashes[$relative] = (Get-FileHash -LiteralPath (Join-Path $installerDir $relative) -Algorithm SHA256).Hash.ToLowerInvariant()
}
$summary.receipt_sha256 = $receiptHashes
$summary | ConvertTo-Json -Depth 12 | Out-File -LiteralPath (Join-Path $installerDir "ci-installed-acceptance-summary.json") -Encoding utf8
