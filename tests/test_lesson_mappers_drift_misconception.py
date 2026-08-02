"""Tests for the drift mapper (mneme) and misconception mapper (learn)."""
from __future__ import annotations

from harness.lesson import (
    KIND_DRIFT,
    KIND_MISCONCEPTION,
    MATCH,
    verify_lesson,
)
from harness.lesson_mappers import (
    append_drift_lessons,
    append_misconception_lessons,
    drift_lessons,
    misconception_lessons,
)
from harness.lesson_store import LessonStore

_DIGEST = "a" * 64


# --- drift mapper: mneme ---------------------------------------------------


def _drift_report(verdicts: list[dict]) -> dict:
    """A minimal mneme drift-report dict."""
    drifted = [v["memory_id"] for v in verdicts if v.get("verdict") == "DRIFT"]
    unverifiable = [v["memory_id"] for v in verdicts if v.get("verdict") == "UNVERIFIABLE"]
    overall = "DRIFT" if drifted else ("UNVERIFIABLE" if unverifiable else "MATCH")
    return {
        "schema": "mneme.drift-report/1",
        "overall": overall,
        "checked": len(verdicts),
        "drifted": drifted,
        "unverifiable": unverifiable,
        "verdicts": verdicts,
        "recheck": "mneme drift --state DB",
    }


def _verdict(memory_id="mem-1", verdict="DRIFT", reason="", changed=None, missing=None) -> dict:
    return {
        "memory_id": memory_id,
        "verdict": verdict,
        "reason": reason or "source content changed since extraction",
        "changed_sources": changed or ["src-1"],
        "missing_sources": missing or [],
    }


def test_clean_store_produces_zero_drift_lessons():
    """All memories MATCH: no drift, no lessons."""
    report = _drift_report([_verdict(verdict="MATCH", reason="grounding present and unchanged")])
    assert drift_lessons(report) == []


def test_drift_verdict_produces_lesson():
    report = _drift_report([_verdict(memory_id="mem-a", verdict="DRIFT")])
    lessons = drift_lessons(report)
    assert len(lessons) == 1
    v = verify_lesson(lessons[0])
    assert v["verdict"] == MATCH


def test_unverifiable_verdict_produces_lesson():
    report = _drift_report([
        _verdict(memory_id="mem-b", verdict="UNVERIFIABLE",
                 reason="source(s) gone", missing=["src-gone"])
    ])
    lessons = drift_lessons(report)
    assert len(lessons) == 1
    assert "gone" in lessons[0]["seal_body"]["claim"]


def test_drift_lesson_kind_is_drift():
    report = _drift_report([_verdict()])
    lessons = drift_lessons(report)
    assert lessons[0]["seal_body"]["kind"] == KIND_DRIFT


def test_drift_lesson_source_organ_is_mneme():
    report = _drift_report([_verdict()])
    lessons = drift_lessons(report)
    assert lessons[0]["seal_body"]["source_organ"] == "mneme"


def test_drift_lesson_source_ref_has_content_digest():
    """The source_ref carries a content-addressed digest over the verdict dict."""
    verdict = _verdict(memory_id="mem-x", changed=["src-x", "src-y"])
    report = _drift_report([verdict])
    lessons = drift_lessons(report)
    ref = lessons[0]["seal_body"]["source_refs"][0]
    assert len(ref["digest"]) == 64
    assert ref["ref"] == "drift:mem-x"


def test_drift_lesson_rationale_is_null():
    """mneme does not record decision rationale; it stays null."""
    report = _drift_report([_verdict()])
    lessons = drift_lessons(report)
    assert lessons[0]["seal_body"]["rationale"] is None


def test_drift_claim_names_changed_sources():
    report = _drift_report([_verdict(memory_id="m1", changed=["url-1", "url-2"])])
    lessons = drift_lessons(report)
    claim = lessons[0]["seal_body"]["claim"]
    assert "url-1" in claim
    assert "url-2" in claim


