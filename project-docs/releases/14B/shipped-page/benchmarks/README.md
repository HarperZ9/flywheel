# Benchmark artifacts

The JSON behind every number on [BENCHMARKS.md](../BENCHMARKS.md). Each file
names its own arms, counts, and model references so you can recompute any figure
without trusting the page.

| File | What it is | How to read it |
|---|---|---|
| `he_base_comparison.json` | Paired base against continued-pretrained, 164 code-completion tasks, pass@1 greedy at temperature 0, same harness for both arms | The strongest artifact here. It reports the discordant pairs, so you can recompute McNemar yourself |
| `humaneval_base_qwen14b.json` | The base arm's per-task record | Raw input to the comparison above |
| `humaneval_flywheel14b.json` | The continued-pretrained arm's per-task record | Raw input to the comparison above |
| `easy_set_8task_scorecard.json` | 8 everyday tasks, every arm saturating at 8/8 | Read as a range check, not as evidence. Saturated arms cannot separate |
| `hard_set_scorecard_QUARANTINED.json` | The 10 point hard-set difference | **Quarantined.** n=10, one task of difference, interval [-0.236, +0.420]. It did not reproduce. It is shipped because deleting an unfavourable artifact is worse than publishing it with its label |

## Recompute the headline result yourself

From `he_base_comparison.json`, using only the discordant pairs:

```python
import json, math
from math import comb
d = json.load(open("he_base_comparison.json"))
p = d["paired"]
b = p["regressions_flywheel_fail_base_pass"]   # 14
c = p["gains_flywheel_pass_base_fail"]         #  9
n = d["base"]["n"]                             # 164

delta = (c - b) / n                                     # -0.0305
chi2  = (abs(b - c) - 1) ** 2 / (b + c)                 #  0.6957
m, k  = b + c, min(b, c)
p_val = min(1.0, 2 * sum(comb(m, i) for i in range(k + 1)) / 2 ** m)   # 0.4049
se    = math.sqrt(b + c - (b - c) ** 2 / n) / n
ci    = (delta - 1.96 * se, delta + 1.96 * se)          # (-0.0876, +0.0266)
```

The exact binomial McNemar and the continuity-corrected chi-square agree to
three decimal places here, which they need not in general.

## What these artifacts do not establish

- **The base control arm is not hash-pinned.** It is recorded as
  `ollama:qwen2.5-coder:14b-instruct-q4_K_M`, a name rather than a digest, and
  that name no longer resolves on the machine that produced these numbers. The
  comparison is our most trustworthy result and its control arm cannot currently
  be identified byte for byte. That is a defect in our record, not a caveat about
  the method, and it is being fixed by publishing a name to weight-digest
  resolution table.
- **Contamination is not bounded.** The training corpus manifest records a file
  count and not a file list, so we cannot prove the evaluation set was absent
  from training. For this 14B the ordering is favourable, since continued
  pretraining finished before the hard task set was written, but ordering bounds
  when a task was admitted and not what was in the corpus.
- **One run each.** There is no between-seed variance component in any figure
  here, so none of these intervals include run-to-run variability.
