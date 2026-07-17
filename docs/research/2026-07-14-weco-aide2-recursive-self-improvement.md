# Weco AIDE2: recursive self-improvement, read against our loop

Source: https://www.weco.ai/blog/first-evidence-of-recursive-self-improvement
(operator-shared 2026-07-14). Snapshot receipt: the direct fetch froze a
BLOCK/CHALLENGE page, named as such by the snapshot lane
(`artifacts/research/9f5a7b59...bin`, sha 9f5a7b595d37aa0e...), so the
content summary below is from a rendered fetch, status
operator_relayed_secondary until a clean freeze exists. That honesty gap is
itself the cycle-3 block-page detector working.

## Their claim (relayed, moderate confidence)

An outer-loop agent (AIDE2) rewrote an inner-loop agent's code over ~100
iterations against heterogeneous ML-engineering tasks under fixed budgets.
The discovered agent (AIDE85) beat the hand-tuned baseline on three external
benchmarks, compressed its prompt ~16x, invented a bandit-style search
policy, and cut reward-hacking from 63% to 34%. Authors state plainly: no
"ignition" (improved agents did not become better improvers), evolved code
is hard to maintain, no third-order generalization.

## Read against the improvement loop (what pours back)

- Their loop optimizes an agent against benchmark reward; ours consults
  adversarially and repairs against the credo with external oracles. The
  shared failure class is the same one: a verifier that can be gamed.
  Their 34% residual reward-hacking is what "no learned model in the accept
  path" plus oracle_can_fail (cycles 4-5) exist to drive to zero, not to a
  lower percentage.
- Their honest no-ignition null is the register discipline we keep: banked
  as stated, no uplift inferred beyond their own numbers.
- Candidate experiment for the invention lane: measure whether OUR loop's
  fix rate per cycle decays (cycles 1-5: 24, 17, 16, 19, 23 findings) --
  a falsifiable "does the loop dry up" curve, preregistered before cycle 6.

No claim of ours changes on this source alone.
