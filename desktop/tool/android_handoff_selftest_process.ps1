# Process-capture self-test for run_android_handoff_acceptance.ps1.
# Dot-sourced after android_handoff_runner_support.ps1, which defines
# Invoke-Captured and Quote-PSLiteral.
#
# The timeout case must kill a grandchild, so the grandchild has to exist
# before the deadline fires. The old self-test gave the parent pwsh one second
# to start, spawn the grandchild and write its PID. A loaded Windows runner can
# spend longer than that starting pwsh; the deadline then killed the parent
# first, no PID file appeared, and the self-test failed although the kill path
# worked. The poll hook below blocks until the PID is on disk, and
# Invoke-Captured checks the deadline only after the hook returns, so the kill
# always happens with a known grandchild.

function New-SelfTestScripts([string]$Ps) {
  $temp = [System.IO.Path]::GetTempPath()
  $paths = @{}
  foreach ($name in @("io", "timeout", "poll", "env")) { $paths[$name] = Join-Path $temp ("fw-android-$name-" + [Guid]::NewGuid().ToString("N") + ".ps1") }
  $paths["child_pid"] = Join-Path $temp ("fw-android-child-" + [Guid]::NewGuid().ToString("N") + ".txt")
  $pidPart = $paths["child_pid"] + ".part"
  Set-Content -LiteralPath $paths["io"] -Encoding ASCII -Value "foreach (`$i in 1..600) { Write-Output `"out-`$i`"; [Console]::Error.WriteLine(`"err-`$i`") }"
  $timeoutLines = @(
    "`$child = Start-Process -WindowStyle Hidden -FilePath $(Quote-PSLiteral $Ps) -ArgumentList @('-NoProfile','-Command','Start-Sleep -Seconds 20') -PassThru",
    "Set-Content -LiteralPath $(Quote-PSLiteral $pidPart) -Value `$child.Id -Encoding ASCII",
    "Move-Item -LiteralPath $(Quote-PSLiteral $pidPart) -Destination $(Quote-PSLiteral $paths["child_pid"]) -Force",
    "Start-Sleep -Seconds 20")
  Set-Content -LiteralPath $paths["timeout"] -Encoding ASCII -Value ($timeoutLines -join "`n")
  Set-Content -LiteralPath $paths["poll"] -Encoding ASCII -Value "Start-Sleep -Milliseconds 900; Write-Output poll-ok"
  Set-Content -LiteralPath $paths["env"] -Encoding ASCII -Value "Write-Output `$env:FW_ANDROID_SIGNING_ENV_SELFTEST"
  return $paths
}

function Invoke-SelfTestTimeoutCase([string]$Ps, [string]$Script, [string]$ChildPidFile) {
  # The pid file is renamed into place, so a reader never sees a partial write.
  $readPid = {
    $fwSelfTestUntil = [DateTimeOffset]::UtcNow.AddSeconds(20)
    while ([DateTimeOffset]::UtcNow -lt $fwSelfTestUntil) {
      if (Test-Path -LiteralPath $ChildPidFile) { return @{ child_pid = [int](Get-Content -LiteralPath $ChildPidFile -Raw).Trim() } }
      Start-Sleep -Milliseconds 50
    }
    return @{ child_pid = -1 }
  }
  $run = Invoke-Captured $Ps @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $Script) ([System.IO.Path]::GetTempPath()) 1 -OnPoll $readPid -PollMilliseconds 50
  $childPid = if ($null -ne $run.poll_result) { [int]$run.poll_result.child_pid } else { -1 }
  $child = if ($childPid -gt 0) { Get-Process -Id $childPid -ErrorAction SilentlyContinue } else { $null }
  # Wait for the exit event instead of sleeping a fixed time; the grandchild
  # sleeps 20 s, so a missed kill still shows as alive after this bound.
  $childAlive = ($childPid -le 0) -or (($null -ne $child) -and -not $child.WaitForExit(5000))
  return @{ run = $run; child_pid = $childPid; child_alive = $childAlive }
}

function Assert-SelfTestProcessCapture($Io, $Timeout, $Poll, $EnvRun) {
  $failures = @()
  if ($Io.exit_code -ne 0 -or $Io.stdout -notmatch "out-600" -or $Io.stderr -notmatch "err-600") { $failures += "stdout/stderr capture" }
  if ($Timeout.child_pid -le 0) { $failures += "timeout grandchild pid never written" }
  if ($Timeout.run.exit_code -ne 124 -or $Timeout.run.timed_out -ne $true) { $failures += "timeout exit code" }
  if ($Timeout.child_alive) { $failures += "timeout grandchild survived" }
  if ($Poll.exit_code -ne 0 -or $null -eq $Poll.poll_result -or $Poll.poll_result.captured -ne $true) { $failures += "during-run poll" }
  if ($EnvRun.stdout.Trim() -ne "ok") { $failures += "environment override" }
  if ($failures.Count -gt 0) { throw ("self-test process assertions failed: " + ($failures -join "; ")) }
}

function Invoke-SelfTestProcessCapture {
  $ps = (Get-Process -Id $PID).Path; $temp = [System.IO.Path]::GetTempPath(); $paths = New-SelfTestScripts $ps; $timeout = $null
  try {
    $pollState = @{ count = 0 }
    $io = Invoke-Captured $ps @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $paths["io"]) $temp 20
    $timeout = Invoke-SelfTestTimeoutCase $ps $paths["timeout"] $paths["child_pid"]
    $poll = Invoke-Captured $ps @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $paths["poll"]) $temp 10 -OnPoll { $pollState.count += 1; return @{ captured = $true; polls = $pollState.count } } -PollMilliseconds 100
    $envRun = Invoke-Captured $ps @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $paths["env"]) $temp 10 -Environment @{ FW_ANDROID_SIGNING_ENV_SELFTEST = "ok" }
    Assert-SelfTestProcessCapture $io $timeout $poll $envRun
    return @{ io = $io; timeout = $timeout; poll = $poll; env = $envRun }
  } finally {
    if ($null -ne $timeout -and $timeout.child_pid -gt 0) { Stop-Process -Id $timeout.child_pid -Force -ErrorAction SilentlyContinue }
    Remove-Item -LiteralPath $paths["io"], $paths["timeout"], $paths["poll"], $paths["env"], $paths["child_pid"], ($paths["child_pid"] + ".part") -Force -ErrorAction SilentlyContinue
  }
}
