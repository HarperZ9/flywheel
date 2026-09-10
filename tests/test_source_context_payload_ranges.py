"""Reject misleading source locators even when the payload is rehashed."""
from __future__ import annotations

import hashlib

import pytest

from harness.evidence_json import canonical_sha256
from harness.source_context_error import SourceContextError
from harness.source_context_payload import validated_gather_payload


def payload(row):
    value = {"schema": "gather.readable-context/v1", "selections": [row],
             "selection_count": 1, "total_text_chars": 3,
             "omissions": [], "does_not_prove": ["source truth"]}
    return seal(value)


def seal(value):
    base = {key: val for key, val in value.items()
            if key not in {"selection_digest", "verified", "verified_scope"}}
    return dict(base, selection_digest=canonical_sha256(base),
                verified=True, verified_scope="selected_rows")


def row():
    return {"row_ref": "row_demo", "kind": "document", "id": "demo",
            "ref": "demo", "method": "file-read", "sha256": "a" * 64,
            "range": {"start": 1, "end": 4}, "text": "abc",
            "full_text_chars": 5, "body_bytes_read": 5, "omissions": []}


@pytest.mark.parametrize("span", [
    {"start": 100, "end": 103},  # Correct span length, outside source.
    {"start": 1, "end": 3},  # Inside source, wrong excerpt length.
    {"start": 4, "end": 7},  # Start inside source, end outside it.
])
def test_rehashed_invalid_range_is_rejected(span):
    selected = row()
    selected["range"] = span
    with pytest.raises(SourceContextError) as error:
        validated_gather_payload(payload(selected))
    assert error.value.code == "SOURCE_CONTEXT_SELECTION_FAILED"


@pytest.mark.parametrize("field", ["full_text_chars", "body_bytes_read"])
@pytest.mark.parametrize("count", [True, 5.5, "5", None, -1])
def test_row_counts_are_not_coerced(field, count):
    selected = row()
    selected[field] = count
    with pytest.raises(SourceContextError) as error:
        validated_gather_payload(payload(selected))
    assert error.value.code == "SOURCE_CONTEXT_SELECTION_FAILED"


@pytest.mark.parametrize("selected", [None, [], "PRIVATE-CONTENT-CANARY", 1])
def test_non_object_row_uses_private_safe_typed_error(selected):
    with pytest.raises(SourceContextError) as error:
        validated_gather_payload(payload(selected))
    assert str(error.value) == "SOURCE_CONTEXT_SELECTION_FAILED"


def test_boolean_selection_count_is_not_one_row():
    value = payload(row())
    value["selection_count"] = True
    with pytest.raises(SourceContextError) as error:
        validated_gather_payload(seal(value))
    assert error.value.code == "SOURCE_CONTEXT_SELECTION_FAILED"


@pytest.mark.parametrize("text,span,full_chars,byte_count", [
    ("é🙂\n", {"start": 2, "end": 5}, 7, 11),
    ("e\u0301", {"start": 1, "end": 3}, 4, 5),
    ("", {"start": 5, "end": 5}, 5, 5),
    ("", {"start": 0, "end": 0}, 0, 0),
])
def test_valid_partial_unicode_and_empty_ranges_keep_exact_text(
        text, span, full_chars, byte_count):
    selected = row()
    selected.update(text=text, range=span, full_text_chars=full_chars,
                    body_bytes_read=byte_count)
    value = payload(selected)
    value["total_text_chars"] = len(text)
    rows, _caps = validated_gather_payload(seal(value))
    assert rows[0]["text"] == text
    assert rows[0]["range"] == span
    assert rows[0]["selected_text_utf8_sha256"] == hashlib.sha256(
        text.encode("utf-8")).hexdigest()
