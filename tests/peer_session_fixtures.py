"""Synthetic transcript builders for the peer-session tests.

Every string that must never leak into observer output carries the CANARY
marker. Shapes mirror what the observers document; no real transcript is
copied here.
"""
from __future__ import annotations

import json
from pathlib import Path

CANARY = "CANARY-TEXT-MUST-NOT-LEAK"
ACCOUNT_CANARY = "acct-CANARY-0000-0000"
CLAUDE_SESSION = "5f0c1e2a-1111-4222-8333-444455556666"
CODEX_THREAD = "01a0aaaa-bbbb-7ccc-8ddd-eeeeffff0001"
CODEX_PARENT = "01a0aaaa-bbbb-7ccc-8ddd-eeeeffff0000"
CLAUDE_TITLE = f"{CANARY} title"
CODEX_REPO_URL = f"https://user:{CANARY}@example.invalid/x/y.git"


def jsonl(records: list[dict]) -> bytes:
    return b"".join(json.dumps(r, separators=(",", ":")).encode("utf-8") + b"\n" for r in records)


def claude_records(session_id: str = CLAUDE_SESSION, *, turns: int = 2,
                   model: str = "claude-test-model") -> list[dict]:
    base = {"sessionId": session_id, "cwd": "C:\\work\\repo", "version": "9.9.9",
            "gitBranch": "main", "entrypoint": "cli", "userType": "external"}
    out = [{"type": "bridge-session", "bridgeSessionId": "b-1", "lastSequenceNum": 0,
            "ownerAccountUuid": ACCOUNT_CANARY, "ownerOrganizationUuid": ACCOUNT_CANARY,
            "sessionId": session_id}]
    for i in range(turns):
        out.append({**base, "type": "user", "uuid": f"u-{i}", "parentUuid": None,
                    "isSidechain": False, "timestamp": f"2026-09-10T10:0{i}:00.000Z",
                    "message": {"role": "user", "content": f"{CANARY} prompt {i}"}})
        out.append({**base, "type": "assistant", "uuid": f"a-{i}", "parentUuid": f"u-{i}",
                    "isSidechain": False, "timestamp": f"2026-09-10T10:0{i}:30.000Z",
                    "message": {"role": "assistant", "model": model, "stop_reason": "tool_use",
                                "content": [{"type": "text", "text": f"{CANARY} reply {i}"},
                                            {"type": "tool_use", "name": "Bash",
                                             "input": {"command": CANARY}}]}})
    out.append({"type": "custom-title", "customTitle": CLAUDE_TITLE, "sessionId": session_id})
    out.append({"type": "last-prompt", "lastPrompt": f"{CANARY} last", "sessionId": session_id})
    return out


def codex_records(thread_id: str = CODEX_THREAD, *, subagent: bool = False,
                  model: str = "gpt-test-model", turns: int = 2) -> list[dict]:
    source = ({"subagent": {"thread_spawn": {"parent_thread_id": CODEX_PARENT, "depth": 1,
                                             "agent_nickname": "worker", "agent_role": "default",
                                             "agent_path": "agents/default"}}}
              if subagent else "vscode")
    meta = {"timestamp": "2026-09-10T09:00:00.000Z", "ordinal": 0, "type": "session_meta",
            "payload": {"id": thread_id, "session_id": thread_id, "cwd": "C:\\work\\repo",
                        "originator": "codex_desktop", "cli_version": "1.2.3", "source": source,
                        "thread_source": "user", "model_provider": "openai",
                        "base_instructions": {"text": f"{CANARY} instructions",
                                              "provenance": {"type": "builtin"}},
                        "git": {"commit_hash": "0" * 40, "branch": "main",
                                "repository_url": CODEX_REPO_URL}}}
    out = [meta]
    ordinal = 1
    for i in range(turns):
        turn = f"turn-{i}"
        ts = f"2026-09-10T09:0{i}:00.000Z"
        out.append({"timestamp": ts, "ordinal": ordinal, "type": "turn_context",
                    "payload": {"turn_id": turn, "cwd": "C:\\work\\repo", "model": model,
                                "effort": "high"}})
        out.append({"timestamp": ts, "ordinal": ordinal + 1, "type": "event_msg",
                    "payload": {"type": "user_message", "message": f"{CANARY} ask {i}",
                                "thread_id": thread_id}})
        out.append({"timestamp": ts, "ordinal": ordinal + 2, "type": "response_item",
                    "payload": {"type": "function_call", "name": "shell",
                                "arguments": json.dumps({"cmd": CANARY}), "call_id": f"c{i}"}})
        out.append({"timestamp": ts, "ordinal": ordinal + 3, "type": "event_msg",
                    "payload": {"type": "agent_message", "message": f"{CANARY} answer {i}",
                                "thread_id": thread_id}})
        out.append({"timestamp": ts, "ordinal": ordinal + 4, "type": "event_msg",
                    "payload": {"type": "token_count", "thread_id": thread_id,
                                "info": {"total_token_usage": {
                                    "input_tokens": 100 * (i + 1), "cached_input_tokens": 10,
                                    "output_tokens": 20, "reasoning_output_tokens": 5,
                                    "total_tokens": 100 * (i + 1) + 20}}}})
        ordinal += 5
    return out


def write_claude(root: Path, slug: str = "C--work-repo", session_id: str = CLAUDE_SESSION,
                 *, subagent: bool = False, records: list[dict] | None = None) -> Path:
    folder = root / ".claude" / "projects" / slug
    if subagent:
        folder = folder / session_id / "subagents"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{session_id}.jsonl"
    path.write_bytes(jsonl(records if records is not None else claude_records(session_id)))
    return path


def write_codex(root: Path, thread_id: str = CODEX_THREAD, *, day: str = "2026/09/10",
                records: list[dict] | None = None) -> Path:
    folder = root / ".codex" / "sessions" / day
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"rollout-2026-09-10T09-00-00-{thread_id}.jsonl"
    path.write_bytes(jsonl(records if records is not None else codex_records(thread_id)))
    return path


def assert_no_canary(obj: object) -> None:
    text = json.dumps(obj, ensure_ascii=True, sort_keys=True)
    assert CANARY not in text, "transcript text leaked into observer output"
    assert ACCOUNT_CANARY not in text, "account identifier leaked into observer output"
    assert "example.invalid" not in text, "a remote host name leaked into observer output"
