# Benchmark Methodology for the Outside Observer

Date: 2026-07-09
Subject: `Flywheel-Local-Coder-14B` (`telos-coder-14b-cpt2020-q4_k_m.gguf`)
Status: easy-set results final; first hard-set run landed (Section 6.1, with
confidence intervals); the 100-task curated lane is the remaining instrument

This document is written for a skeptical outside observer. It describes
what was measured, how the task set was built, what the arms and metrics
mean, what controls hold the runs steady, and exactly which commands
reproduce everything on your own machine. Nothing here asks to be taken on
faith; the point of the design is that you can rerun it end to end and
compare artifacts.

## 1. What is under test

Two things, and it matters to keep them separate.

The model: a local 14B coding model, base `Qwen2.5-Coder-14B-Instruct`
(Apache-2.0) merged with QLoRA continued-pretraining adapter
`checkpoint-2020` (train_loss 0.035), quantized Q4_K_M, shipped as a single
GGUF of 8,988,110,880 bytes with sha256
`613db240e3efc6730f24042a4602d1f12f1c6b397af1d5a4d74f4e064d4064be`.

The harness: a verification loop in which the model proposes code, an
oracle (a hidden pytest suite) is the only thing that accepts, and every
accepted answer carries a proof envelope a third party can re-run. The
harness is the product under study; the model is deliberately the
replaceable part. The benchmark question is therefore not "how smart is
this model" but "what does the propose-verify-witness loop measurably do,
and can every number it reports be re-derived by someone else."

No capability uplift is claimed in this release. An earlier internal
observation of a +10% lift did not reproduce and has been retired. This
document reports what the current instruments actually showed.

## 2. Artifact identity and provenance

Recorded in `tasks/research/gguf_ship_manifest_checkpoint2020.json`
(schema `telos.model-artifact/v1`), each layer re-derivable by whoever
holds that layer's artifact:

| Layer | Value |
| --- | --- |
| corpus_content_hash (17,997 files) | `68345cdc6667f20d1678ac0a9139edc170348dfdebb9ae6045cde3d204f4fe62` |
| pack_shards_hash | `018798dfce7d4c86f5a6ea502a383553220f2e76facfe76acbe52b1c278ae543` |
| checkpoint_adapter_sha256 | `4de07c6ea342d1cc200d4a6e2b28a63f6ee37f34c5c0926c35d8c7db74d38d0f` |
| GGUF sha256 | `613db240e3efc6730f24042a4602d1f12f1c6b397af1d5a4d74f4e064d4064be` |
| adapter-as-GGUF sha256 | `c89091709d7f385226000091dca976b7ce68086255e78af96599d06b6b52f547` |

Dataset receipt: `tasks/research/dataset_receipt_checkpoint2020.json`.
Determinism smoke on the shipped artifact: `llama-completion` at
temperature 0, seed 7, 48 tokens, byte-identical across reruns (verdict
MATCH, output sha256
`970af540244384407918aa3b0172b403c24d17800e3c514c3c19937d88c7e636`).

## 3. Task set construction

### 3.1 The easy held-out set (run to date)

Eight coding tasks defined in `harness/tasks_lib.py` (`REGISTRY`), held out
from training. Each task carries a prompt, a reference solution, and a
hidden pytest suite the model never sees. The discipline for every task:
the reference solution must pass its own hidden tests, or the benchmark is
considered broken.

### 3.2 The hard set (in flight) and leak-gated admission

The easy set saturates (Section 6), so a harder set is being assembled
under mechanized admission gates in `harness/task_curator.py`. Hand-curating
a large set invites quality decay: task 87 gets vacuous tests, task 92
leaks its solution into the prompt, and the eval ends up measuring
nothing. Admission is therefore gated, and a candidate task enters the
registry only if every gate passes:

| Gate | What it requires |
| --- | --- |
| `reference_passes` | the reference solution passes its own hidden tests |
| `oracle_can_fail` | a derived return-None stub FAILS the hidden tests; vacuous tests are rejected |
| `deterministic` | the reference passes twice in fresh working directories; flaky tests are rejected |
| `no_solution_leak` | no substantive solution line appears in the prompt |
| `edge_coverage` | at least 4 hidden test functions, edge-heavy by design |
| `dedup` | task id, normalized solution body, and a behavioral-duplicate probe are all new |

