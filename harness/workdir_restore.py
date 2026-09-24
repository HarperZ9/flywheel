"""workdir_restore.py: put a task workdir back after every candidate run.

RLFromOracle.collect, accept_gate, best-of-N and the witness run every
candidate for a task in the same workdir. Before 2026-09-23 nothing undid
what a run wrote there, and clear_bytecode removed only __pycache__. On
Windows, Python 3.12.10, pytest 8.4.2, a candidate that wrote conftest.py at
import time left a collection hook that kept only the one test a lazy
`return 0` passes. The lazy rollout after it was paid reward 1.0 with
held-out reward 1.0, and the planter's own held-out run read PASS through the
file its visible run wrote. A candidate that rewrote the task's test file had
the same effect. The AST guard flags neither, since writing a file is
ordinary Python.

What this module does: PytestOracle.verify and witness_envelope take a
snapshot of every file under the workdir after they write the candidate and
before the run starts, and restore it when the run ends, whatever the
verdict. A file or
directory the run created is removed. A file it changed, removed or replaced
is written back byte for byte, as a new file, so a hard link planted in its
place is never written through. File and directory modes go back as well.
The next run starts from the files the task supplied plus its own candidate.

A link, meaning a symbolic link or on Windows any reparse point such as a
junction, is recorded by its target and never entered. os.walk enters a
junction even with followlinks=False, so a walk that trusted it would delete
files outside the workdir. A link the run created is removed as a link. A
link the task supplied and the run changed or removed is not recreated.

A restore that cannot finish raises WorkdirRestoreError after it has tried
every entry. The next run would otherwise be graded in a workdir that still
holds what this run left, and that is the failure this module exists to
stop.

Does not prove: a process the candidate leaves running after pytest exits
can write into the workdir after the restore, and a write outside the
workdir, such as a .pth file in site-packages, is not undone.
python_execution_containment.py names the boundary that would stop both.
A run that changes a task file changes it for its own grade too, and the
restore only protects the runs after it. PythonExecutorOracle in
exec_oracle.py runs candidates in a shared workdir without a restore. The
cost is one read of every workdir file before the run and one after it.
"""
from __future__ import annotations

import os
import stat
from dataclasses import dataclass, field
from pathlib import Path

_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)


class WorkdirRestoreError(RuntimeError):
    """The workdir could not be put back, so the next run is not safe."""


@dataclass
class Snapshot:
    """What the workdir held before a run, keyed by POSIX relative path."""
    root: Path
    root_mode: int = 0
    files: dict[str, bytes] = field(default_factory=dict)
    dirs: set[str] = field(default_factory=set)
    links: dict[str, str] = field(default_factory=dict)
    modes: dict[str, int] = field(default_factory=dict)


def _is_link(st: os.stat_result) -> bool:
    """A symbolic link, or on Windows any reparse point, junctions included."""
    return stat.S_ISLNK(st.st_mode) or bool(
        getattr(st, "st_file_attributes", 0) & _REPARSE_POINT)


def _target(path: str) -> str:
    try:
        return os.readlink(path)
    except OSError:
        return ""       # a reparse point that is not a link: kept by name


def _kind(st: os.stat_result) -> str:
    if _is_link(st):
        return "link"
    return "dir" if stat.S_ISDIR(st.st_mode) else "file"


def _open_dir(path: str, st: os.stat_result) -> None:
    """Give the owner full access, so no entry hides behind a mode change."""
    mode = stat.S_IMODE(st.st_mode)
    if mode & stat.S_IRWXU != stat.S_IRWXU:
        os.chmod(path, mode | stat.S_IRWXU)


def _scan(root: Path, errors: list[str], *, unlock: bool = False) -> list:
    """Every entry under `root` as (rel, kind, lstat), each parent before its
    children. Never enters a link. `unlock` opens each directory first."""
    out: list[tuple[str, str, os.stat_result]] = []
    stack = [str(root)]
    while stack:
        top = stack.pop()
        try:
            names = sorted(os.listdir(top))
        except OSError as exc:
            errors.append(f"list {top}: {exc}")
            continue
        for name in names:
            full = os.path.join(top, name)
            try:
                st = os.lstat(full)
                kind = _kind(st)
                if kind == "dir":
                    if unlock:
                        _open_dir(full, st)
                    stack.append(full)
            except OSError as exc:
                errors.append(f"stat {full}: {exc}")
                continue
            out.append((Path(full).relative_to(root).as_posix(), kind, st))
    return out


