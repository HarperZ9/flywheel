"""test_blocks.py -- the authored-block loader. Covers what a directory yields,
and what it does with a file it cannot turn into a record. The rule under test
is that a bad file is reported, never dropped: a pool that silently omits the
record someone just wrote looks exactly like a clean load.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from canon.blocks import ENV_BLOCKS_DIR, default_blocks_dir, load_blocks
from canon.layering import resolve_blocks
from canon.schema import (
    KIND_EPISODIC_MEMORY,
    KIND_PERSONALITY_BLOCK,
    Provenance,
    Record,
    Temporal,
)
from canon.textblock import render_region
from canon.validator import validate_record


def _block(id_: str, *, scope: str = "global", ord_: int = 1) -> Record:
    return Record(
        kind=KIND_PERSONALITY_BLOCK, id=id_, scope=scope,
        data={"title": id_, "body": "b"},
        provenance=Provenance(harness="author", source_hash="a" * 64, create_ord=ord_),
        temporal=Temporal(valid_until=None, supersedes=None))


def _memory(id_: str) -> Record:
    return Record(
        kind=KIND_EPISODIC_MEMORY, id=id_, scope="global",
        data={"layer": "L0", "text": "t", "source_ids": []},
        provenance=Provenance(harness="mneme", source_hash="b" * 64, create_ord=2),
        temporal=Temporal(valid_until=None, supersedes=None))


def _write(directory, name: str, payload) -> None:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    (directory / name).write_text(text, encoding="utf-8")


def test_a_directory_of_records_loads_in_filename_order(tmp_path):
    _write(tmp_path, "b.json", _block("second", ord_=2).to_dict())
    _write(tmp_path, "a.json", _block("first", ord_=1).to_dict())
    load = load_blocks(str(tmp_path))
    assert load.ok and load.problems == ()
    assert [r.id for r in load.records] == ["first", "second"]
    assert load.directory == str(tmp_path)


def test_a_mixed_directory_keeps_every_kind(tmp_path):
    _write(tmp_path, "a.json", _block("b1").to_dict())
    _write(tmp_path, "b.json", _memory("m1").to_dict())
    load = load_blocks(str(tmp_path))
    assert load.ok
    assert {r.kind for r in load.records} == {KIND_PERSONALITY_BLOCK, KIND_EPISODIC_MEMORY}


def test_unparseable_json_is_a_problem_not_a_silent_drop(tmp_path):
    _write(tmp_path, "good.json", _block("kept").to_dict())
    _write(tmp_path, "bad.json", "{not json")
    load = load_blocks(str(tmp_path))
    assert [r.id for r in load.records] == ["kept"]
    assert len(load.problems) == 1 and "bad.json" in load.problems[0]
    # The count of files is conserved: one loaded, one reported, none vanished.
    assert len(load.records) + len(load.problems) == 2
    assert not load.ok


def test_a_foreign_schema_tag_is_refused_by_name(tmp_path):
    payload = _block("b1").to_dict()
    payload["canon_schema"] = "canon.record/v99"
    _write(tmp_path, "future.json", payload)
    load = load_blocks(str(tmp_path))
    assert load.records == () and len(load.problems) == 1
    assert "future.json" in load.problems[0] and "v99" in load.problems[0]


def test_a_record_that_parses_but_does_not_validate_is_a_problem(tmp_path):
    payload = _block("b1").to_dict()
    payload["provenance"]["source_hash"] = "not-a-digest"
    _write(tmp_path, "bad-prov.json", payload)
    load = load_blocks(str(tmp_path))
    assert load.records == ()
    assert "source_hash" in load.problems[0]


def test_a_missing_structural_key_names_the_file(tmp_path):
    payload = _block("b1").to_dict()
    del payload["provenance"]
    _write(tmp_path, "no-prov.json", payload)
    load = load_blocks(str(tmp_path))
    assert load.records == () and "no-prov.json" in load.problems[0]


def test_non_json_files_are_not_read(tmp_path):
    # blocks/ ships a README.md beside the records. A loader that globbed
    # everything would report the prose as a malformed record on every call.
    _write(tmp_path, "a.json", _block("b1").to_dict())
    (tmp_path / "README.md").write_text("# blocks\n", encoding="utf-8")
    load = load_blocks(str(tmp_path))
    assert load.ok and [r.id for r in load.records] == ["b1"]


def test_an_empty_directory_is_an_empty_pool_not_a_failure(tmp_path):
    load = load_blocks(str(tmp_path))
    assert load.ok and load.records == () and load.problems == ()
    assert load.directory == str(tmp_path)


def test_a_path_that_is_not_a_directory_reports_the_path(tmp_path):
    missing = tmp_path / "nope"
    load = load_blocks(str(missing))
    assert load.directory is None and not load.ok
    assert str(missing) in load.problems[0]


def test_no_directory_at_all_is_a_different_fact_from_an_empty_one(monkeypatch):
    # A configured directory holding nothing is an authored set with no entries.
    # No directory at all is an unconfigured server, and `directory` is None so
    # a caller can tell the two apart.
    monkeypatch.setattr("canon.blocks.default_blocks_dir", lambda: None)
    load = load_blocks()
    assert load.directory is None and not load.ok
    assert ENV_BLOCKS_DIR in load.problems[0]


def test_the_env_variable_overrides_the_checkout_directory(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_BLOCKS_DIR, str(tmp_path))
    assert default_blocks_dir() == str(tmp_path)
    _write(tmp_path, "a.json", _block("from-env").to_dict())
    assert [r.id for r in load_blocks().records] == ["from-env"]


def test_an_unset_env_variable_falls_back_to_the_checkout(monkeypatch):
    monkeypatch.delenv(ENV_BLOCKS_DIR, raising=False)
    found = default_blocks_dir()
    # This checkout may or may not carry a blocks/ directory; both are honest
    # answers, and neither is a path this loader invented.
    assert found is None or found.endswith("blocks")


def test_the_checkout_block_set_is_valid_public_clean_and_renderable(monkeypatch):
    monkeypatch.delenv(ENV_BLOCKS_DIR, raising=False)
    directory = default_blocks_dir()
    assert directory is not None and directory.endswith("blocks")
    root = Path(directory)
    load = load_blocks()

    assert load.ok and [rec.id for rec in load.records] == [
        "evidence-insight-and-useful-work"]
    for file in root.iterdir():
        if file.is_file():
            assert "—" not in file.read_text(encoding="utf-8")
    for rec in load.records:
        assert validate_record(rec) == []
        assert rec.to_dict() == json.loads((root / f"{rec.id}.json").read_text("utf-8"))
        resolved = resolve_blocks(load.records, rec.scope)
        assert rec in resolved
        assert rec.data["title"] in render_region(list(resolved), rec.scope)


def test_the_loader_reads_and_never_writes(tmp_path):
    _write(tmp_path, "a.json", _block("b1").to_dict())
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    load_blocks(str(tmp_path))
    after = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert before == after


@pytest.mark.parametrize("payload", ["[]", '"a string"', "null", "3"])
def test_a_json_document_that_is_not_an_object_is_refused(tmp_path, payload):
    _write(tmp_path, "wrong-shape.json", payload)
    load = load_blocks(str(tmp_path))
    assert load.records == () and len(load.problems) == 1
    assert "wrong-shape.json" in load.problems[0]
