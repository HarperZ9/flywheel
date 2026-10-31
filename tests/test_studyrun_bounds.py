"""studyrun.bounds tests (prior update PU30-02, F91 C5).

Run: python -m pytest tests/test_studyrun*.py  (from the repository root)

The rule must hold its family-wise error when every arm sits exactly at its bound (the case F79's
per-test Wald rule failed), still flag a clear exceedance, and agree with the shared CC0 stats vectors (tests/data/stats_vectors.json,
a copy of cmmns analysis/vectors/stats_vectors.json).
"""
import json
import random
import sys
from pathlib import Path

import pytest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]

from harness.studyrun import bounds  # noqa: E402


def _wald_flag(k, n, b, z=1.959963984540054):
    p = k / n
    return p - z * (p * (1 - p) / n) ** 0.5 > b


def test_all_null_family_rate_is_held_and_wald_is_not():
    rnd = random.Random(7)
    fams, n, bound, m = 200, 400, 0.3, 50
    holm_hits = wald_hits = 0
    for _ in range(fams):
        tests = [(sum(rnd.random() < bound for _ in range(n)), n, bound) for _ in range(m)]
        flags, _ = bounds.violations(tests)
        holm_hits += any(flags)
        wald_hits += any(_wald_flag(k, n, b) for k, n, b in tests)
    assert holm_hits / fams <= 0.09
    assert wald_hits / fams >= 0.3


def test_clear_exceedance_is_flagged():
    flags, ps = bounds.violations([(80, 100, 0.5), (50, 100, 0.5), (10, 100, 0.5)])
    assert flags == [True, False, False]
    assert ps[0] < 1e-8 and ps[2] > 0.99


def test_bound_at_one_never_flags_and_unknown_method_refused():
    flags, ps = bounds.violations([(100, 100, 1.0)])
    assert flags == [False] and ps == [1.0]
    with pytest.raises(ValueError):
        bounds.violations([(1, 2, 0.5)], method="wald")


def _vectors():
    return json.loads((ROOT / "tests" / "data" / "stats_vectors.json").read_text(encoding="utf-8"))


def test_upper_tail_matches_the_shared_stats_vectors():
    rows = _vectors()["binomial_upper_tail"]
    assert len(rows) >= 10
    for row in rows:
        got = bounds.exact_p(row["k"], row["n"], row["bound"])
        assert abs(got - row["p_upper"]) <= 1e-9 * max(row["p_upper"], 1e-300), row


def test_family_corrections_match_the_shared_stats_vectors():
    for fam in _vectors()["families"]:
        for method in ("holm", "bonferroni", "bh"):
            assert bounds.RULES[method](fam["p"], fam["alpha"]) == fam[method], (fam["id"], method)
