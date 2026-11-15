from __future__ import annotations

from coherence_membrane.observation import Status
from coherence_membrane.organs.quantity_verifier import QuantityVerifierOrgan
from coherence_membrane.quantity import LENGTH, MASS, TIME, Quantity, newton
from coherence_membrane.quantity_oracle import QuantityClaim


def _fma_true():
    m = Quantity(2.0, MASS)
    a = Quantity(3.0, LENGTH / TIME ** 2)
    return QuantityClaim("F = m*a", m * a, 6.0 * newton)


def test_quantity_organ_verifies_true_equation():
    obs = QuantityVerifierOrgan().observe(_fma_true())[0]
    assert obs.status == Status.PASS
    assert obs.data["verdict"] == "verified"
    assert obs.data["oracle"] == "dimensional-invariant-v1"
    assert obs.provenance.digest.startswith("sha256:")
    assert len(obs.provenance.digest) == len("sha256:") + 64


def test_quantity_organ_refutes_dimension_mismatch():
    claim = QuantityClaim("mass == length", Quantity(1.0, MASS), Quantity(1.0, LENGTH))
    obs = QuantityVerifierOrgan().observe(claim)[0]
    assert obs.status == Status.PASS
    assert obs.data["verdict"] == "refuted"


def test_quantity_organ_ignores_foreign_subject():
    assert QuantityVerifierOrgan().observe("not a claim") == []
    assert QuantityVerifierOrgan().observe(42) == []


def test_quantity_organ_selftest_passes():
    assert QuantityVerifierOrgan().selftest().passed
