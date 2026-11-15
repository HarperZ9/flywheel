from __future__ import annotations

import pytest

from coherence_membrane.certificate import Verdict
from coherence_membrane.distribution import Distribution
from coherence_membrane.distribution_oracle import (
    DistributionClaim, check_distribution, check_moments, check_normalized,
)


def _fair_coin():
    return Distribution(((0.0, 0.5), (1.0, 0.5)))


def test_check_normalized():
    assert check_normalized(_fair_coin()).verdict is Verdict.VERIFIED
    assert check_normalized(Distribution(((0.0, 0.4), (1.0, 0.4)))).verdict is Verdict.REFUTED
    assert check_normalized(Distribution(((0.0, -0.1), (1.0, 1.1)))).verdict is Verdict.REFUTED
    assert check_normalized(Distribution(())).verdict is Verdict.UNVERIFIABLE


def test_check_moments_rederives():
    d = _fair_coin()
    assert check_moments(d, mean=0.5, variance=0.25).verdict is Verdict.VERIFIED
    assert check_moments(d, mean=0.9).verdict is Verdict.REFUTED
    assert check_moments(d).verdict is Verdict.UNVERIFIABLE                       # no claim
    assert check_moments(Distribution(()), mean=0.0).verdict is Verdict.UNVERIFIABLE  # zero mass


def test_check_moments_refuted_evidence():
    c = check_moments(_fair_coin(), variance=1.0)
    assert c.verdict is Verdict.REFUTED
    assert dict(c.evidence)["derived_variance"] == repr(0.25)


def test_check_distribution_combines_fail_closed():
    d = _fair_coin()
    assert check_distribution(d, mean=0.5, variance=0.25).verdict is Verdict.VERIFIED
    assert check_distribution(d, mean=0.9).verdict is Verdict.REFUTED            # wrong moment
    bad = Distribution(((0.0, 0.4), (1.0, 0.4)))                                 # sums to 0.8
    assert check_distribution(bad, mean=0.5).verdict is Verdict.REFUTED          # not normalized
    assert check_distribution(d).verdict is Verdict.VERIFIED                     # normalization only


def test_check_distribution_pathological_tol_is_unverifiable():
    # inf/nan/negative tolerances must not launder a false VERIFIED (soundness)
    bad = Distribution(((0.0, 0.4), (1.0, 0.4)))   # sums to 0.8, NOT normalized
    assert check_normalized(bad, tol=float("inf")).verdict is Verdict.UNVERIFIABLE
    assert check_moments(_fair_coin(), mean=0.9, rel_tol=float("inf")).verdict is Verdict.UNVERIFIABLE
    assert check_moments(_fair_coin(), mean=0.9, rel_tol=float("nan")).verdict is Verdict.UNVERIFIABLE


def test_distribution_claim_frozen():
    c = DistributionClaim("x", _fair_coin(), mean=0.5)
    assert c.rel_tol == 1e-9
    with pytest.raises(AttributeError):
        c.mean = 0.1
