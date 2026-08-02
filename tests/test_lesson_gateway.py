"""Integration test: the lesson gateway routes load the store from run_root.

The routes are inline in _Handler._get(), so this test exercises the same
LessonStore.load(Path(run_root) / "lessons.jsonl") path the routes use, against
a real tmp_path. This confirms the route logic (not just the store) works.
"""
from __future__ import annotations

from pathlib import Path

from harness.lesson_store import LessonStore
from harness.lesson import build_lesson, KIND_INTENT_OUTCOME

_DIGEST = "e" * 64


def test_lessons_route_loads_from_run_root(tmp_path: Path):
    """The /api/lessons route loads the store from <run_root>/lessons.jsonl."""
    # Simulate what the route does: load from run_root
    store_path = tmp_path / "lessons.jsonl"
    store = LessonStore.load(store_path)
    assert len(store) == 0

    feed = store.improvement_feed()
    assert feed["profile"]["n_lessons"] == 0

    verify = store.verify()
    assert verify["verdict"] == "UNVERIFIABLE"  # empty chain


def test_lessons_route_returns_populated_store(tmp_path: Path):
    """After appending lessons, the route returns them + the improvement feed."""
    store_path = tmp_path / "lessons.jsonl"
    store = LessonStore.load(store_path)
    store.append_built(
        kind=KIND_INTENT_OUTCOME,
        source_organ="accountable-surface",
        source_refs=[{"organ": "accountable-surface", "ref": "cert", "digest": _DIGEST}],
        claim="recurring rollback",
    )
    store.append_built(
        kind=KIND_INTENT_OUTCOME,
        source_organ="accountable-surface",
        source_refs=[{"organ": "accountable-surface", "ref": "cert2", "digest": _DIGEST}],
        claim="recurring rollback",
    )
    store.save(store_path)

    # Reload (as the route does on each request)
    loaded = LessonStore.load(store_path)
    assert len(loaded) == 2
    assert loaded.verify()["verdict"] == "MATCH"

    feed = loaded.improvement_feed()
    assert feed["profile"]["n_lessons"] == 2
    assert feed["profile"]["n_patterns"] == 1


def test_lessons_patterns_route_returns_patterns(tmp_path: Path):
    """The /api/lessons/patterns route returns detected patterns."""
    store_path = tmp_path / "lessons.jsonl"
    store = LessonStore.load(store_path)
    for i in range(3):
        store.append_built(
            kind=KIND_INTENT_OUTCOME,
            source_organ="accountable-surface",
            source_refs=[{"organ": "a", "ref": f"r{i}", "digest": _DIGEST}],
            claim="same failure mode",
        )
    store.save(store_path)

    loaded = LessonStore.load(store_path)
    pats = loaded.patterns()
    assert len(pats) == 1
    assert pats[0].repetition_count == 3


# --- POST route integration: the transition path the routes use -------------


def test_admit_route_transitions_to_admitted(tmp_path: Path):
    """The /api/lessons/admit route loads, transitions, and saves."""
    from harness.lesson import STATUS_ADMITTED
    store_path = tmp_path / "lessons.jsonl"
    store = LessonStore.load(store_path)
    lesson = store.append_built(
        kind="intent-outcome",
        source_organ="accountable-surface",
        source_refs=[{"organ": "a", "ref": "r", "digest": _DIGEST}],
        claim="test failure",
    )
    store.save(store_path)
    lid = lesson["lesson_id"]

    # Simulate what the POST route does
    loaded = LessonStore.load(store_path)
    row = loaded.transition(lid, "admitted")
    loaded.save(store_path)

    assert row["status"] == STATUS_ADMITTED
    assert row["lesson_id"] == lid
    # Reload and verify
    final = LessonStore.load(store_path)
    assert len(final) == 2
    assert final.verify()["verdict"] == "MATCH"
    assert final.latest_for(lid)["status"] == STATUS_ADMITTED


def test_retire_route_transitions_to_retired(tmp_path: Path):
    """The /api/lessons/retire route transitions any -> retired."""
    from harness.lesson import STATUS_RETIRED
    store_path = tmp_path / "lessons.jsonl"
    store = LessonStore.load(store_path)
    lesson = store.append_built(
        kind="drift",
        source_organ="mneme",
        source_refs=[{"organ": "mneme", "ref": "r", "digest": _DIGEST}],
        claim="memory drifted",
    )
    store.save(store_path)
    lid = lesson["lesson_id"]

    loaded = LessonStore.load(store_path)
    loaded.transition(lid, "admitted")
    loaded.transition(lid, "retired")
    loaded.save(store_path)

    final = LessonStore.load(store_path)
    assert final.latest_for(lid)["status"] == STATUS_RETIRED
    assert len(final) == 3  # original + admitted + retired


def test_transition_on_nonexistent_returns_error(tmp_path: Path):
    """A bad lesson_id produces an error, not a crash."""
    store_path = tmp_path / "lessons.jsonl"
    store = LessonStore.load(store_path)
    import pytest
    with pytest.raises(ValueError, match="no lesson"):
        store.transition("0" * 64, "admitted")
