"""import_codex.py -- propose records from a Codex CLI rollout file.

Codex writes a session as JSON lines under `sessions/YYYY/MM/DD/rollout-*.jsonl`.
Since Codex 0.32 each line is a tagged envelope, `{"timestamp", "type",
"payload"}`, and this importer reads that form only (field names confirmed
against the openai/codex source on 2026-09-23). A rollout from an older Codex,
where lines are bare items, is refused as an unsupported format.

Read:

  session_meta     payload.id (the thread; a sub-agent's rollout shares the
                   root's session_id but has its own id), cwd,
                   git.repository_url, git.branch
  turn_context     cwd, so a relative apply_patch path resolves where Codex
                   resolved it
  response_item    message (role user or assistant, content input_text or
                   output_text), function_call update_plan (the plan), and the
                   file names in an apply_patch call (the areas being worked on)
  event_msg        thread_rolled_back {num_turns}: everything gathered in the
                   last num_turns user turns is discarded

User-role text Codex writes itself (environment and instructions, a user shell
command and its output, a skill, a sub-agent notice, an aborted-turn notice,
internal context) is dropped by its marker, from the list Codex keeps in
core/src/context/contextual_user_message.rs. Every other line type Codex is
known to write is a declared drop.
"""
from __future__ import annotations

import json
import os
import re

from canon.workspace.identity import ProjectIdentity
from canon.workspace.import_common import (
    COMMON_DROPS,
    Collector,
    Extraction,
    ImportRefused,
    Ledger,
    Source,
    accept_session_id,
)

IMPORTER = "codex"
STATE_TYPES = frozenset({
    "turn_context", "compacted", "token_usage_record", "world_state",
    "retained_context", "security_risk_score", "realtime_item",
    "inter_agent_communication", "inter_agent_communication_metadata",
})
STATE_ITEMS = frozenset({"configuration_update"})
OTHER_ITEMS = frozenset({
    "web_search_call", "image_generation_call", "compaction", "compaction_summary",
    "context_compaction", "ghost_snapshot", "tool_search_call", "tool_search_output",
    "agent_message", "other",
})
SHELL_PREFIX = "<user_shell_command>"
INJECTED_PREFIXES = (
    "<environment_context>", "<user_instructions>", "# AGENTS.md instructions",
    "<turn_aborted>", "<subagent_notification>", "<skill>", "<codex_internal_context",
    "<goal_context>", "<agent_message_board_notification>")
PATCH_FILE_RE = re.compile(r"(?m)^\*\*\* (?:Add|Update|Delete) File: (.+?)\s*$")
DECLARED_DROPS = {
    **COMMON_DROPS,
    "session-state": "a line or response item of session state: "
                     + ", ".join(sorted(STATE_TYPES | STATE_ITEMS)),
    "event": "an event_msg line other than a rollback: user and agent messages the "
             "response items also carry, and progress, token and goal events",
    "reasoning": "a reasoning item",
    "injected-context": "a user-role message Codex wrote itself: environment, "
                        "instructions, a skill, a sub-agent or aborted-turn notice",
    "system-message": "a developer or system role message",
    "other-response-item": "a response item of type " + ", ".join(sorted(OTHER_ITEMS)),
    "rolled-back": "a candidate, plan or edit from a turn the session rolled back",
}


class _Walk:
    def __init__(self, col: Collector, ex: Extraction) -> None:
        self.col, self.ex, self.cwd, self.session_read = col, ex, None, False


def _user_part(text: str, line: int, walk: _Walk) -> None:
    stripped = text.lstrip()
    if stripped.startswith(SHELL_PREFIX):
        walk.col.ledger.drop("tool-output")
    elif stripped.startswith(INJECTED_PREFIXES):
        walk.col.ledger.drop("injected-context")
    else:
        walk.col.start_turn()
        walk.col.add_text(text, line, role="user")


def _message(payload: dict, line: int, walk: _Walk) -> None:
    col, role = walk.col, payload.get("role")
    if role in ("developer", "system"):
        col.ledger.drop("system-message")
        return
    if role not in ("user", "assistant"):
        col.ledger.unknown(f"message role {role!r}", line)
        return
    content = payload.get("content")
    for part in content if isinstance(content, list) else [None]:
        kind = part.get("type") if isinstance(part, dict) else None
        if kind in ("input_text", "output_text") and isinstance(part.get("text"), str):
            if role == "user":
                _user_part(part["text"], line, walk)
            else:
                col.add_text(part["text"], line, role=role)
        elif kind in ("input_image", "input_audio"):
            col.ledger.drop("image")
        else:
            col.ledger.unknown(f"message content {kind!r}", line)


