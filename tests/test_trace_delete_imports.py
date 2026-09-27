"""I19 for imports: deleting an imported session removes its chunks,
manifest, index rows and keys and adds exclusion entries first, so a later
import of the resumed transcript is skipped as PREVIOUSLY_DELETED_SESSION
and nothing of the deleted prefix comes back."""
import pytest

from harness import trace_import_exclusion as exclusion
from harness.trace_delete_apply import apply_plan
from harness.trace_delete_plan import make_plan
from harness.trace_import_claude import plan_claude
from harness.trace_import_core import ImportStore, run_import
from harness.trace_keystore import Keystore
from harness.trace_presence import confirm
from harness.trace_witness import MemorySink
from import_fixtures import OWNER, PROJECT, SESSION, age_tree, claude_tree
from trace_enc_fakes import StreamTestProvider, using


@pytest.fixture
def imported(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "state").mkdir(parents=True)
    (home / "owner.ref").write_text(OWNER)
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))
    monkeypatch.setenv("FLYWHEEL_RUN_ROOT", str(tmp_path / "run"))
    root, _, _ = claude_tree(tmp_path)
    with using(StreamTestProvider()):
        assert run_import(home, plan_claude(home, root=root))["imported"] == 5
        yield home, root


def _delete_session(home):
    plan = make_plan(home, OWNER, {"session": {"client": "claude-code", "session_id": SESSION}})
    ref = confirm(home / "state", OWNER, "delete_apply", plan["plan_digest"], "delete")
    return plan, apply_plan(home, OWNER, plan["plan_digest"], ref, sink=MemorySink())


def test_deleting_an_imported_session_removes_items_index_and_keys(imported):
    home, _ = imported
    refs = ImportStore(home, OWNER).item_refs()
    plan, report = _delete_session(home)
    assert plan["counts"]["IM"] == 5 and report["state"] == "DELETED", report
    assert ImportStore(home, OWNER).item_refs() == []
    keystore = Keystore(home / "state", OWNER)
    assert not any(keystore.present("IM", r) for r in refs)
    assert not list((home / "state" / "imports").rglob("chunk-*.enc"))
    listed = exclusion.entries(home, OWNER)
    assert len([e for e in listed if e.get("kind") != "session"]) == 5
    assert [e for e in listed if e.get("kind") == "session"] == [
        {"kind": "session", "session": listed[0]["session"]}]
    assert report["remedies"] == {"claude-code": "claude project purge"}


def test_a_resumed_transcript_does_not_bring_the_deleted_prefix_back(imported):
    home, root = imported
    _delete_session(home)
    path = root / "projects" / PROJECT / f"{SESSION}.jsonl"
    with open(path, "ab") as stream:
        stream.write(b'{"type": "user", "message": {"content": "after resume"}}\n')
    age_tree(root, seconds=300)
    plan = plan_claude(home, root=root)
    item = next(i for i in plan["items"] if i["rel"].endswith(f"{SESSION}.jsonl"))
    assert item["state"] == "PREVIOUSLY_DELETED_SESSION" and item["new_bytes"] > 0
    assert run_import(home, plan)["imported"] == 0
    assert ImportStore(home, OWNER).item_refs() == []
    assert all(i["state"].startswith("PREVIOUSLY_DELETED") for i in plan["items"])


def test_imports_can_be_selected_by_ref(imported):
    home, _ = imported
    store = ImportStore(home, OWNER)
    ref = next(r for r in store.item_refs() if store.manifest(r)["kind"] == "tool_result")
    plan = make_plan(home, OWNER, {"import_refs": [ref]})
    assert [e["item"] for e in plan["entries"]] == [ref]
