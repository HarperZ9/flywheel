param(
  [string]$FlutterPath = "",
  [string]$PythonPath = "",
  [string]$ValidationDir = ""
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktopRoot = (Resolve-Path (Join-Path $scriptRoot "..")).Path
$repoRoot = (Resolve-Path (Join-Path $desktopRoot "..")).Path

function Resolve-Executable {
  param(
    [string]$ExplicitPath,
    [string[]]$CommandNames,
    [string]$ParameterName
  )
  if (![string]::IsNullOrWhiteSpace($ExplicitPath)) {
    $resolved = Resolve-Path -LiteralPath $ExplicitPath -ErrorAction Stop
    if ($resolved.Count -ne 1) {
      throw "-$ParameterName resolved to $($resolved.Count) paths"
    }
    return $resolved[0].ProviderPath
  }
  foreach ($commandName in $CommandNames) {
    $command = Get-Command $commandName -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -ne $command) {
      return $command.Source
    }
  }
  throw "Unable to locate $($CommandNames -join ' or '); pass -$ParameterName with an executable path."
}

function Read-JsonFile {
  param([string]$Path)
  try {
    return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
  } catch {
    throw "Unable to parse JSON at ${Path}: $($_.Exception.Message)"
  }
}

function Require-StringField {
  param(
    [object]$Object,
    [string]$FieldName,
    [string]$Source
  )
  $value = $Object.$FieldName
  if ($value -isnot [string] -or [string]::IsNullOrWhiteSpace($value)) {
    throw "$Source field '$FieldName' is missing or empty"
  }
  return $value
}

function Assert-GatewayReceipt {
  param(
    [string]$ReceiptPath,
    [string]$ConfigPath
  )
  if (!(Test-Path -LiteralPath $ReceiptPath)) {
    throw "Flutter test exited 0 but did not write gateway E2E receipt: $ReceiptPath"
  }
  $receipt = Read-JsonFile $ReceiptPath
  $config = Read-JsonFile $ConfigPath
  if ($receipt.schema -ne "flywheel.bulletin-media-dart-gateway-e2e/v1") {
    throw "Unexpected gateway E2E receipt schema: $($receipt.schema)"
  }
  if ($receipt.complete -ne $true) {
    throw "Gateway E2E receipt is not complete"
  }
  if ($receipt.result_state -ne "posted_readback_match") {
    throw "Gateway E2E result_state was '$($receipt.result_state)', expected 'posted_readback_match'"
  }
  if ([int64]$receipt.preview_bytes -le 0) {
    throw "Gateway E2E preview_bytes must be positive"
  }
  foreach ($field in @("run_id", "artifact_id", "proposal_ref", "grant_ref")) {
    Require-StringField $receipt $field "receipt" | Out-Null
  }
  if ($receipt.run_id -ne $config.run_id) {
    throw "Gateway E2E receipt run_id does not match fixture config"
  }
  if ($receipt.artifact_id -ne $config.artifact_id) {
    throw "Gateway E2E receipt artifact_id does not match fixture config"
  }
}

$flutterExe = Resolve-Executable $FlutterPath @("flutter") "FlutterPath"
$pythonExe = Resolve-Executable $PythonPath @("python", "python3") "PythonPath"
$startedAt = [DateTime]::UtcNow.ToString("o")
$runStamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$runId = [guid]::NewGuid().ToString("N")
if ([string]::IsNullOrWhiteSpace($ValidationDir)) {
  $validationBase = [System.IO.Path]::GetTempPath()
} else {
  New-Item -ItemType Directory -Force -Path $ValidationDir | Out-Null
  $validationBase = (Resolve-Path -LiteralPath $ValidationDir).Path
}
$validationRoot = Join-Path $validationBase "flywheel-bulletin-gateway-e2e-$runStamp-$runId"

$fixtureRoot = Join-Path $validationRoot "fixture"
$configPath = Join-Path $fixtureRoot "gateway-fixture.json"
$receiptPath = Join-Path $validationRoot "bulletin-media-dart-gateway-e2e-values.json"
$fixtureLog = Join-Path $validationRoot "bulletin-media-gateway-fixture.log"
$fixtureErrLog = Join-Path $validationRoot "bulletin-media-gateway-fixture.err.log"
$testLog = Join-Path $validationRoot "bulletin-media-dart-gateway-e2e-flutter-test.log"
$runSummaryPath = Join-Path $validationRoot "bulletin-media-gateway-e2e-run.json"
$process = $null
$testExit = 1
$caughtError = $null

New-Item -ItemType Directory -Force -Path $fixtureRoot | Out-Null
Set-Location $desktopRoot

try {
  & $flutterExe pub get
  if ($LASTEXITCODE -ne 0) {
    $testExit = $LASTEXITCODE
    throw "flutter pub get failed with exit code $testExit"
  }

  $fixtureArgs = @(
    (Join-Path $scriptRoot "bulletin_media_gateway_fixture.py"),
    "--fixture-root", $fixtureRoot,
    "--config", $configPath
  )
  $process = Start-Process -FilePath $pythonExe -ArgumentList $fixtureArgs `
    -WorkingDirectory $repoRoot -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput $fixtureLog -RedirectStandardError $fixtureErrLog

  $deadline = (Get-Date).AddSeconds(20)
  while (!(Test-Path -LiteralPath $configPath)) {
    if ($process.HasExited) {
      throw "fixture exited before writing config; see $fixtureLog"
    }
    if ((Get-Date) -gt $deadline) {
      throw "fixture did not become ready before timeout; see $fixtureLog"
    }
    Start-Sleep -Milliseconds 250
  }

  $env:BULLETIN_GATEWAY_FIXTURE = $configPath
  $env:BULLETIN_GATEWAY_E2E_RECEIPT = $receiptPath

  & $flutterExe test test/bulletin_media_gateway_e2e_test.dart --reporter expanded `
    --dart-define "BULLETIN_GATEWAY_FIXTURE=$configPath" `
    --dart-define "BULLETIN_GATEWAY_E2E_RECEIPT=$receiptPath" 2>&1 |
    Tee-Object -FilePath $testLog
  $testExit = $LASTEXITCODE
  if ($testExit -eq 0) {
    Assert-GatewayReceipt $receiptPath $configPath
  }
} catch {
  $caughtError = $_
  $testExit = 1
} finally {
  if ($null -ne $process -and !$process.HasExited) {
    Stop-Process -Id $process.Id -Force
    $process.WaitForExit()
  }

  $summary = [ordered]@{
    schema = "flywheel.bulletin-media-gateway-e2e-run/v1"
    complete = ($null -eq $caughtError -and $testExit -eq 0)
    started_at = $startedAt
    finished_at = [DateTime]::UtcNow.ToString("o")
    validation_root = $validationRoot
    fixture_root = $fixtureRoot
    config_path = $configPath
    receipt_path = $receiptPath
    fixture_log = $fixtureLog
    fixture_error_log = $fixtureErrLog
    test_log = $testLog
    flutter_path = $flutterExe
    python_path = $pythonExe
    fixture_pid = if ($null -ne $process) { $process.Id } else { $null }
    test_exit = $testExit
    error = if ($null -ne $caughtError) { $caughtError.Exception.Message } else { $null }
  }
  $summary | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $runSummaryPath -Encoding UTF8
  Write-Host "Gateway E2E run summary: $runSummaryPath"
}

if ($null -ne $caughtError) {
  [Console]::Error.WriteLine($caughtError.Exception.Message)
}
exit $testExit
