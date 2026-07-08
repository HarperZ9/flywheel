"""local_tools.py — the gated tool surface for the local agent's agentic loop.

Small local models cannot be trusted with native tool-calling or with an open
shell, so the tool surface is (1) a simple text protocol a 7B model can emit
reliably, and (2) gated by default: file reads/lists are sandboxed to a root;
writes and command execution are OFF unless explicitly allowed, and even then a
denylist blocks obviously destructive commands. Every call returns a ToolResult
that the loop records into the witnessed session ledger.

Protocol (one call per line, args as a JSON object):
    TOOL read_file {"path": "harness/loop.py"}
    TOOL list_dir {"path": "."}
    TOOL write_file {"path": "out.txt", "content": "..."}
    TOOL run {"cmd": "python -m pytest -q"}
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field

_TOOL_LINE = re.compile(r"^\s*TOOL\s+(\w+)\s+(\{.*\})\s*$")

# Commands refused even when exec is allowed. Not a security boundary against a
# determined operator — a guardrail against a small model wrecking the tree.
_DENY = re.compile(
    r"\b(rm\s+-rf|rmdir\s+/s|del\s+/|format\s|mkfs|dd\s+if=|shutdown|reboot|"
    r":\(\)\s*\{|curl[^|]*\|\s*(sh|bash)|wget[^|]*\|\s*(sh|bash)|>\s*/dev/sd)",
    re.IGNORECASE)


@dataclass
class ToolResult:
    name: str
    args: dict
    ok: bool
    output: str


@dataclass
class ToolGate:
    """Default-deny for anything that writes or executes."""
    allow_write: bool = False
    allow_exec: bool = False

    def check(self, name: str, args: dict) -> "str | None":
        if name in ("write_file", "edit_file") and not self.allow_write:
            return "write disabled (pass --allow-write)"
        if name in ("run",):
            if not self.allow_exec:
                return "exec disabled (pass --allow-exec)"
            if _DENY.search(args.get("cmd", "")):
                return "command blocked by denylist"
        return None


def parse_tool_calls(text: str) -> list[tuple[str, dict]]:
    """Extract (name, args) calls from model output. A malformed args object is
    skipped (not executed) so a garbled emission never runs something unintended."""
    calls: list[tuple[str, dict]] = []
    for line in text.splitlines():
        m = _TOOL_LINE.match(line)
        if not m:
            continue
        try:
            args = json.loads(m.group(2))
        except json.JSONDecodeError:
            continue
        if isinstance(args, dict):
            calls.append((m.group(1), args))
    return calls


def _safe_path(root: str, path: str) -> "str | None":
    """Resolve path under root; None if it escapes (no traversal out of the tree)."""
    root_abs = os.path.realpath(root)
    target = os.path.realpath(os.path.join(root_abs, path))
    if target == root_abs or target.startswith(root_abs + os.sep):
        return target
    return None


@dataclass
class ToolExecutor:
    root: str = "."
    gate: ToolGate = field(default_factory=ToolGate)
    max_output: int = 4000
    runner: "callable" = None      # inject for tests; default = subprocess

    def execute(self, name: str, args: dict) -> ToolResult:
        denied = self.gate.check(name, args)
        if denied:
            return ToolResult(name, args, False, f"[gate] {denied}")
        fn = getattr(self, f"_t_{name}", None)
        if fn is None:
            return ToolResult(name, args, False, f"[error] unknown tool {name!r}")
        try:
            ok, out = fn(args)
        except Exception as e:                       # a tool must never crash the loop
            return ToolResult(name, args, False, f"[error] {type(e).__name__}: {e}")
        return ToolResult(name, args, ok, out[: self.max_output])

    def _t_read_file(self, args) -> "tuple[bool, str]":
        p = _safe_path(self.root, args.get("path", ""))
        if p is None:
            return False, "[error] path escapes root"
        with open(p, encoding="utf-8", errors="replace") as f:
            return True, f.read()

    def _t_list_dir(self, args) -> "tuple[bool, str]":
        p = _safe_path(self.root, args.get("path", "."))
        if p is None:
            return False, "[error] path escapes root"
        return True, "\n".join(sorted(os.listdir(p)))

    def _t_write_file(self, args) -> "tuple[bool, str]":
        p = _safe_path(self.root, args.get("path", ""))
        if p is None:
            return False, "[error] path escapes root"
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(args.get("content", ""))
        return True, f"wrote {len(args.get('content', ''))} bytes to {args.get('path')}"

    def _t_edit_file(self, args) -> "tuple[bool, str]":
        """Precise search/replace: the `old` text must match EXACTLY ONCE, so an
        ambiguous or stale edit is refused instead of silently corrupting code."""
        p = _safe_path(self.root, args.get("path", ""))
        if p is None:
            return False, "[error] path escapes root"
        old, new = args.get("old", ""), args.get("new", "")
        if not old:
            return False, "[error] edit_file needs a non-empty 'old' string"
        with open(p, encoding="utf-8") as f:
            body = f.read()
        n = body.count(old)
        if n == 0:
            return False, "[error] 'old' text not found (stale or mismatched)"
        if n > 1:
            return False, f"[error] 'old' matches {n} times; add context to make it unique"
        with open(p, "w", encoding="utf-8") as f:
            f.write(body.replace(old, new, 1))
        return True, f"edited {args.get('path')} (1 replacement)"

    def _t_repo_map(self, args) -> "tuple[bool, str]":
        from .local_repomap import build_repo_map
        sub = _safe_path(self.root, args.get("path", "."))
        if sub is None:
            return False, "[error] path escapes root"
        return True, build_repo_map(sub, rel_to=self.root)

    def _t_run(self, args) -> "tuple[bool, str]":
        cmd = args.get("cmd", "")
        if self.runner is not None:
            return self.runner(cmd, self.root)
        proc = subprocess.run(cmd, shell=True, cwd=self.root, capture_output=True,
                              text=True, timeout=120)
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode == 0, f"[exit {proc.returncode}]\n{out}"


TOOLS_SYSTEM = (
    "You can use tools by emitting lines in this exact format (one per line):\n"
    'TOOL repo_map {"path": "."}\n'
    'TOOL read_file {"path": "<path>"}\n'
    'TOOL list_dir {"path": "<path>"}\n'
    'TOOL edit_file {"path": "<path>", "old": "<exact text>", "new": "<replacement>"}\n'
    'TOOL write_file {"path": "<path>", "content": "<text>"}\n'
    'TOOL run {"cmd": "<shell command>"}\n'
    "Prefer repo_map then read_file to locate code, and edit_file (the 'old' text "
    "must be unique) over write_file for changes. After you receive the tool "
    "results, continue. When you have the final answer and need no more tools, "
    "reply with the answer and DO NOT emit any TOOL line. Keep tool use minimal."
)
