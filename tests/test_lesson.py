"""Tests for the sealed lesson record (build + verify + chain).

Mirrors the tool-call receipt test posture: every claim has a falsifier. A
lesson is a claim derived from witnessed artifacts, sealed and chain-linked.
"""
from __future__ import annotations

import copy
import json

import pytest

from harness.lesson import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MODERATE,
    CONFIDENCE_UNKNOWN,
    EVIDENCE_CROSS_OPERATOR,
    EVIDENCE_REPEATED,
    EVIDENCE_SINGLE,
    GENESIS_HASH,
    KIND_DRIFT,
    KIND_INTENT_OUTCOME,
    MATCH,
    SCHEMA,
    STATUS_APPLIED,
    STATUS_SURFACED,
    TAMPERED,
    UNVERIFIABLE,
    build_lesson,
    derive_confidence,
    verify_lesson,
    verify_lesson_chain,
)

_DIGEST_A = "a" * 64
_DIGEST_B = "b" * 64


def _sample_lesson(**overrides) -> dict:
    """A minimal valid lesson derived from one witnessed artifact."""
    defaults = dict(
        kind=KIND_INTENT_OUTCOME,
        source_organ="accountable-surface",
        source_refs=[{"organ": "accountable-surface", "ref": "cert-001", "digest": _DIGEST_A}],
        claim="allowed action rolled back: target state did not match grounding",
        evidence_class=EVIDENCE_SINGLE,
        repetition_count=1,
        scope="single action; does not prove a systemic pattern",
        rationale=None,
        seq=0,
        prev_hash=GENESIS_HASH,
        status=STATUS_SURFACED,
        created_at="2026-08-01T00:00:00Z",
    )
    defaults.update(overrides)
    return build_lesson(**defaults)


# --- build + seal ----------------------------------------------------------


def test_build_lesson_produces_sealed_object():
    lesson = _sample_lesson()
    assert lesson["schema"] == SCHEMA
    assert len(lesson["seal_hash"]) == 64
    assert lesson["lesson_id"] == lesson["seal_hash"]  # content-addressed
    assert lesson["seal_body"]["confidence"] == CONFIDENCE_LOW  # derived, not asserted
    assert lesson["seal_body"]["rationale"] is None  # honest null


def test_seal_is_deterministic():
    l1 = _sample_lesson()
    l2 = _sample_lesson()
    assert l1["seal_hash"] == l2["seal_hash"]


def test_seal_changes_with_content():
    l1 = _sample_lesson(claim="lesson one")
    l2 = _sample_lesson(claim="lesson two")
    assert l1["seal_hash"] != l2["seal_hash"]


def test_seal_changes_with_different_source_ref_digest():
    l1 = _sample_lesson(source_refs=[{"organ": "a", "ref": "r1", "digest": _DIGEST_A}])
    l2 = _sample_lesson(source_refs=[{"organ": "a", "ref": "r1", "digest": _DIGEST_B}])
    assert l1["seal_hash"] != l2["seal_hash"]


# --- confidence derivation (the witnessing stamp) --------------------------


def test_derive_confidence_single_is_low():
    assert derive_confidence(EVIDENCE_SINGLE, 1) == CONFIDENCE_LOW


def test_derive_confidence_repeated_is_moderate():
    assert derive_confidence(EVIDENCE_REPEATED, 3) == CONFIDENCE_MODERATE


def test_derive_confidence_cross_operator_is_high():
    assert derive_confidence(EVIDENCE_CROSS_OPERATOR, 2) == CONFIDENCE_HIGH


def test_derive_confidence_unknown_for_uncheckable():
    assert derive_confidence("bogus", 0) == CONFIDENCE_UNKNOWN


def test_cross_operator_below_two_is_unknown():
    assert derive_confidence(EVIDENCE_CROSS_OPERATOR, 1) == CONFIDENCE_UNKNOWN


# --- verify: the falsifiers ------------------------------------------------


def test_seal_round_trips():
    v = verify_lesson(_sample_lesson())
    assert v["verdict"] == MATCH
    assert v["confidence"] == CONFIDENCE_LOW


def test_tampered_claim_breaks_seal():
    lesson = _sample_lesson()
    lesson["seal_body"]["claim"] = "tampered claim"
    v = verify_lesson(lesson)
    assert v["verdict"] == TAMPERED
    assert v["failure_class"] == "SEAL_MISMATCH"


def test_tampered_rationale_breaks_seal():
    lesson = _sample_lesson()
    lesson["seal_body"]["rationale"] = {"stated_intent": "fabricated"}
    v = verify_lesson(lesson)
    assert v["verdict"] == TAMPERED
    assert v["failure_class"] == "SEAL_MISMATCH"


