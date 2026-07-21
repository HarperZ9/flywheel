# QCR Unblock Wave 2 Implementation Plan

> **For Codex:** Use `superpowers:subagent-driven-development` task by task.
> Write the falsifier first, observe RED, implement the smallest conforming
> behavior, then rerun the exact gate before review.

**Goal:** Populate the source-derived amplitude/channel manifest, make the five
preserved Mneme measurements executable through Crucible's existing replay-pack
contract, and exercise or conclusively identify the existing Windows-native 14B
endpoint without WSL or new infrastructure.

**Architecture:** Flywheel owns the physics manifest and source receipt; Mneme
owns its drift oracle and replay-pack producer; Crucible adds one generic
fail-closed assessment-presence check while retaining its provider-neutral pack
contract; the endpoint uses the existing Ollama release/profile/gate/proposer
and TaskSpec surfaces. Scratch run `qcr-2026-07-21-02` carries cross-repository
and runtime receipts.

**Tech stack:** Python 3.10+, stdlib JSON/SQLite/hashlib, pytest, existing
Flywheel/Mneme/Crucible CLIs, Windows-native Ollama.

**Design:**
`docs/superpowers/specs/2026-07-21-qcr-unblock-wave2-design.md`

## Task 1: Pin the amplitude/channel manifest contract with RED tests

**Owner:** Flywheel worktree

**Files:**

- Create: `tests/test_qcr_amplitude_manifest.py`
- Expected missing target: `configs/qcr/amplitude-closure-manifest-v1.json`

### Step 1: Write the failing schema/semantic tests

The tests must require:

- schema `qcr.amplitude-closure-manifest/v1` and a non-result status;
- exactly the four version-pinned source records and their PDF/source hashes;
- stable variants for same field, distinct species, full no-pair sector,
  four-branch projection, particle/antiparticle null, barrier, and binding;
- Hamiltonian/action records, initial state, basis/sectors, perturbative
  convention through Dyson orders 0--4, evolution/projection definitions, and
  O1--O6;
- unique row-level amplitude/channel IDs with variant, order, initial branch,
  final sector/state, species assignment, definition, source locus, inclusion
  state, and completeness rule;
- a symbolic exhaustive rule for every `A^(n)_{f;kl}`, `n=0..4`, all four
  initial branches, and the declared full final basis;
- explicit included, excluded, disputed, and unknown-blocked states;
- no JSON `null`; every unknown uses the tagged unknown shape from the design;
- numeric tolerance records distinguish source-derived values from
  implementation controls; and
- output artifact declarations do not claim that amplitude results exist.

### Step 2: Observe RED

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest tests/test_qcr_amplitude_manifest.py -q -p no:cacheprovider
```

Expected: failure because the canonical manifest does not exist.

## Task 2: Populate and review the source-derived manifest

**Owner:** Flywheel worktree

**Files:**

- Create: `configs/qcr/amplitude-closure-manifest-v1.json`
- Modify: `docs/research/2026-07-21-quantum-classical-falsification-lanes.md`
- Modify scratch:
  `C:/dev/scratch/qcr-2026-07-21-02/sources/source-retrieval-receipt.json`

### Step 1: Populate only source-supported declarations

Use exact version/hash/source-locus evidence from:

- Aziz--Howl `2510.19714v3`;
- Gundhi--Infantino--Bassi `2604.19696v2`;
- Vidal--Iyer `2607.03429v1`; and
- Tang et al. `2512.13675v2`.

Represent direct conflicts as variants/disputed rows. Preserve the no-pair
omission of pair terms as an explicit exclusion, not an absent channel. Record
orders 0--4 and all 16 projected transitions per order through the symbolic
completeness rule. Mark the Hamiltonian-sign convention, N>1 off-diagonal
dispute, barrier/distinct-field Hamiltonians, finite-basis generator, and
numeric convergence thresholds as named blocking objects.

Extend the source retrieval receipt with a `declarations` array. Every manifest
Hamiltonian, state, sector, amplitude/channel, exclusion, evolution, and oracle
record must have a stable declaration ID that resolves to an exact source ID,
version, canonical URL, PDF/source hash, section and/or equation label, and
evidence state. The manifest record cites that declaration ID; the test fails on
an unresolved or hash-inconsistent citation.

### Step 2: Replace the blank template pointer

Link the canonical JSON from the research document. Change only the blocker
description: the manifest is populated and source-bounded, while physical
execution remains blocked on its named technical gates.

### Step 3: Observe GREEN and run proportional baseline gates

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest tests/test_qcr_amplitude_manifest.py -q -p no:cacheprovider
python -m pytest tests/test_tasks_physics.py -q -p no:cacheprovider
python -m pytest tests/test_task_curator.py -q -p no:cacheprovider
git diff --check
```

### Step 4: Independent source/manifest review

Require a reviewer to map every manifest declaration to its source locus and
flag unsupported completeness, equation, or tolerance claims. Resolve all P0/P1
findings and rerun Step 3.

## Task 3: Pin Mneme source-byte tamper and descriptor behavior with RED tests

**Owner:** Mneme worktree

**Files:**