def snapshot(workdir: str | Path) -> Snapshot:
    """Record every file, directory, link and mode under `workdir`."""
    root = Path(workdir).resolve()
    snap = Snapshot(root=root, root_mode=stat.S_IMODE(os.lstat(root).st_mode))
    errors: list[str] = []
    for rel, kind, st in _scan(root, errors):
        if kind == "link":
            snap.links[rel] = _target(str(root / rel))
            continue
        snap.modes[rel] = stat.S_IMODE(st.st_mode)
        if kind == "dir":
            snap.dirs.add(rel)
            continue
        try:
            snap.files[rel] = (root / rel).read_bytes()
        except OSError as exc:
            errors.append(f"read {rel}: {exc}")
    if errors:
        raise WorkdirRestoreError(
            f"cannot take a snapshot of {root}: " + "; ".join(errors[:8]))
    return snap


def _rm(path: str, kind: str) -> None:
    if kind == "dir":
        os.rmdir(path)
    else:
        os.unlink(path)


def _unlink(path: str, kind: str) -> None:
    """Remove one entry. A link goes as a link; its target is never touched."""
    try:
        _rm(path, kind)
    except (PermissionError, IsADirectoryError):
        if kind == "link":
            os.rmdir(path)      # a Windows directory link
            return
        os.chmod(path, stat.S_IMODE(os.lstat(path).st_mode) | stat.S_IRWXU)
        _rm(path, kind)


def _reset_root(snap: Snapshot) -> None:
    """Make the root a real, open directory again, never following a link."""
    root = str(snap.root)
    try:
        st = os.lstat(root)
        if _kind(st) != "dir":
            _unlink(root, _kind(st))
    except FileNotFoundError:
        pass
    os.makedirs(root, exist_ok=True)
    _open_dir(root, os.lstat(root))


def _drop_added(snap: Snapshot, errors: list[str]) -> None:
    """Remove every entry the run added or retyped, children first."""
    for rel, kind, _st in reversed(_scan(snap.root, errors, unlock=True)):
        full = str(snap.root / rel)
        if kind == "link":
            keep = snap.links.get(rel) == _target(full)
        else:
            keep = rel in (snap.dirs if kind == "dir" else snap.files)
        if keep:
            continue
        try:
            _unlink(full, kind)
        except OSError as exc:
            errors.append(f"remove {rel}: {exc}")


def _through_link(root: Path, path: Path) -> bool:
    """True when a parent of `path` inside `root` is a link or is missing."""
    for parent in path.relative_to(root).parents:
        if str(parent) == ".":
            return False
        try:
            if _is_link(os.lstat(root / parent)):
                return True
        except OSError:
            return True
    return False


def _put_back_file(snap: Snapshot, rel: str, data: bytes) -> str:
    """Rewrite one file if the run changed it. Returns an error, or ""."""
    path = snap.root / rel
    if _through_link(snap.root, path):
        return f"rewrite {rel}: a parent is a link or missing"
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        st = None
    if st is not None and _kind(st) != "file":
        return f"rewrite {rel}: the run left a {_kind(st)} in its place"
    if st is not None:
        try:
            if path.read_bytes() == data:
                return ""
        except PermissionError:
            pass                        # unreadable now: replaced below
        _unlink(str(path), "file")      # never write through a hard link
    path.write_bytes(data)
    return ""


def _put_back(snap: Snapshot, errors: list[str]) -> None:
    """Recreate directories, rewrite changed files, then reset every mode."""
    for rel in sorted(snap.dirs):
        path = snap.root / rel
        try:
            if not _through_link(snap.root, path):
                path.mkdir(exist_ok=True)
        except OSError as exc:
            errors.append(f"mkdir {rel}: {exc}")
    for rel, data in sorted(snap.files.items()):
        try:
            error = _put_back_file(snap, rel, data)
        except OSError as exc:
            error = f"rewrite {rel}: {exc}"
        if error:
            errors.append(error)
    for rel, target in sorted(snap.links.items()):
        link = str(snap.root / rel)
        if not os.path.lexists(link) or _target(link) != target:
            errors.append(f"link {rel} was changed or removed; not recreated")
    _reset_modes(snap, errors)


def _reset_modes(snap: Snapshot, errors: list[str]) -> None:
    entries = [(snap.root / rel, mode) for rel, mode in snap.modes.items()]
    for path, mode in entries + [(snap.root, snap.root_mode)]:
        try:
            st = os.lstat(path)
            if not _is_link(st) and stat.S_IMODE(st.st_mode) != mode:
                os.chmod(path, mode)
        except OSError as exc:
            errors.append(f"chmod {path.relative_to(snap.root)}: {exc}")


def restore(snap: Snapshot) -> None:
    """Put the workdir back to `snap`. Raises if any entry could not be."""
    errors: list[str] = []
    try:
        _reset_root(snap)
    except OSError as exc:
        raise WorkdirRestoreError(f"cannot reopen {snap.root}: {exc}") from exc
    _drop_added(snap, errors)
    _put_back(snap, errors)
    if errors:
        raise WorkdirRestoreError(
            f"could not restore {snap.root}: " + "; ".join(errors[:8]))
