"""POSIX half of handle-based removal: `openat` with O_NOFOLLOW relative to
the pinned directory descriptor, `unlinkat` for files and links, and
recursion into real directories only."""
from __future__ import annotations

import os
from pathlib import Path
import stat

from .private_artifact_remove import RemovalError

_DIR_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)


def _identity(fd: int):
    from .private_artifact_fs import ArtifactIdentity
    info = os.fstat(fd)
    return ArtifactIdentity("posix", int(info.st_dev), int(info.st_ino))


def _remove_entry(parent: int, name: str, counts: dict) -> None:
    try:
        info = os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        return
    if stat.S_ISLNK(info.st_mode):
        os.unlink(name, dir_fd=parent)
        counts["links"] += 1
        return
    if not stat.S_ISDIR(info.st_mode):
        os.unlink(name, dir_fd=parent)
        counts["files"] += 1
        return
    child = os.open(name, _DIR_FLAGS, dir_fd=parent)
    try:
        for entry in sorted(os.listdir(child)):
            _remove_entry(child, entry, counts)
    finally:
        os.close(child)
    os.rmdir(name, dir_fd=parent)
    counts["dirs"] += 1


def remove_at(root: Path, parts: tuple[str, ...], expected) -> dict:
    counts = {"files": 0, "dirs": 0, "links": 0}
    try:
        fd = os.open(root, _DIR_FLAGS)
    except FileNotFoundError:
        if expected is not None:
            raise RemovalError("ROOT_CHANGED") from None
        return counts
    chain = [fd]
    try:
        if expected is not None and _identity(fd) != expected:
            raise RemovalError("ROOT_CHANGED")
        for name in parts[:-1]:
            try:
                chain.append(os.open(name, _DIR_FLAGS, dir_fd=chain[-1]))
            except FileNotFoundError:
                return counts
            except OSError:
                raise RemovalError("UNSAFE_PATH") from None
        _remove_entry(chain[-1], parts[-1], counts)
        return counts
    finally:
        for handle in reversed(chain):
            os.close(handle)
