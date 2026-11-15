# tests/test_cross_verifier_organ.py
from __future__ import annotations

from coherence_membrane.observation import Status
from coherence_membrane.organs.cross_verifier import CrossCheckVerifierOrgan
from coherence_membrane.propositional import And, Implies, Var


def _mp():
    A, B = Var("A"), Var("B")
    return Implies(And(A, Implies(A, B)), B)


def test_cross_organ_verifies_by_consensus():
    obs = CrossCheckVerifierOrgan().observe(_mp())[0]
    assert obs.status == Status.PASS
    assert obs.data["verdict"] == "verified"
    assert obs.data["oracle"] == "cross-check-v1"
    assert len(obs.provenance.digest) == len("sha256:") + 64


def test_cross_organ_refutes():
    obs = CrossCheckVerifierOrgan().observe(Implies(Var("A"), Var("B")))[0]
    assert obs.status == Status.PASS
    assert obs.data["verdict"] == "refuted"


def test_cross_organ_ignores_foreign_subject():
    assert CrossCheckVerifierOrgan().observe("nope") == []
    assert CrossCheckVerifierOrgan().observe(7) == []


def test_cross_organ_selftest_passes():
    assert CrossCheckVerifierOrgan().selftest().passed
