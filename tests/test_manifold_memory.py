"""Tests for Symmetry-Manifold Witnessed Memory (harness/manifold_memory.py)."""
from __future__ import annotations

import hashlib
import math

import pytest

from harness.manifold_memory import (
    CAPSULE_SCHEMA,
    MANIFOLD_CIRCULAR,
    MANIFOLD_LINEAR,
    MANIFOLD_RIPPLED_1D,
    MAX_SUMMARY_CHARS,
    VERDICT_DRIFT,
    VERDICT_MATCH,
    VERDICT_UNVERIFIABLE,
    ManifoldRecord,
    compile_memory_capsule,
    compute_capsule_sha256,
    embed_rippled_1d,
    manifold_distance,
    verify_capsule_provenance,
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_circular_manifold_wrap_around_geodesic_distance():
    near_zero = 0.05
    near_two_pi = 2.0 * math.pi - 0.05
    dist = manifold_distance(MANIFOLD_CIRCULAR, (near_zero,), (near_two_pi,))
    assert dist == pytest.approx(0.10, abs=1e-9)

    far = manifold_distance(MANIFOLD_CIRCULAR, (near_zero,), (math.pi + 0.05,))
    assert far == pytest.approx(math.pi, abs=1e-9)

    records = [
        ManifoldRecord("wrap-near", MANIFOLD_CIRCULAR, (near_two_pi,), "hue near 2pi", _sha("wrap-near")),
        ManifoldRecord("mid-arc", MANIFOLD_CIRCULAR, (1.0,), "hue at 1 rad", _sha("mid-arc")),
        ManifoldRecord("opposite", MANIFOLD_CIRCULAR, (math.pi,), "opposite hue", _sha("opposite")),
    ]
    capsule = compile_memory_capsule(records, MANIFOLD_CIRCULAR, (near_zero,))
    assert [s["record_id"] for s in capsule["slots"]] == ["wrap-near", "mid-arc", "opposite"]
    assert capsule["slots"][0]["distance"] == pytest.approx(0.10, abs=1e-9)


def test_rippled_1d_manifold_harmonic_curvature_and_ranking():
    assert embed_rippled_1d(0.0, 1.0) == (0.0, 1.0, 0.0)
    # Two points at equal arc-length delta from t=0, with same k=1.0, have identical distance;
    # a point one full period away (2*pi) aligns in harmonic phase (cos, sin) while differing in t.
    d_period = manifold_distance(MANIFOLD_RIPPLED_1D, (0.0, 1.0), (2.0 * math.pi, 1.0))
    assert d_period == pytest.approx(2.0 * math.pi, abs=1e-9)

    d_half = manifold_distance(MANIFOLD_RIPPLED_1D, (0.0, 1.0), (math.pi, 1.0))
    assert d_half == pytest.approx(math.hypot(math.pi, 2.0), abs=1e-9)

    records = [
        ManifoldRecord("v1", MANIFOLD_RIPPLED_1D, (1.0,), "release v1", _sha("v1")),
        ManifoldRecord("v2", MANIFOLD_RIPPLED_1D, (2.0,), "release v2", _sha("v2")),
        ManifoldRecord("v10", MANIFOLD_RIPPLED_1D, (10.0,), "release v10", _sha("v10")),
    ]
    capsule = compile_memory_capsule(records, MANIFOLD_RIPPLED_1D, (1.9,))
    assert [s["record_id"] for s in capsule["slots"]] == ["v2", "v1", "v10"]


def test_linear_manifold_euclidean_distance_and_weight_ranking():
    records = [
        ManifoldRecord("close-low", MANIFOLD_LINEAR, (1.0, 0.0), "close low weight", _sha("a"), weight=0.5),
        ManifoldRecord("mid-high", MANIFOLD_LINEAR, (2.0, 0.0), "mid high weight", _sha("b"), weight=3.0),
        ManifoldRecord("far", MANIFOLD_LINEAR, (10.0, 10.0), "far away", _sha("c"), weight=1.0),
        ManifoldRecord("wrong-manifold", MANIFOLD_CIRCULAR, (0.1,), "ignored", _sha("d"), weight=10.0),
    ]
    capsule = compile_memory_capsule(records, MANIFOLD_LINEAR, (0.0, 0.0))
    assert capsule["schema"] == CAPSULE_SCHEMA
    assert [s["record_id"] for s in capsule["slots"]] == ["mid-high", "close-low", "far"]


def test_fixed_16_slot_budget_and_deterministic_capsule_hash():
    records = [
        ManifoldRecord(
            record_id=f"rec-{i:02d}",
            manifold=MANIFOLD_LINEAR,
            coords=(float(i), 0.0),
            summary=f"entry {i} " + ("x" * 300),
            source_sha256=_sha(f"payload-{i}"),
            weight=1.0,
        )
        for i in range(25)
    ]
    cap_forward = compile_memory_capsule(records, MANIFOLD_LINEAR, (0.0, 0.0))
    cap_reversed = compile_memory_capsule(list(reversed(records)), MANIFOLD_LINEAR, (0.0, 0.0))

    assert cap_forward["slot_count"] == 16
    assert len(cap_forward["slots"]) == 16
    assert cap_forward["capsule_sha256"] == cap_reversed["capsule_sha256"]
    assert compute_capsule_sha256(cap_forward) == cap_forward["capsule_sha256"]
    assert all(len(slot["summary"]) <= MAX_SUMMARY_CHARS for slot in cap_forward["slots"])
    assert cap_forward["slots"][0]["record_id"] == "rec-00"
    assert cap_forward["slots"][-1]["record_id"] == "rec-15"


def test_verify_capsule_provenance_match_drift_and_unverifiable():
    records = [
        ManifoldRecord("r1", MANIFOLD_LINEAR, (0.0, 0.0), "alpha", _sha("alpha")),
        ManifoldRecord("r2", MANIFOLD_LINEAR, (1.0, 0.0), "beta", _sha("beta")),
    ]
    capsule = compile_memory_capsule(records, MANIFOLD_LINEAR, (0.0, 0.0))
    known = {"r1": _sha("alpha"), "r2": _sha("beta")}

    ok = verify_capsule_provenance(capsule, known)
    assert ok["verdict"] == VERDICT_MATCH
    assert ok["capsule_hash_valid"] is True
    assert ok["checked_slots"] == 2
    assert ok["mismatches"] == []
    assert ok["missing"] == []

    drifted_source = verify_capsule_provenance(capsule, {"r1": _sha("alpha"), "r2": _sha("tampered")})
    assert drifted_source["verdict"] == VERDICT_DRIFT
    assert drifted_source["mismatches"] == ["r2"]

    tampered_capsule = dict(capsule)
    tampered_capsule["capsule_sha256"] = "0" * 64
    drifted_hash = verify_capsule_provenance(tampered_capsule, known)
    assert drifted_hash["verdict"] == VERDICT_DRIFT
    assert drifted_hash["capsule_hash_valid"] is False

    partial = verify_capsule_provenance(capsule, {"r1": _sha("alpha")})
    assert partial["verdict"] == VERDICT_UNVERIFIABLE
    assert partial["missing"] == ["r2"]
