"""The v3 compute denominator: the budget ceiling, retries, oracle-feedback
access, and an exact graded score.

The load-bearing tests here are not the validators. They are:

  * the claim digest MOVES when a new field moves, which is what proves the
    field is actually covered rather than merely stored;
  * the subject digest does NOT move, which proves the placement was a decision
    and not an accident;
  * a graded score never displaces the four-way verdict;
  * nothing new introduces a float into a hashed structure.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.receipt import Receipt, SCHEMA, subject_digest
from harness.receipt_fields import (
    Budget, Denominator, EvidenceKind, GradedScore, ReceiptError, Tier,
    canonical, no_floats)
from harness.verdict import Verdict, Attribution


def _den(**kw):
    base = dict(attempts=8, group_size=4, oracle_calls_consumed=9, hits=1,
                undecided=0, unverifiable=0, parse_failures=0, timeouts=0,
                tokens_in=120, tokens_out=512, cache_hit_tokens=0,
                tasks_proposed=4, tasks_filtered_out=0, retries=0,
                oracle_feedback_visible=False, filter_id="f.v1",
                filter_hash="sha256:" + "f" * 64, filter_is_learned=False)
    base.update(kw)
    return Denominator(**base)


def _budget(**kw):
    base = dict(wall_seconds_limit=600, tokens_limit=4096, retries_limit=2,
                exhausted=False)
    base.update(kw)
    return Budget(**base)


def _score(**kw):
    base = dict(numerator=3, denominator=4, trials=5, grader_id="grader.v1",
                grader_sha256="sha256:" + "9" * 64)
    base.update(kw)
    return GradedScore(**base)


def _r(**kw):
    base = dict(
        criterion_id="zarankiewicz.z_2_2", criterion_version=1,
        criterion_sha256="sha256:" + "c" * 64, family="zarankiewicz",
        family_instance_id="z-7", generator_id="g.v1", generator_seed=7,
        candidate_sha256="sha256:" + "d" * 64, prompt_hash="sha256:" + "e" * 64,
        checker_module="harness.certificates.zarankiewicz",
        checker_source_sha256="sha256:" + "a" * 64,
        executes_candidate_code=False, oracle_qa_card_hash="deadbeefdeadbeef",
        held_out_agreement="AGREE", evidence_kind=EvidenceKind.CONSTRUCTIVE,
        tier=Tier.CONSTRUCTION_CERTIFICATE, verdict=Verdict.PASS,
        attribution=Attribution.CANDIDATE, objective="21",
        incumbent_objective="21", incumbent_source="operator_search",
        coverage={"predicate_exact": True, "search_space_enumerated": False},
        raw_stdout_sha256="sha256:" + "b" * 64,
        analysis_script_sha256="sha256:" + "7" * 64,
        denominator=_den(), budget=_budget(), model_ref="qwen2.5:7b",
        base_weights_digest="sha256:" + "8" * 64, harness_version="0.1.0")
    base.update(kw)
    return Receipt(**base)


# --- the fields are covered by the claim, and only the claim ----------------

def test_a_different_budget_changes_the_claim_digest():
    """If the ceiling were stored but unhashed, a signature would attest to a
    result while saying nothing about what it was allowed to spend."""
    a = _r(budget=_budget(tokens_limit=4096))
    b = _r(budget=_budget(tokens_limit=999999))
    assert a.claim_sha256() != b.claim_sha256()


def test_a_different_budget_leaves_the_subject_digest_alone():
    """Two verifiers spending different budgets on the SAME candidate must still
    agree on what was checked, or their disagreement cannot be located."""
    a = _r(budget=_budget(tokens_limit=4096))
    b = _r(budget=_budget(tokens_limit=999999))
    assert a.subject_sha256() == b.subject_sha256()


def test_retries_and_feedback_access_change_the_claim_digest():
    base = _r()
    assert _r(denominator=_den(retries=3)).claim_sha256() != base.claim_sha256()
    assert _r(denominator=_den(oracle_feedback_visible=True)).claim_sha256() \
        != base.claim_sha256()


def test_a_graded_score_changes_the_claim_digest():
    assert _r(graded_score=_score()).claim_sha256() != _r().claim_sha256()
    assert _r(graded_score=_score(numerator=1)).claim_sha256() \
        != _r(graded_score=_score(numerator=3)).claim_sha256()


# --- a score never becomes a verdict ----------------------------------------

def test_a_perfect_score_does_not_turn_a_fail_into_a_pass():
    r = _r(verdict=Verdict.FAIL, attribution=Attribution.CANDIDATE,
           graded_score=_score(numerator=1, denominator=1))
    d = r.to_dict()
    assert d["verdict"] == "FAIL"
    assert d["graded_score"]["numerator"] == 1
    assert d["graded_score"]["denominator"] == 1


def test_an_absent_score_is_an_explicit_null():
    assert _r().to_dict()["graded_score"] is None


# --- no floats reach a hash -------------------------------------------------

def test_the_wire_form_carries_no_float_anywhere():
    r = _r(graded_score=_score(), budget=_budget(exhausted=True))
    no_floats(r.to_dict(), "receipt")
    canonical(r.to_dict())          # refuses NaN and infinity


def test_the_decimal_form_is_exact_integer_arithmetic():
    assert _score(numerator=3, denominator=4).as_decimal_string() == "0.750000"
    assert _score(numerator=1, denominator=3).as_decimal_string() == "0.333333"
    assert _score(numerator=1, denominator=1).as_decimal_string() == "1.000000"
    assert _score(numerator=0, denominator=5).as_decimal_string() == "0.000000"
    assert _score(numerator=1, denominator=8).as_decimal_string(3) == "0.125"


def test_the_decimal_form_stays_out_of_the_hashed_dict():
    assert "as_decimal_string" not in _score().to_dict()
    assert set(_score().to_dict()) == {
        "numerator", "denominator", "trials", "grader_id", "grader_sha256"}


# --- the honesty lines fire on the new facts --------------------------------

def test_an_undeclared_budget_is_reported_not_hidden():
    assert "NOT_PROVES_COST_BOUNDED" in _r(
        budget=Budget.undeclared()).does_not_prove()
    assert "NOT_PROVES_COST_BOUNDED" not in _r().does_not_prove()


def test_a_result_reached_at_the_ceiling_says_so():
    assert "NOT_PROVES_UNCONSTRAINED_BY_BUDGET" in _r(
        budget=_budget(exhausted=True)).does_not_prove()
    assert "NOT_PROVES_UNCONSTRAINED_BY_BUDGET" not in _r().does_not_prove()


def test_retries_and_visible_feedback_are_reported():
    assert "NOT_PROVES_FIRST_ATTEMPT_SUCCESS" in _r(
        denominator=_den(retries=1)).does_not_prove()
    assert "NOT_PROVES_FIRST_ATTEMPT_SUCCESS" not in _r().does_not_prove()
    assert "NOT_PROVES_FOUND_WITHOUT_ORACLE_FEEDBACK" in _r(
        denominator=_den(oracle_feedback_visible=True)).does_not_prove()
    assert "NOT_PROVES_FOUND_WITHOUT_ORACLE_FEEDBACK" \
        not in _r().does_not_prove()


def test_a_single_trial_score_is_flagged_as_unstable():
    assert "NOT_PROVES_SCORE_STABILITY" in _r(
        graded_score=_score(trials=1)).does_not_prove()
    assert "NOT_PROVES_SCORE_STABILITY" not in _r(
        graded_score=_score(trials=2)).does_not_prove()


# --- refusals ---------------------------------------------------------------

def test_a_budget_refuses_an_incoherent_absence():
    with pytest.raises(ReceiptError):
        Budget(wall_seconds_limit=60, tokens_limit=0, retries_limit=0,
               exhausted=False, declared=False)
    with pytest.raises(ReceiptError):
        Budget(wall_seconds_limit=0, tokens_limit=0, retries_limit=0,
               exhausted=True, declared=False)


def test_a_budget_refuses_a_bool_or_negative_limit():
    with pytest.raises(ReceiptError):
        _budget(tokens_limit=True)
    with pytest.raises(ReceiptError):
        _budget(tokens_limit=-1)
    with pytest.raises(ReceiptError):
        _budget(exhausted="yes")


def test_undeclared_is_a_stated_absence_not_three_zeros():
    b = Budget.undeclared()
    assert b.declared is False and b.exhausted is False
    assert (b.wall_seconds_limit, b.tokens_limit, b.retries_limit) == (0, 0, 0)


def test_a_receipt_refuses_a_budget_that_is_not_a_budget():
    with pytest.raises(ReceiptError):
        _r(budget=None)
    with pytest.raises(ReceiptError):
        _r(budget={"tokens_limit": 10})


def test_a_receipt_refuses_a_score_that_is_not_a_graded_score():
    with pytest.raises(ReceiptError):
        _r(graded_score={"numerator": 1, "denominator": 2})


def test_retries_refuses_a_bool_and_feedback_refuses_an_int():
    with pytest.raises(ReceiptError):
        _den(retries=True)
    with pytest.raises(ReceiptError):
        _den(retries=-1)
    with pytest.raises(ReceiptError):
        _den(oracle_feedback_visible=1)


def test_a_score_outside_the_unit_interval_is_refused():
    with pytest.raises(ReceiptError):
        _score(numerator=5, denominator=4)
    with pytest.raises(ReceiptError):
        _score(numerator=1, denominator=0)
    with pytest.raises(ReceiptError):
        _score(numerator=-1, denominator=4)


def test_a_score_without_trials_or_a_named_grader_is_refused():
    with pytest.raises(ReceiptError):
        _score(trials=0)
    with pytest.raises(ReceiptError):
        _score(grader_id="")
    with pytest.raises(ReceiptError):
        _score(grader_sha256="")


# --- the version guard ------------------------------------------------------

def test_a_foreign_schema_is_refused_rather_than_reinterpreted():
    d = _r().to_dict()
    d["schema"] = "flywheel.receipt/v2"
    with pytest.raises(ReceiptError):
        Receipt.from_dict(d)
    del d["schema"]
    with pytest.raises(ReceiptError):
        Receipt.from_dict(d)


def test_the_standalone_subject_digest_equals_the_receipt_s():
    """The endpoint computes a subject digest without a claim around it. If the
    two ever disagreed, the difference would look like a real verification
    failure rather than the bookkeeping accident it would actually be."""
    r = _r()
    assert subject_digest(
        criterion_id=r.criterion_id, criterion_version=r.criterion_version,
        criterion_sha256=r.criterion_sha256, family=r.family,
        family_instance_id=r.family_instance_id, generator_id=r.generator_id,
        generator_seed=r.generator_seed, candidate_sha256=r.candidate_sha256,
        prompt_hash=r.prompt_hash, checker_module=r.checker_module,
        checker_source_sha256=r.checker_source_sha256,
        executes_candidate_code=r.executes_candidate_code,
        evidence_kind=r.evidence_kind, tier=r.tier) == r.subject_sha256()


def test_the_standalone_subject_digest_accepts_plain_strings():
    """A caller holding JSON should not have to reconstruct the enums."""
    r = _r()
    kw = dict(
        criterion_id=r.criterion_id, criterion_version=r.criterion_version,
        criterion_sha256=r.criterion_sha256, family=r.family,
        family_instance_id=r.family_instance_id, generator_id=r.generator_id,
        generator_seed=r.generator_seed, candidate_sha256=r.candidate_sha256,
        prompt_hash=r.prompt_hash, checker_module=r.checker_module,
        checker_source_sha256=r.checker_source_sha256,
        executes_candidate_code=r.executes_candidate_code)
    assert subject_digest(evidence_kind=r.evidence_kind.value,
                          tier=r.tier.value, **kw) == r.subject_sha256()


def test_the_wire_form_roundtrips_with_every_new_field():
    r = _r(graded_score=_score(), budget=_budget(exhausted=True),
           denominator=_den(retries=2, oracle_feedback_visible=True))
    back = Receipt.from_dict(r.to_dict())
    assert back.claim_sha256() == r.claim_sha256()
    assert back.subject_sha256() == r.subject_sha256()
    assert back.budget == r.budget
    assert back.graded_score == r.graded_score
    assert back.denominator.retries == 2
    assert back.to_dict()["schema"] == SCHEMA


def test_oracle_specific_limits_roundtrip_exactly_and_are_claim_bound():
    receipt = _r(extra_does_not_prove=("NOT_PROVES_ORACLE_SPECIFIC_BOUNDARY",))
    body = receipt.to_dict(); back = Receipt.from_dict(body)
    assert back.extra_does_not_prove == receipt.extra_does_not_prove
    assert back.to_dict() == body
    assert receipt.claim_sha256() != _r().claim_sha256()