- Modify: `tests/test_drift_content.py` (or the existing focused drift file)
- Modify: `tests/test_compose.py`
- Create: `tests/test_crucible_replay.py`

### Step 1: Add the source-byte falsifier

Directly change a stored source turn's `text` through SQLite while leaving its
stored `content_sha256` untouched. Repeat for a cited memory row in an L2/L3
chain, changing its text while leaving its stored hash stale. Assert
`check_memory` returns DRIFT in both cases. These must fail before implementation.

### Step 2: Add descriptor/golden-vector falsifiers

Require every export row to carry exactly:

```json
{
  "schema": "mneme.recheck/1",
  "oracle": "mneme:drift/v1",
  "memory_id": "<id>",
  "grounding_sha256": "<64 lowercase hex>",
  "measurement_contract_sha256": "<64 lowercase hex>"
}
```

Pin canonical JSON bytes/digests with a golden vector. Reject path, command,
argv, cwd, environment, and shell fields.

### Step 3: Add replay-pack falsifiers

Build a synthetic five-row Crucible template. Require an assessment-bound
five-row pack, preserved claim SHA/timestamp/tolerance/method/evidence, and
recomputed deviations. Reject null/missing assessment triples, duplicate or
omitted rows, unsupported schemas/oracles, descriptor swaps, changed target
grounding, and claim/measurement mismatches. Source drift becomes deviation
`1.0`; a missing source becomes `null`.

Add CLI-level RED tests that invoke `main()` for a successful UTF-8 pack write,
refuse overwriting an existing output, and return nonzero with a named stderr
message for assessment/descriptor binding failure. Decode the written bytes as
strict UTF-8 and assert the pack round-trips.

### Step 4: Observe RED

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest tests/test_drift_content.py tests/test_compose.py tests/test_crucible_replay.py -q -p no:cacheprovider
```

Expected: raw source tamper remains MATCH, descriptors are absent, and the
replay producer/CLI do not exist.

## Task 4: Implement Mneme-owned deterministic replay

**Owner:** Mneme worktree

**Files:**

- Modify: `src/mneme/drift.py`
- Modify: `src/mneme/compose.py`
- Create: `src/mneme/replay.py`
- Modify: `src/mneme/memory.py`
- Modify: `src/mneme/cli.py`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `mneme.interop.json`
- Modify tests from Task 3

### Step 1: Recompute current source hashes

For turn rows, recompute the existing `content_hash(role, text)`. For memory
rows, recompute the existing `memory_hash(text, source_ids, criterion)`. A
mismatch against the row's stored hash is DRIFT before comparison to the
extraction snapshot.

### Step 2: Emit portable descriptors

Canonicalize the exact grounding and portable measurement records defined by
the design, hash them with existing `content_hash`, and attach the descriptor to
every measurement. Do not expose source text, state paths, tenant values,
commands, or environment.

### Step 3: Add the pure pack producer and CLI

Implement:

```text
mneme --state DB replay-crucible TEMPLATE.json --out PACK.json
```

The library accepts decoded template data and returns decoded pack data. The CLI
reads/writes UTF-8, refuses overwrite unless the repository's established CLI
policy says otherwise, never imports Crucible, and returns a nonzero named error
for binding failures.

### Step 4: Observe GREEN

Use Task 3's focused command.

### Step 5: Full Mneme regression and interface checks

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest -q -p no:cacheprovider
$env:PYTHONPATH='src'
python -m mneme.cli --help
python -m mneme.cli replay-crucible --help
git diff --check
```

## Task 5: Require assessment binding in Crucible replay packs

**Owner:** Crucible worktree

**Files:**

- Modify: `tests/test_cli_recheck.py`
- Modify: `src/crucible/recheck_cmd.py`
- Modify: `README.md`
- Modify: `USAGE.md`
- Modify: `CHANGELOG.md`

### Step 1: Write and observe the RED security test

Add `test_recheck_pack_rejects_missing_assessment_binding`. Seed a real
assessment, create an otherwise valid pack without top-level `assessment`, and
require CLI exit 1 plus `assessment binding` in stderr.

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest tests/test_cli_recheck.py -q -p no:cacheprovider
```

Expected: the new test fails because `_load_replay_pack` currently skips the
check when the key is absent.

### Step 2: Implement the smallest fail-closed check

When `expected_assessment` is supplied, require an object-valued `assessment`
before comparing `thesis_id`, `assessment_seal`, and `measurement_seal`. Update
successful fixtures to include their real binding. Do not change descriptor
canonicalization or the API-level replayer interface.

### Step 3: GREEN, docs, and full regression

Document that CLI packs are assessment-bound, then run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest tests/test_cli_recheck.py -q -p no:cacheprovider
python -m pytest -q -p no:cacheprovider
$env:PYTHONPATH='src'
python -m crucible.cli status --json
python -m crucible.cli doctor --json
git diff --check
```

## Task 6: Replay the five preserved QCR rows through real Crucible

**Owners:** Mneme produces; Crucible verifies; scratch stores receipts

**Inputs:**

- immutable original:
  `C:/dev/scratch/qcr-2026-07-21-01/run-001/mneme.db`
