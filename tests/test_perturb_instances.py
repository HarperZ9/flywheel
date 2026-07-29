"""The frozen transforms, proved against the real checkers.

Two properties carry the whole design, and both are PROVED here rather than
asserted: solution preservation (a valid answer to the original, mapped, passes
against the transformed instance) and teeth (the UNMAPPED original answer fails
against the transformed instance). A transform with the first property but not
the second is the vacuity the addendum exists to correct.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

_spec = importlib.util.spec_from_file_location(
    "perturb_instances", ROOT / "scripts" / "perturb_instances.py")
pi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pi)

import json                                                          # noqa: E402

from harness.certificates.crossing import (                          # noqa: E402
    CrossingOracle, count_crossings, normalize_edges)
from harness.certificates.crossing_generator import crossing_instance  # noqa: E402
from harness.certificates.generators import zarankiewicz_instance    # noqa: E402
from harness.certificates.zarankiewicz import ZarankiewiczOracle     # noqa: E402
from harness.verdict import Verdict                                  # noqa: E402


def _z_cert(instance) -> dict:
    """The instance's own seed witness as a certificate: a star is K_{2,2}-free
    (a K_{2,2} needs two rows, a star uses one), so this is VALID for the
    original instance, which the first test proves rather than assumes."""
    edges = [list(e) for e in instance["seed_edges"]]
    return {"m": instance["m"], "n": instance["n"], "s": instance["s"],
            "t": instance["t"], "edges": edges, "edge_count": len(edges)}


def _drawing(instance) -> dict:
    """An honest drawing: vertices on a convex curve (general position), with
    the crossing count computed by the checker's own counter, so the claim is
    true by construction."""
    n = int(instance["n"])
    coords = [[i, i * i] for i in range(1, n + 1)]      # strictly convex
    edges = [list(e) for e in normalize_edges(instance["edges"])]
    crossings = count_crossings([tuple(c) for c in coords],
                                normalize_edges(instance["edges"]))
    return {"n": n, "coords": coords, "edges": edges, "crossings": crossings}


# --- zarankiewicz: transpose ------------------------------------------------

def test_transpose_preserves_a_valid_certificate():
    oracle = ZarankiewiczOracle()
    inst = zarankiewicz_instance(seed=0, difficulty=3)
    cert = _z_cert(inst)
    assert oracle.verify(json.dumps(cert), task=inst).verdict_ is Verdict.PASS
    mapped = pi.map_zarankiewicz_certificate(cert)
    perturbed = pi.transpose_zarankiewicz(inst)
    assert oracle.verify(json.dumps(mapped),
                         task=perturbed).verdict_ is Verdict.PASS


def test_transpose_has_teeth():
    """The vacuity the addendum corrects: the UNMAPPED original answer must
    FAIL against the transformed instance, or a memorizer scores a zero gap."""
    oracle = ZarankiewiczOracle()
    inst = zarankiewicz_instance(seed=0, difficulty=3)
    cert = _z_cert(inst)
    perturbed = pi.transpose_zarankiewicz(inst)
    r = oracle.verify(json.dumps(cert), task=perturbed)
    assert r.verdict_ is Verdict.FAIL
    assert "does not answer the instance" in r.stdout_excerpt


def test_transpose_is_an_involution_on_the_bound_fields():
    inst = zarankiewicz_instance(seed=7, difficulty=2)
    back = pi.transpose_zarankiewicz(pi.transpose_zarankiewicz(inst))
    for key in ("m", "n", "s", "t"):
        assert back[key] == inst[key]
    assert [tuple(e) for e in back["seed_edges"]] == \
        [tuple(e) for e in inst["seed_edges"]]


def test_a_square_instance_is_refused_not_passed_through():
    inst = dict(zarankiewicz_instance(seed=0, difficulty=1))
    inst["n"] = inst["m"]
    with pytest.raises(pi.PerturbError):
        pi.transpose_zarankiewicz(inst)


# --- crossing: vertex relabeling --------------------------------------------

def test_relabeling_preserves_a_valid_drawing():
    oracle = CrossingOracle()
    inst = crossing_instance(seed=0, difficulty=1)
    cert = _drawing(inst)
    assert oracle.verify(json.dumps(cert), task=inst).verdict_ is Verdict.PASS
    perturbed, perm = pi.relabel_crossing(inst, "t0")
    mapped = pi.map_crossing_drawing(cert, perm)
    r = oracle.verify(json.dumps(mapped), task=perturbed)
    assert r.verdict_ is Verdict.PASS
    # Same points, same segments, different labels: the count cannot move.
    assert mapped["crossings"] == cert["crossings"]
    # And the GEOMETRY is identical, not merely count-coincident: the correct
    # mapping direction reproduces the exact segment set, while the inverse
    # direction produces a doubly-permuted drawing whose count can agree by
    # luck on a small instance. Counts lie; segments do not.
    def segments(c):
        pts = [tuple(p) for p in c["coords"]]
        return {frozenset((pts[u], pts[v]))
                for u, v in normalize_edges(c["edges"])}
    assert segments(mapped) == segments(cert)


def test_relabeling_has_teeth():
    oracle = CrossingOracle()
    inst = crossing_instance(seed=0, difficulty=1)
    cert = _drawing(inst)
    perturbed, _ = pi.relabel_crossing(inst, "t0")
    r = oracle.verify(json.dumps(cert), task=perturbed)
    assert r.verdict_ is Verdict.FAIL
    assert "does not answer the instance" in r.stdout_excerpt


def test_relabeling_is_deterministic_per_task_id():
    inst = crossing_instance(seed=3, difficulty=2)
    a, perm_a = pi.relabel_crossing(inst, "task-x")
    b, perm_b = pi.relabel_crossing(inst, "task-x")
    c, perm_c = pi.relabel_crossing(inst, "task-y")
    assert perm_a == perm_b and a == b
    assert perm_c != perm_a or c != a


def test_an_all_automorphism_task_is_excluded_and_named():
    """K_n is fixed by every permutation, so no draw can move its edge list.
    The addendum excludes and names such a task rather than keeping it."""
    n = 5
    kn = {"n": n, "edges": [[u, v] for u in range(n) for v in range(u + 1, n)]}
    with pytest.raises(pi.PerturbError) as e:
        pi.relabel_crossing(kn, "kn-task")
    assert "kn-task" in str(e.value)


# --- the frozen set, end to end ---------------------------------------------

def test_the_full_frozen_set_transforms_with_no_exclusions():
    """The addendum's own coverage measurement, re-run as a test: 60 of 60 for
    both families. A skip or a raise here means the generator or the transforms
    drifted from the frozen design."""
    for family in ("zarankiewicz", "rectilinear_crossing"):
        rows = pi.build_perturbed(family)
        assert len(rows) == 60
        for task_id, original, perturbed, extra in rows:
            assert perturbed != original


def test_task_ids_are_preserved_so_pools_pair():
    rows = pi.build_perturbed("zarankiewicz")
    assert rows[0][0].startswith("zarankiewicz.seed00.d1")


def test_the_declared_seed_matches_the_frozen_addendum():
    """The addendum names the permutation seed; this module carries it. Drift
    between the two would quietly run a different experiment than the one
    frozen, so the pair is pinned here."""
    assert pi.PERM_SEED == 20260728
    doc = (ROOT / "project-docs" / "prereg"
           / "2026-07-28-isomorphic-perturbation-addendum.md").read_text(
               encoding="utf-8")
    assert str(pi.PERM_SEED) in doc
    assert "transpose" in doc.lower() and "relabel" in doc.lower()