The gates fail closed: a solution the stub-deriver cannot parse is
rejected outright. Admitted tasks persist as JSONL data where every row
carries a content hash; loading re-checks each hash and raises loudly on
any mismatch, so a tampered task cannot silently enter an eval.

A 38-task hard-set run against this release is in flight. It is the
discriminating instrument for arm-vs-arm comparisons. Its results tables
will be appended to this document when the run lands. Pending.

## 4. The four arms

Defined in `harness/eval.py`. All arms run the same tasks against the same
model and the same oracles; only the search configuration differs.

| Arm | Candidates | Description |
| --- | --- | --- |
| `single_shot` | 1 | one proposal at temperature 0.0, one oracle call; the frontier baseline analog |
| `verified_inference` | 4 | the full harness: diversified best-of-4 across a declared temperature ladder, first oracle PASS accepted |
| `flat_n` | 4 | best-of-4 without escalation; isolates what plain resampling buys |
| `no_search` | 1 | single proposal through the oracle and witness path; isolates the verification machinery itself |

The multi-candidate arms sample at the declared ladder
`[0.0, 0.4, 0.8, 1.1]` (`harness/search.py`, `DEFAULT_TEMPS`) with seeds
derived as `task.seed + i`. When no candidate passes and the candidates
are highly correlated with one another (max pairwise Jaccard at or above
0.85), the search returns UNVERIFIABLE rather than a confident FAIL,
because four copies of the same wrong answer are not four opinions.

## 5. Metrics

Three metrics, each declared inside the scorecard itself (`METRICS` in
`harness/eval.py`) with explicit range and good-direction, so a scorecard
reads without tribal knowledge:

| Metric | Range | Good | Meaning |
| --- | --- | --- | --- |
| `pass_rate` | 0 to 1 | higher | fraction of tasks where the arm produced an oracle-passing answer |
| `avg_oracle_calls` | 0 and up | lower | verification budget spent per task |
| `receipt_reproducibility` | 0 to 1 | higher | fraction of runs whose receipts re-checked |

Comparisons between a fresh run and a prior one always go through a pinned
scorecard (`--pinned`), never a re-narrated memory of the baseline.

## 6. Results to date, and saturation honesty

The recorded run for this release: M7 easy held-out set, 4 arms by 8
tasks, model served through Ollama
(`model_ref: ollama:flywheel-local-coder-14b`). Scorecard artifact:
`artifacts/flywheel-local-coder-14b-benchmark-m7-scorecard.json`.

| Arm | n_tasks | pass_rate | avg_oracle_calls | avg_candidates | receipt_reproducibility |
| --- | --- | --- | --- | --- | --- |
| single_shot | 8 | 1.0 | 1.0 | 1.0 | 1.0 |
| verified_inference | 8 | 1.0 | 4.0 | 4.0 | 1.0 |
| flat_n | 8 | 1.0 | 4.0 | 4.0 | 1.0 |
| no_search | 8 | 1.0 | 1.0 | 1.0 | 1.0 |

Whole-run verdict: MATCH, defined narrowly as `verified_inference`
pass_rate at or above `single_shot` pass_rate on this set. It carries no
claim beyond that inequality.

Read this table plainly. Every arm passed 8 of 8 and every receipt
re-checked. That establishes two things worth having: the released
artifact generates correct code on this held-out set, and the receipt
pipeline reproduces at 100% end to end. It establishes nothing about
differences between arms, because a set where every arm scores 1.0 cannot
discriminate. The easy set is saturated, exactly as its own documentation
predicts, and we say so rather than dressing the ceiling up as a result.

Consequences we hold ourselves to:

- No uplift claim is made from this data. There is no arm-vs-arm signal in
  a saturated set.
- The retired +10% claim stays retired. It did not reproduce, so it does
  not appear in release materials.
- The 38-task hard set is the discriminating instrument. Its run is in
  flight, and its results will be appended here as tables in the same
  format, whatever they show. MATCH and DRIFT are both publishable
  outcomes; the framework exists to report the data, not to flatter the
  harness.

### 6.1 Hard-set results (landed 2026-07-09) with confidence intervals

The first hard-set run used the 10-task held-out hard registry (the larger
curated lane is still being assembled; see Section 3.2). Same artifact, same
arms, same controls.

