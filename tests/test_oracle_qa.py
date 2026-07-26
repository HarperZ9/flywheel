"""Verifier QA precedes training. No card, no reward eligibility.

A verifier whose false accepts have never been measured is a reward function of
unknown correctness, and training on it teaches whatever it happens to be wrong
about. So every checker is attacked before its verdicts are treated as rewards.

Two disciplines the card enforces:

  1. A zero-count false-accept result is NOT reported as a rate of zero. Zero out
     of three proves almost nothing. The card reports a Wilson UPPER BOUND at a
     declared confidence, so "0 false accepts" becomes "at most 0.6 at 95%
     confidence with n=3" and the weakness of the evidence is visible on the face
     of the claim.
  2. Every mutation class needs a required minimum n. A battery that ran one
     mutant per class and found nothing has bounded almost nothing, and a card
     that hides that is worse than no card.

Honest bound, stated on the card itself: the battery bounds only the mutations
imagined. It quantifies the sample, never the imagination.
"""
import json
import math

import pytest

from harness.oracle_qa import (
    wilson_upper_bound, MutationClass, qa_battery, OracleQACard, QAError,
    REQUIRED_N_PER_CLASS, mutate,
)
from harness.certificates.zarankiewicz import ZarankiewiczOracle, encode
from harness.certificates.independent import IndependentZarankiewiczOracle

FANO_LINES = [(0, 1, 2), (0, 3, 4), (0, 5, 6), (1, 3, 5),
              (1, 4, 6), (2, 3, 6), (2, 4, 5)]
FANO_EDGES = [(p, li) for li, pts in enumerate(FANO_LINES) for p in pts]


def _valid_certs():
    """Known-valid certificates: a star at several sizes plus the Fano plane."""
    out = [encode(7, 7, FANO_EDGES)]
    for n in (5, 9, 13):
        out.append(encode(4, n, [(0, j) for j in range(n)]))
    return out


# --- the statistic ------------------------------------------------------------

def test_wilson_upper_bound_of_zero_successes_is_not_zero():
    # The whole point. Zero out of three is not a rate of zero.
    b = wilson_upper_bound(0, 3)
    assert b > 0.5
    assert b < 1.0


def test_the_bound_tightens_as_n_grows():
    bounds = [wilson_upper_bound(0, n) for n in (3, 10, 30, 100, 300)]
    assert bounds == sorted(bounds, reverse=True)
    assert bounds[-1] < 0.02


def test_the_bound_is_a_decimal_string_friendly_float_in_range():
    for k, n in ((0, 10), (1, 10), (5, 10), (10, 10)):
        b = wilson_upper_bound(k, n)
        assert 0.0 <= b <= 1.0


def test_all_successes_gives_a_bound_of_one():
    assert wilson_upper_bound(10, 10) == pytest.approx(1.0, abs=1e-9)


def test_a_higher_confidence_gives_a_looser_bound():
    assert wilson_upper_bound(0, 30, confidence=0.99) > wilson_upper_bound(0, 30, confidence=0.95)


def test_zero_n_is_refused_rather_than_dividing_by_zero():
    with pytest.raises(QAError):
        wilson_upper_bound(0, 0)


def test_more_successes_than_trials_is_refused():
    with pytest.raises(QAError):
        wilson_upper_bound(11, 10)


# --- the mutation engine ------------------------------------------------------

def test_every_mutation_class_produces_something_different():
    base = encode(7, 7, FANO_EDGES)
    for cls in MutationClass:
        muts = mutate(base, cls, count=3, seed=1)
        assert muts, cls
        for m in muts:
            assert m != base, cls


def test_mutation_is_deterministic_in_its_seed():
    base = encode(7, 7, FANO_EDGES)
    a = mutate(base, MutationClass.DUPLICATE_EDGE, count=4, seed=9)
    b = mutate(base, MutationClass.DUPLICATE_EDGE, count=4, seed=9)
    assert a == b


def test_a_near_miss_mutant_is_genuinely_close_to_valid():
    # A near miss must still parse. A mutant that fails to parse tests the parser,
    # not the predicate, and would inflate the apparent rejection rate.
    base = encode(7, 7, FANO_EDGES)
    for m in mutate(base, MutationClass.ADD_EDGE, count=5, seed=3):
        json.loads(m)


def test_the_planted_exploit_class_includes_the_bool_index():
    # The exploit the battery found in Task 6 is now a permanent regression probe.
    base = encode(7, 7, FANO_EDGES)
    muts = mutate(base, MutationClass.TYPE_CONFUSION, count=8, seed=1)
    assert any("true" in m for m in muts)