- claim IDs:
  `da6f0d932c09dd48`, `561936c28ba4e7e9`, `48e0465411177b51`,
  `849a783ce3bd4960`, `18987a65c43aba4a`

### Step 1: Copy and export the five-row state

Run from PowerShell with the exact paths below. Opening the copied DB, never the
run-001 DB, prevents SQLite migration metadata from changing preserved evidence.

```powershell
$run = 'C:\dev\scratch\qcr-2026-07-21-02\replay'
$original = 'C:\dev\scratch\qcr-2026-07-21-01\run-001\mneme.db'
$state = Join-Path $run 'mneme-baseline.db'
$export = Join-Path $run 'mneme-export.json'
$thesis = Join-Path $run 'crucible-thesis.json'
$registry = Join-Path $run 'crucible-registry'
$template = Join-Path $run 'crucible-replay-template.json'
$pack = Join-Path $run 'mneme-replay-pack.json'
$expectedStateSha = '6f6764296b77243c151152306736fc46d441cb7f1f6bdf1a602be6cbfa368845'
New-Item -ItemType Directory -Path $run -Force | Out-Null
if ((Get-FileHash $original -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedStateSha) {
  throw 'run-001 state hash differs from the pinned recovery evidence'
}
Copy-Item -LiteralPath $original -Destination $state
if ((Get-FileHash $state -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedStateSha) {
  throw 'state copy hash mismatch'
}

Set-Location 'C:\dev\worktrees\mneme-qcr-replay-v1'
$env:PYTHONPATH = 'C:\dev\worktrees\mneme-qcr-replay-v1\src'
python -m mneme.cli --state $state to-crucible --session qcr-2026-07-21-01 |
  Out-File -LiteralPath $export -Encoding utf8
if ($LASTEXITCODE -ne 0) { throw 'Mneme export failed' }
$doc = Get-Content -Raw -LiteralPath $export | ConvertFrom-Json
$doc.thesis | ConvertTo-Json -Depth 100 |
  Out-File -LiteralPath $thesis -Encoding utf8
$expectedIds = @('da6f0d932c09dd48','561936c28ba4e7e9','48e0465411177b51',
  '849a783ce3bd4960','18987a65c43aba4a')
if (@($doc.measurements).Count -ne 5 -or
    (Compare-Object $expectedIds @($doc.measurements.claim)).Count -ne 0 -or
    @($doc.measurements | Where-Object { $_.mneme_verdict -ne 'MATCH' -or -not $_.recheck }).Count) {
  throw 'five-row export contract mismatch'
}
```

### Step 2: Register, assess, and write the real replay template

```powershell
Set-Location 'C:\dev\worktrees\crucible-qcr-replay-v1'
$env:PYTHONPATH = 'C:\dev\worktrees\crucible-qcr-replay-v1\src'
python -m crucible.cli register $thesis --registry $registry --json |
  Out-File -LiteralPath (Join-Path $run 'crucible-register.json') -Encoding utf8
if ($LASTEXITCODE -ne 0) { throw 'Crucible register failed' }
python -m crucible.cli assess $thesis --measurements $export --strict --registry $registry --json |
  Out-File -LiteralPath (Join-Path $run 'crucible-assess.json') -Encoding utf8
if ($LASTEXITCODE -ne 0) { throw 'Crucible assess failed' }
python -m crucible.cli recheck $registry --json |
  Out-File -LiteralPath (Join-Path $run 'crucible-recheck-plan.json') -Encoding utf8
if ($LASTEXITCODE -ne 0) { throw 'Crucible recheck plan failed' }
python -m crucible.cli recheck $registry --template $template |
  Out-File -LiteralPath (Join-Path $run 'crucible-template-command.txt') -Encoding utf8
if ($LASTEXITCODE -ne 0) { throw 'Crucible template failed' }
$plan = Get-Content -Raw (Join-Path $run 'crucible-recheck-plan.json') | ConvertFrom-Json
if ($plan.summary.descriptors -ne 5 -or $plan.summary.skipped -ne 0) {
  throw 'Crucible did not expose five replay descriptors'
}
```

### Step 3: Produce and verify the assessment-bound pack

```powershell
Set-Location 'C:\dev\worktrees\mneme-qcr-replay-v1'
$env:PYTHONPATH = 'C:\dev\worktrees\mneme-qcr-replay-v1\src'
python -m mneme.cli --state $state replay-crucible $template --out $pack
if ($LASTEXITCODE -ne 0) { throw 'Mneme replay-pack generation failed' }

Set-Location 'C:\dev\worktrees\crucible-qcr-replay-v1'
$env:PYTHONPATH = 'C:\dev\worktrees\crucible-qcr-replay-v1\src'
python -m crucible.cli recheck $registry --pack $pack --json |
  Out-File -LiteralPath (Join-Path $run 'crucible-replay-result.json') -Encoding utf8
if ($LASTEXITCODE -ne 0) { throw 'five-row Crucible replay failed' }
$result = Get-Content -Raw (Join-Path $run 'crucible-replay-result.json') | ConvertFrom-Json
if (-not $result.ok -or $result.replay.checked -ne 5 -or
    $result.replay.skipped -ne 0 -or $result.replay.missing -ne 0 -or
    $result.replay.mismatched -ne 0 -or $result.replay.failed -ne 0) {
  throw 'five-row replay counters failed'
}
```

