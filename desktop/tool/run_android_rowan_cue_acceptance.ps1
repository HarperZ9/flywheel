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
$selfTestSchema = "flywheel.android-rowan-cue-runner-selftest/v1"
$schema = "flywheel.android-rowan-cue-acceptance/v1"
. (Join-Path $scriptRoot "android_real_gateway_runner_support.ps1")

function New-RowanRunId { "android_rowan_" + [DateTimeOffset]::UtcNow.ToString("yyyyMMddTHHmmssZ") + "_" + [Guid]::NewGuid().ToString("N").Substring(0, 8) }
function New-RowanFlutterTestArgs($RunId, $SelectedDevice, [ValidateSet("start", "recover")]$Phase) {
  @(
    "test",
    "integration_test/android_rowan_cue_acceptance_test.dart",
    "-d",
    $SelectedDevice,
    "--no-uninstall",
    "--dart-define=FLYWHEEL_ANDROID_ROWAN_CUE_PHASE=$Phase",
    "--dart-define=FLYWHEEL_ANDROID_ROWAN_CUE_RUN_ID=$RunId"
  )
}
function Select-RowanPhaseReceipt($Stdout) {
  $prefix = "FLYWHEEL_ANDROID_ROWAN_CUE_RECEIPT_JSON:"
  foreach ($line in ($Stdout -split "`r?`n")) {
    if ($line.StartsWith($prefix)) {
      try { return ($line.Substring($prefix.Length) | ConvertFrom-Json -ErrorAction Stop) }
      catch { return [pscustomobject]@{ invalid_phase_receipt = $true; parse_error = $_.Exception.Message } }
    }
  }
  $null
}
function Test-RowanPhaseReceipt($Receipt, $RunId, [string]$Phase) {
  if ($null -eq $Receipt) { return @{ ok = $false; reason = "missing_phase_receipt" } }
  if ((Get-PropValue $Receipt "invalid_phase_receipt") -eq $true) { return @{ ok = $false; reason = "invalid_phase_receipt_json" } }
  if ((Get-PropValue $Receipt "schema") -ne "flywheel.android-rowan-cue-acceptance-phase/v1") { return @{ ok = $false; reason = "schema_mismatch" } }
  if ((Get-PropValue $Receipt "run_id") -ne $RunId -or (Get-PropValue $Receipt "phase") -ne $Phase) { return @{ ok = $false; reason = "phase_identity_mismatch" } }
  if ((Get-PropValue $Receipt "platform") -ne "android") { return @{ ok = $false; reason = "platform_not_android" } }
  if ((Get-PropValue (Get-PropValue $Receipt "connection") "token_sha256") -eq "") { return @{ ok = $false; reason = "missing_token_hash" } }
  if ($Phase -eq "start") {
    if ((Get-PropValue (Get-PropValue $Receipt "rowan_controls") "enabled_after_opt_in") -ne $true) { return @{ ok = $false; reason = "rowan_opt_in_not_enabled" } }
    $operationCue = Get-PropValue $Receipt "operation_cue"
    if ((Get-PropValue $operationCue "caption_strip_visible") -ne $true) { return @{ ok = $false; reason = "caption_strip_not_visible" } }
    if ([int](Get-PropValue $operationCue "telemetry_count") -lt 1) { return @{ ok = $false; reason = "missing_rowan_telemetry" } }
    if ((Get-PropValue (Get-PropValue $operationCue "duplicate_or_cooldown") "ok") -ne $true) { return @{ ok = $false; reason = "duplicate_or_cooldown_not_observed" } }
    $mute = Get-PropValue $Receipt "mute"
    if ((Get-PropValue $mute "muted_after_toggle") -ne $true -or (Get-PropValue $mute "muted_decision_reason") -ne "muted") { return @{ ok = $false; reason = "muted_suppression_not_observed" } }
    $native = Get-PropValue $Receipt "native_playback"
    if ((Get-PropValue $native "native_player_completion_observed") -ne $true) { return @{ ok = $false; reason = "native_player_completion_not_observed" } }
    if ((Get-PropValue $native "audible_output_confirmed") -ne $false) { return @{ ok = $false; reason = "audible_boundary_missing" } }
    foreach ($field in @("playback_provenance_sha256", "clip_sha256", "audio_sha256")) { if ([string](Get-PropValue $native $field) -eq "") { return @{ ok = $false; reason = "missing_$field" } } }
  }
  if ($Phase -eq "recover") {
    if ((Get-PropValue $Receipt "recover_from_session") -ne $true) { return @{ ok = $false; reason = "recover_from_session_failed" } }
    if ((Get-PropValue $Receipt "recovery_silent") -ne $true) { return @{ ok = $false; reason = "recovery_not_silent" } }
    if ([int](Get-PropValue (Get-PropValue $Receipt "operation_cue") "telemetry_count") -ne 0) { return @{ ok = $false; reason = "recovery_emitted_cue" } }
    $terminalRef = [string](Get-PropValue $Receipt "terminal_operation_ref")
    if ($terminalRef -eq "") { return @{ ok = $false; reason = "recover_terminal_missing" } }
    if ((Get-PropValue $Receipt "terminal_completed") -ne $true -or (Get-PropValue $Receipt "terminal_state") -ne "completed") { return @{ ok = $false; reason = "recover_terminal_not_completed" } }
    if ((Get-PropValue $Receipt "result_required") -ne $true -or $null -eq (Get-PropValue $Receipt "result")) { return @{ ok = $false; reason = "recover_result_missing" } }
    if ((Get-PropValue $Receipt "result_verified") -ne $true -or (Get-PropValue $Receipt "result_state") -ne "completed") { return @{ ok = $false; reason = "recover_result_not_verified" } }
    if ((Get-PropValue $Receipt "result_operation_ref") -ne $terminalRef -or [string](Get-PropValue $Receipt "result_canonical_sha256") -eq "") { return @{ ok = $false; reason = "recover_result_identity_mismatch" } }
  }
  @{ ok = $true; reason = "ok" }
}
function New-RowanPhaseEvidence($Result, [string[]]$Arguments, [string]$RunId, [string]$Phase, [string]$Token, [string]$DeviceId) {
  $stdout = Redact-GatewayText $Result.stdout $Token $DeviceId
  $phaseReceipt = Select-RowanPhaseReceipt $stdout
  @{
    exit_code = $Result.exit_code
    args = @($Arguments | ForEach-Object { Redact-GatewayText $_ $Token $DeviceId })
    receipt = $phaseReceipt
    validation = Test-RowanPhaseReceipt $phaseReceipt $RunId $Phase
    stdout = $stdout
    stderr = Redact-GatewayText $Result.stderr $Token $DeviceId
    stdout_tail = Redact-GatewayTail $Result.stdout $Token $DeviceId
    stderr_tail = Redact-GatewayTail $Result.stderr $Token $DeviceId
  }
}
function Test-RowanCombinedReceipt($Start, $Recover) {
  $request = Get-PropValue $Start "request_sha256"
  if ([string]$request -eq "") { return @{ ok = $false; reason = "missing_request_sha256" } }
  if ((Get-PropValue $Recover "request_sha256") -ne $request) { return @{ ok = $false; reason = "request_sha_mismatch" } }
  if ((Get-PropValue $Recover "recover_from_session") -ne $true) { return @{ ok = $false; reason = "recover_from_session_failed" } }
  $startRefs = @((Get-PropValue $Start "operation_refs")); $recoverRefs = @((Get-PropValue $Recover "operation_refs"))
  if ($startRefs.Count -ne 1 -or $recoverRefs.Count -ne 1 -or $startRefs[0] -ne $recoverRefs[0]) { return @{ ok = $false; reason = "journey_operation_set_mismatch" } }
  if ([int](Get-PropValue $Recover "operation_count_for_request") -ne 1) { return @{ ok = $false; reason = "journey_operation_set_mismatch" } }
  if ((Get-PropValue $Recover "terminal_completed") -ne $true -or (Get-PropValue $Recover "terminal_state") -ne "completed") { return @{ ok = $false; reason = "recover_terminal_not_completed" } }
  if ((Get-PropValue $Recover "result_verified") -ne $true -or $null -eq (Get-PropValue $Recover "result")) { return @{ ok = $false; reason = "recover_result_missing" } }
  @{ ok = $true; reason = "ok"; operation_ref = $startRefs[0] }
}
function Select-RowanRunnerBlocker([int]$StartExit, [int]$RecoverExit, $StartValidation, $RecoverValidation, $Combined, $Binding) {
  if ($StartExit -ne 0) { return "start_phase_failed" }
  if ($RecoverExit -ne 0) { return "recover_phase_failed" }
  foreach ($v in @($StartValidation, $RecoverValidation, $Combined, $Binding)) { if ((Get-PropValue $v "ok") -ne $true) { return Get-PropValue $v "reason" } }
  "unknown_failure"
}
function Get-RowanSourceIdentity {
  $files = @(
    "desktop/integration_test/android_rowan_cue_acceptance_test.dart",
    "desktop/integration_test/android_rowan_cue_acceptance_helpers.dart",
    "desktop/integration_test/android_rowan_cue_acceptance_receipts.dart",
    "desktop/integration_test/android_rowan_cue_acceptance_surface.dart",
    "desktop/tool/run_android_rowan_cue_acceptance.ps1",
    "desktop/tool/android_real_gateway_runner_support.ps1"
  )
  $hashes = @{}; foreach ($file in $files) { $hashes[$file] = Get-FileSha256 (Join-Path $repoRoot $file) }
  # A detached HEAD prints no branch; the string wrap reads that as "".
  @{ repo_head = "$(& git -C $repoRoot rev-parse HEAD)".Trim(); branch = "$(& git -C $repoRoot branch --show-current)".Trim(); owned_status = @(& git -C $repoRoot status --short -- $files); files = $hashes }
}
function Complete-RowanReceipt($Receipt, [string]$Token, [string]$Device) {
  $json = $Receipt | ConvertTo-Json -Depth 32
  if ($Token -ne "" -and $json.Contains($Token)) { $Receipt.status = "failed"; $Receipt.blocker = "token_leaked_in_receipt" }
  if ($Device -ne "" -and $json.Contains($Device)) { $Receipt.status = "failed"; $Receipt.blocker = "device_serial_leaked_in_receipt" }
  Write-JsonFile $ReceiptPath $Receipt
}
function Invoke-RowanSelfTest {
  $startArgs = New-RowanFlutterTestArgs "android_rowan_selftest" "emulator-5554" "start"
  $recoverArgs = New-RowanFlutterTestArgs "android_rowan_selftest" "emulator-5554" "recover"
  $op = "op_" + ("a" * 32); $op2 = "op_" + ("d" * 32); $request = "b" * 64
  $nativeOk = [pscustomobject]@{ native_player_completion_observed = $true; audible_output_confirmed = $false; playback_provenance_sha256 = ("d" * 64); clip_sha256 = ("e" * 64); audio_sha256 = ("f" * 64) }
  $startReceipt = [pscustomobject]@{ schema = "flywheel.android-rowan-cue-acceptance-phase/v1"; run_id = "android_rowan_selftest"; phase = "start"; platform = "android"; request_sha256 = $request; operation_refs = @($op); operation_count_for_request = 1; connection = [pscustomobject]@{ token_sha256 = ("c" * 64) }; rowan_controls = [pscustomobject]@{ enabled_after_opt_in = $true }; operation_cue = [pscustomobject]@{ caption_strip_visible = $true; telemetry_count = 1; duplicate_or_cooldown = [pscustomobject]@{ ok = $true } }; mute = [pscustomobject]@{ muted_after_toggle = $true; muted_decision_reason = "muted" }; native_playback = $nativeOk }
  $recoverReceipt = [pscustomobject]@{ schema = "flywheel.android-rowan-cue-acceptance-phase/v1"; run_id = "android_rowan_selftest"; phase = "recover"; platform = "android"; request_sha256 = $request; operation_refs = @($op); operation_count_for_request = 1; recover_from_session = $true; recovery_silent = $true; connection = [pscustomobject]@{ token_sha256 = ("c" * 64) }; operation_cue = [pscustomobject]@{ telemetry_count = 0 }; terminal_operation_ref = $op; terminal_state = "completed"; terminal_completed = $true; result_required = $true; result = [pscustomobject]@{ operation_ref = $op; state = "completed" }; result_verified = $true; result_state = "completed"; result_operation_ref = $op; result_canonical_sha256 = ("a" * 64) }
  $validStart = Test-RowanPhaseReceipt $startReceipt "android_rowan_selftest" "start"; $validRecover = Test-RowanPhaseReceipt $recoverReceipt "android_rowan_selftest" "recover"; $combined = Test-RowanCombinedReceipt $startReceipt $recoverReceipt
  $badAudible = $startReceipt.PSObject.Copy(); $badAudible.native_playback = [pscustomobject]@{ native_player_completion_observed = $true; audible_output_confirmed = $true; playback_provenance_sha256 = ("d" * 64); clip_sha256 = ("e" * 64); audio_sha256 = ("f" * 64) }
  $badNative = $startReceipt.PSObject.Copy(); $badNative.native_playback = [pscustomobject]@{ native_player_completion_observed = $false; audible_output_confirmed = $false; playback_provenance_sha256 = ("d" * 64); clip_sha256 = ("e" * 64); audio_sha256 = ("f" * 64) }
  $missingMute = $startReceipt.PSObject.Copy(); $missingMute.mute = [pscustomobject]@{ muted_after_toggle = $false; muted_decision_reason = "none" }
  $nonterminal = $recoverReceipt.PSObject.Copy(); $nonterminal.terminal_state = "running"; $nonterminal.terminal_completed = $false; $nonterminal.result_verified = $false; $nonterminal.result_state = "running"
  $missingResult = $recoverReceipt.PSObject.Copy(); $missingResult.result = $null; $missingResult.result_verified = $false
  $duplicate = $recoverReceipt.PSObject.Copy(); $duplicate.operation_refs = @($op, $op2); $duplicate.operation_count_for_request = 2
  $controls = @{ audible_claim_control = Test-RowanPhaseReceipt $badAudible "android_rowan_selftest" "start"; native_completion_control = Test-RowanPhaseReceipt $badNative "android_rowan_selftest" "start"; mute_control = Test-RowanPhaseReceipt $missingMute "android_rowan_selftest" "start"; nonterminal_control = Test-RowanPhaseReceipt $nonterminal "android_rowan_selftest" "recover"; missing_result_control = Test-RowanPhaseReceipt $missingResult "android_rowan_selftest" "recover"; duplicate_control = Test-RowanCombinedReceipt $startReceipt $duplicate }
  if (!$validStart.ok -or !$validRecover.ok -or !$combined.ok) { throw "positive self-test validation failed" }
  foreach ($control in $controls.GetEnumerator()) { if ((Get-PropValue $control.Value "ok") -eq $true) { throw "negative control unexpectedly passed: $($control.Key)" } }
  $owned = New-OwnedRealGatewayRoot; $safe = $false; try { $safe = (Test-Path -LiteralPath (Assert-OwnedRealGatewayPath $owned.root)) } finally { Remove-OwnedRealGatewayRoot $owned.root }
  $clean = @{ reverse = @{ exit_code = 0 }; uninstall_required = $true; uninstall = @{ exit_code = 0 }; post_package = @{ status = "absent" }; gateway = @{ stopped = $true; stdio_drain_complete = $true }; temp_root_removed = $true }
  $proof = @{ schema = $selfTestSchema; mode = "self_test"; transport = @{ mode = "usb_reverse"; lan_modes = "not_implemented" }; token_material = "run_as_stdin_redacted"; package_policy = @{ requires_absent_package = $true; clear_data = $false; cleanup_owned_install = $true }; state_preservation = @{ flutter_test_uninstall_disabled = ($startArgs -contains "--no-uninstall" -and $recoverArgs -contains "--no-uninstall"); checks_app_private_sentinel = $true; owned_temp_root_guard = $safe }; rowan_assertions = @{ opt_in = $true; mute = $true; recovery_silent = $true; duplicate_or_cooldown = $true; captions = $true; native_player_completion = $true; result_verified = $true; audible_confirmation_separate = $true }; flutter_phase_args = @(@{ phase = "start"; args = $startArgs }, @{ phase = "recover"; args = $recoverArgs }); validation = @{ start = $validStart; recover = $validRecover; combined = $combined; controls = $controls }; cleanup_gate = @{ all_clean = Test-RealCleanupState $clean }; remote_custody = @{ token_write = Test-AdbRunAsCustody @("dd", "of=files/.flywheel/connection.json") $true }; limits = @("USB reverse only", "stub provider only", "native player completion is not audible human confirmation") }
  Write-JsonFile $ReceiptPath $proof
  Write-Output "Android Rowan cue runner self-test passed"
}
if ($SelfTest) { Invoke-RowanSelfTest; exit 0 }

