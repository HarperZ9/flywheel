"""Tests for harness.epistemic_vorticity."""

from __future__ import annotations

from harness.epistemic_vorticity import (
    EpistemicVorticityMonitor,
    audit_definition_integrity,
    build_expander_witness_graph,
)


def test_vorticity_monitor_distinguishes_grounded_laminar_from_unforced_blowup() -> None:
    grounded = EpistemicVorticityMonitor(turbulent_threshold=1.5, blowup_threshold=3.0)
    for _ in range(5):
        t = grounded.record_turn(
            self_reference_ratio=0.15,
            claim_confidence=0.70,
            novel_evidence_ratio=0.85,
        )
        assert t.regime == "LAMINAR"
    assert not grounded.should_vent_or_rest()

    unforced = EpistemicVorticityMonitor(turbulent_threshold=1.5, blowup_threshold=3.0)
    regimes = []
    for _ in range(3):
        t = unforced.record_turn(
            self_reference_ratio=0.95,
            claim_confidence=0.95,
            novel_evidence_ratio=0.05,
        )
        regimes.append(t.regime)
    assert regimes[-1] == "BLOWUP_RISK"
    assert unforced.should_vent_or_rest()
    assert len(unforced.summary()["digest"]) == 64


def test_definition_integrity_auditor_catches_planted_escape_hatches() -> None:
    clean_modules = {
        "kernel.py": "def verify(x: int) -> bool:\n    return x * x >= 0\n",
        "proof.lean": "theorem nonneg (n : Nat) : 0 <= n := Nat.zero_le n\n",
    }
    clean = audit_definition_integrity(clean_modules, required_symbols=["verify", "nonneg"])
    assert clean["verdict"] == "CLEAN"
    assert clean["finding_count"] == 0

    planted = {
        "proof.lean": "axiom magic_shortcut : False\ntheorem fake : False := by sorry\n",
        "test_fake.py": "@pytest.mark.skip\ndef test_x():\n    assert True\n",
    }
    drift = audit_definition_integrity(planted, required_symbols=["verify"])
    assert drift["verdict"] == "DRIFT"
    rules = {f["rule"] for f in drift["findings"]}
    assert {"lean_sorry", "lean_custom_axiom", "python_trivial_assert", "python_unconditional_skip"} <= rules
    assert drift["missing_symbols"] == ["verify"]


def test_expander_witness_graph_is_deterministic_and_beats_plain_ring_gap() -> None:
    nodes = [f"agent-{i:02d}" for i in range(16)]
    ring = build_expander_witness_graph(nodes, degree=2)
    mesh = build_expander_witness_graph(nodes, degree=4)
    mesh_again = build_expander_witness_graph(nodes, degree=4)

    assert mesh["digest"] == mesh_again["digest"]
    assert mesh["min_degree"] >= 4
    assert mesh["spectral_gap"] > ring["spectral_gap"]
