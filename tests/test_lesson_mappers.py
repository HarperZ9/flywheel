"""Tests for the intent-vs-outcome mapper (accountable-surface -> lessons)."""
from __future__ import annotations

from harness.lesson import KIND_INTENT_OUTCOME, MATCH, verify_lesson
from harness.lesson_mappers import (
    append_intent_outcome_lessons,
    intent_outcome_lessons,
)
from harness.lesson_store import LessonStore

_DIGEST = "a" * 64


def _outcome(**overrides) -> dict:
    """A minimal ActuationOutcome dict projection."""
    defaults = dict(
        acted=True,
        decision="allow",
        verified=False,
        verdict="failed",
        rolled_back=True,
        reasons=["after-state digest mismatch"],
        before_digest=_DIGEST,
        after_digest="b" * 64,
        grounding={"subject": "apply config patch", "confidence": "grounded", "digest": _DIGEST},
        certificate={"certificate_id": "cert-001"},
    )
    defaults.update(overrides)
    return defaults


# --- the honest null: clean runs produce zero lessons ----------------------


def test_clean_run_produces_zero_lessons():
    """All outcomes pass: no divergence, no lessons. The absence is meaningful."""
    outcomes = [
        _outcome(decision="allow", verdict="pass", rolled_back=False, verified=True),
        _outcome(decision="allow", verdict="pass", rolled_back=False, verified=True),
    ]
    assert intent_outcome_lessons(outcomes) == []


def test_denied_action_is_not_a_divergence():
    outcomes = [_outcome(decision="deny")]
    assert intent_outcome_lessons(outcomes) == []


def test_needs_human_is_not_a_divergence():
    outcomes = [_outcome(decision="needs-human")]
    assert intent_outcome_lessons(outcomes) == []


# --- divergence produces a verifiable lesson -------------------------------


def test_failed_action_produces_lesson():
    outcomes = [_outcome(verdict="failed", rolled_back=False)]
    lessons = intent_outcome_lessons(outcomes)
    assert len(lessons) == 1
    v = verify_lesson(lessons[0])
    assert v["verdict"] == MATCH


def test_rolled_back_action_produces_lesson():
    outcomes = [_outcome(verdict="failed", rolled_back=True, reasons=[])]
    lessons = intent_outcome_lessons(outcomes)
    assert len(lessons) == 1
    assert "rolled back" in lessons[0]["seal_body"]["claim"]


def test_lesson_source_ref_uses_after_digest():
    outcomes = [_outcome(after_digest="c" * 64)]
    lessons = intent_outcome_lessons(outcomes)
    ref = lessons[0]["seal_body"]["source_refs"][0]
    assert ref["digest"] == "c" * 64
    assert ref["organ"] == "accountable-surface"


def test_lesson_claim_derived_from_reasons():
    outcomes = [_outcome(reasons=["target mismatch", "digest drift"])]
    lessons = intent_outcome_lessons(outcomes)
    claim = lessons[0]["seal_body"]["claim"]
    assert "target mismatch" in claim
    assert "digest drift" in claim


def test_lesson_kind_is_intent_outcome():
    outcomes = [_outcome()]
    lessons = intent_outcome_lessons(outcomes)
    assert lessons[0]["seal_body"]["kind"] == KIND_INTENT_OUTCOME


# --- rationale projection --------------------------------------------------


def test_rationale_projected_from_grounding():
    outcomes = [_outcome(grounding={"subject": "patch config", "confidence": "weak", "digest": _DIGEST})]
    lessons = intent_outcome_lessons(outcomes)
    rationale = lessons[0]["seal_body"]["rationale"]
    assert rationale is not None
    assert rationale["stated_intent"] == "patch config"
    assert rationale["confidence"] == "weak"


def test_rationale_null_when_no_grounding():
    outcomes = [_outcome(grounding=None)]
    lessons = intent_outcome_lessons(outcomes)
    assert lessons[0]["seal_body"]["rationale"] is None


def test_rationale_null_when_grounding_has_no_subject():
    outcomes = [_outcome(grounding={"confidence": "grounded", "digest": _DIGEST})]
    lessons = intent_outcome_lessons(outcomes)
    assert lessons[0]["seal_body"]["rationale"] is None


# --- skip when no digest (unverifiable lesson) -----------------------------


def test_outcome_without_any_digest_is_skipped():
    """A lesson with no witnessed digest is unverifiable; skip honestly."""
    outcomes = [_outcome(before_digest="", after_digest=None)]
    assert intent_outcome_lessons(outcomes) == []


# --- append helper ---------------------------------------------------------


def test_append_helper_adds_to_store():
    store = LessonStore()
    outcomes = [_outcome(), _outcome(verdict="pass", rolled_back=False)]
    appended = append_intent_outcome_lessons(store, outcomes)
    assert len(appended) == 1  # only the divergence
    assert len(store) == 1
    assert store.verify()["verdict"] == MATCH


# --- confidence is honestly low for a single instance ---------------------


def test_single_divergence_is_low_confidence():
    outcomes = [_outcome()]
    lessons = intent_outcome_lessons(outcomes)
    assert lessons[0]["seal_body"]["confidence"] == "low"


def test_repeated_divergences_form_pattern_in_store():
    store = LessonStore()
    # Two outcomes with identical reasons -> same normalized claim -> pattern
    for i in range(2):
        append_intent_outcome_lessons(
            store,
            [_outcome(reasons=["target mismatch"], certificate={"certificate_id": f"c{i}"})],
        )
    pats = store.patterns()
    assert len(pats) == 1
    assert pats[0].repetition_count == 2