### Step 4: Negative integration proof on a second copy

```powershell
$driftState = Join-Path $run 'mneme-drift.db'
$driftPack = Join-Path $run 'mneme-drift-pack.json'
$driftResult = Join-Path $run 'crucible-drift-replay-result.json'
Copy-Item -LiteralPath $state -Destination $driftState
Set-Location 'C:\dev\worktrees\mneme-qcr-replay-v1'
$env:PYTHONPATH = 'C:\dev\worktrees\mneme-qcr-replay-v1\src'
python -c "from mneme import AgentMemory; m=AgentMemory(r'$driftState'); m.store.add_turn('qcr-source-5','qcr-2026-07-21-01','user','The QCR oracle scope changed under replay.'); m.close()"
if ($LASTEXITCODE -ne 0) { throw 'copied-state drift mutation failed' }
python -m mneme.cli --state $driftState replay-crucible $template --out $driftPack
if ($LASTEXITCODE -ne 0) { throw 'drift pack generation failed' }

Set-Location 'C:\dev\worktrees\crucible-qcr-replay-v1'
$env:PYTHONPATH = 'C:\dev\worktrees\crucible-qcr-replay-v1\src'
python -m crucible.cli recheck $registry --pack $driftPack --json |
  Out-File -LiteralPath $driftResult -Encoding utf8
$negativeExit = $LASTEXITCODE
if ($negativeExit -ne 1) { throw "expected Crucible drift exit 1, got $negativeExit" }
$negative = Get-Content -Raw $driftResult | ConvertFrom-Json
if ($negative.ok -or $negative.replay.mismatched -ne 1 -or
    $negative.replay.checked -ne 5) { throw 'negative replay counters failed' }
```

Never open or modify run-001.

Finally hash every run-002 replay artifact with `Get-FileHash -Algorithm
SHA256` into `replay-artifact-hashes.json`.

## Task 7: Exercise or identify the existing bounded 14B endpoint

**Owner:** Flywheel runtime lane; scratch stores receipts

**No repository code is added for this task.** Reuse existing profile, endpoint
gate, proposer, TaskSpec, and oracle APIs.

### Step 1: Immutable preflight before any process start

- hash the 8,988,110,880-byte GGUF and require SHA-256 `613db240...d4064be`;
- capture `nvidia-smi`; require at least 12 GiB free GPU memory;
- prove `127.0.0.1:11439` is unused and require no pre-existing Ollama process;
- parse read-only manifest
  `C:/Users/Zain/.ollama/models/manifests/registry.ollama.ai/library/telos-coder-14b/latest`
  and require its model layer digest/size exactly match the GGUF before startup;
- record `ollama.exe` version; and
- make no firewall, model-store, WSL, or system-service change.

If any preflight gate fails, write an identified-target receipt and do not create
the wave PID.

### Step 2: Run one bounded loopback lifecycle command

Set `OLLAMA_HOST=127.0.0.1:11439`, start `ollama serve` hidden, record its PID,
and enforce the design's 60-second startup, 360-second post-start lifecycle, and
`finally` cleanup bounds. Require listener PID/address equality.

From `C:/dev/worktrees/local-model-qcr-manifest-v1`, execute one PowerShell
`try/catch/finally` block. It must:

1. set `OLLAMA_HOST=127.0.0.1:11439` and start the installed `ollama.exe serve`
   with `-WindowStyle Hidden -PassThru`;
2. require the listener to appear within 60 seconds with exact loopback address
   and the recorded server PID;
3. call `/api/tags` with `-TimeoutSec 10` and require
   `telos-coder-14b`/`telos-coder-14b:latest`;
4. write a one-row scratch artifact using the existing schema
   `harness.model-endpoint-profile/v1`, endpoint
   `http://127.0.0.1:11439`, selector `telos-coder-14b`, and model ref
   `ollama:telos-coder-14b`;
5. run the existing endpoint gate exactly as follows:

```powershell
python scripts/run_model_endpoint_gate.py `
  --profile-artifact C:\dev\scratch\qcr-2026-07-21-02\endpoint\profile.json `
  --models 14B --backends ollama --timeout-seconds 60 --max-tokens 64 --seed 7 `
  --out C:\dev\scratch\qcr-2026-07-21-02\endpoint\endpoint-gate.json `
  --markdown-out C:\dev\scratch\qcr-2026-07-21-02\endpoint\endpoint-gate.md `
  --strict-exit
