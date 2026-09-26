"""I9, 7.6: the Claude Code importer classifies every file, refuses a
junction or symlink under the client root, stores exact bytes encrypted,
keeps record types it does not know, and leaves the source tree untouched."""
import pytest

from harness.trace_import_claude import plan_claude
from harness.trace_import_core import ImportStore, run_import
from import_fixtures import OWNER, PROJECT, SESSION, claude_tree, snapshot, transcript
from trace_enc_fakes import StreamTestProvider, using

P = f"projects/{PROJECT}"


@pytest.fixture
def tree(tmp_path):
    home = tmp_path / "home"
    (home / "state").mkdir(parents=True)
    (home / "owner.ref").write_text(OWNER)
    root, outside, linked = claude_tree(tmp_path)
    with using(StreamTestProvider()):
        yield home, root, outside, linked


def test_the_plan_classifies_every_file_and_refuses_the_link(tree):
    home, root, _, linked = tree
    plan = plan_claude(home, root=root)
    kinds = {item["rel"]: item["kind"] for item in plan["items"]}
    assert kinds == {f"{P}/{SESSION}.jsonl": "transcript",
                     f"{P}/{SESSION}/subagents/agent-1.jsonl": "subagent",
                     f"{P}/{SESSION}/tool-results/out-1.bin": "tool_result",
                     f"{P}/{SESSION}.orphaned.jsonl": "variant",
                     f"{P}/{SESSION}/workflows/wf.json": "undocumented"}
    if linked:
        assert plan["refused"] == [{"rel": f"{P}/linked", "reason": "REPARSE_REFUSED"}]
    named = {row["name"] for row in plan["not_imported"]}
    assert {"history.jsonl", "file-history"} <= named
    assert all(item["state"] == "new" for item in plan["items"])


def test_import_keeps_exact_bytes_encrypted(tree):
    home, root, _, _ = tree
    result = run_import(home, plan_claude(home, root=root))
    assert result["imported"] == 5 and result["refused"] == {}
    store = ImportStore(home, OWNER)
    by_rel = {store.manifest(ref)["rel"]: ref for ref in store.item_refs()}
    assert store.read_bytes(by_rel[f"{P}/{SESSION}.jsonl"]) == transcript()
    assert store.read_bytes(by_rel[f"{P}/{SESSION}/tool-results/out-1.bin"]) == (
        bytes(range(256)) * 4)
    stored = b"".join(p.read_bytes() for p in (home / "state").rglob("*") if p.is_file())
    assert b"please list the files" not in stored and b"a.txt" not in stored


def test_unknown_record_types_are_kept_and_counted(tree):
    from harness.trace_views_claude import view_lines
    home, root, _, _ = tree
    run_import(home, plan_claude(home, root=root))
    store = ImportStore(home, OWNER)
    ref = next(r for r in store.item_refs() if store.manifest(r)["kind"] == "transcript")
    assert store.manifest(ref)["record_types"]["mystery-kind"] == 1
    views = view_lines(store.read_bytes(ref))
    assert views[-1]["kind"] == "unknown" and views[-1]["raw"]["type"] == "mystery-kind"
    assert any(v.get("content_trust") == "untrusted" for v in views if v["kind"] == "tool_result")


def test_the_source_tree_is_identical_afterwards(tree):
    home, root, outside, _ = tree
    before, before_outside = snapshot(root), snapshot(outside)
    run_import(home, plan_claude(home, root=root))
    assert snapshot(root) == before and snapshot(outside) == before_outside


def test_nothing_behind_the_link_is_stored(tree):
    home, root, _, linked = tree
    run_import(home, plan_claude(home, root=root))
    stored = b"".join(p.read_bytes() for p in (home / "state").rglob("*") if p.is_file())
    assert b"NOT-A-REAL-KEY" not in stored
    store = ImportStore(home, OWNER)
    assert all("linked" not in store.manifest(r)["rel"] for r in store.item_refs())
