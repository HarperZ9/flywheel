"""Falsifiers for accountability_bench — the benchmark must be able to FAIL.

The load-bearing assertion is NOT that the harness scores high (that is
near-tautological, and the module says so itself). It is that the STRAWMAN
scores near zero: a benchmark that cannot score an unaccountable system badly
measures nothing. Plus: the self-authored caveat must be present in the
output, so the tautology is carried in the receipt, not hidden.
"""
from harness.accountability_bench import score_harness, score_strawman

EXPECTED_DIMS = {"re_checkability", "externalization", "adversarial_soundness",
                 "no_regression", "invariant_fidelity", "null_space_honesty",
                 "provenance", "buildc_receipt_bridge"}


def test_harness_scores_high_on_its_own_axes():
    r = score_harness()
    assert r["n_dimensions"] == 8
    assert {d["name"] for d in r["dimensions"]} == EXPECTED_DIMS
    assert all(0.0 <= d["score"] <= 1.0 for d in r["dimensions"])
    assert r["overall"] >= 0.9


def test_strawman_scores_near_zero():
    # THE credibility falsifier: an unaccountable system must score badly.
    r = score_strawman()
    assert r["overall"] < 0.2
    assert r["credibility"] is True


def test_benchmark_separates_the_two_systems():
    # the separation IS the measurement; if it collapses, the bench is dead
    gap = score_harness()["overall"] - score_strawman()["overall"]
    assert gap > 0.7


def test_self_authored_caveat_is_carried_in_the_receipt():
    r = score_harness()
    caveat = r["self_authored_caveat"]
    assert "near-tautological" in caveat
    assert "OTHER systems" in caveat          # the real value is scoring others
    assert "unearned" in caveat               # no capability/uplift axis, and why
    assert "NOT capability" in r["non_goal"]


def test_every_dimension_is_grounded_in_a_real_module():
    # no free-floating scores: each dimension names the module that computes it
    r = score_harness()
    for d in r["dimensions"]:
        assert d["grounded_in"], d["name"]
        mod = d["grounded_in"].split(".")[0].split(" ")[0]
        __import__(f"harness.{mod}")          # the grounding module must exist
