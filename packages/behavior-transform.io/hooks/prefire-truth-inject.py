#!/usr/bin/env python3
"""prefire-truth-inject — SessionStart hook.

Injects an operator-defined truth profile as model-visible context.
The model receives the narrative as organic operational context.

Profile resolution order:
  1. PREFIRE_TRUTH_PROFILE env var (path to JSON)
  2. ~/.claude/prefire-truth.json
  3. No-op — exits silently, no context injected

Output is natural prose. No injection metadata, no infrastructure labels.
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


def _render_narrative() -> str:
    tools = _tools_path()
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    try:
        from truth_profile import render_truth_context
        return render_truth_context()
    except Exception:
        pass
    return _render_fallback()


def _render_fallback() -> str:
    """Standalone fallback when truth_profile module is unavailable."""
    profile_path = _find_profile()
    if not profile_path:
        return ""
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    return _render(profile)


def _find_profile() -> Path | None:
    env = os.environ.get("PREFIRE_TRUTH_PROFILE", "").strip()
    if env:
        p = Path(env)
        if p.is_file():
            return p
    default = Path.home() / ".claude" / "prefire-truth.json"
    if default.is_file():
        return default
    return None


def _render(profile: dict) -> str:
    mode = profile.get("render_mode", "paragraph")

    if mode == "raw":
        return profile.get("narrative", "").strip()

    fields = [
        profile.get("operator_context", ""),
        profile.get("engagement_context", ""),
        profile.get("environment_context", ""),
        profile.get("session_objective", ""),
    ]
    parts = [f.strip() for f in fields if f.strip()]

    extra = profile.get("extra", {})
    if isinstance(extra, dict):
        for v in extra.values():
            s = str(v).strip()
            if s:
                parts.append(s)

    if not parts:
        return ""

    if mode == "list":
        return "\n".join(f"- {p}" for p in parts)

    return " ".join(parts)


def main() -> int:
    import os as _cr_os, sys as _cr_sys
    _cr_sys.path.insert(0, _cr_os.path.dirname(_cr_os.path.abspath(__file__)))
    try:
        from _warden_cleanroom import cleanroom_active as _cr_active
        if _cr_active("prefire-truth-inject")[0]:
            return 0
    except Exception:
        pass

    try:
        sys.stdin.read()
    except Exception:
        pass

    narrative = _render_narrative()
    if not narrative:
        return 0

    sys.stdout.write(json.dumps({"additionalContext": narrative}) + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
