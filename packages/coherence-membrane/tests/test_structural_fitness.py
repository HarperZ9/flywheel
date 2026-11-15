from __future__ import annotations

import math

import pytest

from coherence_membrane.certificate import Verdict
from coherence_membrane.composition import compose
from coherence_membrane.novelty import novelty_criterion
from coherence_membrane.phash import hamming
from coherence_membrane.phyllotaxis import GOLDEN_ANGLE, golden_angle_deviation
from coherence_membrane.reconcile import reconcile
from coherence_membrane.structural_fitness import structural_fitness_criterion


def _golden_spiral(n, direction=1):
    return [(math.sqrt(i) * math.cos(math.radians(i * GOLDEN_ANGLE * direction)),
             math.sqrt(i) * math.sin(math.radians(i * GOLDEN_ANGLE * direction))) for i in range(n)]


def test_fit_verified_below_tolerance():
    crit = structural_fitness_criterion(golden_angle_deviation, tolerance=10.0)
    assert crit.judge(_golden_spiral(400)).verdict is Verdict.VERIFIED      # ~0 -> fit
    assert crit.judge(_golden_spiral(400)).oracle == "structural-fitness-v1"


def test_unfit_refuted_above_tolerance():
    crit = structural_fitness_criterion(golden_angle_deviation, tolerance=10.0)
    grid = [(x, y) for x in range(10) for y in range(10)]
    assert crit.judge(grid).verdict is Verdict.REFUTED                      # ~114 -> unfit


def test_nonfinite_deviation_is_unverifiable():
    # too-few-points -> inf -> UNVERIFIABLE (can't measure, not "unfit")
    crit = structural_fitness_criterion(golden_angle_deviation, tolerance=10.0)
    assert crit.judge([(0.0, 0.0), (1.0, 1.0)]).verdict is Verdict.UNVERIFIABLE


def test_raising_measure_is_unverifiable():
    def boom(form):
        raise ValueError("cannot measure")
    crit = structural_fitness_criterion(boom, tolerance=1.0)
    assert crit.judge(object()).verdict is Verdict.UNVERIFIABLE


def test_nan_measure_is_unverifiable():
    crit = structural_fitness_criterion(lambda f: float("nan"), tolerance=1.0)
    assert crit.judge(None).verdict is Verdict.UNVERIFIABLE


def test_rejects_nonfinite_or_negative_tolerance():
    # inf tolerance would VERIFY everything (the tier-2 rel_tol=inf bug) -> rejected loudly
    for bad in (float("inf"), float("nan"), -1.0, None):
        with pytest.raises(ValueError):
            structural_fitness_criterion(golden_angle_deviation, tolerance=bad)


def test_fit_via_reconcile():
    crit = structural_fitness_criterion(golden_angle_deviation, tolerance=10.0)
    obs = reconcile(_golden_spiral(400), perceive=lambda p: (p, repr(p).encode()), criterion=crit)
    assert obs.data["verdict"] == "verified"
    assert obs.data["criterion"] == "structural-fitness"
    assert obs.data["oracle"] == "structural-fitness-v1"


def test_grounded_creativity_novel_and_structured():
    # the payoff: creativity = novelty (far from corpus) AND structural fitness, composed
    # via the proven meet. VERIFIED iff BOTH hold; either failing -> REFUTED.
    corpus = [0x0, 0xFFFFFFFFFFFFFFFF]
    novel = novelty_criterion(corpus, distance=hamming, min_distance=12).judge(0x0F0F0F0F0F0F0F0F)
    derivative = novelty_criterion(corpus, distance=hamming, min_distance=12).judge(0x1)
    fit = structural_fitness_criterion(golden_angle_deviation, tolerance=10.0).judge(_golden_spiral(400))
    unfit = structural_fitness_criterion(golden_angle_deviation, tolerance=10.0).judge(
        [(x, y) for x in range(10) for y in range(10)])

    assert compose([novel, fit], claim="novel AND structured").verdict is Verdict.VERIFIED
    assert compose([derivative, fit], claim="derivative but structured").verdict is Verdict.REFUTED
    assert compose([novel, unfit], claim="novel but noise").verdict is Verdict.REFUTED
