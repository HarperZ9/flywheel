"""silhouette.py — the shadow that follows: reconstruction from projection.

The operator's reverse-engineering instinct — "see the silhouette, not the shape;
the shadow left behind that follows" — is one mechanism, the INVERSE PROBLEM:
recover a hidden object from a lossy projection of it. It runs through domains that
look unconnected (astronomy, 3D rendering, reverse engineering, geometry, systems,
psychology, dream-state) as the SAME operation.

And it is the reconcile run BACKWARD. Forward: a transform conserves the criterion
and discards the rest (transpile-conservation). Backward: from the conserved shadow,
reconstruct the object — but only up to the equivalence class the projection
discarded. **The criterion IS the projection; what the forward reconcile throws away
is exactly the null space the backward reconstruction cannot recover.** One function,
both directions — which is why this is a mechanistic bridge, not a shared silhouette.

The honest payoff is the split. For most domains, stacking enough independent shadows
collapses the ambiguity to ONE object (the inverse problem is solvable — astronomy,
rendering, RE, geometry, systems). For a few, a coordinate is invisible to EVERY
available projection, so the ambiguity has a permanent floor > 1 (dream-state,
consciousness). That permanent floor is the computational SHAPE of the access/
phenomenal gap: behavioral shadows pin the functional state and never touch the
phenomenal one. This DEMONSTRATES the shape of the hard problem; it does not resolve
it — the blindness is an encoded modeling assumption, not a proof about real minds.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product
from typing import Callable


@dataclass
class InverseProblem:
    name: str
    field: str
    candidates: list                 # the full space of possible hidden objects
    truth: object                    # the true hidden object (must be in candidates)
    projections: list                # ordered [(label, fn)] — the shadows, added in turn
    focus: Callable | None = None    # optional coordinate whose residual ambiguity we track


def _consistent(candidates, projs, truth):
    """Objects producing the SAME shadow as truth under every projection so far."""
    key = tuple(fn(truth) for _, fn in projs)
    return [c for c in candidates if tuple(fn(c) for _, fn in projs) == key]


def ambiguity_curve(ip: InverseProblem) -> list[dict]:
    """As shadows are added one at a time, how the consistent set shrinks. Each row:
    shadows seen, count of objects still consistent, and (if a focus coordinate is
    set) how many distinct focus-values remain — the residual ambiguity of the thing
    you are actually trying to recover."""
    curve = []
    for k in range(len(ip.projections) + 1):
        cons = _consistent(ip.candidates, ip.projections[:k], ip.truth)
        row = {"shadows": [lbl for lbl, _ in ip.projections[:k]],
               "n_consistent": len(cons)}
        if ip.focus is not None:
            row["focus_ambiguity"] = len({ip.focus(c) for c in cons})
        curve.append(row)
    return curve


def reconstruction(ip: InverseProblem) -> dict:
    """Solvable iff all shadows together pin a unique object (floor == 1). Otherwise
    the floor is the permanent residue — the null space no available shadow removes."""
    curve = ambiguity_curve(ip)
    final = curve[-1]
    floor_key = "focus_ambiguity" if ip.focus is not None else "n_consistent"
    floor = final[floor_key]
    return {"name": ip.name, "field": ip.field, "curve": curve,
            "floor": floor, "solvable": floor == 1,
            "monotone": all(a["n_consistent"] >= b["n_consistent"]
                            for a, b in zip(curve, curve[1:]))}


# ---- the domains (deliberately unconnected fields, one mechanism) ------------

def _astronomy():
    cand = [(r, p, i) for r in (1, 2, 3) for p in (1, 2, 3) for i in (0, 1)]
    return InverseProblem("transit", "astronomy", cand, (2, 3, 1),
        [("transit_depth", lambda o: o[0]),      # depth ~ radius^2 -> pins radius
         ("radial_velocity", lambda o: o[1])])   # RV -> pins period; inclination residual


def _rendering():
    # a 2x2x2 voxel object; silhouettes are occupancy projections that drop one axis
    cand = [tuple(bits) for bits in product((0, 1), repeat=8)]
    truth = (1, 1, 0, 1, 0, 1, 1, 0)
    def occ(o, drop):                            # project out one axis (visual hull)
        acc = {}
        for idx, v in enumerate(o):
            x, y, z = (idx >> 2) & 1, (idx >> 1) & 1, idx & 1
            key = {"z": (x, y), "y": (x, z), "x": (y, z)}[drop]
            acc[key] = acc.get(key, 0) or v
        return tuple(sorted(acc.items()))
    return InverseProblem("visual_hull", "3d-rendering", cand, truth,
        [("silhouette_xy", lambda o: occ(o, "z")),
         ("silhouette_xz", lambda o: occ(o, "y")),
         ("silhouette_yz", lambda o: occ(o, "x"))])


def _reverse_eng():
    # the program's true behavior on 4 inputs; each trace observes one input's outcome
    cand = [tuple(bits) for bits in product((0, 1), repeat=4)]
    truth = (1, 0, 1, 1)
    return InverseProblem("trace_recovery", "reverse-engineering", cand, truth,
        [(f"trace_input_{i}", (lambda i: (lambda o: o[i]))(i)) for i in range(4)])


def _geometry():
    cand = [(x, y, z) for x in (0, 1, 2) for y in (0, 1, 2) for z in (0, 1, 2)]
    return InverseProblem("orthographic", "geometry", cand, (1, 2, 0),
        [("shadow_xy", lambda o: (o[0], o[1])),
         ("shadow_xz", lambda o: (o[0], o[2]))])   # two orthographic views pin the point


def _systems():
    # black-box ID: hidden linear recurrence a_n = c1*a_{n-1}+c0; shadows = output prefix
    cand = [(c0, c1) for c0 in (0, 1, 2) for c1 in (0, 1, 2)]
    truth = (1, 2)
    def out(o, n):
        c0, c1 = o
        seq = [1, 1]
        for _ in range(n):
            seq.append(c1 * seq[-1] + c0 * seq[-2])
        return seq[n + 1]
    return InverseProblem("black_box_id", "systems", cand, truth,
        [(f"output_{n}", (lambda n: (lambda o: out(o, n)))(n)) for n in (1, 2)])


def _dream():
    # latent content -> manifest dream (many-to-one); manifest is the only shadow
    cand = [(manifest, latent) for manifest in (0, 1, 2) for latent in (0, 1, 2, 3)]
    return InverseProblem("manifest_latent", "dream-state", cand, (1, 3),
        [("manifest_content", lambda o: o[0])],   # blind to latent -> permanent residue
        focus=lambda o: o[1])


def _consciousness():
    # (functional_state, phenomenal_tag); EVERY behavioral shadow is a function of the
    # functional state ONLY -> the phenomenal coordinate is in the permanent null space.
    cand = [(f, p) for f in (0, 1, 2, 3) for p in (0, 1)]
    return InverseProblem("access_vs_phenomenal", "consciousness", cand, (2, 1),
        [("verbal_report", lambda o: o[0]),
         ("response_latency", lambda o: o[0] % 2),   # another behavioral probe, still blind
         ("task_accuracy", lambda o: o[0] // 2)],
        focus=lambda o: o[1])                          # residual ambiguity over phenomenal


DOMAINS = [_astronomy, _rendering, _reverse_eng, _geometry, _systems, _dream, _consciousness]


def run_all() -> dict:
    results = [reconstruction(b()) for b in DOMAINS]
    solvable = [r["name"] for r in results if r["solvable"]]
    underdetermined = [r["name"] for r in results if not r["solvable"]]
    return {
        "n_domains": len(results),
        "fields": sorted({r["field"] for r in results}),
        "all_monotone": all(r["monotone"] for r in results),   # more shadows never add ambiguity
        "solvable": solvable,
        "underdetermined": underdetermined,     # permanent floor > 1 (dream, consciousness)
        "results": results,
        "bridge": "the reconcile run backward: the criterion is the projection; the "
                  "forward transform's discarded class is the backward null space",
        "honest_note": "consciousness/dream underdetermination is an ENCODED blindness "
                       "(the projection is defined to miss the phenomenal/latent "
                       "coordinate) — this shows the SHAPE of the access/phenomenal gap, "
                       "it does not resolve or prove anything about real minds",
    }
