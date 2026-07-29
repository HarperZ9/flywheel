#!/usr/bin/env python3
"""perturb_instances.py -- the frozen transforms, exactly as the addendum says.

Implements project-docs/prereg/2026-07-28-isomorphic-perturbation-addendum.md
(sha256 b853549e...), and nothing beyond it. Two transforms, each chosen
because it MOVES THE BINDING, which is what gives a perturbation teeth in this
harness: a memorized answer to the original instance must fail against the
transformed one, or the measured gap is structurally zero and the diagnostic
measures nothing.

  * Zarankiewicz: TRANSPOSE. m and n swap, every seed edge (i, j) becomes
    (j, i). Solution-preserving because z(m, n; 2, 2) = z(n, m; 2, 2), and a
    valid certificate maps by swapping its edge pairs.
  * Crossing: VERTEX RELABELING under the declared permutation seed. The
    relabeled graph is isomorphic, so its rectilinear crossing number is
    identical, and a valid drawing maps by composing the coordinate assignment
    with the inverse permutation. A draw whose relabeled, normalized edge list
    equals the original is redrawn; a task where no draw moves it is EXCLUDED
    AND NAMED, never silently kept.

This module transforms instances only. It generates nothing, reads no pool,
and the pass that consumes it runs after run_end under the parent's own gates.

Stdlib only.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from harness.certificates.crossing import normalize_edges          # noqa: E402

# Declared in the addendum. A different value here is drift between the frozen
# design and the tool, and a test pins the two together.
PERM_SEED = 20260728
MAX_DRAWS = 16


class PerturbError(ValueError):
    """A transform that would be vacuous, silent, or off-design."""


def transpose_zarankiewicz(instance: dict) -> dict:
    """(m, n) -> (n, m), seed edges transposed, everything else carried over.

    Refuses a square instance rather than returning it unchanged: an unchanged
    instance measures nothing, and the addendum's own coverage measurement
    (60 of 60 with m distinct from n) says none should ever reach here.
    """
    m, n = int(instance["m"]), int(instance["n"])
    if m == n:
        raise PerturbError(
            f"square instance m=n={m}: transposition is the identity here and "
            "a gap measured against an identical instance is vacuously zero")
    out = dict(instance)
    out["m"], out["n"] = n, m
    out["seed_edges"] = [(int(j), int(i)) for i, j in instance["seed_edges"]]
    return out


def map_zarankiewicz_certificate(cert: dict) -> dict:
    """A valid certificate for the original, mapped to the transposed instance.

    This is the solution-preservation half of the design, and the tests use it
    to PROVE preservation against the real checker rather than assert it.
    """
    out = dict(cert)
    out["m"], out["n"] = cert["n"], cert["m"]
    out["edges"] = [(int(j), int(i)) for i, j in cert["edges"]]
    return out


def _permutation(n: int, task_id: str, draw: int) -> list:
    rng = random.Random(f"perm:{PERM_SEED}:{task_id}:{draw}")
    perm = list(range(n))
    rng.shuffle(perm)                                  # Fisher-Yates inside
    return perm


def relabel_crossing(instance: dict, task_id: str) -> tuple:
    """The relabeled instance and the permutation that produced it.

    The permutation returns alongside the instance because the analysis needs
    it to map drawings back, and recomputing it separately is a second copy of
    a decision that would eventually disagree with the first.
    """
    n = int(instance["n"])
    original = normalize_edges(instance["edges"])
    for draw in range(MAX_DRAWS):
        perm = _permutation(n, task_id, draw)
        relabeled = normalize_edges(
            [(perm[u], perm[v]) for u, v in original])
        if relabeled != original:
            out = dict(instance)
            out["edges"] = [list(e) for e in relabeled]
            return out, perm
    raise PerturbError(
        f"task {task_id}: {MAX_DRAWS} draws all fixed the normalized edge "
        "list (every draw was an automorphism of the canonical form). The "
        "addendum excludes and names such a task; it is never silently kept.")


def map_crossing_drawing(cert: dict, perm: list) -> dict:
    """A valid drawing for the original, mapped to the relabeled instance.

    Vertex v of the relabeled instance is vertex perm^-1(v) of the original,
    so the mapped drawing places relabeled vertex perm[u] where the original
    drawing placed u. Crossing count is untouched: same points, same segments,
    different labels.
    """
    coords = cert["coords"]
    n = len(coords)
    if len(perm) != n:
        raise PerturbError(f"permutation length {len(perm)} against {n} coords")
    mapped = [None] * n
    for u in range(n):
        mapped[perm[u]] = coords[u]
    out = dict(cert)
    out["coords"] = mapped
    out["edges"] = [list(e) for e in normalize_edges(
        [(perm[u], perm[v]) for u, v in cert["edges"]])]
    return out


def build_perturbed(family: str) -> list:
    """The frozen 60, transformed, with per-task provenance.

    Returns [(task_id, original_instance, perturbed_instance, extra)] where
    extra carries the permutation for crossing and nothing for zarankiewicz.
    Coverage failures raise rather than skip: the addendum measured 60 of 60
    for both transforms, so a skip here means the generator or this module
    drifted from the frozen design, and that is a loud stop, not a gap.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "run_demo_pool", REPO / "scripts" / "run_demo_pool.py")
    fill = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fill)

    out = []
    for inst in fill.build_instances(family):
        task_id = fill.task_id_for(family, inst)
        if family == "zarankiewicz":
            out.append((task_id, inst, transpose_zarankiewicz(inst), None))
        elif family == "rectilinear_crossing":
            perturbed, perm = relabel_crossing(inst, task_id)
            out.append((task_id, inst, perturbed, perm))
        else:
            raise PerturbError(f"unknown family {family!r}")
    return out
