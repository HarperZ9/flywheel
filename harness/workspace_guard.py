"""workspace_guard.py -- the paths inside a project a command may not change.

A coding session lets a sandboxed command write inside the project folder.
The kernel keeps that command inside the folder. It cannot tell an ordinary
file from one that starts a program later, outside the sandbox, as the user:

  <git folder>/hooks/         git runs these on commit, checkout, merge, push
  <git folder>/config         can name programs git starts (see git_config_guard)
  .flywheel/permissions.json  the session's own allow and deny rules
  .flywheel/hooks.json        commands the session runs outside the sandbox
  .flywheel/mcp.json, .mcp.json   servers the session starts outside it
  .git, when it is a file     says which repository a linked worktree uses

`workspace_paths.protected` lists them. They are read before the command runs
and compared after it. A change is put back and the run is reported as
refused. The check compares content by path, so a command that renames `.git`
aside and builds a new one in its place gains nothing.

Putting back means the same bytes, the same permission bits (a hook keeps its
executable bit) and, for a name that was a link, a link to the same target.
A file larger than MAX_KEEP (1 MiB) is remembered by its sha256 only: a
change to it is seen and cannot be undone. Anything that cannot be undone is
listed in `Problems.failed`, and the caller then holds the project read-only.

Two exceptions keep git usable. A new `*.sample` file in a hooks folder is
allowed, because `git init` writes them and git never runs them. Additions to
a git config are allowed when every added entry is on the allowlist in
`git_config_guard`. A hooks folder named by `core.hooksPath`, such as
`.husky/`, is ordinary project content and is not guarded here.

This is a check after the fact. Between the write and the check the changed
file is on disk, and a git command the user starts in that moment would see
it. The platform backends narrow that window by making the paths that already
exist read-only to the command; see `Workspace.kernel_paths`.
"""
from __future__ import annotations

import hashlib
import logging
import os
import stat
from pathlib import Path

from .git_config_guard import strip_unsafe, unsafe_additions
from .workspace_paths import CONTROL_FILES, fold, is_link, merged, protected

__all__ = ["CONTROL_FILES", "MAX_KEEP", "Problems", "protected", "snapshot", "verify"]

log = logging.getLogger(__name__)
#: Beyond this size a file is remembered by digest and cannot be put back.
MAX_KEEP = 1 << 20
_is_link = is_link


class Problems(list):
    """One line per change. `failed` holds the lines for what was not undone."""

    def __init__(self):
        super().__init__()
        self.failed = []

    def add(self, line: str, failed: bool = False) -> None:
        self.append(line)
        if failed:
            self.failed.append(line)