# --- the battery --------------------------------------------------------------

def test_the_battery_passes_a_sound_checker():
    card = qa_battery(ZarankiewiczOracle(), _valid_certs(), seed=5)
    assert card.passed is True
    assert card.false_accepts == 0
    assert card.false_rejects == 0


def test_the_battery_also_passes_the_independent_checker():
    card = qa_battery(IndependentZarankiewiczOracle(), _valid_certs(), seed=5)
    assert card.passed is True


def test_the_card_reports_a_bound_not_a_bare_zero():
    card = qa_battery(ZarankiewiczOracle(), _valid_certs(), seed=5)
    assert card.false_accept_upper_bound > 0.0
    assert card.confidence == 0.95


def test_the_card_records_n_per_mutation_class():
    card = qa_battery(ZarankiewiczOracle(), _valid_certs(), seed=5)
    for cls in MutationClass:
        assert card.per_class[cls.value]["n"] >= REQUIRED_N_PER_CLASS


def test_a_battery_below_the_required_n_does_not_pass():
    # One valid certificate and one mutant per class gives n=1 per class, below
    # the floor of 3. A battery that thin has bounded almost nothing.
    card = qa_battery(ZarankiewiczOracle(), [encode(7, 7, FANO_EDGES)], seed=5,
                      count_per_class=1)
    assert card.passed is False
    assert "INSUFFICIENT_N" in card.failures


def test_a_checker_that_accepts_a_mutant_fails_the_battery():
    class _Lax(ZarankiewiczOracle):
        def check(self, cert):
            from harness.certificates.base import Coverage
            return True, "accepts anything", Coverage(
                True, True, "1", "complete", None)

    card = qa_battery(_Lax(), _valid_certs(), seed=5)
    assert card.passed is False
    assert card.false_accepts > 0
    assert "FALSE_ACCEPT" in card.failures


def test_a_checker_that_rejects_a_valid_certificate_fails_the_battery():
    class _Paranoid(ZarankiewiczOracle):
        def check(self, cert):
            from harness.certificates.base import Coverage
            return False, "rejects everything", Coverage(
                True, True, "1", "complete", None)

    card = qa_battery(_Paranoid(), _valid_certs(), seed=5)
    assert card.passed is False
    assert card.false_rejects > 0
    assert "FALSE_REJECT" in card.failures


def test_the_battery_needs_at_least_one_known_valid_certificate():
    with pytest.raises(QAError):
        qa_battery(ZarankiewiczOracle(), [], seed=1)


def test_out_of_scope_responses_are_not_counted_as_rejections():
    # UNVERIFIABLE is not a rejection of the candidate. Counting it as a false
    # reject would punish a checker for honestly declaring its scope.
    card = qa_battery(ZarankiewiczOracle(), _valid_certs(), seed=5)
    assert card.unverifiable_seen >= 0
    assert card.false_rejects == 0


# --- the card as an artifact ---------------------------------------------------

def test_the_card_hash_is_stable_and_content_addressed():
    a = qa_battery(ZarankiewiczOracle(), _valid_certs(), seed=5)
    b = qa_battery(ZarankiewiczOracle(), _valid_certs(), seed=5)
    assert a.card_hash() == b.card_hash()


def test_a_different_result_gives_a_different_card_hash():
    a = qa_battery(ZarankiewiczOracle(), _valid_certs(), seed=5)
    b = qa_battery(ZarankiewiczOracle(), _valid_certs(), seed=6)
    assert a.card_hash() != b.card_hash() or a.to_dict() == b.to_dict()


def test_the_card_states_its_own_limit():
    card = qa_battery(ZarankiewiczOracle(), _valid_certs(), seed=5)
    assert any("imagin" in s.lower() for s in card.does_not_prove)


def test_the_card_serializes_to_plain_json():
    card = qa_battery(ZarankiewiczOracle(), _valid_certs(), seed=5)
    text = json.dumps(card.to_dict(), sort_keys=True)
    back = json.loads(text)
    assert back["oracle_type"] == "zarankiewicz_certificate"
    assert back["schema"] == "flywheel.oracle-qa-card/v1"


def test_the_card_records_the_checker_source_hash():
    # A card that does not pin the code it graded could be reused after an edit.
    card = qa_battery(ZarankiewiczOracle(), _valid_certs(), seed=5)
    assert len(card.checker_source_sha256) == 64
