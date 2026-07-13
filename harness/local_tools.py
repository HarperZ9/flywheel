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
from pathlib import Path

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
    allow_mcp: bool = False        # outbound calls to external MCP tool servers

    def check(self, name: str, args: dict) -> "str | None":
        if name in ("write_file", "edit_file", "apply_patch") and not self.allow_write:
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


def _strip_ab(path: str) -> str:
    return path[2:] if path[:2] in ("a/", "b/") else path


def _apply_hunks(old_lines: list, body: list) -> "tuple[bool, list | str]":
    """Apply one file's hunks strictly. Every context/removed line must match."""
    new_lines, cursor, i = [], 0, 0
    while i < len(body):
        if not body[i].startswith("@@"):
            i += 1
            continue
        m = re.match(r"@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@", body[i])
        if not m:
            return False, f"bad hunk header: {body[i][:40]}"
        start = int(m.group(1)) - 1
        start = max(start, 0)
        if start < cursor or start > len(old_lines):
            return False, f"hunk at {start + 1} out of range"
        new_lines.extend(old_lines[cursor:start])
        cursor = start
        i += 1
        while i < len(body) and not body[i].startswith("@@"):
            h = body[i]
            i += 1
            if h == "" or h.startswith("\\"):        # split artifact / "no newline" marker
                continue
            tag, text = h[0], h[1:]
            if tag == " ":
                if cursor >= len(old_lines) or old_lines[cursor] != text:
                    return False, f"context mismatch at line {cursor + 1}"
                new_lines.append(old_lines[cursor])
                cursor += 1
            elif tag == "-":
                if cursor >= len(old_lines) or old_lines[cursor] != text:
                    return False, f"removed-line mismatch at line {cursor + 1}"
                cursor += 1
            elif tag == "+":
                new_lines.append(text)
    new_lines.extend(old_lines[cursor:])
    return True, new_lines


def _apply_unified_diff(root: str, patch: str) -> "tuple[bool, str]":
    """Apply a unified diff (LF, one or more file sections) strictly under root. On
    ANY hunk mismatch the whole patch is refused (verified before a byte is written),
    so a stale diff never corrupts a file. New files (--- /dev/null) are created."""
    lines = patch.replace("\r\n", "\n").split("\n")
    i, sections = 0, []
    while i < len(lines):
        if (lines[i].startswith("--- ") and i + 1 < len(lines)
                and lines[i + 1].startswith("+++ ")):
            old_hdr, new_hdr, j, body = lines[i], lines[i + 1], i + 2, []
            while j < len(lines) and not (lines[j].startswith("--- ") and j + 1 < len(lines)
                                          and lines[j + 1].startswith("+++ ")):
                body.append(lines[j])
                j += 1
            sections.append((old_hdr, new_hdr, body))
            i = j
        else:
            i += 1
    if not sections:
        return False, "no file sections in patch"
    writes, names = [], []
    for old_hdr, new_hdr, body in sections:
        rel = _strip_ab(new_hdr[4:].strip())
        target = _safe_path(root, rel)
        if target is None:
            return False, f"path escapes root: {rel}"
        is_new = "/dev/null" in old_hdr
        try:
            old_lines = [] if is_new else Path(target).read_text(encoding="utf-8").split("\n")
        except OSError:
            old_lines = []
        ok, result = _apply_hunks(old_lines, body)
        if not ok:
            return False, f"{rel}: {result}"
        writes.append((target, "\n".join(result)))
        names.append(rel)
    for target, content in writes:                  # only after every hunk verified
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
    return True, f"applied {len(writes)} file(s): " + ", ".join(names)


@dataclass
class ToolExecutor:
    root: str = "."
    gate: ToolGate = field(default_factory=ToolGate)
    max_output: int = 4000
    runner: "callable" = None      # inject for tests; default = subprocess
    external: dict = field(default_factory=dict)   # name -> {"fn": args->(ok,str), "description": str}

    def external_tools_system(self) -> str:
        """Advertise registered external (MCP) tools to the model, in the same
        TOOL protocol. Empty when none are registered."""
        if not self.external:
            return ""
        lines = ["Additional tools (same TOOL protocol, one call per line):"]
        for name, spec in sorted(self.external.items()):
            desc = (spec.get("description", "") or "").splitlines()[0][:100]
            lines.append(f'TOOL {name} {{...}}   # {desc}')
        return "\n".join(lines)

    def execute(self, name: str, args: dict) -> ToolResult:
        if name in self.external:
            if not self.gate.allow_mcp:
                return ToolResult(name, args, False,
                                  "[gate] external/MCP tools disabled (pass allow_mcp)")
            try:
                ok, out = self.external[name]["fn"](args)
            except Exception as e:                       # an external server must never crash the loop
                return ToolResult(name, args, False, f"[error] {type(e).__name__}: {e}")
            return ToolResult(name, args, bool(ok), str(out)[: self.max_output])
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

    def _t_grep(self, args) -> "tuple[bool, str]":
        pattern = args.get("pattern", "")
        if not pattern:
            return False, "[error] grep needs a 'pattern'"
        try:
            rx = re.compile(pattern)
        except re.error as e:
            return False, f"[error] bad regex: {e}"
        base = _safe_path(self.root, args.get("path", "."))
        if base is None:
            return False, "[error] path escapes root"
        root_abs = os.path.realpath(self.root)
        p = Path(base)
        files = [p] if p.is_file() else p.rglob(args.get("glob", "*"))
        hits = []
        for f in files:
            if not f.is_file():
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for n, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    rel = os.path.relpath(str(f), root_abs).replace("\\", "/")
                    hits.append(f"{rel}:{n}:{line[:200]}")
                    if len(hits) >= 200:
                        return True, "\n".join(hits) + "\n... (truncated at 200 matches)"
        return True, "\n".join(hits) if hits else "(no matches)"

    def _t_glob(self, args) -> "tuple[bool, str]":
        root_abs = os.path.realpath(self.root)
        matches = []
        for f in Path(root_abs).rglob(args.get("pattern", "*")):
            matches.append(os.path.relpath(str(f), root_abs).replace("\\", "/"))
            if len(matches) >= 500:
                break
        return True, "\n".join(sorted(matches)) if matches else "(no matches)"

    def _t_apply_patch(self, args) -> "tuple[bool, str]":
        patch = args.get("patch") or args.get("diff") or ""
        if not patch.strip():
            return False, "[error] apply_patch needs a unified diff in 'patch'"
        ok, msg = _apply_unified_diff(self.root, patch)
        return ok, msg if ok else f"[error] {msg}"


TOOLS_SYSTEM = (
    "You can use tools by emitting lines in this exact format (one per line):\n"
    'TOOL repo_map {"path": "."}\n'
    'TOOL read_file {"path": "<path>"}\n'
    'TOOL list_dir {"path": "<path>"}\n'
    'TOOL edit_file {"path": "<path>", "old": "<exact text>", "new": "<replacement>"}\n'
    'TOOL write_file {"path": "<path>", "content": "<text>"}\n'
    'TOOL run {"cmd": "<shell command>"}\n'
    'TOOL grep {"pattern": "<regex>", "path": "<dir>", "glob": "*.py"}\n'
    'TOOL glob {"pattern": "**/*.py"}\n'
    'TOOL apply_patch {"patch": "<unified diff>"}\n'
    "Prefer repo_map then read_file to locate code, and edit_file (the 'old' text "
    "must be unique) over write_file for changes. After you receive the tool "
    "results, continue. When you have the final answer and need no more tools, "
    "reply with the answer and DO NOT emit any TOOL line. Keep tool use minimal."
)
