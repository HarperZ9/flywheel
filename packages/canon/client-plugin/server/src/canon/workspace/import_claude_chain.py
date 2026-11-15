"""import_claude_chain.py -- the parts of a Claude Code session file that are
not one message at a time: which branch is live, and the task list.

Claude Code links entries by `uuid` and `parentUuid`. When a person rewinds to
an earlier message and prompts again, the new prompt hangs off an earlier entry
and the old branch stays in the file (public parsers call these within-session
forks). The live conversation is the chain from the last main-thread entry back
to the root, following `logicalParentUuid` across a compaction boundary. An
entry off that chain is abandoned only when its branch starts with a typed
prompt; a branch that starts with a tool result is kept, so a fork the tool
machinery makes is never mistaken for a rewind.

Claude Code 2.1.16 added a task system (TaskCreate, TaskUpdate) beside
TodoWrite. A task is created by subject, gets its number from the tool result
("Task #N created successfully: ..."), and changes status by number, so the
list is rebuilt here and handed to the collector as one plan.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_CREATED_RE = re.compile(r"Task #(\d+) created successfully")
_MAIN = ("user", "assistant")


@dataclass(frozen=True, slots=True)
class Chain:
    uuids: frozenset
    abandoned: frozenset


def _parent(obj: dict) -> str | None:
    return obj.get("parentUuid") or obj.get("logicalParentUuid")


def _typed_prompt(obj: dict) -> bool:
    if obj.get("type") != "user" or obj.get("isMeta") is True:
        return False
    content = (obj.get("message") or {}).get("content")
    if isinstance(content, str):
        return bool(content.strip())
    return isinstance(content, list) and any(
        isinstance(b, dict) and b.get("type") == "text" for b in content)


def _live(by_uuid: dict, leaf: str | None) -> set:
    live: set = set()
    while leaf and leaf in by_uuid and leaf not in live:
        live.add(leaf)
        leaf = _parent(by_uuid[leaf][1])
    return live


def _branch_head(uid: str, by_uuid: dict, live: set) -> str:
    """The first entry of the branch `uid` sits on: the one whose parent is
    live, missing, or absent from the file."""
    head, seen = uid, set()
    while True:
        parent = _parent(by_uuid[head][1])
        if parent is None or parent not in by_uuid or parent in live or parent in seen:
            return head
        seen.add(head)
        head = parent


def session_chain(lines) -> Chain:
    """The file's entry uuids and the line numbers of abandoned entries."""
    by_uuid, leaf, linked = {}, None, False
    for line, obj, _raw in lines:
        uid = obj.get("uuid")
        if isinstance(uid, str):
            by_uuid[uid] = (line, obj)
            linked = linked or "parentUuid" in obj
            if obj.get("type") in _MAIN and obj.get("isSidechain") is not True:
                leaf = uid
    live = _live(by_uuid, leaf) if linked else set()
    abandoned = set()
    if live:
        for uid, (line, obj) in by_uuid.items():
            if uid in live or obj.get("type") not in _MAIN or obj.get("isSidechain") is True:
                continue
            if _typed_prompt(by_uuid[_branch_head(uid, by_uuid, live)][1]):
                abandoned.add(line)
    return Chain(frozenset(by_uuid), frozenset(abandoned))


def result_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content
                         if isinstance(b, dict) and isinstance(b.get("text"), str))
    return ""


@dataclass
class Tasks:
    """The task list TaskCreate and TaskUpdate build, in creation order."""

    items: dict = field(default_factory=dict)
    pending: dict = field(default_factory=dict)
    line: int | None = None

    def create(self, tool_id: object, subject: object, line: int) -> None:
        number = str(len(self.items) + 1)
        self.items[number] = [str(subject or ""), "pending"]
        if isinstance(tool_id, str):
            self.pending[tool_id] = number
        self.line = line

    def bind(self, tool_id: object, content: object) -> None:
        """Re-key a created task by the number its tool result names."""
        number = self.pending.pop(tool_id, None) if isinstance(tool_id, str) else None
        found = _CREATED_RE.search(result_text(content))
        if number is None or found is None or found.group(1) == number:
            return
        if found.group(1) not in self.items:
            self.items = {(found.group(1) if k == number else k): v
                          for k, v in self.items.items()}

    def update(self, payload: dict, line: int) -> None:
        item = self.items.get(str(payload.get("taskId")))
        if item is None:
            return
        if isinstance(payload.get("subject"), str) and payload["subject"].strip():
            item[0] = payload["subject"]
        if isinstance(payload.get("status"), str):
            item[1] = payload["status"]
        self.line = line

    def steps(self) -> list[tuple[str, str]]:
        return [(subject, status) for subject, status in self.items.values()]
