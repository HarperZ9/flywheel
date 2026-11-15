from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat

from .undo_receipts import UndoError

_UNDO = (".canon", "undo")


@dataclass(frozen=True, slots=True)
class DirCap:
    path: Path
    fd: int
    key: tuple[int, int]


def supported() -> bool:
    return (
        os.name != "nt"
        and os.open in os.supports_dir_fd
        and os.mkdir in os.supports_dir_fd
        and os.rename in os.supports_dir_fd
        and os.unlink in os.supports_dir_fd
        and all(hasattr(os, name) for name in ("O_DIRECTORY", "O_NOFOLLOW"))
    )


def open_root(path: Path, expected_key: tuple[int, int]) -> DirCap:
    if not supported():
        raise UndoError("unsafe_path")
    try:
        fd = _open_dir_path(path)
    except FileNotFoundError as exc:
        raise UndoError("unsafe_path") from exc
    cap = DirCap(path, fd, _fd_key(fd))
    try:
        if cap.key != expected_key:
            raise UndoError("unsafe_path")
        verify(cap)
        return cap
    except Exception:
        os.close(fd)
        raise


def open_parent(root: DirCap, relative: Path) -> DirCap:
    parts = () if str(relative) == "." else relative.parts
    cap = root
    try:
        for index, part in enumerate(parts):
            child = open_child(cap, part, root.path.joinpath(*parts[: index + 1]))
            close_child(cap, root)
            cap = child
        return cap
    except FileNotFoundError as exc:
        close_child(cap, root)
        raise UndoError("conflict") from exc
    except Exception:
        close_child(cap, root)
        raise


def ensure_undo(root: DirCap) -> DirCap:
    canon = ensure_child(root, _UNDO[0], root.path / _UNDO[0])
    try:
        return ensure_child(canon, _UNDO[1], canon.path / _UNDO[1])
    finally:
        close_child(canon, root)


def open_undo(root: DirCap, *, required: bool) -> DirCap | None:
    try:
        canon = open_child(root, _UNDO[0], root.path / _UNDO[0])
        try:
            return open_child(canon, _UNDO[1], canon.path / _UNDO[1])
        finally:
            close_child(canon, root)
    except FileNotFoundError:
        if required:
            raise UndoError("conflict") from None
        return None


def ensure_child(parent: DirCap, name: str, path: Path) -> DirCap:
    check_name(name)
    verify(parent)
    try:
        os.mkdir(name, 0o700, dir_fd=parent.fd)
        fsync_dir(parent.fd)
    except FileExistsError:
        pass
    except OSError as exc:
        raise UndoError("unsafe_path") from exc
    return open_child(parent, name, path)


def open_child(parent: DirCap, name: str, path: Path) -> DirCap:
    check_name(name)
    verify(parent)
    fd = _open_dir_path(name, parent.fd)
    cap = DirCap(path, fd, _fd_key(fd))
    try:
        verify(cap)
        return cap
    except Exception:
        os.close(fd)
        raise


def verify(cap: DirCap) -> None:
    try:
        path_info = cap.path.lstat()
        fd_info = os.fstat(cap.fd)
    except OSError as exc:
        raise UndoError("unsafe_path") from exc
    if not stat.S_ISDIR(path_info.st_mode) or _stat_key(path_info) != cap.key or _stat_key(fd_info) != cap.key:
        raise UndoError("unsafe_path")


def close_child(cap: DirCap, root: DirCap) -> None:
    if cap is not root:
        close_fd(cap.fd)


def close_root(root: DirCap) -> None:
    close_fd(root.fd)


def check_name(name: str) -> None:
    if type(name) is not str or name in ("", ".", "..") or "/" in name or "\\" in name or "\0" in name:
        raise UndoError("unsafe_path")


def fsync_dir(fd: int) -> None:
    try:
        os.fsync(fd)
    except OSError:
        pass


def close_fd(fd: int | None) -> None:
    if fd is None:
        return
    try:
        os.close(fd)
    except OSError:
        pass


def _open_dir_path(path: str | Path, dir_fd: int | None = None) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
    try:
        return os.open(path, flags) if dir_fd is None else os.open(path, flags, dir_fd=dir_fd)
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise UndoError("unsafe_path") from exc


def _fd_key(fd: int) -> tuple[int, int]:
    return _stat_key(os.fstat(fd))


def _stat_key(info: os.stat_result) -> tuple[int, int]:
    return (info.st_dev, info.st_ino)


__all__ = [
    "DirCap",
    "check_name",
    "close_child",
    "close_fd",
    "close_root",
    "ensure_undo",
    "fsync_dir",
    "open_parent",
    "open_root",
    "open_undo",
    "supported",
    "verify",
]
