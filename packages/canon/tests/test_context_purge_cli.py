"""`canon context purge` and `canon context retention` on the command line.

--dry-run prints the plan and deletes nothing. --yes plans and applies. With
neither, the command prints the plan and asks, and only the word "purge" typed
back applies it. Text the command prints from stored events has its control
characters escaped, so a captured prompt cannot drive the terminal.
"""
from __future__ import annotations

import io
import json
import sqlite3

from canon.cli import run_cli
from canon.context_retention import POLICY_SCHEMA
from canon.context_store import ContextStore

from ._context_fixtures import PROJECT, WORKSPACE, answer_payload, counts, prompt_payload


def _run(args, stdin="", env=None):
    out, err = io.StringIO(), io.StringIO()
    code = run_cli(args, stdin=io.StringIO(stdin), stdout=out, stderr=err, environ=env or {})
    return code, out.getvalue(), err.getvalue()


def _purge_args(db, *extra):
    return ["context", "purge", "--db", str(db), "--workspace-id", WORKSPACE,
            "--project-id", PROJECT, *extra]


def _stored(tmp_path, prompt_text="Prompt about the tide tables"):
    db = tmp_path / "context.sqlite"
    store = ContextStore(db)
    prompt = store.ingest(prompt_payload("turn-1", prompt_text))["event_record_id"]
    store.ingest(answer_payload(prompt, "turn-1", "Answer about the tide tables"))
    return db, store, prompt


def test_dry_run_prints_the_plan_and_deletes_nothing(tmp_path) -> None:
    db, _, prompt = _stored(tmp_path)
    before = counts(db)

    code, out, err = _run(_purge_args(db, "--event-id", prompt, "--dry-run"))

    assert (code, err) == (0, "")
    assert "records to purge: 4 (events 1, answers 1, derived 2)" in out
    assert prompt in out
    assert "plan sha256:" in out
    assert "freed disk clusters" in out
    assert "dry run: nothing was deleted" in out
    assert counts(db) == before


def test_yes_applies_and_prints_the_report_with_its_residue(tmp_path) -> None:
    db, store, prompt = _stored(tmp_path)

    code, out, err = _run(_purge_args(db, "--event-id", prompt, "--yes"))

    assert (code, err) == (0, "")
    assert "purged 4 records (events 1, answers 1, derived 2)" in out
    assert "residual scan: 0 hits" in out
    assert "legacy fingerprints: 0" in out
    assert "outside canon's reach:" in out
    assert store.get(WORKSPACE, PROJECT, prompt)["status"] == "not_found_in_searched_sources"


def test_without_yes_it_asks_and_only_the_word_purge_confirms(tmp_path) -> None:
    db, store, prompt = _stored(tmp_path)
    before = counts(db)

    code, out, err = _run(_purge_args(db, "--all"), stdin="yes\n")
    assert code == 1
    assert "Type purge to delete these 4 records" in out
    assert "not confirmed" in err
    assert counts(db) == before

    code, out, _ = _run(_purge_args(db, "--all"), stdin="purge\n")
    assert code == 0
    assert "purged 4 records" in out
    assert store.get(WORKSPACE, PROJECT, prompt)["status"] == "not_found_in_searched_sources"


def test_json_dry_run_is_machine_readable_and_json_needs_a_mode(tmp_path) -> None:
    db, _, prompt = _stored(tmp_path)

    code, out, _ = _run(["--json"] + _purge_args(db, "--event-id", prompt, "--dry-run"))
    result = json.loads(out)
    assert code == 0 and result["ok"] is True
    assert result["data"]["counts"]["records"] == 4
    assert result["data"]["plan_sha256"].startswith("sha256:")

    code, out, _ = _run(["--json"] + _purge_args(db, "--event-id", prompt))
    assert code == 2 and json.loads(out)["failure_code"] == "invalid_args"


