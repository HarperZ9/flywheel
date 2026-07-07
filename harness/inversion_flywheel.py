"""inversion_flywheel.py — the active inverse loop: the reconstruction picks the next shadow.

The whole map, read as one object. Forward: transpile-conservation is a PROJECTION
(keep the criterion, discard the rest). Backward: silhouette RECONSTRUCTS up to the
discarded null space. The FLYWHEEL is the third piece that makes it compound: instead
of passively stacking whatever shadows arrive, the current reconstruction CHOOSES the
next shadow to maximize disambiguation — cycle n's posterior selects cycle n+1's
measurement. That is active inference / Bayesian optimal experiment design (Lindley),
here self-directed = "organic".

Two honest bounds, both tested:
  1. ACCELERATION (real, empirical): greedy information-gain ordering reaches the floor
     in strictly FEWER shadows than a passive order that wastes a cycle on a redundant
     shadow. The loop's self-direction skips the shadow that would tell it nothing.
  2. FLOOR-PRESERVATION (structural, near-definitional — and stated as such): reordering
     a fixed set of measurements cannot change their full intersection, so the active
     loop reaches the SAME permanent floor as passive on the underdetermined domains
     (consciousness/dream). The flywheel spins faster over what is recoverable; it
     manufactures NO access to the null space. Same shape as the amortization ceiling:
     the power and the limit are one fact.

Not a new law — active learning is textbook. The contribution is the composition: the
reconcile's own backward direction driven as a self-directed compounding loop, with the
conservation floor proven to hold against it.
"""
from __future__ import annotations

from .silhouette import InverseProblem, DOMAINS, _consistent


def _focus_metric(ip: InverseProblem):
    return ip.focus if ip.focus is not None else (lambda c: c)


def _ambiguity(ip: InverseProblem, projs) -> int:
    m = _focus_metric(ip)
    return len({m(c) for c in _consistent(ip.candidates, projs, ip.truth)})


def active_curve(ip: InverseProblem) -> list[int]:
    """Greedy: at each step pick the unused projection that splits the CURRENT
    consistent set into the most groups (max myopic information gain — needs no
    knowledge of truth beyond its observed shadows)."""
    used, remaining = [], list(ip.projections)
    curve = [_ambiguity(ip, [])]
    while remaining:
        cons = _consistent(ip.candidates, used, ip.truth)
        best = max(remaining, key=lambda p: len({p[1](c) for c in cons}))
        used.append(best)
        remaining.remove(best)
        curve.append(_ambiguity(ip, used))
    return curve


def passive_curve(ip: InverseProblem) -> list[int]:
    """Shadows applied in the order they happen to arrive (the given order)."""
    return [_ambiguity(ip, ip.projections[:k]) for k in range(len(ip.projections) + 1)]


def shadows_to_floor(curve: list[int]) -> int:
    floor = curve[-1]
    return next(i for i, v in enumerate(curve) if v == floor)


# A domain where shadows DIFFER in informativeness (one arrives redundant), so the
# self-directed loop provably beats the passive order. Candidates 0..7, truth 5=101;
# the passive stream wastes cycle 2 on a duplicate of bit0.
def acceleration_demo() -> InverseProblem:
    def bit(i):
        return lambda x: (x >> i) & 1
    return InverseProblem(
        "bit_recovery", "active-inference", list(range(8)), 5,
        [("bit0", bit(0)), ("bit0_dup", bit(0)), ("bit1", bit(1)), ("bit2", bit(2))])


def run_acceleration() -> dict:
    ip = acceleration_demo()
    a, p = active_curve(ip), passive_curve(ip)
    return {"active_curve": a, "passive_curve": p,
            "active_to_floor": shadows_to_floor(a), "passive_to_floor": shadows_to_floor(p),
            "accelerated": shadows_to_floor(a) < shadows_to_floor(p),
            "same_floor": a[-1] == p[-1]}


def run_floor_preservation() -> dict:
    """Across every silhouette domain: the active loop reaches the SAME floor as
    passive. Structural (reordering a fixed measurement set can't change its full
    intersection) — which is EXACTLY why the flywheel cannot reach the null space."""
    per = []
    for build in DOMAINS:
        ip = build()
        a, p = active_curve(ip), passive_curve(ip)
        per.append({"name": ip.name, "field": ip.field,
                    "active_floor": a[-1], "passive_floor": p[-1],
                    "floor_preserved": a[-1] == p[-1],
                    "active_faster_or_equal": shadows_to_floor(a) <= shadows_to_floor(p)})
    return {"n": len(per),
            "all_floors_preserved": all(x["floor_preserved"] for x in per),
            "all_faster_or_equal": all(x["active_faster_or_equal"] for x in per),
            "per_domain": per,
            "note": "floor-preservation is structural (reorder can't change the full "
                    "intersection) — the flywheel accelerates recovery but reaches no "
                    "coordinate the measurement set never observes"}
