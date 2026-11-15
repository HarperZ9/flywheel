from __future__ import annotations

import os
import stat
from pathlib import Path

from .cli_artifacts import WorkspaceRoot
from .path_policy import PathPolicyError, assert_operational_surface_path, is_reparse_point
from .undo_io import read_regular_file
from .undo_posix_core import close_child, close_root, open_parent, open_root, supported
from .undo_posix_files import write_new_or_same
from .undo_receipts import UndoError


def write_output_file(workspace: WorkspaceRoot, relative: str, data: bytes) -> str:
    target = _checked_relative_target(workspace, relative)
    if supported():
        return _write_posix(workspace, relative, data)
    return _read_only_existing(target, workspace, data)


def _write_posix(workspace: WorkspaceRoot, relative: str, data: bytes) -> str:
    target = Path(relative)
    root = open_root(workspace.path, workspace.stat_key)
    try:
        parent = open_parent(root, target.parent)
        try:
            return write_new_or_same(parent, target.name, data)
        finally:
            close_child(parent, root)
    finally:
        close_root(root)


def _read_only_existing(target: Path, workspace: WorkspaceRoot, data: bytes) -> str:
    _assert_workspace_stable(workspace)
    if not _exists_or_link(target):
        raise UndoError("unsafe_path")
    if read_regular_file(target) == data:
        _assert_workspace_stable(workspace)
        return "idempotent"
    raise UndoError("conflict")


def _checked_relative_target(workspace: WorkspaceRoot, relative: str) -> Path:
    if type(relative) is not str or relative == "" or "\0" in relative:
        raise UndoError("unsafe_path")
    _assert_workspace_stable(workspace)
    try:
        target = assert_operational_surface_path(relative, root=workspace.path)
    except PathPolicyError as exc:
        raise UndoError("unsafe_path") from exc
    _reject_reserved_target(target, workspace.path)
    _assert_workspace_stable(workspace)
    return target


def _reject_reserved_target(path: Path, root: Path) -> None:
    rel = os.path.relpath(path, root).replace(os.sep, "/")
    parts = tuple(part.casefold() for part in rel.split("/"))
    if parts[0] == ".git" or parts[:2] == (".canon", "undo") or parts[:2] == ("tests", "fixtures"):
        raise UndoError("unsafe_path")


def _assert_workspace_stable(workspace: WorkspaceRoot) -> None:
    try:
        info = workspace.path.lstat()
    except OSError as exc:
        raise UndoError("unsafe_path") from exc
    if _stat_key(info) != workspace.stat_key or not stat.S_ISDIR(info.st_mode) or is_reparse_point(workspace.path):
        raise UndoError("unsafe_path")


def _exists_or_link(path: Path) -> bool:
    try:
        return path.exists() or path.is_symlink()
    except OSError:
        return True


def _stat_key(info: os.stat_result) -> tuple[int, int]:
    if os.name == "nt":
        return (info.st_dev & 0xFFFFFFFF, info.st_ino)
    return (info.st_dev, info.st_ino)


__all__ = ["write_output_file"]
