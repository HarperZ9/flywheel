#!/usr/bin/env python
"""safe-input - local input audit hook.

Records prompt-level audit counters for local state and, in strict mode,
returns an opaque revision decision. Default mode exits silently.

Stdin payload:
    {
        "session_id": "...",
        "transcript_path": "...",
        "cwd": "...",
        "permission_mode": "...",
        "hook_event_name": "UserPromptSubmit",
        "prompt": "<operator-typed text>"
    }

Output in strict mode:
    {"decision": "block", "reason": "Input requires revision before processing."}
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path


_TOOLS_CANDIDATES = (
    Path(__file__).resolve().parents[1] / "tools",
)
for _tools_root in _TOOLS_CANDIDATES:
    if _tools_root.is_dir() and str(_tools_root) not in sys.path:
        sys.path.insert(0, str(_tools_root))

from text_rules import collect_text_rules, scan_text_rules  # noqa: E402


_ARCHIVE_ROOT = ".warden-safe-cache/prompts"


def _archive(raw: str, counter: Counter, session_id: str) -> Path | None:
    try:
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
        base = Path.cwd() / _ARCHIVE_ROOT
        base.mkdir(parents=True, exist_ok=True)
        archive = base / f"{digest}.raw"
        archive.write_text(raw, encoding="utf-8")

        sidecar = base / f"{digest}.audit.json"
        sidecar.write_text(
            json.dumps(
                {
                    "session_id": session_id,
                    "audit_counts": dict(counter),
                    "total": sum(counter.values()),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return archive
    except OSError:
        return None


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

    import os as _cr_os, sys as _cr_sys

    _cr_sys.path.insert(0, _cr_os.path.dirname(_cr_os.path.abspath(__file__)))
    try:
        from _warden_cleanroom import cleanroom_active as _cr_active, write_gap_journal as _cr_journal

        active, tag_required = _cr_active("safe-input-calibrate")
        if active:
            if tag_required:
                _cr_journal("safe-input-calibrate", data)
            return 0
    except Exception:
        pass

    prompt = data.get("prompt") or ""
    if not prompt.strip():
        return 0

    session_id = data.get("session_id") or "unknown"

    rules = collect_text_rules(prose_sensitive=True)
    if not rules:
        return 0

    counter, _hits = scan_text_rules(prompt, rules)
    total = sum(counter.values())

    _archive(prompt, counter, session_id)

    if total == 0:
        return 0

    strict = os.environ.get("WARDEN_SAFE_INPUT_STRICT", "").lower() in ("1", "true", "yes")
    if strict and counter.get("T1", 0) > 0:
        sys.stdout.write(
            json.dumps({"decision": "block", "reason": "Input requires revision before processing."})
            + "\n"
        )
        return 0

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        sys.stderr.write(f"safe-input hook error: {exc}\n")
        sys.exit(0)
