"""What the capture hook stores, what it refuses, and what it hands back.

An answer is stored only beside the prompt it answers, so a purge of that
prompt always takes it; an answer whose prompt was purged or never captured is
not stored, and the hook says which. `--transcript-locator none` keeps no path
at all. Secret-shaped values are redacted before a prompt or an answer is
stored, and before any excerpt is returned. Stored answers are left out of the
context returned to later prompts unless the owner turns replay on. A prompt
sent again after a purge is stored again, and the hook says so.
"""
from __future__ import annotations

import secrets

from canon.context_purge import select
from canon.context_store import ContextStore

from ._context_fixtures import prompt_payload
from .test_client_capture_stop import (
    RESPONSES, _answers, _events, _prompt_hook, _prompt_record_id, _run, _stop_hook,
)


def _purge_prompt(db) -> str:
    store, prompt = ContextStore(db), _prompt_record_id(db)
    plan = store.purge_plan("cdev", "canon", select(event_id=prompt, keep_responses=True))
    store.purge("cdev", "canon", select(event_id=prompt, keep_responses=True),
                confirm_plan_sha256=plan["plan_sha256"])
    return prompt


def _fake_key() -> str:
    return "sk-FAKE" + secrets.token_hex(20)


def test_an_answer_without_a_captured_prompt_is_not_stored_and_says_why(tmp_path) -> None:
    db = tmp_path / "context.sqlite"

    code, out, err = _run(_stop_hook("claude-code"), db, "claude-code", *RESPONSES)

    assert (code, err) == (0, "")
    assert "no captured prompt" in out["systemMessage"]
    assert "not stored" in out["systemMessage"]
    assert _answers(db) == []


def test_a_stop_for_a_purged_prompt_stores_nothing_and_says_it_was_purged(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    _run(_prompt_hook("claude-code"), db, "claude-code", *RESPONSES)
    _purge_prompt(db)

    code, out, _ = _run(_stop_hook("claude-code"), db, "claude-code", *RESPONSES)

    assert code == 0
    assert "purged" in out["systemMessage"] and "not stored" in out["systemMessage"]
    assert _answers(db) == []
    assert b"harbor ledger" not in db.read_bytes()


def test_a_stop_before_its_prompt_is_stored_once_after_the_prompt_arrives(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    assert "systemMessage" in _run(_stop_hook("claude-code"), db, "claude-code", *RESPONSES)[1]
    _run(_prompt_hook("claude-code"), db, "claude-code", *RESPONSES)

    _run(_stop_hook("claude-code"), db, "claude-code", *RESPONSES)
    _run(_stop_hook("claude-code"), db, "claude-code", *RESPONSES)

    assert [a["data"]["event_id"] for a in _answers(db)] == ["native-7-response-1"]


def test_transcript_locator_none_records_no_path_at_all(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    args = (*RESPONSES, "--transcript-locator", "none")

    _run(_prompt_hook("claude-code"), db, "claude-code", *args)
    _run(_stop_hook("claude-code"), db, "claude-code", *args)

    raw = db.read_bytes()
    assert b"/work/project" not in raw and b"/transcripts/" not in raw
    assert b"retained as locators" not in raw
    [prompt] = [e for e in _events(db) if "message_role" not in e["data"]]
    assert prompt["data"]["cwd"] is None
    assert prompt["data"]["coverage"]["cwd"] == "not_recorded"


def test_a_planted_credential_is_redacted_before_it_is_stored(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    in_prompt, in_answer = _fake_key(), _fake_key()

    _run(_prompt_hook("claude-code", f"Use OPENAI_API_KEY={in_prompt} here"), db,
         "claude-code", *RESPONSES)
    _run(_stop_hook("claude-code", f"I set the key to {in_answer} for you."), db,
         "claude-code", *RESPONSES)

    raw = db.read_bytes()
    assert in_prompt.encode() not in raw and in_answer.encode() not in raw
    for event in _events(db):
        assert "[REDACTED:" in event["data"]["message_text"]
        assert sum(event["data"]["coverage"]["redactions"].values()) >= 1


def test_an_excerpt_is_scrubbed_before_it_is_returned(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    fake = _fake_key()
    ContextStore(db).ingest(prompt_payload("old-1", f"The tide token is {fake} for the ledger"))

    _, out, _ = _run(_prompt_hook("codex", "Which tide token does the ledger use?"), db, "codex")

    context = out["hookSpecificOutput"]["additionalContext"]
    assert fake not in context and "[REDACTED:" in context


def test_answers_are_left_out_of_returned_context_unless_replay_is_on(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    _run(_prompt_hook("claude-code"), db, "claude-code", *RESPONSES)
    _run(_stop_hook("claude-code"), db, "claude-code", *RESPONSES)
    later = _prompt_hook("claude-code", "Tell me about the harbor ledger")
    later["prompt_id"] = "native-8"

    _, out, _ = _run(later, db, "claude-code")
    context = out["hookSpecificOutput"]["additionalContext"]
    assert "harbor ledger." not in context
    assert "answers left out: 1" in context

    later["prompt_id"] = "native-9"
    _, out, _ = _run(later, db, "claude-code", "--replay-answers", "on")
    assert "They live in the harbor ledger." in out["hookSpecificOutput"]["additionalContext"]


def test_a_prompt_sent_again_after_a_purge_is_stored_again_and_says_so(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    _run(_prompt_hook("claude-code"), db, "claude-code")
    _purge_prompt(db)

    code, out, _ = _run(_prompt_hook("claude-code"), db, "claude-code")

    assert code == 0
    assert "purged earlier" in out["systemMessage"]
    assert len(_events(db)) == 1
