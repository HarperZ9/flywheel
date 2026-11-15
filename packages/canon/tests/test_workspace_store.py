"""The per-project store. The contamination controls here are the point: a
record written for project A must never reach project B's render or read, and
the only ways across are an explicit promotion or an explicit declaration."""
from __future__ import annotations

import json
from dataclasses import replace

import pytest

from canon.concurrency import LockError, acquire_run_lock, release_run_lock
from canon.surface import render_surface
from canon.workspace.identity import derive_identity
from canon.workspace.moves import adopt, promote
from canon.workspace.pool import block_pool, project_pool, visible_records
from canon.workspace.rows import RowError
from canon.workspace.store import IsolationError, ProjectStore, StoreError

from ._workspace_helpers import block, decision, init_repo

A_SECRET_WORD = "alpha-only-phrase"


@pytest.fixture()
def two_projects(tmp_path):
    root = tmp_path / "store"
    a = derive_identity(init_repo(tmp_path / "a", "https://github.com/o/a"))
    b = derive_identity(init_repo(tmp_path / "b", "https://github.com/o/b"))
    store_a, store_b = ProjectStore(root, a), ProjectStore(root, b)
    store_a.put(block("voice", f"Project A says {A_SECRET_WORD}.", 1))
    store_a.put(decision("d-1", f"A decided {A_SECRET_WORD}.", 2))
    store_b.put(block("voice-b", "Project B voice.", 1))
    return store_a, store_b


def test_a_new_record_is_stored_bound_to_its_project(two_projects):
    store_a, _ = two_projects
    lines = (store_a.project_dir() / "records.jsonl").read_text(encoding="utf-8")
    rows = [json.loads(line) for line in lines.splitlines()]
    assert {row["project_id"] for row in rows} == {store_a.project_id}
    assert {row["record"]["scope"] for row in rows} == {"workspace"}


def test_contamination_control_project_a_never_reaches_project_b(two_projects):
    store_a, store_b = two_projects
    pool = project_pool(store_b)
    rendered = render_surface(block_pool(pool), "workspace")
    assert A_SECRET_WORD not in rendered
    assert "Project B voice." in rendered
    assert all(t.project_id in (None, store_b.project_id) for t in pool)
    assert A_SECRET_WORD not in json.dumps([t.record.to_dict() for t in pool])


def test_a_row_misfiled_into_another_project_is_refused_not_filtered(two_projects):
    store_a, store_b = two_projects
    a_line = (store_a.project_dir() / "records.jsonl").read_text(encoding="utf-8")
    b_file = store_b.project_dir() / "records.jsonl"
    b_file.write_text(b_file.read_text(encoding="utf-8") + a_line, encoding="utf-8")
    with pytest.raises(IsolationError, match="refusing the file"):
        store_b.records()
    with pytest.raises(IsolationError):
        project_pool(store_b)


def test_another_project_is_readable_only_when_declared(two_projects):
    store_a, store_b = two_projects
    tagged = visible_records(store_b, include_projects=(store_a.project_id,))
    foreign = [rec for pid, rec in tagged if pid == store_a.project_id]
    assert {rec.id for rec in foreign} == {"voice", "d-1"}
    undeclared = visible_records(store_b)
    assert all(pid != store_a.project_id for pid, _ in undeclared)


def test_a_declared_block_that_collides_by_id_is_refused(two_projects):
    store_a, store_b = two_projects
    store_b.put(block("voice", "B also has a voice block.", 3))
    with pytest.raises(IsolationError, match="override"):
        project_pool(store_b, include_projects=(store_a.project_id,))


def test_a_global_record_cannot_be_put_only_promoted(two_projects):
    store_a, _ = two_projects
    with pytest.raises(StoreError, match="promote"):
        store_a.put(block("g", "global body", 9, scope="global"))


def test_promotion_is_explicit_logged_and_then_visible_everywhere(two_projects):
    store_a, store_b = two_projects
    with pytest.raises(StoreError, match="reason"):
        promote(store_a, "voice", reason="  ")
    row = promote(store_a, "voice", reason="applies to every project")
    assert row.project_id is None and row.promoted_from == store_a.project_id
    assert row.record.scope == "global"
    assert "voice" not in {r.id for r in store_a.records()}
    b_pool = [t for t in project_pool(store_b) if t.record.id == "voice"]
    assert [t.project_id for t in b_pool] == [None]
    actions = [e["action"] for e in store_a.log_entries()]
    assert actions[-1] == "promote"
    global_log = (store_a.global_dir() / "log.jsonl").read_text(encoding="utf-8")
    entry = json.loads(global_log.splitlines()[-1])
    assert entry["from_project"] == store_a.project_id
    assert entry["reason"] == "applies to every project"


