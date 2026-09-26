"""I19, SP-16: a source the owner deleted does not come back through import,
and neither does a resumed session that extends a deleted prefix. Without
the custody key the list cannot match, so import fails closed."""
import pytest

from harness import trace_import_exclusion as exclusion
from harness.trace_enc import EncError
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
    with using(StreamTestProvider()) as provider:
        yield home, root, provider


def _exclude_transcript(home, root):
    path = root / "projects" / PROJECT / f"{SESSION}.jsonl"
    exclusion.add(home, OWNER, "claude-code", path, SESSION, path.read_bytes())
    return path


def _state_of(plan, rel):
    return next(i for i in plan["items"] if i["rel"] == rel)


def test_an_excluded_source_is_skipped_as_previously_deleted(tree):
    home, root, _ = tree
    _exclude_transcript(home, root)
    plan = plan_claude(home, root=root)
    rel = f"projects/{PROJECT}/{SESSION}.jsonl"
    assert _state_of(plan, rel)["state"] == "PREVIOUSLY_DELETED"
    result = run_import(home, plan)
    assert result["skipped"]["PREVIOUSLY_DELETED"] == 1
    store = ImportStore(home, OWNER)
    assert all(store.manifest(r)["rel"] != rel for r in store.item_refs())


def test_a_resumed_session_extending_a_deleted_prefix_is_skipped(tree):
    home, root, _ = tree
    path = _exclude_transcript(home, root)
    prefix = path.read_bytes()
    with open(path, "ab") as stream:
        stream.write(b'{"type": "user", "message": {"content": "resumed later"}}\n')
    plan = plan_claude(home, root=root)
    item = _state_of(plan, f"projects/{PROJECT}/{SESSION}.jsonl")
    assert item["state"] == "PREVIOUSLY_DELETED_SESSION"
    assert item["new_bytes"] == path.stat().st_size - len(prefix)
    run_import(home, plan)
    stored = b"".join(p.read_bytes() for p in (home / "state").rglob("*") if p.is_file())
    assert b"please list the files" not in stored


def test_the_list_holds_keyed_digests_only(tree):
    home, root, _ = tree
    _exclude_transcript(home, root)
    raw = exclusion.list_path(home, OWNER).read_bytes()
    assert SESSION.encode() not in raw and PROJECT.encode() not in raw
    assert b"please list" not in raw


def test_without_the_custody_key_import_fails_closed(tree, monkeypatch):
    home, root, provider = tree
    _exclude_transcript(home, root)

    def unavailable(blob, context):
        raise EncError("OS_KEY_UNAVAILABLE")
    monkeypatch.setattr(provider, "unseal", unavailable)
    plan = plan_claude(home, root=root)
    assert plan["state"] == "CUSTODY_KEY_UNAVAILABLE"
    assert run_import(home, plan)["imported"] == 0
