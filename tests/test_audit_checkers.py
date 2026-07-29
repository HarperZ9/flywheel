"""test_audit_checkers.py -- the fault-injection audit proves itself first.

Before a TPR/FPR/Youden-J receipt can be trusted to grade the certificate
checkers, this harness has to prove: every named mutator genuinely produces a
certificate an honest checker refuses; a known-good certificate genuinely
passes; the rate arithmetic is right on a hand-computed fixture; and the same
(seed, n_good) reproduces the same receipt byte for byte.

Nothing here edits harness/certificates/*; only scripts/audit_mutations.py
and scripts/audit_checkers.py are under test.
"""
from __future__ import annotations

import json

import pytest

from harness.certificates.crossing import CrossingOracle
from harness.certificates.crossing_independent import IndependentCrossingOracle
from harness.certificates.independent import IndependentZarankiewiczOracle
from harness.certificates.zarankiewicz import ZarankiewiczOracle
from scripts.audit_checkers import DOES_NOT_PROVE, SCHEMA, _rates, run_audit
from scripts.audit_mutations import (
    CROSSING_FAULTS, ZARANKIEWICZ_FAULTS, cr_known_good_certs,
    zk_known_good_certs,
)


# --- known-good certificates pass both checkers in a family -------------------

def test_known_good_zarankiewicz_certs_pass_both_checkers():
    good = zk_known_good_certs(12, seed=2)
    primary, held_out = ZarankiewiczOracle(), IndependentZarankiewiczOracle()
    for cert in good:
        s = json.dumps(cert)
        assert primary.verify(s, None).verdict() == "PASS", cert
        assert held_out.verify(s, None).verdict() == "PASS", cert


def test_known_good_crossing_certs_pass_both_checkers():
    good = cr_known_good_certs(12, seed=2)
    primary, held_out = CrossingOracle(), IndependentCrossingOracle()
    for cert in good:
        s = json.dumps(cert)
        assert primary.verify(s, None).verdict() == "PASS", cert
        assert held_out.verify(s, None).verdict() == "PASS", cert


# --- every named mutator is genuinely refused by both checkers ----------------

@pytest.mark.parametrize("name", [n for n, _ in ZARANKIEWICZ_FAULTS])
def test_every_zarankiewicz_fault_is_refused_by_both_checkers(name):
    mutate = dict(ZARANKIEWICZ_FAULTS)[name]
    good = zk_known_good_certs(6, seed=1)
    primary, held_out = ZarankiewiczOracle(), IndependentZarankiewiczOracle()
    for cert in good:
        bad = json.dumps(mutate(cert))
        assert primary.verify(bad, None).verdict() != "PASS", (name, bad)
        assert held_out.verify(bad, None).verdict() != "PASS", (name, bad)


@pytest.mark.parametrize("name", [n for n, _ in CROSSING_FAULTS])
def test_every_crossing_fault_is_refused_by_both_checkers(name):
    mutate = dict(CROSSING_FAULTS)[name]
    good = cr_known_good_certs(6, seed=1)
    primary, held_out = CrossingOracle(), IndependentCrossingOracle()
    for cert in good:
        bad = json.dumps(mutate(cert))
        assert primary.verify(bad, None).verdict() != "PASS", (name, bad)
        assert held_out.verify(bad, None).verdict() != "PASS", (name, bad)


# --- rate arithmetic on a hand-computed fixture --------------------------------

def test_rate_arithmetic_matches_a_hand_computed_fixture():
    # 10 known-good: the checker wrongly refuses 2 -> fpr = 0.2
    # 20 known-bad: the checker catches 18 -> tpr = 0.9 -> J = 0.7
    good_verdicts = ["PASS"] * 8 + ["FAIL"] * 2
    bad_verdicts = ["FAIL"] * 15 + ["UNVERIFIABLE"] * 3 + ["PASS"] * 2
    rates = _rates(good_verdicts, bad_verdicts)
    assert (rates["n_good"], rates["n_bad"]) == (10, 20)
    assert (rates["fp"], rates["tn"]) == (2, 8)
    assert (rates["tp"], rates["fn"]) == (18, 2)
    assert rates["fpr"] == pytest.approx(0.2)
    assert rates["tpr"] == pytest.approx(0.9)
    assert rates["youden_j"] == pytest.approx(0.7)


def test_a_perfect_checker_scores_youden_j_of_one():
    rates = _rates(["PASS"] * 5, ["FAIL"] * 5)
    assert rates["fpr"] == 0.0
    assert rates["tpr"] == 1.0
    assert rates["youden_j"] == 1.0


def test_a_checker_that_refuses_everything_scores_youden_j_of_zero():
    # Catches every fault, but also refuses every good certificate: J = 1 - 1.
    rates = _rates(["FAIL"] * 5, ["FAIL"] * 5)
    assert rates["fpr"] == 1.0
    assert rates["tpr"] == 1.0
    assert rates["youden_j"] == 0.0


def test_an_empty_bad_or_good_set_does_not_divide_by_zero():
    assert _rates([], ["FAIL"])["fpr"] == 0.0
    assert _rates(["PASS"], [])["tpr"] == 0.0


# --- determinism: two runs of the whole audit agree ----------------------------

def test_two_runs_of_the_full_audit_agree_byte_for_byte():
    r1 = run_audit(n_good=6, seed=99)
    r2 = run_audit(n_good=6, seed=99)
    assert r1 == r2
    assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)


def test_a_different_seed_changes_the_generated_certificates():
    r1 = run_audit(n_good=6, seed=1)
    r2 = run_audit(n_good=6, seed=2)
    assert r1 != r2


# --- receipt shape --------------------------------------------------------------

def test_the_receipt_carries_schema_taxonomy_rates_and_denominators():
    receipt = run_audit(n_good=5, seed=3)
    assert receipt["schema"] == SCHEMA
    assert set(receipt["families"]) == {"zarankiewicz", "rectilinear_crossing"}
    for fam in receipt["families"].values():
        assert fam["fault_classes"]
        assert fam["n_good"] == 5
        for checker_name in ("primary", "held_out"):
            c = fam["checkers"][checker_name]
            for key in ("n_good", "n_bad", "tp", "fn", "fp", "tn",
                        "tpr", "fpr", "youden_j", "by_fault_class"):
                assert key in c, (checker_name, key)
            assert c["n_good"] == 5
            assert c["n_bad"] == 5 * len(fam["fault_classes"])
    assert receipt["does_not_prove"] == DOES_NOT_PROVE


def test_does_not_prove_states_the_two_mandatory_caveats():
    text = " ".join(DOES_NOT_PROVE)
    assert "natural candidate distribution" in text
    assert "fault class" in text and "nobody imagined" in text


def test_the_mutation_module_never_imports_a_checker_it_stresses():
    # Building a "known-bad" fixture by asking the checker under audit
    # whether it looks bad would make the audit trust the thing it exists to
    # measure. Mutators must only touch plain dicts.
    import inspect

    import scripts.audit_mutations as m
    src = inspect.getsource(m)
    for banned in ("ZarankiewiczOracle", "IndependentZarankiewiczOracle",
                   "CrossingOracle", "IndependentCrossingOracle"):
        assert banned not in src
