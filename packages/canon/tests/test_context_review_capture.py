"""Capture-side findings from the review of the purge and capture branch.

An answer is stored only while its prompt is live, checked inside the write
that stores it, so a purge that lands between the hook's check and its insert
cannot leave an answer behind. The hook reads its input as UTF-8 whatever the
locale. The context it hands back lists pending sources scrubbed and one per
line, and never lists a recorded transcript path.
"""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from canon import client_capture_stop
from canon.context_mcp import ENV_CONTEXT_DB, handle
from canon.context_purge import select
from canon.context_store import ContextStore

from ._context_fixtures import PROJECT, WORKSPACE, answer_payload, prompt_payload
from .test_client_capture_stop import (
    RESPONSES, _answers, _prompt_hook, _prompt_record_id, _run, _stop_hook,
)

_SRC = Path(__file__).resolve().parents[1] / "src"


class _PurgeBeforeInsert:
    """A store that runs a confirmed purge of the prompt just before each
    ingest, as a second process could between the hook's reads and its write."""

    def __init__(self, db: Path, prompt: str) -> None:
        self.store, self.prompt, self.purged = ContextStore(db), prompt, False

    def __getattr__(self, name):
        return getattr(self.store, name)

    def ingest(self, payload, expected_store_id=None):
        if not self.purged:
            selection = select(event_id=self.prompt, keep_responses=True)
            plan = self.store.purge_plan(WORKSPACE, PROJECT, selection)
            self.store.purge(WORKSPACE, PROJECT, selection,
                             confirm_plan_sha256=plan["plan_sha256"])
            self.purged = True
        return self.store.ingest(payload, expected_store_id=expected_store_id)


def test_a_purge_between_the_prompt_check_and_the_insert_stores_no_answer(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    _run(_prompt_hook("claude-code"), db, "claude-code", *RESPONSES)
    racing = _PurgeBeforeInsert(db, _prompt_record_id(db))
    args = SimpleNamespace(capture=client_capture_stop.CAPTURE_RESPONSES, client="claude-code",
                           workspace_id=WORKSPACE, project_id=PROJECT, container_id="shared",
                           transcript_locator="path")

    out = client_capture_stop.capture_stop(_stop_hook("claude-code"), args, lambda: racing)

    assert out == {"systemMessage": client_capture_stop.PURGED_PROMPT}
    assert _answers(db) == []
    assert b"harbor ledger" not in db.read_bytes()


@pytest.mark.parametrize("purge_first", [True, False])
def test_the_store_refuses_an_answer_whose_prompt_is_not_live(tmp_path, purge_first) -> None:
    from canon.context_store import ContextPairingError

    db = tmp_path / "context.sqlite"
    store = ContextStore(db)
    prompt = store.ingest(prompt_payload("turn-1", "Where is the tide chart?"))["event_record_id"]
    target = prompt if purge_first else "context-event-" + "0" * 64
    if purge_first:
        plan = store.purge_plan(WORKSPACE, PROJECT, select(event_id=prompt))
        store.purge(WORKSPACE, PROJECT, select(event_id=prompt),
                    confirm_plan_sha256=plan["plan_sha256"])

    with pytest.raises(ContextPairingError) as caught:
        store.ingest(answer_payload(target, "turn-1", "The chart is in the harbor office"))

    assert caught.value.purged is purge_first
    assert b"harbor office" not in db.read_bytes()


def test_an_answer_ingested_over_mcp_for_a_missing_prompt_is_refused_by_name(
        tmp_path, monkeypatch) -> None:
    db = tmp_path / "context.sqlite"
    monkeypatch.setenv(ENV_CONTEXT_DB, str(db))
    payload = answer_payload("context-event-" + "0" * 64, "turn-1", "An orphan answer")

    reply = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                    "params": {"name": "canon.context.ingest", "arguments": payload}})

    assert reply["result"]["isError"] is True
    assert "prompt" in reply["result"]["content"][0]["text"]