def _key(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _target(path: Path) -> tuple:
    try:
        return os.readlink(path), os.path.isdir(path)
    except OSError as exc:
        return f"?{type(exc).__name__}", False


def _entry(path: Path, name: str) -> tuple:
    """(name, kind, data, mode) for what is at `path` now."""
    if is_link(path):
        return name, "link", _target(path), 0
    try:
        info = path.stat()
        mode = stat.S_IMODE(info.st_mode)
        if info.st_size > MAX_KEEP:
            with path.open("rb") as handle:
                return name, "big", hashlib.file_digest(handle, "sha256").hexdigest(), mode
        return name, "file", path.read_bytes(), mode
    except OSError as exc:
        return name, "unreadable", type(exc).__name__, 0


def _links(root: Path, rel: str, leaf: bool) -> list:
    """Each folder on the way to `rel` that is a link, shortest first."""
    if os.path.isabs(rel):
        return [rel] if leaf and is_link(Path(rel)) else []
    found, here, parts = [], root, rel.split("/")
    for part in parts if leaf else parts[:-1]:
        here = here / part
        if is_link(here):
            found.append(here.relative_to(root).as_posix())
    return found


def _link_map(root: Path, paths: dict) -> dict:
    pairs = [(rel, True) for rel in paths["hooks"]]
    pairs += [(rel, False) for rel in paths["configs"] + paths["control"]]
    return {fold(name): (name, _target(root / name))
            for rel, leaf in pairs for name in _links(root, rel, leaf)}


def _hook_entries(root: Path, rel: str) -> dict:
    entries = {}
    for folder, dirs, names in os.walk(root / rel):
        here = Path(folder)
        linked = [d for d in dirs if is_link(here / d)]
        dirs[:] = [d for d in dirs if d not in linked]
        for name in names + linked:
            key = _key(root, here / name)
            entries[fold(key)] = _entry(here / name, key)
    return entries


def snapshot(root, paths: "dict | None" = None) -> dict:
    """What the guarded paths hold now: links, hook files and guarded files."""
    root = Path(root)
    paths = protected(root) if paths is None else paths
    state = {"paths": paths, "links": _link_map(root, paths), "hooks": {}, "files": {}}
    for rel in paths["hooks"]:
        state["hooks"].update(_hook_entries(root, rel))
    for rel in paths["configs"] + paths["control"]:
        path = root / rel
        if os.path.lexists(path) and (is_link(path) or not path.is_dir()):
            state["files"][fold(rel)] = _entry(path, rel)
    return state


def _remove(path) -> bool:
    """Remove a file, link, junction or empty folder without following it."""
    if not os.path.lexists(path):
        return True
    last = None
    for call in (os.unlink, os.rmdir):
        for retry in (False, True):
            try:
                call(path)
                return True
            except PermissionError as exc:      # a read-only file on Windows
                last = exc
                if retry or is_link(path):
                    break
                try:
                    os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
                except OSError:
                    break
            except OSError as exc:
                last = exc
                break
    log.warning("could not remove %s", path, exc_info=last)
    return False


def _relink(path: Path, target: tuple) -> None:
    """Make `path` a link to `target` again: a symlink, or a junction on Windows."""
    where, is_dir = target
    try:
        os.symlink(where, path, target_is_directory=is_dir)
    except OSError:
        if os.name != "nt" or not is_dir:
            raise
        import _winapi
        _winapi.CreateJunction(where.removeprefix("\\\\?\\"), str(path))


def _put(root: Path, entry: tuple) -> str:
    """Put `entry` back at its path; returns what went wrong, or an empty string."""
    name, kind, data, mode = entry
    path = root / name
    if kind not in ("file", "link"):
        return "too large to put back" if kind == "big" else "could not be read before the run"
    if not _remove(path):
        return "could not remove"
    try:
        if os.path.lexists(path.parent) and not path.parent.is_dir() and not _remove(path.parent):
            return "could not remove"
        path.parent.mkdir(parents=True, exist_ok=True)
        if kind == "link":
            _relink(path, data)
        else:
            path.write_bytes(data)
            os.chmod(path, mode)
    except OSError as exc:
        log.warning("could not put back %s", path, exc_info=True)
        return f"could not put back ({type(exc).__name__})"
    return ""


def _restore(root: Path, old: tuple, what: str, out: Problems) -> None:
    error = _put(root, old)
    out.add(f"{old[0]}: {what}, {error or 'put back'}", bool(error))


def _drop(root: Path, name: str, what: str, done: str, out: Problems) -> bool:
    removed = _remove(root / name)
    out.add(f"{name}: {what}, {done if removed else 'could not remove'}", not removed)
    return removed


def _check_links(root: Path, before: dict, paths: dict, out: Problems) -> None:
    """Undo links planted, retargeted or removed on the way to a guarded path."""
    now = _link_map(root, paths)
    for key, (name, target) in now.items():
        old = before["links"].get(key)
        if old is None:
            _drop(root, name, "replaced by a link", "link removed", out)
        elif old[1] != target:
            _restore(root, (name, "link", old[1], 0), "link changed", out)
    for key, (name, target) in before["links"].items():
        if key not in now:
            _restore(root, (name, "link", target, 0), "link removed", out)


def _check_hooks(root: Path, before: dict, now: dict, out: Problems) -> None:
    for key, entry in now["hooks"].items():
        old = before["hooks"].get(key)
        if old is None:
            if not (key.endswith(".sample") and entry[1] != "link"):
                _drop(root, entry[0], "added", "removed", out)
        elif entry[1:] != old[1:]:
            _restore(root, old, "changed", out)
    for key, old in before["hooks"].items():
        if key not in now["hooks"]:
            _restore(root, old, "deleted", out)


def _check_files(root: Path, before: dict, now: dict, paths: dict, out: Problems) -> None:
    configs = {fold(rel) for rel in paths["configs"]}
    for rel in paths["configs"] + paths["control"]:
        key = fold(rel)
        old, new = before["files"].get(key), now["files"].get(key)
        if old is not None and new is None:
            _restore(root, old, "deleted", out)
        elif new is not None and key in configs and new[1] != "link":
            _check_config(root, old, new, out)
        elif new is not None and old is None:
            _drop(root, new[0], "added", "removed", out)
        elif new is not None and new[1:] != old[1:]:
            _restore(root, old, "changed", out)


def _check_config(root: Path, old, new: tuple, out: Problems) -> None:
    if old is not None and new[1:3] == old[1:3]:
        return
    if new[1] != "file":
        out.add(f"{new[0]}: changed, too large to check", True)
        return
    kept = old is not None and old[1] == "file"
    bad = unsafe_additions(old[2] if kept else None, new[2])
    if not bad:
        return
    names = ", ".join(bad[:6])
    if kept:
        _restore(root, old, f"added {names}", out)
    else:
        _restore(root, (new[0], "file", strip_unsafe(new[2]), new[3]), f"added {names}", out)


def verify(root, before: dict) -> Problems:
    """Compare the guarded paths with `before` and put back what changed.

    Returns one line per change; an empty result means the run left every
    guarded path as it found it, apart from the two allowed exceptions.
    `failed` on the result lists what could not be undone.
    """
    root, out = Path(root), Problems()
    paths = merged(before["paths"], protected(root))
    if paths["capped"] and not before["paths"].get("capped"):
        out.add(".git/modules: more git folders than the guard reads", True)
    _check_links(root, before, paths, out)
    now = snapshot(root, paths)
    _check_hooks(root, before, now, out)
    _check_files(root, before, now, paths, out)
    return out
