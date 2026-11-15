# tests/test_distribution_verifier_organ.py
from __future__ import annotations

from coherence_membrane.distribution import Distribution
from coherence_membrane.distribution_oracle import DistributionClaim
from coherence_membrane.observation import Status
from coherence_membrane.organs.distribution_verifier import DistributionVerifierOrgan


def _coin():
    return Distribution(((0.0, 0.5), (1.0, 0.5)))


def test_distribution_organ_verifies():
    obs = DistributionVerifierOrgan().observe(
        DistributionClaim("fair coin", _coin(), mean=0.5, variance=0.25))[0]
    assert obs.status == Status.PASS
    assert obs.data["verdict"] == "verified"
    assert obs.data["oracle"] == "distribution-invariant-v1"
    assert len(obs.provenance.digest) == len("sha256:") + 64


def test_distribution_organ_refutes_wrong_moment():
    obs = DistributionVerifierOrgan().observe(
        DistributionClaim("wrong mean", _coin(), mean=0.9))[0]
    assert obs.status == Status.PASS
    assert obs.data["verdict"] == "refuted"


def test_distribution_organ_ignores_foreign_subject():
    assert DistributionVerifierOrgan().observe("not a claim") == []


def test_distribution_organ_selftest_passes():
    assert DistributionVerifierOrgan().selftest().passed
