"""hooks.py -- lifecycle hooks for a coding session, in Claude Code's format.

Hooks live in FLYWHEEL_HOME/hooks.json (yours, trusted) and the project's
.flywheel/hooks.json (needs your yes, like project MCP servers):

    {"hooks": {"PreToolUse": [{"matcher": "write_file|edit_file",
                               "hooks": [{"type": "command", "command": "lint.sh"}]}]}}

Events: SessionStart, UserPromptSubmit, PreToolUse, PermissionRequest,
PostToolUse, PreCompact, PostCompact, SubagentStart, SubagentStop, Stop,
SessionEnd. Each hook command gets the event as JSON on stdin
(hook_event_name, session_id, cwd, and tool_name, tool_input, tool_response or
prompt where they apply). `matcher` is a regular expression over the tool name;
empty or "*" matches every tool. A UserPromptSubmit or PreToolUse hook blocks
by exiting 2 (stderr is the reason) or by printing {"decision": "block",
"reason": "..."}; a blocked tool call never reaches the tool, and the model is
told why. Every hook run, with its exit code and whether it blocked, goes on the
ledger. Hook commands run as you, outside the command sandbox, because you
wrote them; that is why a project's hooks need your yes.
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PermissionRequest",
          "PostToolUse", "PreCompact", "PostCompact", "SubagentStart", "SubagentStop",
          "Stop", "SessionEnd")
BLOCKING = frozenset({"UserPromptSubmit", "PreToolUse", "PermissionRequest"})
USER_FILE = "hooks.json"
PROJECT_FILE = Path(".flywheel") / "hooks.json"
TIMEOUT = 60


@dataclass
class HookEntry:
    event: str
    matcher: str
    command: str
    source: str


@dataclass
class Outcome:
    blocked: bool = False
    reason: str = ""
    allowed: bool = False          # a PermissionRequest hook answered allow
    runs: list = field(default_factory=list)


def _parse(path: Path, errors: list) -> list[HookEntry]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        errors.append(f"{path}: {e.__class__.__name__}")
        return []
    hooks = data.get("hooks") if isinstance(data, dict) else None
    if not isinstance(hooks, dict):
        errors.append(f"{path}: expected an object with hooks")
        return []
    out = []
    for event, groups in hooks.items():
        if event not in EVENTS or not isinstance(groups, list):
            errors.append(f"{path}: unknown or malformed event {event!r}")
            continue
        for group in groups:
            matcher = str(group.get("matcher", "")) if isinstance(group, dict) else ""
            for hook in (group.get("hooks", []) if isinstance(group, dict) else []):
                if isinstance(hook, dict) and hook.get("type") == "command" and hook.get("command"):
                    out.append(HookEntry(event, matcher, str(hook["command"]), str(path)))
    return out


def load(root: str, home: "str | None", *, trust_project: bool = False,
         ask=None) -> "tuple[list[HookEntry], list[str], bool]":
    """(entries, errors, project_loaded). Project hooks need trust or a yes."""
    errors: list = []
    entries = _parse(Path(home) / USER_FILE, errors) if home and \
        (Path(home) / USER_FILE).is_file() else []
    from .plugins import plugin_roots
    for plugin in plugin_roots(home):                     # installed by the user: trusted
        if (plugin / "hooks" / "hooks.json").is_file():
            entries += _parse(plugin / "hooks" / "hooks.json", errors)
    project = Path(root) / PROJECT_FILE
    loaded = False
    if project.is_file():
        found = _parse(project, errors)
        if found and (trust_project or (ask is not None and ask(found))):
            entries += found
            loaded = True
    return entries, errors, loaded


def _matches(entry: HookEntry, tool: "str | None") -> bool:
    if entry.matcher in ("", "*") or tool is None:
        return True
    try:
        return re.fullmatch(entry.matcher, tool) is not None
    except re.error:
        return False


def _run_one(entry: HookEntry, payload: dict, cwd: str) -> dict:
    from harness.safe_program import shell_env
    started = time.monotonic()
    try:
        p = subprocess.run(entry.command, shell=True, cwd=cwd, env=shell_env(cwd=cwd),
                           input=json.dumps(payload), capture_output=True, text=True,
                           timeout=TIMEOUT)
        code, out, err = p.returncode, p.stdout or "", p.stderr or ""
    except subprocess.TimeoutExpired:
        code, out, err = -1, "", f"hook timed out after {TIMEOUT}s"
    return {"command": entry.command[:120], "source": entry.source, "exit": code,
            "stdout": out[:2000], "stderr": err[:2000],
            "ms": int((time.monotonic() - started) * 1000)}


def _block_reason(event: str, run: dict) -> "str | None":
    if event not in BLOCKING:
        return None
    if run["exit"] == 2:
        return run["stderr"].strip() or "blocked by a hook"
    try:
        said = json.loads(run["stdout"]) if run["stdout"].strip().startswith("{") else {}
    except ValueError:
        said = {}
    if isinstance(said, dict) and said.get("decision") in ("block", "deny"):
        return str(said.get("reason") or "blocked by a hook")
    return None


def _says_allow(run: dict) -> bool:
    try:
        said = json.loads(run["stdout"]) if run["stdout"].strip().startswith("{") else {}
    except ValueError:
        return False
    return isinstance(said, dict) and said.get("decision") == "allow"


@dataclass
class Hooks:
    entries: list = field(default_factory=list)
    cwd: str = "."
    record: "object | None" = None        # callable(dict) -> None, the ledger writer

    def fire(self, event: str, payload: dict, tool: "str | None" = None) -> Outcome:
        outcome = Outcome()
        for entry in self.entries:
            if entry.event != event or not _matches(entry, tool):
                continue
            run = _run_one(entry, {"hook_event_name": event, **payload}, self.cwd)
            reason = _block_reason(event, run)
            run.update({"event": event, "blocked": reason is not None})
            if event == "PermissionRequest" and reason is None and _says_allow(run):
                outcome.allowed = True
            outcome.runs.append(run)
            if self.record is not None:
                self.record(run)
            if reason is not None:
                outcome.blocked, outcome.reason = True, reason
                break
        return outcome
