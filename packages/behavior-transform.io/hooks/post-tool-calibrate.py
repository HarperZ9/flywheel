#!/usr/bin/env python3
"""post-tool-capture -- PostToolUse hook.

Captures tool results from all tools (Bash, PowerShell, Grep, MCP tools,
Agent, etc.) for local handling.

Flow:
  1. Parse tool_response from the JSON payload.
  2. Extract text (handles str / dict / list shapes).
  3. Run the local text helper when available.
  4. Exit silently.

PostToolUse payload shape:
  {
    "session_id": "...",
    "hook_event_name": "PostToolUse",
    "tool_name": "Bash",
    "tool_input": {...},
    "tool_response": "..." | {...} | [...]
  }
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Cap captured output to avoid overwhelming local handling.
_MAX_CHARS = 40_000


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


def _maybe_journal(data: dict) -> None:
    """Write a gap journal entry if tool response is present."""
    import os
    from pathlib import Path
    bt = os.environ.get("BEHAVIOR_TRANSFORM_TOOLS", "").strip()
    _tools = Path(bt) if bt and Path(bt).is_dir() else Path(__file__).resolve().parents[1] / "tools"
    if str(_tools) not in sys.path:
        sys.path.insert(0, str(_tools))
    try:
        from _warden_cleanroom import write_gap_journal
        if data.get("tool_response"):
            write_gap_journal("post-tool-calibrate", data)
    except Exception:
        pass  # advisory — never block


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
        _active, _tag_required = _cr_active("post-tool-calibrate")
        if _active:
            if _tag_required:
                _cr_journal("post-tool-calibrate", data)
            return 0
    except Exception:
        pass

    # Journal the tool response if present
    _maybe_journal(data)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        sys.stderr.write(f"post-tool-calibrate hook error: {exc}\n")
        sys.exit(0)
