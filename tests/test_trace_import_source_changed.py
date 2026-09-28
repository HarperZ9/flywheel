"""I9, SP-30: a source that changes while it is read aborts that item with
SOURCE_CHANGED and leaves nothing half imported; the other items import."""
import pytest

from harness.trace_import_claude import plan_claude
from harness.trace_import_core import ImportStore, run_import
from import_fixtures import OWNER, PROJECT, SESSION, claude_tree
from trace_enc_fakes import StreamTestProvider, using


@pytest.fixture
def tree(tmp_path):
    home = tmp_path / "home"
    (home / "state").mkdir(parents=True)
    (home / "owner.ref").write_text(OWNER)
    root, _, _ = claude_tree(tmp_path)
    with using(StreamTestProvider()):
        yield home, root


def _rels(home):
    store = ImportStore(home, OWNER)
    return {store.manifest(r)["rel"] for r in store.item_refs()}


def test_an_append_during_the_read_gives_source_changed(tree):
    home, root = tree
    target = root / "projects" / PROJECT / f"{SESSION}.jsonl"

    def append(path):
        if path == target:
            with open(path, "ab") as stream:
                stream.write(b'{"type": "user", "late": true}\n')
    result = run_import(home, plan_claude(home, root=root), on_read=append)
    assert result["refused"] == {"SOURCE_CHANGED": 1}
    assert f"projects/{PROJECT}/{SESSION}.jsonl" not in _rels(home)
    assert len(_rels(home)) == 4
    leftovers = [p for p in (home / "state" / "imports").rglob("*") if p.name.startswith(".")]
    assert leftovers == []