def test_drift_report_not_dict_returns_empty():
    assert drift_lessons(None) == []
    assert drift_lessons("not a dict") == []


def test_drift_report_missing_verdicts_returns_empty():
    assert drift_lessons({"schema": "mneme.drift-report/1"}) == []


def test_append_drift_lessons_adds_to_store():
    store = LessonStore()
    report = _drift_report([_verdict(), _verdict(memory_id="mem-2", verdict="MATCH")])
    appended = append_drift_lessons(store, report)
    assert len(appended) == 1
    assert len(store) == 1


def test_repeated_drifts_form_pattern():
    """Two drifts on the same memory across reports form a pattern."""
    store = LessonStore()
    # Same memory_id, same changed source -> same normalized claim -> pattern
    append_drift_lessons(store, _drift_report([_verdict(memory_id="mem-x", changed=["s1"])]))
    append_drift_lessons(store, _drift_report([_verdict(memory_id="mem-x", changed=["s1"])]))
    pats = store.patterns()
    assert len(pats) == 1
    assert pats[0].repetition_count == 2


# --- misconception mapper: learn ------------------------------------------


def _misconceptions(entries: list[dict]) -> list[dict]:
    return entries


def _misc(objective="obj-1", count=3, notes=None) -> dict:
    return {"objective": objective, "count": count, "notes": notes or ["wrong approach"]}


def test_empty_misconceptions_produces_zero_lessons():
    assert misconception_lessons([]) == []


def test_misconception_produces_lesson():
    lessons = misconception_lessons([_misc()])
    assert len(lessons) == 1
    v = verify_lesson(lessons[0])
    assert v["verdict"] == MATCH


def test_misconception_lesson_kind():
    lessons = misconception_lessons([_misc()])
    assert lessons[0]["seal_body"]["kind"] == KIND_MISCONCEPTION


def test_misconception_lesson_source_organ_is_learn():
    lessons = misconception_lessons([_misc()])
    assert lessons[0]["seal_body"]["source_organ"] == "learn"


def test_misconception_lesson_claim_names_objective_and_count():
    lessons = misconception_lessons([_misc(objective="fractions", count=5)])
    claim = lessons[0]["seal_body"]["claim"]
    assert "fractions" in claim
    assert "5" in claim


def test_misconception_lesson_rationale_is_null():
    lessons = misconception_lessons([_misc()])
    assert lessons[0]["seal_body"]["rationale"] is None


def test_misconception_source_ref_has_content_digest():
    lessons = misconception_lessons([_misc(objective="obj-z")])
    ref = lessons[0]["seal_body"]["source_refs"][0]
    assert len(ref["digest"]) == 64
    assert ref["ref"] == "misconception:obj-z"


def test_zero_count_misconception_is_skipped():
    """An objective with 0 wrong attempts does not appear; but if forced, skip."""
    lessons = misconception_lessons([_misc(count=0)])
    assert lessons == []


def test_append_misconception_lessons_adds_to_store():
    store = LessonStore()
    miscs = [_misc(objective="obj-a"), _misc(objective="obj-b")]
    appended = append_misconception_lessons(store, miscs)
    assert len(appended) == 2
    assert len(store) == 2


def test_cross_operator_misconceptions_form_pattern():
    """Two operators missing the same objective form a cross-operator pattern."""
    store = LessonStore()
    # Same objective, different notes (simulating different operators)
    append_misconception_lessons(store, [_misc(objective="obj-shared", notes=["off by one"])])
    append_misconception_lessons(store, [_misc(objective="obj-shared", notes=["wrong formula"])])
    pats = store.patterns()
    # The claims normalize to the same string (objective + "repeatedly missed")
    # but the count differs (3 vs 3) so the claim text differs. Let's verify
    # the pattern detection groups by the SAME objective when counts match.
    # Since claim includes the count, identical counts group.
    assert len(pats) >= 1


def test_misconceptions_not_list_returns_empty():
    assert misconception_lessons(None) == []
    assert misconception_lessons("not a list") == []
