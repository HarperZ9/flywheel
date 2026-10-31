"""trace_observation's Wilson and Holm against the shared CC0 stats vectors (tests/data/stats_vectors.json).

The vectors come from cmmns analysis/vectors/stats_vectors.json; repositories share the vectors, not the
code. trace_observation's Holm rejects only when the adjusted p is strictly below alpha, where the vectors
reject at equality. The tie case pins that difference so it cannot change silently.
"""
import json
from pathlib import Path

from harness.trace_observation.intervals import holm, wilson

VECTORS = json.loads((Path(__file__).resolve().parent / "data" / "stats_vectors.json").read_text(encoding="utf-8"))
STRICT_AT_TIE = {"holm-tie", "single", "bh-step-up"}  # each has p * m == alpha exactly


def test_wilson_matches_the_vectors():
    rows = VECTORS["wilson"]
    assert len(rows) >= 5
    for row in rows:
        lo, hi = wilson(row["k"], row["n"], row["z"])
        assert abs(lo - row["interval"][0]) <= 1e-12 and abs(hi - row["interval"][1]) <= 1e-12, row


def test_holm_matches_the_vectors_except_at_an_exact_tie():
    checked = 0
    for fam in VECTORS["families"]:
        if not fam["p"]:
            continue
        names = [f"h{i}" for i in range(len(fam["p"]))]
        out = holm(dict(zip(names, fam["p"])), fam["alpha"])
        got = [out[n]["reject"] == "true" for n in names]
        if fam["id"] in STRICT_AT_TIE:
            assert got != fam["holm"], fam["id"]
            assert got == [False] * len(names), fam["id"]
        else:
            assert got == fam["holm"], fam["id"]
            checked += 1
    assert checked >= 3
