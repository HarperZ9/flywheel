import json

import pytest

from harness.inspect_evidence import InspectImportError, import_inspect_log


def _raw(value):
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def _log(score):
    return {
        "version": 2,
        "status": "success",
        "eval": {"task": "task", "model": "mockllm/model", "run_id": "run"},
        "results": {"total_samples": 1, "completed_samples": 1},
        "samples": [{"id": "case", "epoch": 1, "scores": {"match": score}}],
    }


def _pointers(doc):
    return {item["json_pointer"]: item["source_value"] for item in doc["source_pointers"]}


def test_score_edit_history_reports_safe_provenance_without_payload_spill():
    score = {
        "value": "I",
        "answer": "do not copy current answer",
        "explanation": "do not copy current explanation",
        "reason": "manual_review",
        "history": [
            {
                "value": "C",
                "answer": "do not copy old answer",
                "explanation": "do not copy old explanation",
                "metadata": {"hidden": "do not copy metadata"},
            },
            {
                "value": "I",
                "reason": "manual_review",
                "metadata": "UNCHANGED",
                "provenance": {
                    "timestamp": "2026-09-13T15:21:45Z",
                    "author": "flywheel-test",
                    "reason": "bounded edit provenance acceptance",
                    "metadata": {"private": "do not copy provenance metadata"},
                },
            },
        ],
    }

    imported = import_inspect_log(_raw(_log(score)))

    assert imported["assessment"] == "reported"
    reported = imported["samples"][0]["scores"][0]
    assert reported["value"] == "I"
    assert reported["score_history"] == {
        "state": "present",
        "events": [
            {"value": "C", "redacted_fields": ["answer", "explanation", "metadata"]},
            {
                "value": "I",
                "reason": "manual_review",
                "provenance": {
                    "timestamp": "2026-09-13T15:21:45Z",
                    "author": "flywheel-test",
                    "reason": "bounded edit provenance acceptance",
                },
                "redacted_fields": ["metadata"],
            },
        ],
    }
    assert imported["scoring_coverage"]["score_history"] == {
        "present": 1,
        "empty": 0,
        "missing": 0,
    }
    pointers = _pointers(imported)
    assert pointers["/samples/0/scores/match/reason"] == "manual_review"
    assert pointers["/samples/0/scores/match/history/0/value"] == "C"
    assert pointers["/samples/0/scores/match/history/1/value"] == "I"
    assert pointers["/samples/0/scores/match/history/1/reason"] == "manual_review"
    assert pointers["/samples/0/scores/match/history/1/provenance/author"] == "flywheel-test"
    assert pointers["/samples/0/scores/match/history/1/provenance/reason"] == "bounded edit provenance acceptance"
    assert pointers["/samples/0/scores/match/history/1/provenance/timestamp"] == "2026-09-13T15:21:45Z"
    dumped = json.dumps(imported, ensure_ascii=False)
    assert "do not copy" not in dumped
    assert "/answer" not in dumped
    assert "/explanation" not in dumped
    assert "/metadata" not in dumped
    assert any("score edit history" in item for item in imported["does_not_prove"])


def test_empty_and_missing_score_history_are_distinct():
    imported = import_inspect_log(_raw(_log({
        "value": "C",
        "history": [],
    })))
    missing = import_inspect_log(_raw(_log({"value": "C"})))

    assert imported["samples"][0]["scores"][0]["score_history"] == {
        "state": "empty",
        "events": [],
    }
    assert _pointers(imported)["/samples/0/scores/match/history"] == []
    assert imported["scoring_coverage"]["score_history"] == {
        "present": 0,
        "empty": 1,
        "missing": 0,
    }
    assert "score_history" not in missing["samples"][0]["scores"][0]
    assert "score_history" not in missing["scoring_coverage"]


def test_score_history_coverage_counts_missing_peers_when_history_is_observed():
    imported = import_inspect_log(_raw({
        "version": 2,
        "status": "success",
        "eval": {"task": "task", "model": "mockllm/model", "run_id": "run"},
        "results": {"total_samples": 1, "completed_samples": 1},
        "samples": [{
            "id": "case",
            "epoch": 1,
            "scores": {
                "with-history": {"value": "C", "history": []},
                "missing-history": {"value": "C"},
            },
        }],
    }))

    assert imported["scoring_coverage"]["score_history"] == {
        "present": 0,
        "empty": 1,
        "missing": 1,
    }


def test_unchanged_score_edit_event_preserves_reported_provenance():
    imported = import_inspect_log(_raw(_log({
        "value": "C",
        "history": [{
            "value": "UNCHANGED",
            "answer": "UNCHANGED",
            "explanation": "do not copy improved explanation",
            "reason": "UNCHANGED",
            "metadata": {"reviewed": True},
            "provenance": {
                "timestamp": "2026-09-13T15:26:00Z",
                "author": "flywheel-test",
                "reason": "explanation edit",
            },
        }],
    })))

    event = imported["samples"][0]["scores"][0]["score_history"]["events"][0]
    assert event == {
        "value": "UNCHANGED",
        "reason": "UNCHANGED",
        "provenance": {
            "timestamp": "2026-09-13T15:26:00Z",
            "author": "flywheel-test",
            "reason": "explanation edit",
        },
        "redacted_fields": ["answer", "explanation", "metadata"],
    }
    assert "do not copy improved explanation" not in json.dumps(imported)


@pytest.mark.parametrize("history", [
    "not-a-list",
    [None],
    [{"value": None}],
    [{"provenance": "not-an-object"}],
    [{"provenance": {"author": 7}}],
    [{"value": "C"} for _ in range(129)],
    [{"value": "C", "reason": "x" * 4097}],
])
def test_malformed_score_history_fails_closed(history):
    with pytest.raises(InspectImportError):
        import_inspect_log(_raw(_log({"value": "C", "history": history})))
