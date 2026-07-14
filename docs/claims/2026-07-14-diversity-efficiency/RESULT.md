# Result — the sealed prediction, adjudicated

Witnessed verdict `cc7808b1…`. Two claims, sealed before their benches
completed, now judged against the artifacts.

## The prediction MISSED, low, by 0.0009 — and that is the finding

The 3b best-of-5 wrapped rate landed at **23/110 = 0.2091**. The sealed band
was [0.21, 0.36]. It misses the floor by 0.0009 of a task — a razor miss,
but a miss. Crucible calls it DRIFT and it ships as DRIFT.

No narrative rescue, per the frozen verdict rule. But note precisely what
missed and what did not, because the interpretation was frozen in the
addendum BEFORE this number existed:

- The adversarial math review predicted, in writing, that bimodal rescue
  distributions land at **0.19-0.22, missing low**. The measured 0.209 is
  dead in that predicted band. The naive eta-constant-in-N model is
  falsified; the adversary's heterogeneity model is corroborated. **The
  process caught its own error before the data could.**
- Per the addendum: a low miss falsifies eta-constancy in N, NOT the
  cross-scale diversity claim, which was never what this single-model band
  tested. The corrected E0-E6 protocol (per-task panels, the greedy-first
  null, the mutated-twin memorization control) remains the real instrument
  and is unaffected.
- `c-eta-order` (eta(3b) > eta(7b) at best-of-3) stays a witnessed MATCH.

The honest headline: **we predicted a number, sealed it, and were wrong by
one part in a thousand — in exactly the direction our own skeptic warned.**
That is preregistration working as designed. A field that only publishes
its hits learns nothing from a miss like this; we learned the confound is
real.

## The 14B fork — H-neutral, weakly

The telos-coder-14b full lane (best-of-3): **bare 46/110 (42%), wrapped
58/110 (53%)**, uplift +11% [-0.022, 0.235] — includes zero, no uplift
claimed at this n. eta(14B-CPT) = 0.2835, just above the 7b-base 0.269.

Sealed fork verdict: **H-neutral is favored** — continued-pretraining did
not collapse proposal diversity below the base; eta tracks scale, not
training. Weak (0.2835 vs 0.269, inside every Jensen caveat), directional
only, but it was the registered call and the number chose it.

## What the 14B run establishes regardless of eta

- **The trained flagship is genuinely strong**: 42% single-shot / 53%
  verified on the hard lane, more than double the 7b's 18% / 25%. The
  provenance chain (sha 613db240…) and the artifact agree.
- **The frontier is confirmed multi-axis, no single king**:
  - per-GB: **3b wins** (0.110 wrapped-pass/GB vs 14B 0.059, 7b 0.054)
  - quality ceiling: **14B wins, decisively** (53% vs 25%)
  - per-second: 7b/14B bare beat any wrapped arm — verification buys
    accuracy with time, never saves it.
  The right model is the one whose binding constraint you name. That is the
  answer to "instead of streaming a bigger model in, multiply a smaller one"
  — true when RAM binds, false when accuracy binds, and the receipts say
  which.
