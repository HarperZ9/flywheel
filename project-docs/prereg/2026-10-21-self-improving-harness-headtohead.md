# Preregistration: Flywheel's gated self-improving harness against Harness-squared

**Status:** frozen at the commit that adds this file, before any preregistered
cell ran. Smoke runs on seeds 100 and up exercised the code paths and were not
analyzed for outcomes. The register is `flavored`.

## 1. Decision this informs

- **Decision.** Whether Flywheel's self-improving loop ships with the held-out
  gate on by default, and whether Flywheel may state that its loop beats
  Harness-squared on contrast-gaming robustness on this substitute benchmark.
- **Owner.** The author (Zain Dana Harper).
- **Baseline.** Harness-squared as released (google-research/harness2 at
  `1cfe254e8d25b15f37048c3730134686abe60335`), run through its own `run_task`,
  recursion, selection, reflection and Library code.
- **What would change the decision.** The rule in section 5.

## 2. Benchmark

`ledger-quirks` (`harness/self_improve_bench.py`), a documented substitute. The
three benchmarks Harness-squared reports grade with hosted model judges and
need hosted executors, so none runs locally without spend. Each task is a ledger
whose exact signed total is the answer. Quirks per task: negatives, thousands
separators, parenthesized negatives, currency symbols, duplicated rows, each
with probability 0.5. The harness's self-check sees unparsed rows and is blind
to sign errors and duplicates.

Splits per seed, generated from disjoint random streams: stream 20 tasks, gate
16 tasks (Flywheel only), test 24 tasks (no system sees them before the test
phase; neither system edits its carried state during it).

## 3. Arms and budgets

Both systems use the same deterministic executor, the same seeded scripted
editor (`ScriptedEditor`: per probe slot, gaming edit with probability
`p_game`, harmful edit 0.15, real fix otherwise), the same composer and the
same contrast selector (self-check verdict plus parsed-row fraction).

| Arm | Carry-over |
|---|---|
| `harness2_c0.50` | Library as released; editor copies the latest entry with probability 0.5 |
| `harness2_c1.00` | Same, copy probability 1.0 (sensitivity) |
| `flywheel_gated` | Incumbent moves only through the held-out gate (leave-one-out component attribution, paired bootstrap, 90% interval, point > 0 and lower bound >= 0) |
| `flywheel_ungated` | Chosen harness always becomes the incumbent (ablation) |
| `base` | Base harness, no loop |

Configurations: (parallel, k=1), (parallel, k=2), (sequential, k=2). Both
systems spend 4k rollouts and 3k editor calls per task. Flywheel also spends
gate executions; they are reported, not hidden. Gaming rates: 0.0, 0.15, 0.30.
Seeds 0 to 5.

## 4. Endpoints

- **Primary.** Test-phase accuracy, `flywheel_gated` minus `harness2_c0.50`,
  paired by (seed, task), 95% interval from a cluster bootstrap over seeds
  (4000 draws, seed 7), per (rate, configuration).
- **Secondary.** Stream accuracy; the same contrast against `harness2_c1.00`,
  `flywheel_ungated` and `base`; poisoned rate (delivering harness carries a
  gaming or harmful feature); executions per task; the planted-edit control
  verdict per cell.

## 5. Decision rule

- At `p_game = 0`: NON-INFERIOR if every configuration's lower bound exceeds
  -0.05, otherwise INFERIOR.
- At `p_game > 0`: WIN if the lower bound exceeds 0 in at least two of three
  configurations, otherwise NO WIN.
- Flywheel is better on this benchmark only if p = 0 is NON-INFERIOR, every
  p > 0 is a WIN, and every cell's control suite is FIT.
- If the rule fails, the result says so, the gate default is decided on the
  measured tradeoff, and no superiority claim is made.

## 6. What this cannot show

The editor is scripted with a declared proposal mix, not a model. The result
measures carry-over mechanics under identical proposal streams. It does not
predict either system's gains on WorkBuddy-Bench, JobBench or LAB, and it does
not measure what a model editor proposes. Flywheel uses 16 graded tasks per
seed that Harness-squared does not; that is the design difference under test,
and its cost is reported.
