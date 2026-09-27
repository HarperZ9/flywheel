"""Imported items and their leftovers leave custody together.

A transcript that grew is imported again as a new item that `supersedes` the
old one; the old one is a byte prefix of the same transcript, so deleting
either deletes the whole chain. An import interrupted by an error discards its
staging folder and key, and staging a crash left behind is swept at gateway
start, key first."""
import os
import time

import pytest

from harness import trace_import_items
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
def world(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "state").mkdir(parents=True)
    (home / "owner.ref").write_text(OWNER)
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))
    monkeypatch.setenv("FLYWHEEL_RUN_ROOT", str(tmp_path / "run"))
    root, _, _ = claude_tree(tmp_path)
    with using(StreamTestProvider()):
        yield home, root


def _grow(home, root):
    run_import(home, plan_claude(home, root=root))
    path = root / "projects" / PROJECT / f"{SESSION}.jsonl"
    with open(path, "ab") as stream:
        stream.write(b'{"type": "user", "message": {"content": "later"}}\n')
    age_tree(root, seconds=300)
    run_import(home, plan_claude(home, root=root))
    store = ImportStore(home, OWNER)
    chain = [r for r in store.item_refs() if store.manifest(r).get("session_id") == SESSION
             and store.manifest(r)["kind"] == "transcript"]
    newer = next(r for r in chain if store.manifest(r).get("supersedes"))
    return store, store.manifest(newer)["supersedes"], newer


@pytest.mark.parametrize("pick", ["older", "newer"])
def test_deleting_one_version_deletes_the_whole_chain(world, pick):
    home, root = world
    store, older, newer = _grow(home, root)
    chosen = older if pick == "older" else newer
    plan = make_plan(home, OWNER, {"import_refs": [chosen]})
    assert {older, newer} <= {e["item"] for e in plan["entries"]}
    ref = confirm(home / "state", OWNER, "delete_apply", plan["plan_digest"], "delete")
    assert apply_plan(home, OWNER, plan["plan_digest"], ref, sink=MemorySink())["state"] == \
        "DELETED"
    left = ImportStore(home, OWNER).item_refs()
    assert older not in left and newer not in left


def test_an_error_while_staging_discards_the_folder_and_key(world, monkeypatch):
    home, root = world
    made = []
    real = trace_import_items.StagedItem.__init__

    def track(self, *a, **k):
        real(self, *a, **k)
        made.append((self.ref, self.dir))
    monkeypatch.setattr(trace_import_items.StagedItem, "__init__", track)

    def broken(self, chunk):
        raise OSError("disk full (planted)")
    monkeypatch.setattr(trace_import_items.StagedItem, "write", broken)
    with pytest.raises(OSError):
        run_import(home, plan_claude(home, root=root))
    keystore = Keystore(home / "state", OWNER)
    assert made and all(not d.exists() for _, d in made)
    assert not any(keystore.present("IM", ref) for ref, _ in made)


def test_staging_a_crash_left_is_swept_key_first_and_fresh_staging_stays(world):
    home, _ = world
    store = ImportStore(home, OWNER)
    stale, fresh = store.stage("claude-code"), store.stage("claude-code")
    stale.write(b"x" * 10)
    (stale.dir / "chunk-00000.enc").write_bytes(stale.cipher.seal("chunk-00000", b"planted"))
    past = time.time() - 7200
    for path in [stale.dir, *stale.dir.iterdir()]:
        os.utime(path, (past, past))
    assert trace_import_items.sweep_staging(home) == 1
    keystore = Keystore(home / "state", OWNER)
    assert not stale.dir.exists() and not keystore.present("IM", stale.ref)
    assert fresh.dir.exists()


def test_gateway_start_runs_the_sweep(world):
    from harness.trace_enc_probe import startup
    home, _ = world
    stale = ImportStore(home, OWNER).stage("codex")
    past = time.time() - 7200
    os.utime(stale.dir, (past, past))
    startup(home)
    assert not stale.dir.exists()
