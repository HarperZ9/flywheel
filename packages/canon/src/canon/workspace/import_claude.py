"""import_claude.py -- propose records from a Claude Code session transcript.

Claude Code writes one JSON object per line to a session file. Anthropic's
documentation says the entry format is internal and changes between versions,
so this importer reads only the fields public parsers agree on, names what it
drops, and refuses an entry type it has not seen rather than guess.

Read (field names confirmed against public parsers, 2026-09-23, among them
daaain/claude-code-log):

  type: user | assistant      message.role, message.content (string or blocks)
  content blocks              text, tool_use {name, input}, tool_result,
                              thinking, redacted_thinking, image
  type: summary               summary and leafUuid; used only when leafUuid
                              names an entry of this file, since a summary line
                              routinely describes another session
  type: ai-title              aiTitle, the session's own title, when no own
                              summary exists and its sessionId is this file's
  uuid, parentUuid            the live branch (import_claude_chain)
  sessionId, cwd, gitBranch   session id, the project check, the focus branch
  TodoWrite tool_use          input.todos[] {content, status}: the plan
  TaskCreate, TaskUpdate      {subject} and {taskId, status}: the task list
  Edit/Write/MultiEdit        input.file_path: the areas being worked on

User text that Claude Code wrote rather than the person typed is dropped by
name: slash commands and local command output, bash-mode input and output, a
compaction summary, and system-reminder or IDE blocks inside a message. Every
other entry type Claude Code is known to write is a declared drop. The format
is not a stable interface; a new Claude Code release can add an entry type, and
this importer then refuses until the drop is declared.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from canon.workspace.identity import ProjectIdentity
from canon.workspace.import_claude_chain import Chain, Tasks, session_chain
from canon.workspace.import_common import (
    COMMON_DROPS,
    Collector,
    Extraction,
    Ledger,
    Source,
    accept_session_id,
)

IMPORTER = "claude-code"
META_TYPES = frozenset({
    "system", "file-history-snapshot", "queue-operation", "attachment", "progress",
    "ai-title", "last-prompt", "permission-mode", "custom-title", "agent-name",
    "agent-color", "frame-link", "agent-setting", "pr-link",
})
EDIT_TOOLS = {"Edit": "file_path", "Write": "file_path", "MultiEdit": "file_path",
              "NotebookEdit": "notebook_path"}
LOCAL_COMMAND_PREFIXES = (
    "<command-name>", "<command-message>", "<command-args>", "<local-command-stdout>",
    "<local-command-stderr>", "<local-command-caveat>", "<bash-input>",
    "<bash-stdout>", "<bash-stderr>")
COMPACT_PREFIX = "This session is being continued from a previous conversation"
INJECTED_BLOCK_RE = re.compile(
    r"<(system-reminder|ide_selection|ide_opened_file)>.*?</\1>", re.DOTALL)
DECLARED_DROPS = {
    **COMMON_DROPS,
    "meta-entry": "an entry that carries no conversation: " + ", ".join(sorted(META_TYPES)),
    "sidechain": "a sidechain (subagent) entry",
    "meta-message": "a message Claude Code marked isMeta (injected, not typed)",
    "thinking": "an assistant thinking block",
    "message-metadata": "an assistant entry's model, request id and token usage",
    "local-command": "a slash command, local command output, or bash-mode input or "
                     "output in the user role; the person did not type it as a message",
    "compact-summary": "a compaction summary Claude Code wrote in the user role",
    "injected-block": "a system-reminder or IDE block Claude Code put inside user text",
    "abandoned-branch": "an entry on a branch the person rewound away from",
    "foreign-summary": "a summary line whose leafUuid names no entry in this file",
    "unused-summary": "an own summary line that is empty or replaced by a later one",
}


@dataclass
class _Walk:
    col: Collector
    ex: Extraction
    chain: Chain
    tasks: Tasks = field(default_factory=Tasks)
    summaries: list = field(default_factory=list)
    titles: list = field(default_factory=list)
    session_read: bool = False


def _content_blocks(content: object, line: int, ledger: Ledger) -> list[dict]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if not isinstance(content, list):
        ledger.unknown("message content shape", line)
        return []
    return [block if isinstance(block, dict) else {"type": None} for block in content]


def _tool_use(block: dict, line: int, walk: _Walk) -> None:
    name, payload = block.get("name"), block.get("input")
    payload = payload if isinstance(payload, dict) else {}
    col = walk.col
    if name == "TodoWrite":
        todos = payload.get("todos")
        if not isinstance(todos, list):
            col.ledger.unknown("TodoWrite input shape", line)
            return
        col.add_plan(line, [(t.get("content", ""), t.get("status"))
                            for t in todos if isinstance(t, dict)])
    elif name == "TaskCreate":
        walk.tasks.create(block.get("id"), payload.get("subject"), line)
    elif name == "TaskUpdate":
        walk.tasks.update(payload, line)
    elif name in EDIT_TOOLS and isinstance(payload.get(EDIT_TOOLS[name]), str):
        col.add_edit(payload[EDIT_TOOLS[name]])
    else:
        col.ledger.drop("tool-call")


def _user_text(text: str, line: int, walk: _Walk) -> None:
    ledger = walk.col.ledger
    stripped = text.lstrip()
    if stripped.startswith(LOCAL_COMMAND_PREFIXES):
        ledger.drop("local-command")
        return
    if stripped.startswith(COMPACT_PREFIX):
        ledger.drop("compact-summary")
        return
    text, injected = INJECTED_BLOCK_RE.subn("", text)
    ledger.drop("injected-block", injected)
    if text.strip() or not injected:
        walk.col.add_text(text, line, role="user")


def _block(block: dict, line: int, role: str, walk: _Walk) -> None:
    kind, ledger = block.get("type"), walk.col.ledger
    if kind == "text" and isinstance(block.get("text"), str):
        if role == "user":
            _user_text(block["text"], line, walk)
        else:
            walk.col.add_text(block["text"], line, role=role)
    elif kind in ("thinking", "redacted_thinking"):
        ledger.drop("thinking")
    elif kind == "image":
        ledger.drop("image")
    elif kind == "tool_use":
        _tool_use(block, line, walk)
    elif kind == "tool_result":
        walk.tasks.bind(block.get("tool_use_id"), block.get("content"))
        ledger.drop("tool-output")
    else:
        ledger.unknown(f"content block {kind!r}", line)


def _side_entry(obj: dict, line: int, walk: _Walk) -> bool:
    """Handle an entry that carries no message; True when it was one."""
    kind = obj.get("type")
    if kind == "summary":
        walk.summaries.append((line, obj.get("summary"), obj.get("leafUuid")))
    elif kind == "ai-title" and isinstance(obj.get("aiTitle"), str):
        walk.titles.append((line, obj["aiTitle"], obj.get("sessionId")))
    elif kind in META_TYPES:
        walk.col.ledger.drop("meta-entry")
    elif kind not in ("user", "assistant"):
        walk.col.ledger.unknown(f"entry type {kind!r}", line)
    else:
        return False
    return True


def _entry(obj: dict, line: int, walk: _Walk) -> None:
    if _side_entry(obj, line, walk):
        return
    ledger, kind = walk.col.ledger, obj.get("type")
    if obj.get("isSidechain") is True:
        ledger.drop("sidechain")
    elif line in walk.chain.abandoned:
        ledger.drop("abandoned-branch")
    elif obj.get("isMeta") is True:
        ledger.drop("meta-message")
    elif kind == "user" and obj.get("isCompactSummary") is True:
        ledger.drop("compact-summary")
    else:
        _session_fields(obj, walk)
        if kind == "assistant":
            ledger.drop("message-metadata")
        message = obj.get("message") if isinstance(obj.get("message"), dict) else {}
        for block in _content_blocks(message.get("content"), line, ledger):
            _block(block, line, kind, walk)


def _session_fields(obj: dict, walk: _Walk) -> None:
    ex, col = walk.ex, walk.col
    if not walk.session_read and "sessionId" in obj:
        walk.session_read = True
        ex.session_id = accept_session_id(obj["sessionId"], col.ledger)
    if isinstance(obj.get("cwd"), str) and obj["cwd"] not in ex.cwds:
        ex.cwds.append(obj["cwd"])
    if isinstance(obj.get("gitBranch"), str) and obj["gitBranch"]:
        col.branch = obj["gitBranch"]


def _choose_title(walk: _Walk) -> None:
    """The focus goal: the last own summary, else the last own ai-title."""
    ledger = walk.col.ledger
    own = []
    for line, text, leaf in walk.summaries:
        if leaf not in walk.chain.uuids:
            ledger.drop("foreign-summary")
        elif isinstance(text, str) and text.strip():
            own.append((line, text))
        else:
            ledger.drop("unused-summary")
    titles = [(line, title) for line, title, sid in walk.titles
              if sid is not None and sid == walk.ex.session_id and title.strip()]
    ledger.drop("unused-summary", max(0, len(own) - 1))
    ledger.drop("meta-entry", len(walk.titles) - (1 if titles and not own else 0))
    if own:
        walk.col.set_summary(*own[-1])
    elif titles:
        walk.col.set_summary(*titles[-1])


def extract(source: Source, identity: ProjectIdentity, *,
            user_drops: frozenset[str] = frozenset()) -> Extraction:
    """Walk a Claude Code session and collect candidates and the loss ledger."""
    ledger = Ledger(DECLARED_DROPS, user_drops)
    if source.truncated_tail:
        ledger.drop("truncated-tail")
    ex = Extraction([], ledger)
    walk = _Walk(Collector(identity, ledger, hits=ex.hits), ex, session_chain(source.lines))
    for line, obj, _raw in source.lines:
        _entry(obj, line, walk)
    _choose_title(walk)
    if walk.tasks.items:
        walk.col.add_plan(walk.tasks.line, walk.tasks.steps())
    ex.candidates = walk.col.finish()
    return ex