def test_tampered_repetition_count_breaks_seal():
    lesson = _sample_lesson()
    lesson["seal_body"]["repetition_count"] = 99
    v = verify_lesson(lesson)
    assert v["verdict"] == TAMPERED


def test_lesson_id_mismatch_is_caught():
    lesson = _sample_lesson()
    lesson["lesson_id"] = "c" * 64  # wrong content address
    v = verify_lesson(lesson)
    assert v["verdict"] == UNVERIFIABLE
    assert "content-addressed" in v["detail"]


def test_inflated_confidence_is_caught():
    """confidence is derived, never asserted: a low-evidence lesson claiming high fails."""
    lesson = _sample_lesson()
    # single-instance + count 1 warrants low; forge it to high
    lesson["seal_body"]["confidence"] = CONFIDENCE_HIGH
    # recompute seal to pass the seal check, so we isolate the confidence rule
    import hashlib

    canonical = json.dumps(lesson["seal_body"], separators=(",", ":"), ensure_ascii=False).encode()
    lesson["seal_hash"] = hashlib.sha256(canonical).hexdigest()
    lesson["lesson_id"] = lesson["seal_hash"]
    v = verify_lesson(lesson)
    assert v["verdict"] == UNVERIFIABLE
    assert "inflated" in v["detail"]


def test_null_rationale_stays_null_through_round_trip():
    """A null rationale is honest, never fabricated into content on verify."""
    lesson = _sample_lesson(rationale=None)
    v = verify_lesson(lesson)
    assert v["verdict"] == MATCH
    assert lesson["seal_body"]["rationale"] is None


def test_present_rationale_round_trips():
    lesson = _sample_lesson(
        rationale={
            "stated_intent": "apply config patch",
            "options_considered": ["patch", "rebuild"],
            "chosen_option": "patch",
            "confidence": "moderate",
        }
    )
    v = verify_lesson(lesson)
    assert v["verdict"] == MATCH
    assert lesson["seal_body"]["rationale"]["chosen_option"] == "patch"


def test_source_ref_without_digest_is_rejected():
    with pytest.raises(ValueError, match="digest"):
        build_lesson(
            kind=KIND_DRIFT,
            source_organ="mneme",
            source_refs=[{"organ": "mneme", "ref": "mem-1"}],  # no digest
            claim="memory drifted from source",
        )


def test_invalid_kind_is_rejected():
    with pytest.raises(ValueError, match="kind"):
        build_lesson(
            kind="wishful-thinking",
            source_organ="flywheel",
            source_refs=[{"organ": "flywheel", "ref": "r", "digest": _DIGEST_A}],
            claim="claim",
        )


def test_empty_claim_is_rejected():
    with pytest.raises(ValueError, match="claim"):
        build_lesson(
            kind=KIND_DRIFT,
            source_organ="mneme",
            source_refs=[{"organ": "mneme", "ref": "r", "digest": _DIGEST_A}],
            claim="   ",
        )


# --- chain verification ----------------------------------------------------


def _chain_of(n: int) -> list[dict]:
    """Build a valid chain of n lessons, each linking to the prior."""
    lessons = []
    prev = GENESIS_HASH
    for i in range(n):
        lesson = build_lesson(
            kind=KIND_INTENT_OUTCOME,
            source_organ="accountable-surface",
            source_refs=[{"organ": "accountable-surface", "ref": f"cert-{i}", "digest": _DIGEST_A}],
            claim=f"lesson {i}",
            seq=i,
            prev_hash=prev,
        )
        lessons.append(lesson)
        prev = lesson["seal_hash"]
    return lessons


def test_valid_chain_verifies():
    chain = _chain_of(3)
    result = verify_lesson_chain(chain)
    assert result["verdict"] == MATCH
    assert result["n"] == 3
    assert all(r["verdict"] == MATCH for r in result["lessons"])


def test_broken_chain_link_is_rejected():
    chain = _chain_of(3)
    # tamper the middle lesson's prev_hash so it no longer links
    chain[1]["prev_hash"] = "d" * 64
    result = verify_lesson_chain(chain)
    assert result["verdict"] == TAMPERED
    assert any(r.get("failure_class") == "CHAIN_BROKEN" for r in result["lessons"])


def test_empty_chain_is_unverifiable():
    result = verify_lesson_chain([])
    assert result["verdict"] == UNVERIFIABLE


def test_chain_with_tampered_seal_is_rejected():
    chain = _chain_of(3)
    chain[1]["seal_body"]["claim"] = "tampered"
    result = verify_lesson_chain(chain)
    assert result["verdict"] == TAMPERED


def test_genesis_first_lesson_uses_genesis_hash():
    lesson = _sample_lesson(prev_hash=GENESIS_HASH, seq=0)
    v = verify_lesson(lesson)
    assert v["verdict"] == MATCH