def test_a_global_file_holding_a_project_row_is_refused(two_projects):
    store_a, store_b = two_projects
    a_line = (store_a.project_dir() / "records.jsonl").read_text(encoding="utf-8")
    (store_b.global_dir()).mkdir(parents=True, exist_ok=True)
    (store_b.global_dir() / "records.jsonl").write_text(a_line, encoding="utf-8")
    with pytest.raises(IsolationError):
        store_b.global_rows()


def test_the_file_bytes_do_not_depend_on_write_order(tmp_path):
    ident = derive_identity(init_repo(tmp_path / "r", "https://github.com/o/r"))
    one, two = ProjectStore(tmp_path / "s1", ident), ProjectStore(tmp_path / "s2", ident)
    recs = [block("b", "B body", 2), block("a", "A body", 1)]
    for rec in recs:
        one.put(rec)
    for rec in reversed(recs):
        two.put(rec)
    assert (one.project_dir() / "records.jsonl").read_bytes() == \
        (two.project_dir() / "records.jsonl").read_bytes()


def test_a_malformed_row_is_reported_with_its_line(two_projects):
    _, store_b = two_projects
    path = store_b.project_dir() / "records.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + "{not json\n", encoding="utf-8")
    with pytest.raises(RowError, match=r"records.jsonl:2"):
        store_b.records()


def test_an_invalid_record_in_a_row_is_refused(two_projects):
    _, store_b = two_projects
    path = store_b.project_dir() / "records.jsonl"
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    row["record"]["data"]["body"] = ""
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(RowError, match="invalid"):
        store_b.records()


def test_a_held_run_lock_blocks_a_second_writer(two_projects):
    store_a, _ = two_projects
    lock = acquire_run_lock(store_a.root, f"canon-project-{store_a.project_id}")
    try:
        with pytest.raises(LockError):
            store_a.put(block("late", "Late body", 5))
    finally:
        release_run_lock(lock)
    assert "late" not in {r.id for r in store_a.records()}


def test_a_store_opened_by_id_alone_does_not_write_a_manifest(tmp_path):
    ident = derive_identity(init_repo(tmp_path / "r", "https://github.com/o/r"))
    bare = ProjectStore(tmp_path / "s", ident.project_id)
    with pytest.raises(StoreError, match="does not write"):
        bare.put(block("x", "X body", 1))


def test_replacing_a_record_keeps_one_row_per_id(two_projects):
    store_a, _ = two_projects
    first = next(r for r in store_a.records() if r.id == "voice")
    store_a.put(replace(first, data={**first.data, "body": "Rewritten."}))
    ids = [r.id for r in store_a.records()]
    assert sorted(ids) == sorted(set(ids))
    assert store_a.next_ord() == 3


def test_a_moved_unversioned_project_recovers_its_records_by_adoption(tmp_path):
    root = tmp_path / "store"
    old = derive_identity(init_repo(tmp_path / "old-place" / "proj"))
    new = derive_identity(init_repo(tmp_path / "new-place" / "proj"))
    assert old.project_id != new.project_id
    ProjectStore(root, old).put(block("voice", "Carried over.", 1))
    target = ProjectStore(root, new)
    with pytest.raises(StoreError, match="reason"):
        adopt(target, old.project_id, reason="")
    rows = adopt(target, old.project_id, reason="moved the checkout")
    assert [r.record.id for r in rows] == ["voice"]
    assert {r.project_id for r in target.rows()} == {new.project_id}
    entry = target.log_entries()[-1]
    assert entry["action"] == "adopt" and entry["from_project"] == old.project_id


def test_adoption_never_overwrites_this_projects_own_record(two_projects):
    store_a, store_b = two_projects
    store_b.put(block("voice", "B keeps its own voice.", 5))
    before = (store_b.project_dir() / "records.jsonl").read_bytes()
    with pytest.raises(StoreError, match="overwrite"):
        adopt(store_b, store_a.project_id, reason="merge")
    assert (store_b.project_dir() / "records.jsonl").read_bytes() == before


def test_a_project_directory_that_names_another_project_is_refused(two_projects):
    store_a, store_b = two_projects
    manifest = store_b.project_dir() / "project.json"
    manifest.write_text(json.dumps({"project_id": store_a.project_id}), encoding="utf-8")
    fresh = ProjectStore(store_b.root, store_b.identity)
    with pytest.raises(StoreError, match="names another project"):
        fresh.put(block("late", "Late body.", 9))
