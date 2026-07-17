# Agent reliability: domain dossier (2026-07-14)

Method: every finding below was adversarially re-checked against a live fetch
of its source; claim text was matched to the source's own words and numbers.
Nine findings survived as drafted, one after a numeric correction, and ten
failed checking and were dropped. Nulls are first-class content here.

## 1. The frontier in five sentences

Agent reliability in mid-2026 is a selection problem, not a generation
problem: repeated sampling keeps finding correct solutions for hundreds of
attempts, but every verifier-free selector measured so far plateaus long
before the coverage ceiling (https://arxiv.org/abs/2407.21787, July 2024).
The systems that close the gap all reach for executable evidence: model-written
tests (https://arxiv.org/abs/2501.14723, January 2025), synthesized
distinguishing inputs (https://arxiv.org/abs/2502.14382, February 2025), and
compute allocation keyed to task difficulty (https://arxiv.org/abs/2408.03314,
August 2024). Meanwhile the benchmark used to certify progress is itself under
audit: 24.4% of SWE-bench Verified leaderboard entries contained patches that
pass the official tests without fixing the issue (high confidence,
https://arxiv.org/abs/2506.09289, June 2025). The scaling mathematics has also
matured: aggregate pass@k power laws are an artifact of heavy-tailed per-task
success rates, and per-task curves decay exponentially
(https://arxiv.org/abs/2502.17578, February 2025). All five pressures land on
machinery this repo already has: a pytest oracle that can fail, per-task
outcome vectors on every bench run, an exact pass@k/consensus@k model, and a
difficulty screen.

## 2. Confirmed findings

### F1. Top SWE-bench Verified leaderboard rows are provenance-mixed

Claim: the steel.dev SWE-bench Verified leaderboard lists Claude Mythos 5 at
95.5% and Claude Fable 5 at 95.0% (both high confidence, fetched live during
verification), and the page itself warns that some rows are independently
benchmarked and some are team-reported, with contamination and test-design
caveats on top scores.

Source: steel.dev SWE-bench Verified leaderboard; data current 2026-05-28,
page updated 2026-07-10. The exact URL path was not retained in the
verification record (domain high confidence, path unknown).

Why it matters: the reference benchmark for coding agents now reads mid-90s
while its own host disclaims row provenance. The missing property is what a
verified-inference platform emits: a score row carrying a re-runnable receipt.

Pour-back: `BATTLE-MAP.md` benchmark axis and
`scripts/model_card_benchmark_shapes.py`. Shape: every published score row
records its provenance class (independently-run vs self-reported) plus a
receipt pointer; the benchmark-claim escrow niche targets this gap directly.

### F2. SWE-bench Verified exists because the raw benchmark failed human audit

Claim: 93 experienced Python developers annotated 1,699 random SWE-bench
samples; 38.3% were flagged for underspecified problem statements and 61.1%
for unit tests that could unfairly reject valid solutions; the final set is
500 human-validated tasks scored via FAIL_TO_PASS tests in a Docker harness
(all figures high confidence, read from the page during verification).

Source: https://openai.com/index/introducing-swe-bench-verified/ (URL moderate
confidence from memory; content verified live), August 2024.

Why it matters: the flagship benchmark needed a majority of raw tasks flagged.
Task admission gating is the difference between a benchmark and noise, and it
matches this repo's two-arm hard set (soundness curator, difficulty screen).

Pour-back: the task admission lane (curator gates plus
`scripts/difficulty_screen.py`). Shape: add an explicit underspecification
annotation axis to admission records, mirroring the two dominant flag reasons.

### F3. Passing official tests is not fixing the issue (UTBoost)

Claim: UTBoost found 345 patches that pass official SWE-bench tests without
resolving the issue, affecting 24.4% of SWE-bench Verified leaderboard entries
and changing 11 Verified rankings (all high confidence, matched to the
abstract).

Source: https://arxiv.org/abs/2506.09289, June 2025.

Why it matters: an oracle-only accept path is only as strong as its oracle,
and UTBoost shows weak test oracles corrupting even a human-audited benchmark
at scale. Oracle strength must be audited, not assumed.

Pour-back: `harness/oracle.py` and the oracle_can_fail admission gate. Shape:
a standing false-pass audit that attacks each task's oracle with non-solutions
and records the outcome in the task's admission receipt (build candidate B).

### F4. Coverage scales log-linearly; verifier-free selection plateaus

Claim: coverage grows log-linearly over four orders of magnitude of samples;
DeepSeek-Coder-V2-Instruct on SWE-bench Lite rises from 15.9% at one sample to
56% at 250 samples (high confidence); majority voting and reward models
plateau beyond several hundred samples.

Source: https://arxiv.org/abs/2407.21787 (Large Language Monkeys), July 2024.

Why it matters: this is the empirical basis for the platform's core bet. Pools
hold far more capability than single-shot inference extracts, and only a real
executable oracle keeps extracting as n grows. The pass@k vs consensus@k gap
in `scripts/passn_model.py` is this plateau measured natively on our bench.

Pour-back: `scripts/passn_model.py` and the bench report. Shape: report the
coverage-vs-selection gap as a first-class column, with the plateau as the
stated reason the oracle tier exists.

### F5. Aggregate pass@k power laws are a distributional artifact

Claim: aggregate polynomial pass@k scaling arises when single-attempt success
probabilities are heavy-tailed across tasks, while each individual task decays
exponentially with attempts; a distributional fit forecasts the scaling
exponent with about an order of magnitude lower relative error, equivalent to
roughly 2-4 orders of magnitude less inference compute (high confidence).

Source: https://arxiv.org/abs/2502.17578, February 2025.

Why it matters: `scripts/passn_model.py` currently flags k>n extrapolation as
a weak iid binomial fallback; this paper supplies the principled replacement.
It is also the mathematical core of the eta wound (Jensen bias from aggregated
heterogeneous rates) in `docs/research/2026-07-14-diversity-efficiency-memo.md`.

Pour-back: `scripts/passn_model.py` extrapolation mode plus E1 of the
diversity program. Shape: fit the per-task success distribution on a training
split and emit sealed held-out forecasts (build candidate A).

### F6. Compute-optimal allocation beats uniform best-of-N by more than 4x

Claim: compute-optimal test-time allocation improves efficiency by more than
4x over a best-of-N baseline (high confidence), with the winning strategy
depending on prompt difficulty, and can let a smaller model beat a 14x larger
one in a FLOPs-matched comparison.

Source: https://arxiv.org/abs/2408.03314 (Snell et al.), August 2024.

Why it matters: the difficulty screen already labels tasks saturates_at_temp0
vs headroom_at_temp0; that label is the difficulty signal this result says
should drive allocation. On local hardware budget is the binding constraint,
so a 4x efficiency claim earns an in-house replication attempt.

Pour-back: `scripts/difficulty_screen.py` labels wired into the bench runner.
Shape: difficulty-gated allocation A/B at matched budget (build candidate D).

### F7. CodeMonkeys prices the whole loop: 57.4% of SWE-bench Verified for about USD 2,300 (corrected after refutation)

Claim: CodeMonkeys resolved 57.4% of SWE-bench Verified issues on a budget of
approximately USD 2,300, using model-generated test scripts, test-based voting,
and a dedicated selection trajectory; ensemble selection over existing top
submissions scored 66.2% (all high confidence, read from the abstract). The
draft of this finding said 57.7% and was refuted on that number; 57.4% is what
the abstract states.

Source: https://arxiv.org/abs/2501.14723, January 2025.

Why it matters: it publishes cost alongside resolution, and cost per resolved
task is the column `BATTLE-MAP.md` already identifies as the number nobody
publishes. It also shows model-written tests working as a mid-tier oracle.

Pour-back: bench cost accounting. Shape: cost per resolved task (dollars or
tokens) as a standing receipt field, plus a model-written-test selection tier
above consensus@k.

### F8. Execution-grounded selection with distinguishing inputs moves small models past larger ones (S*)

Claim: with parallel sampling, sequential debugging, and a selector that
adaptively generates distinguishing inputs for pairwise comparison combined
with execution-grounded information, GPT-4o-mini beats o1-preview by 3.7% on
LiveCodeBench, and DeepSeek-R1-Distill-Qwen-32B reaches 85.7% vs o1 (high) at
88.5% (all high confidence, matched to the abstract).

Source: https://arxiv.org/abs/2502.14382, February 2025.

Why it matters: this is the strongest published recipe found for the
oracle-free tier. Executing candidates on inputs chosen to make them disagree
recovers a large part of the pass@k vs consensus@k distance on this bench.

Pour-back: the selection stage of the harness. Shape: an offline
distinguishing-input selector replayed against stored best-of-n artifacts
(build candidate C).

### F9. Diversified sampling buys Pass@100; majority voting can erase it

Claim: diversified sampling under a diversity-fidelity trade-off yields
relative gains of 9.5% in Pass@100 for code and 9.6% for math over stationary
sampling (high confidence), while under majority voting the diversity gains
can vanish.

Source: https://arxiv.org/abs/2502.11027, February 2025.

Why it matters: this is one half of the unclaimed quadrant the eta program
aims at. Diversity interventions raise coverage, but only an oracle-backed
selector keeps the gain; consensus selection is where the gain dies.

Pour-back: E1 and E6 in `docs/research/2026-07-14-diversity-efficiency-memo.md`.
Shape: a diversified-sampling arm in the iid candidate panels, scored at both
the pass@k ceiling and the consensus@k tier.

### F10. Min-p sampling did not survive independent reanalysis

Claim: with matched hyperparameter sweeps, min-p did not outperform baselines
in quality, diversity, or the quality-diversity trade-off, and the original
paper's human evaluation omitted data and applied statistical tests
incorrectly (high confidence, matched to the paper).

Source: https://arxiv.org/abs/2506.13681, June 2025.

Why it matters: sampler novelty is cheap and sweep-matched evidence is rare;
an ICLR 2025 oral fell to a controlled reanalysis. For the proposer this means
temperature plus top-p stays the default until a challenger wins under matched
sweeps on this bench.

Pour-back: harness proposer sampling defaults. Shape: one admission rule in
the bench docs: sampler changes require sweep-matched paired evidence, the
same bar eta is held to.

## 3. Honest nulls

- Min-p's headline claim (better quality AND diversity than temperature and
  top-p) failed an independent sweep-matched reanalysis
  (https://arxiv.org/abs/2506.13681, June 2025). The field has not shown a
  decoder-side sampler that dominates tuned temperature plus top-p for
  best-of-n coverage.
- No published work was found that measures a per-model proposal-diversity
  coefficient (like Flywheel's eta) and uses it to make sealed, pre-registered
  predictions of best-of-n uplift. The closest results
  (https://arxiv.org/abs/2502.11027 on prompt-diversity gains, February 2025;
  https://arxiv.org/abs/2502.17578 on distributional forecasting, February
  2025) each cover one half; nobody has combined them. That quadrant appears
  unclaimed (moderate confidence: absence after targeted search, not proof).
- Verifier-free selection does not scale: majority voting and learned reward
  models plateau beyond a few hundred samples
  (https://arxiv.org/abs/2407.21787, July 2024). No method has been shown to
  close the coverage-vs-selection gap without a real executable oracle.
- Sequential self-revision is not uniformly beneficial for agents: the
  systematic study at https://arxiv.org/abs/2506.12928 (June 2025) found
  reflection helps only when timed selectively, so "always revise" is not
  supported.
- Top SWE-bench Verified scores (95%+) are not clean evidence of solved
  software engineering: the leaderboard mixes team-reported and
  independently-run rows (steel.dev leaderboard, page updated 2026-07-10), and
  UTBoost showed 24.4% of Verified leaderboard entries contained patches that
  pass official tests without fixing the issue
  (https://arxiv.org/abs/2506.09289, June 2025).
- The power-law framing of repeated-sampling gains is an aggregation artifact,
  not a per-task law: individual tasks decay exponentially
  (https://arxiv.org/abs/2502.17578, February 2025), so extrapolating an
  aggregate pass@k curve to a single task is unsupported.

## 4. Dropped in verification

Ten findings failed adversarial checking against their sources and were
dropped; they are not reproduced here. One further finding (the CodeMonkeys
headline) was refuted as drafted and appears above only as corrected (F7).

## 5. Build candidates

### A. Distributional pass@k forecaster with sealed predictions

Grounds: F5 plus the unclaimed-quadrant null. Replace the flagged iid
extrapolation in `scripts/passn_model.py` with a heavy-tailed per-task fit
whose forecasts are sealed and falsifiable before the confirming run.

Smallest committable slice: add a fit mode to `scripts/passn_model.py` that
fits per-task success probabilities on a training split of the existing n=110
per-task outcome vectors, emits a held-out pass@k forecast as a
content-addressed JSON artifact, and fails loudly when the held-out error
exceeds the iid baseline's. One script change plus one artifact.

### B. Oracle strength audit for the hard set

Grounds: F2, F3. UTBoost found false-pass oracles behind 24.4% of a
human-audited leaderboard's entries; audit ours before anyone else does.

Smallest committable slice: `scripts/oracle_strength_audit.py` that runs a
non-solution battery (empty function, constant-return stubs, reference
solution with one mutated line) against every hard-set task's pytest oracle
and writes a per-task false-pass report; any task where a non-solution passes
gets flagged in its admission record. Pure local execution, no GPU.

### C. Distinguishing-input selector for the oracle-free tier

Grounds: F4, F8, F9. The consensus@k ceiling in `scripts/passn_model.py` is
the measured cost of having no oracle; S*-style execution-grounded pairwise
comparison is the published route to buying some of it back.

Smallest committable slice: an offline replay script that takes stored
best-of-n artifacts, finds tasks with disagreeing candidates, executes the
candidates on generated distinguishing inputs, selects by execution outcome,
and reports selection accuracy against the consensus@k and pass@k curves from
`scripts/passn_model.py`. No serve required; runs on existing artifacts.

### D. Difficulty-gated compute allocation A/B

Grounds: F6 plus the reflection-timing null. The difficulty screen's
saturates_at_temp0 vs headroom_at_temp0 labels are an allocation signal the
bench does not yet use.

Smallest committable slice: a budget-matched replay over existing bench
artifacts comparing uniform best-of-3 against an allocation giving one sample
to saturated tasks and the freed budget to headroom tasks, reporting the
paired delta with an interval. Replay only; a live confirming run is a later
slice.
