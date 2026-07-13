"""The memory surface must be content-addressed and honest: a note's span
hash re-derives from its content, duplicates never double-store, recall
returns verbatim spans, and an empty store says it is empty."""

import hashlib

from harness.memory_api import memory_note, memory_recall, memory_stats


def test_empty_store_reports_empty(tmp_path):
    doc = memory_stats(tmp_path)
    assert doc["spans"] == 0
    assert doc["persisted"] is False
    recall = memory_recall(tmp_path, "anything")
    assert recall["results"] == []


def test_note_recall_roundtrip_is_verbatim(tmp_path):
    text = "the gateway binds 127.0.0.1 and the oracle disposes"
    note = memory_note(tmp_path, text)
    assert note["span_hash"] == hashlib.sha256(text.encode()).hexdigest()
    assert note["existed"] is False
    recall = memory_recall(tmp_path, "oracle gateway")
    assert recall["n"] == 1
    assert recall["results"][0]["messages"][0]["content"] == text
    assert recall["results"][0]["span_hash"] == note["span_hash"]


def test_duplicate_note_never_double_stores(tmp_path):
    memory_note(tmp_path, "same content")
    again = memory_note(tmp_path, "same content")
    assert again["existed"] is True
    assert memory_stats(tmp_path)["spans"] == 1


def test_empty_note_is_refused(tmp_path):
    assert "error" in memory_note(tmp_path, "   ")
