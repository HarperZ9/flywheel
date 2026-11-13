"""workspace_paths.py -- which paths of a project the guard reads, and where git lives.

`protected(root)` names the guarded paths: every git folder's `hooks` and
`config`, and the session's own permission, hook and MCP files. Paths inside
the project are relative; paths of a linked worktree's repository, which sit
outside the project, are absolute.

Git folders are found by walking `.git/modules` for directories that hold a
`HEAD` file, so a submodule named `libs/a` and a submodule of a submodule
(`modules/a/modules/b`) are both found. The walk stops at MAX_DEPTH levels
and MAX_GIT_DIRS folders. A project past either cap is reported as `capped`,
and the caller keeps it read-only to commands: a hook folder the guard did
not read is one it cannot put back.

A linked worktree (`.git` is a file) keeps its index in an admin folder inside
the main repository, and its objects and refs in that repository's common
folder. `linked_git` resolves both. `opened` lists what git has to write for
`git add` and `git commit`: the admin folder, and `objects`, `refs` and `logs`
of the common folder. The common folder itself, with its hooks and config,
stays closed.
"""
from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

#: Files the session reads to decide what it may run. Any change is put back.
CONTROL_FILES = (".flywheel/permissions.json", ".flywheel/hooks.json",
                 ".flywheel/mcp.json", ".mcp.json")
MAX_DEPTH = 8
MAX_GIT_DIRS = 128
#: Windows reparse tags for a symbolic link and a junction.
_LINK_TAGS = frozenset({0xA000000C, 0xA0000003})
#: Hosts whose usual filesystem treats `Pre-Commit` and `pre-commit` as one file.
FOLDS = sys.platform in ("win32", "darwin")


def fold(key: str) -> str:
    """The form two names are compared in: lower case where the host folds case."""
    return key.lower() if FOLDS else key


def is_link(path) -> bool:
    """A symlink or a Windows junction: a name whose content lives elsewhere."""
    try:
        info = os.lstat(path)
    except OSError:
        return False
    return stat.S_ISLNK(info.st_mode) or getattr(info, "st_reparse_tag", 0) in _LINK_TAGS


def git_dirs(root) -> tuple:
    """(relative git folders under `root`, whether a cap was hit)."""
    found, capped = [".git"], False
    modules = Path(root) / ".git" / "modules"
    for folder, dirs, files in os.walk(modules):
        here = Path(folder)
        depth = len(here.relative_to(modules).parts)
        dirs[:] = sorted(d for d in dirs if not is_link(here / d))
        if depth and "HEAD" in files:
            found.append(here.relative_to(root).as_posix())
            dirs[:] = [d for d in dirs if d == "modules"]
        if depth >= MAX_DEPTH and dirs:
            capped, dirs[:] = True, []
        if len(found) > MAX_GIT_DIRS:
            return found[:MAX_GIT_DIRS], True
    return found, capped


def linked_git(root) -> "tuple | None":
    """(admin folder, common folder) for a checkout whose `.git` is a file."""
    dot = Path(root) / ".git"
    try:
        if not dot.is_file() or dot.stat().st_size > 4096:
            return None
        first = dot.read_text(encoding="utf-8", errors="replace").splitlines()[0]
        if not first.startswith("gitdir:"):
            return None
        admin = (Path(root) / first[len("gitdir:"):].strip()).resolve()
        pointer = admin / "commondir"
        common = ((admin / pointer.read_text(encoding="utf-8").strip()).resolve()
                  if pointer.is_file() else admin)
    except (OSError, IndexError):
        return None
    if not (admin / "HEAD").is_file() or not (common / "objects").is_dir():
        return None
    return admin, common


def protected(root) -> dict:
    """The guarded paths of `root` by kind, plus `opened` and `capped`."""
    root = Path(root)
    dirs, capped = git_dirs(root)
    hooks = [f"{d}/hooks" for d in dirs]
    configs = [f"{d}/{name}" for d in dirs for name in ("config", "config.worktree")]
    control, opened = list(CONTROL_FILES), []
    if (root / ".git").is_file():
        control.append(".git")
    linked = linked_git(root)
    if linked is not None:
        admin, common = linked
        hooks.append((common / "hooks").as_posix())
        configs += [(common / "config").as_posix(), (admin / "config.worktree").as_posix()]
        opened = [admin] + ([common / name for name in ("objects", "refs", "logs")
                             if (common / name).is_dir()] if common != admin else [])
    return {"hooks": tuple(hooks), "configs": tuple(configs), "control": tuple(control),
            "opened": tuple(str(path) for path in opened), "capped": capped}


def merged(first: dict, second: dict) -> dict:
    """Two `protected` results as one, so a path seen either time is checked."""
    out = {key: tuple(dict.fromkeys(first.get(key, ()) + second[key]))
           for key in ("hooks", "configs", "control", "opened")}
    out["capped"] = bool(first.get("capped")) or second["capped"]
    return out
