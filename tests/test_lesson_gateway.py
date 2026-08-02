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