def _plan(arguments: object, line: int, col: Collector) -> None:
    try:
        parsed = json.loads(arguments) if isinstance(arguments, str) else None
    except json.JSONDecodeError:
        parsed = None
    steps = parsed.get("plan") if isinstance(parsed, dict) else None
    if not isinstance(steps, list):
        col.ledger.unknown("update_plan arguments shape", line)
        return
    col.add_plan(line, [(s.get("step", ""), s.get("status"))
                        for s in steps if isinstance(s, dict)])


def _patch(text: object, walk: _Walk) -> None:
    body = text if isinstance(text, str) else ""
    if body.lstrip().startswith("{"):
        try:
            body = str(json.loads(body).get("input", ""))
        except (json.JSONDecodeError, AttributeError):
            pass
    for path in PATCH_FILE_RE.findall(body):
        if not os.path.isabs(path) and walk.cwd:
            path = os.path.join(walk.cwd, path)
        walk.col.add_edit(path)


def _response_item(payload: dict, line: int, walk: _Walk) -> None:
    kind, name, ledger = payload.get("type"), payload.get("name"), walk.col.ledger
    if kind == "message":
        _message(payload, line, walk)
    elif kind == "function_call" and name == "update_plan":
        _plan(payload.get("arguments"), line, walk.col)
    elif kind in ("function_call", "custom_tool_call") and name == "apply_patch":
        _patch(payload.get("arguments", payload.get("input")), walk)
    elif kind in ("function_call", "custom_tool_call", "local_shell_call"):
        ledger.drop("tool-call")
    elif kind in ("function_call_output", "custom_tool_call_output"):
        ledger.drop("tool-output")
    elif kind == "reasoning":
        ledger.drop("reasoning")
    elif kind in STATE_ITEMS:
        ledger.drop("session-state")
    elif kind in OTHER_ITEMS:
        ledger.drop("other-response-item")
    else:
        ledger.unknown(f"response item {kind!r}", line)


def _session_meta(payload: dict, walk: _Walk) -> None:
    ex, col = walk.ex, walk.col
    if not walk.session_read:
        thread = payload.get("id", payload.get("session_id"))
        if thread is not None:
            walk.session_read = True
            ex.session_id = accept_session_id(thread, col.ledger)
    if isinstance(payload.get("cwd"), str):
        ex.cwds.append(payload["cwd"])
        walk.cwd = payload["cwd"]
    git = payload.get("git") if isinstance(payload.get("git"), dict) else {}
    if isinstance(git.get("repository_url"), str):
        ex.repository_url = git["repository_url"]
    if isinstance(git.get("branch"), str) and git["branch"]:
        col.branch = git["branch"]


def _event(payload: dict, walk: _Walk) -> None:
    if payload.get("type") == "thread_rolled_back" and isinstance(payload.get("num_turns"), int):
        walk.col.ledger.drop("rolled-back", walk.col.roll_back(payload["num_turns"]))
    else:
        walk.col.ledger.drop("event")


def _line(obj: dict, line: int, walk: _Walk) -> None:
    kind, payload = obj.get("type"), obj.get("payload")
    if not isinstance(kind, str) or not isinstance(payload, dict):
        raise ImportRefused(
            "unsupported_format", f"line {line} is not a tagged rollout line; rollouts "
            "from Codex before 0.32 are not supported")
    if kind == "session_meta":
        _session_meta(payload, walk)
    elif kind == "response_item":
        _response_item(payload, line, walk)
    elif kind == "event_msg":
        _event(payload, walk)
    elif kind in STATE_TYPES:
        if kind == "turn_context" and isinstance(payload.get("cwd"), str):
            walk.cwd = payload["cwd"]
        walk.col.ledger.drop("session-state")
    else:
        walk.col.ledger.unknown(f"line type {kind!r}", line)


def extract(source: Source, identity: ProjectIdentity, *,
            user_drops: frozenset[str] = frozenset()) -> Extraction:
    """Walk a Codex rollout and collect candidates and the loss ledger."""
    ledger = Ledger(DECLARED_DROPS, user_drops)
    if source.truncated_tail:
        ledger.drop("truncated-tail")
    ex = Extraction([], ledger)
    walk = _Walk(Collector(identity, ledger, hits=ex.hits), ex)
    for line, obj, _raw in source.lines:
        _line(obj, line, walk)
    ex.candidates = walk.col.finish()
    return ex
