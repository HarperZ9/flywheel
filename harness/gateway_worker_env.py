"""Explicit private environment for owned gateway worker children."""
from __future__ import annotations

from pathlib import Path
import os

_KEEP = frozenset(("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT",
                   "PATH", "TEMP", "TMP"))


def minimal_worker_env(repo_root: Path, *, run_root: Path,
                       state_root: Path | None = None) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items()
           if key.upper() in _KEEP}
    home = Path(state_root) if state_root is not None else Path(run_root) / "worker-home"
    profile = home / "worker-profile"
    env.update({
        "PYTHONPATH": str(Path(repo_root)),
        "FLYWHEEL_HOME": str(home),
        "FLYWHEEL_RUN_ROOT": str(Path(run_root)),
        "HOME": str(profile),
        "USERPROFILE": str(profile),
    })
    return env
