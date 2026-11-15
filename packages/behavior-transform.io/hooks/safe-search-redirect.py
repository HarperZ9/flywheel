#!/usr/bin/env python3
"""safe-search - workspace search hook.

Routes search and file-listing requests through the standard workspace
search path.

Grep -> python .../safe_exec.py -- grep -rn <pattern> [<path>]
Glob -> python .../safe_exec.py -- find [<path>] -name "<pattern>"

Trigger: PreToolUse matching "Grep|Glob".
Stdin:   JSON with tool_name + tool_input.
Stdout:  silent on allow.
Stderr:  search guidance on exit 2.

Always allowed:
  * Glob patterns scoped entirely inside .warden-safe-cache/
    (managed workspace output; no extra routing needed).
  * Calls to wrapper infrastructure via Grep
    (safe_*.py and companion tools).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

def _tools_path() -> Path:
    bt = os.environ.get("BEHAVIOR_TRANSFORM_TOOLS", "").strip()
    if bt and Path(bt).is_dir():
        return Path(bt)
    return Path(__file__).resolve().parents[1] / "tools"

_SAFE_EXEC = str(_tools_path() / "safe_exec.py")

_GREP_GUIDANCE_MSG = """\
Use the workspace search command for this pattern:

    python {tool} -- grep -rn "{pattern}" {path_arg}

Options:
    --include-stderr    capture grep stderr (e.g. permission warnings)
    # File-type filter:
    python {tool} -- grep -rn --include="*.py" "{pattern}" {path_arg}

For direct native inspection, ask the operator to enable research or academic mode.
"""

_GLOB_GUIDANCE_MSG = """\
Use the workspace find command for this glob:

    python {tool} -- find {path_arg} -name "{pattern}"

    # Limit depth:
    python {tool} -- find {path_arg} -maxdepth 3 -name "{pattern}"

For direct native inspection, ask the operator to enable research or academic mode.
"""

_CACHE_DIR = ".warden-safe-cache"

_INFRA_PREFIXES = ("safe_", "safe-", "aup_", "aup-")
_INFRA_NAMES = {
    "io_state.py",
    "io_mode.py",
    "channel_router.py",
    "container_ecosystem.py",
}


def _grep_is_infra(pattern: str, path: str) -> bool:
    """True if the grep call is scanning wrapper infrastructure files."""
    p = Path(path) if path else None
    if p and _CACHE_DIR in p.parts:
        return True
    if p and p.name in _INFRA_NAMES:
        return True
    if p and p.name.startswith(_INFRA_PREFIXES) and p.suffix in (".py", ".ps1", ".sh", ".md"):
        return True
    if pattern.strip() in _INFRA_NAMES:
        return True
    if pattern.strip().startswith(_INFRA_PREFIXES):
        return True
    return False


def _glob_is_cache(pattern: str, path: str) -> bool:
    """True if the glob is scoped entirely inside .warden-safe-cache/."""
    p = Path(path) if path else None
    if p and _CACHE_DIR in p.parts:
        return True
    if _CACHE_DIR in pattern:
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
        _active, _tag_required = _cr_active("safe-search-redirect")
        if _active:
            if _tag_required:
                _cr_journal("safe-search-redirect", data)
            return 0
    except Exception:
        pass

    tool_name = data.get("tool_name", "")
    if tool_name not in {"Grep", "Glob"}:
        return 0

    tool_input = data.get("tool_input", {}) or {}

    if tool_name == "Grep":
        pattern = tool_input.get("pattern") or ""
        path    = tool_input.get("path") or "."
        if not pattern:
            return 0
        if _grep_is_infra(pattern, path):
            return 0
        path_arg = f'"{path}"' if path and path != "." else "."
        sys.stderr.write(_GREP_GUIDANCE_MSG.format(
            tool=_SAFE_EXEC,
            pattern=pattern.replace('"', '\\"'),
            path_arg=path_arg,
        ))
        return 2

    if tool_name == "Glob":
        pattern = tool_input.get("pattern") or ""
        path    = tool_input.get("path") or "."
        if not pattern:
            return 0
        if _glob_is_cache(pattern, path):
            return 0
        path_arg = f'"{path}"' if path and path != "." else "."
        sys.stderr.write(_GLOB_GUIDANCE_MSG.format(
            tool=_SAFE_EXEC,
            pattern=pattern.replace('"', '\\"'),
            path_arg=path_arg,
        ))
        return 2

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        sys.stderr.write(f"safe-search hook error: {exc}\n")
        sys.exit(0)
