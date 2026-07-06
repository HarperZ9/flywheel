"""harness — Layer B verified-inference harness (HARNESS-ROADMAP.md M0-M7).

M0 (proposer) is serve.py. This package implements M1: the minimal witnessed
loop (task -> retrieve -> propose -> oracle-verify -> envelope -> witness).

Invariants carried through every module (HARNESS.md §reward-shaping, §envelope):
  - no receipt -> no accept
  - no learned model in the accept path (only the real oracle accepts)
  - the harness never authors the criterion (operator names the oracle)
"""
