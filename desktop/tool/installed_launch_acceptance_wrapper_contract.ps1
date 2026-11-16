$schema = "flywheel.installed-launch-acceptance/v1"
$assertionIds = @(
  "H01_app_exe_exists", "H02_engine_exe_exists_under_install_root", "H03_installer_payload_files_when_expected", "H04_start_menu_shortcut_targets_app_exe",
  "H05_desktop_shortcut_optional_or_targets_app_exe", "H06_uninstall_registry_appid_singleton_or_access_denied", "H07_protocol_registration_supported_or_explicit_unsupported", "H08_port_precheck_refuses_foreign_gateway",
  "H09_installed_engine_owned_start", "H10_desktop_status_schema_required", "H11_token_used_but_redacted", "H12_owned_process_cleanup_no_survivors",
  "H13_hidden_gateway_visible_window_count_when_observer_available", "H14_journey_read_only_availability_or_typed_unavailable", "H15_offline_to_ready_status_transition", "H16_restart_same_isolated_profile",
  "H17_upgrade_before_after_snapshot_compare", "H18_known_unavailable_lanes_not_live", "H19_standalone_cli_separated_from_installed_engine", "H20_receipt_fresh_complete_and_source_bound"
)
$phaseAssertions = [ordered]@{
  "P0_payload_manifest_preflight" = @("H01_app_exe_exists", "H02_engine_exe_exists_under_install_root", "H03_installer_payload_files_when_expected", "H20_receipt_fresh_complete_and_source_bound")
  "P1_shortcut_registry_targets" = @("H04_start_menu_shortcut_targets_app_exe", "H05_desktop_shortcut_optional_or_targets_app_exe", "H06_uninstall_registry_appid_singleton_or_access_denied", "H07_protocol_registration_supported_or_explicit_unsupported")
  "P2_owned_gateway_start_status_cleanup" = @("H08_port_precheck_refuses_foreign_gateway", "H09_installed_engine_owned_start", "H10_desktop_status_schema_required", "H11_token_used_but_redacted", "H12_owned_process_cleanup_no_survivors", "H13_hidden_gateway_visible_window_count_when_observer_available")
  "P3_journey_offline_to_ready_observable" = @("H14_journey_read_only_availability_or_typed_unavailable", "H15_offline_to_ready_status_transition")
  "P4_restart_and_recovery_snapshot" = @("H16_restart_same_isolated_profile")
  "P5_upgrade_snapshot_compare" = @("H17_upgrade_before_after_snapshot_compare")
  "P6_explicit_unavailable_lanes" = @("H18_known_unavailable_lanes_not_live", "H19_standalone_cli_separated_from_installed_engine")
}
$modeRequired = @{
  "preflight" = @("H01_app_exe_exists", "H02_engine_exe_exists_under_install_root", "H20_receipt_fresh_complete_and_source_bound")
  "metadata" = @("H01_app_exe_exists", "H02_engine_exe_exists_under_install_root", "H04_start_menu_shortcut_targets_app_exe", "H06_uninstall_registry_appid_singleton_or_access_denied", "H20_receipt_fresh_complete_and_source_bound")
  "engine" = @("H01_app_exe_exists", "H02_engine_exe_exists_under_install_root", "H08_port_precheck_refuses_foreign_gateway", "H09_installed_engine_owned_start", "H10_desktop_status_schema_required", "H11_token_used_but_redacted", "H12_owned_process_cleanup_no_survivors", "H15_offline_to_ready_status_transition", "H20_receipt_fresh_complete_and_source_bound")
  "full" = @("H01_app_exe_exists", "H02_engine_exe_exists_under_install_root", "H04_start_menu_shortcut_targets_app_exe", "H06_uninstall_registry_appid_singleton_or_access_denied", "H08_port_precheck_refuses_foreign_gateway", "H09_installed_engine_owned_start", "H10_desktop_status_schema_required", "H11_token_used_but_redacted", "H12_owned_process_cleanup_no_survivors", "H14_journey_read_only_availability_or_typed_unavailable", "H15_offline_to_ready_status_transition", "H16_restart_same_isolated_profile", "H20_receipt_fresh_complete_and_source_bound")
}
$validStates = @("PASS", "FAIL", "NOT_CHECKED", "UNTESTED", "UNSUPPORTED", "SKIP", "ACCESS_DENIED", "UNAVAILABLE", "READY_EMPTY", "UPGRADE_NOT_CHECKED", "PORT_OCCUPIED_PRECHECK", "AUTH_TOKEN_UNAVAILABLE", "STATUS_CONTRACT_MISSING", "STATUS_SCHEMA_INVALID", "STATUS_VERSION_MISMATCH", "JOURNEY_SCHEMA_INVALID")

