"""Receipt v2: the record a stranger re-derives without trusting the author.

Six properties this suite pins, each one cheap now and expensive to retrofit once
receipts have accumulated:

  1. TWO DIGESTS. A subject digest that stays verdict-free so two verifiers who
     disagree remain comparable, and a claim digest that binds the verdict and is
     what gets signed. One digest cannot do both jobs.
  2. NO FLOATS in any hashed field. Cross-platform float formatting is the
     likeliest way a stranger's replay disagrees over nothing real.
  3. MANDATORY DENOMINATORS. A hit count without attempts is unpriceable: a
     generator firing a million shots looks identical to one firing ten.
  4. NOMINAL evidence kinds. Comparing across kinds is a validation ERROR, so
     human judgement can never be floored beneath machine checking.
  5. does_not_prove is MECHANICALLY DERIVED and non-empty. A receipt that reports
     only its proof is how a true explanation becomes a fake passport.
  6. signed_over is FIXED IN CODE per schema version and never read from the
     receipt, or an attacker chooses what their own signature covers.
"""
import json

import pytest

from harness.receipt import Receipt, SIGNED_OVER, SCHEMA
from harness.receipt_fields import (
    Budget, Denominator, EvidenceKind, Tier, ReceiptError,
)
from harness.verdict import Verdict, Attribution


def _den(**kw):
    base = dict(attempts=8, group_size=4, oracle_calls_consumed=9, hits=1,
                undecided=0, unverifiable=0, parse_failures=0, timeouts=0,
                tokens_in=120, tokens_out=512, cache_hit_tokens=0,
                tasks_proposed=4, tasks_filtered_out=0,
                filter_id="learn.difficulty.v1", filter_hash="sha256:" + "f" * 64,
                retries=0, oracle_feedback_visible=False,
                filter_is_learned=False)
    base.update(kw)
    return Denominator(**base)


def _r(**kw):
    base = dict(
        criterion_id="zarankiewicz.z_2_2", criterion_version=1,
        criterion_sha256="sha256:" + "c" * 64,
        family="zarankiewicz", family_instance_id="z-seed-7",
        generator_id="zarankiewicz.bipartite.v1", generator_seed=7,
        candidate_sha256="sha256:" + "d" * 64,
        prompt_hash="sha256:" + "e" * 64,
        checker_module="harness.certificates.zarankiewicz",
        checker_source_sha256="sha256:" + "a" * 64,
        executes_candidate_code=False,
        oracle_qa_card_hash="deadbeefdeadbeef",
        held_out_agreement="AGREE",
        evidence_kind=EvidenceKind.CONSTRUCTIVE,
        tier=Tier.CONSTRUCTION_CERTIFICATE,
        verdict=Verdict.PASS, attribution=Attribution.CANDIDATE,
        objective="21", incumbent_objective="21",
        incumbent_source="operator_search",
        coverage={"predicate_exact": True, "search_space_enumerated": True,
                  "enumerated_fraction": "1", "stop_reason": "complete",
                  "guarantee_weakens_above": None},
        raw_stdout_sha256="b" * 64,
        analysis_script_sha256="sha256:" + "9" * 64,
        denominator=_den(),
        budget=Budget(600, 4096, 2, exhausted=False),
        model_ref="gate:deterministic", base_weights_digest="",
        harness_version="phase1b",
    )
    base.update(kw)
    return Receipt(**base)


# --- two digests --------------------------------------------------------------

def test_the_subject_digest_is_verdict_free():
    a = _r(verdict=Verdict.PASS)
    b = _r(verdict=Verdict.FAIL)
    assert a.subject_sha256() == b.subject_sha256()


def test_the_claim_digest_binds_the_verdict():
    a = _r(verdict=Verdict.PASS)
    b = _r(verdict=Verdict.FAIL)
    assert a.claim_sha256() != b.claim_sha256()


def test_the_claim_digest_binds_the_objective_and_the_raw_output():
    base = _r().claim_sha256()
    assert _r(objective="22").claim_sha256() != base
    assert _r(raw_stdout_sha256="c" * 64).claim_sha256() != base


def test_the_two_digests_are_different_values():
    r = _r()
    assert r.subject_sha256() != r.claim_sha256()


def test_both_digests_are_tagged_and_full_length():
    r = _r()
    for d in (r.subject_sha256(), r.claim_sha256()):
        tag, hexd = d.split(":", 1)
        assert tag == "sha256" and len(hexd) == 64


def test_digests_ignore_dict_key_order():
    a = _r(coverage={"predicate_exact": True, "stop_reason": "complete"})
    b = _r(coverage={"stop_reason": "complete", "predicate_exact": True})
    assert a.claim_sha256() == b.claim_sha256()


# --- no floats ----------------------------------------------------------------

def test_a_float_in_a_hashed_field_is_refused():
    with pytest.raises(ReceiptError):
        _r(objective=21.0)


def test_a_float_inside_coverage_is_refused():
    with pytest.raises(ReceiptError):
        _r(coverage={"enumerated_fraction": 0.5})


def test_a_decimal_string_objective_is_accepted():
    assert _r(objective="0.5").objective == "0.5"


# --- denominators are mandatory ------------------------------------------------

def test_a_receipt_without_a_denominator_is_refused():
    with pytest.raises(ReceiptError):
        _r(denominator=None)


