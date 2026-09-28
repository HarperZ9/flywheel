# Shared commands for the CI-only installed acceptance orchestrator.
function Invoke-Checked([string]$Label, [string]$FilePath, [string[]]$Arguments, [string]$WorkingDirectory = $repoRoot) {
  Push-Location $WorkingDirectory
  try {
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Label failed with exit $LASTEXITCODE" }
  } finally {
    Pop-Location
  }
}

function Read-Version() {
  $line = Get-Content -LiteralPath (Join-Path $desktopRoot "pubspec.yaml") | Where-Object { $_ -match '^version:' } | Select-Object -First 1
  if ($null -eq $line) { throw "could not read desktop pubspec version" }
  return (($line -replace 'version:\s*', '') -split '\+')[0].Trim()
}

function Assert-Sha256([string]$Name, [string]$Value) {
  if ($Value -notmatch '^[0-9a-f]{64}$') { throw "$Name is not a lowercase SHA-256" }
}