function New-LaunchRunId { return "installed_launch_" + [Guid]::NewGuid().ToString("N") }
function Write-JsonFile($Path, $Value) { $Value | ConvertTo-Json -Depth 32 | Set-Content -LiteralPath $Path -Encoding UTF8 }
function Copy-Receipt($Value) { return ($Value | ConvertTo-Json -Depth 32 | ConvertFrom-Json) }
function Read-JsonFile($Path) {
  try { return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json }
  catch { throw "Installed-launch receipt is malformed JSON: $($_.Exception.Message)" }
}
function Assert-True($Condition, $Message) { if (-not $Condition) { throw $Message } }
function Assert-ObjectRow($Object, $Label) {
  Assert-True ($null -ne $Object -and $null -ne $Object.PSObject) "$Label is not an object"
  Assert-True ($Object.GetType().FullName -ne "System.String") "$Label is not an object"
  Assert-True (-not ($Object -is [System.Array])) "$Label is not an object"
}
function Get-RequiredProperty($Object, $Name) {
  Assert-ObjectRow $Object "Receipt row"
  $prop = $Object.PSObject.Properties[$Name]
  if ($null -eq $prop) { throw "Missing required receipt property: $Name" }
  return $prop.Value
}
function Assert-ExactRows($Rows, [string[]]$ExpectedIds, $Label) {
  $ids = @()
  for ($i = 0; $i -lt @($Rows).Count; $i++) {
    $row = @($Rows)[$i]
    Assert-ObjectRow $row "$Label row $i"
    $id = Get-RequiredProperty $row "id"
    Assert-True ($id -is [string]) "$Label row $i id is not a string"
    $ids += $id
  }
  foreach ($id in $ExpectedIds) { Assert-True (@($ids | Where-Object { $_ -eq $id }).Count -eq 1) "Missing or duplicate $Label row: $id" }
  foreach ($id in $ids) { Assert-True ($ExpectedIds -contains $id) "Unknown $Label row: $id" }
}
function Test-CriticalState($Id, $State) {
  if ($Id -eq "H14_journey_read_only_availability_or_typed_unavailable") { return ($State -eq "PASS" -or $State -eq "READY_EMPTY") }
  return ($State -eq "PASS")
}
function Test-ReceiptSemantics($Receipt) {
  $assertions = @(Get-RequiredProperty $Receipt "assertions"); $phases = @(Get-RequiredProperty $Receipt "phase_results")
  $mode = if ($Receipt.PSObject.Properties["mode"]) { [string]$Receipt.mode } else { "preflight" }
  Assert-True ($modeRequired.ContainsKey($mode)) "Unknown installed-launch mode: $mode"
  Assert-ExactRows $assertions $assertionIds "assertion"; Assert-ExactRows $phases ([string[]]@($phaseAssertions.Keys)) "phase"
  foreach ($row in $assertions) {
    $id = Get-RequiredProperty $row "id"; $state = Get-RequiredProperty $row "state"; $severity = Get-RequiredProperty $row "severity"
    Assert-True ($validStates -contains $state) "Unknown assertion state: $state"; Assert-True (($severity -eq "critical") -or ($severity -eq "info")) "Invalid assertion severity: $id"
    if ((Get-RequiredProperty $Receipt "complete") -eq $true -and $severity -eq "critical") { Assert-True (Test-CriticalState $id $state) "Required assertion $id is $state" }
  }
  foreach ($id in $modeRequired[$mode]) {
    $row = $assertions | Where-Object { $_.id -eq $id } | Select-Object -First 1
    Assert-True ($row.severity -eq "critical") "Mode $mode requires critical assertion $id"; Assert-True (Test-CriticalState $id $row.state) "Mode $mode required assertion $id is $($row.state)"
  }
  foreach ($phase in $phases) {
    $id = Get-RequiredProperty $phase "id"; Assert-True ((Get-RequiredProperty $phase "state") -eq "RECORDED") "Invalid phase state: $id"
    $expected = @($phaseAssertions[$id]); $actual = @(Get-RequiredProperty $phase "assertion_ids")
    Assert-True (($actual -join "|") -eq ($expected -join "|")) "Phase assertion mapping mismatch: $id"
  }
}
function Test-InstalledLaunchReceipt($ReceiptPath, $ExpectedRunId, $ExpectedSource) {
  if (!(Test-Path -LiteralPath $ReceiptPath)) { throw "Installed-launch receipt missing after zero exit: $ReceiptPath" }
  $receipt = Read-JsonFile $ReceiptPath
  Assert-True ((Get-RequiredProperty $receipt "schema") -eq $schema) "Installed-launch receipt schema mismatch"
  Assert-True ((Get-RequiredProperty $receipt "complete") -eq $true) "Installed-launch receipt is not complete"
  Assert-True ((Get-RequiredProperty $receipt "run_id") -eq $ExpectedRunId) "Installed-launch receipt run_id is stale or mismatched"
  if (![string]::IsNullOrWhiteSpace($ExpectedSource)) { Assert-True ((Get-RequiredProperty $receipt "source_commit_expected") -eq $ExpectedSource) "Installed-launch source commit mismatch" }
  Test-ReceiptSemantics $receipt
  $h20 = @(Get-RequiredProperty $receipt "assertions") | Where-Object { $_.id -eq "H20_receipt_fresh_complete_and_source_bound" } | Select-Object -First 1
  Assert-True ($null -ne $h20) "Installed-launch receipt missing H20 source binding row"; Assert-True ($h20.state -eq "PASS") "Installed-launch H20 source binding did not pass"
  $text = Get-Content -LiteralPath $ReceiptPath -Raw; Assert-True ($text -notmatch 'secret-token') "Installed-launch receipt leaked a token-like test value"
  return $receipt
}
function Invoke-SelfTest {
  $root = Join-Path ([System.IO.Path]::GetTempPath()) ("flywheel-installed-launch-wrapper-selftest-" + [Guid]::NewGuid().ToString("N").Substring(0, 8))
  New-Item -ItemType Directory -Force -Path $root | Out-Null; $run = New-LaunchRunId
  $validAssertions = @($assertionIds | ForEach-Object { @{ id = $_; state = "PASS"; severity = "critical" } })
  $validPhases = @($phaseAssertions.Keys | ForEach-Object { @{ id = $_; state = "RECORDED"; assertion_ids = @($phaseAssertions[$_]) } })
  $valid = @{ schema = $schema; complete = $true; run_id = $run; source_commit_expected = "abc"; mode = "preflight"; assertions = $validAssertions; phase_results = $validPhases }
  $script:cases = @()
  function Run-Case($Name, $ExpectPass, $Prepare) {
    $path = Join-Path $root ($Name + ".json"); & $Prepare $path; $passed = $false; $message = ""
    try { [void](Test-InstalledLaunchReceipt $path $run "abc"); $passed = $true } catch { $message = ([string]$_.Exception.Message).Replace($root, "<selftest_root>") }
    $ok = ($passed -eq $ExpectPass); $script:cases += @{ name = $Name; expected_pass = $ExpectPass; observed_pass = $passed; ok = $ok; message = $message }
    if (-not $ok) { throw "Self-test case $Name failed: $message" }
  }
  Run-Case "valid-control" $true { param($p) Write-JsonFile $p $valid }
  Run-Case "zero-exit-missing-receipt" $false { param($p) }
  Run-Case "zero-exit-stale-run-id" $false { param($p) $copy = $valid.Clone(); $copy.run_id = "old"; Write-JsonFile $p $copy }
  Run-Case "zero-exit-malformed-receipt" $false { param($p) Set-Content -LiteralPath $p -Encoding UTF8 -Value "{" }
  Run-Case "zero-exit-incomplete-receipt" $false { param($p) $copy = $valid.Clone(); $copy.complete = $false; Write-JsonFile $p $copy }
  Run-Case "zero-exit-missing-h20" $false { param($p) $copy = Copy-Receipt $valid; $copy.assertions = @($copy.assertions | Where-Object { $_.id -ne "H20_receipt_fresh_complete_and_source_bound" }); Write-JsonFile $p $copy }
  Run-Case "zero-exit-duplicate-h20" $false { param($p) $copy = Copy-Receipt $valid; $copy.assertions += @($copy.assertions[-1]); Write-JsonFile $p $copy }
  Run-Case "zero-exit-missing-phase" $false { param($p) $copy = Copy-Receipt $valid; $copy.phase_results = @($copy.phase_results | Select-Object -First 6); Write-JsonFile $p $copy }
  Run-Case "zero-exit-critical-untested" $false { param($p) $copy = Copy-Receipt $valid; $copy.assertions[0].state = "UNTESTED"; Write-JsonFile $p $copy }
  Run-Case "zero-exit-nonobject-assertion-row" $false { param($p) $copy = Copy-Receipt $valid; $copy.assertions[0] = "bad-row"; Write-JsonFile $p $copy }
  Run-Case "zero-exit-list-assertion-id" $false { param($p) $copy = Copy-Receipt $valid; $copy.assertions[0].id = @("H01", "H02"); Write-JsonFile $p $copy }
  Run-Case "zero-exit-nonobject-phase-row" $false { param($p) $copy = Copy-Receipt $valid; $copy.phase_results[0] = "bad-row"; Write-JsonFile $p $copy }
  Run-Case "zero-exit-list-phase-id" $false { param($p) $copy = Copy-Receipt $valid; $copy.phase_results[0].id = @("P0", "P1"); Write-JsonFile $p $copy }
  @{ schema = "flywheel.installed-launch-runner-selftest/v1"; complete = $true; root = "<redacted-local-path>"; cases = $script:cases } | ConvertTo-Json -Depth 12
}
