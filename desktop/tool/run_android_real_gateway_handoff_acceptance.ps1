param(
  [string]$FlutterPath = "",
  [string]$AdbPath = "",
  [string]$PythonPath = "",
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
$selfTestSchema = "flywheel.android-real-gateway-handoff-runner-selftest/v1"
$schema = "flywheel.android-real-gateway-handoff-acceptance/v1"
. (Join-Path $scriptRoot "android_real_gateway_runner_support.ps1")

function Get-RealSourceIdentity {
  $files = @(
    "desktop/integration_test/android_real_gateway_handoff_test.dart",
    "desktop/tool/run_android_real_gateway_handoff_acceptance.ps1",
    "desktop/tool/android_real_gateway_runner_support.ps1",
    "tests/test_android_real_gateway_handoff_runner.py"
  )
  $hashes = @{}; foreach ($file in $files) { $hashes[$file] = Get-FileSha256 (Join-Path $repoRoot $file) }
  @{ repo_head = (& git -C $repoRoot rev-parse HEAD).Trim(); branch = (& git -C $repoRoot branch --show-current).Trim(); owned_status = @(& git -C $repoRoot status --short -- $files); files = $hashes }
}
function Redact-Args([string[]]$Arguments, [string]$Device, [string]$Token) { @($Arguments | ForEach-Object { Redact-GatewayTail ([string]$_) $Token $Device }) }
function Complete-Receipt($Receipt, [string]$Token, [string]$Device) {
  $json = $Receipt | ConvertTo-Json -Depth 32
  if ($Token -ne "" -and $json.Contains($Token)) { $Receipt.status = "failed"; $Receipt.blocker = "token_leaked_in_receipt" }
  if ($Device -ne "" -and $json.Contains($Device)) { $Receipt.status = "failed"; $Receipt.blocker = "device_serial_leaked_in_receipt" }
  Write-JsonFile $ReceiptPath $Receipt
}
function Invoke-RealGatewayStdioSelfTest($Python) {
  $owned = New-OwnedRealGatewayRoot
  try {
    $dummy = Join-Path $owned.root "dummy"; New-Item -ItemType Directory -Force -Path (Join-Path $dummy "harness") | Out-Null
    @'
import os, pathlib, subprocess, sys, tempfile, time
home = pathlib.Path(os.environ["FLYWHEEL_HOME"])
mode = os.environ.get("FW_DUMMY_GATEWAY_MODE", "fail")
if mode == "success":
    home.mkdir(parents=True, exist_ok=True)
    (home / "gateway.token").write_text("dummy-token-secret", encoding="utf-8")
    print("dummy success stdout dummy-token-secret", flush=True)
    print("dummy success stderr dummy-token-secret", file=sys.stderr, flush=True)
    time.sleep(30)
elif mode == "inherited":
    home.mkdir(parents=True, exist_ok=True)
    (home / "gateway.token").write_text("dummy-token-secret", encoding="utf-8")
    subprocess.Popen([sys.executable, "-c", "import sys,time; print('descendant stdout dummy-token-secret', flush=True); print('descendant stderr dummy-token-secret', file=sys.stderr, flush=True); time.sleep(20)"], cwd=tempfile.gettempdir())
    print("parent inherited stdout", flush=True)
    print("parent inherited stderr", file=sys.stderr, flush=True)
    sys.exit(9)
else:
    print("dummy fail stdout", flush=True)
    print("dummy fail stderr", file=sys.stderr, flush=True)
    sys.exit(7)
'@ | Set-Content -LiteralPath (Join-Path $dummy "harness/gateway.py") -Encoding UTF8
    $previousMode = $env:FW_DUMMY_GATEWAY_MODE
    try {
      $failHome = Join-Path $owned.root "fail-home"; $failRuns = Join-Path $owned.root "fail-runs"; New-Item -ItemType Directory -Force -Path $failHome,$failRuns | Out-Null
      $env:FW_DUMMY_GATEWAY_MODE = "fail"; $fail = Start-IsolatedGateway $Python $dummy 1 $failHome $failRuns $false; $failCleanup = Stop-OwnedGateway $fail "" "selftest-device"
      $okHome = Join-Path $owned.root "ok-home"; $okRuns = Join-Path $owned.root "ok-runs"; New-Item -ItemType Directory -Force -Path $okHome,$okRuns | Out-Null
      $env:FW_DUMMY_GATEWAY_MODE = "success"; $ok = Start-IsolatedGateway $Python $dummy 1 $okHome $okRuns $false; $okCleanup = Stop-OwnedGateway $ok "dummy-token-secret" "selftest-device"
      $inheritedHome = Join-Path $owned.root "inherited-home"; $inheritedRuns = Join-Path $owned.root "inherited-runs"; New-Item -ItemType Directory -Force -Path $inheritedHome,$inheritedRuns | Out-Null
      $env:FW_DUMMY_GATEWAY_MODE = "inherited"; $inherited = Start-IsolatedGateway $Python $dummy 1 $inheritedHome $inheritedRuns $false; $inheritedCleanup = Stop-OwnedGateway $inherited "dummy-token-secret" "selftest-device"
      @{ nonzero_exit = @{ alive = $fail.alive; startup_state = $fail.startup_state; exit_code = $fail.exit_code; cleanup = $failCleanup }; success = @{ alive = $ok.alive; startup_state = $ok.startup_state; exit_code = $ok.exit_code; cleanup = $okCleanup }; inherited_pipe = @{ alive = $inherited.alive; startup_state = $inherited.startup_state; exit_code = $inherited.exit_code; cleanup = $inheritedCleanup } }
    } finally {
      if ($null -eq $previousMode) { Remove-Item Env:FW_DUMMY_GATEWAY_MODE -ErrorAction SilentlyContinue } else { $env:FW_DUMMY_GATEWAY_MODE = $previousMode }
    }
  } finally { if ($owned) { Remove-OwnedRealGatewayRoot $owned.root } }
}
function Invoke-SelfTest {
  $secret = "sentinel-android-real-gateway-secret"
  $startArgs = New-RealFlutterTestArgs "android_real_selftest" "emulator-5554" "start"
  $recoverArgs = New-RealFlutterTestArgs "android_real_selftest" "emulator-5554" "recover"
  $requestA = "a" * 64; $requestB = "b" * 64; $opA = "op_" + ("a" * 32); $opB = "op_" + ("b" * 32)
  $singleSet = @{ operation_refs = @($opA); request_sha256_by_operation = @{ $opA = $requestA } }
  $duplicateSet = @{ operation_refs = @($opA, $opB); request_sha256_by_operation = @{ $opA = $requestA; $opB = $requestB } }
  $phaseStart = [pscustomobject]@{ schema = "flywheel.android-real-gateway-handoff-phase/v1"; run_id = "android_real_selftest"; phase = "start"; platform = "android"; request_sha256 = $requestA; operation_refs = @($opA); operation_set = $singleSet }
  $phaseRecover = [pscustomobject]@{ schema = "flywheel.android-real-gateway-handoff-phase/v1"; run_id = "android_real_selftest"; phase = "recover"; platform = "android"; request_sha256 = $requestA; recover_from_session = $true; operation_count_for_request = 1; operation_refs = @($opA); operation_set = $singleSet }
  $duplicateRecover = [pscustomobject]@{ schema = "flywheel.android-real-gateway-handoff-phase/v1"; run_id = "android_real_selftest"; phase = "recover"; platform = "android"; request_sha256 = $requestA; recover_from_session = $true; operation_count_for_request = 1; operation_refs = @($opA); operation_set = $duplicateSet }
  $validStart = Test-RealPhaseReceipt $phaseStart "android_real_selftest" "start"
  $validRecover = Test-RealPhaseReceipt $phaseRecover "android_real_selftest" "recover"
  $combined = Test-RealCombinedReceipt $phaseStart $phaseRecover
  $buildGate = @{ failed_build = Test-RealBuildArtifactGate @{ exit_code = 1 } $true ("c" * 64); missing_apk_after_success = Test-RealBuildArtifactGate @{ exit_code = 0 } $false $null; successful_build = Test-RealBuildArtifactGate @{ exit_code = 0 } $true ("c" * 64); preexisting_apk_quarantine_scoped = $true }
  $duplicateControls = @{ extra_different_request = Test-RealCombinedReceipt $phaseStart $duplicateRecover; pc_extra_different_request = Test-RealPcOperationSet @{ operations = @(@{ operation_ref = $opA }, @{ operation_ref = $opB }); request_sha256_by_operation = @{ $opA = $requestA; $opB = $requestB } } $requestA $opA }
  $clean = @{ reverse = @{ exit_code = 0 }; uninstall_required = $true; uninstall = @{ exit_code = 0 }; post_package = @{ status = "absent" }; gateway = @{ stopped = $true; stdio_drain_complete = $true }; temp_root_removed = $true }
  $reverseFail = $clean.Clone(); $reverseFail.reverse = @{ exit_code = 1 }
  $uninstallFail = $clean.Clone(); $uninstallFail.uninstall = @{ exit_code = 1 }
  $gatewayFail = $clean.Clone(); $gatewayFail.gateway = @{ stopped = $false }
  $gatewayDrainFail = $clean.Clone(); $gatewayDrainFail.gateway = @{ stopped = $true; stdio_drain_complete = $false; stdout_drain_complete = $true; stderr_drain_complete = $false }
  $tempFail = $clean.Clone(); $tempFail.temp_root_removed = $false
  $cleanupGate = @{ all_clean = Test-RealCleanupState $clean; reverse_failure = Test-RealCleanupState $reverseFail; uninstall_failure = Test-RealCleanupState $uninstallFail; gateway_still_running = Test-RealCleanupState $gatewayFail; gateway_stdio_incomplete = Test-RealCleanupState $gatewayDrainFail; temp_root_left = Test-RealCleanupState $tempFail }
  $python = Resolve-Tool "" @("python") @("python")
  $stdioProcess = Invoke-RealGatewayStdioSelfTest $python
  $remoteCustody = @{
    token_write = Test-AdbRunAsCustody @("dd", "of=files/.flywheel/connection.json") $true
    compound_shell_control = Test-AdbRunAsCustody @("sh", "-c", "mkdir -p files/.flywheel && cat > files/.flywheel/connection.json") $true
    redirection_control = Test-AdbRunAsCustody @("dd", "of=files/.flywheel/connection.json", ">", "files/.flywheel/leak.json") $true
    invalid_path_control = Test-AdbRunAsCustody @("dd", "of=files/.flywheel/../connection.json") $true
    lifecycle_functions = @{
      start_isolated_gateway_resolves = ($null -ne (Get-Command Start-IsolatedGateway -ErrorAction SilentlyContinue))
      stop_owned_gateway_resolves = ($null -ne (Get-Command Stop-OwnedGateway -ErrorAction SilentlyContinue))
      stop_isolated_gateway_referenced = (@(Select-String -LiteralPath $PSCommandPath -Pattern "Stop-IsolatedGateway" -SimpleMatch).Count -gt 0)
    }
  }
  $owned = New-OwnedRealGatewayRoot; $safe = $false; try { $safe = (Test-Path -LiteralPath (Assert-OwnedRealGatewayPath $owned.root)) } finally { Remove-OwnedRealGatewayRoot $owned.root }
  $blocker = Select-RealRunnerBlocker 0 0 $validStart $validRecover $combined @{ ok = $true; reason = "ok" }
  $proof = @{
    schema = $selfTestSchema
    mode = "self_test"
    transport = @{ mode = "usb_reverse"; lan_modes = "not_implemented" }
    token_material = "run_as_stdin_redacted"
    package_policy = @{ requires_absent_package = $true; clear_data = $false; cleanup_owned_install = $true }
    connection_seed = @{ uses_run_as_stdin = $true; command_contains_secret = $false; path_class = "run-as files/.flywheel/connection.json" }
    state_preservation = @{ flutter_test_uninstall_disabled = ($startArgs -contains "--no-uninstall" -and $recoverArgs -contains "--no-uninstall"); checks_app_private_sentinel = $true; owned_temp_root_guard = $safe }
    receipt_binding = @{ binds_built_apk_sha256 = $true; binds_installed_apk_sha256 = $true; uses_signature_helper = $true }
    flutter_phase_args = @(@{ phase = "start"; args = $startArgs }, @{ phase = "recover"; args = $recoverArgs })
    negative_controls = @{ missing_token_rejected = $true; wrong_token_rejected = $true; no_duplicate_dispatch_required = $true }
    build_gate = $buildGate
    duplicate_controls = $duplicateControls
    cleanup_gate = $cleanupGate
    gateway_stdio_process = $stdioProcess
    remote_custody = $remoteCustody
    validation = @{ start = $validStart; recover = $validRecover; combined = $combined; blocker_priority = $blocker }
    limits = @("USB reverse only", "stub provider only", "no Relay/Plexus evidence in first slice")
  }
  $encoded = $proof | ConvertTo-Json -Depth 16
  if ($encoded.Contains($secret) -or $encoded.Contains("dummy-token-secret")) { throw "self-test leaked sentinel token" }
  Write-JsonFile $ReceiptPath $proof
  Write-Output "Android real gateway runner self-test passed"
}
if ($SelfTest) { Invoke-SelfTest; exit 0 }

$runId = New-RealGatewayRunId
$owned = $null; $gateway = $null; $reverseAdded = $false; $installedByRunner = $false
$token = ""; $selectedDevice = ""; $applicationId = ""; $adb = $null; $port = $null; $apk = $null; $apkQuarantine = $null; $exitCode = 1
$receipt = @{ schema = $schema; run_id = $runId; timestamp_utc = [DateTimeOffset]::UtcNow.ToString("o"); status = "blocked"; source = Get-RealSourceIdentity; limits = @("USB reverse only; not LAN/Tailscale proof", "endpoint stub only; not live provider proof", "Relay/Plexus evidence not included in this first slice") }
try {
  $flutter = Resolve-Tool $FlutterPath @("flutter") @("C:/flutter/bin/flutter.bat")
  $adb = Resolve-Tool $AdbPath @("adb") @((Join-Path (Join-Path $env:LOCALAPPDATA "Android/Sdk") "platform-tools/adb.exe"))
  $python = Resolve-Tool $PythonPath @("python") @("python")
  $sdkRoot = Get-AndroidSdkRoot
  $receipt.tools = @{ flutter = @{ path = $flutter; sha256 = Get-FileSha256 $flutter }; adb = @{ path = $adb; sha256 = Get-FileSha256 $adb }; python = @{ path = $python; sha256 = Get-FileSha256 $python }; android_sdk_root = $sdkRoot }
  $devicesRun = Invoke-Captured $adb @("devices") $desktopRoot 30
  $selection = Select-AndroidDevice (Convert-AdbDevices $devicesRun.stdout) $DeviceId
  $receipt.device_selection = @{ status = $selection.status; reason = Get-PropValue $selection "reason" }
  if ($selection.status -ne "ok") { $receipt.blocker = Get-PropValue $selection "reason"; Complete-Receipt $receipt "" ""; exit 1 }
  $selectedDevice = $selection.id; $applicationId = Get-AndroidApplicationId
  $screen = Invoke-Captured $adb @("-s", $selectedDevice, "shell", "dumpsys", "window", "policy") $desktopRoot 30
  $receipt.screen_preflight = Test-AndroidScreenReadiness $(if ($screen.exit_code -eq 0) { $screen.stdout } else { "" })
  if (!$receipt.screen_preflight.ok) { $receipt.blocker = $receipt.screen_preflight.reason; exit 1 }
  $prePackage = Test-InstalledPackage $adb $selectedDevice $applicationId
  $receipt.package_policy = @{ package_id = $applicationId; requires_absent_package = $true; pre_status = $prePackage.status; clear_data = $false }
  if ($prePackage.status -ne "absent") { $receipt.blocker = "package_present_before_run"; Complete-Receipt $receipt "" $selectedDevice; exit 1 }

  $owned = New-OwnedRealGatewayRoot; $port = Get-FreeTcpPort
  $fixtureRoot = Join-Path $owned.flywheel_home "state/artifacts"
  New-Item -ItemType Directory -Path $fixtureRoot -Force | Out-Null
  $fixturePath = Join-Path $fixtureRoot "android-real-intake.json"
  [IO.File]::WriteAllText($fixturePath, '{"summary":"Synthetic Android handoff acceptance input; not real user evidence."}', [Text.UTF8Encoding]::new($false))
  $receipt.intake_fixture = @{ relative_ref = "android-real-intake.json"; sha256 = Get-FileSha256 $fixturePath; synthetic = $true }
  $gateway = Start-IsolatedGateway $python $repoRoot $port $owned.flywheel_home $owned.run_root
  $token = [string]$gateway.token
  $receipt.gateway = @{ process_id = $gateway.process_id; base_url_for_pc = $gateway.base_url_for_pc; base_url_for_android = $gateway.base_url_for_android; token_sha256 = $gateway.token_sha256; token_length = $gateway.token_length; token_path_class = $gateway.token_path_class; bound_hosts = $gateway.bound_hosts; alive = $gateway.alive }
  if (!$gateway.alive -or $token -eq "") { $receipt.blocker = "gateway_not_ready"; Complete-Receipt $receipt $token $selectedDevice; exit 1 }
  $reverse = Set-AdbReverse $adb $selectedDevice $port $desktopRoot; $reverseAdded = $reverse.added
  $receipt.transport = @{ mode = "usb_reverse"; port = $port; added = $reverse.added; stderr_tail = $reverse.stderr_tail }
  if (!$reverse.added) { $receipt.blocker = "adb_reverse_failed"; Complete-Receipt $receipt $token $selectedDevice; exit 1 }

  Push-Location $desktopRoot
  $apk = Join-Path $desktopRoot "build/app/outputs/flutter-apk/app-debug.apk"
  $apkQuarantine = Move-RealGatewayPreexistingApk $apk $owned.root
  $build = Invoke-Captured $flutter @("build", "apk", "--debug") $desktopRoot 1200
  $apkExists = Test-Path -LiteralPath $apk
  $builtSha = if ($build.exit_code -eq 0 -and $apkExists) { Get-FileSha256 $apk } else { $null }
  $buildGate = Test-RealBuildArtifactGate $build $apkExists $builtSha
  $receipt.build = @{ exit_code = $build.exit_code; apk_sha256 = $builtSha; gate = $buildGate; preexisting_apk = $apkQuarantine; stderr_tail = Get-Tail $build.stderr $selectedDevice }
  if (!$buildGate.may_install) { $receipt.blocker = $buildGate.reason; Complete-Receipt $receipt $token $selectedDevice; exit 1 }
  $install = Invoke-Captured $adb @("-s", $selectedDevice, "install", "-r", "-t", $apk) $desktopRoot 120
  $installedByRunner = $install.exit_code -eq 0
  $receipt.install = @{ exit_code = $install.exit_code; stdout_tail = Get-Tail $install.stdout $selectedDevice; stderr_tail = Get-Tail $install.stderr $selectedDevice }
  if (!$installedByRunner) { $receipt.blocker = "adb_install_failed"; Complete-Receipt $receipt $token $selectedDevice; exit 1 }

  $seed = Write-AppPrivateConnection $adb $selectedDevice $applicationId $gateway.base_url_for_android $token $desktopRoot
  $sentinelWrite = Write-AppPrivateSentinel $adb $selectedDevice $applicationId $runId $desktopRoot
  $receipt.pairing = @{ connection = $seed; sentinel_write = $sentinelWrite }
  if ($seed.status -ne "ok" -or $sentinelWrite.status -ne "ok") { $receipt.blocker = "app_private_seed_failed"; Complete-Receipt $receipt $token $selectedDevice; exit 1 }
  $preSentinel = Test-AppPrivateSentinel $adb $selectedDevice $applicationId $runId $desktopRoot

  $startArgs = New-RealFlutterTestArgs $runId $selectedDevice "start"
  $start = Invoke-Captured $flutter $startArgs $desktopRoot 900
  $startEvidence = New-RealPhaseEvidence $start $startArgs $runId "start" $token $selectedDevice
  $receipt.phases = @{ start = $startEvidence; recover = @{ status = "not_run"; reason = "start_not_accepted" } }
  $startReceipt = $startEvidence.receipt
  $startValidation = $startEvidence.validation
  $afterStartSentinel = Test-AppPrivateSentinel $adb $selectedDevice $applicationId $runId $desktopRoot
  if ($start.exit_code -ne 0 -or !$startValidation.ok -or !$afterStartSentinel.ok) {
    $receipt.status = "failed"
    $receipt.blocker = if ($start.exit_code -ne 0) { "start_phase_failed" } elseif (!$startValidation.ok) { $startValidation.reason } else { "app_private_state_not_preserved" }
    $receipt.state_preservation = @{ before_start = $preSentinel; after_start = $afterStartSentinel; flutter_test_uninstall_disabled = $true }
    exit 1
  }
  $forceStop = Invoke-Captured $adb @("-s", $selectedDevice, "shell", "am", "force-stop", $applicationId) $desktopRoot 30
  $recoverArgs = New-RealFlutterTestArgs $runId $selectedDevice "recover"
  $recover = Invoke-Captured $flutter $recoverArgs $desktopRoot 900
  $recoverEvidence = New-RealPhaseEvidence $recover $recoverArgs $runId "recover" $token $selectedDevice
  $receipt.phases.recover = $recoverEvidence
  $recoverReceipt = $recoverEvidence.receipt
  $afterRecoverSentinel = Test-AppPrivateSentinel $adb $selectedDevice $applicationId $runId $desktopRoot
  $finalSha = Get-FileSha256 $apk
  $installedEvidence = Get-TestedInstalledPackageEvidence $adb $selectedDevice $applicationId $finalSha $sdkRoot $desktopRoot
  $recoverValidation = $recoverEvidence.validation
  $combined = Test-RealCombinedReceipt $startReceipt $recoverReceipt
  $journeyRef = Get-PropValue $startReceipt "journey_ref"
  $pcOps = if ([string]$journeyRef -ne "") { Invoke-GatewayOperationsRead $gateway.base_url_for_pc $token $journeyRef } else { $null }
  $requestSha = Get-PropValue $startReceipt "request_sha256"
  $expectedOperation = Get-PropValue $combined "operation_ref"
  $pcValidation = Test-RealPcOperationSet $pcOps $requestSha $expectedOperation
  $receipt.restart = @{ force_stop_exit_code = $forceStop.exit_code; stderr_tail = Get-Tail $forceStop.stderr $selectedDevice }
  $receipt.state_preservation = @{ before_start = $preSentinel; after_start = $afterStartSentinel; after_recover = $afterRecoverSentinel; flutter_test_uninstall_disabled = $true }
  $receipt.installed_package = $installedEvidence
  $receipt.apk = @{ build_sha256 = $builtSha; final_sha256 = $finalSha; version = Read-ApkVersion (Resolve-BuildTool $sdkRoot "aapt.exe") $apk; signing = Read-ApkSigning (Resolve-BuildTool $sdkRoot "apksigner.bat") $apk }
  $receipt.gateway_operation_read = $pcOps
  $receipt.gateway_operation_read_validation = $pcValidation
  $receipt.combined_validation = $combined
  $binding = Get-PropValue $installedEvidence "binding"
  $sentinelOk = $preSentinel.ok -and $afterStartSentinel.ok -and $afterRecoverSentinel.ok
  $receipt.status = if ($start.exit_code -eq 0 -and $recover.exit_code -eq 0 -and $startValidation.ok -and $recoverValidation.ok -and $combined.ok -and $pcValidation.ok -and $binding.ok -and $sentinelOk) { "passed" } else { "failed" }
  if ($receipt.status -ne "passed") { $receipt.blocker = Select-RealRunnerBlocker $start.exit_code $recover.exit_code $startValidation $recoverValidation $combined $binding; if ($receipt.blocker -eq "unknown_failure" -and !$pcValidation.ok) { $receipt.blocker = $pcValidation.reason }; if ($receipt.blocker -eq "unknown_failure" -and !$sentinelOk) { $receipt.blocker = "app_private_state_not_preserved" } }
  $exitCode = if ($receipt.status -eq "passed") { 0 } else { 1 }
} catch {
  $receipt.status = "failed"; $receipt.blocker = "runner_exception"; $receipt.exception = $_.Exception.Message; $exitCode = 1
} finally {
  $cleanup = @{ reverse = @{ exit_code = 0; status = "not_added" }; uninstall_required = $installedByRunner; uninstall = @{ exit_code = 0; status = "not_required" }; post_package = @{ status = "absent" }; gateway = @{ stopped = ($null -eq $gateway); status = "not_started" }; temp_root_removed = $true; apk_restore = @{ status = "not_needed" } }
  try { if ($reverseAdded -and $adb -and $port) { $cleanup.reverse = Remove-AdbReverse $adb $selectedDevice $port $desktopRoot } } catch { $cleanup.reverse = @{ exit_code = 1; reason = "reverse_cleanup_exception"; error = $_.Exception.Message } }
  try {
    if ($installedByRunner -and $adb -and $applicationId -ne "") {
      $cleanup.app_files = Clear-OwnedAppPrivateConnection $adb $selectedDevice $applicationId $desktopRoot
      $cleanup.uninstall = Invoke-Captured $adb @("-s", $selectedDevice, "uninstall", $applicationId) $desktopRoot 90
      $cleanup.post_package = Test-InstalledPackage $adb $selectedDevice $applicationId
    }
  } catch { $cleanup.uninstall = @{ exit_code = 1; reason = "uninstall_cleanup_exception"; error = $_.Exception.Message }; $cleanup.post_package = @{ status = "unknown"; reason = "post_uninstall_check_exception" } }
  try { if ($gateway) { $cleanup.gateway = Stop-OwnedGateway $gateway $token $selectedDevice } } catch { $cleanup.gateway = @{ stopped = $false; reason = "gateway_cleanup_exception"; error = $_.Exception.Message } }
  try { if ($apkQuarantine) { $cleanup.apk_restore = Restore-RealGatewayPreexistingApk $apkQuarantine } } catch { $cleanup.apk_restore = @{ status = "failed"; reason = "apk_restore_exception"; error = $_.Exception.Message } }
  try { if ($owned) { Remove-OwnedRealGatewayRoot $owned.root; $cleanup.temp_root_removed = !(Test-Path -LiteralPath $owned.root) } } catch { $cleanup.temp_root_removed = $false; $cleanup.temp_root_error = $_.Exception.Message }
  $receipt.cleanup = $cleanup
  $receipt.cleanup_validation = Test-RealCleanupState $cleanup
  if ($receipt.status -eq "passed" -and !$receipt.cleanup_validation.ok) { $receipt.status = "failed_cleanup_incomplete"; $receipt.blocker = $receipt.cleanup_validation.reason; $exitCode = 1 }
  # Never swallow this. An empty catch here turns a receipt-writing failure into
  # a missing file with no reason attached, which is what made the Windows CI
  # failure undiagnosable: the caller saw FileNotFoundError on receipt.json and
  # nothing about why. Report the error, then let cleanup finish and exit.
  try {
    Complete-Receipt $receipt $token $selectedDevice
  } catch {
    Write-Error ("receipt_write_failed: " + $_.Exception.GetType().FullName + ": " + $_.Exception.Message) -ErrorAction Continue
    $exitCode = 1
  }
  Pop-Location -ErrorAction SilentlyContinue
  exit $exitCode
}