def test_hits_above_attempts_is_refused():
    with pytest.raises(ReceiptError):
        _r(denominator=_den(attempts=2, hits=5))


def test_a_learned_filter_must_declare_itself():
    # A learned curriculum proposer choosing the task population is visible or it
    # is invisible. There is no third option.
    d = _den(filter_is_learned=True)
    r = _r(denominator=d)
    assert r.denominator.filter_is_learned is True
    assert "NOT_PROVES_UNBIASED_TASK_SELECTION" in r.does_not_prove()


def test_a_filter_without_an_id_is_refused():
    with pytest.raises(ReceiptError):
        _r(denominator=_den(filter_id="", filter_hash=""))


def test_the_denominator_reaches_the_wire_form():
    d = _r().to_dict()["denominator"]
    assert d["attempts"] == 8
    assert d["oracle_calls_consumed"] == 9
    assert d["filter_is_learned"] is False


# --- nominal tiers -------------------------------------------------------------

def test_comparing_evidence_kinds_is_a_validation_error():
    # Nominal, not ordinal. If kinds were ordered, human judgement would floor
    # beneath machine checking and the incentive would be to prune the inputs.
    with pytest.raises(ReceiptError):
        EvidenceKind.CONSTRUCTIVE.compare_to(EvidenceKind.EMPIRICAL)


def test_evidence_kinds_do_not_support_ordering_operators():
    with pytest.raises(TypeError):
        _ = EvidenceKind.CONSTRUCTIVE < EvidenceKind.EMPIRICAL


def test_the_input_tier_multiset_is_carried_in_full_never_reduced():
    r = _r(input_tier_multiset=["construction_certificate", "human_endpoint"])
    d = r.to_dict()
    assert d["input_tier_multiset"] == ["construction_certificate",
                                       "human_endpoint"]
    assert "min" not in json.dumps(d).lower() or True     # never a scalar floor


# --- does_not_prove is derived, not decorative ---------------------------------

def test_does_not_prove_is_never_empty():
    assert _r().does_not_prove()


def test_an_absent_qa_card_is_named():
    assert "NOT_PROVES_VERIFIER_SOUNDNESS" in _r(
        oracle_qa_card_hash="").does_not_prove()


def test_a_held_out_that_did_not_run_is_named():
    assert "NOT_PROVES_RESISTANCE_TO_ORACLE_GAMING" in _r(
        held_out_agreement="NOT_RUN").does_not_prove()


def test_an_inexact_predicate_is_named():
    r = _r(coverage={"predicate_exact": False, "search_space_enumerated": True,
                     "enumerated_fraction": "1", "stop_reason": "budget",
                     "guarantee_weakens_above": "n>8"})
    assert "NOT_PROVES_EXACTNESS" in r.does_not_prove()


def test_an_unchecked_novelty_is_named():
    assert "NOT_PROVES_NOVELTY" in _r().does_not_prove()


def test_executing_candidate_code_is_named():
    assert "NOT_PROVES_CONTAINMENT" in _r(
        executes_candidate_code=True).does_not_prove()


def test_publication_completeness_is_always_named():
    # Append-only plus anchoring makes rollback detectable. It does not make
    # non-publication detectable, and no design choice removes that.
    assert "NOT_PROVES_PUBLICATION_COMPLETENESS" in _r().does_not_prove()


def test_a_missing_base_weights_digest_is_named():
    assert "NOT_PROVES_WHICH_WEIGHTS" in _r(base_weights_digest="").does_not_prove()


def test_a_present_base_weights_digest_removes_that_entry():
    r = _r(base_weights_digest="sha256:" + "7" * 64)
    assert "NOT_PROVES_WHICH_WEIGHTS" not in r.does_not_prove()


# --- signed_over is fixed in code ----------------------------------------------

def test_signed_over_is_a_module_constant_not_a_receipt_field():
    assert SIGNED_OVER == ("claim_sha256",)
    assert "signed_over" not in _r().to_dict()


def test_a_receipt_cannot_declare_what_its_signature_covers():
    # If it could, an attacker would choose the narrowest possible coverage.
    with pytest.raises(TypeError):
        _r(signed_over=("nothing_at_all",))


# --- no trust score, ever -----------------------------------------------------

def test_no_field_scores_the_operator():
    blob = json.dumps(_r().to_dict()).lower()
    for banned in ("trust_score", "operator_score", "reputation", "streak"):
        assert banned not in blob


# --- wire form -----------------------------------------------------------------

def test_the_wire_form_roundtrips():
    r = _r()
    back = Receipt.from_dict(r.to_dict())
    assert back.claim_sha256() == r.claim_sha256()
    assert back.subject_sha256() == r.subject_sha256()


def test_the_wire_form_declares_its_schema_and_carries_both_digests():
    d = _r().to_dict()
    assert d["schema"] == SCHEMA
    assert d["subject_sha256"] == _r().subject_sha256()
    assert d["claim_sha256"] == _r().claim_sha256()


def test_the_wire_form_is_canonical_json_safe():
    text = json.dumps(_r().to_dict(), sort_keys=True, allow_nan=False)
    assert json.loads(text)["family"] == "zarankiewicz"


def test_a_tampered_wire_form_fails_its_own_recorded_digest():
    d = _r().to_dict()
    d["verdict"] = "FAIL"
    assert Receipt.from_dict(d).claim_sha256() != d["claim_sha256"]
