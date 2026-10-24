# Self-improving harness: Flywheel against Harness-squared

Register: `flavored`. Internal document. Last updated 2026-10-21 (v2).

Author direction, 2026-10-21: "Flywheel should be the better self improving
harness". This document records the study of Harness-squared, the gap table,
the design and its targets, the MVP that shipped, the head-to-head result, and
the open gaps.

## 1. What Harness-squared is

Source: arXiv 2610.14224 (submitted 2026-10-09, Northwestern and Google Cloud
AI Research), repository `google-research/harness2` at
`1cfe254e8d25b15f37048c3730134686abe60335` (Apache-2.0, read and run here).

- **Method.** Two levels of recursion with model weights fixed. Task level: a
  Propose-Probe-Compose step proposes harness edits (INV general and DOM
  domain-specific), probes each edit by running it on the same task, and
  composes a refined harness from the behavioural contrast between executions.
  No ground-truth grader is used. Harnessing level: after the selector adopts a
  final, a reflector writes an "evidence-supported lesson" and the adopted tree
  into a per-domain Library that later tasks' editors read.
- **Editable surface.** Eight components: system prompt, guardrails, memory,
  tool guidance, subagents, skills, scripts, plugins.
- **Budgets.** Both modes spend 4k rollouts and 3k improvement stages per task
  (`harness2/core/recursion.py` docstring; checked by their test
  `test_recursion_budget_and_resume`). Parallel: k reference rollouts, k INV
  and k DOM probes, k compositions. Sequential: k nested steps.
- **Selection.** An LLM selector picks one of the k anonymized finals. The pool
  is finals only (`selection_pool`); the base harness is never a candidate, so
  every task ships a refined harness.
- **Executors.** OpenCode (default, run from a pinned source checkout through
  Bun) and Codex (`--substrate cx`, Responses API, bridged to Vertex through a
  local LiteLLM server). Improver: Claude Opus 4.8 under OpenCode in the paper.
- **Benchmarks.** WorkBuddy-Bench (100 test tasks; Gemini 3.5 Flash judge plus
  deterministic checks), JobBench (34 test tasks; Claude Opus 4.8 judge), LAB
  (100 test tasks; Claude Sonnet 4.6 judge). Means of three shuffled streams,
  standard deviations, no intervals or significance tests.
- **Reported gains (authors).** One step (k=1): up to +11.5 WorkBuddy-Bench
  (GLM-5, OpenCode, 64.2 to 75.7), +4.5 JobBench (Gemini, OpenCode), +11.8 pp
  LAB partial (GLM-5, OpenCode). Parallel k=5 adds 2.6 to 6.7 points more.
- **Failure cases the authors report.** Selection preferring a weaker candidate
  (a WB-code output scored 55 chosen over one scored 95); an incorrect premise
  propagating across candidates (2 to 11 point losses); outcome noise and
  missing judge verdicts. Harness Scaling falls below base in 7 of 12 pairs;
  Meta-Harness beats Harness-squared on LAB partial for Gemini under Codex. In a
  validation run a Codex rollout downloaded its JobBench rubric unprompted; the
  release does not restrict network access. Failed evaluations stay unscored
  rather than counting as zero.
- **What their evidence does not cover.** The grader-free loop is validated
  only on graded benchmarks after the fact; nothing in the loop checks that a
  carried lesson helps a held-out task. Best-of-k is defined but its results
  are not in the main tables (moderate confidence: read from the HTML version).

## 2. Gap table

