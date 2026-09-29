"""SP-29, A13: hostile sources are bounded. A line past the line bound is
kept raw and marked oversized while the item continues; JSON nested past the
view bound is kept raw and marked unparseable; a plan larger than free space
minus a margin refuses with INSUFFICIENT_SPACE."""
import json

import pytest

from harness import trace_import_core
from harness.trace_import_claude import plan_claude
from harness.trace_import_core import ImportStore, run_import
from import_fixtures import OWNER, PROJECT, SESSION, age_tree, claude_tree, transcript
from trace_enc_fakes import StreamTestProvider, using


@pytest.fixture
def tree(tmp_path):
    home = tmp_path / "home"
    (home / "state").mkdir(parents=True)
    (home / "owner.ref").write_text(OWNER)
    root, _, _ = claude_tree(tmp_path)
    with using(StreamTestProvider()):
        yield home, root


def _transcript_manifest(home):
    store = ImportStore(home, OWNER)
    ref = next(r for r in store.item_refs() if store.manifest(r)["kind"] == "transcript")
    return store, ref, store.manifest(ref)


def test_a_line_past_the_bound_is_kept_and_marked_oversized(tree, monkeypatch):
    home, root = tree
    monkeypatch.setattr(trace_import_core, "LINE_BOUND", 4096)
    long_line = json.dumps({"type": "user", "blob": "z" * 10_000}).encode() + b"\n"
    path = root / "projects" / PROJECT / f"{SESSION}.jsonl"
    path.write_bytes(transcript(long_line))
    age_tree(root, seconds=300)
    run_import(home, plan_claude(home, root=root))
    store, ref, manifest = _transcript_manifest(home)
    assert manifest["line_kinds"]["oversized"] == 1
    assert store.read_bytes(ref) == path.read_bytes()


def test_deep_nesting_is_kept_raw_and_marked_unparseable(tree):
    home, root = tree
    deep = b"[" * 10_000 + b"]" * 10_000 + b"\n"
    path = root / "projects" / PROJECT / f"{SESSION}.jsonl"
    path.write_bytes(transcript(deep))
    age_tree(root, seconds=300)
    run_import(home, plan_claude(home, root=root))
    store, ref, manifest = _transcript_manifest(home)
    assert manifest["line_kinds"]["unparseable"] == 1
    assert store.read_bytes(ref).endswith(deep)


def test_a_plan_larger_than_free_space_refuses(tree):
    home, root = tree
    plan = plan_claude(home, root=root, free_space=lambda path: 1024)
    assert plan["state"] == "INSUFFICIENT_SPACE"
    result = run_import(home, plan)
    assert result["state"] == "INSUFFICIENT_SPACE" and result["imported"] == 0
    assert not (home / "state" / "imports").exists()


def test_files_past_the_per_directory_cap_are_listed_not_read(tree, monkeypatch):
    home, root = tree
    monkeypatch.setattr(trace_import_core, "FILES_PER_DIRECTORY", 2)
    results = root / "projects" / PROJECT / SESSION / "tool-results"
    for index in range(4):
        (results / f"extra-{index}.txt").write_bytes(b"x")
    age_tree(root, seconds=300)
    plan = plan_claude(home, root=root)
    over = [row for row in plan["not_imported"] if row.get("reason") == "INPUT_BOUND:files"]
    assert len(over) == 1 and over[0]["count"] == 3
