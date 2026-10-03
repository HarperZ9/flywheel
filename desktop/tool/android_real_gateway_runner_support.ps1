$commonSupport = Join-Path $PSScriptRoot "android_handoff_runner_support.ps1"
if (Test-Path -LiteralPath $commonSupport) { . $commonSupport }

function New-RealGatewayRunId { "android_real_" + [DateTimeOffset]::UtcNow.ToString("yyyyMMddTHHmmssZ") + "_" + [Guid]::NewGuid().ToString("N").Substring(0, 8) }
function Get-TextSha256([string]$Value) { $bytes = [Text.Encoding]::UTF8.GetBytes($Value); ([Security.Cryptography.SHA256]::Create().ComputeHash($bytes) | ForEach-Object { $_.ToString("x2") }) -join "" }
function Get-FreeTcpPort { $l = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0); $l.Start(); $p = $l.LocalEndpoint.Port; $l.Stop(); $p }
function New-OwnedRealGatewayRoot {
  $leaf = "fw-android-real-gateway-" + [Guid]::NewGuid().ToString("N")
  $root = Join-Path ([IO.Path]::GetTempPath()) $leaf
  New-Item -ItemType Directory -Path $root | Out-Null
  foreach ($name in @("flywheel-home", "run-root", "receipts")) { New-Item -ItemType Directory -Path (Join-Path $root $name) | Out-Null }
  @{ root = $root; flywheel_home = Join-Path $root "flywheel-home"; run_root = Join-Path $root "run-root"; receipt_root = Join-Path $root "receipts" }
}
function Assert-OwnedRealGatewayPath([string]$Path) {
  $resolved = Resolve-Path -LiteralPath $Path -ErrorAction Stop
  if (@($resolved).Count -ne 1) { throw "Owned real gateway path is ambiguous" }
  $target = [IO.Path]::GetFullPath($resolved.Path).TrimEnd("\", "/")
  $temp = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd("\", "/")
  $parent = [IO.Path]::GetFullPath((Split-Path -Parent $target)).TrimEnd("\", "/")
  $leaf = Split-Path -Leaf $target
  if ($parent -ine $temp -or $leaf -notmatch "^fw-android-real-gateway-[0-9a-fA-F]{32}$") { throw "Refusing unsafe real gateway cleanup target" }
  $item = Get-Item -LiteralPath $target -Force
  if (!$item.PSIsContainer -or (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) { throw "Refusing non-directory/reparse cleanup target" }
  if ($null -ne (Get-ChildItem -LiteralPath $target -Recurse -Force | Where-Object { ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 } | Select-Object -First 1)) { throw "Refusing cleanup target with reparse child" }
  $target
}
function Remove-OwnedRealGatewayRoot([string]$Path) { if (Test-Path -LiteralPath $Path) { Remove-Item -LiteralPath (Assert-OwnedRealGatewayPath $Path) -Recurse -Force } }

function Invoke-CapturedInput($File, [string[]]$Arguments, $WorkingDirectory, [string]$InputText, [int]$TimeoutSeconds = 60) {
  $psi = [Diagnostics.ProcessStartInfo]::new(); $psi.FileName = $File
  if ($null -ne ([Diagnostics.ProcessStartInfo].GetProperties() | Where-Object Name -eq "ArgumentList" | Select-Object -First 1)) { foreach ($arg in $Arguments) { [void]$psi.ArgumentList.Add($arg) } } else { $psi.Arguments = Join-ProcessArguments $Arguments }
  $psi.WorkingDirectory = $WorkingDirectory; $psi.RedirectStandardInput = $true; $psi.RedirectStandardOutput = $true; $psi.RedirectStandardError = $true; $psi.UseShellExecute = $false; $psi.CreateNoWindow = $true
  $p = [Diagnostics.Process]::Start($psi); $p.StandardInput.Write($InputText); $p.StandardInput.Close(); $stdout = $p.StandardOutput.ReadToEndAsync(); $stderr = $p.StandardError.ReadToEndAsync()
  $done = $p.WaitForExit($TimeoutSeconds * 1000); if (!$done) { Stop-ProcessTree $p.Id; $p.WaitForExit(5000) | Out-Null }
  @{ exit_code = if ($done) { $p.ExitCode } else { 124 }; stdout = $stdout.GetAwaiter().GetResult(); stderr = $stderr.GetAwaiter().GetResult(); timed_out = (-not $done) }
}
function Test-AppPrivateJsonPath([string]$RelativePath) { $RelativePath -match "^files/\.flywheel/[A-Za-z0-9._-]+\.json$" }
function Assert-AppPrivateJsonPath([string]$RelativePath) { if (!(Test-AppPrivateJsonPath $RelativePath)) { throw "Unsafe app-private path" }; $RelativePath }
function Test-AdbRunAsCustody([string[]]$RunAsArguments, [bool]$UsesStdin) {
  if ($RunAsArguments.Count -eq 0) { return @{ ok = $false; reason = "run_as_empty_argv"; uses_shell = $false } }
  if (@($RunAsArguments | Where-Object { $_ -eq "sh" -or $_ -eq "-c" }).Count -gt 0) { return @{ ok = $false; reason = "run_as_shell_forbidden"; uses_shell = $true } }
  if (@($RunAsArguments | Where-Object { $_ -match "[><|&;]" }).Count -gt 0) { return @{ ok = $false; reason = "run_as_metachar_forbidden"; uses_shell = $false } }
  $cmd = $RunAsArguments[0]
  if ($cmd -eq "mkdir" -and $RunAsArguments.Count -eq 3 -and $RunAsArguments[1] -eq "-p" -and $RunAsArguments[2] -eq "files/.flywheel" -and !$UsesStdin) { return @{ ok = $true; reason = "ok"; uses_shell = $false; command = "mkdir"; stdin_target = "none" } }
  if ($cmd -eq "dd" -and $RunAsArguments.Count -eq 2 -and $RunAsArguments[1].StartsWith("of=") -and $UsesStdin) { if (!(Test-AppPrivateJsonPath $RunAsArguments[1].Substring(3))) { return @{ ok = $false; reason = "run_as_path_forbidden"; uses_shell = $false } }; return @{ ok = $true; reason = "ok"; uses_shell = $false; command = "dd"; stdin_target = "run-as-child-dd-of" } }
  if ($cmd -eq "cat" -and $RunAsArguments.Count -eq 2 -and !$UsesStdin) { if (!(Test-AppPrivateJsonPath $RunAsArguments[1])) { return @{ ok = $false; reason = "run_as_path_forbidden"; uses_shell = $false } }; return @{ ok = $true; reason = "ok"; uses_shell = $false; command = "cat"; stdin_target = "none" } }
  if ($cmd -eq "rm" -and $RunAsArguments.Count -ge 3 -and $RunAsArguments[1] -eq "-f" -and !$UsesStdin) {
    foreach ($path in @($RunAsArguments | Select-Object -Skip 2)) { if (!(Test-AppPrivateJsonPath $path)) { return @{ ok = $false; reason = "run_as_path_forbidden"; uses_shell = $false } } }
    return @{ ok = $true; reason = "ok"; uses_shell = $false; command = "rm"; stdin_target = "none" }
  }
  @{ ok = $false; reason = "run_as_argv_forbidden"; uses_shell = $false }
}
function Assert-AdbRunAsCustody([string[]]$RunAsArguments, [bool]$UsesStdin) { $custody = Test-AdbRunAsCustody $RunAsArguments $UsesStdin; if (!$custody.ok) { throw "Unsafe run-as argv: $($custody.reason)" }; $RunAsArguments }
function Invoke-AdbRunAsInput($Adb, $Device, $PackageId, [string[]]$RunAsArguments, [string]$InputText, $WorkingDirectory) { Invoke-CapturedInput $Adb (@("-s", $Device, "shell", "run-as", $PackageId) + (Assert-AdbRunAsCustody $RunAsArguments $true)) $WorkingDirectory $InputText 60 }
function Invoke-AdbRunAs($Adb, $Device, $PackageId, [string[]]$RunAsArguments, $WorkingDirectory) { Invoke-Captured $Adb (@("-s", $Device, "shell", "run-as", $PackageId) + (Assert-AdbRunAsCustody $RunAsArguments $false)) $WorkingDirectory 60 }
function Write-AppPrivateFile($Adb, $Device, $PackageId, [string]$RelativePath, [string]$Content, $WorkingDirectory) {
  $safePath = Assert-AppPrivateJsonPath $RelativePath
  $mkdir = Invoke-AdbRunAs $Adb $Device $PackageId @("mkdir", "-p", "files/.flywheel") $WorkingDirectory
  if ($mkdir.exit_code -ne 0) { return @{ status = "failed"; exit_code = $mkdir.exit_code; stderr_tail = Get-Tail $mkdir.stderr $Device; command_contains_secret = $false; path_class = "run-as mkdir files/.flywheel"; uses_no_shell_argv = $true } }
  $r = Invoke-AdbRunAsInput $Adb $Device $PackageId @("dd", "of=$safePath") $Content $WorkingDirectory
  @{ status = if ($r.exit_code -eq 0) { "ok" } else { "failed" }; exit_code = $r.exit_code; mkdir_exit_code = $mkdir.exit_code; stderr_tail = Get-Tail $r.stderr $Device; command_contains_secret = $false; path_class = "run-as dd of=$safePath"; uses_no_shell_argv = $true; stdin_target = "run-as-child-dd-of" }
}
function Read-AppPrivateFile($Adb, $Device, $PackageId, [string]$RelativePath, $WorkingDirectory) {
  Invoke-AdbRunAs $Adb $Device $PackageId @("cat", (Assert-AppPrivateJsonPath $RelativePath)) $WorkingDirectory
}
function Write-AppPrivateConnection($Adb, $Device, $PackageId, $BaseUrl, $Token, $WorkingDirectory) {
  $json = @{ base_url = $BaseUrl; token = $Token } | ConvertTo-Json -Compress
  $r = Write-AppPrivateFile $Adb $Device $PackageId "files/.flywheel/connection.json" $json $WorkingDirectory
  $r["base_url"] = $BaseUrl; $r["token_sha256"] = Get-TextSha256 $Token; $r["token_length"] = $Token.Length; $r["uses_run_as_stdin"] = $true; $r
}
function Write-AppPrivateSentinel($Adb, $Device, $PackageId, $RunId, $WorkingDirectory) { Write-AppPrivateFile $Adb $Device $PackageId "files/.flywheel/android-real-gateway-sentinel.json" (@{ run_id = $RunId } | ConvertTo-Json -Compress) $WorkingDirectory }
function Test-AppPrivateSentinel($Adb, $Device, $PackageId, $RunId, $WorkingDirectory) {
  $r = Read-AppPrivateFile $Adb $Device $PackageId "files/.flywheel/android-real-gateway-sentinel.json" $WorkingDirectory
  $ok = $false; if ($r.exit_code -eq 0) { try { $ok = ((($r.stdout | ConvertFrom-Json).run_id) -eq $RunId) } catch {} }
  @{ ok = $ok; exit_code = $r.exit_code; stderr_tail = Get-Tail $r.stderr $Device }
}
function Clear-OwnedAppPrivateConnection($Adb, $Device, $PackageId, $WorkingDirectory) { Invoke-AdbRunAs $Adb $Device $PackageId @("rm", "-f", "files/.flywheel/connection.json", "files/.flywheel/android-real-gateway-sentinel.json") $WorkingDirectory }

function Add-GatewayProcessArguments($ProcessStartInfo, [string[]]$Arguments) { if ($null -ne $ProcessStartInfo.ArgumentList) { foreach ($arg in $Arguments) { [void]$ProcessStartInfo.ArgumentList.Add($arg) } } else { $ProcessStartInfo.Arguments = Join-ProcessArguments $Arguments } }
function Complete-GatewayTextTask($Task, [int]$TimeoutMilliseconds = 500) {
  if ($null -eq $Task) { return @{ text = ""; completed = $true; timed_out = $false } }
  try {
    if ($Task.IsCompleted -or $Task.Wait($TimeoutMilliseconds)) {
      return @{ text = [string]$Task.GetAwaiter().GetResult(); completed = $true; timed_out = $false }
    }
    return @{ text = ""; completed = $false; timed_out = $true }
  } catch {
    return @{ text = ""; completed = $false; timed_out = $false; error = $_.Exception.Message }
  }
}
function Redact-GatewayText($Text, [string]$Token, [string]$DeviceId) {
  $value = [string]$Text
  if (![string]::IsNullOrEmpty($Token)) { $value = $value.Replace($Token, "[redacted]") }
  Redact-Text $value $DeviceId
}
function Redact-GatewayTail($Text, [string]$Token, [string]$DeviceId) { Get-Tail (Redact-GatewayText $Text $Token $DeviceId) $DeviceId }
function Test-AndroidScreenReadiness([string]$PolicyText) {
  $showing = @([regex]::Matches($PolicyText, '(?m)^\s*showing=(true|false)\s*$') | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique)
  if ($showing.Count -ne 1) { return @{ ok = $false; reason = "android_screen_state_unknown" } }
  if ($showing[0] -eq "true") { return @{ ok = $false; reason = "android_screen_locked" } }
  $screen = @([regex]::Matches($PolicyText, '(?m)^\s*screenState=(\w+)\s*$') | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique)
  $interactive = @([regex]::Matches($PolicyText, '(?m)^\s*interactiveState=(\w+)\s*$') | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique)
  if ($screen.Count -ne 1 -or $interactive.Count -ne 1) { return @{ ok = $false; reason = "android_screen_state_unknown" } }
  if ($screen[0] -ne "SCREEN_STATE_ON" -or $interactive[0] -ne "INTERACTIVE_STATE_AWAKE") { return @{ ok = $false; reason = "android_screen_not_awake" } }
  @{ ok = $true; reason = "ok" }
}
function New-RealPhaseEvidence($Result, [string[]]$Arguments, [string]$RunId, [string]$Phase, [string]$Token, [string]$DeviceId) {
  $stdout = Redact-GatewayText $Result.stdout $Token $DeviceId
  $phaseReceipt = Select-RealPhaseReceipt $stdout
  @{
    exit_code = $Result.exit_code
    args = @($Arguments | ForEach-Object { Redact-GatewayText $_ $Token $DeviceId })
    receipt = $phaseReceipt
    validation = Test-RealPhaseReceipt $phaseReceipt $RunId $Phase
    stdout = $stdout
    stderr = Redact-GatewayText $Result.stderr $Token $DeviceId
    stdout_tail = Redact-GatewayTail $Result.stdout $Token $DeviceId
    stderr_tail = Redact-GatewayTail $Result.stderr $Token $DeviceId
  }
}
function Start-IsolatedGateway($Python, $RepoRoot, [int]$Port, $FlywheelHome, $RunRoot, [bool]$ProbeWorld = $true) {
  $psi = [Diagnostics.ProcessStartInfo]::new(); $psi.FileName = $Python; $psi.WorkingDirectory = $RepoRoot
  Add-GatewayProcessArguments $psi @("harness/gateway.py", "--port", "$Port", "--host", "127.0.0.1", "--root", $RepoRoot, "--run-root", $RunRoot)
  $psi.Environment["FLYWHEEL_HOME"] = $FlywheelHome; $psi.RedirectStandardOutput = $true; $psi.RedirectStandardError = $true; $psi.UseShellExecute = $false; $psi.CreateNoWindow = $true
  $p = [Diagnostics.Process]::new(); $p.StartInfo = $psi; [void]$p.Start()
  $stdoutTask = $p.StandardOutput.ReadToEndAsync(); $stderrTask = $p.StandardError.ReadToEndAsync()
  $tokenPath = Join-Path $FlywheelHome "gateway.token"; $token = $null; $alive = $false; $startupState = "waiting_for_token"
  for ($i = 0; $i -lt 80; $i++) { if (Test-Path -LiteralPath $tokenPath) { $token = (Get-Content -LiteralPath $tokenPath -Raw).Trim(); if ($token -ne "") { $startupState = "token_ready"; break } }; if ($p.HasExited) { $startupState = "process_exited_before_token"; break }; Start-Sleep -Milliseconds 250 }
  if ([string]$token -ne "" -and !$p.HasExited -and !$ProbeWorld) { $alive = $true; $startupState = "running_without_world_probe" }
  elseif ([string]$token -ne "" -and !$p.HasExited) { for ($i = 0; $i -lt 80; $i++) { try { $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/api/world" -Headers @{ Authorization = "Bearer $token" } -TimeoutSec 2; if ($r.StatusCode -eq 200) { $alive = $true; $startupState = "world_ready"; break } } catch {}; if ($p.HasExited) { $startupState = "process_exited_before_world"; break }; Start-Sleep -Milliseconds 250 } }
  @{ process = $p; process_id = $p.Id; base_url_for_pc = "http://127.0.0.1:$Port"; base_url_for_android = "http://127.0.0.1:$Port"; token_path_class = "owned FLYWHEEL_HOME gateway.token"; token_sha256 = if ($token) { Get-TextSha256 $token } else { $null }; token_length = if ($token) { $token.Length } else { 0 }; token = $token; bound_hosts = @("127.0.0.1"); alive = $alive; startup_state = $startupState; exit_code = if ($p.HasExited) { $p.ExitCode } else { $null }; stdout_task = $stdoutTask; stderr_task = $stderrTask }
}
function Stop-OwnedGateway($Gateway, [string]$Token, [string]$DeviceId) {
  $process = Get-PropValue $Gateway "process"
  if ($process -and !$process.HasExited) { Stop-ProcessTree $process.Id; $process.WaitForExit(5000) | Out-Null }
  $stopped = ($null -eq $process -or $process.HasExited)
  $stdout = Complete-GatewayTextTask (Get-PropValue $Gateway "stdout_task") 500
  $stderr = Complete-GatewayTextTask (Get-PropValue $Gateway "stderr_task") 500
  $stdoutComplete = (Get-PropValue $stdout "completed") -eq $true
  $stderrComplete = (Get-PropValue $stderr "completed") -eq $true
  @{ stopped = $stopped; exit_code = if ($process -and $process.HasExited) { $process.ExitCode } else { $null }; stdout_tail = Redact-GatewayTail (Get-PropValue $stdout "text") $Token $DeviceId; stderr_tail = Redact-GatewayTail (Get-PropValue $stderr "text") $Token $DeviceId; stdout_drain_complete = $stdoutComplete; stderr_drain_complete = $stderrComplete; stdio_drain_complete = ($stdoutComplete -and $stderrComplete); stdout_drain_timed_out = ((Get-PropValue $stdout "timed_out") -eq $true); stderr_drain_timed_out = ((Get-PropValue $stderr "timed_out") -eq $true) }
}
function Set-AdbReverse($Adb, $Device, [int]$Port, $WorkingDirectory) { $r = Invoke-Captured $Adb @("-s", $Device, "reverse", "tcp:$Port", "tcp:$Port") $WorkingDirectory 30; $list = Invoke-Captured $Adb @("-s", $Device, "reverse", "--list") $WorkingDirectory 30; @{ mode = "usb_reverse"; port = $Port; added = ($r.exit_code -eq 0 -and $list.stdout -match "tcp:$Port\s+tcp:$Port"); exit_code = $r.exit_code; list_tail = Get-Tail $list.stdout $Device; stderr_tail = Get-Tail $r.stderr $Device } }
function Remove-AdbReverse($Adb, $Device, [int]$Port, $WorkingDirectory) { Invoke-Captured $Adb @("-s", $Device, "reverse", "--remove", "tcp:$Port") $WorkingDirectory 30 }

function Resolve-BuildTool([string]$SdkRoot, [string]$Name) { if ($null -eq $SdkRoot) { return $null }; $t = Get-ChildItem -LiteralPath (Join-Path $SdkRoot "build-tools") -Recurse -Filter $Name -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | Select-Object -First 1; if ($t) { $t.FullName } else { $null } }
function Read-ApkVersion($Aapt, $ApkPath) { if ($null -eq $Aapt -or !(Test-Path -LiteralPath $ApkPath)) { return @{ status = "unavailable" } }; $r = Invoke-Captured $Aapt @("dump", "badging", $ApkPath) (Split-Path -Parent $ApkPath) 30; $line = ($r.stdout -split "`r?`n" | Where-Object { $_.StartsWith("package:") } | Select-Object -First 1); $m = [regex]::Match([string]$line, "name='([^']+)'.*versionCode='([^']+)'.*versionName='([^']*)'"); if ($r.exit_code -ne 0 -or !$m.Success) { return @{ status = "unknown"; reason = "aapt_failed"; stdout_tail = Get-Tail $r.stdout ""; stderr_tail = Get-Tail $r.stderr "" } }; @{ status = "ok"; package_name = $m.Groups[1].Value; version_code = $m.Groups[2].Value; version_name = $m.Groups[3].Value } }
function Resolve-JavaForApkSigner { $cmd = Get-Command java -ErrorAction SilentlyContinue | Select-Object -First 1; if ($cmd) { return @{ status = "ok"; source = "PATH"; java_path = $cmd.Source } }; @{ status = "missing"; reason = "java_unavailable" } }
function Convert-ApkSigningResult($Run, $Java) { $stdout = Get-Tail $Run.stdout ""; $stderr = Get-Tail $Run.stderr ""; if ($Run.exit_code -ne 0) { return @{ status = "unknown"; reason = if (("$stdout`n$stderr") -match "JAVA_HOME|java") { "java_unavailable" } else { "apksigner_failed" }; stdout_tail = $stdout; stderr_tail = $stderr; java = $Java } }; $line = ($stdout -split "`r?`n" | Where-Object { $_ -match "Signer #1 certificate SHA-256 digest:" } | Select-Object -First 1); if (!$line) { return @{ status = "unknown"; reason = "missing_certificate_digest"; stdout_tail = $stdout; stderr_tail = $stderr; java = $Java } }; $digest = ([regex]::Match($line, "digest:\s*(.+)$").Groups[1].Value -replace "[^0-9A-Fa-f]", "").ToLowerInvariant(); if ($digest -notmatch "^[0-9a-f]{64}$") { return @{ status = "unknown"; reason = "malformed_certificate_digest" } }; @{ status = "ok"; certificate_sha256 = $digest; stdout_tail = $stdout; stderr_tail = $stderr; java = $Java } }
function Read-ApkSigning($ApkSigner, $ApkPath) { if ($null -eq $ApkSigner -or !(Test-Path -LiteralPath $ApkPath)) { return @{ status = "unavailable" } }; Convert-ApkSigningResult (Invoke-Captured $ApkSigner @("verify", "--print-certs", $ApkPath) (Split-Path -Parent $ApkPath) 30) (Resolve-JavaForApkSigner) }
function Get-TestedInstalledPackageEvidence($Adb, $Device, $PackageId, $ExpectedSha256, $SdkRoot, $WorkingDirectory) { $e = Test-InstalledPackage $Adb $Device $PackageId; if ($e.status -ne "present") { $e["binding"] = Test-TestedPackageBinding $e $ExpectedSha256; return $e }; $tmp = Join-Path ([IO.Path]::GetTempPath()) ("fw-android-apk-" + [Guid]::NewGuid().ToString("N")); New-Item -ItemType Directory -Path $tmp | Out-Null; try { $hashes = @(); $i = 0; foreach ($devicePath in @($e.package_paths)) { $local = Join-Path $tmp "pkg-$i.apk"; $pull = Invoke-Captured $Adb @("-s", $Device, "pull", $devicePath, $local) $WorkingDirectory 60; if ($pull.exit_code -ne 0 -or !(Test-Path -LiteralPath $local)) { $e["status"] = "unknown"; $e["reason"] = "adb_pull_failed"; $e["binding"] = Test-TestedPackageBinding $e $ExpectedSha256; return $e }; $hashes += @{ device_path = $devicePath; sha256 = Get-FileSha256 $local; bytes = (Get-Item -LiteralPath $local).Length }; $i++ }; $base = Join-Path $tmp "pkg-0.apk"; $e["apk_hashes"] = $hashes; $e["version"] = Read-ApkVersion (Resolve-BuildTool $SdkRoot "aapt.exe") $base; $e["signing"] = Read-ApkSigning (Resolve-BuildTool $SdkRoot "apksigner.bat") $base; $e["binding"] = Test-TestedPackageBinding $e $ExpectedSha256; $e } finally { Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue } }

function Test-RealGatewayApkTarget($ApkPath) { ([IO.Path]::GetFileName($ApkPath) -eq "app-debug.apk") -and (([IO.Path]::GetFullPath($ApkPath)) -match [regex]::Escape("build" + [IO.Path]::DirectorySeparatorChar + "app" + [IO.Path]::DirectorySeparatorChar + "outputs" + [IO.Path]::DirectorySeparatorChar + "flutter-apk" + [IO.Path]::DirectorySeparatorChar + "app-debug.apk")) }
function Move-RealGatewayPreexistingApk($ApkPath, $OwnedRoot) {
  if (!(Test-Path -LiteralPath $ApkPath)) { return @{ status = "absent"; scoped = $true } }
  if (!(Test-RealGatewayApkTarget $ApkPath)) { throw "Refusing unscoped APK quarantine target" }
  $dir = Join-Path $OwnedRoot "apk-quarantine"; New-Item -ItemType Directory -Path $dir -Force | Out-Null
  $backup = Join-Path $dir "app-debug.preexisting.apk"; Move-Item -LiteralPath $ApkPath -Destination $backup -Force
  @{ status = "quarantined"; scoped = $true; original_path = $ApkPath; quarantine_path = $backup }
}
function Restore-RealGatewayPreexistingApk($Info) {
  if ((Get-PropValue $Info "status") -ne "quarantined") { return @{ status = "not_needed" } }
  $target = Get-PropValue $Info "original_path"; $backup = Get-PropValue $Info "quarantine_path"
  if (!(Test-RealGatewayApkTarget $target) -or !(Test-Path -LiteralPath $backup)) { return @{ status = "failed"; reason = "quarantine_missing_or_unscoped" } }
  if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Force }
  Move-Item -LiteralPath $backup -Destination $target -Force
  @{ status = "restored"; scoped = $true }
}
function Test-RealBuildArtifactGate($BuildRun, [bool]$ApkExists, $ApkSha256) {
  if ((Get-PropValue $BuildRun "exit_code") -ne 0) { return @{ ok = $false; may_install = $false; reason = "flutter_build_failed" } }
  if (!$ApkExists) { return @{ ok = $false; may_install = $false; reason = "missing_built_apk" } }
  if ([string]$ApkSha256 -eq "") { return @{ ok = $false; may_install = $false; reason = "missing_built_apk_hash" } }
  @{ ok = $true; may_install = $true; reason = "ok"; apk_sha256 = $ApkSha256 }
}

function New-RealFlutterTestArgs($RunId, $SelectedDevice, [ValidateSet("start", "recover")]$Phase) { @("test", "integration_test/android_real_gateway_handoff_test.dart", "-d", $SelectedDevice, "--no-uninstall", "--dart-define=FLYWHEEL_ANDROID_REAL_HANDOFF_PHASE=$Phase", "--dart-define=FLYWHEEL_ANDROID_REAL_HANDOFF_RUN_ID=$RunId") }
function Select-RealPhaseReceipt($Stdout) { $prefix = "FLYWHEEL_ANDROID_REAL_GATEWAY_HANDOFF_RECEIPT_JSON:"; foreach ($line in ($Stdout -split "`r?`n")) { if ($line.StartsWith($prefix)) { try { return ($line.Substring($prefix.Length) | ConvertFrom-Json -ErrorAction Stop) } catch { return [pscustomobject]@{ invalid_phase_receipt = $true; parse_error = $_.Exception.Message } } } }; $null }
function Get-Prop($Object, [string]$Name) { Get-PropValue $Object $Name }
function Test-RealPhaseReceipt($Receipt, $RunId, [string]$Phase) { if ($null -eq $Receipt) { return @{ ok = $false; reason = "missing_phase_receipt" } }; if ((Get-Prop $Receipt "invalid_phase_receipt") -eq $true) { return @{ ok = $false; reason = "invalid_phase_receipt_json" } }; if ((Get-Prop $Receipt "schema") -ne "flywheel.android-real-gateway-handoff-phase/v1") { return @{ ok = $false; reason = "schema_mismatch" } }; if ((Get-Prop $Receipt "run_id") -ne $RunId -or (Get-Prop $Receipt "phase") -ne $Phase) { return @{ ok = $false; reason = "phase_identity_mismatch" } }; if ((Get-Prop $Receipt "platform") -ne "android") { return @{ ok = $false; reason = "platform_not_android" } }; @{ ok = $true; reason = "ok" } }
function Get-RealMapEntries($Map) { if ($null -eq $Map) { return @() }; if ($Map -is [Collections.IDictionary]) { return @($Map.GetEnumerator() | ForEach-Object { @{ key = $_.Key; value = $_.Value } }) }; @($Map.PSObject.Properties | ForEach-Object { @{ key = $_.Name; value = $_.Value } }) }
function Test-RealOperationSet($OperationSet, [string]$ExpectedRequest, [string]$ExpectedOperation, [string]$Reason) {
  $rawRefs = Get-PropValue $OperationSet "operation_refs"; $refs = @(); if ($null -ne $rawRefs) { $refs = @($rawRefs) }
  if ($refs.Count -eq 0) { $refs = @((Get-PropValue $OperationSet "operations") | ForEach-Object { Get-PropValue $_ "operation_ref" }) }
  $map = Get-PropValue $OperationSet "request_sha256_by_operation"; $entries = @(Get-RealMapEntries $map)
  if ($null -ne (Get-PropValue $OperationSet "next_cursor")) { return @{ ok = $false; reason = $Reason; operation_count = $refs.Count; request_map_count = $entries.Count; paged = $true } }
  if ($refs.Count -ne 1 -or $refs[0] -ne $ExpectedOperation -or $entries.Count -ne 1 -or $entries[0].key -ne $ExpectedOperation -or $entries[0].value -ne $ExpectedRequest) { return @{ ok = $false; reason = $Reason; operation_count = $refs.Count; request_map_count = $entries.Count } }
  @{ ok = $true; reason = "ok"; operation_ref = $ExpectedOperation }
}
function Test-RealCombinedReceipt($Start, $Recover) {
  $request = Get-Prop $Start "request_sha256"; if ([string]$request -eq "") { return @{ ok = $false; reason = "missing_request_sha256" } }
  if ((Get-Prop $Recover "request_sha256") -ne $request) { return @{ ok = $false; reason = "request_sha_mismatch" } }
  if ((Get-Prop $Recover "recover_from_session") -ne $true) { return @{ ok = $false; reason = "recover_from_session_failed" } }
  $startRefs = @((Get-Prop $Start "operation_refs")); $recoverRefs = @((Get-Prop $Recover "operation_refs"))
  if ($startRefs.Count -ne 1 -or $recoverRefs.Count -ne 1 -or $startRefs[0] -ne $recoverRefs[0]) { return @{ ok = $false; reason = "journey_operation_set_mismatch" } }
  if ([int](Get-Prop $Recover "operation_count_for_request") -ne 1) { return @{ ok = $false; reason = "journey_operation_set_mismatch" } }
  $s = Test-RealOperationSet (Get-Prop $Start "operation_set") $request $startRefs[0] "journey_operation_set_mismatch"; if (!$s.ok) { return $s }
  $r = Test-RealOperationSet (Get-Prop $Recover "operation_set") $request $startRefs[0] "journey_operation_set_mismatch"; if (!$r.ok) { return $r }
  @{ ok = $true; reason = "ok"; operation_ref = $startRefs[0] }
}
function Test-RealPcOperationSet($PcOps, [string]$ExpectedRequest, [string]$ExpectedOperation) {
  $ops = @((Get-PropValue $PcOps "operations") | Where-Object { $null -ne $_ }); $refs = @($ops | ForEach-Object { Get-PropValue $_ "operation_ref" })
  if ($refs.Count -ne 1 -or $refs[0] -ne $ExpectedOperation) { return @{ ok = $false; reason = "pc_operation_set_mismatch"; operation_count = $refs.Count } }
  Test-RealOperationSet @{ operation_refs = $refs; request_sha256_by_operation = (Get-PropValue $PcOps "request_sha256_by_operation") } $ExpectedRequest $ExpectedOperation "pc_operation_set_mismatch"
}
function Test-RealCleanupState($Cleanup) {
  if ((Get-PropValue (Get-PropValue $Cleanup "reverse") "exit_code") -ne 0) { return @{ ok = $false; reason = "reverse_cleanup_failed" } }
  if ((Get-PropValue $Cleanup "uninstall_required") -eq $true) {
    if ((Get-PropValue (Get-PropValue $Cleanup "uninstall") "exit_code") -ne 0) { return @{ ok = $false; reason = "uninstall_cleanup_failed" } }
    if ((Get-PropValue (Get-PropValue $Cleanup "post_package") "status") -ne "absent") { return @{ ok = $false; reason = "package_left_installed" } }
  }
  $gatewayCleanup = Get-PropValue $Cleanup "gateway"
  if ((Get-PropValue $gatewayCleanup "stopped") -ne $true) { return @{ ok = $false; reason = "gateway_cleanup_failed" } }
  if ((Get-PropValue $gatewayCleanup "status") -ne "not_started" -and (Get-PropValue $gatewayCleanup "stdio_drain_complete") -ne $true) { return @{ ok = $false; reason = "gateway_stdio_drain_incomplete" } }
  if ((Get-PropValue (Get-PropValue $Cleanup "apk_restore") "status") -eq "failed") { return @{ ok = $false; reason = "apk_restore_failed" } }
  if ((Get-PropValue $Cleanup "temp_root_removed") -ne $true) { return @{ ok = $false; reason = "temp_root_cleanup_failed" } }
  @{ ok = $true; reason = "ok" }
}
function Select-RealRunnerBlocker([int]$StartExit, [int]$RecoverExit, $StartValidation, $RecoverValidation, $Combined, $Binding) { if ($StartExit -ne 0) { return "start_phase_failed" }; if ($RecoverExit -ne 0) { return "recover_phase_failed" }; foreach ($v in @($StartValidation, $RecoverValidation, $Combined, $Binding)) { if ((Get-Prop $v "ok") -ne $true) { return Get-Prop $v "reason" } }; "unknown_failure" }
function Invoke-GatewayOperationsRead($BaseUrl, $Token, $JourneyRef) { try { $uri = "$BaseUrl/api/operations?journey_ref=$([Uri]::EscapeDataString($JourneyRef))&limit=50"; $body = Invoke-WebRequest -UseBasicParsing -Uri $uri -Headers @{ Authorization = "Bearer $Token" } -TimeoutSec 10; ($body.Content | ConvertFrom-Json) } catch { [pscustomobject]@{ error = $_.Exception.Message } } }

