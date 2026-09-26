"""The environment a frozen build's bundled lane child starts with.

A bundled lane runs as a self-child of the engine executable with a small fixed
environment instead of the engine's whole one. The base set is what a Windows or
POSIX process needs to start and find its temp and profile folders, with PATH cut
to the system folder so a lane cannot pick up an arbitrary tool from the user's
PATH. On top of that base the child gets:

  - FLYWHEEL_HOME, resolved, so the lane and the engine agree on one home;
  - PYTHONUTF8=1 and PYTHONIOENCODING=utf-8, so a lane that prints non-ASCII
    text to a pipe does not fail on the Windows code page;
  - the folder holding git, appended to PATH when one is found, since the index
    lane shells out to git for branch and history.

Git is found in this order: FLYWHEEL_GIT (a git executable or its folder; the
value ``none`` means not found), git on the engine's PATH, then
``%ProgramFiles%\\Git\\cmd\\git.exe`` on Windows. Reading the user and machine
PATH from the registry belongs to the tool discovery module, which can replace
this lookup.

The lane's declared names, the operator's env_allow grant and the lane folder
join later, where the lane registry row is known (lane_env.confine_lane_launch).
A provider key joins only per call, through a bound credential slot
(lane_credentials.py).
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Callable, Mapping

from .lane_workdir import flywheel_home

_UNSET = object()
_WINDOWS_BASE = frozenset((
    "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "SYSTEMDRIVE",
    "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA"))
_POSIX_BASE = frozenset(("LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "TEMP", "TMP"))
UTF8_ENV = (("PYTHONIOENCODING", "utf-8"), ("PYTHONUTF8", "1"))


def bundled_child_environment(
        environ: Mapping[str, str], *, platform: str = os.name,
        git_dir: object = _UNSET) -> dict[str, str]:
    """Return the base environment passed to a bundled lane child.

    ``git_dir`` injects the Git folder (``None`` for not found); left unset, it
    is discovered from ``environ``."""
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


def git_directory(environ: Mapping[str, str], *,
                  which: Callable[..., str | None] = shutil.which,
                  platform: str = os.name) -> str | None:
    """The folder holding git, or None. Nothing is executed."""
    pinned = _get(environ, "FLYWHEEL_GIT")
    if pinned:
        return None if pinned.strip().lower() == "none" else _git_folder(pinned)
    found = which("git", path=_get(environ, "PATH") or "")
    if found:
        return str(Path(found).parent)
    program_files = _get(environ, "PROGRAMFILES")
    if platform == "nt" and program_files:
        return _git_folder(str(Path(program_files) / "Git" / "cmd" / "git.exe"))
    return None


def _git_folder(value: str) -> str | None:
    path = Path(os.path.expanduser(value))
    if path.is_dir():
        for name in ("git.exe", "git"):
            if (path / name).is_file():
                return str(path)
        return None
    return str(path.parent) if path.is_file() else None


def _get(environ: Mapping[str, str], name: str) -> str:
    for key, value in environ.items():
        if isinstance(key, str) and key.upper() == name:
            return str(value)
    return ""
