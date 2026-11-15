"""The domain regression corpus: every sample produces exactly its expected pack
categories, clean samples pass their gate, and every pack category is exercised
by at least one flagged sample, so a new rule cannot ship without a sample.
"""
from articulate import bench_domains, rules_ext


def test_every_sample_matches_its_expectation():
    rows = bench_domains.results()
    bad = [(name, sorted(exp), sorted(found)) for name, _p, exp, found, _g, ok in rows if not ok]
    assert rows and not bad, bad


def test_every_pack_category_has_a_flagged_sample():
    covered = set()
    for _name, _p, expected, _found, _g, _ok in bench_domains.results():
        covered |= expected
    assert covered == rules_ext.categories()


def test_clean_samples_pass_their_gate():
    for name, _p, expected, _found, gate, _ok in bench_domains.results():
        if not expected:
            assert gate == "ok", name
