"""Falsifier for passn_model's pass@k / consensus@k estimators.

The exact hypergeometric formulas (k<=n) are checked against brute-force
enumeration of every k-subset of the pool -- if the closed form disagrees with
the ground-truth count, the test fails. The posterior-predictive branch (k>n)
is checked for the properties it must have: monotonic in k, bounded [0,1], and
pass >= consensus always.
"""
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.passn_model import pass_at_k, consensus_at_k


def _brute_pass(n, c, k):
    """Ground truth: fraction of k-subsets of n (c correct) with >=1 correct."""
    pool = [1] * c + [0] * (n - c)
    subsets = list(combinations(pool, k))
    hits = sum(1 for s in subsets if sum(s) >= 1)
    return hits / len(subsets)


def _brute_consensus(n, c, k):
    """Ground truth: fraction of k-subsets with >=2 correct."""
    pool = [1] * c + [0] * (n - c)
    subsets = list(combinations(pool, k))
    hits = sum(1 for s in subsets if sum(s) >= 2)
    return hits / len(subsets)


def test_pass_at_k_matches_bruteforce():
    for n in range(1, 13):
        for c in range(0, n + 1):
            for k in range(1, n + 1):
                exact = pass_at_k(n, c, k)
                brute = _brute_pass(n, c, k)
                assert abs(exact - brute) < 1e-9, \
                    f"pass_at_k({n},{c},{k})={exact} != brute {brute}"


def test_consensus_at_k_matches_bruteforce():
    for n in range(1, 13):
        for c in range(0, n + 1):
            for k in range(1, n + 1):
                exact = consensus_at_k(n, c, k)
                brute = _brute_consensus(n, c, k)
                assert abs(exact - brute) < 1e-9, \
                    f"consensus_at_k({n},{c},{k})={exact} != brute {brute}"


def test_pass_ge_consensus():
    """pass@k (>=1) must always be >= consensus@k (>=2), for all k incl. k>n."""
    for n in [4, 8, 16, 32]:
        for c in range(0, n + 1):
            for k in [1, 2, 4, 8, 16, 32, 64, 128]:
                assert pass_at_k(n, c, k) >= consensus_at_k(n, c, k) - 1e-12, \
                    f"pass < consensus at n={n} c={c} k={k}"


def test_monotonic_in_k():
    """Both metrics must be non-decreasing in the budget k."""
    for n in [4, 8, 16]:
        for c in range(0, n + 1):
            ks = [1, 2, 4, 8, 16, 32, 64, 128]
            pv = [pass_at_k(n, c, k) for k in ks]
            cv = [consensus_at_k(n, c, k) for k in ks]
            for a, b in zip(pv, pv[1:]):
                assert b >= a - 1e-12, f"pass not monotonic n={n} c={c}: {pv}"
            for a, b in zip(cv, cv[1:]):
                assert b >= a - 1e-12, f"consensus not monotonic n={n} c={c}: {cv}"


def test_bounds():
    for n in [4, 16]:
        for c in range(0, n + 1):
            for k in [1, 8, 64]:
                for f in (pass_at_k, consensus_at_k):
                    v = f(n, c, k)
                    assert 0.0 <= v <= 1.0, f"{f.__name__}({n},{c},{k})={v} out of bounds"


def test_zero_correct_never_reaches_within_pool():
    """A pool with 0 correct has pass@k=0 for k<=n (no correct to find)."""
    for n in [4, 8, 16]:
        for k in range(1, n + 1):
            assert pass_at_k(n, 0, k) == 0.0
            assert consensus_at_k(n, 0, k) == 0.0


def test_zero_correct_can_wake_up_beyond_pool():
    """A 0/n pool is NOT assumed p=0 forever: k>n predicts nonzero (Jeffreys)."""
    v = pass_at_k(16, 0, 64)
    assert v > 0.0, f"cold task should have nonzero pass at k>n, got {v}"


def test_single_correct_consensus_zero_within_pool():
    """1 correct in the pool -> consensus (>=2) is 0 for k<=n."""
    for n in [4, 8, 16]:
        for k in range(1, n + 1):
            assert consensus_at_k(n, 1, k) == 0.0
