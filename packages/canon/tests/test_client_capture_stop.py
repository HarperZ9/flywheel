"""The capture hook's response scope: Stop deliveries and the paired answer.

Prompt capture stays the default. With `--capture prompts+responses` a Stop
delivery stores the client's last assistant message as an assistant event
whose id is `<native_id>-response-<segment>`, linked to the prompt event with
the same `prompt_id` (Claude Code) or `turn_id` (Codex). Tool calls and
reasoning are not captured, and the event says so. A Stop the hook does not
store always says why, so a hook mounted on Stop never fails silently.
"""
from __future__ import annotations

import io
import json
import sqlite3
from pathlib import Path

from canon import client_capture
from canon.context_purge import select
from canon.context_store import ContextStore

RESPONSES = ("--capture", "prompts+responses")
OFF_MESSAGE = "Canon: response capture is off; this Stop event was not stored"


def _prompt_hook(client: str, prompt: str = "Where do the tide tables live?") -> dict:
    hook = {"session_id": f"{client}-session", "cwd": "/work/project",
            "transcript_path": f"/transcripts/{client}.jsonl",
            "hook_event_name": "UserPromptSubmit", "permission_mode": "default",
            "prompt": prompt}
    hook["turn_id" if client == "codex" else "prompt_id"] = "native-7"
    return hook


def _stop_hook(client: str, message: object = "They live in the harbor ledger.") -> dict:
    hook = {"session_id": f"{client}-session", "cwd": "/work/project",
            "transcript_path": f"/transcripts/{client}.jsonl",
            "hook_event_name": "Stop", "stop_hook_active": False,
            "last_assistant_message": message}
    hook["turn_id" if client == "codex" else "prompt_id"] = "native-7"
    return hook


