#!/usr/bin/env pwsh
<#
  critic.ps1 - the bilateral accountability critic (operator-facing).

  The substrate judges the WORK (green/red). This judges the OPERATOR: it reads
  live state - git across the sub-repos + STATE.md - and asks the questions the
  GAPS imply: FINISH, FOCUS, VERIFY, SCOPE. Questions are generated from state,
  not a question bank, and there is no flag to make it flatter you. Evidence over
  ego, aimed at the human instead of the machine.

  Default                       -> the standup (the questions it puts to you).
  -For <TAG> -Record "<answer>" -> append a decision-receipt to DECISIONS.md
                                   (append-only, inspectable, not re-litigated).
  -Repos a,b,c                  -> override the repos to scan (default: git
                                   subdirectories of the repo root).

  Reference implementation. Part of accountable-engine.
#>
param([string] $For = '', [string] $Record = '', [string[]] $Repos = @())
$ErrorActionPreference = 'Continue'

$Root      = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$StateFile = Join-Path $Root 'STATE.md'
$Decisions = Join-Path $Root 'DECISIONS.md'

if (-not $Repos -or $Repos.Count -eq 0) {
  $Repos = @(Get-ChildItem $Root -Directory -ErrorAction SilentlyContinue |
             Where-Object { Test-Path (Join-Path $_.FullName '.git') } |
             ForEach-Object { $_.Name })
}

# --- record a decision-receipt --------------------------------------------
if ($Record) {
  if (-not (Test-Path $Decisions)) {
    @(
      '# Operator decision ledger - the bilateral critic''s answers',
      '',
      '> The substrate records what the work did; this records what the operator',
      '> decided, and why. Append-only, inspectable, not re-litigated.',
      ''
    ) -join "`r`n" | Set-Content -LiteralPath $Decisions -Encoding utf8
  }
  $tag = if ($For) { "**[$For]** " } else { '' }
  "- $((Get-Date).ToString('yyyy-MM-dd HH:mm')) - $tag$Record" |
    Add-Content -LiteralPath $Decisions -Encoding utf8
  Write-Host "recorded -> DECISIONS.md"
  return
}

$state = if (Test-Path $StateFile) { Get-Content $StateFile -Raw } else { '' }
function Head($t) { Write-Host "`n$t" -ForegroundColor Cyan }
Write-Host "=== critic - the substrate's questions for YOU ===" -ForegroundColor White

# 1. FINISH (keystone) - unmerged branches. The cure for sprawl runs first.
$unmerged = New-Object System.Collections.Generic.List[string]
foreach ($r in $Repos) {
  $d = Join-Path $Root $r
  if (-not (Test-Path (Join-Path $d '.git'))) { continue }
  $nm = @(git -C $d branch --no-merged main 2>$null) |
        ForEach-Object { ($_ -replace '^[\*\+ ]+','').Trim() } |
        Where-Object { $_ -and $_ -notmatch '^\(' }
  foreach ($b in $nm) { $unmerged.Add("$r/$b") }
}
Head "[FINISH]  keystone - sprawl check"
if ($unmerged.Count) {
  Write-Host "  $($unmerged.Count) branch(es) unmerged to main:"
  $unmerged | ForEach-Object { Write-Host "    - $_" }
  Write-Host "  Q: which ONE reaches main first? Nothing new starts until one does."
} else {
  Write-Host "  clean - everything is merged."
}

# 2. FOCUS - claimed unit vs. open fronts
$open = @([regex]::Matches($state, '(?m)^\| ([A-Z]{2,5}-\d+) \| ') | ForEach-Object { $_.Groups[1].Value })
Head "[FOCUS]   one unit, one branch"
Write-Host ("  open edges in STATE: " + $(if ($open.Count) { $open -join ', ' } else { 'none listed' }))
Write-Host "  Q: are you finishing the claimed unit, or fragmenting onto a new front?"

# 3. VERIFY - claimed/pushed without a green receipt
$unver = @([regex]::Matches($state, '(?im)^.*\b(not yet run|unverified|pending|untrusted|pre-merge gate|deploy pending)\b.*$') |
           ForEach-Object { ($_.Value -replace '\s+',' ').Trim() } | Select-Object -First 5)
Head "[VERIFY]  receipt, not vibe"
if ($unver.Count) {
  $unver | ForEach-Object { Write-Host "    ! $_" }
  Write-Host "  Q: are you trusting that on a receipt, or on a vibe?"
} else {
  Write-Host "  no unverified markers flagged in STATE."
}

# 4. SCOPE (gate) - the standing ethics check
Head "[SCOPE]   GATE - answer before proceeding"
Write-Host "  Q: does the current work touch your declared out-of-scope boundary?"
Write-Host "     - authorization in place?"
Write-Host "     - in scope, or out by construction?"
Write-Host "     - the work you intend, or drift away from it?"

Write-Host "`nAnswer any:  ./critic.ps1 -For FINISH -Record `"<your call>`"   (-> DECISIONS.md)" -ForegroundColor DarkGray
