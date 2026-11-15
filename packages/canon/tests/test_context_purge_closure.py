"""What a purge plan covers beyond one live prompt, and what the store refuses.

An answer stored after its prompt was purged goes with a rerun of that purge.
`keep_responses` keeps the paired answers whichever selector names the
prompts. A retention policy cannot both retain an answer and purge the prompt
that takes it. A schema object canon did not create, such as a trigger that
copies deleted rows, fails integrity before any plan. The purge chain step and
the tombstone set are pinned, and every plan and report says that no owner
presence check guards the apply.
"""
from __future__ import annotations

import hashlib
import sqlite3

import pytest

from canon.backends.sqlite import SqliteBackend
from canon.context_purge import ContextPurgeError, select
from canon.context_retention import POLICY_SCHEMA, policy_selection
from canon.context_scrub import live_values
from canon.context_store import ContextIntegrityError, ContextStore

from ._context_fixtures import (
    PROJECT, WORKSPACE, answer_payload, db_files, prompt_payload, rows, short_canary,
    window_hits,
)


def _pair(tmp_path, canary="tide tables"):
    db = tmp_path / "context.sqlite"
    store = ContextStore(db)
    prompt = store.ingest(prompt_payload("turn-7", f"Prompt about {canary}"))["event_record_id"]
    answer = store.ingest(answer_payload(prompt, "turn-7", f"Answer about {canary}"))
    store.ingest(prompt_payload("turn-8", "An unrelated kept prompt about gardening"))
    return db, store, prompt, answer["event_record_id"]


def _purge(store, selection):
    plan = store.purge_plan(WORKSPACE, PROJECT, selection)
    return plan, store.purge(WORKSPACE, PROJECT, selection,
                             confirm_plan_sha256=plan["plan_sha256"])


def _found(store, record_id) -> bool:
    return store.get(WORKSPACE, PROJECT, record_id)["status"] == "found_in_searched_sources"


def test_a_rerun_takes_an_answer_stored_after_its_prompt_was_purged(tmp_path,
                                                                     monkeypatch) -> None:
    canary = short_canary()
    db = tmp_path / "context.sqlite"
    store = ContextStore(db)
    prompt = store.ingest(prompt_payload("turn-1", f"Prompt {canary}"))["event_record_id"]
    _purge(store, select(event_id=prompt))
    # The store now refuses such an answer (D-164); one stored before that
    # check existed is planted with the check turned off.
    monkeypatch.setattr("canon.context_store._require_prompt", lambda *args: None)
    late = store.ingest(answer_payload(prompt, "turn-1", f"Answer {canary}"))["event_record_id"]
    monkeypatch.undo()

    plan, report = _purge(store, select(event_id=prompt))

    assert plan["already_purged"] == [prompt]
    assert plan["counts"]["responses"] == 1
    assert report["status"] == "purged"
    assert not _found(store, late)
    assert store.query(WORKSPACE, PROJECT, canary)["hits"] == []
    assert window_hits(db_files(db), canary) == 0


@pytest.mark.parametrize("selector", [{"all_events": True}, {"before_ord": 10_000}])
def test_keep_responses_keeps_the_answer_with_a_bulk_selector(tmp_path, selector) -> None:
    _, store, prompt, answer = _pair(tmp_path)

    plan, report = _purge(store, select(keep_responses=True, **selector))

    assert plan["counts"]["responses"] == 0
    assert answer not in {row["event_record_id"] for row in plan["entries"]}
    assert report["status"] == "purged"
    assert _found(store, answer) and not _found(store, prompt)


def test_a_bulk_selector_without_keep_responses_still_takes_the_answer(tmp_path) -> None:
    _, store, prompt, answer = _pair(tmp_path)

    _purge(store, select(all_events=True))

    assert not _found(store, answer) and not _found(store, prompt)


@pytest.mark.parametrize("answer_action", ["retain", "purge-derived"])
def test_a_policy_that_keeps_an_answer_its_prompt_rule_removes_is_refused(
        tmp_path, answer_action) -> None:
    _, store, prompt, answer = _pair(tmp_path)
    policy = {"schema": POLICY_SCHEMA, "policies": [
        {"subject_id": prompt, "action": "purge-all", "derived_stores": ["sqlite"]},
        {"subject_id": answer, "action": answer_action, "derived_stores": ["sqlite"]}]}

    with pytest.raises(ContextPurgeError, match="keep_responses"):
        store.purge_plan(WORKSPACE, PROJECT, policy_selection(policy))

    policy["keep_responses"] = True
    plan, _ = _purge(store, policy_selection(policy))
    assert plan["counts"]["responses"] == 0
    assert _found(store, answer) and not _found(store, prompt)