```

6. run one `python -c` child built in memory (Base64-encoded only to preserve
   argument boundaries; no script file). The child imports the existing
   `OllamaBackend`, `BackendProposer`, `PHYSICS_REGISTRY`, `materialize`,
   `load_task`, and `PytestOracle`; selects only
   `branch_entanglement_invariants`; generates at temperature 0, seed 7, maximum
   512 tokens with backend timeout 180; grades with `PytestOracle(timeout=60)`;
   and prints `qcr.local-task-endpoint-receipt/v1` JSON containing task/model
   identity, prompt/candidate SHA-256, candidate length, oracle PASS/FAIL, return
   code, oracle-output hash, and latency. Start this child with redirected
   stdout/stderr, require exit within 250 seconds, and kill only that child PID
   on timeout; and
7. enforce a `DateTimeOffset.UtcNow.AddSeconds(360)` overall post-start deadline
   before each phase.

The host-command skeleton is normative; fill no unstated process or network
behavior into it:

```powershell
$ErrorActionPreference = 'Stop'
$repo = 'C:\dev\worktrees\local-model-qcr-manifest-v1'
$run = 'C:\dev\scratch\qcr-2026-07-21-02\endpoint'
$ollama = 'C:\Users\Zain\AppData\Local\Programs\Ollama\ollama.exe'
$gguf = 'E:\local-model-run\release\flywheel-local-coder-14b\telos-coder-14b-cpt2020-q4_k_m.gguf'
$alias = 'telos-coder-14b'
$aliasManifest = 'C:\Users\Zain\.ollama\models\manifests\registry.ollama.ai\library\telos-coder-14b\latest'
$expectedSha = '613db240e3efc6730f24042a4602d1f12f1c6b397af1d5a4d74f4e064d4064be'
$expectedBytes = 8988110880
$endpoint = 'http://127.0.0.1:11439'
$python = (Get-Command python).Source
New-Item -ItemType Directory -Path $run -Force | Out-Null
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
function Write-QcrJson([object]$value, [string]$path) {
  [System.IO.File]::WriteAllText(
    $path, (($value | ConvertTo-Json -Depth 20) + "`n"), $utf8NoBom)
}
function New-QcrFailureReceipt(
  [string]$failureClass, [double]$latencyMs, $childExit = $null
) {
  [ordered]@{
    schema='qcr.local-task-endpoint-receipt/v1'; state='UNVERIFIABLE'
    task_id='branch_entanglement_invariants'; model_ref="ollama:$alias"
    endpoint=$endpoint; seed=7; temperature=0.0; max_new_tokens=512
    prompt_sha256=$null; candidate_sha256=$null; candidate_chars=$null
    oracle_passed=$null; oracle_rc=$null; oracle_output_hash=$null
    error_type=$null; failure_class=$failureClass; child_exit=$childExit
    latency_ms=[Math]::Round($latencyMs, 3)
  }
}

$preflight = [ordered]@{
  schema='qcr.endpoint-preflight/v1'; ok=$false; error=$null
  gguf_sha256=$null; gguf_bytes=$null; alias=$alias
  alias_layer_digest=$null; alias_layer_bytes=$null; gpu_free_mib=$null
  existing_ollama_processes=$null; port_11439_listeners=$null
  ollama_version=$null; python_argument_smoke='not_run'
}
try {
  $aliasDoc = Get-Content -Raw -LiteralPath $aliasManifest | ConvertFrom-Json
  $modelLayer = @($aliasDoc.layers | Where-Object {
    $_.mediaType -eq 'application/vnd.ollama.image.model'
  }) | Select-Object -First 1
  $existingOllama = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^ollama(\.exe)?$'
  })
  $portOwners = @(Get-NetTCPConnection -State Listen -LocalPort 11439 -ErrorAction SilentlyContinue)
  $gpuFreeMiB = [int]((& nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits |
    Select-Object -First 1).Trim())
  $actualSha = (Get-FileHash -LiteralPath $gguf -Algorithm SHA256).Hash.ToLowerInvariant()
  $actualBytes = (Get-Item -LiteralPath $gguf).Length
  $preflight.gguf_sha256 = $actualSha
  $preflight.gguf_bytes = $actualBytes
  $preflight.alias_layer_digest = $modelLayer.digest
  $preflight.alias_layer_bytes = $modelLayer.size
  $preflight.gpu_free_mib = $gpuFreeMiB
  $preflight.existing_ollama_processes = $existingOllama.Count
  $preflight.port_11439_listeners = $portOwners.Count
  $preflight.ollama_version = ((& $ollama --version 2>&1) -join "`n")

  $smokeMarker = Join-Path $run ("python-argument-smoke-$([guid]::NewGuid().ToString('N')).txt")
  $env:QCR_SMOKE_PATH = $smokeMarker
  $smokeCode = "__import__('pathlib').Path(__import__('os').environ['QCR_SMOKE_PATH']).write_text('qcr-arg-smoke',encoding='utf-8')"
  $smokeEncoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($smokeCode))
  $smokeLauncher = "exec(__import__('base64').b64decode('$smokeEncoded'))"
  $smoke = Start-Process -FilePath $python -WindowStyle Hidden -PassThru -ArgumentList @('-c',$smokeLauncher)
  if (-not $smoke.WaitForExit(5000)) {
    try { Stop-Process -Id $smoke.Id -Force -ErrorAction Stop } catch {}
    throw 'python argument smoke timed out'
  }
  $smoke.Refresh()
  if ($smoke.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $smokeMarker) -or
      (Get-Content -Raw -LiteralPath $smokeMarker).Trim() -ne 'qcr-arg-smoke') {
    throw 'python argument smoke failed'
  }
  $preflight.python_argument_smoke = 'pass'
  $preflight.ok = ($actualSha -eq $expectedSha -and $actualBytes -eq $expectedBytes -and
    $modelLayer.digest -eq "sha256:$expectedSha" -and
    [int64]$modelLayer.size -eq $expectedBytes -and $gpuFreeMiB -ge 12288 -and
    $existingOllama.Count -eq 0 -and $portOwners.Count -eq 0)
  if (-not $preflight.ok) { $preflight.error = 'one or more immutable preflight predicates failed' }
} catch {
  $preflight.error = $_.Exception.Message
  $preflight.ok = $false
} finally {
  Write-QcrJson $preflight (Join-Path $run 'preflight.json')
}
if (-not $preflight.ok) { exit 2 }

