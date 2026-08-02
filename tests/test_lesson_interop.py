"""Tests for the lesson spine entry (organ-bundle interop)."""
from __future__ import annotations

import json

from harness.lesson import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MODERATE,
    EVIDENCE_REPEATED,
    KIND_INTENT_OUTCOME,
    STATUS_ADMITTED,
    STATUS_APPLIED,
    STATUS_RETIRED,
    STATUS_SURFACED,
    build_lesson,
)
from harness.lesson_interop import (
    ORGAN,
    SPINE_KIND,
    lesson_bundle,
    lesson_entry,
    validate_lesson_entry,
)

_DIGEST = "a" * 64


def _make(**overrides) -> dict:
    defaults = dict(
        kind=KIND_INTENT_OUTCOME,
        source_organ="accountable-surface",
        source_refs=[{"organ": "accountable-surface", "ref": "cert", "digest": _DIGEST}],
        claim="allowed action diverged",
        evidence_class="single-instance",
        repetition_count=1,
        status=STATUS_SURFACED,
    )
    defaults.update(overrides)
    return build_lesson(**defaults)


# --- entry shape -----------------------------------------------------------


def test_entry_has_seven_fields():
    entry = lesson_entry(_make())
    expected = {"entry_id", "organ_id", "receipt_kind", "status", "payload_sha256", "summary", "payload_ref"}
    assert set(entry.keys()) == expected


def test_entry_organ_and_kind():
    entry = lesson_entry(_make())
    assert entry["organ_id"] == ORGAN
    assert entry["receipt_kind"] == SPINE_KIND


def test_entry_payload_sha_is_seal_hash():
    lesson = _make()
    entry = lesson_entry(lesson)
    assert entry["payload_sha256"] == lesson["seal_hash"]


# --- status mapping --------------------------------------------------------


def test_surfaced_low_confidence_maps_to_unverified():
    # single-instance + count 1 => low confidence => surfaced low => unverified
    lesson = _make(evidence_class="single-instance", repetition_count=1, status=STATUS_SURFACED)
    assert lesson["seal_body"]["confidence"] == CONFIDENCE_LOW
    entry = lesson_entry(lesson)
    assert entry["status"] == "unverified"


def test_surfaced_moderate_maps_to_needs_human():
    lesson = _make(
        evidence_class="repeated",
        repetition_count=3,
        status=STATUS_SURFACED,
    )
    entry = lesson_entry(lesson)
    # repeated + 3 => moderate confidence => surfaced moderate => needs-human
    assert lesson["seal_body"]["confidence"] == CONFIDENCE_MODERATE
    assert entry["status"] == "needs-human"


def test_admitted_maps_to_pass():
    entry = lesson_entry(_make(status=STATUS_ADMITTED))
    assert entry["status"] == "pass"


def test_applied_maps_to_pass():
    entry = lesson_entry(_make(status=STATUS_APPLIED))
    assert entry["status"] == "pass"


def test_retired_maps_to_not_applicable():
    entry = lesson_entry(_make(status=STATUS_RETIRED))
    assert entry["status"] == "not-applicable"


# --- validation ------------------------------------------------------------


def test_valid_entry_validates():
    entry = lesson_entry(_make())
    assert validate_lesson_entry(entry) is True


def test_wrong_organ_fails():
    entry = lesson_entry(_make())
    entry["organ_id"] = "wrong"
    assert validate_lesson_entry(entry) is False


def test_wrong_kind_fails():
    entry = lesson_entry(_make())
    entry["receipt_kind"] = "learn-receipt"  # not learn-lesson
    assert validate_lesson_entry(entry) is False


def test_bad_digest_fails():
    entry = lesson_entry(_make())
    entry["payload_sha256"] = "not-a-hash"
    assert validate_lesson_entry(entry) is False


def test_missing_field_fails():
    entry = lesson_entry(_make())
    del entry["summary"]
    assert validate_lesson_entry(entry) is False


def test_extra_field_fails():
    entry = lesson_entry(_make())
    entry["extra"] = "no"
    assert validate_lesson_entry(entry) is False


# --- bundle ----------------------------------------------------------------


def test_bundle_round_trips():
    lessons = [_make(claim="a"), _make(claim="b"), _make(claim="c")]
    bundle = lesson_bundle(lessons)
    assert bundle["organ_bundle_version"] == "0.1"
    assert len(bundle["entries"]) == 3
    assert all(validate_lesson_entry(e) for e in bundle["entries"])
    assert len(bundle["edges"]) == 2  # observed-after chain


def test_bundle_entries_carry_real_seal_hashes():
    lessons = [_make(claim="x")]
    bundle = lesson_bundle(lessons)
    assert bundle["entries"][0]["payload_sha256"] == lessons[0]["seal_hash"]


# --- cross-validation against proof-surface's real organ-bundle validator ---

def test_lesson_bundle_validates_against_proof_surface():
    """The lesson bundle must validate against proof-surface's real validator.

    This is the seam test: after adding 'learn-lesson' to RECEIPT_KINDS, a
    bundle of lesson entries validates with zero issues. If proof-surface is not
    installed, this test is skipped (the spine contract is still enforced by
    validate_lesson_entry above).
    """
    pytest = __import__("pytest")
    try:
        from proof_surface import validate_organ_receipt_bundle
    except ImportError:
        pytest.skip("proof-surface not installed; spine contract enforced locally")

    lessons = [_make(claim="a"), _make(claim="b")]
    bundle = lesson_bundle(
        lessons,
        bundle_id="lesson-bundle-cross-val",
        generated_at="2026-08-01T00:00:00Z",
    )
    issues = validate_organ_receipt_bundle(bundle)
    assert issues == [], f"proof-surface rejected lesson bundle: {issues}"


def test_lesson_bundle_rejects_bad_kind_against_proof_surface():
    """A tampered receipt_kind is still rejected by proof-surface's validator."""
    pytest = __import__("pytest")
    try:
        from proof_surface import validate_organ_receipt_bundle
    except ImportError:
        pytest.skip("proof-surface not installed")

    lessons = [_make(claim="a")]
    bundle = lesson_bundle(lessons)
    bundle["entries"][0]["receipt_kind"] = "self-declared"
    issues = validate_organ_receipt_bundle(bundle)
    assert len(issues) > 0
