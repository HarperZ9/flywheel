$root = Join-Path ([System.IO.Path]::GetTempPath()) ("flywheel-bulletin-decoder-validator-selftest-" + [Guid]::NewGuid().ToString("N").Substring(0, 8))
  New-Item -ItemType Directory -Force -Path $root | Out-Null
  $positive = Join-Path $root "positive.mp4"
  $unsupported = Join-Path $root "unsupported.mp4"
  Copy-Item -LiteralPath (Get-PositiveMp4Source) -Destination $positive -Force
  Ensure-UnsupportedFixture $unsupported
  $runId = New-DecoderRunId
  $valid = @{
    schema = $proofSchema
    run_id = $runId
    complete = $true
    fixtures = @{
      h264_mp4 = @{ path = $positive; sha256 = $positiveSha256; bytes = (Get-Item -LiteralPath $positive).Length }
      unsupported_h264_high10_mp4 = @{ path = $unsupported; sha256 = $unsupportedSha256; bytes = (Get-Item -LiteralPath $unsupported).Length }
    }
    cases = @{
      wav = @{ path = "tone.wav"; sha256 = "x"; bytes = 1; initialized = $true; has_error = $false; duration_ms = 2000; position_ms = 100; frame_width = 0; frame_height = 0 }
      h264_mp4 = @{ path = $positive; sha256 = $positiveSha256; bytes = (Get-Item -LiteralPath $positive).Length; initialized = $true; has_error = $false; duration_ms = 7540; position_ms = 100; frame_width = 1280; frame_height = 720 }
      corrupt_mp4 = @{ path = "corrupt.mp4"; sha256 = "x"; bytes = 512; initialized = $false; has_error = $false; initialize_threw = $false; duration_ms = 0; position_ms = 0; frame_width = 0; frame_height = 0; negative = $true }
      unsupported_h264_high10_mp4 = @{ path = $unsupported; sha256 = $unsupportedSha256; bytes = (Get-Item -LiteralPath $unsupported).Length; initialized = $false; has_error = $true; initialize_threw = $false; duration_ms = 0; position_ms = 0; frame_width = 0; frame_height = 0; negative = $true }
    }
  }
  $cases = @()
  function Run-ValidatorCase($Name, $ExpectPass, $Prepare) {
    $receipt = Join-Path $root ($Name + ".json")
    & $Prepare $receipt
    $passed = $false
    $message = ""
    try {
      [void](Test-DecoderReceipt $receipt $runId $positive $unsupported)
      $passed = $true
    } catch {
      $message = $_.Exception.Message
    }
    $ok = ($passed -eq $ExpectPass)
    $script:cases += @{ name = $Name; simulated_flutter_exit = 0; expected_pass = $ExpectPass; observed_pass = $passed; ok = $ok; message = $message }
    if (-not $ok) { throw "Self-test case $Name failed: $message" }
  }
  Run-ValidatorCase "valid-control" $true { param($p) Write-JsonFile $p $valid }
  Run-ValidatorCase "zero-exit-missing-receipt" $false { param($p) }
  Run-ValidatorCase "zero-exit-stale-run-id" $false { param($p) $copy = $valid.Clone(); $copy.run_id = "decoder_stale"; Write-JsonFile $p $copy }
  Run-ValidatorCase "zero-exit-wrong-fixture" $false { param($p) $copy = $valid.Clone(); $copy.fixtures = $valid.fixtures.Clone(); $copy.fixtures.h264_mp4 = $valid.fixtures.h264_mp4.Clone(); $copy.fixtures.h264_mp4.sha256 = "0000000000000000000000000000000000000000000000000000000000000000"; Write-JsonFile $p $copy }
  Run-ValidatorCase "zero-exit-malformed-receipt" $false { param($p) Set-Content -LiteralPath $p -Encoding UTF8 -Value "{" }
  $summary = @{ schema = "flywheel.bulletin-media-windows-decoder-runner-selftest/v1"; complete = $true; root = $root; cases = $cases }
  $summaryPath = Join-Path $root "selftest-summary.json"
  Write-JsonFile $summaryPath $summary
  $summary | ConvertTo-Json -Depth 12