Set-Location $repo
$env:OLLAMA_HOST = '127.0.0.1:11439'
$env:QCR_ENDPOINT = $endpoint
$env:QCR_ALIAS = $alias
$env:QCR_TASK_ROOT = Join-Path $run 'task-work'
$server = $null
$runError = $null
$startedAt = [DateTimeOffset]::UtcNow
$deadline = $startedAt.AddSeconds(360)
$phases = [ordered]@{
  startup='not_started'; bind='not_started'; health='not_started'
  endpoint_gate='not_started'; qcr_task='not_started'
}
$resources = [ordered]@{gpu_free_mib_before=$preflight.gpu_free_mib; gpu_free_mib_after=$null}
$cleanup = [ordered]@{
  model_stop='not_started'; normal_stop='not_started'; forced=$false
  server_exited=$false; port_closed=$false; errors=@()
}
function Assert-QcrDeadline([string]$phase) {
  if ([DateTimeOffset]::UtcNow -ge $deadline) { throw "QCR endpoint lifecycle deadline before $phase" }
}
try {
  $server = Start-Process -FilePath $ollama -ArgumentList @('serve') -PassThru -WindowStyle Hidden
  $phases.startup = 'process_started'
  $startupDeadline = [DateTimeOffset]::UtcNow.AddSeconds(60)
  $listeners = @()
  while ([DateTimeOffset]::UtcNow -lt $startupDeadline) {
    Start-Sleep -Milliseconds 250
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort 11439 -ErrorAction SilentlyContinue)
    if ($listeners.Count -eq 1 -and $listeners[0].LocalAddress -eq '127.0.0.1' -and
        $listeners[0].OwningProcess -eq $server.Id) { break }
  }
  if ($listeners.Count -ne 1 -or $listeners[0].LocalAddress -ne '127.0.0.1' -or
      $listeners[0].OwningProcess -ne $server.Id) {
    $phases.startup='timeout_or_ambiguous_bind'
    throw 'port 11439 did not become exclusively loopback-and-wave-PID-owned within 60s'
  }
  $phases.startup = 'ready'
  $phases.bind = "127.0.0.1:11439 pid=$($server.Id)"
  Assert-QcrDeadline 'tags'
  $tags = Invoke-RestMethod -Uri "$endpoint/api/tags" -Method Get -TimeoutSec 10
  $tagNames = @($tags.models | ForEach-Object { $_.name })
  if ($tagNames -notcontains $alias -and $tagNames -notcontains "$alias`:latest") {
    $phases.health='alias_missing'; throw 'verified alias absent from /api/tags'
  }
  $phases.health = 'pass'

  $profile = [ordered]@{
    schema='harness.model-endpoint-profile/v1'; profile_id='qcr-ollama-14b'
    model='14B'; model_key='flywheel-local-coder-14b'; backend='ollama'
    provider_role='ollama_local'; endpoint_url=$endpoint; selectors=@($alias)
    model_ref="ollama:$alias"; source='verified-local-ollama-manifest'
  }
  $profilePath = Join-Path $run 'profile.json'
  Write-QcrJson $profile $profilePath

  Assert-QcrDeadline 'endpoint gate'
  $gate = Start-Process -FilePath $python -WindowStyle Hidden -PassThru -ArgumentList @(
    'scripts/run_model_endpoint_gate.py','--profile-artifact',$profilePath,
    '--models','14B','--backends','ollama','--timeout-seconds','60',
    '--max-tokens','64','--seed','7','--out',(Join-Path $run 'endpoint-gate.json'),
    '--markdown-out',(Join-Path $run 'endpoint-gate.md'),'--strict-exit')
  $gateWaitMs = [int][Math]::Min(90000, [Math]::Max(1, ($deadline-[DateTimeOffset]::UtcNow).TotalMilliseconds))
  if (-not $gate.WaitForExit($gateWaitMs)) {
    Stop-Process -Id $gate.Id -Force; $phases.endpoint_gate='timeout'; throw 'endpoint gate timed out'
  }
  if ($gate.ExitCode -ne 0) { $phases.endpoint_gate="exit:$($gate.ExitCode)"; throw "endpoint gate exit $($gate.ExitCode)" }
  $phases.endpoint_gate = 'pass'

  Assert-QcrDeadline 'QCR TaskSpec'
  $qcrCode = @'
