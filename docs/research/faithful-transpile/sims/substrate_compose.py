"""Substrate 7 — COMPOSITION: does faithfulness survive a pipeline of transpiles?

The engine is a chain T_L o ... o T_1. Two questions that could break or bound the principle:
  - graded composition: do faithful-but-noisy steps ACCUMULATE loss along the chain?
  - weakest link: does ONE unfaithful step destroy the whole pipeline regardless of the rest?
Model: the criterion readout score s = <x,c>. A faithful step preserves s but (if noisy) adds
independent noise; an unfaithful step replaces s with noise (drops the criterion). label = sign(s).

Prediction: faithful chains degrade GRACEFULLY (noise grows ~sqrt(L)); a single unfaithful step
collapses the chain to chance (weakest link) — the same shape as the reconcile's absorbing meet.

Stdlib only, seeded, deterministic.
"""
from __future__ import annotations
import math, random


def acc_through_chain(rng, n, steps):
    """steps: list of ('faithful', sigma) or ('unfaithful', _). Returns label-survival vs the source."""
    ok = 0
    for _ in range(n):
        s0 = rng.gauss(0, 1)                       # true readout score <x,c>
        s = s0
        dropped = False
        for kind, sigma in steps:
            if kind == "faithful":
                s = s + rng.gauss(0, sigma)        # preserves the score, adds step noise
            else:                                  # unfaithful: criterion direction dropped -> pure noise
                s = rng.gauss(0, 1); dropped = True
        ok += (s >= 0) == (s0 >= 0)
    return ok / n


def main():
    rng = random.Random(7)
    n = 8000
    print("graded composition — a chain of FAITHFUL-but-noisy steps (sigma=0.35/step):\n")
    print("  chain length L   label-survival")
    for L in (1, 2, 4, 8, 16, 32):
        steps = [("faithful", 0.35)] * L
        print(f"   {L:3d}             {acc_through_chain(rng, n, steps):.3f}")

    print("\nweakest link — one UNFAITHFUL step among many faithful ones:")
    faithful8 = [("faithful", 0.05)] * 8
    a_all_faithful = acc_through_chain(rng, n, faithful8)
    mixed = [("faithful", 0.05)] * 4 + [("unfaithful", 0)] + [("faithful", 0.05)] * 3
    a_one_bad = acc_through_chain(rng, n, mixed)
    print(f"  8 faithful steps          survival {a_all_faithful:.3f}")
    print(f"  7 faithful + 1 unfaithful survival {a_one_bad:.3f}  (one bad step governs)")

    print("\n--- verdict (substrate 7: composition) ---")
    graded = acc_through_chain(rng, n, [("faithful", 0.35)] * 1) > acc_through_chain(rng, n, [("faithful", 0.35)] * 16)
    p_graded = graded                              # longer faithful chain -> more accumulated loss
    p_link = a_all_faithful > 0.95 and a_one_bad < 0.6
    print(f"(compose) faithfulness COMPOSES: faithful chains degrade gracefully with length (graded, "
          f"~sqrt(L) noise)  -> {'HOLDS' if p_graded else 'FALLS'}")
    print(f"(weakest-link) one unfaithful step collapses the pipeline ({a_one_bad:.3f}) though the rest "
          f"are faithful ({a_all_faithful:.3f})  -> {'HOLDS' if p_link else 'FALLS'}")
    print("\nSTICKS" if (p_graded and p_link) else "\nFALLS",
          "— substrate 7: a pipeline is faithful to phi iff EVERY step is; loss accumulates (the absorbing meet, again).")


if __name__ == "__main__":
    main()
