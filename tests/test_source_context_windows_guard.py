import os
import subprocess
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
from harness.source_context_store import SourceContextError, SourceContextStore
from harness.source_context_route import admit_flywheel_corpus, source_context_post
from tests.test_source_context_route import FakeGather
from tests.test_source_context_route import NOW, OWNER
from tests.test_source_context_store import CORPUS_ID, _selection

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows guard contract")


def _junction(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir(parents=True, exist_ok=True)
    result = subprocess.run([os.environ.get("COMSPEC", "cmd.exe"), "/c",
        "mklink", "/J", str(link), str(target)], check=False,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        pytest.skip(f"junction unavailable: {result.stderr or result.stdout}")


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


def test_store_publication_rejects_junction_anchor_without_outside_writes(tmp_path):
    state, outside = tmp_path / "state", tmp_path / "outside-store"
    (state / "source-context").mkdir(parents=True)
    _junction(state / "source-context" / "v1", outside)
    store = SourceContextStore(state, clock=lambda: NOW)
    state_id = store.state_root_identity()

    with pytest.raises(SourceContextError) as exc:
        store.publish_selection(owner_ref=OWNER, state_root_identity=state_id,
            root_mode="flywheel_corpus", profile="demo", corpus_locator="tiny",
            corpus_root_identity=CORPUS_ID, gather_payload=_selection(),
            selected_at=NOW)

    assert exc.value.code == "SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE"
    assert list(outside.rglob("*.json")) == []


def test_store_refread_rejects_junction_anchor_before_outside_read(
        tmp_path, monkeypatch):
    state = tmp_path / "state"
    state.mkdir()
    store = SourceContextStore(state, clock=lambda: NOW)
    state_id = store.state_root_identity()
    attached = store.publish_selection(owner_ref=OWNER,
        state_root_identity=state_id, root_mode="flywheel_corpus",
        profile="demo", corpus_locator="tiny", corpus_root_identity=CORPUS_ID,
        gather_payload=_selection(), selected_at=NOW)
    v1, outside = state / "source-context" / "v1", tmp_path / "outside-store"
    v1.rename(outside)
    _junction(v1, outside)
    import harness.source_context_windows as win
    reads = []
    original = win._read_handle
    def observed_read(handle, size):
        reads.append(str(handle.path))
        return original(handle, size)
    monkeypatch.setattr(win, "_read_handle", observed_read)

    with pytest.raises(SourceContextError) as exc:
        store.resolve_worker_payload(OWNER, (attached["source_context_ref"],))

    assert exc.value.code == "SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE"
    assert reads == []


def test_admission_registry_write_rejects_junction_without_outside_write(tmp_path):
    corpus = tmp_path / "source-context" / "corpora" / OWNER / "demo" / "tiny"
    corpus.mkdir(parents=True)
    outside = tmp_path / "outside-admissions"
    _junction(tmp_path / "source-context" / "admissions", outside)

    with pytest.raises(SourceContextError) as exc:
        admit_flywheel_corpus(tmp_path, OWNER, "demo", "tiny",
            clock=lambda: NOW)

    assert exc.value.code == "SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE"
    assert list(outside.rglob("*.json")) == []


def test_admission_registry_read_rejects_junction_before_outside_read(
        tmp_path, monkeypatch):
    corpus = tmp_path / "source-context" / "corpora" / OWNER / "demo" / "tiny"
    corpus.mkdir(parents=True)
    admit_flywheel_corpus(tmp_path, OWNER, "demo", "tiny",
        clock=lambda: NOW)
    admissions = tmp_path / "source-context" / "admissions"
    outside = tmp_path / "outside-admissions"
    admissions.rename(outside)
    _junction(admissions, outside)
    import harness.source_context_windows as win
    reads = []
    original = win._read_handle
    def observed_read(handle, size):
        reads.append(str(handle.path))
        return original(handle, size)
    monkeypatch.setattr(win, "_read_handle", observed_read)

    body, status = source_context_post("/api/source-context/inspect",
        b'{"schema":"flywheel.source-context-request/v1",'
        b'"root_mode":"flywheel_corpus","profile":"demo","corpus":"tiny"}',
        owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW,
        gather=FakeGather())

    assert status == 409
    assert body["error"]["code"] == "SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE"
    assert reads == []
