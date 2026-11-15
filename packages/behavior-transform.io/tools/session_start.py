#!/usr/bin/env python3
"""Native fail-open SessionStart hook for behavior-transform.io.

Session startup never depends on a shell profile or mutates the workspace.
The IO calibration layer owns all transforms; this hook only reports the
current IO mode/profile and exits successfully even when diagnostics are
unavailable.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

TOOLS_ROOT = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_ROOT.parent

if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))


def _load_io_state():
    try:
        import io_state

        return io_state
    except Exception:
        return None


def _precommit_status() -> str:
    hook = REPO_ROOT / ".git" / "hooks" / "pre-commit"
    return "installed" if hook.is_file() else "missing"


def _context(surface: str) -> str:
    io_state = _load_io_state()
    if io_state is None:
        io_mode = "unknown"
        io_profile = "unknown"
        io_state_file = None
    else:
        io_mode = io_state.env_mode()
        io_profile = io_state.env_profile()
        io_state_file = str(io_state.state_file_path())

    lines = [
        "behavior-transform.io native session layer active.",
        f"  Surface       : {surface}",
        f"  IO mode       : {io_mode}",
        f"  IO profile    : {io_profile}",
        f"  IO state file : {io_state_file or 'unavailable'}",
        f"  Pre-commit    : {_precommit_status()}",
        "",
        "SessionStart is diagnostic-only; filesystem, network, subprocess, and tool",
        "payload transforms are owned by the native IO calibration layer.",
    ]
    return "\n".join(lines)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Emit native behavior-transform.io session context."
    )
    parser.add_argument("--surface", default="codex", help="Calling surface label.")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        payload = {"additionalContext": _context(args.surface)}
    except Exception as exc:
        payload = {
            "additionalContext": (
                "behavior-transform.io native session layer fail-open.\n"
                f"  Surface       : {args.surface}\n"
                f"  Diagnostic    : {type(exc).__name__}: {exc}"
            )
        }
    sys.stdout.write(json.dumps(payload) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
