"""The environment a frozen build's bundled lane child starts with.

A bundled lane runs as a self-child of the engine executable with a small fixed
environment instead of the engine's whole one. The base set is what a Windows or
POSIX process needs to start and find its temp and profile folders, with PATH cut
to the system folder so a lane cannot pick up an arbitrary tool from the user's
PATH. On top of that base the child gets:

  - FLYWHEEL_HOME, resolved, so the lane and the engine agree on one home;
  - PYTHONUTF8=1 and PYTHONIOENCODING=utf-8, so a lane that prints non-ASCII
    text to a pipe does not fail on the Windows code page;
  - the folder holding git, appended to PATH only for a lane whose tool table
    lists ``git`` in some tool's ``needs`` (index today), since index shells
    out to git for branch and history. Every other lane keeps the system PATH.

Git comes from ``tool_discovery.find_git``, the finder the Git setup item reads
(FLYWHEEL_GIT, the registry user and machine PATH, the engine PATH, Program
Files), so the card and the child agree. Only three kinds of folder join a
PATH: the folder FLYWHEEL_GIT names, a Git for Windows ``cmd`` folder, and
``%ProgramFiles%\\Git\\cmd``. A shim folder that happens to hold a git (scoop
shims, a user bin folder) never joins, since it would expose every tool in it,
the claude and codex CLIs included, to the lane.

TEMP, TMP and the app-data folders are replaced with folders inside the lane
folder where the lane registry row is known (lane_workdir.pin_lane_workdir).
The lane's declared names, the operator's env_allow grant and the lane folder
join there too (lane_env.confine_lane_launch). A provider key joins only per
call, through a bound credential slot (lane_credentials.py).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Mapping

from .lane_workdir import flywheel_home

_UNSET = object()
_WINDOWS_BASE = frozenset((
    "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "SYSTEMDRIVE",
    "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA"))
_POSIX_BASE = frozenset(("LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "TEMP", "TMP"))
UTF8_ENV = (("PYTHONIOENCODING", "utf-8"), ("PYTHONUTF8", "1"))


def lane_needs_git(lane: str | None) -> bool:
    """True when some tool in the lane's table needs the ``git`` setup item."""
    from .lane_tool_policy import lane_policy
    return bool(lane) and any("git" in entry.needs for entry in lane_policy(lane).values())


def bundled_child_environment(
        environ: Mapping[str, str], *, platform: str = os.name,
        git_dir: object = _UNSET, lane: str | None = None) -> dict[str, str]:
    """Return the base environment passed to a bundled lane child.

    The Git folder joins PATH only when ``lane`` needs git. ``git_dir``
    injects it (``None`` for not found); left unset, it is discovered."""
    if platform == "nt":
        env = {key: str(value) for key, value in environ.items()
               if key.upper() in _WINDOWS_BASE}
        root = env.get("SYSTEMROOT") or env.get("WINDIR") or "C:/Windows"
        env["PATH"] = str(Path(root) / "System32").replace("\\", "/")
    else:
        env = {key: str(value) for key, value in environ.items()
               if key in _POSIX_BASE}
        env["PATH"] = os.defpath
    env["FLYWHEEL_HOME"] = str(flywheel_home(environ))
    env.update(UTF8_ENV)
    if not lane_needs_git(lane):
        return env
    folder = (git_directory(environ, platform=platform)
              if git_dir is _UNSET else git_dir)
    if folder:
        env["PATH"] = append_path_dir(env["PATH"], str(folder), platform)
    return env


def append_path_dir(path: str, folder: str, platform: str = os.name) -> str:
    """``path`` with ``folder`` appended once."""
    sep = ";" if platform == "nt" else ":"
    parts = [part for part in path.split(sep) if part]
    if folder in parts:
        return path
    return sep.join([*parts, folder])


def git_directory(environ: Mapping[str, str], *, platform: str = os.name,
                  read_registry_path: Callable[[str], str | None] | None = None
                  ) -> str | None:
    """The accepted folder holding git, or None. Nothing is executed."""
    from .tool_discovery import find_git, registry_path
    found = find_git(environ, read_registry_path=read_registry_path or registry_path,
                     platform=platform)
    if not found.found or not found.path:
        return None
    folder = Path(found.path).parent
    if found.source == "FLYWHEEL_GIT" or platform != "nt" or _git_for_windows(folder):
        return str(folder)
    return None


def _git_for_windows(folder: Path) -> bool:
    """A Git for Windows ``cmd`` folder: named cmd, beside the install's
    mingw64 or usr folder, or inside a folder named Git."""
    if folder.name.lower() != "cmd":
        return False
    parent = folder.parent
    return (parent.name.lower() == "git" or (parent / "mingw64").is_dir()
            or (parent / "usr" / "bin").is_dir())


def _get(environ: Mapping[str, str], name: str) -> str:
    for key, value in environ.items():
        if isinstance(key, str) and key.upper() == name:
            return str(value)
    return ""
