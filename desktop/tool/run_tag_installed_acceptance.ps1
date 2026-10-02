param([string]$Tag, [switch]$DefineOnly)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$entryRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$tagDefineOnly = [bool]$DefineOnly
# Load existing source/host/argument checks without rebuilding or checking out anything.
. (Join-Path $entryRoot "run_ci_installed_acceptance.ps1") -DefineOnly
function Assert-TagInstallerSource([string]$Tag, [string]$Version, [string]$Commit) {
  # Minor (vX.Y.0) and patch (vX.Y.Z) release tags; no pre-release or build suffix.
  if ($Tag -cne "v$Version" -or $Tag -cnotmatch '^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$') { throw "tag must match release source version" }
  Assert-ExactCommit $Commit
  $tagCommit = (& git -C $repoRoot rev-parse "refs/tags/$Tag^{commit}").Trim()
  if ($LASTEXITCODE -ne 0 -or $tagCommit -cne $Commit) { throw "release tag does not match exact source commit" }
}
function Read-ExpectedInstallerHash() {
  $rows = @(Get-Content -LiteralPath (Join-Path $installerDir "SHA256SUMS.txt"))
  if ($rows.Count -ne 1 -or $rows[0] -cnotmatch '^([0-9a-f]{64})  (Flywheel-Setup-[^\\/]+\.exe)$') {
    throw "expected one exact installer checksum"
  }
  $expectedHash = $Matches[1]
  $installerName = $Matches[2]
  $installers = @(Get-ChildItem -LiteralPath $installerDir -Filter "Flywheel-Setup-*.exe")
  if ($installers.Count -ne 1 -or $installers[0].Name -cne $installerName) { throw "installer checksum filename mismatch" }
  return $expectedHash
}
if ($tagDefineOnly) { return }
Set-Location $repoRoot
Assert-Repository
$targetCommit = (& git -C $repoRoot rev-parse HEAD).Trim()
$version = Read-Version
Assert-TagInstallerSource $Tag $version $targetCommit
Assert-WorkflowSource $targetCommit
Assert-CleanWorkspaceNoUntracked "before tag candidate acceptance"
$expectedInstallerHash = Read-ExpectedInstallerHash
. (Join-Path $scriptRoot "installed_acceptance_phase.ps1") -ExpectedInstallerSha256 $expectedInstallerHash -SourceKind "tag-candidate"
