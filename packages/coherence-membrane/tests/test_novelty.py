from __future__ import annotations

import pytest

from coherence_membrane.certificate import Verdict
from coherence_membrane.novelty import novelty_criterion
from coherence_membrane.phash import hamming
from coherence_membrane.reconcile import reconcile


def test_novelty_perceptual_hamming():
    # the shipped instantiation: signatures are 64-bit perceptual hashes, distance = hamming
    corpus = [0x0000000000000000, 0xFFFFFFFF00000000]   # two prior-work hashes
    crit = novelty_criterion(corpus, distance=hamming, min_distance=12)
    assert crit.judge(0x0F0F0F0F0F0F0F0F).verdict is Verdict.VERIFIED   # far from both (~32 bits) -> novel
    assert crit.judge(0x0000000000000003).verdict is Verdict.REFUTED    # 2 bits from corpus[0] -> derivative


def test_novelty_empty_corpus_is_unverifiable():
    crit = novelty_criterion([], distance=hamming, min_distance=10)
    assert crit.judge(123).verdict is Verdict.UNVERIFIABLE


def test_novelty_generic_distance():
    crit = novelty_criterion([0, 10], distance=lambda a, b: abs(a - b), min_distance=5)
    assert crit.judge(20).verdict is Verdict.VERIFIED   # nearest = 10 >= 5
    assert crit.judge(12).verdict is Verdict.REFUTED    # nearest = 2  < 5


def test_novelty_failed_distance_is_unverifiable():
    def bad(a, b):
        raise TypeError("incomparable")
    crit = novelty_criterion([1, 2], distance=bad, min_distance=1)
    assert crit.judge(object()).verdict is Verdict.UNVERIFIABLE


def test_novelty_anti_collapse():
    # the Cell-Patterns "visual elevator music" antidote: an exact duplicate of a corpus
    # member is REFUTED (mode-collapse caught), never waved through.
    corpus = [0xABCDEF, 0x123456]
    crit = novelty_criterion(corpus, distance=hamming, min_distance=8)
    assert crit.judge(0xABCDEF).verdict is Verdict.REFUTED


def test_novelty_via_reconcile():
    # creativity as a reconcile binding: perceive a work's signature, judge novelty
    crit = novelty_criterion([0x0, 0xFF], distance=hamming, min_distance=12)
    obs = reconcile(0x0F0F0F0F0F0F0F0F, perceive=lambda sig: (sig, str(sig).encode()), criterion=crit)
    assert obs.data["verdict"] == "verified"
    assert obs.data["criterion"] == "novelty-vs-corpus"
    assert obs.data["oracle"] == "novelty-vs-corpus-v1"


def test_novelty_rejects_degenerate_min_distance():
    # a degenerate threshold is a construction-time programmer error, raised loudly:
    # None/NaN are non-real; 0 would admit exact duplicates as novel (disables anti-collapse).
    for bad in (None, 0, float("nan"), -1):
        with pytest.raises(ValueError):
            novelty_criterion([1, 2], distance=hamming, min_distance=bad)
