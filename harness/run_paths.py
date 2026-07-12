"""run_paths.py — portable default for the training/run root, so the shipped
source carries no build-machine absolute path (the shipped-posture rule: no
C:\\ or E:\\ on a product surface).

Resolution order, first hit wins:
  1. FLYWHEEL_RUN_ROOT environment variable.
  2. a `.flywheel-run-root` marker file at the repo root (gitignored, never
     shipped) whose single line is the run root. This lets a specific machine
     (e.g. one with an external drive) keep its real path with zero env setup,
     while the published source stays clean.
  3. a portable per-user default under the home directory.

Zero dependencies.
"""
from __future__ import annotations

import os
from pathlib import Path

_MARKER = Path(__file__).resolve().parent.parent / ".flywheel-run-root"


def run_root_default() -> str:
    """The default training/run root, with no absolute build-machine path baked
    into the source. Callers may still override via --run-root or an argument."""
    env = os.environ.get("FLYWHEEL_RUN_ROOT")
    if env:
        return env
    try:
        if _MARKER.is_file():
            val = _MARKER.read_text(encoding="utf-8").strip()
            if val:
                return val
    except OSError:
        pass
    return str(Path.home() / ".flywheel" / "run")
