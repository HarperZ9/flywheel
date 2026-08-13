import hashlib
from pathlib import Path

import pytest

from harness.evidence_json import (
    admit_artifact_ref,
    canonical_bytes,
    canonical_sha256,
    strict_load_json,
)


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', '{"a":1,"a":2}'])
def test_strict_load_rejects_duplicate_object_keys(raw):
    with pytest.raises(ValueError, match="duplicate"):
        strict_load_json(raw)


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity", "1e999"])
def test_strict_load_rejects_nonfinite_numbers(token):
    with pytest.raises(ValueError, match="non-finite"):
        strict_load_json('{"value":' + token + "}")


@pytest.mark.parametrize("raw", [b"\xff", "\ud800"])
def test_strict_load_requires_utf8(raw):
    with pytest.raises((UnicodeError, ValueError)):
        strict_load_json(raw)


@pytest.mark.parametrize("raw", ["[]", "null", "1", '"evidence"'])
def test_strict_load_requires_an_object_top_level(raw):
    with pytest.raises(ValueError, match="top-level"):
        strict_load_json(raw)


def test_strict_load_enforces_byte_bound_before_parsing():
    with pytest.raises(ValueError, match="byte"):
        strict_load_json('{"a":1}', max_bytes=6)


def test_strict_load_enforces_container_depth_bound():
    with pytest.raises(ValueError, match="depth"):
        strict_load_json('{"a":{"b":1}}', max_depth=1)


def test_canonical_json_has_sorted_keys_compact_utf8_and_stable_digest():
    value = {"z": 1, "a": "é"}
    assert canonical_bytes(value) == b'{"a":"\xc3\xa9","z":1}'
    assert canonical_sha256({"b": 2, "a": 1}) == (
        "43258cff783fe7036d8a43033f830adfc60ec037382473548ac742b888292777"
    )
    assert canonical_sha256({"a": 1, "b": 2}) == canonical_sha256({"b": 2, "a": 1})


@pytest.mark.parametrize("value", [{"v": float("nan")}, {"v": float("inf")}])
def test_canonical_json_rejects_nonfinite_numbers(value):
    with pytest.raises(ValueError):
        canonical_bytes(value)


@pytest.mark.parametrize("ref", ["/outside.json", "../outside.json", "nested/../../outside.json", "C:\\outside.json", "C:outside.json", "\\\\server\\share\\outside.json"])
def test_artifact_admission_rejects_absolute_and_escaping_refs(tmp_path, ref):
    root = tmp_path / "artifacts"
    root.mkdir()
    with pytest.raises(ValueError):
        admit_artifact_ref(root, ref)


def test_artifact_admission_returns_resolved_regular_file_under_root(tmp_path):
    root = tmp_path / "artifacts"
    root.mkdir()
    target = root / "nested" / "evidence.json"
    target.parent.mkdir()
    target.write_text("{}", encoding="utf-8")
    assert admit_artifact_ref(root, "nested/evidence.json") == target.resolve()


def test_artifact_admission_rejects_symlink_escape(tmp_path):
    root = tmp_path / "artifacts"
    root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    link = root / "linked.json"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")
    with pytest.raises(ValueError, match="root"):
        admit_artifact_ref(root, "linked.json")


@pytest.mark.parametrize("name", ["missing.json", "directory"])
def test_artifact_admission_requires_existing_regular_file(tmp_path, name):
    root = tmp_path / "artifacts"
    root.mkdir()
    (root / "directory").mkdir()
    with pytest.raises(ValueError):
        admit_artifact_ref(root, name)


def test_artifact_admission_can_return_a_nonexistent_contained_ref_when_requested(tmp_path):
    root = tmp_path / "artifacts"
    root.mkdir()
    assert admit_artifact_ref(root, "future.json", must_exist=False) == (root / "future.json").resolve()


def test_canonical_digest_is_standard_sha256_of_the_canonical_bytes():
    value = {"b": 2, "a": 1}
    assert canonical_sha256(value) == hashlib.sha256(canonical_bytes(value)).hexdigest()
