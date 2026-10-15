"""policy.py -- permission modes for a coding session, enforced before the gate.

Four named modes, the shape the strong harnesses converged on:

  plan  reads only; every write and command is refused at the gate
  ask   reads run; each write and each command waits for your yes
  edit  reads and writes run; each command waits for your yes
  auto  everything runs, still behind the denylist and the pre-action monitor

The decision happens in SessionExecutor.execute, ahead of the existing
ToolGate, the pre-action monitor and the receipt path, and every decision is
handed to the session so it lands on the hash-chained ledger: what was asked,
what was decided, and who decided it (the mode, a standing "always", or the
person at the prompt). A refused call never reaches the tool. Nothing here
loosens the gate: plan mode builds the gate with writes and exec off, so even
a policy bug cannot let a write through in plan mode.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from harness.local_tools import ToolExecutor, ToolGate, ToolResult

MODES = ("plan", "ask", "edit", "auto")
WRITE_TOOLS = frozenset({"write_file", "edit_file", "apply_patch"})
EXEC_TOOLS = frozenset({"run"})
# `task` is allowed in every mode because its child decides each of its own calls
# under the same mode, rules and approver.
READ_TOOLS = frozenset({"read_file", "list_dir", "repo_map", "grep", "glob", "todo", "skill",
                        "task"})
NETWORK_TOOLS = frozenset({"web_fetch"})
TODO_STATES = ("pending", "in_progress", "done")
TODO_TOOL_TEXT = (
    'TOOL todo {"items": [{"text": "<step>", "status": "pending|in_progress|done"}, ...]}\n'
    "For work with several steps, keep a todo list with the todo tool: send the "
    "whole list each time, mark one item in_progress while you work on it, and "
    "mark items done as you finish them.")

WEB_TOOL_TEXT = ('Also available, in the same TOOL protocol: TOOL web_fetch {"url": "https://..."} '
                 "reads one web page as text.")
DENIED_BY_USER = ("[denied] the user declined this call. Do not retry it "
                  "unchanged; explain what you need or choose another approach.")
DENIED_BY_RULE = "[denied] a permission rule refuses this call: {rule}"
DENIED_BY_MODE = ("[denied] plan mode is read-only: writes and commands are off. "
                  "Describe the change as a plan instead.")


def tool_class(name: str) -> str:
    if name in READ_TOOLS:
        return "read"
    if name in WRITE_TOOLS:
        return "write"
    if name in EXEC_TOOLS:
        return "exec"
    if name in NETWORK_TOOLS:
        return "network"
    return "other"           # external MCP tools and anything unknown


def mode_decision(mode: str, cls: str) -> str:
    """allow, ask or deny for a tool class under a mode."""
    if cls == "read":
        return "allow"
    if mode == "plan":
        return "deny"
    if mode == "auto":
        return "allow"
    if mode == "edit" and cls == "write":
        return "allow"
    return "ask"


def gate_for(mode: str) -> ToolGate:
    """The inner gate for a mode. Plan mode turns writes and exec off at the gate."""
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; choose one of {', '.join(MODES)}")
    on = mode != "plan"
    return ToolGate(allow_write=on, allow_exec=on, allow_mcp=on)


Approver = Callable[[str, dict], str]      # returns "yes", "no" or "always"


def deny_all(_name: str, _args: dict) -> str:
    """The approver when nobody is at the keyboard: every ask becomes a no."""
    return "no"


@dataclass
class SessionExecutor(ToolExecutor):
    """ToolExecutor with a permission mode, an approver and a decision log."""
    mode: str = "ask"
    approver: Approver = deny_all
    on_decision: "Callable[[dict], None] | None" = None
    always: set = field(default_factory=set)
    before_write: "Callable[[str, dict], None] | None" = None
    rules: "object | None" = None
    pre_tool: "Callable[[str, dict], str | None] | None" = None    # returns a block reason
    post_tool: "Callable[[str, dict, ToolResult], None] | None" = None
    todos: list = field(default_factory=list)
    skills: dict = field(default_factory=dict)
    allowed_tools: "frozenset | None" = None     # a subagent's tool list; None is all
    task_runner: "Callable[[dict], tuple[bool, str]] | None" = None

    def set_mode(self, mode: str) -> None:
        self.gate = gate_for(mode)
        self.mode = mode

    def _decide(self, name: str, args: dict) -> "tuple[str, str]":
        if self.allowed_tools is not None and name not in self.allowed_tools:
            return "deny", "agent:tool-not-listed"
        cls = tool_class(name)
        verdict = mode_decision(self.mode, cls)
        matched = self.rules.match(name, args) if self.rules is not None else None
        if matched and matched[0] == "deny":
            return "deny", f"rule:deny:{matched[1]}"
        if verdict != "ask":
            return verdict, f"mode:{self.mode}"
        if matched:
            return "allow", f"rule:allow:{matched[1]}"
        if name in self.always:
            return "allow", "always"
        answer = self.approver(name, args)
        if answer == "always":
            self.always.add(name)
            return "allow", "user:always"
        return ("allow", "user:yes") if answer == "yes" else ("deny", "user:no")

    def execute(self, name: str, args: dict, rationale: "dict | None" = None) -> ToolResult:
        blocked = self.pre_tool(name, args) if self.pre_tool is not None else None
        if blocked is not None:
            if self.on_decision is not None:
                self.on_decision({"tool": name, "class": tool_class(name), "mode": self.mode,
                                  "decision": "deny", "by": "hook"})
            return ToolResult(name, args, False, f"[denied] a PreToolUse hook blocked "
                              f"this call: {blocked}")
        result = self._execute_decided(name, args, rationale)
        if self.post_tool is not None:
            self.post_tool(name, args, result)
        return result

    def _execute_decided(self, name: str, args: dict, rationale) -> ToolResult:
        verdict, source = self._decide(name, args)
        if self.on_decision is not None:
            self.on_decision({"tool": name, "class": tool_class(name), "mode": self.mode,
                              "decision": verdict, "by": source})
        if verdict == "deny":
            text = ("[denied] this agent's tool list does not include " + name
                    if source == "agent:tool-not-listed" else
                    DENIED_BY_MODE if source == "mode:plan" else
                    DENIED_BY_RULE.format(rule=source[len("rule:deny:"):])
                    if source.startswith("rule:deny:") else DENIED_BY_USER)
            return ToolResult(name, args, False, text)
        if name in WRITE_TOOLS and self.before_write is not None:
            self.before_write(name, args)
        return super().execute(name, args, rationale=rationale)

    def _t_todo(self, args) -> "tuple[bool, str]":
        """Replace the session's todo list; returns it rendered."""
        items = args.get("items")
        if not isinstance(items, list):
            return False, "[error] todo needs an 'items' list"
        clean = []
        for item in items:
            if not isinstance(item, dict) or not str(item.get("text", "")).strip():
                return False, "[error] each todo item needs a 'text'"
            status = item.get("status", "pending")
            if status not in TODO_STATES:
                return False, f"[error] status must be one of {', '.join(TODO_STATES)}"
            clean.append({"text": str(item["text"]).strip(), "status": status})
        self.todos = clean
        return True, render_todos(clean)


    def _t_task(self, args) -> "tuple[bool, str]":
        if self.task_runner is None:
            return False, "[error] subagents are not available here"
        return self.task_runner(args)

    def _t_skill(self, args) -> "tuple[bool, str]":
        from .skills import read_skill
        return read_skill(self.skills, str(args.get("name", "")))

    def _t_web_fetch(self, args) -> "tuple[bool, str]":
        from .web import fetch
        return fetch(str(args.get("url", "")))


def render_todos(items: list) -> str:
    if not items:
        return "(no todo items)"
    marks = {"pending": "[ ]", "in_progress": "[>]", "done": "[x]"}
    return "\n".join(f"{marks[i['status']]} {i['text']}" for i in items)