import hashlib, json, os, time
import traceback
from pathlib import Path
started = time.perf_counter()
receipt_path = Path(os.environ["QCR_RECEIPT_PATH"])
stderr_path = Path(os.environ["QCR_STDERR_PATH"])
receipt = {
    "schema": "qcr.local-task-endpoint-receipt/v1",
    "state": "UNVERIFIABLE",
    "task_id": "branch_entanglement_invariants",
    "model_ref": f"ollama:{os.environ.get('QCR_ALIAS', '')}",
    "endpoint": os.environ.get("QCR_ENDPOINT", ""),
    "seed": 7,
    "temperature": 0.0,
    "max_new_tokens": 512,
    "prompt_sha256": "",
    "candidate_sha256": "",
    "candidate_chars": 0,
    "oracle_passed": None,
    "oracle_rc": None,
    "oracle_output_hash": "",
    "error_type": "",
}
exit_code = 2
try:
    from harness.endpoint_registry import BackendProposer
    from harness.local_agent import OllamaBackend
    from harness.oracle import PytestOracle
    from harness.task import load_task
    from harness.tasks_lib import materialize
    from harness.tasks_physics import PHYSICS_REGISTRY
    spec = next(s for s in PHYSICS_REGISTRY if s.task_id == receipt["task_id"])
    receipt["prompt_sha256"] = hashlib.sha256(spec.prompt.encode()).hexdigest()
    backend = OllamaBackend(base_url=os.environ["QCR_ENDPOINT"], model=os.environ["QCR_ALIAS"], timeout=180)
    proposer = BackendProposer(backend, model_ref=receipt["model_ref"], extract=True)
    candidate = proposer.generate(spec.prompt, seed=7, temperature=0.0, max_new_tokens=512).text
    receipt["candidate_sha256"] = hashlib.sha256(candidate.encode()).hexdigest()
    receipt["candidate_chars"] = len(candidate)
    task_dir = materialize(spec, Path(os.environ["QCR_TASK_ROOT"]))
    task = load_task(task_dir, workdir=task_dir / "wd")
    verdict = PytestOracle(timeout=60).verify(candidate, task)
    receipt.update(state="PASS" if verdict.passed else "FAIL", oracle_passed=verdict.passed,
                   oracle_rc=verdict.rc, oracle_output_hash=verdict.output_hash)
    exit_code = 0 if verdict.passed else 1
except Exception as exc:
    receipt.update(state="UNVERIFIABLE", error_type=type(exc).__name__)
    stderr_path.write_text(traceback.format_exc(), encoding="utf-8")
