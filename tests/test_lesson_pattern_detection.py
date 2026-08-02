"""Tests for sophisticated pattern detection: semantic and temporal."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

from harness.lesson import KIND_INTENT_OUTCOME, build_lesson
from harness.lesson_store import LessonStore

_DIGEST = "a" * 64


def _make(claim: str, **overrides) -> dict:
    defaults = dict(
        kind=KIND_INTENT_OUTCOME,
        source_organ="accountable-surface",
        source_refs=[{"organ": "a", "ref": "r", "digest": _DIGEST}],
        claim=claim,
    )
    defaults.update(overrides)
    return build_lesson(**defaults)


# --- semantic similarity ---------------------------------------------------


def test_semantic_groups_near_match_claims():
    """Two claims sharing most content words form one semantic pattern."""
    store = LessonStore()
    store.append(_make("allowed action rolled back: target mismatch"))
    store.append(_make("allowed action rolled back: digest drift"))
    pats = store.patterns_semantic(threshold=0.5)
    assert len(pats) == 1
    assert pats[0].repetition_count == 2


def test_semantic_does_not_group_unrelated_claims():
    """Claims with <30% token overlap stay separate."""
    store = LessonStore()
    store.append(_make("allowed action rolled back: target mismatch"))
    store.append(_make("memory drifted from source: url changed"))
    pats = store.patterns_semantic(threshold=0.5)
    # Neither reaches min_group=2 when separate
    assert pats == []


def test_semantic_threshold_controls_grouping():
    """At a high threshold, only near-identical claims group."""
    store = LessonStore()
    store.append(_make("action rolled back target mismatch here"))
    store.append(_make("action rolled back digest drift there"))
    # Shares "action", "rolled", "back" = 3 of 7 unique -> ~0.43
    assert len(store.patterns_semantic(threshold=0.3)) == 1
    assert len(store.patterns_semantic(threshold=0.6)) == 0


def test_semantic_single_instance_does_not_form_pattern():
    store = LessonStore()
    store.append(_make("a unique claim"))
    assert store.patterns_semantic() == []


def test_semantic_unions_transitively():
    """A ~ B and B ~ C merge into one group even if A ~ C is below threshold."""
    store = LessonStore()
    store.append(_make("action rolled back target mismatch issue"))
    store.append(_make("action rolled back target mismatch bug"))  # high overlap with #1
    store.append(_make("action rolled back digest drift problem"))  # overlaps with #2
    pats = store.patterns_semantic(threshold=0.3)
    assert len(pats) == 1
    assert pats[0].repetition_count == 3


# --- temporal decay --------------------------------------------------------


def _make_with_date(claim: str, days_ago: int) -> dict:
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return _make(claim, created_at=dt.isoformat())


def test_temporal_decay_weights_recent_lessons_higher():
    """A recent pattern ranks above a less-recent one with the same count."""
    store = LessonStore()
    # Very recent pair
    store.append(_make_with_date("recent failure", days_ago=1))
    store.append(_make_with_date("recent failure", days_ago=2))
    # Less recent pair (still within cutoff, lower weight)
    store.append(_make_with_date("older failure", days_ago=20))
    store.append(_make_with_date("older failure", days_ago=21))
    pats = store.patterns_temporal()
    assert len(pats) == 2
    # More-recent pattern should have higher weight and rank first
    assert pats[0].weight > pats[1].weight
    assert "recent" in pats[0].claim_normalized


def test_temporal_old_lessons_do_not_form_patterns_alone():
    """A single old lesson (past cutoff) contributes weight 0."""
    store = LessonStore()
    store.append(_make_with_date("ancient failure", days_ago=100))
    store.append(_make_with_date("ancient failure", days_ago=101))
    # Both past 90-day cutoff -> weight 0 each -> total 0 < threshold 2
    pats = store.patterns_temporal()
    assert pats == []


def test_temporal_mixed_recent_and_old_groups_by_weight():
    """A group with 1 recent + 1 old lesson has lower weight than 2 recent."""
    store = LessonStore()
    store.append(_make_with_date("mixed failure", days_ago=1))
    store.append(_make_with_date("mixed failure", days_ago=80))
    pats = store.patterns_temporal()
    assert len(pats) == 1
    # Weight is > 0 (recent dominates) but < 2.0 (would be 2 fresh lessons)
    assert 0 < pats[0].weight < 2.0


def test_temporal_improvement_feed_carries_window_note():
    """The temporal feed_summary notes the decay window."""
    store = LessonStore()
    store.append(_make_with_date("temporal test", days_ago=5))
    store.append(_make_with_date("temporal test", days_ago=10))
    feed = store.improvement_feed(temporal=True)
    assert "temporal decay" in feed["feed_summary"]
    assert len(feed["improvement_candidates"]) >= 1


def test_temporal_future_dated_lesson_treated_as_fresh():
    """A future-dated lesson (clock skew) gets weight 1.0, not negative."""
    future = datetime.now(timezone.utc) + timedelta(days=1)
    store = LessonStore()
    store.append(_make("future failure", created_at=future.isoformat()))
    store.append(_make("future failure", created_at=future.isoformat()))
    pats = store.patterns_temporal()
    assert len(pats) == 1
    assert pats[0].weight == 2.0  # both fresh


# --- backward compatibility ------------------------------------------------


def test_exact_patterns_unchanged():
    """The existing patterns() still does exact match (backward-compatible)."""
    store = LessonStore()
    store.append(_make("allowed action rolled back: target mismatch"))
    store.append(_make("allowed action rolled back: digest drift"))
    # Exact match: different claims -> no pattern at threshold 2
    assert store.patterns() == []


def test_pattern_to_dict_includes_weight():
    """Pattern.to_dict carries the weight field (0.0 for exact patterns)."""
    store = LessonStore()
    store.append(_make("same failure"))
    store.append(_make("same failure"))
    pats = store.patterns()
    d = pats[0].to_dict()
    assert "weight" in d
    assert d["weight"] == 0.0  # exact patterns have no weight
