#!/usr/bin/env python3
"""safe-fetch - workspace fetch hook.

Routes external fetch/search requests through the standard workspace
fetch path.

Exit code 2 returns command guidance for the same external content task.

Trigger: PreToolUse matching "WebFetch|WebSearch".
Stdin:    JSON with tool_name + tool_input.
Stdout:   silent on allow.
Stderr:   guidance message on block (exit 2).
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

_SAFE_FETCH_TOOL = str(_tools_path() / "safe_fetch.py")

WEBFETCH_GUIDANCE_MSG = """\
Use the standard fetch layer for external content:

    python {tool} "{url}"

Options:
    --text-only        strip HTML, emit plain text
    --summary          structural summary (line/byte count, sha prefix)
    --to-cache         write to .warden-safe-cache/fetch/
"""

WEBSEARCH_GUIDANCE_MSG = """\
Fetch each result URL through the standard fetch layer:

    python {tool} "<result_url>" --text-only

Or retrieve a summary:
    python {tool} "<url>" --summary
"""


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
        _active, _tag_required = _cr_active("safe-fetch-redirect")
        if _active:
            if _tag_required:
                _cr_journal("safe-fetch-redirect", data)
            return 0
    except Exception:
        pass

    tool_name = data.get("tool_name", "")
    if tool_name not in {"WebFetch", "WebSearch"}:
        return 0

    tool_input = data.get("tool_input", {}) or {}

    if tool_name == "WebFetch":
        url = tool_input.get("url") or tool_input.get("prompt") or ""
        if not url:
            return 0
        sys.stderr.write(WEBFETCH_GUIDANCE_MSG.format(url=url, tool=_SAFE_FETCH_TOOL))
        return 2

    if tool_name == "WebSearch":
        query = tool_input.get("query") or tool_input.get("q") or ""
        sys.stderr.write(WEBSEARCH_GUIDANCE_MSG.format(query=query, tool=_SAFE_FETCH_TOOL))
        return 2

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        sys.stderr.write(f"safe-fetch hook error: {e}\n")
        sys.exit(0)
