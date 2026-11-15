"""The purge command's exit status, its refusals, and what it prints.

A purge that leaves residue, leaves its scrub unfinished or ends with an audit
chain that fails exits with a failure code, so a script sees it. A file that
is not a canon context store is refused before anything is written to it.
`--confirm-plan` applies only the plan a dry run showed, and `--yes` prints the
plan it applies. Previews run through the secret scrubber, and JSON output
carries them only with `--show-preview`.
"""
from __future__ import annotations

import io
import json
import secrets
import sqlite3

import pytest

import canon.context_purge as context_purge
from canon.cli import run_cli
from canon.context_store import ContextStore

from ._context_fixtures import PROJECT, WORKSPACE, answer_payload, counts, prompt_payload, rows


def _run(args, stdin=""):
    out, err = io.StringIO(), io.StringIO()
    code = run_cli(args, stdin=io.StringIO(stdin), stdout=out, stderr=err, environ={})
    return code, out.getvalue(), err.getvalue()


def _args(db, *extra, workspace=WORKSPACE):
    return ["context", "purge", "--db", str(db), "--workspace-id", workspace,
            "--project-id", PROJECT, *extra]


def _stored(tmp_path, text="Prompt about the tide tables"):
    db = tmp_path / "context.sqlite"
    store = ContextStore(db)
    prompt = store.ingest(prompt_payload("turn-1", text))["event_record_id"]
    store.ingest(answer_payload(prompt, "turn-1", "Answer about the tide tables"))
    return db, store, prompt


def _json(args):
    code, out, _ = _run(["--json", *args])
    return code, json.loads(out)


def test_residue_found_exits_with_a_failure_code(tmp_path, monkeypatch) -> None:
    db, _, prompt = _stored(tmp_path)
    real = context_purge.residual_scan
    monkeypatch.setattr(context_purge, "residual_scan",
                        lambda *a, **k: {**real(*a, **k), "hits": 3})

    code, result = _json(_args(db, "--event-id", prompt, "--yes"))

    assert code == 1 and result["ok"] is False
    assert result["failure_code"] == "residue_found"
    assert result["data"]["status"] == "residue_found"


def test_an_unfinished_scrub_exits_with_a_failure_code_now_and_on_the_rerun(
        tmp_path, monkeypatch) -> None:
    db, _, prompt = _stored(tmp_path)
    busy = {"journal_mode": "delete", "vacuum": "skipped_database_busy",
            "wal_checkpoint": "not_needed"}
    monkeypatch.setattr(context_purge, "scrub_database", lambda conn, budget: dict(busy))

    code, result = _json(_args(db, "--event-id", prompt, "--yes"))
    assert (code, result["failure_code"]) == (1, "scrub_incomplete")

    code, result = _json(_args(db, "--event-id", prompt, "--yes"))
    assert (code, result["failure_code"]) == (1, "scrub_incomplete")
    assert result["data"]["status"] == "scrub_incomplete"


def test_an_audit_chain_that_fails_after_the_purge_exits_with_a_failure_code(
        tmp_path, monkeypatch) -> None:
    db, _, prompt = _stored(tmp_path)
    monkeypatch.setattr(ContextStore, "verify_chain", lambda self: {"ok": False, "length": 0})

    code, result = _json(_args(db, "--event-id", prompt, "--yes"))

    assert (code, result["failure_code"]) == (1, "audit_failed")


def test_a_file_that_is_not_a_database_is_refused_without_a_traceback(tmp_path) -> None:
    db = tmp_path / "notes.sqlite"
    db.write_text("these are plain notes, not a database\n", encoding="utf-8")

    code, out, err = _run(_args(db, "--all", "--dry-run"))

    assert code == 8 and "Traceback" not in out + err
    assert "not a canon context store" in err


@pytest.mark.parametrize("workspace", ["", "w" * 300])
def test_a_bad_workspace_id_is_invalid_args_without_a_traceback(tmp_path, workspace) -> None:
    db, _, _ = _stored(tmp_path)

    code, result = _json(_args(db, "--all", "--dry-run", workspace=workspace))

    assert (code, result["failure_code"]) == (2, "invalid_args")


def test_a_dry_run_against_another_sqlite_file_writes_nothing_into_it(tmp_path) -> None:
    other = tmp_path / "other.sqlite"
    con = sqlite3.connect(str(other))
    con.execute("CREATE TABLE notes(body TEXT)")
    con.commit()
    con.close()
    before = other.read_bytes()

    code, result = _json(_args(other, "--all", "--dry-run"))

    assert (code, result["failure_code"]) == (8, "store_invalid")
    assert rows(other, "SELECT name FROM sqlite_master") == [("notes",)]
    assert other.read_bytes() == before


def test_confirm_plan_refuses_a_plan_the_store_has_moved_past(tmp_path) -> None:
    db, store, _ = _stored(tmp_path)
    _, dry = _json(_args(db, "--all", "--dry-run"))
    store.ingest(prompt_payload("turn-2", "Captured after the dry run"))
    before = counts(db)

    code, result = _json(_args(db, "--all", "--confirm-plan", dry["data"]["plan_sha256"]))
    assert (code, result["failure_code"]) == (5, "plan_stale")
    assert counts(db) == before

    _, fresh = _json(_args(db, "--all", "--dry-run"))
    code, result = _json(_args(db, "--all", "--confirm-plan", fresh["data"]["plan_sha256"]))
    assert code == 0 and result["data"]["records_purged"] == 7


def test_yes_prints_the_plan_it_applies(tmp_path) -> None:
    db, _, prompt = _stored(tmp_path)

    code, out, _ = _run(_args(db, "--event-id", prompt, "--yes"))

    assert code == 0
    assert out.index("records to purge: 4") < out.index("plan sha256:") < out.index("purged 4")


def test_previews_are_scrubbed_and_json_carries_them_only_on_request(tmp_path) -> None:
    fake = "sk-FAKE" + secrets.token_hex(20)
    db, _, prompt = _stored(tmp_path, f"OPENAI_API_KEY={fake} and the tide tables")

    code, out, _ = _run(_args(db, "--event-id", prompt, "--dry-run"))
    assert code == 0 and fake not in out and "[REDACTED:" in out

    _, result = _json(_args(db, "--event-id", prompt, "--dry-run"))
    assert "events" not in result["data"] and fake not in json.dumps(result)

    _, result = _json(_args(db, "--event-id", prompt, "--dry-run", "--show-preview"))
    assert result["data"]["events"] and fake not in json.dumps(result)