def _run(hook: dict, db: Path, client: str, *args: str, env=None) -> tuple[int, dict, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    code = client_capture.run(
        ["--db", str(db), "--workspace-id", "cdev", "--project-id", "canon",
         "--container-id", "shared", "--client", client, *args],
        stdin=io.StringIO(json.dumps(hook)), stdout=stdout, stderr=stderr, env=env or {})
    return code, json.loads(stdout.getvalue()), stderr.getvalue()


def _events(db: Path) -> list[dict]:
    """Every stored event record, read through the store's own verified get."""
    if not db.exists():
        return []
    store = ContextStore(db)
    con = sqlite3.connect(str(db))
    try:
        ids = [row[0] for row in con.execute("SELECT id FROM records ORDER BY key")]
    finally:
        con.close()
    records = [store.get("cdev", "canon", record_id)["record"] for record_id in ids]
    return [rec for rec in records if rec["data"]["record_role"] == "event"]


def _answers(db: Path) -> list[dict]:
    return [rec for rec in _events(db) if rec["data"].get("message_role") == "assistant"]


def _prompt_record_id(db: Path) -> str:
    return next(rec["id"] for rec in _events(db) if "message_role" not in rec["data"])


def test_a_claude_code_stop_stores_a_linked_answer_without_a_collision(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    assert _run(_prompt_hook("claude-code"), db, "claude-code", *RESPONSES)[0] == 0

    code, out, err = _run(_stop_hook("claude-code"), db, "claude-code", *RESPONSES)

    assert (code, err) == (0, "")
    assert "decision" not in out and "hookSpecificOutput" not in out
    [answer] = _answers(db)
    data, prompt_id = answer["data"], _prompt_record_id(db)
    assert data["event_id"] == "native-7-response-1"
    assert data["message_text"] == "They live in the harbor ledger."
    assert data["responds_to"] == prompt_id
    refs = [source["ref"] for source in data["sources"]
            if source["source_kind"] == "canon_event_ref"]
    assert refs == [prompt_id]
    assert data["coverage"]["tool_calls"] == "not_captured"
    assert data["coverage"]["reasoning"] == "not_captured"
    assert data["coverage"]["pairing"] == "prompt_event_found"


def test_a_codex_stop_links_by_turn_id(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    _run(_prompt_hook("codex"), db, "codex", *RESPONSES)

    code, _, err = _run(_stop_hook("codex"), db, "codex", *RESPONSES)

    assert (code, err) == (0, "")
    [answer] = _answers(db)
    assert answer["data"]["responds_to"] == _prompt_record_id(db)
    assert answer["provenance"]["harness"] == "codex"


def test_prompts_only_mode_stores_nothing_on_stop_and_says_so(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    _run(_prompt_hook("claude-code"), db, "claude-code")

    code, out, err = _run(_stop_hook("claude-code"), db, "claude-code")

    assert (code, err) == (0, "")
    assert out == {"systemMessage": OFF_MESSAGE}
    assert _answers(db) == []


def test_a_null_last_assistant_message_stores_nothing_and_says_so(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    _run(_prompt_hook("claude-code"), db, "claude-code", *RESPONSES)

    code, out, _ = _run(_stop_hook("claude-code", None), db, "claude-code", *RESPONSES)

    assert code == 0
    assert "no last assistant message" in out["systemMessage"]
    assert "not stored" in out["systemMessage"]
    assert _answers(db) == []


def test_a_stop_without_a_prompt_id_stores_nothing_and_says_why(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    hook = _stop_hook("claude-code")
    del hook["prompt_id"]

    code, out, _ = _run(hook, db, "claude-code", *RESPONSES)

    assert code == 0
    assert "no prompt id" in out["systemMessage"]
    assert _answers(db) == []


def test_user_prompt_submit_is_unchanged_by_default(tmp_path) -> None:
    db = tmp_path / "context.sqlite"

    code, out, err = _run(_prompt_hook("claude-code"), db, "claude-code")

    assert (code, err) == (0, "")
    assert out["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    [prompt] = _events(db)
    assert "message_role" not in prompt["data"] and "responds_to" not in prompt["data"]
    assert prompt["data"]["event_id"] == "native-7"
    locators = [s for s in prompt["data"]["sources"] if s["source_kind"] == "transcript_locator"]
    assert [s["locator"] for s in locators] == ["/transcripts/claude-code.jsonl"]


def test_a_redelivered_stop_is_idempotent_and_a_new_answer_takes_the_next_segment(
        tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    _run(_prompt_hook("claude-code"), db, "claude-code", *RESPONSES)
    _run(_stop_hook("claude-code"), db, "claude-code", *RESPONSES)

    _run(_stop_hook("claude-code"), db, "claude-code", *RESPONSES)
    code, _, err = _run(_stop_hook("claude-code", "The tide tables moved to the harbor annex."),
                        db, "claude-code", *RESPONSES)

    assert (code, err) == (0, "")
    ids = sorted(answer["data"]["event_id"] for answer in _answers(db))
    assert ids == ["native-7-response-1", "native-7-response-2"]


def test_the_environment_turns_response_capture_on_and_a_bad_value_fails_visibly(
        tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    _run(_prompt_hook("codex"), db, "codex")

    code, out, _ = _run(_stop_hook("codex"), db, "codex",
                        env={"CANON_CONTEXT_CAPTURE": "prompts+responses"})
    assert code == 0 and "systemMessage" not in out
    assert len(_answers(db)) == 1

    code, out, _ = _run(_stop_hook("codex"), db, "codex",
                        env={"CANON_CONTEXT_CAPTURE": "everything"})
    assert code == 0 and "capture must be one of" in out["systemMessage"]


def test_transcript_locator_none_keeps_no_transcript_path(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    args = (*RESPONSES, "--transcript-locator", "none")

    _run(_prompt_hook("claude-code"), db, "claude-code", *args)
    _run(_stop_hook("claude-code"), db, "claude-code", *args)

    assert b"/transcripts/claude-code.jsonl" not in db.read_bytes()
    for record in _events(db):
        kinds = {source["source_kind"] for source in record["data"]["sources"]}
        assert "transcript_locator" not in kinds


def test_purging_the_prompt_takes_the_captured_answer_with_it(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    _run(_prompt_hook("claude-code"), db, "claude-code", *RESPONSES)
    _run(_stop_hook("claude-code"), db, "claude-code", *RESPONSES)
    store, prompt = ContextStore(db), _prompt_record_id(db)

    plan = store.purge_plan("cdev", "canon", select(event_id=prompt))
    report = store.purge("cdev", "canon", select(event_id=prompt),
                         confirm_plan_sha256=plan["plan_sha256"])

    assert plan["counts"]["responses"] == 1
    assert report["status"] == "purged"
    assert _events(db) == []


def test_the_stop_fragments_mount_the_hook_with_response_capture_on() -> None:
    root = Path(__file__).resolve().parents[1] / "examples" / "shared-context-hooks"
    for client in ("claude-code", "codex"):
        fragment = json.loads((root / f"{client}-stop.fragment.json").read_text(encoding="utf-8"))
        [entry] = fragment["hooks"]["Stop"]
        [hook] = entry["hooks"]
        assert hook["command"] == (f"python -m canon.client_capture --client {client} "
                                   "--capture prompts+responses")