"Before" is `origin/main` at `1d262594`. "Now" is the MVP (#422) plus v2
(incumbent in the pool, line-level attribution). Ahead, behind and absent are
against Harness-squared as released.

| Feature | Harness-squared | Flywheel before | Flywheel now | Evidence |
|---|---|---|---|---|
| Task-level harness editing | 8 components, model editor | absent; `evolve.py` ranks improvement candidates, edits nothing | parity on mechanics, 9 components | `self_improve_tree.py`, `self_improve_loop.py` |
| Propose-Probe-Compose without a grader | yes | absent | parity; grader keys stripped and refused | `test_grader_keys_never_reach_editor_or_selector` |
| Parallel and sequential budgets, 4k/3k | yes | absent (`mcts.py` searches answers, not harnesses) | parity | `test_budget_matches_harness_squared` |
| Model-backed editor | OpenCode or Claude CLI sessions | absent | behind: `CommandEditor` exists, never run against a model | `self_improve_adapters.py` |
| Model-backed selector | LLM, anonymized finals | absent | behind: contrast-score selector only | `ContrastSelector` |
| Executor adapters | OpenCode, Codex, benchmark runners | local agent loop, Codex and Claude session clients, none wired to harness edits | behind: argv presets and `CommandExecutor`, unverified against the real CLIs | `opencode_argv`, `codex_argv` |
| Carry-over across tasks | per-domain Library of full trees and lessons | `lesson_store.py` hash chain, not tied to harness edits | parity, gated | `self_improve_library.py` |
| Held-out graded set gating carry-over | absent | absent | ahead | `self_improve_gate.py` |
| Receipt per adopted edit (diff, contrast, held-out interval) | absent; `summary.json`, harness fingerprint, no seal | absent for harness edits | ahead | `self_improve_receipt.py` |
| False-success controls on the adoption path | leak globs, `assert_no_grader_verdicts` | `skill_gate.py` checks evidence consistency only | ahead: planted-edit suite, FIT or UNFIT | `self_improve_controls.py` |
| Lesson provenance and quarantine | entry names its label and run id; no quarantine | lessons journaled, no quarantine | ahead: quarantine first, cascade to descendants | `test_quarantine_cascades_to_descendants` |
| Rollback | `Library.forget` by task id | absent | ahead: lineage rollback quarantines later lessons | `test_rollback_restores_and_quarantines_later_lessons` |
| Change attribution | offline analysis (paper E.1, E.2) | absent | ahead: online leave-one-out, files then hunks then lines | `self_improve_units.py`, `_attribute` |
| Incumbent can win selection | no: finals-only pool, every task ships a refined harness | n/a | ahead: incumbent in the pool, wins ties | `pool_incumbent` in `run_task` |
| Statistical reporting | mean and SD over 3 runs | cluster bootstrap and MDE in `statistics.py` | ahead in method | `analyze.py` |
| Benchmarks | WorkBuddy-Bench, JobBench, LAB | none for harness editing | behind: one CPU substitute | `self_improve_bench.py` |
| Measured model-backed uplift | +1.2 to +11.8 points reported | none | absent | section 6 |
| Network restriction for executors | documented, not enforced | sandbox and egress modules exist | behind: not wired into this loop | open gap 4 |
| Cost accounting | rollouts, stages and USD per stage | `cost_floor`, receipts | partial: rollouts, edits and gate executions; no USD | `TaskRun.budget` |
| Editor concurrency | thread pool for proposals and rollouts | n/a | behind: rollouts only | `workers` in `run_task` |
| Transfer studies | cross-model, cross-benchmark | absent | absent | open gap 6 |

## 3. Design: self-improvement that cannot fool itself

The task-level loop matches Harness-squared, so each task still gets the
contrast-chosen answer with no grader in the loop. What changes is the state
every later task inherits.

1. **Receipts.** Every gate decision, adopt or reject, is a sealed
   `flywheel.harness-edit-receipt/v3`: parent, candidate and adopted digests,
   the unified diff, the adopted change units, the contrast record (finals,
   scores, stages), the held-out effect with interval, the leave-one-out
   attribution, and a `scope` list of what the decision covers. v1 and v2
   receipts still verify. `verify_edit_receipt` re-derives the seal, the trees, the diff and the
   decision; numbers that do not support the decision read INCONSISTENT.
2. **A held-out graded set the refiner never sees.** The gate runs incumbent
   and candidate on the same graded tasks. Adopt when the paired mean
   difference is above 0 and the 90% bootstrap lower bound is at least 0.
   Attribution runs coarse to fine: leave each changed file out, then each
   hunk inside a kept file, then each line inside a kept hunk of at most 24
   lines. Only units whose removal costs held-out score are adopted.
3. **False-success controls.** Six planted edits per gate: forced-pass
   self-check, forced pass plus a wrong premise, a hard-coded leaked answer
   (all must be rejected), the complete fix, the complete fix with a
   forced-pass rider (adopted with the rider dropped), and the complete fix
   with a wrong-premise line in the same file (adopted with that line
   dropped). A gate that fails any control is UNFIT.
4. **Lesson provenance and quarantine.** Lessons enter quarantined and admit
   only on a receipt that re-verifies as MATCH with decision ADOPT and whose
   parents are admitted. Quarantine cascades to descendants.
5. **Rollback.** Adopted versions form a lineage; rollback restores a version
   and quarantines every lesson introduced after it.
6. **The incumbent competes.** The task-level selector chooses among the
   finals and the incumbent's own reference rollout, which wins ties. A task
   whose edits all made things worse keeps what it started with.

### Measurable targets

| Target | Threshold | Status |
|---|---|---|
| Planted false-success edits accepted | 0 of every control suite | met: v1 0 in 54, v2 0 in 54 |
| Planted real fixes rejected | 0 | met: v1 0 in 54, v2 0 in 54 |
| Gated incumbents carrying a harmful or gaming change | 0 of 54 | v1: 1 of 54; v2: 0 of 54 |
| Receipts that fail to re-verify | 0 for gated decisions | test-enforced |
| Test accuracy vs Harness-squared, no gaming | lower bound above -0.05 | v1: not met in 2 of 3; v2: met in 3 of 3 |
| Test accuracy vs Harness-squared, gaming 0.15 and 0.30 | lower bound above 0 in 2 of 3 configs | v1 and v2: met, 3 of 3 at both rates |
| Budget parity on the task loop | 4k rollouts, 3k edits | test-enforced |
| Model-backed uplift on a graded local benchmark | lower bound above 0 vs base | not run (section 6) |

## 4. The MVP

Eleven stdlib modules under `harness/` (all under 300 lines, every function
under 50), 80 tests under `tests/test_self_improve_*.py`, and a head-to-head
kit under `benchmarks/self_improve/`.

| Module | Role |
|---|---|
| `self_improve_tree.py` | harness as a tree of text; surface, digest, diff, component restriction |
| `self_improve_loop.py` | Propose-Probe-Compose, parallel and sequential, grader keys stripped |
| `self_improve_gate.py` | held-out paired gate, bootstrap interval, coarse-to-fine leave-one-out |
| `self_improve_units.py` | change units at file, hunk and line granularity; subset application |
| `self_improve_receipt.py` | sealed receipt and its re-derivation |
| `self_improve_library.py` | lessons with provenance, quarantine, cascade, lineage, rollback |
| `self_improve_stream.py` | harnessing-level recursion across a task stream, gate on or off |
| `self_improve_controls.py` | planted-edit control suite |
| `self_improve_adapters.py` | callable and command-line executors and editors, contrast selector |
| `self_improve_bench.py` | ledger-quirks substitute benchmark |
| `self_improve_bench_agents.py` | seeded scripted editor, composer, planted edits |

## 5. Head-to-head result, v1

Preregistration: `project-docs/prereg/2026-10-21-self-improving-harness-headtohead.md`,
frozen at commit `adafa696` (sha256 `ec30dff5...0948d3`) before any
preregistered cell ran.

Run: 54 cells (6 seeds, 3 gaming rates, 3 configurations), CPU only, in WSL,
about 40 minutes. Raw cell files: 3.6 MB, sha256 over the sorted files
`96c130be...4eb643`; the run is deterministic and reruns from the commit above.
Analysis output: `project-docs/records/2026-10-21-self-improving-harness-headtohead.results.json`.

**Verdict under the preregistered rule: not established.** Flywheel wins at
both gaming rates. At gaming rate 0 the point estimates favour Flywheel in all
three configurations, but two intervals reach below the -0.05 margin, so the
non-inferiority half of the rule fails and no superiority claim is made.

Primary contrast, test phase, `flywheel_gated` minus `harness2_c0.50`
(accuracy difference, 95% cluster-bootstrap interval over 6 seeds, 144 paired
tasks per cell row):

| Gaming rate | parallel k=1 | parallel k=2 | sequential k=2 | Rule |
|---|---|---|---|---|
| 0.00 | +0.35 [+0.16, +0.53] | +0.12 [-0.13, +0.38] | +0.16 [-0.06, +0.39] | NON-INFERIOR not met |
| 0.15 | +0.38 [+0.22, +0.51] | +0.26 [+0.18, +0.35] | +0.26 [+0.08, +0.42] | WIN |
| 0.30 | +0.19 [+0.05, +0.33] | +0.13 [+0.01, +0.24] | +0.23 [+0.09, +0.35] | WIN |

Test accuracy by arm (mean over 144 tasks):

| Gaming rate, config | base | Harness-squared c=0.5 | Harness-squared c=1.0 | Flywheel ungated | Flywheel gated | Flywheel gated incumbent alone |
|---|---|---|---|---|---|---|
| 0.00 parallel k=1 | 0.01 | 0.35 | 0.25 | 0.24 | 0.70 | 1.00 |
| 0.00 parallel k=2 | 0.01 | 0.34 | 0.11 | 0.15 | 0.46 | 1.00 |
| 0.00 sequential k=2 | 0.01 | 0.44 | 0.14 | 0.15 | 0.60 | 1.00 |
| 0.15 parallel k=1 | 0.01 | 0.15 | 0.00 | 0.00 | 0.52 | 0.90 |
| 0.15 parallel k=2 | 0.01 | 0.01 | 0.00 | 0.00 | 0.28 | 0.85 |
| 0.15 sequential k=2 | 0.01 | 0.13 | 0.00 | 0.00 | 0.39 | 1.00 |
| 0.30 parallel k=1 | 0.01 | 0.14 | 0.00 | 0.00 | 0.33 | 0.51 |
| 0.30 parallel k=2 | 0.01 | 0.06 | 0.00 | 0.00 | 0.19 | 0.47 |
| 0.30 sequential k=2 | 0.01 | 0.07 | 0.00 | 0.00 | 0.30 | 0.79 |

Other preregistered numbers:

- **Controls.** 54 of 54 control suites FIT: no planted false-success edit was
  adopted and no planted real fix was refused.
- **Gate ablation.** Gated minus ungated is positive with the interval above 0
  in all nine test cells (+0.19 to +0.52). The gate, not the rest of the loop,
  carries the result.
- **Cost.** Harness-squared and both Flywheel arms spend 4k rollouts per task.
  The gate adds held-out executions during the stream: Flywheel gated averages
  11.5 to 29.6 executions per stream task against 4 to 8. Test-phase cost is
  equal because the gate is off while state is frozen.
- **Carry-over poisoning.** One of 54 gated incumbents carried a harmful
  feature: seed 0, gaming 0.30, parallel k=2, where `abs` rode into
  `scripts/summarize.py` together with three real fixes in the same file. The
  gate attributes by file, so a bad change inside a file with a net-positive
  edit passes. Harness-squared's delivered harnesses carried a gaming or
  harmful feature on 17% to 99% of test tasks.

Exploratory finding, not preregistered: the gated incumbent run alone scores
0.47 to 1.00 on the test set, well above the gated loop's own delivered output
(0.19 to 0.70). The task-level loop, which matches Harness-squared by
selecting among refined finals only, degrades a good incumbent because its
grader-free selector cannot tell a harmful edit from a real one. Adding the
incumbent to the selection pool is the obvious next change. It needs its own
preregistration on fresh seeds before it counts.

What this does not show: anything about either system with a model editor, or
on WorkBuddy-Bench, JobBench or LAB. The proposal mix is a declared parameter.

**Decision record.** Finding: the held-out gate removes most carry-over
poisoning at equal task-loop budget, for about two to four times the stream
executions, and the non-inferiority margin at gaming rate 0 was not met.
Decision (for the author): ship the gate on by default and make no superiority
claim against Harness-squared. Recheck trigger: the incumbent-in-pool change
and a model-backed run (section 6).

## 5b. Head-to-head result, v2

Preregistration: `project-docs/prereg/2026-10-21-self-improving-harness-headtohead-v2.md`,
frozen at commit `d6bb0049` (sha256 `871773a1...669fbd`) before any counted
cell ran. Fresh seeds 200 to 205. The design changes were chosen after reading
v1 and are tested here, not claimed from v1's data. Run: 54 cells, CPU only, in
WSL, about 45 minutes. Raw cell files 6.3 MB, sha256 over the sorted files
`300d1c74...6650a0`, not committed; the run reruns deterministically. Analysis
output: `project-docs/records/2026-10-21-self-improving-harness-headtohead-v2.results.json`.

**Verdict under the v2 rule: met on this substitute benchmark.** Gaming rate 0
is NON-INFERIOR in all three configurations, rates 0.15 and 0.30 are WINs in
all three, and all 54 line-gate control suites are FIT. This is a result about
ledger-quirks with a scripted editor. It says nothing about model editors or
about Harness-squared's own benchmarks.

Primary contrast, test phase, `flywheel_v2` minus `harness2_c0.50`, 95%
cluster-bootstrap interval over 6 seeds, 144 paired tasks per cell:

| Gaming rate | parallel k=1 | parallel k=2 | sequential k=2 | Rule |
|---|---|---|---|---|
| 0.00 | +0.44 [+0.17, +0.72] | +0.61 [+0.12, +0.99] | +0.60 [+0.31, +0.88] | NON-INFERIOR |
| 0.15 | +0.24 [+0.08, +0.41] | +0.72 [+0.43, +0.98] | +0.71 [+0.42, +0.95] | WIN |
| 0.30 | +0.28 [+0.03, +0.59] | +0.30 [+0.08, +0.60] | +0.65 [+0.33, +0.94] | WIN |

Test accuracy by arm:

| Gaming rate, config | Harness-squared c=0.5 | Flywheel v1 | Flywheel line only | Flywheel pool only | Flywheel v2 |
|---|---|---|---|---|---|
| 0.00 parallel k=1 | 0.33 | 0.74 | 0.74 | 0.76 | 0.76 |
| 0.00 parallel k=2 | 0.29 | 0.53 | 0.53 | 0.90 | 0.90 |
| 0.00 sequential k=2 | 0.40 | 0.62 | 0.62 | 0.74 | 1.00 |
| 0.15 parallel k=1 | 0.13 | 0.49 | 0.49 | 0.37 | 0.38 |
| 0.15 parallel k=2 | 0.03 | 0.25 | 0.25 | 0.78 | 0.76 |
| 0.15 sequential k=2 | 0.06 | 0.40 | 0.40 | 0.77 | 0.76 |
| 0.30 parallel k=1 | 0.04 | 0.31 | 0.31 | 0.38 | 0.33 |
| 0.30 parallel k=2 | 0.01 | 0.11 | 0.11 | 0.41 | 0.31 |
| 0.30 sequential k=2 | 0.01 | 0.17 | 0.17 | 0.66 | 0.66 |

Secondary rules:

- **Pool: supported.** `flywheel_v2` minus `flywheel_line_only` at rate 0:
  +0.02 [-0.30, +0.31] (parallel k=1), +0.38 [+0.09, +0.56] (parallel k=2),
  +0.38 [+0.27, +0.49] (sequential k=2). Two of three lower bounds are above
  0. With k=1 the pool adds nothing measurable, and at rate 0.15 parallel k=1
  the point estimate is negative: -0.11 [-0.24, +0.03].
- **Line attribution: supported.** Gated incumbents carrying a gaming or
  harmful feature, each of 54: `flywheel_v2` 0, `flywheel_line_only` 0,
  `flywheel_v1` 0, `flywheel_pool_only` 7, `flywheel_ungated` 51. On these
  seeds the file-level gate leaked once it also had the incumbent in the
  pool, and line attribution closed that. Line attribution changed accuracy
  little: `flywheel_v2` minus `flywheel_pool_only` is 0.00 to +0.26 at rate 0
  and -0.10 to +0.01 at rates above 0, every interval covering 0.
- **Check of the check: passed.** The file-gate control suite is UNFIT in 54
  of 54 cells and fails only `complete_fix_with_wrong_premise_line`, so the
  new control has teeth.
- **v1 on fresh seeds.** `flywheel_v1` minus `harness2_c0.50` is positive in
  all nine cells. At rate 0 two intervals reach below 0 (-0.06 and -0.05),
  the same pattern as the v1 run.
- **The loop no longer degrades the incumbent.** The v2 incumbent alone minus
  the v2 loop's delivered output runs from -0.06 to 0.00. In v1 the incumbent
  alone was far ahead.
- **Cost.** `flywheel_v2` spends 10.3 to 25.3 executions per stream task
  against 4 to 8 for Harness-squared. The gate accounts for all of the
  difference. Test-phase cost is equal.

**Decision record.** Finding: with the incumbent in the pool and line-level
attribution, Flywheel's loop meets the preregistered rule against
Harness-squared on ledger-quirks, with zero poisoned incumbents in 54 cells, at
about two to three times the stream executions. Decision (for the author):
ship the v2 defaults (`pool_incumbent=True`, `granularity="line"`). The claim
that may be stated is narrow: on the CPU substitute benchmark ledger-quirks,
with a scripted editor and identical proposal streams, Flywheel's gated loop
beat Harness-squared as released under a preregistered rule. It does not
extend to model editors or to WorkBuddy-Bench, JobBench or LAB. Recheck
trigger: the model-backed run in section 6.

## 6. Model-backed run: ready to run, not run

The GPU stayed free by direction of the author on 2026-10-21 (engine and game
work first), and no paid call was made. The plan below needs the local GPU and
nothing paid. Take the GPU through the lock helper the Low Water repo is
adding (`tools/gpu-lock.mjs`); this document does not touch `D:/gpu.lock.d`.

1. Model: `qwen3-coder:30b` on the local Ollama server, for executor and
   editor on both sides, so neither system gets a stronger model.
2. Flywheel side (Windows or WSL): run `Stream` on ledger-quirks with
   `CommandExecutor(codex_argv("qwen3-coder:30b", local_provider="ollama"))`
   and `CommandEditor` on the same argv, gate on the seed's 16 gate tasks.
   The mission text for the editor is the open item: it must name the
   editable files and forbid reading anything outside the workspace.
3. Harness-squared side (WSL, POSIX only):

       cd harness2 && uv venv --python 3.12 .venv && . .venv/bin/activate
       uv pip install -e '.[render]'
       export HARNESS2_CODEX_BASE_URL=http://127.0.0.1:11434/v1
       export HARNESS2_CODEX_API_KEY=ollama HARNESS2_CODEX_MODEL=qwen3-coder:30b
       export HARNESS2_SOLVER_MODEL=ollama/qwen3-coder:30b
       export HARNESS2_IMPROVER_MODEL=ollama/qwen3-coder:30b

   then run `benchmarks/self_improve/h2_arm.py` with the released `Proposer`
   in place of `ScriptedProposer`. Unverified: whether the pinned OpenCode
   accepts an `ollama/` provider without an `opencode.json` provider block,
   and whether Ollama's Responses endpoint satisfies the Codex substrate
   (low confidence on both; `harness2-check --substrate cx` is the first
   command to run).
4. JobBench is the one Harness-squared benchmark with a local path:
   `HARNESS2_JUDGE_BASE_URL` points its judge at an OpenAI-compatible
   endpoint. A local judge changes the benchmark (the paper used Claude Opus
   4.8), so results would compare the two systems with each other, not with
   the paper. Flywheel has no JobBench adapter yet.
5. Block `huggingface.co`, `hf.co`, `github.com` and
   `raw.githubusercontent.com` for the executor after setup, as the
   Harness-squared experiment guide asks.

## 7. Open gaps

1. No model-backed result for either system on any benchmark here.
2. No adapter for WorkBuddy-Bench, JobBench or LAB.
3. Model selector and model reflector adapters are absent.
4. The loop does not yet run executors inside Flywheel's egress sandbox.
5. No USD accounting in the loop.
6. No transfer study (cross-model, cross-benchmark).
7. Line attribution splits a hunk only up to 24 lines; a larger hunk is
   judged whole. A line subset that no longer runs counts as a cost, so lines
   inside a kept hunk that only work together are kept together.
8. With k=1 the incumbent in the pool showed no measurable gain, and one
   configuration had a negative point estimate at gaming rate 0.15.
9. The gate costs graded examples. With n = 16 it cannot see an effect
   smaller than one task in sixteen, and a conjunctive fix whose parts only
   pay off together is kept only when the whole candidate carries them.
