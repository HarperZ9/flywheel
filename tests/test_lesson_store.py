"""Tests for the lesson store: append-only chain, patterns, verify, persistence."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.lesson import (
    CONFIDENCE_MODERATE,
    EVIDENCE_SINGLE,
    GENESIS_HASH,
    KIND_DRIFT,
    KIND_INTENT_OUTCOME,
    MATCH,
    STATUS_SURFACED,
    TAMPERED,
    build_lesson,
)
from harness.lesson_store import DEFAULT_PATTERN_THRESHOLD, LessonStore

_DIGEST_A = "a" * 64
_DIGEST_B = "b" * 64


def _make(**overrides) -> dict:
    defaults = dict(
        kind=KIND_INTENT_OUTCOME,
        source_organ="accountable-surface",
        source_refs=[{"organ": "accountable-surface", "ref": "cert", "digest": _DIGEST_A}],
        claim="allowed action rolled back",
        evidence_class=EVIDENCE_SINGLE,
        repetition_count=1,
    )
    defaults.update(overrides)
    return build_lesson(**defaults)


# --- append + chain --------------------------------------------------------


def test_append_sets_seq_and_prev_hash():
    store = LessonStore()
    l0 = store.append(_make(claim="first"))
    l1 = store.append(_make(claim="second"))
    assert l0["seq"] == 0
    assert l0["prev_hash"] == GENESIS_HASH
    assert l1["seq"] == 1
    assert l1["prev_hash"] == l0["seal_hash"]


def test_append_rejects_unverifiable_lesson():
    store = LessonStore()
    bad = _make()
    bad["seal_body"]["claim"] = "tampered"  # breaks the seal
    with pytest.raises(ValueError, match="does not verify"):
        store.append(bad)


def test_verify_valid_chain():
    store = LessonStore()
    store.append(_make(claim="a"))
    store.append(_make(claim="b"))
    store.append(_make(claim="c"))
    result = store.verify()
    assert result["verdict"] == MATCH
    assert result["n"] == 3


def test_verify_detects_broken_chain():
    store = LessonStore()
    store.append(_make(claim="a"))
    store.append(_make(claim="b"))
    # tamper the chain link
    store._lessons[1]["prev_hash"] = "x" * 64
    result = store.verify()
    assert result["verdict"] == TAMPERED


# --- queries ---------------------------------------------------------------


def test_by_source_organ():
    store = LessonStore()
    store.append(_make(source_organ="accountable-surface", claim="x"))
    store.append(_make(source_organ="mneme", claim="y"))
    assert len(store.by_source_organ("accountable-surface")) == 1
    assert len(store.by_source_organ("mneme")) == 1
    assert len(store.by_source_organ("forum")) == 0


def test_by_kind():
    store = LessonStore()
    store.append(_make(kind=KIND_INTENT_OUTCOME, claim="x"))
    store.append(_make(kind=KIND_DRIFT, source_organ="mneme", claim="y"))
    assert len(store.by_kind(KIND_INTENT_OUTCOME)) == 1
    assert len(store.by_kind(KIND_DRIFT)) == 1


# --- patterns: the feedback edge ------------------------------------------


def test_single_instance_does_not_form_pattern():
    """A single instance does not auto-promote to a pattern."""
    store = LessonStore()
    store.append(_make(claim="allowed action rolled back"))
    assert store.patterns() == []


def test_two_converging_lessons_form_pattern():
    store = LessonStore()
    store.append(_make(claim="allowed action rolled back"))
    store.append(_make(claim="Allowed Action Rolled Back"))  # same normalized
    pats = store.patterns()
    assert len(pats) == 1
    assert pats[0].repetition_count == 2
    assert pats[0].confidence == CONFIDENCE_MODERATE


def test_different_claims_do_not_group():
    store = LessonStore()
    store.append(_make(claim="allowed action rolled back"))
    store.append(_make(claim="memory drifted from source", source_organ="mneme"))
    assert len(store.patterns()) == 0  # neither reaches threshold alone


def test_pattern_threshold_is_respected():
    store = LessonStore()
    for i in range(3):
        store.append(_make(claim="recurring failure", source_refs=[
            {"organ": "a", "ref": f"r{i}", "digest": _DIGEST_A}]))
    assert len(store.patterns(threshold=2)) == 1
    assert len(store.patterns(threshold=4)) == 0  # only 3 lessons


def test_patterns_sorted_most_converging_first():
    store = LessonStore()
    for _ in range(3):
        store.append(_make(claim="triple"))
    for _ in range(2):
        store.append(_make(claim="double"))
    pats = store.patterns()
    assert pats[0].repetition_count == 3
    assert pats[1].repetition_count == 2


def test_improvement_feed_shape_matches_telemetry():
    """The feed artifact mirrors telemetry.efficiency_feed: improvement_candidates: list[str]."""
    store = LessonStore()
    for _ in range(2):
        store.append(_make(claim="recurring rollback"))
    feed = store.improvement_feed()
    assert "improvement_candidates" in feed
    assert isinstance(feed["improvement_candidates"], list)
    assert len(feed["improvement_candidates"]) == 1
    assert "profile" in feed
    assert feed["profile"]["n_lessons"] == 2
    assert feed["profile"]["n_patterns"] == 1
    assert "feed_summary" in feed


def test_improvement_candidate_is_a_suggestion_not_an_applied_change():
    """The feedback edge surfaces for admission, it does not apply."""
    store = LessonStore()
    store.append(_make(claim="recurring rollback"))
    store.append(_make(claim="recurring rollback"))
    feed = store.improvement_feed()
    candidate = feed["improvement_candidates"][0]
    assert "review for systemic cause" in candidate


# --- persistence -----------------------------------------------------------


def test_save_load_round_trip(tmp_path: Path):
    path = tmp_path / "lessons.jsonl"
    store = LessonStore()
    store.append(_make(claim="first"))
    store.append(_make(claim="second"))
    store.save(path)

    loaded = LessonStore.load(path)
    assert len(loaded) == 2
    result = loaded.verify()
    assert result["verdict"] == MATCH


def test_load_empty_file_yields_empty_store(tmp_path: Path):
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")
    store = LessonStore.load(path)
    assert len(store) == 0


def test_load_nonexistent_yields_empty_store(tmp_path: Path):
    store = LessonStore.load(tmp_path / "nope.jsonl")
    assert len(store) == 0
