"""workspace_guard.py -- the paths inside a project a command may not change.

A coding session lets a sandboxed command write inside the project folder.
The kernel keeps that command inside the folder. It cannot tell an ordinary
file from one that starts a program later, outside the sandbox, as the user:

  .git/hooks/                 git runs these on commit, checkout, merge, push
  .git/config                 can name programs git starts (see git_config_guard)
  .flywheel/permissions.json  the session's own allow and deny rules
  .flywheel/hooks.json        commands the session runs outside the sandbox
  .flywheel/mcp.json, .mcp.json   servers the session starts outside it

So those paths are read before the command runs and compared after it. A
change is put back, byte for byte, and the run is reported as refused. The
check compares content by path, which is why a command that renames `.git`
aside and builds a new one in its place gains nothing: the new hooks file is
still a hooks file that was not there before.

Two exceptions keep git usable. A new `*.sample` file in a hooks folder is
allowed, because `git init` writes them and git never runs them. Additions to
a git config are allowed when every added entry is on the allowlist in
`git_config_guard`.

This is a check after the fact. Between the write and the check the changed
file is on disk, and a git command the user starts in that moment would see
it. The platform backends narrow that window by making the paths that already
exist read-only to the command; see `Workspace.kernel_paths`.
"""
from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

from .git_config_guard import strip_unsafe, unsafe_additions

__all__ = ["CONTROL_FILES", "protected", "snapshot", "verify"]

#: Files the session reads to decide what it may run. Any change is put back.
CONTROL_FILES = (".flywheel/permissions.json", ".flywheel/hooks.json",
                 ".flywheel/mcp.json", ".mcp.json")
#: Beyond this size a file is remembered by presence only and cannot be put back.
MAX_KEEP = 1 << 20
MAX_MODULES = 64


def protected(root) -> dict:
    """The guarded paths under `root`, relative, by kind.

    Submodule git folders are included one level down, because a hook in
    `.git/modules/<name>/hooks` runs the same way the top one does.
    """
    hooks, configs = [".git/hooks"], [".git/config", ".git/config.worktree"]
    modules = Path(root) / ".git" / "modules"
    try:
        names = sorted(p.name for p in modules.iterdir() if p.is_dir())[:MAX_MODULES]
    except OSError:
        names = []
    for name in names:
        hooks.append(f".git/modules/{name}/hooks")
        configs.append(f".git/modules/{name}/config")
    return {"hooks": tuple(hooks), "configs": tuple(configs), "control": CONTROL_FILES}


#: Windows reparse tags for a symbolic link and a junction.
_LINK_TAGS = frozenset({0xA000000C, 0xA0000003})


def _is_link(path: Path) -> bool:
    """A symlink or a Windows junction: a name whose content lives elsewhere."""
    try:
        info = os.lstat(path)
    except OSError:
        return False
    return stat.S_ISLNK(info.st_mode) or getattr(info, "st_reparse_tag", 0) in _LINK_TAGS


def _links(root: Path, rel: str) -> list:
    """Each leading part of `rel` that is a link, shortest first."""
    found, here = [], root
    for part in rel.split("/"):
        here = here / part
        if _is_link(here):
            found.append(here.relative_to(root).as_posix())
    return found


def _read(path: Path):
    """The file's bytes, or a digest when it is too large to keep."""
    try:
        if path.stat().st_size > MAX_KEEP:
            with path.open("rb") as handle:
                return ("sha256", hashlib.file_digest(handle, "sha256").hexdigest())
        return path.read_bytes()
    except OSError as exc:
        return ("unreadable", type(exc).__name__)


def _hook_files(root: Path, rel: str) -> dict:
    files, base = {}, root / rel
    for folder, dirs, names in os.walk(base):
        dirs[:] = [d for d in dirs if not _is_link(Path(folder) / d)]
        for name in names:
            path = Path(folder) / name
            files[path.relative_to(root).as_posix()] = (
                b"" if _is_link(path) else _read(path))
    return files


