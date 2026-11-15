from __future__ import annotations

import json

import pytest

from proof_surface._strict_json import strict_json_load, strict_json_loads


def test_strict_loads_preserves_normal_json_behavior() -> None:
    assert strict_json_loads('{"a": [1, true, null]}') == {"a": [1, True, None]}


@pytest.mark.parametrize(
    "raw,key",
    [
        ('{"a": 1, "a": 2}', "a"),
        ('{"outer": {"a": 1, "a": 2}}', "a"),
        ('{"action": "read", "act\\u0069on": "write"}', "action"),
    ],
)
def test_strict_loads_rejects_duplicate_decoded_keys(raw: str, key: str) -> None:
    with pytest.raises(ValueError, match=rf"duplicate key {key!r}"):
        strict_json_loads(raw)


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_strict_loads_rejects_non_finite_constants(constant: str) -> None:
    with pytest.raises(ValueError, match="non-finite constant"):
        strict_json_loads('{"value": ' + constant + "}")


def test_strict_loads_preserves_json_decode_error_type() -> None:
    with pytest.raises(json.JSONDecodeError):
        strict_json_loads('{"broken":')


def test_strict_file_loader_preserves_file_errors(tmp_path) -> None:
    missing = tmp_path / "missing.json"
    with pytest.raises(FileNotFoundError):
        strict_json_load(missing)


def test_strict_file_loader_reads_one_document(tmp_path) -> None:
    path = tmp_path / "document.json"
    path.write_text('{"ok": true}', encoding="utf-8")
    assert strict_json_load(path) == {"ok": True}
