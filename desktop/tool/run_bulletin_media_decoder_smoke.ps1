param(
  [string]$FlutterPath = "",
  [string]$ValidationDir = "",
  [string]$NuGetPath = "",
  [switch]$SelfTest
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$ProgressPreference = "SilentlyContinue"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktopRoot = (Resolve-Path (Join-Path $scriptRoot "..")).Path
$positiveSha256 = "c78f3f9d3e4834a91e83a0fb0fd005348354329ea58443f4156407b5f6d80413"
$unsupportedUrl = "https://chromium.googlesource.com/chromium/src/media/+/refs/heads/main/test/data/bear-320x180-hi10p.mp4?format=TEXT"
$unsupportedSha256 = "04ff92825f6c903e0bc1c662e38f45f9cc50177b7bc82c0e1aacca4ec5dd5610"
$proofSchema = "flywheel.bulletin-media-windows-decoder-proof/v2"

function New-DecoderRunId {
  return "decoder_" + [Guid]::NewGuid().ToString("N")
}

function New-DefaultValidationDir {
  $stamp = [DateTimeOffset]::UtcNow.ToString("yyyyMMddTHHmmssZ")
  return Join-Path ([System.IO.Path]::GetTempPath()) ("flywheel-bulletin-decoder-" + $stamp + "-" + [Guid]::NewGuid().ToString("N").Substring(0, 8))
}

function Write-JsonFile($Path, $Value) {
  $Value | ConvertTo-Json -Depth 24 | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Get-FileSha256($Path) {
  return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Resolve-FlutterExecutable($Path) {
  if ($Path -ne "") {
    $resolved = Resolve-Path -LiteralPath $Path -ErrorAction Stop
    if ((Get-Item -LiteralPath $resolved.Path).PSIsContainer) {
      throw "FlutterPath points to a directory, not an executable: $Path"
    }
    return $resolved.Path
  }
  $cmd = Get-Command flutter -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($null -eq $cmd) {
    throw "Flutter was not found on PATH. Pass -FlutterPath with the flutter executable path."
  }
  return $cmd.Source
}

function Add-NuGetToProcessPath($Path) {
  if ($Path -ne "") {
    $resolved = Resolve-Path -LiteralPath $Path -ErrorAction Stop
    if ((Get-Item -LiteralPath $resolved.Path).PSIsContainer) {
      throw "NuGetPath points to a directory, not nuget.exe: $Path"
    }
    $env:PATH = (Split-Path -Parent $resolved.Path) + [System.IO.Path]::PathSeparator + $env:PATH
    return @{ source = "explicit"; path = $resolved.Path }
  }
  $cmd = Get-Command nuget.exe -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($null -eq $cmd) {
    $cmd = Get-Command nuget -ErrorAction SilentlyContinue | Select-Object -First 1
  }
  if ($null -eq $cmd) {
    throw "nuget.exe was not found on PATH. Pass -NuGetPath for a verified portable NuGet CLI. No install or global PATH mutation was attempted."
  }
  return @{ source = "PATH"; path = $cmd.Source }
}

function Convert-PackageRoot($RootUri) {
  $root = [string]$RootUri
  if ($root.StartsWith("file:///")) {
    return [Uri]::UnescapeDataString($root.Substring(8))
  }
  return (Resolve-Path -LiteralPath $root).Path
}

function Get-PositiveMp4Source {
  $packageConfigPath = Join-Path $desktopRoot ".dart_tool/package_config.json"
  $packageConfig = Get-Content -Raw -LiteralPath $packageConfigPath | ConvertFrom-Json
  $videoPlayer = $packageConfig.packages | Where-Object { $_.name -eq "video_player" } | Select-Object -First 1
  if ($null -eq $videoPlayer) { throw "video_player package was not found in $packageConfigPath" }
  $mp4Source = Join-Path (Convert-PackageRoot $videoPlayer.rootUri) "example/assets/Butterfly-209.mp4"
  if (!(Test-Path -LiteralPath $mp4Source)) { throw "MP4 fixture missing from video_player package: $mp4Source" }
  return $mp4Source
}

function Ensure-UnsupportedFixture($Path) {
  if (!(Test-Path -LiteralPath $Path) -or ((Get-FileSha256 $Path) -ne $unsupportedSha256)) {
    $response = Invoke-WebRequest -Uri $unsupportedUrl -UseBasicParsing
    $clean = ([string]$response.Content) -replace "\s", ""
    [System.IO.File]::WriteAllBytes($Path, [Convert]::FromBase64String($clean))
  }
  Assert-True ((Get-FileSha256 $Path) -eq $unsupportedSha256) "Unsupported MP4 fixture hash mismatch"
}

function Assert-True($Condition, $Message) {
  if (-not $Condition) { throw $Message }
}

function Get-RequiredProperty($Object, $Name) {
  if ($null -eq $Object) { throw "Missing object while reading property $Name" }
  $prop = $Object.PSObject.Properties[$Name]
  if ($null -eq $prop) { throw "Missing required property: $Name" }
  return $prop.Value
}

function Assert-NumberGreaterThan($Value, $Min, $Message) {
  if ([double]$Value -le [double]$Min) { throw $Message }
}

function Assert-Bool($Value, $Expected, $Message) {
  if ([bool]$Value -ne [bool]$Expected) { throw $Message }
}

function Test-FixtureIdentity($Fixtures, $Name, $ExpectedPath, $ExpectedSha256) {
  $entry = Get-RequiredProperty $Fixtures $Name
  $actualPath = Get-RequiredProperty $entry "path"
  $actualSha = [string](Get-RequiredProperty $entry "sha256")
  $actualBytes = [int64](Get-RequiredProperty $entry "bytes")
  Assert-True (([System.IO.Path]::GetFullPath([string]$actualPath)) -eq ([System.IO.Path]::GetFullPath([string]$ExpectedPath))) "$Name fixture path mismatch"
  Assert-True ($actualSha.ToLowerInvariant() -eq $ExpectedSha256) "$Name fixture receipt hash mismatch"
  Assert-True (Test-Path -LiteralPath $ExpectedPath) "$Name fixture file missing: $ExpectedPath"
  Assert-True ((Get-FileSha256 $ExpectedPath) -eq $ExpectedSha256) "$Name current file hash mismatch"
  Assert-True ((Get-Item -LiteralPath $ExpectedPath).Length -eq $actualBytes) "$Name fixture byte count mismatch"
}

function Test-CaseShape($Cases, $Name) {
  $case = Get-RequiredProperty $Cases $Name
  foreach ($field in @("path", "sha256", "bytes", "initialized", "has_error", "duration_ms", "position_ms", "frame_width", "frame_height")) {
    [void](Get-RequiredProperty $case $field)
  }
  return $case
}

function Test-DecoderReceipt($ReceiptPath, $RunId, $PositiveFixture, $UnsupportedFixture) {
  if (!(Test-Path -LiteralPath $ReceiptPath)) { throw "Decoder receipt missing after zero exit: $ReceiptPath" }
  try {
    $proof = Get-Content -Raw -LiteralPath $ReceiptPath | ConvertFrom-Json
  } catch {
    throw "Decoder receipt is malformed JSON: $($_.Exception.Message)"
  }
  Assert-True ((Get-RequiredProperty $proof "schema") -eq $proofSchema) "Decoder receipt schema mismatch"
  Assert-Bool (Get-RequiredProperty $proof "complete") $true "Decoder receipt is not complete"
  Assert-True ((Get-RequiredProperty $proof "run_id") -eq $RunId) "Decoder receipt run_id is stale or mismatched"
  $fixtures = Get-RequiredProperty $proof "fixtures"
  Test-FixtureIdentity $fixtures "h264_mp4" $PositiveFixture $positiveSha256
  Test-FixtureIdentity $fixtures "unsupported_h264_high10_mp4" $UnsupportedFixture $unsupportedSha256
  $cases = Get-RequiredProperty $proof "cases"
  $wav = Test-CaseShape $cases "wav"
  $mp4 = Test-CaseShape $cases "h264_mp4"
  $corrupt = Test-CaseShape $cases "corrupt_mp4"
  $unsupported = Test-CaseShape $cases "unsupported_h264_high10_mp4"
  foreach ($field in @("negative", "initialize_threw")) {
    [void](Get-RequiredProperty $corrupt $field)
    [void](Get-RequiredProperty $unsupported $field)
  }
  Assert-Bool (Get-RequiredProperty $wav "initialized") $true "WAV did not initialize"
  Assert-NumberGreaterThan (Get-RequiredProperty $wav "position_ms") 0 "WAV did not progress"
  Assert-Bool (Get-RequiredProperty $mp4 "initialized") $true "H.264 MP4 did not initialize"
  Assert-NumberGreaterThan (Get-RequiredProperty $mp4 "position_ms") 0 "H.264 MP4 did not progress"
  Assert-NumberGreaterThan (Get-RequiredProperty $mp4 "frame_width") 0 "H.264 MP4 frame width missing"
  Assert-NumberGreaterThan (Get-RequiredProperty $mp4 "frame_height") 0 "H.264 MP4 frame height missing"
  Assert-Bool (Get-RequiredProperty $corrupt "negative") $true "Corrupt MP4 was not rejected"
  Assert-Bool (Get-RequiredProperty $unsupported "negative") $true "Unsupported high-10 MP4 was not rejected"
  $unsupportedThrew = [bool](Get-RequiredProperty $unsupported "initialize_threw")
  $unsupportedErrored = [bool](Get-RequiredProperty $unsupported "has_error")
  Assert-True ($unsupportedThrew -or $unsupportedErrored) "Unsupported high-10 MP4 did not throw or report an error"
  return $proof
}

function Save-DecoderFailure($Path, $RunId, $ExitCode, $LogPath, $Message, $ReceiptPath) {
  $partial = $null
  if (Test-Path -LiteralPath $ReceiptPath) {
    try { $partial = Get-Content -Raw -LiteralPath $ReceiptPath | ConvertFrom-Json } catch { $partial = @{ unreadable = $true } }
  }
  Write-JsonFile $Path @{
    schema = "flywheel.bulletin-media-windows-decoder-failure/v1"
    complete = $false
    run_id = $RunId
    exit_code = $ExitCode
    log_path = $LogPath
    receipt_path = $ReceiptPath
    failure = $Message
    partial_proof = $partial
  }
}

function Repair-CMakeInstallPrefix($ValidationRoot) {
  $buildDir = Join-Path $desktopRoot "build/windows/x64"
  if (!(Test-Path -LiteralPath $buildDir)) {
    return @{ attempted = $false; reason = "build/windows/x64 absent; Flutter will generate it" }
  }
  $cmake = Get-Command cmake -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($null -eq $cmake) {
    return @{ attempted = $false; reason = "cmake not found on PATH" }
  }
  $runnerDebug = Join-Path $buildDir "runner/Debug"
  New-Item -ItemType Directory -Force -Path $runnerDebug | Out-Null
  $prefix = (Resolve-Path -LiteralPath $runnerDebug).Path -replace "\\", "/"
  $logPath = Join-Path $ValidationRoot "cmake-reconfigure-runner-debug-install.log"
  Push-Location $desktopRoot
  try {
    & $cmake.Source -S windows -B build/windows/x64 -DCMAKE_INSTALL_PREFIX="$prefix" *> $logPath
    $exit = $LASTEXITCODE
  } finally {
    Pop-Location
  }
  if ($exit -ne 0) { throw "CMake install-prefix repair failed with exit $exit. See $logPath" }
  return @{ attempted = $true; install_prefix = $prefix; log_path = $logPath }
}

if ($SelfTest) {
  . (Join-Path $scriptRoot "test_bulletin_media_decoder_smoke.ps1")
  exit 0
}

$validationRoot = $ValidationDir
if ($validationRoot -eq "") { $validationRoot = New-DefaultValidationDir }
New-Item -ItemType Directory -Force -Path $validationRoot | Out-Null
$fixtureDir = Join-Path $validationRoot "bulletin-media-decoder-fixtures"
$receiptPath = Join-Path $validationRoot "bulletin-media-windows-decoder-values.json"
$failurePath = Join-Path $validationRoot "bulletin-media-windows-decoder-failure.json"
$runSummaryPath = Join-Path $validationRoot "bulletin-media-windows-decoder-run.json"
$logPath = Join-Path $validationRoot "bulletin-media-windows-decoder-flutter-test.log"
$runId = New-DecoderRunId
New-Item -ItemType Directory -Force -Path $fixtureDir | Out-Null
Set-Location $desktopRoot

$oldPath = $env:PATH
try {
  $flutter = Resolve-FlutterExecutable $FlutterPath
  $nuget = Add-NuGetToProcessPath $NuGetPath
  & $flutter pub get
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

  $cmakeRepair = Repair-CMakeInstallPrefix $validationRoot
  $mp4Source = Get-PositiveMp4Source

  $mp4Fixture = Join-Path $fixtureDir "Butterfly-209.mp4"
  $unsupportedFixture = Join-Path $fixtureDir "bear-320x180-hi10p.mp4"
  Copy-Item -LiteralPath $mp4Source -Destination $mp4Fixture -Force
  Assert-True ((Get-FileSha256 $mp4Fixture) -eq $positiveSha256) "Positive MP4 fixture hash mismatch"
  Ensure-UnsupportedFixture $unsupportedFixture

  $env:BULLETIN_DECODER_RECEIPT = $receiptPath
  $env:BULLETIN_DECODER_RUN_ID = $runId
  $env:BULLETIN_DECODER_MP4 = $mp4Fixture
  $env:BULLETIN_DECODER_UNSUPPORTED_MP4 = $unsupportedFixture

  & $flutter test integration_test/bulletin_media_decoder_test.dart -d windows --reporter expanded `
    --dart-define "BULLETIN_DECODER_RECEIPT=$receiptPath" `
    --dart-define "BULLETIN_DECODER_RUN_ID=$runId" `
    --dart-define "BULLETIN_DECODER_MP4=$mp4Fixture" `
    --dart-define "BULLETIN_DECODER_UNSUPPORTED_MP4=$unsupportedFixture" 2>&1 |
    Tee-Object -FilePath $logPath
  $testExit = $LASTEXITCODE
  if ($testExit -ne 0) {
    Save-DecoderFailure $failurePath $runId $testExit $logPath "flutter integration test failed" $receiptPath
    exit $testExit
  }

  try {
    $proof = Test-DecoderReceipt $receiptPath $runId $mp4Fixture $unsupportedFixture
  } catch {
    Save-DecoderFailure $failurePath $runId 1 $logPath $_.Exception.Message $receiptPath
    exit 1
  }

  Write-JsonFile $runSummaryPath @{
    schema = "flywheel.bulletin-media-windows-decoder-run/v1"
    complete = $true
    run_id = $runId
    validation_dir = $validationRoot
    flutter_path = $flutter
    nuget = $nuget
    cmake_install_prefix_repair = $cmakeRepair
    positive_mp4_sha256 = $positiveSha256
    unsupported_mp4_sha256 = $unsupportedSha256
    unsupported_source_url = $unsupportedUrl
    receipt_path = $receiptPath
    log_path = $logPath
    proof = $proof
  }
  Get-Content -Raw -LiteralPath $runSummaryPath
  exit 0
} finally {
  $env:PATH = $oldPath
}
