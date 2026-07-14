# Registered fork: the 14B's diversity efficiency — sealed mid-run

The telos-coder-14b (qwen2.5-coder-14b base + coding CPT, 2019 steps) is
mid-lane on the 110-task bench as this is written; its wrapped arm has not
completed. Two competing hypotheses are registered BEFORE its result
exists, with the discriminating readout named:

- **H-collapse**: post-training narrows proposal distributions (by analogy
  to RLVR/RLHF collapse: arXiv 2504.13837, 2310.06452), so
  eta(14B-CPT) < eta(7b-base) = 0.269. Confidence: low — the analogy
  stretches, CPT is not preference training.
- **H-neutral**: CPT behaves like continued pretraining and preserves base
  diversity; eta(14B) lands at or above the 7b's, tracking scale rather
  than training (REAL Sampling's entropy-vs-scale trend, arXiv 2406.07735).

Readout: aggregate eta from the completed run (with the SAME Jensen and
temperature caveats as the addendum — this fork is directional context,
not a corrected measurement; the E1 per-task panels remain the real
instrument). Neither hypothesis earns a claim without the corrected
protocol; the fork exists so that whichever way the number falls, the
interpretation was chosen before it existed.
