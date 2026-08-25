# Private verified benchmarks: the competitive feature note

Date: 2026-08-23

## The scan (August 2026)

Sources: Morph LLM rankings, tbench.ai leaderboard, Artificial Analysis
Coding Agent Index, Pragmatic Engineer Feb 2026 survey (15,000 devs),
Prime Intellect verifiers-v1 release notes, SWE-bench Pro contamination
audit coverage.

| Competitor | What they ship | The gap this feature exploits |
|---|---|---|
| Claude Code (46% usage share) | Best SWE-bench Verified via Opus; Anthropic-only; $17-100/mo | Scores are vendor-run on public, contaminated tasks; you cannot re-check them or run them on your repo |
| Codex CLI | Terminal-Bench 2.1 lead with GPT-5.5 | Same: vendor harness, public tasks, no receipts |
| OpenCode (172K stars, 7.5M MAU) | Won by decoupling harness from model; BYOK 75+ providers | Evaluation is still "run your model on public benches"; no verification layer at all |
| Cursor | IDE-first, Composer models | No eval transparency; closed |
| Prime Intellect verifiers v1 | Taskset/Harness/Runtime decomposition; Trace artifact; 2,500+ envs; RL training loop | Built for RL training, not for an operator asking "does this endpoint pass MY gates?"; no cryptographic receipts; cloud-hosted |
| omp / pi / Hermes | Token-volume leaderboards (1.6-2T tokens/day) | Volume is not verified correctness; no per-attempt evidence |

The industry's own words: "the harness alone can move the number by
several points" and "every frontier model can reproduce verbatim gold
patches" (SWE-bench Verified contamination audit). Everyone names the
model-vs-harness problem; nobody ships its fix.

## The feature: private verified benchmarks

`harness/verified_bench.py` + `/api/bench/run` (exact grant, exec+network
scopes, `flywheel.verified-bench/v1` + `flywheel.verified-frontier/v1`):

1. Tasks come from your repo as a strict JSONL set -- they never leak
   into any training corpus, so the score is contamination-proof by
   construction.
2. Every candidate endpoint in the ladder (Claude, ox-alpha via
   OpenRouter, DeepSeek, GLM, Gemini, local) proposes; a REAL subprocess
   gate decides. No learned model on the accept path, no shell, hard
   timeout, output hashed into the gate ref.
3. Each attempt is sealed: task, endpoint, proposed-sha256, gate pass,
   gate ref, denominators, does_not_prove, one bench hash.
4. The frontier ranks verified pass rate per endpoint and, with cost
   inputs, the Pareto set of verified quality per dollar -- "verified
   passes per dollar on your gates", a number no vendor benchmark, no
   token counter, and no RL-env hub can produce.

Why it beats the field substantially: it converts evaluation from a
vendor claim you must trust into evidence you re-check offline. OpenCode
decoupled the harness from the model; Flywheel decouples evaluation from
the vendor. That is the layer above them all.

## Verification

```text
python -m pytest tests/test_verified_bench.py -q             # 7/7
python -m pytest tests/test_verified_bench_route.py -q       # 4/4
python -m pytest tests/ -q --tb=no                           # 0 failures
python scripts/check_file_gate.py                            # clean
python scripts/check_verifier_stdlib.py                      # clean
flutter test --no-pub (desktop/)                             # 567 passed
flutter analyze --no-pub (desktop/)                          # no issues
```

## Does not prove

A verified pass rate is over the given task set and gates only; it is
not a general capability score. Cost-per-task figures are operator
inputs, not measurements. The route runs real subprocess gates under an
exec+network exact grant; admission is refused for unconfigured
endpoints and malformed task sets before any run.
