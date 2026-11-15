"""local_tools.py — the gated tool surface for the local agent's agentic loop.

Small local models cannot be trusted with native tool-calling or with an open
shell, so the tool surface is (1) a simple text protocol a 7B model can emit
reliably, and (2) gated by default: file reads/lists/writes are sandboxed to a
root; writes and command execution are OFF unless explicitly allowed. `run` gets
an environment allowlist (child_env), so no provider key reaches it. Two honest
limits: an allowed shell reaches paths OUTSIDE the root (not _safe_path-confined
like the file tools), and its denylist catches only a few literal spellings of
destructive commands (a guardrail, not a security boundary). --allow-exec implies
--allow-write. Each call returns a ToolResult the loop records in the ledger.

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

from .child_env import shell_env
from .hashline import annotate_hashed, as_lines, resolve_anchor
from .tools_prompt import TOOLS_SYSTEM  # re-exported: `from .local_tools import TOOLS_SYSTEM`

_TOOL_LINE = re.compile(r"^\s*TOOL\s+(\w+)\s+(\{.*\})\s*$")

# The file-writing tools, named once. Every accountability guard (the gate,
# integrity, review, bisect, cert, claim-grounding, the witnessed diff) checks
# membership here, so a new write tool is registered in a single place and
# cannot become a blind spot in one guard while the others still cover it.
WRITE_TOOLS = frozenset({"write_file", "edit_file", "edit_lines", "edit_plan", "apply_diff"})


def edited_targets(name: str, args: dict) -> list:
    """The (path, new_text) pairs one write-tool call touches: one source of truth so
    every guard sees the same edit surface, edit_plan's per-op files included. new_text
    is the introduced content the reward-hacking scan reads; a non-write call yields []."""
    if name == "write_file" and args.get("path"):
        return [(str(args["path"]), args.get("content", ""))]
    if name in ("edit_file", "edit_lines") and args.get("path"):
        return [(str(args["path"]), args.get("new", ""))]
    if name == "edit_plan":
        return [(str(op["path"]), op.get("new", ""))
                for op in args.get("ops", [])
                if isinstance(op, dict) and op.get("path")]
    if name == "apply_diff" and args.get("path"):        # scan only the added lines
        added = "\n".join(ln[1:] for ln in str(args.get("diff", "")).splitlines()
                          if ln.startswith("+") and not ln.startswith("+++"))
        return [(str(args["path"]), added)]
    return []

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
    """Default-deny for anything that writes or executes.

    exec is a SUPERSET of write: an allowed shell can create/overwrite files
    (redirection, tee, sed -i, python -c). So --allow-exec implies --allow-write —
    the gate couples them rather than presenting writes as 'off' while an open
    shell is enabled, which would be a gate the run path silently bypasses."""
    allow_write: bool = False
    allow_exec: bool = False

    def __post_init__(self):
        if self.allow_exec:
            self.allow_write = True

    def check(self, name: str, args: dict) -> "str | None":
        if name in WRITE_TOOLS and not self.allow_write:
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
            body = f.read()
        if args.get("hashed"):
            return True, annotate_hashed(body)   # opt-in; default read is unchanged
        return True, body

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

    def _t_edit_lines(self, args) -> "tuple[bool, str]":
        """Hash-anchored edit. Address lines by the anchors a `hashed` read emits
        instead of by repeating their text:
            replace one line    -> {"path", "at": "<anchor>", "new": "..."}
            replace a block      -> {"path", "at": "<start>", "end": "<stop>", "new": "..."}
            insert after a line  -> {"path", "after": "<anchor>", "new": "..."}
            delete               -> an empty "new" with "at" (or "at" + "end")
        An anchor computed against a stale view will not match, so a mismatched
        edit is refused rather than landing on the wrong line."""
        p = _safe_path(self.root, args.get("path", ""))
        if p is None:
            return False, "[error] path escapes root"
        at, end, after = args.get("at"), args.get("end"), args.get("after")
        if not at and not after:
            return False, "[error] edit_lines needs 'at' (replace) or 'after' (insert)"
        new = args.get("new", "")
        with open(p, encoding="utf-8") as f:
            lines = f.read().splitlines(keepends=True)

        if after:
            i, err = resolve_anchor(lines, after)
            if err:
                return False, err
            if not lines[i].endswith(("\n", "\r")):     # keep a separator at EOF
                lines[i] += "\n"
            lines[i + 1:i + 1] = as_lines(new, "\n")
            msg = f"insert after {after}"
        else:
            i, err = resolve_anchor(lines, at)
            if err:
                return False, err
            j = i
            if end:
                j, err = resolve_anchor(lines, end)
                if err:
                    return False, err
                if j < i:
                    return False, "[error] 'end' anchor precedes 'at'"
            nl = "\n" if lines[j].endswith("\n") else ""   # preserve a no-EOL final line
            lines[i:j + 1] = as_lines(new, nl)
            span = at if j == i else f"{at}..{end}"
            msg = f"{'delete' if new == '' else 'replace'} {span}"

        with open(p, "w", encoding="utf-8") as f:
            f.write("".join(lines))
        return True, f"edited {args.get('path')} ({msg})"

    def _t_edit_plan(self, args) -> "tuple[bool, str]":
        """Transactional multi-file edit: apply a list of hash-anchored ops as ONE
        all-or-nothing checkpoint (each op is {path, at|after, end?, new}). If any
        anchor is stale, ambiguous, or overlaps another op, nothing is written. The
        receipt lets a stranger recompute each anchor from its recorded pre-image."""
        from .edit_plan import build_plan
        ops = args.get("ops")
        if not isinstance(ops, list) or not ops:
            return False, "[error] edit_plan needs a non-empty 'ops' list"

        def _read(path):
            try:
                with open(path, encoding="utf-8") as f:
                    return f.read()
            except FileNotFoundError:
                return None

        result, err = build_plan(lambda rel: _safe_path(self.root, rel), _read, ops)
        if err:
            return False, f"[error] {err}"
        writes, receipt = result
        for path, text in writes:                    # validated fully; now write each once
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        return True, (f"edit_plan applied {len(ops)} ops across {len(writes)} file(s)\n"
                      + json.dumps({"receipt": receipt}, sort_keys=True))

    def _t_apply_diff(self, args) -> "tuple[bool, str]":
        """Apply a unified diff to one file, fail-closed: each hunk's context and
        removed lines must match the current file exactly, or the whole patch is
        refused (no fuzz). A model that emits diffs gets the anchored-edit guarantee."""
        from .udiff import apply_udiff, parse_hunks
        p = _safe_path(self.root, args.get("path", ""))
        if p is None:
            return False, "[error] path escapes root"
        if not str(args.get("diff", "")).strip():
            return False, "[error] apply_diff needs a non-empty 'diff'"
        hunks, err = parse_hunks(args["diff"])
        if err:
            return False, f"[error] {err}"
        with open(p, encoding="utf-8") as f:
            new, err = apply_udiff(f.read(), hunks)
        if err:
            return False, f"[error] {err}"
        with open(p, "w", encoding="utf-8") as f:
            f.write(new)
        return True, f"applied {len(hunks)} hunk(s) to {args.get('path')}"

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
                              text=True, timeout=120, env=shell_env(cwd=self.root))
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode == 0, f"[exit {proc.returncode}]\n{out}"