| Arm | Passed | Wilson 95% CI |
|---|---|---|
| single_shot | 8/10 (80%) | [0.490, 0.943] |
| verified_inference | 9/10 (90%) | [0.596, 0.982] |
| flat_n | 9/10 (90%) | [0.596, 0.982] |
| no_search | 8/10 (80%) | [0.490, 0.943] |

Receipt reproducibility was 100% in every arm. Verdict: MATCH
(verified_inference is not worse than single_shot).

The difference that matters, stated with an interval instead of an
adjective: verified_inference minus single_shot is +0.100 with a 95%
interval of [-0.236, +0.420] (Newcombe score interval; the run predates
per-task vectors in the scorecard schema, so this is the unpaired
approximation, which is typically conservative). The interval includes
zero. On top of that, flat_n (best-of-4 with no verification escalation)
ties verified_inference exactly, so even the point difference is explained
by sampling more candidates, not by verification. No uplift is claimed.

Intervals were produced by `scripts/run_benchmark_ci.py` (stdlib, Wilson
and Newcombe score intervals, paired bootstrap when per-task vectors
exist). Full output: `artifacts/flywheel-local-coder-14b-benchmark-ci.json`
and `.md`. Scorecards written after 2026-07-09 carry per-task outcome
vectors, so future runs get the paired bootstrap automatically.

For calibration: at this effect size, excluding zero would need roughly
n around 100, which is exactly why the curated hard lane targets 100
tasks before any efficiency claim is put in front of an outside observer.

## 7. Determinism controls

- Single-candidate arms generate at temperature 0.0 with the task's fixed
  seed.
- Multi-candidate arms use the declared temperature ladder
  `[0.0, 0.4, 0.8, 1.1]` and derived seeds `task.seed + i`; the diversity
  is itself a recorded configuration, not an accident.
- The oracle hash is computed over canonical test outcomes, never raw
  stdout, so pytest's timing lines cannot break the receipt chain
  (`harness/oracle.py`).
- Bytecode caches are cleared and `PYTHONDONTWRITEBYTECODE` is set for
  every oracle run, so stale `.pyc` files cannot leak state between runs.
- At the artifact level, the shipped GGUF reproduced byte-identical output
  at temperature 0, seed 7 (Section 2).

## 8. Threat model: what a receipt proves, and what it does not

A proof envelope (`harness/envelope.py`) records the task id, the exact
candidate code, the oracle command, a canonical hash of the oracle
outcome, the verdict, the model reference, the seed, and the prompt hash.
A witness (`harness/witness.py`) re-runs the oracle command against the
candidate and recomputes the hash: MATCH if reproduced, DRIFT if the
envelope and reality diverge, UNVERIFIABLE if the oracle cannot be re-run.

What this proves:

- This exact candidate, judged by this exact command, produced this exact
  outcome, and an independent party can reproduce that judgment.
- The scorecard can be reconstructed from its artifacts without re-running
  the eval, and any fresh run can be compared against a pinned prior.
- The artifact you benchmarked is the artifact that was shipped, via the
  sha256 chain in Section 2.

What this does not prove:

- Correctness beyond the hidden tests. The oracle is the criterion; a
  passing answer is correct relative to those tests, not in some absolute
  sense. This is why the admission gates demand edge-heavy suites that a
  stub cannot pass.
- General capability. Eight tasks are eight tasks. Receipts make the
  claim precise; they do not make it larger.
- Performance on your workload. The honest path to that claim is running
  the harness on your own tasks, which the reproduction section below
  makes cheap.
- Anything about safety, alignment, or the quality of the training corpus.
  The corpus hash proves identity, not virtue.
- Uplift. Receipts certify what happened in a run; they cannot conjure a
  difference a saturated set never measured.

And one structural honesty: a verifier chosen by the same people it
verifies could in principle be vacuous. The design answer is Section 9,
and the practical answer is that every piece is local and open to you, so
the strongest audit available is the one you run yourself.

## 9. The verifier must be able to fail

A verifier that cannot fail verifies nothing, so failure paths are built
in and exercised:

- The whole-run comparison can return DRIFT (`compare()` in
  `harness/eval.py` reports `single_shot > verified_inference` when that
  is what the data shows). The framework's own documentation commits to
  publishing either outcome.
