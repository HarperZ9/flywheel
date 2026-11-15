"""Tests for the extended plexus registry (learn, telos, flywheel-infra + probe)."""
from __future__ import annotations

from plexus.registry import builtin_manifests, probe_all, probe_lane


def test_builtin_manifests_count():
    """Should now have 10 manifests (8 prior + canon + relay)."""
    manifests = builtin_manifests()
    assert len(manifests) == 10


def test_learn_manifest_present():
    manifests = builtin_manifests()
    organs = [m.organ for m in manifests]
    assert "learn" in organs


def test_telos_manifest_present():
    manifests = builtin_manifests()
    organs = [m.organ for m in manifests]
    assert "telos" in organs


def test_flywheel_infra_manifest_present():
    manifests = builtin_manifests()
    organs = [m.organ for m in manifests]
    assert "flywheel-infra" in organs


def test_canon_manifest_present():
    manifests = builtin_manifests()
    organs = [m.organ for m in manifests]
    assert "canon" in organs


def test_relay_manifest_present():
    manifests = builtin_manifests()
    organs = [m.organ for m in manifests]
    assert "relay" in organs


def test_learn_manifest_emits():
    manifests = builtin_manifests()
    learn = next(m for m in manifests if m.organ == "learn")
    caps = [e.capability for e in learn.emits]
    assert "learn-receipt" in caps
    assert "learn.tutor-mastery/1" in caps


def test_flywheel_infra_emits():
    manifests = builtin_manifests()
    infra = next(m for m in manifests if m.organ == "flywheel-infra")
    caps = [e.capability for e in infra.emits]
    assert "flywheel.egress/1" in caps
    assert "flywheel.lesson/1" in caps
    assert "flywheel.tadr-classification/1" in caps


def test_flywheel_infra_consumes_actuation_outcome():
    """flywheel-infra consumes accountable-surface actuation outcomes for lessons."""
    manifests = builtin_manifests()
    infra = next(m for m in manifests if m.organ == "flywheel-infra")
    caps = [c.capability for c in infra.consumes]
    assert any("actuation-outcome" in c for c in caps)


def test_probe_unknown_lane():
    result = probe_lane("nonexistent", timeout=1)
    assert result["reachable"] is False
    assert "unknown lane" in result["error"] or "not available" in result["error"]


def test_probe_all_returns_list():
    results = probe_all(timeout=1)
    assert isinstance(results, list)
    assert len(results) > 0


def test_original_manifests_unchanged():
    """The original 5 manifests (gather, crucible, index, forum, mneme) still exist."""
    manifests = builtin_manifests()
    organs = [m.organ for m in manifests]
    for expected in ("gather", "crucible", "index", "forum", "mneme"):
        assert expected in organs
