param(
  [string]$FlutterPath = "",
  [string]$AdbPath = "",
  [string]$EmulatorPath = "",
  [string]$DeviceId = "",
  [string]$ReceiptPath = "",
  [switch]$SelfTest
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$ProgressPreference = "SilentlyContinue"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktopRoot = (Resolve-Path (Join-Path $scriptRoot "..")).Path
$repoRoot = (Resolve-Path (Join-Path $desktopRoot "..")).Path
$fixtureRel = "integration_test/android_gateway_handoff_test.dart"
$schema = "flywheel.android-handoff-acceptance-runner/v1"
$selfTestSchema = "flywheel.android-handoff-runner-selftest/v1"
. (Join-Path $scriptRoot "android_handoff_runner_support.ps1")
function Resolve-BuildTool([string]$SdkRoot, [string]$Name) {
  if ($null -eq $SdkRoot) { return $null }
  $tool = Get-ChildItem -LiteralPath (Join-Path $SdkRoot "build-tools") -Recurse -Filter $Name -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | Select-Object -First 1
  if ($null -eq $tool) { return $null }
  return $tool.FullName
}
function Read-ApkVersion($Aapt, $ApkPath) {
  if ($null -eq $Aapt -or !(Test-Path -LiteralPath $ApkPath)) { return @{ status = "unavailable" } }
  $r = Invoke-Captured $Aapt @("dump", "badging", $ApkPath) $desktopRoot 30
  $line = ($r.stdout -split "`r?`n" | Where-Object { $_.StartsWith("package:") } | Select-Object -First 1)
  $m = [regex]::Match([string]$line, "name='([^']+)'.*versionCode='([^']+)'.*versionName='([^']*)'")
  if ($r.exit_code -ne 0 -or !$m.Success) { return @{ status = "unknown"; exit_code = $r.exit_code; stderr = Get-Tail $r.stderr "" } }
  return @{ status = "ok"; package_name = $m.Groups[1].Value; version_code = $m.Groups[2].Value; version_name = $m.Groups[3].Value }
}
function Resolve-JavaForApkSigner {
  $envHome = [string]$env:JAVA_HOME
  if ($envHome -ne "") { $java = Join-Path $envHome "bin/java.exe"; if (Test-Path -LiteralPath $java) { return @{ status = "ok"; source = "JAVA_HOME"; java_home = (Resolve-Path -LiteralPath $envHome).Path; java_path = (Resolve-Path -LiteralPath $java).Path } } }
  $cmd = Get-Command java -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($null -ne $cmd) { return @{ status = "ok"; source = "PATH"; java_path = $cmd.Source } }
  $homes = @(); if ([string]$env:ProgramFiles -ne "") { $homes += Join-Path $env:ProgramFiles "Android/Android Studio/jbr" }; if ([string]$env:LOCALAPPDATA -ne "") { $homes += Join-Path $env:LOCALAPPDATA "Programs/Android Studio/jbr" }
  foreach ($home in $homes) { $java = Join-Path $home "bin/java.exe"; if (Test-Path -LiteralPath $java) { return @{ status = "ok"; source = "android_studio_jbr"; java_home = (Resolve-Path -LiteralPath $home).Path; java_path = (Resolve-Path -LiteralPath $java).Path } } }
  return @{ status = "missing"; reason = "java_unavailable" }
}
function Convert-ApkSigningResult($Run, $Java) {
  $stdout = Get-Tail $Run.stdout ""; $stderr = Get-Tail $Run.stderr ""; $base = @{ status = "unknown"; exit_code = $Run.exit_code; timed_out = $Run.timed_out; stdout_tail = $stdout; stderr_tail = $stderr; java = $Java }
  if ($Run.timed_out) { $base["reason"] = "apksigner_timeout"; return $base }
  $combined = "$stdout`n$stderr"; $line = (($stdout -split "`r?`n") | Where-Object { $_ -match "Signer #1 certificate SHA-256 digest:" } | Select-Object -First 1)
  if ($Run.exit_code -ne 0) { $base["reason"] = if ($combined -match "JAVA_HOME is not set|no 'java' command|could not find .*java") { "java_unavailable" } else { "apksigner_failed" }; return $base }
  if ($null -eq $line) { $base["reason"] = "missing_certificate_digest"; return $base }
  $m = [regex]::Match([string]$line, "Signer #1 certificate SHA-256 digest:\s*(.+)$"); $digest = ($m.Groups[1].Value -replace "[^0-9A-Fa-f]", "").ToLowerInvariant()
  if ($digest -notmatch "^[0-9a-f]{64}$") { $base["reason"] = "malformed_certificate_digest"; return $base }
  return @{ status = "ok"; certificate_sha256 = $digest; exit_code = $Run.exit_code; timed_out = $Run.timed_out; stdout_tail = $stdout; stderr_tail = $stderr; java = $Java }
}
function Read-ApkSigning($ApkSigner, $ApkPath) {
  if ($null -eq $ApkSigner -or !(Test-Path -LiteralPath $ApkPath)) { return @{ status = "unavailable" } }
  $java = Resolve-JavaForApkSigner; $envMap = $null
  if ($java.ContainsKey("java_home")) { $envMap = @{ JAVA_HOME = $java["java_home"]; Path = (Join-Path $java["java_home"] "bin") + ";" + [string]$env:Path } }
  return Convert-ApkSigningResult (Invoke-Captured $ApkSigner @("verify", "--print-certs", $ApkPath) $desktopRoot 30 -Environment $envMap) $java
}
function Remove-OwnedTempApkDir($Path) {
  if (!(Test-Path -LiteralPath $Path)) { return }
  $tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath()).TrimEnd("\", "/")
  $resolved = Resolve-Path -LiteralPath $Path -ErrorAction Stop
  if (@($resolved).Count -ne 1) { throw "Temp APK cleanup target did not resolve to exactly one path" }
  $target = [System.IO.Path]::GetFullPath($resolved.Path).TrimEnd("\", "/")
  $parent = [System.IO.Path]::GetFullPath((Split-Path -Parent $target)).TrimEnd("\", "/")
  $leaf = Split-Path -Leaf $target
  if ($parent -ine $tempRoot -or $leaf -notmatch "^fw-android-apk-[0-9a-fA-F]{32}$") { throw "Refusing unsafe temp APK cleanup target" }
  $item = Get-Item -LiteralPath $target -Force -ErrorAction Stop
  if (!$item.PSIsContainer -or (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0)) { throw "Refusing non-directory or reparse temp APK cleanup target" }
  $reparse = Get-ChildItem -LiteralPath $target -Recurse -Force -ErrorAction Stop | Where-Object { ($_.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0 } | Select-Object -First 1
  if ($null -ne $reparse) { throw "Refusing temp APK cleanup target containing reparse point" }
  Remove-Item -LiteralPath $target -Recurse -Force
}
function Get-TestedInstalledPackageEvidence($Adb, $Device, $PackageId, $ExpectedSha256, $SdkRoot) {
  $evidence = Test-InstalledPackage $Adb $Device $PackageId
  if ($evidence.status -ne "present") { $evidence["binding"] = Test-TestedPackageBinding $evidence $ExpectedSha256; return $evidence }
  $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("fw-android-apk-" + [Guid]::NewGuid().ToString("N"))
  New-Item -ItemType Directory -Path $tmp | Out-Null
  try {
    $hashes = @(); $i = 0
    foreach ($devicePath in @($evidence.package_paths)) {
      $local = Join-Path $tmp ("pkg-$i.apk"); $pull = Invoke-Captured $Adb @("-s", $Device, "pull", $devicePath, $local) $desktopRoot 60
      if ($pull.exit_code -ne 0 -or !(Test-Path -LiteralPath $local)) { $evidence["status"] = "unknown"; $evidence["reason"] = "adb_pull_failed"; $evidence["binding"] = Test-TestedPackageBinding $evidence $ExpectedSha256; return $evidence }
      $hashes += @{ device_path = $devicePath; sha256 = Get-FileSha256 $local; bytes = (Get-Item -LiteralPath $local).Length }; $i += 1
    }
    $baseApk = Join-Path $tmp "pkg-0.apk"
    $evidence["apk_hashes"] = $hashes
    $evidence["version"] = Read-ApkVersion (Resolve-BuildTool $SdkRoot "aapt.exe") $baseApk
    $evidence["signing"] = Read-ApkSigning (Resolve-BuildTool $SdkRoot "apksigner.bat") $baseApk
    $evidence["binding"] = Test-TestedPackageBinding $evidence $ExpectedSha256
    return $evidence
  } finally {
    Remove-OwnedTempApkDir $tmp
  }
}
function Set-FinalTestedPackageBinding($Evidence, [string]$FinalExpectedSha256) {
  if ($null -eq $Evidence) { return $Evidence }
  if (!($Evidence -is [System.Collections.IDictionary])) { throw "Final package evidence must be a dictionary" }
  $captureBinding = Get-PropValue $Evidence "binding"
  if ($null -ne (Get-PropValue $Evidence "expected_apk_sha256") -and $null -ne $captureBinding) { $Evidence["capture_binding"] = $captureBinding }
  $Evidence["final_expected_apk_sha256"] = $FinalExpectedSha256
  $Evidence["binding"] = Test-TestedPackageBinding $Evidence $FinalExpectedSha256
  return $Evidence
}
function Select-RunnerBlocker([int]$TestExitCode, $Validation, $Binding) {
  if ($TestExitCode -ne 0) { return "flutter_test_failed" }
  if ((Get-PropValue $Validation "ok") -ne $true) { return Get-PropValue $Validation "reason" }
  if ((Get-PropValue $Binding "ok") -ne $true) { return Get-PropValue $Binding "reason" }
  return "unknown_failure"
}
function Invoke-SelfTest {
  $secret = "sentinel-android-handoff-secret"; $single = Select-AndroidDevice -Devices @(@{ id = "emulator-5554"; status = "device"; android = $true; raw = "emulator-5554 device" }) -Requested ""; $none = Select-AndroidDevice -Devices @() -Requested ""
  $duplicate = Select-AndroidDevice -Devices @(@{ id = "emulator-5554"; status = "device"; android = $true; raw = "emulator-5554 device" }, @{ id = "ZY22"; status = "device"; android = $true; raw = "ZY22 device" }) -Requested ""; $args = New-FlutterTestArgs "android_handoff_selftest" "emulator-5554"; $containsSecret = (($args -join " ") -like "*$secret*")
  if ($single.status -ne "ok" -or $none.reason -ne "no_android_device" -or $duplicate.reason -ne "multiple_android_devices") { throw "self-test device selection assertions failed" }
  $fixture = New-SelfTestFixtureReceipt "android_handoff_selftest"; $valid = Test-FixtureReceipt $fixture "android_handoff_selftest"; $invalidJson = Test-FixtureReceipt (Select-FixtureReceipt "FLYWHEEL_ANDROID_HANDOFF_RECEIPT_JSON:{bad-json") "android_handoff_selftest"
  $wrongTokenControl = New-SelfTestFixtureReceipt "android_handoff_selftest"; $wrongTokenControl.cases.wrong_token_rejected.ok = $true; $wrongToken = Test-FixtureReceipt $wrongTokenControl "android_handoff_selftest"
  $unreachableControl = New-SelfTestFixtureReceipt "android_handoff_selftest"; $unreachableControl.cases.unreachable_gateway.ok = $true; $unreachable = Test-FixtureReceipt $unreachableControl "android_handoff_selftest"
  if ((Test-FixtureReceipt $null "android_handoff_selftest").reason -ne "missing_fixture_receipt" -or $valid.ok -ne $true -or $invalidJson.reason -ne "invalid_fixture_receipt_json" -or $wrongToken.reason -ne "negative_control_not_rejected" -or $unreachable.reason -ne "negative_control_not_rejected") { throw "self-test fixture receipt control assertions failed" }
  $bat = Join-Path ([System.IO.Path]::GetTempPath()) ("fw-android-bat-" + [Guid]::NewGuid().ToString("N") + ".bat"); Set-Content -LiteralPath $bat -Value "@echo bat-ok" -Encoding ASCII
  try { $batRun = Invoke-Captured $bat @() ([System.IO.Path]::GetTempPath()) 10; if ($batRun.exit_code -ne 0 -or $batRun.stdout -notmatch "bat-ok") { throw "self-test batch launch assertion failed" } } finally { Remove-Item -LiteralPath $bat -Force -ErrorAction SilentlyContinue }
  $ps = (Get-Process -Id $PID).Path; $temp = [System.IO.Path]::GetTempPath(); $ioScript = Join-Path $temp ("fw-android-io-" + [Guid]::NewGuid().ToString("N") + ".ps1"); $timeoutScript = Join-Path $temp ("fw-android-timeout-" + [Guid]::NewGuid().ToString("N") + ".ps1"); $pollScript = Join-Path $temp ("fw-android-poll-" + [Guid]::NewGuid().ToString("N") + ".ps1"); $envScript = Join-Path $temp ("fw-android-env-" + [Guid]::NewGuid().ToString("N") + ".ps1"); $childPidFile = Join-Path $temp ("fw-android-child-" + [Guid]::NewGuid().ToString("N") + ".txt"); $childPid = -1; $childAlive = $true
  Set-Content -LiteralPath $ioScript -Encoding ASCII -Value "foreach (`$i in 1..600) { Write-Output `"out-`$i`"; [Console]::Error.WriteLine(`"err-`$i`") }"; Set-Content -LiteralPath $timeoutScript -Encoding ASCII -Value (("`$child = Start-Process -WindowStyle Hidden -FilePath $(Quote-PSLiteral $ps) -ArgumentList @('-NoProfile','-Command','Start-Sleep -Seconds 20') -PassThru", "Set-Content -LiteralPath $(Quote-PSLiteral $childPidFile) -Value `$child.Id -Encoding ASCII", "Start-Sleep -Seconds 20") -join "`n"); Set-Content -LiteralPath $pollScript -Encoding ASCII -Value "Start-Sleep -Milliseconds 900; Write-Output poll-ok"; Set-Content -LiteralPath $envScript -Encoding ASCII -Value "Write-Output `$env:FW_ANDROID_SIGNING_ENV_SELFTEST"
  try { $pollState = @{ count = 0 }; $ioRun = Invoke-Captured $ps @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $ioScript) $temp 20; $timeoutRun = Invoke-Captured $ps @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $timeoutScript) $temp 1; $pollRun = Invoke-Captured $ps @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $pollScript) $temp 10 -OnPoll { $pollState.count += 1; return @{ captured = $true; polls = $pollState.count } } -PollMilliseconds 100; $envRun = Invoke-Captured $ps @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $envScript) $temp 10 -Environment @{ FW_ANDROID_SIGNING_ENV_SELFTEST = "ok" }; Start-Sleep -Milliseconds 300; $childPid = if (Test-Path -LiteralPath $childPidFile) { [int](Get-Content -LiteralPath $childPidFile -Raw) } else { -1 }; $childAlive = if ($childPid -gt 0) { $null -ne (Get-Process -Id $childPid -ErrorAction SilentlyContinue) } else { $true }; if ($ioRun.exit_code -ne 0 -or $ioRun.stdout -notmatch "out-600" -or $ioRun.stderr -notmatch "err-600" -or $timeoutRun.exit_code -ne 124 -or $timeoutRun.timed_out -ne $true -or $childAlive -or $pollRun.exit_code -ne 0 -or $null -eq $pollRun.poll_result -or $pollRun.poll_result.captured -ne $true -or $envRun.stdout.Trim() -ne "ok") { throw "self-test process assertions failed" } } finally { if ($childPid -gt 0) { Stop-Process -Id $childPid -Force -ErrorAction SilentlyContinue }; Remove-Item -LiteralPath $ioScript,$timeoutScript,$pollScript,$envScript,$childPidFile -Force -ErrorAction SilentlyContinue }
  $absent = Convert-PackageStatus @{ exit_code = 1; stdout = ""; stderr = ""; timed_out = $false }; $present = Convert-PackageStatus @{ exit_code = 0; stdout = "package:/data/app/base.apk"; stderr = ""; timed_out = $false }; $transport = Convert-PackageStatus @{ exit_code = 255; stdout = ""; stderr = "error: device not found"; timed_out = $false }; $unauth = Convert-PackageStatus @{ exit_code = 1; stdout = ""; stderr = "error: device unauthorized"; timed_out = $false }; $offline = Convert-PackageStatus @{ exit_code = 0; stdout = ""; stderr = ""; timed_out = $false } "offline"; $diag = Convert-PackageStatus @{ exit_code = 1; stdout = ""; stderr = "cmd: permission denied"; timed_out = $false }; $malformed = Convert-PackageStatus @{ exit_code = 0; stdout = "weird"; stderr = ""; timed_out = $false }
  $javaSelf = @{ status = "ok"; source = "self_test"; java_home = "C:/selftest/jbr"; java_path = "C:/selftest/jbr/bin/java.exe" }; $digestSelf = "01:23:45:67:89:ab:cd:ef:01:23:45:67:89:ab:cd:ef:01:23:45:67:89:ab:cd:ef:01:23:45:67:89:ab:cd:ef"; $signOk = Convert-ApkSigningResult @{ exit_code = 0; stdout = "Signer #1 certificate SHA-256 digest: $digestSelf"; stderr = ""; timed_out = $false } $javaSelf; $signJavaMissing = Convert-ApkSigningResult @{ exit_code = 1; stdout = "ERROR: JAVA_HOME is not set and no 'java' command could be found in your PATH."; stderr = ""; timed_out = $false } @{ status = "missing"; reason = "java_unavailable" }; $signMissingDigest = Convert-ApkSigningResult @{ exit_code = 0; stdout = "Verified"; stderr = ""; timed_out = $false } $javaSelf
  if ($signOk.status -ne "ok" -or $signOk.certificate_sha256 -ne "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef" -or $signJavaMissing.reason -ne "java_unavailable" -or $signMissingDigest.reason -ne "missing_certificate_digest") { throw "self-test APK signing assertions failed" }
  $matching = [pscustomobject]@{ status = "present"; apk_hashes = @([pscustomobject]@{ sha256 = "abc" }); version = [pscustomobject]@{ package_name = "io.github.harperz9.flywheel" }; signing = [pscustomobject]@{ status = "ok" } }; $hashMismatch = [pscustomobject]@{ status = "present"; apk_hashes = @([pscustomobject]@{ sha256 = "def" }); version = $matching.version; signing = $matching.signing }; $missingSigning = [pscustomobject]@{ status = "present"; apk_hashes = @([pscustomobject]@{ sha256 = "abc" }); version = $matching.version; signing = [pscustomobject]@{ status = "unavailable" } }
  $drift = @{ status = "present"; apk_hashes = @(@{ sha256 = "during" }); version = @{ package_name = "io.github.harperz9.flywheel" }; signing = @{ status = "ok" }; expected_apk_sha256 = "during"; binding = Test-TestedPackageBinding @{ status = "present"; apk_hashes = @(@{ sha256 = "during" }); version = @{ package_name = "io.github.harperz9.flywheel" }; signing = @{ status = "ok" } } "during" }
  $drift = Set-FinalTestedPackageBinding $drift "final"
  $priority = @{ flutter_failure = Select-RunnerBlocker 1 @{ ok = $false; reason = "missing_fixture_receipt" } @{ ok = $false; reason = "tested_package_not_present" }; fixture_failure = Select-RunnerBlocker 0 @{ ok = $false; reason = "missing_fixture_receipt" } @{ ok = $false; reason = "tested_package_not_present" }; binding_failure = Select-RunnerBlocker 0 @{ ok = $true; reason = "ok" } @{ ok = $false; reason = "tested_package_not_present" } }
  $proof = @{ schema = $selfTestSchema; mode = "self_test"; token_material = "generated-and-redacted"; device_selection = @{ single_device = $single; no_device = $none; duplicate_device = $duplicate }; planned_flutter_test = @{ command = "flutter"; args = $args; contains_secret = $containsSecret }; fixture_validation = @{ valid = $valid; invalid_json = $invalidJson; wrong_token = $wrongToken; unreachable_endpoint = $unreachable }; process_capture = @{ stdout_stderr = @{ exit_code = $ioRun.exit_code; stdout_tail_seen = ($ioRun.stdout -match "out-600"); stderr_tail_seen = ($ioRun.stderr -match "err-600") }; timeout = @{ exit_code = $timeoutRun.exit_code; timed_out = $timeoutRun.timed_out; child_killed = (-not $childAlive) }; batch_launch_exit_code = $batRun.exit_code; environment_override = @{ exit_code = $envRun.exit_code; stdout = $envRun.stdout.Trim() }; during_run_poll = $pollRun.poll_result }; package_status = @{ absent = $absent; present = $present; transport_error = $transport; unauthorized = $unauth; offline_device = $offline; stderr_diagnostic = $diag; malformed_stdout = $malformed }; apk_signing = @{ success = $signOk; java_missing = $signJavaMissing; missing_digest = $signMissingDigest }; installed_artifact_binding = @{ matching = Test-TestedPackageBinding $matching "abc"; hash_mismatch = Test-TestedPackageBinding $hashMismatch "abc"; missing_signing = Test-TestedPackageBinding $missingSigning "abc"; postcapture_artifact_drift = $drift }; failure_priority = $priority }
  $encoded = $proof | ConvertTo-Json -Depth 16; if ($encoded -like "*$secret*") { throw "self-test receipt leaked sentinel token" }; Write-JsonFile $ReceiptPath $proof; Write-Output "Android handoff runner self-test passed"
}
if ($SelfTest) {
  Invoke-SelfTest
  exit 0
}
$runId = New-RunId
$sdkRoot = Get-AndroidSdkRoot
$flutter = Resolve-Tool $FlutterPath @("flutter") @("C:/flutter/bin/flutter.bat")
$adb = Resolve-Tool $AdbPath @("adb") @(
  (Join-Path (Join-Path $env:LOCALAPPDATA "Android/Sdk") "platform-tools/adb.exe")
)
$emulator = Resolve-Tool $EmulatorPath @("emulator") @(
  (Join-Path (Join-Path $env:LOCALAPPDATA "Android/Sdk") "emulator/emulator.exe")
)
$receipt = @{
  schema = $schema
  run_id = $runId
  timestamp_utc = [DateTimeOffset]::UtcNow.ToString("o")
  scope = "source integration_test fixture; not installed production app acceptance"
  token_material = "generated inside integration test and redacted from argv, stdout receipt, and runner receipt"
  source = Get-SourceIdentity
  tools = @{
    flutter = @{ path = $flutter; sha256 = Get-FileSha256 $flutter }
    adb = @{ path = $adb; sha256 = Get-FileSha256 $adb }
    emulator = @{ path = $emulator; sha256 = Get-FileSha256 $emulator }
    android_sdk_root = $sdkRoot
    installed_system_images = Get-InstalledSystemImages $sdkRoot
  }
  status = "blocked"
  limits = @(
    "does not install the operator release app",
    "does not call model providers or live Relay/Plexus services",
    "requires a connected Android device or already-created Android emulator"
  )
}
if ($null -eq $flutter -or $null -eq $adb) {
  $receipt.blocker = "missing_flutter_or_adb"
  Write-JsonFile $ReceiptPath $receipt
  throw "Flutter or adb was not found; receipt written if ReceiptPath was provided."
}
$adbDevices = Invoke-Captured $adb @("devices", "-l") $desktopRoot 30
$adbDeviceErrors = @(([string]$adbDevices.stderr -split "`r?`n") | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" -and !$_.StartsWith("* daemon") })
$devices = Convert-AdbDevices $adbDevices.stdout
$selection = Select-AndroidDevice -Devices $devices -Requested $DeviceId
$receipt.device = @{
  adb_devices_exit = $adbDevices.exit_code
  adb_devices = $devices
  selection = $selection
  stderr_tail = Get-Tail ($adbDeviceErrors -join "`n") $DeviceId
}
if ($adbDevices.exit_code -ne 0 -or $adbDeviceErrors.Count -gt 0) {
  $receipt.blocker = "adb_devices_failed"
  Write-JsonFile $ReceiptPath $receipt
  throw "Android device preflight blocked: adb devices failed"
}
if ($selection.status -ne "ok") {
  $receipt.blocker = $selection.reason
  Write-JsonFile $ReceiptPath $receipt
  throw "Android device preflight blocked: $($selection.reason)"
}
$applicationId = Get-AndroidApplicationId
$package = Test-InstalledPackage $adb $selection.id $applicationId
$receipt.android_package = @{
  application_id = $applicationId
  before = $package
}
if ($package.installed) {
  $receipt.blocker = "package_already_installed"
  Write-JsonFile $ReceiptPath $receipt
  throw "Android package already installed; refusing to replace operator app data."
}
if ($package.status -ne "absent" -or $package.verified_absent -ne $true) {
  $receipt.blocker = "package_absence_unverified"
  Write-JsonFile $ReceiptPath $receipt
  throw "Android package absence was not verified; refusing install/test."
}
Push-Location $desktopRoot
try {
  $build = Invoke-Captured $flutter @("build", "apk", "--debug") $desktopRoot
  $apk = Join-Path $desktopRoot "build/app/outputs/flutter-apk/app-debug.apk"
  $receipt.apk = @{
    build_exit_code = $build.exit_code
    path = $apk
    sha256 = Get-FileSha256 $apk
    bytes = if (Test-Path -LiteralPath $apk) { (Get-Item -LiteralPath $apk).Length } else { $null }
    diagnostics = @{ stdout_tail = Get-Tail $build.stdout $selection.id; stderr_tail = Get-Tail $build.stderr $selection.id; timed_out = $build.timed_out }
  }
  if ($build.exit_code -ne 0) {
    $receipt.blocker = "flutter_build_apk_failed"
    Write-JsonFile $ReceiptPath $receipt
    exit $build.exit_code
  }
  $args = New-FlutterTestArgs $runId $selection.id
  $captureState = @{ samples = 0 }
  $test = Invoke-Captured $flutter $args $desktopRoot 900 -OnPoll {
    $captureState.samples += 1
    $pollStartedUtc = [DateTimeOffset]::UtcNow.ToString("o")
    $evidence = Get-TestedInstalledPackageEvidence $adb $selection.id $applicationId $null $sdkRoot
    if ($evidence.status -eq "present") {
      $evidence["capture_started_before_flutter_exit_observed"] = $true
      $evidence["capture_poll_started_utc"] = $pollStartedUtc
      $evidence["capture_poll_completed_utc"] = [DateTimeOffset]::UtcNow.ToString("o")
      $evidence["expected_apk_sha256"] = $null
      $evidence["expected_apk_sha256_status"] = "not_read_during_flutter_test"
      $evidence["poll_samples"] = $captureState.samples
      return $evidence
    }
    return $null
  } -PollMilliseconds 1000
  $postTestApkSha = Get-FileSha256 $apk
  $receipt.apk["post_flutter_test_sha256"] = $postTestApkSha
  $receipt.apk["role"] = "pretest build and post-test artifact path; pass requires installed package hash binding captured while Flutter test is running or still installed afterward"
  $receipt.post_run_package_after_flutter_test = Get-TestedInstalledPackageEvidence $adb $selection.id $applicationId $postTestApkSha $sdkRoot
  $selectedPackage = if ($null -ne $test.poll_result) { $test.poll_result } else { $receipt.post_run_package_after_flutter_test }
  $receipt.tested_installed_package = Set-FinalTestedPackageBinding $selectedPackage $postTestApkSha
  $fixture = Select-FixtureReceipt $test.stdout
  $receipt.flutter_test = @{
    exit_code = $test.exit_code
    args = $args
    fixture_receipt_seen = $null -ne $fixture
    package_capture = @{ captured_during_run = $null -ne $test.poll_result; poll_samples = $captureState.samples; poll_error = $test.poll_error }
    diagnostics = @{ stdout_tail = Get-Tail $test.stdout $selection.id; stderr_tail = Get-Tail $test.stderr $selection.id; timed_out = $test.timed_out }
  }
  $receipt.fixture_receipt = $fixture
  $validation = Test-FixtureReceipt $fixture $runId
  $receipt.fixture_validation = $validation
  $binding = $receipt.tested_installed_package.binding
  $receipt.status = if ($test.exit_code -eq 0 -and $validation.ok -and $binding.ok) { "passed" } else { "failed" }
  if ($test.stdout -like "*sentinel-android-handoff-secret*" -or $test.stderr -like "*sentinel-android-handoff-secret*") {
    $receipt.status = "failed"
    $receipt.blocker = "sentinel_secret_leaked"
  }
  if ($receipt.status -ne "passed" -and !$receipt.ContainsKey("blocker")) { $receipt.blocker = Select-RunnerBlocker $test.exit_code $validation $binding }
  Write-JsonFile $ReceiptPath $receipt
  if ($receipt.status -ne "passed" -and $test.exit_code -eq 0) { exit 1 }
  exit $test.exit_code
} finally {
  Pop-Location
}