- Every admitted task must fail on a derived return-None stub
  (`oracle_can_fail` in `harness/task_curator.py`). A task whose tests a
  stub can pass is rejected before it can inflate a pass rate.
- The witness returns DRIFT on any divergence between envelope and re-run,
  and UNVERIFIABLE when it cannot re-run at all; it does not default to
  MATCH.
- Registry rows carry content hashes; a tampered row raises an error at
  load time rather than being silently evaluated.
- The correlated-failure gate refuses to convert wrong-attractor agreement
  into a confident verdict.

If you want to watch a failure happen, break something on purpose: edit
one character of a candidate inside a stored envelope and re-witness it.
The verdict flips to DRIFT. A pipeline that cannot be made to say no has
no business saying yes.

## 10. Full reproduction, end to end

Requirements: Windows PowerShell (or any shell), Ollama, Python 3.11+,
`pytest`, the `local-model` repository, and the release folder (here,
`E:\local-model-run\release\flywheel-local-coder-14b`).

1. Verify the artifact is the artifact:

```powershell
Get-FileHash "E:\local-model-run\release\flywheel-local-coder-14b\telos-coder-14b-cpt2020-q4_k_m.gguf" -Algorithm SHA256
```

Expect `613db240e3efc6730f24042a4602d1f12f1c6b397af1d5a4d74f4e064d4064be`
(case-insensitive) and a file length of exactly 8,988,110,880 bytes.

Linux / WSL:

```bash
sha256sum telos-coder-14b-cpt2020-q4_k_m.gguf
```

2. Serve the model locally:

```powershell
ollama create flywheel-local-coder-14b -f "E:\local-model-run\release\flywheel-local-coder-14b\Modelfile"
ollama run flywheel-local-coder-14b "say hello"
```

3. Confirm the endpoint the harness will use (backend `ollama` at
`http://127.0.0.1:11434`):

```powershell
Invoke-RestMethod http://127.0.0.1:11434/api/tags | Select-Object -ExpandProperty models | Select-Object name
```

4. Run the easy-set eval, all four arms:

```powershell
Set-Location C:\dev\local-model
python scripts/run_m7_eval.py --local-primary ollama --local-model flywheel-local-coder-14b --out artifacts\m7_scorecard_repro.json
```

Expected console shape, matching Section 6:

```
=== M7 eval (harness lift on the held-out set) ===
  single_shot: pass=100% (8/8) avg_oracle=1.0 receipts=100%
  verified_inference: pass=100% (8/8) avg_oracle=4.0 receipts=100%
  flat_n: pass=100% (8/8) avg_oracle=4.0 receipts=100%
  no_search: pass=100% (8/8) avg_oracle=1.0 receipts=100%
  verdict (verified_inference >= single_shot): MATCH
```

5. Compare your run against the shipped scorecard, pinned:

```powershell
python scripts/run_m7_eval.py --local-primary ollama --local-model flywheel-local-coder-14b --pinned artifacts\flywheel-local-coder-14b-benchmark-m7-scorecard.json --out artifacts\m7_scorecard_repro2.json
```

The delta report at the end compares your `verified_inference` arm against
the pinned baseline and prints IMPROVED, REGRESSED, or FLAT.

6. The hard tier runs with the same command plus `--hard`. The curated
38-task run against this release is in flight; when its scorecard lands,
this document gains a results section in the same table format, and the
same reproduction command applies.

## 11. Artifact index

- Release root: `E:\local-model-run\release\flywheel-local-coder-14b`
  (GGUF, Modelfile, LICENSE, release docs, `checksums.sha256`)
- Ship manifest: `tasks/research/gguf_ship_manifest_checkpoint2020.json`
- Dataset receipt: `tasks/research/dataset_receipt_checkpoint2020.json`
- Shipped scorecard:
  `artifacts/flywheel-local-coder-14b-benchmark-m7-scorecard.json`
- Eval framework: `harness/eval.py`, `harness/search.py`,
  `harness/oracle.py`, `harness/envelope.py`, `harness/witness.py`
- Task sets and admission: `harness/tasks_lib.py`, `harness/tasks_hard.py`,
  `harness/task_curator.py`
- Runner: `scripts/run_m7_eval.py`
- Newcomer walkthrough: `project-docs/releases/14B/WALKTHROUGH.md`
