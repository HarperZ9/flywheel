# Preregistration v2: incumbent in the pool and line-level attribution

**Status:** frozen at the commit that adds this file, before any counted cell
ran. Smoke runs on seeds 300 and up exercised the code paths and were not
analyzed for outcomes. The register is `flavored`.

**Follows:** `2026-10-21-self-improving-harness-headtohead.md` (v1, frozen at
`adafa696`). v1 withheld the superiority claim: Flywheel won at gaming rates
0.15 and 0.30, but the non-inferiority margin at rate 0 was missed in two of
three configurations. v1 also produced two findings this run tests:

- Exploratory: the gated incumbent alone scored 0.47 to 1.00 on test while the
  loop's delivered output scored 0.19 to 0.70. Selecting among refined finals
  only degrades a good incumbent.
- One of 54 gated incumbents carried `abs`, which rode into
  `scripts/summarize.py` beside three real fixes because the gate attributed by
  file.

## 1. Decision this informs

- **Decision.** Whether the shipped defaults become incumbent-in-pool and
  line-level attribution, and whether Flywheel may state that its loop beats
  Harness-squared on this substitute benchmark.
- **Owner.** The author (Zain Dana Harper).
- **Baseline.** Harness-squared as released at
  `1cfe254e8d25b15f37048c3730134686abe60335`, unchanged from v1.

## 2. What changed since v1

1. **Incumbent in the pool.** The incumbent's first reference rollout (base1)
   joins the selection pool and wins ties on the contrast score. It costs no
   extra rollout. Harness-squared keeps its finals-only pool.
2. **Coarse-to-fine attribution.** Leave-one-out first over changed files,
   then over hunks inside kept files, then over lines inside kept hunks of at
   most 24 lines (`self_improve_units.py`). A unit is kept when removing it
   costs held-out score under the v1 rule (point above 0, 90% lower bound at
   least 0).
3. **Benchmark text.** Each feature in `scripts/summarize.py` now sits on its
   own line, so a line diff separates features. Behaviour is unchanged; both
   systems see the same text.
4. **One more control.** `complete_fix_with_wrong_premise_line`: the complete
   fix plus `abs` in the same file. It must be adopted with `abs` dropped.

## 3. Arms

| Arm | Gate | Pool | Attribution |
|---|---|---|---|
| `flywheel_v2` | on | incumbent + finals | line |
| `flywheel_v1` | on | finals | file |
| `flywheel_pool_only` | on | incumbent + finals | file |
| `flywheel_line_only` | on | finals | line |
| `flywheel_ungated` | off | finals | n/a |
| `harness2_c0.50` | as released, carry probability 0.5 | finals | n/a |
| `harness2_c1.00` | as released, carry probability 1.0 | finals | n/a |
| `base` | none | none | none |

Everything else is unchanged from v1: the ledger-quirks benchmark, splits of
20 stream, 16 gate and 24 test tasks, the scripted editor with harmful rate
0.15, the composer and contrast score, 4k rollouts and 3k edits per task,
configurations (parallel k=1, parallel k=2, sequential k=2), gaming rates 0.0,
0.15 and 0.30. **Seeds 200 to 205**, none used before.

## 4. Endpoints

- **Primary.** Test accuracy, `flywheel_v2` minus `harness2_c0.50`, paired by
  (seed, task), 95% cluster-bootstrap interval over seeds (4000 draws, seed 7).
- **Secondary.** `flywheel_v2` against `flywheel_line_only` (effect of the
  pool), against `flywheel_pool_only` (effect of line attribution), against
  `flywheel_v1`, `flywheel_ungated`, `harness2_c1.00` and `base`;
  `flywheel_v1` against `harness2_c0.50` (does v1 replicate on fresh seeds);
  gated incumbents carrying a gaming or harmful feature, per arm; executions
  per stream task; control suites.

## 5. Decision rule

- **Primary.** Same as v1. At gaming rate 0, NON-INFERIOR if every
  configuration's lower bound exceeds -0.05. At each rate above 0, WIN if the
  lower bound exceeds 0 in at least two of three configurations. Flywheel is
  better on this benchmark only if rate 0 is NON-INFERIOR, every rate above 0
  is a WIN, and every line-gate control suite is FIT.
- **Pool.** The pool change is supported if `flywheel_v2` minus
  `flywheel_line_only` has a test lower bound above 0 in at least two of three
  configurations at gaming rate 0.
- **Line attribution.** Supported if `flywheel_v2` and `flywheel_line_only`
  have zero poisoned incumbents across all 54 cells each. A single poisoned
  incumbent fails it.
- **Check of the check.** The file-gate control suite is expected to be UNFIT
  in every cell, failing only `complete_fix_with_wrong_premise_line`. If it
  passes, the new control has no teeth and the line result does not count.
- A rule that fails is reported as failed, and its claim is withheld.

## 6. What this cannot show

Same limits as v1. The editor is scripted with a declared proposal mix. The
result says nothing about model editors or about WorkBuddy-Bench, JobBench or
LAB. The design changes were chosen after reading v1's outcomes, which is why
they are tested here on fresh seeds and not claimed from v1's data.
