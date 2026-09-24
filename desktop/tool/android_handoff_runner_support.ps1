function New-RunId { return "android_handoff_" + [DateTimeOffset]::UtcNow.ToString("yyyyMMddTHHmmssZ") + "_" + [Guid]::NewGuid().ToString("N").Substring(0, 8) }
function Write-JsonFile($Path, $Value) {
  if ($Path -eq "") { return }
  $parent = Split-Path -Parent $Path
  if ($parent -ne "" -and !(Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent | Out-Null }
  $Value | ConvertTo-Json -Depth 32 | Set-Content -LiteralPath $Path -Encoding UTF8
}
function Get-FileSha256($Path) { if ($Path -eq "" -or !(Test-Path -LiteralPath $Path)) { return $null }; return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Resolve-Tool($Explicit, [string[]]$Names, [string[]]$Fallbacks) {
  if ($Explicit -ne "") {
    $resolved = Resolve-Path -LiteralPath $Explicit -ErrorAction Stop
    return $resolved.Path
  }
  foreach ($name in $Names) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -ne $cmd) { return $cmd.Source }
  }
  foreach ($path in $Fallbacks) {
    if (Test-Path -LiteralPath $path) { return (Resolve-Path -LiteralPath $path).Path }
  }
  return $null
}
function Stop-ProcessTree($ProcessId) {
  try { & taskkill.exe /PID $ProcessId /T /F | Out-Null } catch {}
  try { Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue } catch {}
}
function Quote-PSLiteral($Value) { return "'" + ([string]$Value).Replace("'", "''") + "'" }
function Join-CmdCommand($File, [string[]]$Arguments) {
  foreach ($value in @($File) + $Arguments) {
    if ($value -match "[`r`n`0""&|<>^%!]") { throw "Unsafe cmd argument for batch launch" }
  }
  return '"' + $File + '" ' + (($Arguments | ForEach-Object { '"' + $_ + '"' }) -join " ")
}
function Join-ProcessArguments([string[]]$Arguments) { foreach ($value in $Arguments) { if ($value -match "[`r`n`0""]") { throw "Unsafe process argument" } }; return (($Arguments | ForEach-Object { '"' + $_ + '"' }) -join " ") }
function Invoke-Captured($File, [string[]]$Arguments, $WorkingDirectory, [int]$TimeoutSeconds = 900, [scriptblock]$OnPoll = $null, [int]$PollMilliseconds = 500, [hashtable]$Environment = $null) {
  $psi = [System.Diagnostics.ProcessStartInfo]::new()
  if ($File -match "\.(cmd|bat)$") {
    $psi.FileName = $env:ComSpec
    $psi.Arguments = '/d /s /c "' + (Join-CmdCommand $File $Arguments) + '"'
  } else {
    $psi.FileName = $File
    if ($null -ne ([System.Diagnostics.ProcessStartInfo].GetProperties() | Where-Object { $_.Name -eq "ArgumentList" } | Select-Object -First 1)) { foreach ($arg in $Arguments) { [void]$psi.ArgumentList.Add($arg) } } else { $psi.Arguments = Join-ProcessArguments $Arguments }
  }
  $psi.WorkingDirectory = $WorkingDirectory
  if ($null -ne $Environment) { foreach ($key in $Environment.Keys) { $psi.Environment[[string]$key] = [string]$Environment[$key] } }
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.UseShellExecute = $false
  $psi.CreateNoWindow = $true
  $p = [System.Diagnostics.Process]::Start($psi)
  $stdoutTask = $p.StandardOutput.ReadToEndAsync()
  $stderrTask = $p.StandardError.ReadToEndAsync()
  $timedOut = $false
  $pollResult = $null
  $pollError = $null
  $deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
  $pollWait = [Math]::Max(50, $PollMilliseconds)
  while (-not $p.WaitForExit($pollWait)) {
    if ($null -ne $OnPoll -and $null -eq $pollResult) {
      try {
        $candidate = & $OnPoll
        if ($null -ne $candidate) { $pollResult = $candidate }
      } catch {
        $pollError = $_.Exception.Message
      }
    }
    if ([DateTimeOffset]::UtcNow -ge $deadline) {
      $timedOut = $true
      break
    }
  }
  if ($timedOut) { Stop-ProcessTree $p.Id; $p.WaitForExit(5000) | Out-Null }
  $stdout = $stdoutTask.GetAwaiter().GetResult()
  $stderr = $stderrTask.GetAwaiter().GetResult()
  return @{ exit_code = if ($timedOut) { 124 } else { $p.ExitCode }; stdout = $stdout; stderr = $stderr; timed_out = $timedOut; poll_result = $pollResult; poll_error = $pollError }
}
function Redact-Text($Text, $DeviceId) {
  $value = [string]$Text
  if ($DeviceId -ne "") { $value = $value.Replace($DeviceId, "[device-redacted]") }
  return ($value -replace "Bearer\s+[A-Za-z0-9._~+/-]+=*", "Bearer [redacted]")
}
function Get-Tail($Text, $DeviceId) {
  $value = Redact-Text $Text $DeviceId
  if ($value.Length -gt 6000) { return $value.Substring($value.Length - 6000) }
  return $value
}
function Convert-AdbDevices($Text) {
  $devices = @()
  foreach ($line in ($Text -split "`r?`n")) {
    $trimmed = $line.Trim()
    if ($trimmed -eq "" -or $trimmed.StartsWith("List of devices") -or $trimmed.StartsWith("*")) { continue }
    $parts = $trimmed -split "\s+"
    if ($parts.Length -lt 2) { $devices += @{ id = $trimmed; status = "malformed"; android = $false; raw = $trimmed }; continue }
    $devices += @{
      id = $parts[0]
      status = $parts[1]
      android = ($parts[1] -eq "device")
      raw = $trimmed
    }
  }
  return @($devices)
}
function Select-AndroidDevice($Devices, $Requested) {
  $usable = @($Devices | Where-Object { $_.android })
  if ($Requested -ne "") {
    $seen = @($Devices | Where-Object { $_.id -eq $Requested })
    if ($seen.Count -eq 1 -and $seen[0].status -ne "device") { return @{ status = "blocked"; reason = "requested_android_device_$($seen[0].status)"; requested = $Requested } }
    $match = @($seen | Where-Object { $_.android })
    if ($match.Count -eq 1 -and $match[0].id -match "^[A-Za-z0-9._:-]+$") { return @{ status = "ok"; id = $match[0].id } }
    return @{ status = "blocked"; reason = "requested_android_device_not_available"; requested = $Requested }
  }
  if ($usable.Count -eq 1 -and $usable[0].id -match "^[A-Za-z0-9._:-]+$") { return @{ status = "ok"; id = $usable[0].id } }
  if ($usable.Count -eq 1) { return @{ status = "blocked"; reason = "unsafe_android_device_id" } }
  if ($usable.Count -eq 0) {
    $seen = @($Devices | Where-Object { $_.status -ne "malformed" })
    if ($seen.Count -eq 1) { return @{ status = "blocked"; reason = "android_device_$($seen[0].status)" } }
    if (@($Devices | Where-Object { $_.status -eq "malformed" }).Count -gt 0) { return @{ status = "blocked"; reason = "malformed_adb_devices_output" } }
    return @{ status = "blocked"; reason = "no_android_device" }
  }
  return @{ status = "blocked"; reason = "multiple_android_devices"; count = $usable.Count }
}
function Get-AndroidSdkRoot {
  foreach ($candidate in @($env:ANDROID_HOME, $env:ANDROID_SDK_ROOT, (Join-Path $env:LOCALAPPDATA "Android/Sdk"))) {
    if ($null -ne $candidate -and $candidate -ne "" -and (Test-Path -LiteralPath $candidate)) {
      return (Resolve-Path -LiteralPath $candidate).Path
    }
  }
  return $null
}
function Get-InstalledSystemImages($SdkRoot) {
  if ($null -eq $SdkRoot) { return @() }
  $root = Join-Path $SdkRoot "system-images"
  if (!(Test-Path -LiteralPath $root)) { return @() }
  $packages = @()
  foreach ($api in Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue) {
    foreach ($vendor in Get-ChildItem -LiteralPath $api.FullName -Directory -ErrorAction SilentlyContinue) {
      foreach ($abi in Get-ChildItem -LiteralPath $vendor.FullName -Directory -ErrorAction SilentlyContinue) {
        $packages += "system-images;$($api.Name);$($vendor.Name);$($abi.Name)"
      }
    }
  }
  return @($packages | Sort-Object)
}
function New-FlutterTestArgs($RunId, $SelectedDevice) {
  return @(
    "test",
    $fixtureRel,
    "-d",
    $SelectedDevice,
    "--dart-define=FLYWHEEL_ANDROID_HANDOFF_RUN_ID=$RunId"
  )
}
function Select-FixtureReceipt($Stdout) {
  $prefix = "FLYWHEEL_ANDROID_HANDOFF_RECEIPT_JSON:"
  foreach ($line in ($Stdout -split "`r?`n")) {
    if ($line.StartsWith($prefix)) {
      try {
        return ($line.Substring($prefix.Length) | ConvertFrom-Json -ErrorAction Stop)
      } catch {
        return [pscustomobject]@{
          invalid_fixture_receipt = $true
          parse_error = $_.Exception.Message
        }
      }
    }
  }
  return $null
}
function Get-PropValue($Object, [string]$Name) { if ($null -eq $Object) { return $null }; if ($Object -is [System.Collections.IDictionary] -and $Object.Contains($Name)) { return $Object[$Name] }; $prop = $Object.PSObject.Properties[$Name]; if ($null -eq $prop) { return $null }; return $prop.Value }
function Get-CaseValue($Fixture, [string]$Name) { $cases = Get-PropValue $Fixture "cases"; if ($null -eq $cases) { return $null }; return Get-PropValue $cases $Name }
function Get-AndroidApplicationId {
  $gradle = Join-Path $desktopRoot "android/app/build.gradle.kts"
  $text = Get-Content -Raw -LiteralPath $gradle
  $match = [regex]::Match($text, 'applicationId\s*=\s*"([^"]+)"')
  if (!$match.Success) { throw "Could not read Android applicationId" }
  return $match.Groups[1].Value
}
function Convert-PackageStatus($Run, [string]$DeviceState = "device") {
  $stdout = ([string]$Run.stdout).Trim(); $stderr = ([string]$Run.stderr).Trim()
  $base = @{ exit_code = $Run.exit_code; stdout = $stdout; stderr = $stderr; timed_out = $Run.timed_out }
  if ($DeviceState -ne "device") { return $base + @{ status = "unknown"; reason = "adb_state_$DeviceState"; installed = $null; verified_absent = $false } }
  if ($Run.timed_out) { return $base + @{ status = "unknown"; reason = "adb_timeout"; installed = $null; verified_absent = $false } }
  if ($stderr -ne "") {
    $reason = if ($stderr -match "unauthorized") { "adb_unauthorized" } elseif ($stderr -match "offline") { "adb_state_offline" } elseif ($stderr -match "device .*not found|no devices|transport|closed") { "adb_transport_error" } else { "adb_pm_diagnostic" }
    return $base + @{ status = "unknown"; reason = $reason; installed = $null; verified_absent = $false }
  }
  $lines = @($stdout -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" })
  if ($Run.exit_code -eq 1 -and $lines.Count -eq 0) { return $base + @{ status = "absent"; reason = "pm_path_absent"; installed = $false; verified_absent = $true } }
  if ($Run.exit_code -ne 0) { return $base + @{ status = "unknown"; reason = "adb_transport_error"; installed = $null; verified_absent = $false } }
  $paths = @(); foreach ($line in $lines) { if (!$line.StartsWith("package:")) { return $base + @{ status = "unknown"; reason = "malformed_pm_path_output"; installed = $null; verified_absent = $false } }; $paths += $line.Substring(8) }
  if ($paths.Count -eq 0) { return $base + @{ status = "unknown"; reason = "malformed_pm_path_output"; installed = $null; verified_absent = $false } }
  return $base + @{ status = "present"; reason = "pm_path_present"; installed = $true; verified_absent = $false; package_paths = $paths }
}
function Test-InstalledPackage($Adb, $Device, $PackageId) {
  $stateRun = Invoke-Captured $Adb @("-s", $Device, "get-state") $desktopRoot 30
  $state = if ($stateRun.exit_code -eq 0 -and ([string]$stateRun.stderr).Trim() -eq "") { ([string]$stateRun.stdout).Trim() } else { "transport_error" }
  $status = if ($state -eq "device") { Convert-PackageStatus (Invoke-Captured $Adb @("-s", $Device, "shell", "pm", "path", $PackageId) $desktopRoot 30) $state } else { Convert-PackageStatus @{ exit_code = $stateRun.exit_code; stdout = $stateRun.stdout; stderr = $stateRun.stderr; timed_out = $stateRun.timed_out } $state }
  $status["device_state"] = $state; return $status
}
function Test-TestedPackageBinding($Evidence, $ExpectedSha256) {
  if ((Get-PropValue $Evidence "status") -ne "present") { return @{ ok = $false; reason = "tested_package_not_present" } }
  $hashes = @(Get-PropValue $Evidence "apk_hashes"); if ($hashes.Count -eq 0) { return @{ ok = $false; reason = "missing_installed_hash" } }
  if ([string]$ExpectedSha256 -eq "") { return @{ ok = $false; reason = "missing_expected_apk_hash" } }
  if (@($hashes | Where-Object { (Get-PropValue $_ "sha256") -eq $ExpectedSha256 }).Count -eq 0) { return @{ ok = $false; reason = "installed_package_hash_mismatch" } }
  $version = Get-PropValue $Evidence "version"; if ($null -eq $version -or [string](Get-PropValue $version "package_name") -eq "") { return @{ ok = $false; reason = "missing_version_evidence" } }
  $signing = Get-PropValue $Evidence "signing"; if ($null -eq $signing -or (Get-PropValue $signing "status") -ne "ok") { return @{ ok = $false; reason = "missing_signing_evidence" } }
  return @{ ok = $true; reason = "ok" }
}
function Test-FixtureReceipt($Fixture, $RunId) {
  if ($null -eq $Fixture) { return @{ ok = $false; reason = "missing_fixture_receipt" } }
  if ((Get-PropValue $Fixture "invalid_fixture_receipt") -eq $true) {
    return @{ ok = $false; reason = "invalid_fixture_receipt_json"; error = Get-PropValue $Fixture "parse_error" }
  }
  if ((Get-PropValue $Fixture "schema") -ne "flywheel.android-gateway-handoff-fixture/v1") { return @{ ok = $false; reason = "schema_mismatch" } }
  if ((Get-PropValue $Fixture "run_id") -ne $RunId) { return @{ ok = $false; reason = "run_id_mismatch" } }
  $platform = Get-PropValue $Fixture "platform"
  if ($platform -ne "android") { return @{ ok = $false; reason = "platform_not_android"; platform = $platform } }
  foreach ($name in @("paired_world_read", "missing_token_rejected", "wrong_token_rejected", "unreachable_gateway", "assistant_no_response", "duplicate_after_restart")) {
    $case = Get-CaseValue $Fixture $name
    if ($null -eq $case -or (Get-PropValue $case "passed") -ne $true) { return @{ ok = $false; reason = "case_failed"; case = $name } }
  }
  foreach ($name in @("missing_token_rejected", "wrong_token_rejected", "unreachable_gateway", "assistant_no_response")) {
    $case = Get-CaseValue $Fixture $name
    if ((Get-PropValue $case "ok") -ne $false) { return @{ ok = $false; reason = "negative_control_not_rejected"; case = $name } }
  }
  $assistant = Get-CaseValue $Fixture "assistant_no_response"
  if ([int](Get-PropValue $assistant "server_posts") -ne 1) { return @{ ok = $false; reason = "assistant_no_response_post_count" } }
  $duplicate = Get-CaseValue $Fixture "duplicate_after_restart"
  if ([int](Get-PropValue $duplicate "server_agent_posts") -ne 1) { return @{ ok = $false; reason = "duplicate_agent_posts" } }
  if ((Get-PropValue $duplicate "request_hash_bound") -ne $true) { return @{ ok = $false; reason = "request_hash_not_bound" } }
  $gateway = Get-PropValue $Fixture "gateway"
  if ([int](Get-PropValue $gateway "unauthorized_requests") -lt 2) { return @{ ok = $false; reason = "auth_controls_not_observed" } }
  if ([int](Get-PropValue $gateway "relay_start_posts") -ne 1) { return @{ ok = $false; reason = "relay_unavailable_control_not_observed" } }
  if ([int](Get-PropValue $gateway "agent_posts") -ne 1) { return @{ ok = $false; reason = "duplicate_agent_posts" } }
  return @{ ok = $true; reason = "ok" }
}
function New-SelfTestRejectedCase { return [pscustomobject]@{ passed = $true; ok = $false } }
function New-SelfTestFixtureReceipt($RunId) {
  $caseOk = [pscustomobject]@{ passed = $true }
  return [pscustomobject]@{
    schema = "flywheel.android-gateway-handoff-fixture/v1"
    run_id = $RunId
    platform = "android"
    gateway = [pscustomobject]@{ unauthorized_requests = 2; relay_start_posts = 1; agent_posts = 1 }
    cases = [pscustomobject]@{
      paired_world_read = $caseOk
      missing_token_rejected = New-SelfTestRejectedCase
      wrong_token_rejected = New-SelfTestRejectedCase
      unreachable_gateway = New-SelfTestRejectedCase
      assistant_no_response = [pscustomobject]@{ passed = $true; ok = $false; server_posts = 1 }
      duplicate_after_restart = [pscustomobject]@{ passed = $true; server_agent_posts = 1; request_hash_bound = $true }
    }
  }
}
function Get-SourceIdentity {
  # A detached HEAD prints no branch; the string wrap reads that as "".
  $head = "$(& git -C $repoRoot rev-parse HEAD)".Trim()
  $branch = "$(& git -C $repoRoot branch --show-current)".Trim()
  $status = & git -C $repoRoot status --short -- "desktop/integration_test/android_gateway_handoff_test.dart" "desktop/tool/run_android_handoff_acceptance.ps1" "desktop/tool/android_handoff_runner_support.ps1" "tests/test_android_handoff_acceptance_runner.py"
  $runnerPath = Join-Path $scriptRoot "run_android_handoff_acceptance.ps1"
  $supportPath = Join-Path $scriptRoot "android_handoff_runner_support.ps1"
  return @{
    repo_head = $head
    branch = $branch
    owned_status = @($status)
    files = @{
      "desktop/integration_test/android_gateway_handoff_test.dart" = Get-FileSha256 (Join-Path $desktopRoot $fixtureRel)
      "desktop/tool/run_android_handoff_acceptance.ps1" = Get-FileSha256 $runnerPath
      "desktop/tool/android_handoff_runner_support.ps1" = Get-FileSha256 $supportPath
      "tests/test_android_handoff_acceptance_runner.py" = Get-FileSha256 (Join-Path $repoRoot "tests/test_android_handoff_acceptance_runner.py")
    }
  }
}
