"""The workspace-state kinds: their own schema tag, their validation rules, the
optional rejected-alternatives field on a decision, and the promise that every
record written before W1 reads and serializes exactly as it did."""
from __future__ import annotations

import json

import pytest

from canon.backends import FilesBackend, SqliteBackend, UnsupportedKind
from canon.schema import (
    KINDS,
    SCHEMA,
    WORKSPACE_KINDS,
    WORKSPACE_STATE_SCHEMA,
    Record,
    schema_tag_for,
)
from canon.validator import validate_record
from canon.workspace import authoring
from canon.workspace.identity import derive_identity
from canon.workspace.store import ProjectStore

from ._helpers import RECORD_FILES, load_dict
from ._workspace_helpers import decision, init_repo


@pytest.fixture()
def store(tmp_path):
    ident = derive_identity(init_repo(tmp_path / "r", "https://github.com/o/r"))
    return ProjectStore(tmp_path / "store", ident)


def test_the_workspace_kinds_carry_their_own_tag_and_round_trip(store):
    records = [
        authoring.focus(store, goal="Ship the handoff", areas=["src/canon"], branch="main"),
        authoring.work_item(store, title="Write the importer", status="in-progress"),
        authoring.constraint(store, statement="CI runs on Windows too", category="quirk"),
    ]
    for rec in records:
        payload = rec.to_dict()
        assert payload["canon_schema"] == WORKSPACE_STATE_SCHEMA
        assert Record.from_dict(json.loads(json.dumps(payload))) == rec
        assert validate_record(rec) == []


@pytest.mark.parametrize("kind", ["personality-block", "episodic-memory",
                                  "synthesized-persona-l3", "adr-decision",
                                  "research-artifact-ref"])
def test_every_v1_fixture_keeps_its_tag_and_its_bytes(kind):
    raw = load_dict(RECORD_FILES[kind])
    rec = Record.from_dict(raw)
    assert rec.to_dict() == raw
    assert rec.to_dict()["canon_schema"] == SCHEMA == "canon.record/v1"
    assert validate_record(rec) == []


def test_a_mismatched_tag_is_refused_in_both_directions(store):
    ws = authoring.work_item(store, title="t").to_dict()
    ws["canon_schema"] = SCHEMA
    with pytest.raises(ValueError, match="workspace-state"):
        Record.from_dict(ws)
    v1 = load_dict(RECORD_FILES["adr-decision"])
    v1["canon_schema"] = WORKSPACE_STATE_SCHEMA
    with pytest.raises(ValueError, match="canon.record/v1"):
        Record.from_dict(v1)


def test_the_tag_is_a_function_of_the_kind():
    assert {schema_tag_for(k) for k in KINDS} == {SCHEMA}
    assert {schema_tag_for(k) for k in WORKSPACE_KINDS} == {WORKSPACE_STATE_SCHEMA}
    assert schema_tag_for("not-a-kind") == SCHEMA


@pytest.mark.parametrize("builder, kwargs, needle", [
    (authoring.focus, {"goal": ""}, "goal"),
    (authoring.focus, {"goal": "g", "areas": [""]}, "areas"),
    (authoring.work_item, {"title": "t", "status": "finished"}, "status"),
    (authoring.work_item, {"title": ""}, "title"),
    (authoring.constraint, {"statement": "s", "category": "rule"}, "category"),
    (authoring.decision, {"title": "t", "decision_text": "d", "context": "c",
                          "rejected": [("", "no option")]}, "option"),
    (authoring.decision, {"title": "t", "decision_text": "d", "context": "c",
                          "rejected": [("an option", " ")]}, "reason"),
])
def test_an_invalid_workspace_record_is_refused_with_its_reason(store, builder, kwargs, needle):
    with pytest.raises(authoring.AuthoringError, match=needle):
        builder(store, **kwargs)


def test_a_decision_keeps_its_rejected_alternatives_with_reasons(store):
    rec = authoring.decision(store, title="Store format", decision_text="JSONL rows",
                             context="Needs diffs", rejected=[("SQLite", "binary diffs")])
    assert rec.data["rejected_alternatives"] == [{"option": "SQLite", "reason": "binary diffs"}]
    assert rec.to_dict()["canon_schema"] == SCHEMA


@pytest.mark.parametrize("bad", [
    "SQLite",
    [{"option": "SQLite"}],
    [{"option": "SQLite", "reason": "r", "extra": 1}],
    [["SQLite", "reason"]],
])
def test_a_malformed_rejected_alternatives_field_fails_validation(bad):
    rec = decision("d-1", "Use rows.", rejected_alternatives=bad)
    assert any("rejected_alternatives" in p for p in validate_record(rec))


def test_a_decision_without_the_new_field_is_still_valid():
    assert validate_record(decision("d-1", "Use rows.")) == []


def test_focus_is_one_record_per_project(store):
    store.put(authoring.focus(store, goal="first"))
    store.put(authoring.focus(store, goal="second"))
    focus = [r for r in store.records() if r.kind == "workspace-focus"]
    assert [r.data["goal"] for r in focus] == ["second"]


def test_a_status_change_keeps_the_id_and_the_ordinal(store):
    item = authoring.work_item(store, title="Port the parser")
    store.put(item)
    store.put(authoring.work_item(store, title="Later work"))
    updated = authoring.update_work_item(store, item.id, status="done")
    assert updated.id == item.id
    assert updated.provenance.create_ord == item.provenance.create_ord
    assert updated.data["status"] == "done"
    with pytest.raises(authoring.AuthoringError, match="no work item"):
        authoring.update_work_item(store, "task-999", status="done")


def test_the_branch_is_read_from_head_without_running_git(tmp_path):
    repo = init_repo(tmp_path / "r", "https://github.com/o/r")
    (repo / ".git" / "HEAD").write_text("ref: refs/heads/feat/handoff\n", encoding="utf-8")
    assert authoring.current_branch(repo) == "feat/handoff"
    (repo / ".git" / "HEAD").write_text("0123abcd\n", encoding="utf-8")
    assert authoring.current_branch(repo) is None


def test_the_storage_adapters_refuse_a_workspace_state_record(store, tmp_path):
    item = authoring.work_item(store, title="Not for the adapters")
    for backend in (FilesBackend(tmp_path / "files"), SqliteBackend(str(tmp_path / "db.sqlite"))):
        with pytest.raises(UnsupportedKind):
            backend.put(item)
