"""Experiment 1 — stand up the transpile-conservation principle (and try to break it).

HYPOTHESIS (falsifiable): a transform across a substrate can be arbitrarily lossy in BITS yet
conserve the CRITERION-RELEVANT INVARIANT. The conserved quantity is faithfulness to the criterion,
not bit-fidelity; and faithfulness is NOT certifiable from inside the substrate (internal confidence
is blind to it) — only an external witness certifies it.

Setup. Points x in R^d. A hidden criterion direction c (the criterion lives OUTSIDE the substrate).
The invariant I = sign(<x,c>) (linear) — and a NONLINEAR invariant I2 to find where the principle bends.
Transforms = orthonormal projections to a k-dim subspace (a lossy substrate conversion, d->k):
  reversible      : full d-dim basis (k=d) — lossless control.
  faithful_lossy  : k-subspace that CONTAINS c (keeps the criterion direction, discards the rest).
  unfaithful_lossy: k-subspace ORTHOGONAL to c (same bit-loss, discards exactly the criterion).
  random_lossy    : a random k-subspace (partial overlap with c).
Metrics per transform:
  bits_kept      = k/d                         (the substrate's bit budget)
  internal_energy= mean ||proj(x)||^2/||x||^2  (a WITHIN-substrate confidence signal)
  faithfulness   = ||proj(c)|| in [0,1]        (EXTERNAL: how much of the criterion survives)
  invariant_acc  = fraction sign(<proj(x),c>) == sign(<x,c>)   (EXTERNAL witness: did I survive?)

FALSIFIERS: (a) if invariant_acc tracks bits_kept/internal_energy (then no lossy-but-faithful);
(b) if internal_energy distinguishes faithful from unfaithful (then no external witness needed).

Stdlib only, seeded, deterministic. No numpy — pure Python lists.
"""
from __future__ import annotations
import math, random

D, N, K = 48, 300, 6     # 48 -> 6 dims: 8x lossy substrate


def dot(a, b): return sum(x * y for x, y in zip(a, b))
def norm(a): return math.sqrt(dot(a, a))
def scale(a, s): return [x * s for x in a]
def sub(a, b): return [x - y for x, y in zip(a, b)]
def add(a, b): return [x + y for x, y in zip(a, b)]


def unit(a):
    n = norm(a)
    return scale(a, 1.0 / n) if n > 1e-12 else a


def gram_schmidt(vecs):
    """Orthonormalize a list of vectors; drop near-zero residuals."""
    basis = []
    for v in vecs:
        w = list(v)
        for b in basis:
            w = sub(w, scale(b, dot(w, b)))
        if norm(w) > 1e-9:
            basis.append(unit(w))
    return basis


def project(x, basis):
    """Projection of x onto the span of an orthonormal basis."""
    out = [0.0] * len(x)
    for b in basis:
        out = add(out, scale(b, dot(x, b)))
    return out


def make_basis(kind, c, rng):
    rnd = [[rng.gauss(0, 1) for _ in range(D)] for _ in range(D)]
    if kind == "reversible":
        return gram_schmidt([c] + rnd)[:D]
    if kind == "faithful_lossy":
        return gram_schmidt([c] + rnd)[:K]                 # c is basis vector 0
    if kind == "unfaithful_lossy":
        # project c OUT of every random vector, then orthonormalize -> subspace orthogonal to c
        stripped = [sub(v, scale(c, dot(v, c))) for v in rnd]
        return gram_schmidt(stripped)[:K]
    if kind == "random_lossy":
        return gram_schmidt(rnd)[:K]
    raise ValueError(kind)


def evaluate(basis, X, c, c2):
    eng = fa = lin = nonlin = 0.0
    pc = project(c, basis)
    faithfulness = norm(pc)                                 # ||proj(c)||, external
    for x in X:
        px = project(x, basis)
        nx = norm(x)
        eng += (norm(px) ** 2) / (nx * nx + 1e-12)
        # linear invariant I = sign(<x,c>); recovered score = <proj(x), c>
        lin += (1.0 if (dot(px, c) >= 0) == (dot(x, c) >= 0) else 0.0)
        # nonlinear invariant I2 = sign(<x,c>*<x,c2> ) — needs BOTH directions to survive
        true2 = (dot(x, c) * dot(x, c2)) >= 0
        rec2 = (dot(px, c) * dot(px, c2)) >= 0
        nonlin += (1.0 if rec2 == true2 else 0.0)
    n = len(X)
    return {"energy": eng / n, "faithfulness": faithfulness,
            "lin_acc": lin / n, "nonlin_acc": nonlin / n}


def main():
    rng = random.Random(7)
    c = unit([rng.gauss(0, 1) for _ in range(D)])
    c2 = unit(sub([rng.gauss(0, 1) for _ in range(D)], scale(c, 0)))  # second criterion dir
    X = [[rng.gauss(0, 1) for _ in range(D)] for _ in range(N)]
    print(f"d={D} -> k={K} ({D//K}x lossy)  n={N}   criterion c lives OUTSIDE the substrate\n")
    print("transform          bits_kept  internal_energy  faithfulness(ext)  linI_acc  nonlinI_acc")
    rows = {}
    for kind in ("reversible", "faithful_lossy", "unfaithful_lossy", "random_lossy"):
        b = make_basis(kind, c, random.Random(100))
        m = evaluate(b, X, c, c2)
        rows[kind] = m
        bits = len(b) / D
        print(f"  {kind:17s}  {bits:5.2f}      {m['energy']:6.3f}          "
              f"{m['faithfulness']:5.3f}            {m['lin_acc']:5.3f}     {m['nonlin_acc']:5.3f}")

    f, u = rows["faithful_lossy"], rows["unfaithful_lossy"]
    print("\n--- verdict on the falsifiers ---")
    # (1) lossy-but-faithful possible? faithful keeps I at the SAME bit-loss unfaithful destroys it.
    same_bits = True  # both k=K by construction
    p1 = f["lin_acc"] > 0.9 and u["lin_acc"] < 0.65 and same_bits
    print(f"(1) lossy-but-faithful (bit-loss != invariant-loss): "
          f"faithful linI={f['lin_acc']:.2f} vs unfaithful linI={u['lin_acc']:.2f} at equal bits"
          f"  -> {'HOLDS' if p1 else 'FALLS'}")
    # (2) internal confidence blind to faithfulness? energies ~equal but I-survival differs.
    energy_gap = abs(f["energy"] - u["energy"])
    p2 = energy_gap < 0.05 and (f["lin_acc"] - u["lin_acc"]) > 0.3
    print(f"(2) internal confidence cannot certify (needs external witness): "
          f"energy gap {energy_gap:.3f} (~0) while I-survival gap {f['lin_acc']-u['lin_acc']:.2f}"
          f"  -> {'HOLDS' if p2 else 'FALLS'}")
    # (3) where it BENDS: does keeping c alone preserve the NONLINEAR invariant?
    print(f"(3) scope/bend: faithful_lossy preserves linI={f['lin_acc']:.2f} but "
          f"nonlinI={f['nonlin_acc']:.2f} — faithfulness is INVARIANT-SPECIFIC "
          f"({'keeps c suffices for linear, not nonlinear' if f['nonlin_acc'] < 0.9 else 'holds for both'})")
    print("\nSTICKS" if (p1 and p2) else "\nFALLS", "— on the core claim (substrate 1 of N: linear/Gaussian toy).")
    print("Honest bound: one synthetic substrate. Next: phash, color-quantize, context-pack (real organs).")


if __name__ == "__main__":
    main()
