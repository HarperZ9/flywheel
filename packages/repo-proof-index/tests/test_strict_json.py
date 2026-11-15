from __future__ import annotations

from pathlib import Path

import pytest

from repo_proof_index.strict_json import load_json, load_json_object


def test_loader_rejects_float_overflow(tmp_path: Path) -> None:
    path = tmp_path / "overflow.json"
    path.write_text('{"status": 1e999}', encoding="utf-8")

    with pytest.raises(ValueError, match="non-finite JSON value: 1e999"):
        load_json_object(path)


def test_loader_rejects_negative_float_overflow(tmp_path: Path) -> None:
    path = tmp_path / "negative-overflow.json"
    path.write_text('{"status": -1e999}', encoding="utf-8")

    with pytest.raises(ValueError, match="non-finite JSON value: -1e999"):
        load_json_object(path)


def test_loader_reads_only_one_byte_past_limit_before_rejecting(tmp_path: Path) -> None:
    path = tmp_path / "too-large.json"
    path.write_text('{"id":"too-large"}', encoding="utf-8")

    with pytest.raises(ValueError, match="JSON file exceeds 8 byte limit"):
        load_json(path, max_bytes=8)


def test_loader_rejects_excessive_nesting_before_decoding(tmp_path: Path) -> None:
    path = tmp_path / "too-deep.json"
    path.write_text('{"a":{"b":{"c":1}}}', encoding="utf-8")

    with pytest.raises(ValueError, match="JSON nesting exceeds 2 levels"):
        load_json_object(path, max_depth=2)
