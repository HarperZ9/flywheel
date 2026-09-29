"""Handle-based removal inside a pinned private root (7.10, SP-21).

`remove(root, rel, expected=identity)` removes the file, link or tree at `rel`
under `root`. The root is opened first and must match `expected` (volume and
file index on Windows, device and inode on POSIX), or nothing is touched
(ROOT_CHANGED). Every entry is opened without following links: a junction or
symbolic link is deleted as a link and its target stays, and recursion enters
real directories only. Windows deletes by handle; POSIX uses `unlinkat` and
`openat` with O_NOFOLLOW relative to the pinned directory descriptor. The
existing private filesystem backends sit at their size limit, so this is a
separate module with one half per platform.
"""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath, PureWindowsPath


class RemovalError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def parts_of(rel) -> tuple[str, ...]:
    text = str(rel).replace("\\", "/")
    if (not text or text.startswith("/") or PureWindowsPath(text).drive
            or PurePosixPath(text).is_absolute() or ":" in text):
        raise RemovalError("UNSAFE_PATH")
    parts = tuple(p for p in text.split("/") if p not in ("", "."))
    if not parts or any(p == ".." for p in parts):
        raise RemovalError("UNSAFE_PATH")
    return parts


def remove(root, rel, *, expected=None) -> dict:
    """Counts of files, directories and links removed; zeros when absent."""
    parts = parts_of(rel)
    if os.name == "nt":
        from .private_artifact_remove_windows import remove_at
    else:
        from .private_artifact_remove_posix import remove_at
    return remove_at(Path(root), parts, expected)


def remove_all(root, names, *, expected=None) -> dict:
    total = {"files": 0, "dirs": 0, "links": 0}
    for name in names:
        for key, value in remove(root, name, expected=expected).items():
            total[key] += value
    return total
