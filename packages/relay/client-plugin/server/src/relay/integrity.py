"""integrity.py -- reward-hacking guard for the acceptance check (zero-dep).

An acceptance check that CAN fail is only useful if it cannot be TRICKED into
passing. An agent can make `pytest` green without solving the task: skip or xfail
the failing test, sys.exit(0) before the assertion runs, monkeypatch the framework,
or simply edit the test file that grades it. Reward-hacking research shows models
learn exactly these shortcuts, so a pass over a witnessed trajectory is trusted only
when the trajectory did not tamper with the check.

Everything here is rule-based and non-learned: each flag is a fixed rule a third
party re-runs to reproduce the same verdict. Nothing here ACCEPTS anything; it only
lets the caller REFUSE a gamed pass. `scan_reward_hacking(code)` checks a code
fragment; `trajectory_integrity(ledger)` checks the witnessed edit set; both feed
`integrity_report`, a re-checkable {clean, flags, hash}.
"""
from __future__ import annotations

import ast
import fnmatch
import hashlib
import json
from dataclasses import dataclass

from .local_tools import edited_targets

_SKIP_CALLS = {"pytest.skip", "pytest.xfail", "unittest.skip", "unittest.SkipTest",
               "pytest.importorskip"}
_EXIT_CALLS = {"sys.exit", "os._exit", "exit", "quit"}
_TRACE_CALLS = {"sys.settrace", "sys.setprofile", "threading.settrace"}
_PATCH_TARGETS = {"pytest", "unittest", "builtins", "__builtins__"}
_SKIP_DECORATORS = {"skip", "skipif", "xfail", "skipUnless", "skipIf"}

# Files that grade the work: editing these from inside the agent loop is a hack.
DEFAULT_PROTECTED = ("test_*.py", "*_test.py", "tests/*", "conftest.py")


@dataclass(frozen=True)
class Flag:
    kind: str
    detail: str
    where: str = ""

    def as_dict(self) -> dict:
        return {"kind": self.kind, "detail": self.detail, "where": self.where}


def _dotted(node) -> str:
    """Best-effort dotted name for an ast Attribute/Name chain ('' if unknown)."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def _dedup(flags: list) -> list:
    seen, out = set(), []
    for f in flags:
        key = (f.kind, f.detail, f.where)
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


def scan_reward_hacking(code: str) -> list:
    """Flag test-neutralizing patterns in a code fragment. Non-learned, deterministic."""
    if not code or not code.strip():
        return []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []            # a fragment need not be a whole module; not itself a hack
    flags: list = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _dotted(node.func)
            if name in _SKIP_CALLS:
                flags.append(Flag("test_skip", f"calls {name}()"))
            elif name in _EXIT_CALLS:
                flags.append(Flag("premature_exit", f"calls {name}()"))
            elif name in _TRACE_CALLS:
                flags.append(Flag("trace_hijack", f"calls {name}()"))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for dec in node.decorator_list:
                target = dec.func if isinstance(dec, ast.Call) else dec
                dname = _dotted(target)
                if dname and dname.split(".")[-1] in _SKIP_DECORATORS and (
                        "mark" in dname or "unittest" in dname or "pytest" in dname):
                    flags.append(Flag("test_skip", f"@{dname} on {node.name}"))
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "pytestmark":
                    flags.append(Flag("module_skip", "sets module-level pytestmark"))
                elif isinstance(t, ast.Attribute):
                    base = _dotted(t.value)
                    if base in _PATCH_TARGETS:
                        flags.append(Flag("monkeypatch", f"assigns {base}.{t.attr}"))
        elif isinstance(node, ast.Raise) and node.exc is not None:
            exc = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
            if _dotted(exc).split(".")[-1] == "SystemExit":
                flags.append(Flag("premature_exit", "raises SystemExit"))
    return _dedup(flags)


def _parse_tool_call(content: str):
    """A ledger tool_call entry is 'name {json-args}'. Returns (name, args) or None."""
    parts = content.split(None, 1)
    if len(parts) != 2:
        return None
    name, blob = parts[0], parts[1]
    try:
        args = json.loads(blob)
    except (json.JSONDecodeError, ValueError):
        return None
    return (name, args) if isinstance(args, dict) else None


def _matches(path: str, globs) -> bool:
    base = path.replace("\\", "/").rsplit("/", 1)[-1]
    norm = path.replace("\\", "/")
    return any(fnmatch.fnmatch(base, g) or fnmatch.fnmatch(norm, g)
               or fnmatch.fnmatch(norm, f"*/{g}") for g in globs)


def trajectory_integrity(ledger, *, protected=DEFAULT_PROTECTED) -> list:
    """Flags over a witnessed ledger: did the agent edit a file that grades it, or
    write test-neutralizing code? This is what stops a run from 'passing' its check by
    deleting or skipping the failing test."""
    flags: list = []
    for e in getattr(ledger, "entries", []):
        if getattr(e, "kind", "") != "tool_call":
            continue
        parsed = _parse_tool_call(getattr(e, "content", ""))
        if not parsed:
            continue
        name, args = parsed
        where = f"seq {getattr(e, 'seq', '?')}"
        for path, new in edited_targets(name, args):
            if path and _matches(path, protected):
                flags.append(Flag("edited_protected_file", f"{name} {path}", where))
            if isinstance(new, str) and new.strip():
                for sub in scan_reward_hacking(new):
                    flags.append(Flag(f"introduced_{sub.kind}", sub.detail, f"{where} {path}"))
    return _dedup(flags)


def integrity_report(flags: list) -> dict:
    """A re-checkable summary: clean verdict + the flags + a hash over them."""
    rows = [f.as_dict() for f in flags]
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()[:16]
    return {"schema": "relay.integrity/v1", "clean": not flags,
            "flag_count": len(flags), "flags": rows, "flags_sha256": digest}
