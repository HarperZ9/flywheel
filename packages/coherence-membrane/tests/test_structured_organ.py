"""Tests for the StructuredDataOrgan -- the membrane's third sense (reading data)."""

from __future__ import annotations

import hashlib

from coherence_membrane.observation import Status
from coherence_membrane.organs.structured import StructuredDataOrgan, canonical_json_bytes


def test_observe_json_bytes():
    doc = b'{"name": "frame", "count": 3}'
    obs = StructuredDataOrgan().observe(doc)[0]
    assert obs.organ == "structured-data"
    assert obs.status == Status.PASS
    assert obs.data["identity_sha256"] == hashlib.sha256(doc).hexdigest()
    assert obs.data["format"] == "json"
    assert obs.data["top_level_type"] == "object"
    assert obs.data["key_count"] == 2
    assert len(obs.data["canonical_sha256"]) == 64
    assert obs.data["decoded"] is True


def test_canonical_ignores_whitespace_and_key_order():
    a = b'{"b": 2, "a": 1}'
    b = b'{\n  "a": 1,\n  "b": 2\n}'
    oa = StructuredDataOrgan().observe(a)[0]
    ob = StructuredDataOrgan().observe(b)[0]
    # raw identity differs, canonical (semantic) identity is the same
    assert oa.data["identity_sha256"] != ob.data["identity_sha256"]
    assert oa.data["canonical_sha256"] == ob.data["canonical_sha256"]


def test_canonical_changes_on_value_change():
    a = StructuredDataOrgan().observe(b'{"a": 1}')[0]
    b = StructuredDataOrgan().observe(b'{"a": 2}')[0]
    assert a.data["canonical_sha256"] != b.data["canonical_sha256"]


def test_array_order_is_semantic():
    a = StructuredDataOrgan().observe(b'[1, 2, 3]')[0]
    b = StructuredDataOrgan().observe(b'[3, 2, 1]')[0]
    # arrays are ordered, so reordering IS a real change
    assert a.data["canonical_sha256"] != b.data["canonical_sha256"]
    assert a.data["top_level_type"] == "array"
    assert a.data["item_count"] == 3


def test_numeric_spelling_is_an_honest_limitation():
    # documented limitation: 1 vs 1.0 are NOT canonically equal
    a = StructuredDataOrgan().observe(b'{"x": 1}')[0]
    b = StructuredDataOrgan().observe(b'{"x": 1.0}')[0]
    assert a.data["canonical_sha256"] != b.data["canonical_sha256"]


def test_invalid_json_is_identity_only():
    bad = b'{not valid json'
    obs = StructuredDataOrgan().observe(bad)[0]
    assert obs.status == Status.UNVERIFIED
    assert obs.data["canonical_sha256"] is None
    assert obs.data["identity_sha256"] == hashlib.sha256(bad).hexdigest()


def test_nan_is_not_canonicalisable_and_fails_closed():
    # json.loads accepts NaN, but it has no canonical form -> identity only
    obs = StructuredDataOrgan().observe(b'{"x": NaN}')[0]
    assert obs.status == Status.UNVERIFIED
    assert obs.data["canonical_sha256"] is None


def test_observe_is_reproducible():
    doc = b'{"k": [1, 2, {"z": 9}]}'
    organ = StructuredDataOrgan()
    a = organ.observe(doc)[0]
    b = organ.observe(doc)[0]
    assert a.data["identity_sha256"] == b.data["identity_sha256"]
    assert a.data["canonical_sha256"] == b.data["canonical_sha256"]


def test_missing_path_is_unverified(tmp_path):
    obs = StructuredDataOrgan().observe(tmp_path / "nope.json")[0]
    assert obs.status == Status.UNVERIFIED
    assert obs.data["decoded"] is False


def test_observe_reads_from_path(tmp_path):
    doc = b'{"a": 1, "b": 2}'
    p = tmp_path / "data.json"
    p.write_bytes(doc)
    obs = StructuredDataOrgan().observe(p)[0]
    assert obs.data["identity_sha256"] == hashlib.sha256(doc).hexdigest()
    assert obs.status == Status.PASS


def test_canonical_json_bytes_is_sorted_and_compact():
    assert canonical_json_bytes({"b": 1, "a": 2}) == b'{"a":2,"b":1}'


def test_non_json_frame_degrades_without_crashing():
    # A Frame carrying non-JSON bytes must not crash (Path(frame) would TypeError)
    # -- it perceives the bytes and degrades to identity-only.
    from coherence_membrane.capture import Frame, FrameDescriptor

    payload = b"\x00\x01\x02\x03"
    frame = Frame(descriptor=FrameDescriptor(source_id="s", frame_index=0,
                                             pixel_format="bgra"), payload=payload)
    obs = StructuredDataOrgan().observe(frame)[0]
    assert obs.status == Status.UNVERIFIED
    assert obs.data["canonical_sha256"] is None
    assert obs.data["identity_sha256"] == hashlib.sha256(payload).hexdigest()


def test_json_carried_in_a_frame_is_perceived():
    # honest about the real behaviour: a frame whose bytes ARE json is canonicalised
    from coherence_membrane.capture import Frame, FrameDescriptor

    payload = b'{"a": 1, "b": 2}'
    frame = Frame(descriptor=FrameDescriptor(source_id="s", frame_index=0,
                                             pixel_format="bgra"), payload=payload)
    obs = StructuredDataOrgan().observe(frame)[0]
    assert obs.status == Status.PASS
    assert obs.data["canonical_sha256"] is not None


def test_alien_subject_degrades_without_crashing():
    # None/int/list are out of contract; Path() would raise TypeError -- guarded.
    for alien in (None, 123, ["a", "b"]):
        obs = StructuredDataOrgan().observe(alien)[0]
        assert obs.status == Status.UNVERIFIED


def test_selftest_passes():
    result = StructuredDataOrgan().selftest()
    assert result.passed, result.to_dict()
    assert len(result.checks) >= 7


def test_organ_does_not_mutate_input_file(tmp_path):
    doc = b'{"a": [1, 2, 3]}'
    p = tmp_path / "data.json"
    p.write_bytes(doc)
    before = p.read_bytes()
    StructuredDataOrgan().observe(p)
    assert p.read_bytes() == before  # inert
