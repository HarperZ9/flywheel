from __future__ import annotations

from coherence_membrane.distribution import Distribution


def _fair_coin():
    return Distribution(((0.0, 0.5), (1.0, 0.5)))


def test_total_and_support():
    d = _fair_coin()
    assert d.total() == 1.0
    assert d.support() == (0.0, 1.0)


def test_mean_and_variance_rederived():
    d = _fair_coin()
    assert d.mean() == 0.5
    assert d.variance() == 0.25


def test_fair_die_moments():
    d = Distribution(tuple((float(k), 1 / 6) for k in range(1, 7)))
    assert abs(d.mean() - 3.5) < 1e-12
    assert abs(d.variance() - (35 / 12)) < 1e-12     # known variance of a fair die
