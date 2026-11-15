"""Round-trip proof: from_dict -> to_dict is field-identical for every kind.

The F0 exit criterion is that a canonical record survives serialization with
no field lost, added, or coerced. Each of the five on-disk fixtures is loaded,
reconstructed, and re-serialized; the re-serialized dict must equal the
original byte-for-byte after JSON normalization, and the JSON string round-trip
must also be stable.
"""
from __future__ import annotations

import json

import pytest

from canon.schema import (
    SCHEMA,
    Provenance,
    Record,
    Temporal,
)

from ._helpers import RECORD_FILES, load_dict


@pytest.mark.parametrize("kind", list(RECORD_FILES))
def test_from_dict_to_dict_is_field_identical(kind: str) -> None:
    original = load_dict(RECORD_FILES[kind])
    rec = Record.from_dict(original)
    assert rec.kind == kind
    assert rec.to_dict() == original


@pytest.mark.parametrize("kind", list(RECORD_FILES))
def test_json_string_roundtrip_is_stable(kind: str) -> None:
    original = load_dict(RECORD_FILES[kind])
    rec = Record.from_dict(original)
    once = rec.to_json()
    twice = Record.from_json(once).to_json()
    assert once == twice
    # And the JSON decodes back to the same canonical dict.
    assert json.loads(once) == original


@pytest.mark.parametrize("kind", list(RECORD_FILES))
def test_record_equality_survives_roundtrip(kind: str) -> None:
    rec = Record.from_dict(load_dict(RECORD_FILES[kind]))
    assert Record.from_dict(rec.to_dict()) == rec


def test_from_dict_rejects_wrong_schema() -> None:
    d = load_dict(RECORD_FILES["personality-block"])
    d["canon_schema"] = "canon.record/v0"
    with pytest.raises(ValueError):
        Record.from_dict(d)


def test_provenance_and_temporal_roundtrip_directly() -> None:
    prov = Provenance(
        harness="claude-code",
        source_hash="a" * 64,
        native_id="x",
        session_id="s",
        create_ord=7,
        create_time=None,
        model_slug="claude-opus-4-8",
    )
    assert Provenance.from_dict(prov.to_dict()) == prov

    temporal = Temporal(valid_until=42, supersedes="prev")
    assert Temporal.from_dict(temporal.to_dict()) == temporal


def test_temporal_absent_serializes_as_null() -> None:
    d = load_dict(RECORD_FILES["research-artifact-ref"])
    assert d["temporal"] is None
    rec = Record.from_dict(d)
    assert rec.temporal is None
    assert rec.to_dict()["temporal"] is None
    assert rec.to_dict()["canon_schema"] == SCHEMA


def test_to_dict_deep_copies_nested_data() -> None:
    # The record is frozen; the dict it hands out must not alias its payload,
    # so mutating the returned dict (even a nested value) cannot reach back in.
    rec = Record(
        kind="personality-block",
        id="b",
        scope="global",
        data={"title": "t", "body": "b", "tags": ["x"]},
        provenance=Provenance(harness="author", source_hash="a" * 64),
    )
    d = rec.to_dict()
    d["data"]["tags"].append("y")
    assert rec.data["tags"] == ["x"]


def test_from_dict_deep_copies_nested_data() -> None:
    # from_dict takes ownership by copying: mutating the source dict afterward
    # must not mutate the constructed record's payload.
    src = {
        "canon_schema": SCHEMA,
        "kind": "personality-block",
        "id": "b",
        "scope": "global",
        "data": {"title": "t", "body": "b", "tags": ["x"]},
        "provenance": {"harness": "author", "source_hash": "a" * 64},
        "temporal": None,
    }
    rec = Record.from_dict(src)
    src["data"]["tags"].append("y")
    assert rec.data["tags"] == ["x"]
