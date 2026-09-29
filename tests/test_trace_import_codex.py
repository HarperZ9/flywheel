"""N-18, I9: the Codex importer reads plain, archived and compressed rollouts,
names what it cannot read (compression without a zstd module, the SQLite
thread history), waits for live writers, stops a compression bomb at the
ratio cap, keeps provider-encrypted reasoning labeled as such, and recovers
turn ids for pairing."""
import pytest

from codex_fixtures import T1, T3, T4, FakeZstd, codex_tree, rollout
from harness import trace_zstd
from harness.trace_import_codex import plan_codex
from harness.trace_import_core import ImportStore, run_import
from import_fixtures import OWNER
from trace_enc_fakes import StreamTestProvider, using


@pytest.fixture
def tree(tmp_path):
    home = tmp_path / "home"
    (home / "state").mkdir(parents=True)
    (home / "owner.ref").write_text(OWNER)
    root = codex_tree(tmp_path)
    with using(StreamTestProvider()):
        yield home, root


def _by_thread(plan):
    return {item["session_id"]: item for item in plan["items"]}


def test_the_plan_classifies_rollouts_and_names_what_it_cannot_read(tree, monkeypatch):
    monkeypatch.setattr(trace_zstd, "module", lambda: None)
    home, root = tree
    plan = plan_codex(home, root=root)
    items = _by_thread(plan)
    assert items[T1]["kind"] == "rollout" and items[T1]["state"] == "new"
    assert items[T3]["kind"] == "compressed_rollout"
    assert items[T3]["state"] == "UNSUPPORTED_COMPRESSION" and items[T3]["size"] > 0
    assert items[T4]["state"] == "LIVE_WRITER"
    archived = [i for i in plan["items"] if i["kind"] == "archived_rollout"]
    assert len(archived) == 1
    named = {row["name"]: row for row in plan["not_imported"]}
    assert named["thread_history_1.sqlite"]["reason"] == "SQLITE_NOT_READ"
    assert named["thread_history_1.sqlite"]["bytes"] > 0
    assert {"history.jsonl", "session_index.jsonl"} <= set(named)


def test_plain_and_archived_rollouts_import_exactly(tree, monkeypatch):
    monkeypatch.setattr(trace_zstd, "module", lambda: None)
    home, root = tree
    result = run_import(home, plan_codex(home, root=root))
    assert result["imported"] == 2
    assert result["skipped"] == {"UNSUPPORTED_COMPRESSION": 1, "LIVE_WRITER": 1}
    store = ImportStore(home, OWNER)
    stored = [store.read_bytes(r) for r in store.item_refs()]
    assert rollout(T1) in stored


def test_a_compressed_rollout_is_decompressed_as_it_streams(tree, monkeypatch):
    monkeypatch.setattr(trace_zstd, "module", lambda: FakeZstd())
    home, root = tree
    run_import(home, plan_codex(home, root=root))
    store = ImportStore(home, OWNER)
    ref = next(r for r in store.item_refs() if store.manifest(r)["kind"] == "compressed_rollout")
    manifest = store.manifest(ref)
    assert manifest["decompressed_bytes"] == len(rollout(T3))
    assert manifest["record_types"]["response_item"] == 4
    assert store.read_bytes(ref).startswith(b"ZSTDFAKE")


def test_a_compression_bomb_stops_at_the_ratio_cap(tree, monkeypatch):
    monkeypatch.setattr(trace_zstd, "module", lambda: FakeZstd(bomb=True))
    home, root = tree
    result = run_import(home, plan_codex(home, root=root))
    assert result["refused"] == {"INPUT_BOUND:ratio": 1}
    store = ImportStore(home, OWNER)
    assert all(store.manifest(r)["kind"] != "compressed_rollout" for r in store.item_refs())


def test_encrypted_reasoning_is_kept_and_labeled_and_turn_ids_recovered(tree, monkeypatch):
    from harness.trace_views_codex import turn_ids, view_lines
    monkeypatch.setattr(trace_zstd, "module", lambda: None)
    home, root = tree
    run_import(home, plan_codex(home, root=root))
    store = ImportStore(home, OWNER)
    ref = next(r for r in store.item_refs() if store.manifest(r)["session_id"] == T1)
    data = store.read_bytes(ref)
    assert b"gAAAAB-opaque-blob" in data
    reasoning = [v for v in view_lines(data) if v["kind"] == "reasoning"]
    assert reasoning and reasoning[0]["provider_encrypted"] is True
    assert reasoning[0]["readable"] is False
    assert turn_ids(data) == ["turn-1"]
    assert store.manifest(ref)["turn_ids"] == ["turn-1"]
    kinds = {v["kind"] for v in view_lines(data)}
    assert {"message", "tool_call", "tool_result", "unknown"} <= kinds