def _plant(db, *statements) -> None:
    con = sqlite3.connect(str(db))
    try:
        for statement in statements:
            con.execute(statement)
        con.commit()
    finally:
        con.close()


def test_a_trigger_that_copies_deleted_rows_is_refused_before_any_plan(tmp_path) -> None:
    db, store, prompt, _ = _pair(tmp_path)
    _plant(db, "CREATE TABLE kv(v TEXT)",
           "CREATE TRIGGER keep AFTER DELETE ON records BEGIN "
           "INSERT INTO kv VALUES(hex(OLD.envelope)); END")

    with pytest.raises(ContextIntegrityError, match="schema"):
        store.purge_plan(WORKSPACE, PROJECT, select(event_id=prompt))
    assert store.verify_chain()["ok"] is False
    assert rows(db, "SELECT COUNT(*) FROM kv")[0][0] == 0


@pytest.mark.parametrize("statement", [
    "CREATE TABLE kv(v TEXT)",
    "CREATE VIEW everything AS SELECT envelope FROM records",
    "CREATE INDEX envelopes ON records(envelope)",
])
def test_any_schema_object_canon_did_not_create_fails_integrity(tmp_path, statement) -> None:
    db, store, _, _ = _pair(tmp_path)
    _plant(db, statement)

    with pytest.raises(ContextIntegrityError):
        store.query(WORKSPACE, PROJECT, "tide")


def test_the_kept_text_the_scan_subtracts_comes_only_from_canon_tables(tmp_path) -> None:
    db, _, _, _ = _pair(tmp_path)
    marker = short_canary()
    _plant(db, "CREATE TABLE kv(v TEXT)", f"INSERT INTO kv VALUES('{marker}')")

    con = sqlite3.connect(str(db))
    try:
        values = live_values(con)
    finally:
        con.close()

    assert not any(marker.encode() in value for value in values)
    assert any(b"gardening" in value for value in values)


def test_a_purge_row_relabelled_as_a_put_breaks_the_chain(tmp_path) -> None:
    db, store, prompt, _ = _pair(tmp_path)
    _purge(store, select(event_id=prompt))
    seq, key, sha, prev, chain = rows(
        db, "SELECT seq, key, sha256, prev_hash, chain_hash FROM audit WHERE op='purge' "
            "ORDER BY seq")[0]

    expected = hashlib.sha256((prev + "purge" + "\x1f" + key + sha).encode()).hexdigest()
    assert chain == expected
    _plant(db, f"UPDATE audit SET op='put' WHERE seq={seq}")

    assert SqliteBackend(db).verify_chain()["ok"] is False
    assert store.verify_chain()["ok"] is False


def test_an_orphan_tombstone_fails_integrity(tmp_path) -> None:
    db, store, prompt, _ = _pair(tmp_path)
    _purge(store, select(event_id=prompt))
    _plant(db, "INSERT INTO context_tombstones(seq, tombstone) VALUES(99999, '{}')")

    assert store.verify_chain()["ok"] is False
    with pytest.raises(ContextIntegrityError):
        store.query(WORKSPACE, PROJECT, "tide")


def test_plans_and_reports_say_no_presence_check_guards_the_apply(tmp_path) -> None:
    _, store, prompt, _ = _pair(tmp_path)

    plan, report = _purge(store, select(event_id=prompt))

    for result in (plan, report):
        assert result["presence"] == "none"
        assert any("agents included" in line for line in result["does_not_prove"])


def test_a_purged_event_sent_again_is_stored_and_reported_as_stored_after_purge(
        tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    store = ContextStore(db)
    payload = prompt_payload("turn-1", "A prompt the client sends twice")
    first = store.ingest(payload)["event_record_id"]
    _purge(store, select(event_id=first))

    again = store.ingest(payload)

    assert again["status"] == "stored_after_purge"
    assert again["records_stored"] == 3
    assert store.ingest(payload)["status"] == "already_present"
