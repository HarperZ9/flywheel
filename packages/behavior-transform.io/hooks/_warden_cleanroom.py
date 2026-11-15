#!/usr/bin/env python3
"""_warden_cleanroom.py - shared local direct-path state.

This governs ONLY local routing/session hooks:
    safe-read-redirect, post-tool-calibrate, safe-input-calibrate,
    authority-pill-session-start, session-start-calibrate, corpus-preverify

It does NOT govern genuine safety hooks (block-secrets, check-branch,
verify-no-secrets, lint-on-save) - those stay armed in every state.

Mode authority is now unified through io_state.env_mode().
"""
from __future__ import annotations

import json
import os
from pathlib import Path

SENTINEL = Path.home() / ".claude" / ".warden-cleanroom"
CONFIG = Path.home() / ".claude" / "cleanroom.json"

GOVERNED_HOOKS = (
    "safe-read-redirect",
    "post-tool-calibrate",
    "safe-input-calibrate",
    "authority-pill-session-start",
    "session-start-calibrate",
    "corpus-preverify",
)

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def _env_state():
    """Return True/False from WARDEN_CLEANROOM, or None if unset/unrecognised."""
    v = os.environ.get("WARDEN_CLEANROOM", "").strip().lower()
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    return None


def load_config() -> dict:
    try:
        data = json.loads(CONFIG.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


_AUDIT_JOURNAL = Path.home() / ".claude" / ".warden-audit.jsonl"


def _gap_state(cfg: dict) -> bool:
    """True if GAP accountability mode is active (audit tag required)."""
    env = os.environ.get("WARDEN_GAP_MODE", "").strip().lower()
    if env in _TRUE:
        return True
    if env in _FALSE:
        return False
    return bool(cfg.get("gap_mode", False))


def cleanroom_active(hook_name: str = "") -> tuple[bool, bool]:
    """Return (armed, tag_required) derived from io_state mode authority.

    Both values match — armed when mode is 'on', disarmed when 'off'.
    write_gap_journal() remains for GAP-category audit trail.
    """
    import os
    import sys
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
        armed = env_mode() == "on"
        return armed, armed
    except Exception:
        return True, True  # fail closed


def write_gap_journal(hook_name: str, data: dict) -> None:
    """Append a GAP accountability record to the audit journal (JSON-L)."""
    import datetime as _dt
    tool_input = data.get("tool_input") or {}
    entry = {
        "ts": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hook": hook_name,
        "session_id": data.get("session_id") or "unknown",
        "tool_name": data.get("tool_name") or "",
        "subject": (
            tool_input.get("file_path")
            or tool_input.get("url")
            or tool_input.get("query")
            or (tool_input.get("command") or "")[:120]
            or (data.get("prompt") or "")[:120]
            or ""
        ),
        "gap_mode": True,
    }
    try:
        with _AUDIT_JOURNAL.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass
