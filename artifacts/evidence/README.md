# Evidence artifacts, internal

Four run artifacts that existed only on the run drive and were therefore
unavailable to anyone outside this machine. Stranger reproducibility cannot mean
anything while the evidence lives somewhere the stranger cannot reach, and 99 KB
is no reason to keep them out.

They are here because they are the record, not because they support a claim.
Every cross-arm comparison below is retired.

| File | What it holds | Status |
|---|---|---|
| `selector_comparison_headroom.json` | single-shot / external / self selector over 61 headroom tasks, with per-task outcomes | **Retired as a comparison.** Two independent defects, both computed by `harness/findings_stats.py` rather than asserted |
| `selector_consensus_headroom.json` | the same plus a consensus arm | **Retired as a comparison.** This is the artifact `harness/findings.py` reads and hashes |
| `passn_curve_n32.json` | pass@N to N=32 over the headroom set | Diagnostic. A rising pass@k curve is a property of drawing more samples |
| `difficulty_screen_hard_v2_110.json` | single-attempt temperature-0 failure set, 110 tasks | Instrument reading, correctly self-labelled. **Must never define an uplift denominator** |

## Why the selector comparisons are retired

Both defects are visible in the per-task outcomes in these files, so you can
check this rather than take it from us.

1. **Selection on the dependent variable.** The 61-task denominator is the
   headroom screen, and the screen is defined by this same model failing the same
   temperature-0 draw that constitutes the single-shot arm. The single-shot rate
   is near zero by construction, so the difference is a resampling recovery rate
   whose expectation is positive for a model that learned nothing and a selector
   with no skill.
2. **Nested arms.** Zero tasks where single-shot passed and the external selector
   failed. Not one, in either file. The difference cannot be negative, so a
   two-sided p-value tests a null that construction excluded.

For the record, the statistics recomputed from the per-task vectors:

| File | gains | regressions | discordant | chi2_cc | exact p |
|---|---|---|---|---|---|
| `selector_comparison_headroom.json` | 12 | 0 | 12 | 10.0833 | 0.000488 |
| `selector_consensus_headroom.json` | 11 | 0 | 11 | 9.0909 | 0.000977 |

The regressions column is the point. A p-value of 0.0005 next to a zero in that
column is not strong evidence, it is a tautology with a small number attached.

`harness/findings.py` used to carry `McNemar p=0.0015` as a string literal, which
is the chi-square p-value of the *first* file while the code reads and hashes the
*second*. A statistic from one artifact was pinned to another artifact's
provenance hash. Fixed; now derived from whichever file is actually read.

## What replaces them

`harness/pool.py` and `harness/pool_arms.py`. One cached pool of independent
candidates per task with no early stopping, every arm an offline function of that
cache, and `paired()` refusing a two-sided statistic for any arm whose selector is
the same function that scores it.