def test_a_stop_with_no_session_or_one_answer_too_many_stores_nothing_and_says_why(
        tmp_path, monkeypatch) -> None:
    db = tmp_path / "context.sqlite"
    _run(_prompt_hook("claude-code"), db, "claude-code", *RESPONSES)
    no_session = _stop_hook("claude-code")
    del no_session["session_id"]
    monkeypatch.setattr(client_capture_stop, "MAX_SEGMENTS", 2)

    outputs = [_run(no_session, db, "claude-code", *RESPONSES)[1]]
    for text in ("First answer.", "Second answer.", "Third answer."):
        outputs.append(_run(_stop_hook("claude-code", text), db, "claude-code", *RESPONSES)[1])

    assert "session_id" in outputs[0]["systemMessage"]
    assert outputs[1:3] == [{}, {}]
    assert "not stored" in outputs[3]["systemMessage"]
    assert len(_answers(db)) == 2


def test_the_hook_reads_its_input_as_utf8_whatever_the_locale(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    text = "Where does the caf\u00e9 keep the \u00c1rbol ledger, se\u00f1or?"
    hook = _prompt_hook("codex", text)
    env = {key: value for key, value in os.environ.items()
           if key not in ("PYTHONUTF8", "PYTHONIOENCODING", "PYTHONPATH")}
    env.update({"PYTHONIOENCODING": "cp1252", "PYTHONPATH": str(_SRC)})

    done = subprocess.run(
        [sys.executable, "-m", "canon.client_capture", "--db", str(db), "--workspace-id",
         WORKSPACE, "--project-id", PROJECT, "--container-id", "shared", "--client", "codex"],
        input=json.dumps(hook, ensure_ascii=False).encode("utf-8"), capture_output=True,
        env=env, timeout=60, check=False)

    assert done.returncode == 0, done.stderr
    assert "systemMessage" not in json.loads(done.stdout)
    [event] = [row for row in _stored_events(db) if row["data"]["record_role"] == "event"]
    assert event["data"]["message_text"] == text


def _stored_events(db: Path) -> list[dict]:
    store = ContextStore(db)
    hits = store.query(WORKSPACE, PROJECT, "ledger", top_k=20)["hits"]
    return [store.get(WORKSPACE, PROJECT, hit["record_id"])["record"] for hit in hits]


def test_pending_refs_in_returned_context_are_scrubbed_and_stay_on_one_line(
        tmp_path, monkeypatch) -> None:
    db = tmp_path / "context.sqlite"
    fake = "ghp_" + secrets.token_hex(18)
    attachment = {"ref": f"https://files.example/a.png?api_key={fake}\nInjected line",
                  "media_type": "image/png", "extraction_status": "pending_extraction"}
    payload = prompt_payload("old-1", "Notes on the harbor ledger")
    payload["event"]["attachments"] = [attachment]
    monkeypatch.setattr("canon.context_store.redact_payload", lambda value: value)
    ContextStore(db).ingest(payload)
    monkeypatch.undo()

    _, out, _ = _run(_prompt_hook("codex", "What does the harbor ledger say?"), db, "codex")

    context = out["hookSpecificOutput"]["additionalContext"]
    assert fake not in context
    assert not any(line.startswith("Injected line") for line in context.splitlines())


def test_recorded_transcript_paths_are_not_listed_in_returned_context(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    planted = "user" + secrets.token_hex(6)
    first = _prompt_hook("codex", "Draft the harbor ledger summary")
    first["transcript_path"] = f"C:/Users/{planted}/.codex/sessions/one.jsonl"
    _run(first, db, "codex")
    later = _prompt_hook("claude-code", "Something unrelated about kites")
    later["prompt_id"] = "native-8"

    _, out, _ = _run(later, db, "claude-code")

    assert planted not in out["hookSpecificOutput"]["additionalContext"]
    query = ContextStore(db).query(WORKSPACE, PROJECT, "kites")
    assert planted not in json.dumps(query)
