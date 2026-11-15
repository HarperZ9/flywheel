#!/usr/bin/env python3
"""session-start-maintain -- SessionStart hook.

Every session launch triggers this hook in three steps:

  1. Background workstation maintenance -- launch the local maintenance
     worker as a detached process.
     Skipped if a run completed within the last STALE_HOURS hours.

  2. Memory maintenance -- run the local memory helper when available.

  3. Context maintenance -- run the local context helper when available.

All steps fail open; a broken sub-tool must never break session start.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

_MEMORY_DIR = Path.home() / ".claude" / "projects" / "default" / "memory"
_STATUS_FILE = Path.home() / ".warden-safe-cache" / "workstation-maintenance.json"
_LEGACY_STATUS_FILE = Path.home() / ".warden-safe-cache" / "workstation-calibration.json"

STALE_HOURS = 4  # Re-launch background maintenance if last run was older than this.


def _maintenance_is_stale() -> bool:
    status_file = _status_file()
    if status_file is None:
        return True
    try:
        age_hours = (time.time() - status_file.stat().st_mtime) / 3600
        return age_hours > STALE_HOURS
    except OSError:
        return True


def _status_file() -> Path | None:
    for path in (_STATUS_FILE, _LEGACY_STATUS_FILE):
        if path.is_file():
            return path
    return None


def _run_sync(args: list[str], timeout: int = 60) -> str:
    try:
        result = subprocess.run(
            args, capture_output=True, timeout=timeout, cwd=str(Path.home()),
        )
        return result.stdout.decode("utf-8", "replace").strip()
    except (subprocess.SubprocessError, OSError):
        return ""


def _summary_line(out: str, keywords: tuple) -> str:
    for ln in out.splitlines():
        if any(k in ln for k in keywords):
            return ln.strip()
    return ""


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


def _mode_status() -> None:
    """Print current mode and profile to stderr."""
    import os
    from pathlib import Path
    bt = os.environ.get("BEHAVIOR_TRANSFORM_TOOLS", "").strip()
    _tools = Path(bt) if bt and Path(bt).is_dir() else Path(__file__).resolve().parents[1] / "tools"
    if str(_tools) not in sys.path:
        sys.path.insert(0, str(_tools))
    try:
        from io_state import env_mode, env_profile
        mode = env_mode()
        profile = env_profile()
        sys.stderr.write(f"behavior-transform: mode={mode} profile={profile}\n")
    except Exception as exc:
        sys.stderr.write(f"behavior-transform: session-start warning: {exc}\n")


def main() -> int:
    # --- Local direct path (see _warden_cleanroom.py) ---
    import os as _cr_os, sys as _cr_sys
    _cr_sys.path.insert(0, _cr_os.path.dirname(_cr_os.path.abspath(__file__)))
    try:
        from _warden_cleanroom import cleanroom_active as _cr_active
        if _cr_active("session-start-calibrate")[0]:
            return 0
    except Exception:
        pass
    
    if _gate():
        return 0
    
    try:
        sys.stdin.read()
    except Exception:
        pass

    # Call mode status to report current state
    _mode_status()

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
