"""Tests for lesson status transitions (admit, apply, retire)."""
from __future__ import annotations

import pytest

from harness.lesson import (
    MATCH,
    STATUS_ADMITTED,
    STATUS_APPLIED,
    STATUS_RETIRED,
    STATUS_SURFACED,
    build_lesson,
)
from harness.lesson_store import LessonStore

_DIGEST = "a" * 64


def _make(claim: str = "recurring rollback", **overrides) -> dict:
    defaults = dict(
        kind="intent-outcome",
        source_organ="accountable-surface",
        source_refs=[{"organ": "a", "ref": "r", "digest": _DIGEST}],
        claim=claim,
    )
    defaults.update(overrides)
    return build_lesson(**defaults)


def _store_with_lesson(**overrides) -> tuple[LessonStore, str]:
    store = LessonStore()
    lesson = store.append(_make(**overrides))
    return store, lesson["lesson_id"]


# --- transition appends a new row ------------------------------------------


def test_transition_appends_new_row():
    store, lid = _store_with_lesson()
    assert len(store) == 1
    new = store.transition(lid, STATUS_ADMITTED)
    assert len(store) == 2
    assert new["status"] == STATUS_ADMITTED
    assert new["lesson_id"] == lid  # same content-addressed identity


def test_transition_preserves_seal_body():
    store, lid = _store_with_lesson()
    original = store.latest_for(lid)
    new = store.transition(lid, STATUS_ADMITTED)
    assert new["seal_hash"] == original["seal_hash"]
    assert new["seal_body"] == original["seal_body"]


def test_transition_chain_still_verifies():
    store, lid = _store_with_lesson()
    store.transition(lid, STATUS_ADMITTED)
    result = store.verify()
    assert result["verdict"] == MATCH
    assert result["n"] == 2


def test_latest_for_returns_current_status():
    store, lid = _store_with_lesson()
    store.transition(lid, STATUS_ADMITTED)
    store.transition(lid, STATUS_RETIRED)
    latest = store.latest_for(lid)
    assert latest["status"] == STATUS_RETIRED


# --- allowed transitions ---------------------------------------------------


def test_surfaced_to_admitted():
    store, lid = _store_with_lesson()
    new = store.transition(lid, STATUS_ADMITTED)
    assert new["status"] == STATUS_ADMITTED


def test_admitted_to_applied():
    store, lid = _store_with_lesson()
    store.transition(lid, STATUS_ADMITTED)
    new = store.transition(lid, STATUS_APPLIED)
    assert new["status"] == STATUS_APPLIED


def test_surfaced_to_retired():
    store, lid = _store_with_lesson()
    new = store.transition(lid, STATUS_RETIRED)
    assert new["status"] == STATUS_RETIRED


def test_admitted_to_retired():
    store, lid = _store_with_lesson()
    store.transition(lid, STATUS_ADMITTED)
    new = store.transition(lid, STATUS_RETIRED)
    assert new["status"] == STATUS_RETIRED


def test_applied_to_retired():
    store, lid = _store_with_lesson()
    store.transition(lid, STATUS_ADMITTED)
    store.transition(lid, STATUS_APPLIED)
    new = store.transition(lid, STATUS_RETIRED)
    assert new["status"] == STATUS_RETIRED


# --- illegal transitions ---------------------------------------------------


def test_retired_cannot_transition():
    store, lid = _store_with_lesson()
    store.transition(lid, STATUS_RETIRED)
    with pytest.raises(ValueError, match="terminal"):
        store.transition(lid, STATUS_ADMITTED)


def test_surfaced_cannot_skip_to_applied():
    store, lid = _store_with_lesson()
    with pytest.raises(ValueError, match="not allowed"):
        store.transition(lid, STATUS_APPLIED)


def test_invalid_status_raises():
    store, lid = _store_with_lesson()
    with pytest.raises(ValueError):
        store.transition(lid, "bogus-status")


def test_nonexistent_lesson_raises():
    store = LessonStore()
    with pytest.raises(ValueError, match="no lesson"):
        store.transition("0" * 64, STATUS_ADMITTED)


# --- latest_for on empty store --------------------------------------------


def test_latest_for_nonexistent_returns_none():
    store = LessonStore()
    assert store.latest_for("0" * 64) is None


def test_latest_for_on_empty_store():
    store = LessonStore()
    assert store.latest_for("anything") is None


# --- persistence round-trip with transitions ------------------------------


def test_transition_survives_save_load(tmp_path):
    from pathlib import Path
    path = tmp_path / "lessons.jsonl"
    store, lid = _store_with_lesson()
    store.transition(lid, STATUS_ADMITTED)
    store.save(path)

    loaded = LessonStore.load(path)
    assert len(loaded) == 2
    assert loaded.verify()["verdict"] == MATCH
    latest = loaded.latest_for(lid)
    assert latest["status"] == STATUS_ADMITTED
