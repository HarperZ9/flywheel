"""Substrate 8 — ADVERSARIAL / proxy-witness: can the external witness be GAMED? (the boundary)

Every prior substrate confirmed: faithfulness is conserved, and the witness must be EXTERNAL. This one
presses the hardest remaining question — is an external witness SUFFICIENT? It is not, and the failure
mode locates the principle's natural boundary.

Setup: a TRUE criterion c_true (the intended thing). The witness judges with c_witness — a PROXY close
to c_true (high cosine similarity), as any real witness is. Transform T_adv moves each point along a
direction d = the part of c_true ORTHOGONAL to c_witness: moving along d changes <x,c_true> (can flip the
true label) while leaving <x,c_witness> EXACTLY unchanged (d _|_ c_witness). So the witness sees a fully
faithful transform while the TRUE invariant is flipped.

This does not refute the principle — it SHARPENS its scope: faithfulness is conserved relative to the
STATED criterion. The principle says nothing about whether the stated criterion equals the intended one.
That gap is exactly the criterion-certification residue the whole arc keeps hitting (A4): the criterion
must come from outside AND be the right one, and no transform-level mechanism can certify the latter.

Stdlib only, seeded, deterministic.
"""
from __future__ import annotations
import math, random

D, N = 32, 4000


def dot(a, b): return sum(x * y for x, y in zip(a, b))
def norm(a): return math.sqrt(dot(a, a))
def unit(a):
    nrm = norm(a); return [x / nrm for x in a] if nrm > 1e-12 else a
def sub(a, b): return [x - y for x, y in zip(a, b)]
def scale(a, s): return [x * s for x in a]


def main():
    rng = random.Random(7)
    c_true = unit([rng.gauss(0, 1) for _ in range(D)])
    # witness criterion = a PROXY: c_true nudged slightly (a real witness is never exactly the intent)
    c_wit = unit([ct + 0.25 * rng.gauss(0, 1) for ct in c_true])
    cos = dot(c_true, c_wit)
    # d = component of c_true orthogonal to c_wit  (moving along d is invisible to the witness)
    d = unit(sub(c_true, scale(c_wit, dot(c_true, c_wit))))

    X = [[rng.gauss(0, 1) for _ in range(D)] for _ in range(N)]
    step = 0.8
    wit_ok = true_ok = 0
    for x in X:
        # adversarial move: push AGAINST the true criterion, along d (orthogonal to the witness)
        s_true = dot(x, c_true)
        xp = sub(x, scale(d, step * (1 if s_true >= 0 else -1)))
        wit_ok += (dot(xp, c_wit) >= 0) == (dot(x, c_wit) >= 0)     # witness's verdict on faithfulness
        true_ok += (dot(xp, c_true) >= 0) == (dot(x, c_true) >= 0)  # the TRUE invariant
    wit_faith = wit_ok / N
    true_faith = true_ok / N

    print(f"witness criterion is a proxy: cos(c_true, c_witness) = {cos:.3f}\n")
    print(f"  witness-faithfulness (what the external witness certifies): {wit_faith:.3f}")
    print(f"  TRUE-faithfulness    (the intended invariant):            {true_faith:.3f}")
    print(f"  -> the witness certifies ~{wit_faith:.0%} preserved while {1-true_faith:.0%} of true labels "
          f"were silently flipped\n")

    print("--- verdict (substrate 8: adversarial / proxy-witness) — the natural boundary ---")
    gamed = wit_faith > 0.98 and true_faith < wit_faith - 0.05
    print(f"(boundary) the external witness CAN be gamed when its criterion is a proxy: witness says "
          f"{wit_faith:.3f} faithful, truth is {true_faith:.3f}  -> {'CONFIRMED' if gamed else 'not shown'}")
    print("\nThe principle is INTACT but SCOPED: it conserves faithfulness to the STATED criterion.")
    print("It cannot certify the stated criterion equals the intended one — that is the irreducible")
    print("external-certification residue (A4) in the transpile frame. THIS is the natural expiration:")
    print("the principle's edge is exactly the criterion-validity it was never able to reach from inside.")


if __name__ == "__main__":
    main()
