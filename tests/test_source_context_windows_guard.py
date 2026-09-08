import os
from pathlib import Path

import pytest

from harness.source_context_gather import GatherPathAdapter
from harness.source_context_windows import (
    FILE_FLAG_BACKUP_SEMANTICS, FILE_FLAG_OPEN_REPARSE_POINT,
    FILE_ADD_SUBDIRECTORY, FILE_LIST_DIRECTORY, FILE_READ_ATTRIBUTES,
    FILE_SHARE_READ,
    FILE_WRITE_ATTRIBUTES,
    FILE_SHARE_WRITE, OPEN_EXISTING, SYNCHRONIZE,
    SourceContextWindowsGuard, _create_file_handle,
)
from harness.source_context_store import SourceContextError

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows guard contract")


def test_preexisting_writable_directory_handle_returns_busy_before_gather(tmp_path):
    corpus = tmp_path / "state" / "source-context" / "corpora" / ("owner_" + "a" * 32) / "demo" / "tiny"
    corpus.mkdir(parents=True)
    handle = _create_file_handle(corpus,
        FILE_ADD_SUBDIRECTORY | FILE_WRITE_ATTRIBUTES | SYNCHRONIZE,
        FILE_SHARE_READ | FILE_SHARE_WRITE, OPEN_EXISTING,
        FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT)
    try:
        calls = []
        adapter = GatherPathAdapter(inspect_fn=lambda *_a, **_k: calls.append("called") or {}, guard_cls=SourceContextWindowsGuard)
        with pytest.raises(SourceContextError) as exc:
            adapter.inspect(corpus)
        assert exc.value.code == "SOURCE_CONTEXT_AUTHORITY_BUSY"
        assert calls == []
    finally:
        handle.close()


def test_guard_blocks_ancestor_replacement_and_preserves_child_file_writes(tmp_path):
    corpus = tmp_path / "state" / "source-context" / "corpora" / ("owner_" + "a" * 32) / "demo" / "tiny"
    corpus.mkdir(parents=True)
    child = corpus / "child.txt"
    sibling = corpus / "sibling.txt"
    child.write_text("inside", encoding="utf-8")
    sibling.write_text("sibling", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "child.txt").write_text("OUTSIDE-CANARY", encoding="utf-8")
    preexisting = open(child, "a", encoding="utf-8")
    try:
        def inspect(path, **_caps):
            with pytest.raises(OSError):
                Path(path).rename(tmp_path / "moved-corpus")
            preexisting.write(" plus")
            preexisting.flush()
            sibling.write_text("sibling edit", encoding="utf-8")
            return {"marker": Path(path, "child.txt").read_text(encoding="utf-8")}
        result = GatherPathAdapter(inspect_fn=inspect, guard_cls=SourceContextWindowsGuard).inspect(corpus)
    finally:
        preexisting.close()
    assert result["marker"] == "inside plus"
    assert "OUTSIDE-CANARY" not in result["marker"]
    assert sibling.read_text(encoding="utf-8") == "sibling edit"


def test_reparse_aba_attempt_cannot_get_mutator_handle_before_read(tmp_path):
    corpus = tmp_path / "state" / "source-context" / "corpora" / ("owner_" + "a" * 32) / "demo" / "tiny"
    corpus.mkdir(parents=True)
    (corpus / "child.txt").write_text("INSIDE-CANARY", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "child.txt").write_text("OUTSIDE-CANARY", encoding="utf-8")
    def inspect(path, **_caps):
        with pytest.raises(SourceContextError) as exc:
            _create_file_handle(corpus, FILE_ADD_SUBDIRECTORY | FILE_LIST_DIRECTORY | FILE_READ_ATTRIBUTES | FILE_WRITE_ATTRIBUTES | SYNCHRONIZE,
                FILE_SHARE_READ | FILE_SHARE_WRITE, OPEN_EXISTING,
                FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT,
                busy_code="SOURCE_CONTEXT_AUTHORITY_BUSY")
        assert exc.value.code == "SOURCE_CONTEXT_AUTHORITY_BUSY"
        return {"marker": Path(path, "child.txt").read_text(encoding="utf-8")}
    result = GatherPathAdapter(inspect_fn=inspect, guard_cls=SourceContextWindowsGuard).inspect(corpus)
    assert result["marker"] == "INSIDE-CANARY"
    assert "OUTSIDE-CANARY" not in result["marker"]


def test_preexisting_above_state_directory_writer_returns_busy_before_gather(tmp_path):
    corpus = tmp_path / "state" / "source-context" / "corpora" / ("owner_" + "a" * 32) / "demo" / "tiny"
    corpus.mkdir(parents=True)
    handle = _create_file_handle(tmp_path,
        FILE_ADD_SUBDIRECTORY | FILE_WRITE_ATTRIBUTES | SYNCHRONIZE,
        FILE_SHARE_READ | FILE_SHARE_WRITE, OPEN_EXISTING,
        FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT)
    try:
        calls = []
        adapter = GatherPathAdapter(inspect_fn=lambda *_a, **_k: calls.append("called") or {}, guard_cls=SourceContextWindowsGuard)
        with pytest.raises(SourceContextError) as exc:
            adapter.inspect(corpus)
        assert exc.value.code == "SOURCE_CONTEXT_AUTHORITY_BUSY"
        assert calls == []
    finally:
        handle.close()


def test_reparse_corpus_path_is_rejected_before_gather(tmp_path):
    parent = tmp_path / "state" / "source-context" / "corpora" / ("owner_" + "a" * 32) / "demo"
    parent.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = parent / "tiny"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"directory symlink unavailable: {exc}")
    calls = []
    adapter = GatherPathAdapter(inspect_fn=lambda *_a, **_k: calls.append("called") or {}, guard_cls=SourceContextWindowsGuard)
    with pytest.raises(SourceContextError) as err:
        adapter.inspect(link)
    assert err.value.code == "SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE"
    assert calls == []


def test_private_json_preexisting_writer_blocks_growing_file_success(tmp_path):
    from harness.source_context_store import _json_file
    from harness.source_context_windows import FILE_WRITE_DATA
    path = tmp_path / "private.json"
    path.write_text('{"ok":true}', encoding="utf-8")
    handle = _create_file_handle(path, FILE_WRITE_DATA | SYNCHRONIZE,
        FILE_SHARE_READ | FILE_SHARE_WRITE, OPEN_EXISTING, 0)
    try:
        with pytest.raises(SourceContextError) as exc:
            _json_file(path, max_bytes=1_000_000)
        assert exc.value.code == "SOURCE_CONTEXT_AUTHORITY_BUSY"
    finally:
        handle.close()
