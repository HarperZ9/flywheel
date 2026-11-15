from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from . import source_state_cache as _cache
from .cli_artifacts import WorkspaceRoot
from .path_policy import is_reparse_point

if os.name == "nt":
    from . import concurrency_windows_api as _win
else:
    _win = None  # type: ignore[assignment]


class BootstrapStateRootError(OSError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(slots=True)
class BootstrapDirHandle:
    state_root: BootstrapStateRoot
    path: Path
    ref: int
    _closed: bool = False

    def verify_live(self) -> None:
        if self._closed:
            raise BootstrapStateRootError("unsafe_path")
        self.state_root.verify_live()
        _verify_dir_identity(self.path, self.ref)

    def close(self) -> None:
        if not self._closed:
            _close_ref(self.ref)
            self._closed = True


@dataclass(slots=True)
class BootstrapStateRoot:
    workspace: WorkspaceRoot
    path: Path
    ref: int
    _closed: bool = False

    def verify_live(self) -> None:
        if self._closed:
            raise BootstrapStateRootError("unsafe_path")
        _assert_workspace_stable(self.workspace)
        _verify_dir_identity(self.path, self.ref)

    def open_child_dir(self, name: str, *, create: bool = False) -> BootstrapDirHandle | None:
        _check_name(name)
        self.verify_live()
        if create:
            _mkdir_child(self.ref, name)
        try:
            handle = _open_child(self.ref, name, self.path / name)
        except FileNotFoundError:
            if not create:
                return None
            raise BootstrapStateRootError("unsafe_path") from None
        child = BootstrapDirHandle(self, self.path / name, handle)
        child.verify_live()
        return child

    def close(self) -> None:
        if not self._closed:
            _close_ref(self.ref)
            self._closed = True


def open_bootstrap_state_root(workspace: WorkspaceRoot, state_dir: Path) -> BootstrapStateRoot:
    try:
        _cache._require_safe_backend()
        parts = _relative_parts(state_dir, workspace.path)
        _assert_workspace_stable(workspace)
        root_ref = _cache._open_root(workspace.path)
    except Exception as exc:
        raise BootstrapStateRootError("unsafe_path") from exc
    parent_ref = root_ref
    parent_path = workspace.path
    keep_ref: int | None = None
    try:
        for part in parts:
            _mkdir_child(parent_ref, part)
            child_ref = _open_child(parent_ref, part, parent_path / part)
            if parent_ref != root_ref:
                _close_ref(parent_ref)
            parent_ref = child_ref
            parent_path = parent_path / part
        keep_ref = parent_ref
        state_root = BootstrapStateRoot(workspace, parent_path, keep_ref)
        state_root.verify_live()
        return state_root
    except BootstrapStateRootError:
        raise
    except OSError as exc:
        raise BootstrapStateRootError("unsafe_path") from exc
    finally:
        if root_ref != keep_ref:
            _close_silently(root_ref)


def _relative_parts(path: Path, root: Path) -> tuple[str, ...]:
    try:
        rel = os.path.relpath(path, root)
    except ValueError as exc:
        raise BootstrapStateRootError("unsafe_path") from exc
    parts = tuple(Path(rel).parts)
    if not parts or any(part in ("", ".", "..") or "\\" in part or "/" in part for part in parts):
        raise BootstrapStateRootError("unsafe_path")
    return parts


def _check_name(name: str) -> None:
    if type(name) is not str or name in ("", ".", "..") or "\\" in name or "/" in name or "\0" in name:
        raise BootstrapStateRootError("unsafe_path")


def _mkdir_child(parent_ref: int, name: str) -> None:
    try:
        if os.name == "nt":
            handle = _win.nt_create_relative(  # type: ignore[union-attr]
                parent_ref, name, _win.GENERIC_READ | _win.SYNCHRONIZE,  # type: ignore[union-attr]
                _win.FILE_SHARE_READ | _win.FILE_SHARE_WRITE, _win.FILE_CREATE,  # type: ignore[union-attr]
                _cache._WIN_FILE_DIRECTORY_FILE | _win.FILE_OPEN_REPARSE_POINT,  # type: ignore[union-attr]
            )
            _win.close_handle(handle)  # type: ignore[union-attr]
        else:
            os.mkdir(name, 0o700, dir_fd=parent_ref)
    except FileExistsError:
        return
    except OSError as exc:
        raise BootstrapStateRootError("unsafe_path") from exc


def _open_child(parent_ref: int, name: str, path: Path) -> int:
    try:
        handle = _cache._win_open_dir((parent_ref, name)) if os.name == "nt" else _cache._posix_open_dir(name, parent_ref)
        _verify_dir_identity(path, handle)
        return handle
    except BootstrapStateRootError:
        raise
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise BootstrapStateRootError("unsafe_path") from exc


def _verify_dir_identity(path: Path, handle: int) -> None:
    try:
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or is_reparse_point(path):
            raise BootstrapStateRootError("unsafe_path")
        _cache._verify_root_identity(info, handle)
    except BootstrapStateRootError:
        raise
    except Exception as exc:
        raise BootstrapStateRootError("unsafe_path") from exc


def _assert_workspace_stable(workspace: WorkspaceRoot) -> None:
    try:
        info = workspace.path.lstat()
    except OSError as exc:
        raise BootstrapStateRootError("unsafe_path") from exc
    if _stat_key(info) != workspace.stat_key or not stat.S_ISDIR(info.st_mode):
        raise BootstrapStateRootError("unsafe_path")
    if is_reparse_point(workspace.path):
        raise BootstrapStateRootError("unsafe_path")


def _stat_key(info: os.stat_result) -> tuple[int, int]:
    return (info.st_dev & 0xFFFFFFFF, info.st_ino) if os.name == "nt" else (info.st_dev, info.st_ino)


def _close_ref(ref: int) -> None:
    _win.close_handle(ref) if os.name == "nt" else os.close(ref)  # type: ignore[union-attr]


def _close_silently(ref: int) -> None:
    try:
        _close_ref(ref)
    except OSError:
        pass


__all__ = ["BootstrapDirHandle", "BootstrapStateRoot", "BootstrapStateRootError", "open_bootstrap_state_root"]