def test_the_database_comes_from_the_environment_and_must_exist(tmp_path) -> None:
    db, _, prompt = _stored(tmp_path)
    args = ["context", "purge", "--workspace-id", WORKSPACE, "--project-id", PROJECT,
            "--event-id", prompt, "--dry-run"]

    code, out, _ = _run(args, env={"CANON_CONTEXT_DB": str(db)})
    assert code == 0 and "records to purge: 4" in out

    missing = tmp_path / "missing.sqlite"
    code, _, err = _run(args, env={"CANON_CONTEXT_DB": str(missing)})
    assert code != 0 and "not found" in err
    assert not missing.exists()


def test_control_characters_in_stored_text_are_escaped(tmp_path) -> None:
    db, _, prompt = _stored(tmp_path, "Prompt \x1b]0;owned\x07 with an escape")

    code, out, _ = _run(_purge_args(db, "--event-id", prompt, "--dry-run"))

    assert code == 0
    assert "\x1b" not in out and "\x07" not in out
    assert "\\x1b]0;owned\\x07" in out


def test_a_purge_run_again_says_the_event_was_already_purged(tmp_path) -> None:
    db, _, prompt = _stored(tmp_path)
    assert _run(_purge_args(db, "--event-id", prompt, "--yes"))[0] == 0

    code, out, _ = _run(_purge_args(db, "--event-id", prompt, "--dry-run"))
    assert code == 0
    assert "already purged: 1 event" in out

    code, out, _ = _run(_purge_args(db, "--event-id", prompt, "--yes"))
    assert code == 0
    assert "nothing to purge: 1 selected event was already purged" in out


def test_a_policy_file_nested_past_the_parser_limit_is_refused(tmp_path) -> None:
    db, _, _ = _stored(tmp_path)
    policy = tmp_path / "retention.json"
    policy.write_text("[" * 100_000 + "]" * 100_000, encoding="utf-8")

    code, out, _ = _run(["--json", "context", "retention", "--db", str(db), "--workspace-id",
                         WORKSPACE, "--project-id", PROJECT, "--policy", str(policy),
                         "--dry-run"])

    assert code == 2
    assert json.loads(out)["failure_code"] == "invalid_args"


def test_retention_plans_and_applies_a_policy_file(tmp_path) -> None:
    db, store, prompt = _stored(tmp_path)
    policy = tmp_path / "retention.json"
    policy.write_text(json.dumps({"schema": POLICY_SCHEMA, "policies": [
        {"subject_id": prompt, "action": "purge-all", "retain_content_hash": False,
         "derived_stores": ["sqlite"]}]}), encoding="utf-8")
    args = ["context", "retention", "--db", str(db), "--workspace-id", WORKSPACE,
            "--project-id", PROJECT, "--policy", str(policy)]

    code, out, _ = _run(args + ["--dry-run"])
    assert code == 0 and "records to purge: 4" in out
    assert "retention_purge_all" in out

    code, out, _ = _run(args + ["--yes"])
    assert code == 0 and "purged 4 records" in out
    assert store.get(WORKSPACE, PROJECT, prompt)["status"] == "not_found_in_searched_sources"


def _foreign_wal_database(tmp_path, *, store=False):
    db = tmp_path / "context.sqlite"
    if store:
        ContextStore(db).ingest(prompt_payload("turn-1", "Prompt about the tide tables"))
    conn = sqlite3.connect(db)
    assert conn.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    if not store:
        conn.execute("CREATE TABLE unrelated(value TEXT)")
        conn.commit()
    conn.close()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["context.sqlite"]
    return db


def test_a_wal_mode_file_that_is_not_a_store_is_refused_without_new_files(tmp_path) -> None:
    db = _foreign_wal_database(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}

    code, out, _ = _run(["--json", *_purge_args(db, "--all", "--dry-run")])

    assert (code, json.loads(out)["failure_code"]) == (8, "store_invalid")
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_the_store_check_on_a_large_idle_wal_file_creates_no_files(tmp_path, monkeypatch) -> None:
    from canon import client_mcp_store
    db = _foreign_wal_database(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    monkeypatch.setattr(client_mcp_store, "MAX_SNAPSHOT_BYTES", 1)

    code, out, _ = _run(["--json", *_purge_args(db, "--all", "--dry-run")])

    assert (code, json.loads(out)["failure_code"]) == (8, "store_invalid")
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before