$runId = New-RowanRunId
$owned = $null; $gateway = $null; $reverseAdded = $false; $installedByRunner = $false
$token = ""; $selectedDevice = ""; $applicationId = ""; $adb = $null; $port = $null; $apk = $null; $apkQuarantine = $null; $exitCode = 1
$receipt = @{ schema = $schema; run_id = $runId; timestamp_utc = [DateTimeOffset]::UtcNow.ToString("o"); status = "blocked"; source = $null; limits = @("USB reverse only; not LAN/Tailscale proof", "endpoint stub only; not live provider proof", "native player completion is recorded separately from audible output confirmation") }
try {
  $receipt.source = Get-RowanSourceIdentity
  $flutter = Resolve-Tool $FlutterPath @("flutter") @("C:/flutter/bin/flutter.bat")
  $adb = Resolve-Tool $AdbPath @("adb") @((Join-Path (Join-Path $env:LOCALAPPDATA "Android/Sdk") "platform-tools/adb.exe"))
  $python = Resolve-Tool $PythonPath @("python") @("python")
  $sdkRoot = Get-AndroidSdkRoot
  $receipt.tools = @{ flutter = @{ path = $flutter; sha256 = Get-FileSha256 $flutter }; adb = @{ path = $adb; sha256 = Get-FileSha256 $adb }; python = @{ path = $python; sha256 = Get-FileSha256 $python }; android_sdk_root = $sdkRoot }
  $devicesRun = Invoke-Captured $adb @("devices") $desktopRoot 30
  $selection = Select-AndroidDevice (Convert-AdbDevices $devicesRun.stdout) $DeviceId
  $receipt.device_selection = @{ status = $selection.status; reason = Get-PropValue $selection "reason" }
  if ($selection.status -ne "ok") { $receipt.blocker = Get-PropValue $selection "reason"; Complete-RowanReceipt $receipt "" ""; exit 1 }
  $selectedDevice = $selection.id; $applicationId = Get-AndroidApplicationId
  $screen = Invoke-Captured $adb @("-s", $selectedDevice, "shell", "dumpsys", "window", "policy") $desktopRoot 30
  $receipt.screen_preflight = Test-AndroidScreenReadiness $(if ($screen.exit_code -eq 0) { $screen.stdout } else { "" })
  if (!$receipt.screen_preflight.ok) { $receipt.blocker = $receipt.screen_preflight.reason; exit 1 }
  $prePackage = Test-InstalledPackage $adb $selectedDevice $applicationId
  $receipt.package_policy = @{ package_id = $applicationId; requires_absent_package = $true; pre_status = $prePackage.status; clear_data = $false }
  if ($prePackage.status -ne "absent") { $receipt.blocker = "package_present_before_run"; Complete-RowanReceipt $receipt "" $selectedDevice; exit 1 }

  $owned = New-OwnedRealGatewayRoot; $port = Get-FreeTcpPort
  $fixtureRoot = Join-Path $owned.flywheel_home "state/artifacts"
  New-Item -ItemType Directory -Path $fixtureRoot -Force | Out-Null
  $fixturePath = Join-Path $fixtureRoot "android-rowan-cue-intake.json"
  [IO.File]::WriteAllText($fixturePath, '{"summary":"Synthetic Android Rowan cue acceptance input; not real user evidence."}', [Text.UTF8Encoding]::new($false))
  $receipt.intake_fixture = @{ relative_ref = "android-rowan-cue-intake.json"; sha256 = Get-FileSha256 $fixturePath; synthetic = $true }
  $gateway = Start-IsolatedGateway $python $repoRoot $port $owned.flywheel_home $owned.run_root
  $token = [string]$gateway.token
  $receipt.gateway = @{ process_id = $gateway.process_id; base_url_for_pc = $gateway.base_url_for_pc; base_url_for_android = $gateway.base_url_for_android; token_sha256 = $gateway.token_sha256; token_length = $gateway.token_length; token_path_class = $gateway.token_path_class; bound_hosts = $gateway.bound_hosts; alive = $gateway.alive }
  if (!$gateway.alive -or $token -eq "") { $receipt.blocker = "gateway_not_ready"; Complete-RowanReceipt $receipt $token $selectedDevice; exit 1 }
  $reverse = Set-AdbReverse $adb $selectedDevice $port $desktopRoot; $reverseAdded = $reverse.added
  $receipt.transport = @{ mode = "usb_reverse"; port = $port; added = $reverse.added; stderr_tail = $reverse.stderr_tail }
  if (!$reverse.added) { $receipt.blocker = "adb_reverse_failed"; Complete-RowanReceipt $receipt $token $selectedDevice; exit 1 }

  Push-Location $desktopRoot
  $apk = Join-Path $desktopRoot "build/app/outputs/flutter-apk/app-debug.apk"
  $apkQuarantine = Move-RealGatewayPreexistingApk $apk $owned.root
  $build = Invoke-Captured $flutter @("build", "apk", "--debug") $desktopRoot 1200
  $apkExists = Test-Path -LiteralPath $apk
  $builtSha = if ($build.exit_code -eq 0 -and $apkExists) { Get-FileSha256 $apk } else { $null }
  $buildGate = Test-RealBuildArtifactGate $build $apkExists $builtSha
  $receipt.build = @{ exit_code = $build.exit_code; apk_sha256 = $builtSha; gate = $buildGate; preexisting_apk = $apkQuarantine; stderr_tail = Get-Tail $build.stderr $selectedDevice }
  if (!$buildGate.may_install) { $receipt.blocker = $buildGate.reason; Complete-RowanReceipt $receipt $token $selectedDevice; exit 1 }
  $install = Invoke-Captured $adb @("-s", $selectedDevice, "install", "-r", "-t", $apk) $desktopRoot 120
  $installedByRunner = $install.exit_code -eq 0
  $receipt.install = @{ exit_code = $install.exit_code; stdout_tail = Get-Tail $install.stdout $selectedDevice; stderr_tail = Get-Tail $install.stderr $selectedDevice }
  if (!$installedByRunner) { $receipt.blocker = "adb_install_failed"; Complete-RowanReceipt $receipt $token $selectedDevice; exit 1 }

  $seed = Write-AppPrivateConnection $adb $selectedDevice $applicationId $gateway.base_url_for_android $token $desktopRoot
  $sentinelWrite = Write-AppPrivateSentinel $adb $selectedDevice $applicationId $runId $desktopRoot
  $receipt.pairing = @{ connection = $seed; sentinel_write = $sentinelWrite }
  if ($seed.status -ne "ok" -or $sentinelWrite.status -ne "ok") { $receipt.blocker = "app_private_seed_failed"; Complete-RowanReceipt $receipt $token $selectedDevice; exit 1 }
  $preSentinel = Test-AppPrivateSentinel $adb $selectedDevice $applicationId $runId $desktopRoot

  $startArgs = New-RowanFlutterTestArgs $runId $selectedDevice "start"
  $start = Invoke-Captured $flutter $startArgs $desktopRoot 900
  $startEvidence = New-RowanPhaseEvidence $start $startArgs $runId "start" $token $selectedDevice
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
  $recoverArgs = New-RowanFlutterTestArgs $runId $selectedDevice "recover"
  $recover = Invoke-Captured $flutter $recoverArgs $desktopRoot 900
  $recoverEvidence = New-RowanPhaseEvidence $recover $recoverArgs $runId "recover" $token $selectedDevice
  $receipt.phases.recover = $recoverEvidence
  $recoverReceipt = $recoverEvidence.receipt
  $recoverValidation = $recoverEvidence.validation
  $afterRecoverSentinel = Test-AppPrivateSentinel $adb $selectedDevice $applicationId $runId $desktopRoot
  $finalSha = Get-FileSha256 $apk
  $installedEvidence = Get-TestedInstalledPackageEvidence $adb $selectedDevice $applicationId $finalSha $sdkRoot $desktopRoot
  $combined = Test-RowanCombinedReceipt $startReceipt $recoverReceipt
  $binding = Get-PropValue $installedEvidence "binding"
  $sentinelOk = $preSentinel.ok -and $afterStartSentinel.ok -and $afterRecoverSentinel.ok
  $receipt.restart = @{ force_stop_exit_code = $forceStop.exit_code; stderr_tail = Get-Tail $forceStop.stderr $selectedDevice }
  $receipt.state_preservation = @{ before_start = $preSentinel; after_start = $afterStartSentinel; after_recover = $afterRecoverSentinel; flutter_test_uninstall_disabled = $true }
  $receipt.installed_package = $installedEvidence
  $receipt.apk = @{ build_sha256 = $builtSha; final_sha256 = $finalSha; version = Read-ApkVersion (Resolve-BuildTool $sdkRoot "aapt.exe") $apk; signing = Read-ApkSigning (Resolve-BuildTool $sdkRoot "apksigner.bat") $apk }
  $receipt.combined_validation = $combined
  $receipt.status = if ($start.exit_code -eq 0 -and $recover.exit_code -eq 0 -and $startValidation.ok -and $recoverValidation.ok -and $combined.ok -and $binding.ok -and $sentinelOk) { "passed" } else { "failed" }
  if ($receipt.status -ne "passed") { $receipt.blocker = Select-RowanRunnerBlocker $start.exit_code $recover.exit_code $startValidation $recoverValidation $combined $binding; if ($receipt.blocker -eq "unknown_failure" -and !$sentinelOk) { $receipt.blocker = "app_private_state_not_preserved" } }
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
  # Report a receipt-write failure rather than leaving a missing file with no reason.
  try {
    Complete-RowanReceipt $receipt $token $selectedDevice
  } catch {
    Write-Error ("receipt_write_failed: " + $_.Exception.GetType().FullName + ": " + $_.Exception.Message) -ErrorAction Continue
    $exitCode = 1
  }
  Pop-Location -ErrorAction SilentlyContinue
  exit $exitCode
}
