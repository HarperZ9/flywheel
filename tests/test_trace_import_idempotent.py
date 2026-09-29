"""7.6: an import run twice stores nothing new; a transcript that grew becomes
a new version with a `supersedes` edge to the one it extends."""
import pytest

from harness.trace_import_claude import plan_claude
from harness.trace_import_core import ImportStore, run_import
from import_fixtures import OWNER, PROJECT, SESSION, age_tree, claude_tree
from trace_enc_fakes import StreamTestProvider, using


@pytest.fixture
def tree(tmp_path):
    home = tmp_path / "home"
    (home / "state").mkdir(parents=True)
    (home / "owner.ref").write_text(OWNER)
    root, _, _ = claude_tree(tmp_path)
    with using(StreamTestProvider()):
        yield home, root


def test_a_second_run_stores_nothing(tree):
    home, root = tree
    run_import(home, plan_claude(home, root=root))
    before = sorted(p for p in (home / "state" / "imports").rglob("*") if p.is_file())
    plan = plan_claude(home, root=root)
    assert {item["state"] for item in plan["items"]} == {"already"}
    assert run_import(home, plan)["imported"] == 0
    after = sorted(p for p in (home / "state" / "imports").rglob("*") if p.is_file())
    assert after == before


def test_a_grown_transcript_becomes_a_new_version(tree):
    home, root = tree
    run_import(home, plan_claude(home, root=root))
    store = ImportStore(home, OWNER)
    first = next(r for r in store.item_refs() if store.manifest(r)["kind"] == "transcript")
    path = root / "projects" / PROJECT / f"{SESSION}.jsonl"
    with open(path, "ab") as stream:
        stream.write(b'{"type": "user", "message": {"content": "resumed"}}\n')
    age_tree(root, seconds=300)
    plan = plan_claude(home, root=root)
    grown = [i for i in plan["items"] if i["state"] == "grown"]
    assert [i["rel"] for i in grown] == [f"projects/{PROJECT}/{SESSION}.jsonl"]
    assert run_import(home, plan)["imported"] == 1
    store = ImportStore(home, OWNER)
    newest = [r for r in store.item_refs() if store.manifest(r).get("supersedes") == first]
    assert len(newest) == 1 and store.read_bytes(newest[0]) == path.read_bytes()
