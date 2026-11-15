#!/usr/bin/env python
"""safe-exec - workspace command hook.

Routes workspace command requests through the standard command layer.

Exit 2 + stderr message asks the assistant to use the workspace command
form for the same task.

Trigger: PreToolUse matching "Bash|PowerShell".
Stdin:   JSON with tool_name + tool_input.command.
Stdout:  silent on allow.
Stderr:  command guidance on exit 2.

Scope - commands that use the workspace path
--------------------------------------------
Commands whose output frequently includes workspace-specific text:
  grep / rg (ripgrep)     — search output: file content + paths
  git log / diff / show / blame / grep — code content + commit messages
  find / Get-ChildItem    — file path listings
  pytest / python -m pytest — test output: function names + stack traces
  Select-String           — PowerShell grep equivalent
  cat / head / tail       — file content (complement to safe-read)
  python -c / python -m   — ad-hoc execution that may import workspace modules

Always allowed
--------------
  * Any call to safe_exec.py itself (self-reference — would loop)
  * Any call to safe_read / safe_write / safe_fetch (workspace tooling)
  * Any call to companion workspace utilities
  * Any call under ~/.claude/hooks/ (hook infrastructure)
  * Git write operations: commit, push, add, stash, checkout, branch,
    merge, rebase, reset, tag, remote (normally short status output)
  * Package management: pip, npm, yarn, cargo, gem (installer output)
  * Filesystem management: mkdir, mv, cp, rm, touch, setx, export
  * Short probes: git status, git rev-parse, which, type, where

Override
--------
Use the named workstation mode commands for native inspection.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Patterns for commands that use the workspace path.
# ---------------------------------------------------------------------------

def _tools_path() -> Path:
    bt = os.environ.get("BEHAVIOR_TRANSFORM_TOOLS", "").strip()
    if bt and Path(bt).is_dir():
        return Path(bt)
    return Path(__file__).resolve().parents[1] / "tools"

_SAFE_EXEC = str(_tools_path() / "safe_exec.py")

_HIGH_OUTPUT_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\bgrep\b",
        r"\brg\b(?:\s|$)",          # ripgrep (short form — guard against 'rg' in paths)
        r"\bripgrep\b",
        r"\bgit\s+log\b",
        r"\bgit\s+diff\b",
        r"\bgit\s+show\b",
        r"\bgit\s+blame\b",
        r"\bgit\s+grep\b",
        r"\bfind\s+",               # find with args (not 'find' alone)
        r"\bpytest\b",
        r"-m\s+pytest\b",
        r"\bGet-ChildItem\b",
        r"\bSelect-String\b",
        r"\bcat\s+",                # cat with args
        r"\bhead\s+",
        r"\btail\s+",
        r"\bpython\s+-c\b",         # ad-hoc python execution
        r"\bpython3?\s+-m\b",       # python -m <module>
        r"python3?\s+.*warden",     # any python call touching warden modules
    ]
]

# ---------------------------------------------------------------------------
# Patterns for commands that stay on their direct path.
# ---------------------------------------------------------------------------

_ALLOW_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [
        # Workspace wrapper self-reference.
        r"safe_[\w.-]+\.py",
        r"aup_[\w.-]+\.py",
        r"behavior-transform\.io[/\]tools[/\][\w.-]+\.py",
        r"behavior-transform[._-][a-z]+[/\]tools[/\][\w.-]+\.py",
        # Hook infrastructure.
        r"\.claude[/\\]hooks",
        r"check-branch\.sh",
        r"lint-on-save\.sh",
        r"verify-no-secrets\.sh",
        # Git write operations (normally short status output)
        r"\bgit\s+commit\b",
        r"\bgit\s+push\b",
        r"\bgit\s+add\b",
        r"\bgit\s+stash\b",
        r"\bgit\s+checkout\b",
        r"\bgit\s+switch\b",
        r"\bgit\s+branch\b",
        r"\bgit\s+merge\b",
        r"\bgit\s+rebase\b",
        r"\bgit\s+reset\b",
        r"\bgit\s+tag\b",
        r"\bgit\s+remote\b",
        r"\bgit\s+fetch\b",
        r"\bgit\s+clone\b",
        r"\bgit\s+init\b",
        r"\bgit\s+status\b",
        r"\bgit\s+rev-parse\b",
        r"\bgit\s+rev-list\b",
        r"\bgit\s+symbolic-ref\b",
        # Package management
        r"\bpip\s+install\b",
        r"\bpip\s+uninstall\b",
        r"\bnpm\s+install\b",
        r"\byarn\s+",
        r"\bcargo\s+",
        r"\bgem\s+",
        # Filesystem management
        r"^\s*(mkdir|mv|cp|rm|touch|setx|export|echo|printf)\b",
        r"^\s*(New-Item|Remove-Item|Move-Item|Copy-Item|Set-Variable)\b",
        # Simple probes
        r"^\s*which\b",
        r"^\s*type\b",
        r"^\s*where\b",
        r"^\s*ls\b",
        # pytest via safe_exec (already routed)
        r"safe_exec.*pytest",
    ]
]

_EXEC_GUIDANCE_MSG = (
    "Use the workspace command channel for this command:\n\n"
    "    python " + _SAFE_EXEC + " -- {cmd_short}\n\n"
    "    # With stderr:\n"
    "    python " + _SAFE_EXEC + " --include-stderr -- {cmd_short}\n\n"
    "For direct native inspection, ask the operator to enable research or academic mode.\n"
)


def _should_allow(command: str) -> bool:
    for pattern in _ALLOW_PATTERNS:
        if pattern.search(command):
            return True
    return False


def _uses_workspace_path(command: str) -> bool:
    for pattern in _HIGH_OUTPUT_PATTERNS:
        if pattern.search(command):
            return True
    return False


def _gate() -> bool:
    """Return True (caller should sys.exit(0)) when mode is research/academic."""
    import os
    from pathlib import Path

    bt = os.environ.get("BEHAVIOR_TRANSFORM_TOOLS", "").strip()
    _tools = (
        Path(bt)
        if bt and Path(bt).is_dir()
        else Path(__file__).resolve().parents[1] / "tools"
    )
    if str(_tools) not in sys.path:
        sys.path.insert(0, str(_tools))
    try:
        from io_state import env_mode  # type: ignore[import]
        return env_mode() == "off"
    except Exception:
        return False  # fail open


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    if _gate():
        return 0

    # --- Local test direct path (see _warden_cleanroom.py) ---
    import os as _cr_os, sys as _cr_sys
    _cr_sys.path.insert(0, _cr_os.path.dirname(_cr_os.path.abspath(__file__)))
    try:
        from _warden_cleanroom import cleanroom_active as _cr_active, write_gap_journal as _cr_journal
        _active, _tag_required = _cr_active("safe-exec-redirect")
        if _active:
            if _tag_required:
                _cr_journal("safe-exec-redirect", data)
            return 0
    except Exception:
        pass

    tool_name = data.get("tool_name", "")
    if tool_name not in {"Bash", "PowerShell"}:
        return 0

    tool_input = data.get("tool_input", {}) or {}
    command = tool_input.get("command", "").strip()
    if not command:
        return 0

    # Allow patterns take precedence
    if _should_allow(command):
        return 0

    if _uses_workspace_path(command):
        # Truncate for display
        cmd_short = command[:120].replace("\n", " ")
        suffix = "..." if len(command) > 120 else ""
        sys.stderr.write(_EXEC_GUIDANCE_MSG.format(cmd_short=f"{cmd_short}{suffix}"))
        return 2

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        sys.stderr.write(f"safe-exec hook error: {e}\n")
        sys.exit(0)