def snapshot(root) -> dict:
    """What the guarded paths hold now: file bytes by path, and which are links."""
    root, paths = Path(root), protected(root)
    state = {"paths": paths, "links": set(), "hooks": {}, "files": {}}
    for rel in paths["hooks"] + paths["configs"] + paths["control"]:
        state["links"].update(_links(root, rel))
    for rel in paths["hooks"]:
        state["hooks"].update(_hook_files(root, rel))
    for rel in paths["configs"] + paths["control"]:
        if (root / rel).is_file():
            state["files"][rel] = _read(root / rel)
    return state


def _remove(path: Path) -> None:
    """Remove a file, link or junction without following it."""
    for call in (os.unlink, os.rmdir):
        try:
            call(path)
            return
        except OSError:
            continue


def _put_back(root: Path, rel: str, data: bytes) -> None:
    """Write `data` at `rel` without following a link left at that name."""
    path = root / rel
    _remove(path)
    if path.parent.exists() and not path.parent.is_dir():
        _remove(path.parent)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _restore(root: Path, rel: str, data, what: str) -> list:
    """Put the earlier bytes back and name what happened, including a failure."""
    if not isinstance(data, bytes):      # too large to keep: say so, never guess
        return [f"{rel}: {what}, too large to put back"]
    try:
        _put_back(root, rel, data)
    except OSError as exc:
        return [f"{rel}: {what}, could not put back ({type(exc).__name__})"]
    return [f"{rel}: {what}, put back"]


def _drop_new_links(root: Path, before: dict, paths: dict) -> list:
    """Remove any link the run planted on the way to a guarded path."""
    problems = []
    for rel in paths["hooks"] + paths["configs"] + paths["control"]:
        for link in _links(root, rel):
            if link not in before["links"]:
                _remove(root / link)
                problems.append(f"{link}: replaced by a link, link removed")
    return problems


def _check_hooks(root: Path, before: dict, now: dict) -> list:
    problems = []
    for rel, data in now["hooks"].items():
        if rel not in before["hooks"]:
            if not rel.endswith(".sample"):
                _remove(root / rel)
                problems.append(f"{rel}: added, removed")
        elif data != before["hooks"][rel]:
            problems += _restore(root, rel, before["hooks"][rel], "changed")
    for rel, data in before["hooks"].items():
        if rel not in now["hooks"]:
            problems += _restore(root, rel, data, "deleted")
    return problems


def _check_files(root: Path, before: dict, now: dict, paths: dict) -> list:
    problems = []
    for rel in paths["configs"] + paths["control"]:
        old, new = before["files"].get(rel), now["files"].get(rel)
        had, has = rel in before["files"], rel in now["files"]
        if had and not has:
            problems += _restore(root, rel, old, "deleted")
        elif has and rel in paths["configs"]:
            problems += _check_config(root, rel, old if had else None, new, had)
        elif has and (not had or new != old):
            if had:
                problems += _restore(root, rel, old, "changed")
            else:
                _remove(root / rel)
                problems.append(f"{rel}: added, removed")
    return problems


def _check_config(root: Path, rel: str, old, new, had: bool) -> list:
    if new == old:
        return []
    if not isinstance(new, bytes):
        return [f"{rel}: changed, too large to check"]
    bad = unsafe_additions(old if isinstance(old, bytes) else None, new)
    if not bad:
        return []
    names = ", ".join(bad[:6])
    if had and isinstance(old, bytes):
        return _restore(root, rel, old, f"added {names}")
    return _restore(root, rel, strip_unsafe(new), f"added {names}")


def verify(root, before: dict) -> list:
    """Compare the guarded paths with `before` and put back what changed.

    Returns one line per change. An empty list means the run left every
    guarded path as it found it, apart from the two allowed exceptions.
    """
    root = Path(root)
    paths = protected(root)
    merged = {key: tuple(dict.fromkeys(before["paths"][key] + paths[key]))
              for key in paths}
    problems = _drop_new_links(root, before, merged)
    now = snapshot(root)
    problems += _check_hooks(root, before, now)
    problems += _check_files(root, before, now, merged)
    return problems
