"""Substrate 3 — scalar quantization with a threshold invariant (with a lossiness SWEEP).

A third, mechanically-independent substrate (no projections, no images): a continuous value x in
[0,1] quantized to k levels (~log2 k bits — arbitrarily lossy as k shrinks). The criterion-relevant
invariant is a DECISION: I_t(x) = sign(x - t) for a threshold t. Faithfulness here is concrete and
visual: does a bin EDGE sit on the threshold?
  aligned    quantization: a bin edge falls on t  -> every point keeps its side of t (faithful)
  misaligned quantization: t falls at a bin CENTER -> points within half a bin of t flip (lossy)
Both have the SAME k (same bit budget) and the SAME quantization residual (internal confidence) —
only alignment to the EXTERNAL threshold decides faithfulness.

CLAIMS (each can fall), swept over k = 2,4,8,16,32:
 (1) lossy-but-faithful: aligned preserves I_t at tiny k; misaligned (same k) loses points near t.
 (2) internal blindness: residual (mean |x-q(x)|) is identical for aligned/misaligned; only the
     external threshold check separates them.
 (3) criterion-relativity: a quantization aligned to threshold A is faithful to A but lossy to a
     nearby threshold B (which lands at a bin center) — same transform, opposite faithfulness.

Stdlib only, deterministic.
"""
from __future__ import annotations
import random


def quantize(x, k, half_offset=False):
    """k uniform bins on [0,1]; return the bin center. half_offset shifts edges by half a bin,
    moving t=0.5 from a bin EDGE (aligned) to a bin CENTER (misaligned)."""
    w = 1.0 / k
    if not half_offset:
        i = min(int(x * k), k - 1)              # edges at i/k  -> 0.5 is an edge for even k
        return (i + 0.5) * w
    shifted = x + w / 2                          # edges at (i-0.5)/k -> 0.5 is a bin center
    i = min(int(shifted * k), k)
    return i * w - w / 2 if 0 <= i * w - w / 2 <= 1 else max(0.0, min(1.0, i * w - w / 2))


def survival(xs, k, t, half_offset):
    ok = sum(1 for x in xs if ((quantize(x, k, half_offset) - t) >= 0) == ((x - t) >= 0))
    return ok / len(xs)


def residual(xs, k, half_offset):
    return sum(abs(x - quantize(x, k, half_offset)) for x in xs) / len(xs)


def main():
    rng = random.Random(7)
    xs = [rng.random() for _ in range(20000)]
    t = 0.5
    print("threshold t=0.5.  aligned = bin edge on t; misaligned = t at bin center. lower bits = smaller k\n")
    print("  k    bits   aligned I-survival   misaligned I-survival   residual(aligned/misaligned)")
    lowk_ok = True   # lossy-but-faithful where it bites (low bit budgets)
    for k in (2, 4, 8, 16, 32):
        sa = survival(xs, k, t, False)
        sm = survival(xs, k, t, True)
        ra = residual(xs, k, False)
        rm = residual(xs, k, True)
        bits = round((k).bit_length() - 1, 2)
        print(f"  {k:3d}   {bits:4.1f}     {sa:.3f}                {sm:.3f}                 {ra:.4f}/{rm:.4f}")
        if k <= 8 and not (sa > 0.98 and sm < sa - 0.05):
            lowk_ok = False

    # The CORRECT internal-blindness test: ONE transform (aligned, k=4) carries ONE residual, yet its
    # faithfulness differs by criterion -> the internal statistic cannot encode the (external) criterion.
    k = 4
    w = 1.0 / k
    r_one = residual(xs, k, False)                # the single internal statistic of this transform
    sA = survival(xs, k, 0.5, False)              # faithful to threshold A (a bin edge)
    sB = survival(xs, k, 0.5 + w / 2, False)      # lossy to threshold B (a bin center) — SAME transform
    p1 = lowk_ok
    p2 = (sA - sB) > 0.05                          # same residual r_one, different survival by criterion
    p3 = sA > 0.98 and sB < sA - 0.05

    print("\n--- verdict on the falsifiers (substrate 3: scalar quantization) ---")
    print(f"(1) lossy-but-faithful where bits bite (k<=8): aligned ~1.0 vs misaligned clearly lower "
          f"at equal bits  -> {'HOLDS' if p1 else 'FALLS'}  (gap shrinks as k grows, as expected)")
    print(f"(2) internal blindness: ONE transform (k=4, residual {r_one:.4f}) is faithful to t=0.5 "
          f"({sA:.3f}) and lossy to t={0.5+w/2:.3f} ({sB:.3f}) — identical internal stat, different "
          f"faithfulness  -> {'HOLDS' if p2 else 'FALLS'}")
    print(f"(3) criterion-relativity: same transform, faithful to A ({sA:.3f}) / lossy to B ({sB:.3f})"
          f"  -> {'HOLDS' if p3 else 'FALLS'}")
    print("\nSTICKS" if (p1 and p2 and p3) else "\nFALLS", "— substrate 3 (scalar quantization).")


if __name__ == "__main__":
    main()