finally:
    receipt["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
    receipt_path.write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
raise SystemExit(exit_code)
'@
  $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($qcrCode))
  $launcher = "exec(__import__('base64').b64decode('$encoded'))"
  $qcrOut = Join-Path $run 'qcr-task-receipt.json'
  $qcrErr = Join-Path $run 'qcr-task-stderr.txt'
  $env:QCR_RECEIPT_PATH = $qcrOut
  $env:QCR_STDERR_PATH = $qcrErr
  $qcrStarted = [DateTimeOffset]::UtcNow
  $qcr = Start-Process -FilePath $python -WindowStyle Hidden -PassThru -ArgumentList @('-c',$launcher)
  $qcrWaitMs = [int][Math]::Min(250000, [Math]::Max(1, ($deadline-[DateTimeOffset]::UtcNow).TotalMilliseconds))
  if (-not $qcr.WaitForExit($qcrWaitMs)) {
    try { Stop-Process -Id $qcr.Id -Force -ErrorAction Stop } catch {}
    try { [void]$qcr.WaitForExit(5000) } catch {}
    $elapsed = ([DateTimeOffset]::UtcNow - $qcrStarted).TotalMilliseconds
    Write-QcrJson (New-QcrFailureReceipt 'parent_timeout' $elapsed) $qcrOut
    $phases.qcr_task = 'UNVERIFIABLE:parent_timeout'
  } else {
    $qcr.Refresh()
    if (-not (Test-Path $qcrOut) -or (Get-Item $qcrOut).Length -eq 0) {
      $elapsed = ([DateTimeOffset]::UtcNow - $qcrStarted).TotalMilliseconds
      Write-QcrJson (New-QcrFailureReceipt 'missing_child_receipt' $elapsed $qcr.ExitCode) $qcrOut
    }
    try {
      $qcrReceipt = Get-Content -Raw -LiteralPath $qcrOut | ConvertFrom-Json
    } catch {
      $elapsed = ([DateTimeOffset]::UtcNow - $qcrStarted).TotalMilliseconds
      Write-QcrJson (New-QcrFailureReceipt 'invalid_child_receipt' $elapsed $qcr.ExitCode) $qcrOut
      $qcrReceipt = Get-Content -Raw -LiteralPath $qcrOut | ConvertFrom-Json
    }
    $phases.qcr_task = $qcrReceipt.state
  }
} catch {
  $runError = $_.Exception.Message
} finally {
  try {
    if ($server) {
      $stopClient = Start-Process -FilePath $ollama -WindowStyle Hidden -PassThru -ArgumentList @('stop',$alias)
      if ($stopClient.WaitForExit(15000)) { $cleanup.model_stop = "exit:$($stopClient.ExitCode)" }
      else { Stop-Process -Id $stopClient.Id -Force -ErrorAction SilentlyContinue; $cleanup.model_stop = 'timeout-killed' }
    }
  } catch { $cleanup.errors += "model_stop:$($_.Exception.GetType().Name)" }
  try {
    if ($server) {
      $server.Refresh()
      if (-not $server.HasExited) {
        try { Stop-Process -Id $server.Id -ErrorAction Stop } catch {
          $cleanup.errors += "normal_stop:$($_.Exception.GetType().Name)"
        }
        if ($server.WaitForExit(15000)) { $cleanup.normal_stop = 'exited' }
        else {
          try { Stop-Process -Id $server.Id -Force -ErrorAction Stop; $cleanup.forced = $true }
          catch { $cleanup.errors += "forced_stop:$($_.Exception.GetType().Name)" }
          if (-not $server.WaitForExit(5000)) { $cleanup.errors += 'forced_stop:pid_still_running' }
        }
      } else { $cleanup.normal_stop = 'already_exited' }
      $server.Refresh()
      $cleanup.server_exited = $server.HasExited
    }
  } catch { $cleanup.errors += "server_cleanup:$($_.Exception.GetType().Name)" }
  try {
    $closeDeadline = [DateTimeOffset]::UtcNow.AddSeconds(10)
    do {
      $stillOpen = @(Get-NetTCPConnection -State Listen -LocalPort 11439 -ErrorAction SilentlyContinue).Count -gt 0
      if ($stillOpen) { Start-Sleep -Milliseconds 250 }
    } while ($stillOpen -and [DateTimeOffset]::UtcNow -lt $closeDeadline)
    $cleanup.port_closed = -not $stillOpen
  } catch { $cleanup.errors += "port_check:$($_.Exception.GetType().Name)" }
  try {
    $resources.gpu_free_mib_after = [int]((& nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits |
      Select-Object -First 1).Trim())
  } catch { $cleanup.errors += "resource_after:$($_.Exception.GetType().Name)" }
  $serverPid = if ($server) { $server.Id } else { $null }
  $lifecycle = [ordered]@{
    schema='qcr.endpoint-lifecycle/v1'; started_at=$startedAt.ToString('o')
    server_pid=$serverPid; bind_address='127.0.0.1:11439'; endpoint=$endpoint; alias=$alias
    error=$runError; phases=$phases; resources=$resources; cleanup=$cleanup
    completed_at=[DateTimeOffset]::UtcNow.ToString('o')
  }
  try { Write-QcrJson $lifecycle (Join-Path $run 'endpoint-lifecycle.json') }
  catch { Write-Error "endpoint lifecycle receipt write failed: $($_.Exception.Message)" }
}
if ($runError -or -not $cleanup.server_exited -or -not $cleanup.port_closed -or
    $phases.endpoint_gate -ne 'pass' -or $phases.qcr_task -notin @('PASS','FAIL')) { exit 1 }
exit 0
```

The `finally` block always executes. Bound the model stop to 15 seconds, normal
server-PID termination to 15 seconds,
PID-only forced termination to 5 seconds, and port-closure proof to 10 seconds.
Record any escalation. Never stop a pre-existing process or remove an alias.

Write `endpoint-lifecycle.json` from `finally`, including wave PID, bind address,
startup/health/generation/oracle states, errors, cleanup escalation, and final
port-closed state.

## Task 8: Review, regress, commit, publish, and recheck CI

### Step 1: Independent reviews

Review Flywheel source accuracy/manifest completeness and Mneme security,
correctness, public API, and tests. Resolve all blocking findings.

### Step 2: Rerun exact affected gates

- Flywheel: manifest test, physics task test, curator test, `git diff --check`.
- Mneme: focused replay/drift/compose tests, full 111+ test suite,
  `git diff --check`.
- Crucible: focused replay slice, full 350+ test suite, status/doctor, and
  `git diff --check`.
- Cross-repository: five-row successful replay and one negative drift replay.
- Runtime: endpoint lifecycle receipt with terminal cleanup state.

### Step 3: Commit and publish isolated branches

- Flywheel branch `feat/qcr-manifest-v1`.
- Mneme branch `feat/qcr-replay-v1`.
- Crucible branch `test/qcr-mneme-replay-v1`, now containing the proven
  assessment-binding hardening.

Push, open PRs, recheck Actions, and merge only green safe work. If an external
policy blocks publication, preserve the exact command/output and leave the
verified commits intact.

### Step 4: Durable checkpoint

Update the run-002 receipt with source hashes, commits, exact commands/results,
Crucible seals/replay counts, endpoint identity/lifecycle state, tests, PR/run
links, remaining physics blockers, and the next bounded actions. Keep verified,
inferred, unknown, model-bound, and disputed states separate.
