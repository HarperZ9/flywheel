from __future__ import annotations

import stat
import os
from pathlib import Path

from .canonical_json import sha256_bytes
from .cli_artifacts import ArtifactError, WorkspaceRoot, checked_workspace
from .path_policy import PathPolicyError, assert_operational_surface_path, is_reparse_point, resolve_under_root
from .undo_receipts import UndoError, UndoReceipt, valid_receipt_id


def undo_root_path(root: Path) -> Path:
    try:
        return resolve_under_root(".canon/undo", root=root)
    except PathPolicyError as exc:
        raise UndoError("unsafe_path") from exc


def ensure_undo_root(root: Path) -> Path:
    workspace = _workspace_from_root(root)
    if _posix_supported():
        from . import undo_posix

        return undo_posix.ensure_undo_root(workspace.path, workspace.stat_key)
    raise UndoError("unsafe_path")


def receipt_path(root: Path, receipt_id: str) -> Path:
    if not valid_receipt_id(receipt_id):
        raise UndoError("invalid_args")
    return root / f"{receipt_id}.json"


def checked_receipt_target(receipt: UndoReceipt, *, workspace: WorkspaceRoot) -> Path:
    _assert_workspace_stable(workspace)
    try:
        target = assert_operational_surface_path(receipt.target_path, root=workspace.path)
    except PathPolicyError as exc:
        raise UndoError("unsafe_path") from exc
    _reject_reserved_target(target, workspace.path)
    if (receipt.target_adapter, receipt.target_surface, receipt.target_path) not in {
        ("codex-cli", "AGENTS.md", "AGENTS.md"),
        ("claude-code", "CLAUDE.md", "CLAUDE.md"),
    }:
        raise UndoError("conflict")
    _assert_workspace_stable(workspace)
    return target


def read_regular_file(path: Path) -> bytes:
    try:
        before = path.lstat()
    except FileNotFoundError as exc:
        raise UndoError("conflict") from exc
    except OSError as exc:
        raise UndoError("io_error") from exc
    if not stat.S_ISREG(before.st_mode) or is_reparse_point(path):
        raise UndoError("unsafe_path")
    fd = _open_regular_for_read(path)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or _stat_key(info) != _stat_key(before):
            raise UndoError("unsafe_path")
        return _read_fd(fd, info.st_size)
    finally:
        os.close(fd)


def replace_file_guarded(path: Path, expected_hash: str, replacement: bytes) -> None:
    _ = (path, expected_hash, replacement)
    raise UndoError("unsafe_path")


def read_workspace_file(workspace: WorkspaceRoot, relative: str) -> bytes:
    target = _checked_relative_target(workspace, relative)
    if _posix_supported():
        from . import undo_posix

        return undo_posix.read_workspace_file(workspace.path, workspace.stat_key, relative)
    return read_regular_file(target)


def replace_workspace_file(workspace: WorkspaceRoot, relative: str, expected_hash: str, replacement: bytes) -> None:
    _checked_relative_target(workspace, relative)
    if not _posix_supported():
        raise UndoError("unsafe_path")
    from . import undo_posix

    undo_posix.replace_workspace_file(workspace.path, workspace.stat_key, relative, expected_hash, replacement)


def write_receipt_file(workspace: WorkspaceRoot, receipt_id: str, data: bytes) -> str:
    name = _receipt_name(receipt_id)
    if not _posix_supported():
        root = undo_root_path(workspace.path)
        target = receipt_path(root, receipt_id)
        if not _exists_or_link(target):
            raise UndoError("unsafe_path")
        _assert_workspace_stable(workspace)
        if read_regular_file(target) == data:
            _assert_workspace_stable(workspace)
            return "idempotent"
        raise UndoError("conflict")
    from . import undo_posix

    return undo_posix.write_receipt(workspace.path, workspace.stat_key, name, data)


def read_receipt_file(workspace: WorkspaceRoot, receipt_id: str) -> bytes:
    name = _receipt_name(receipt_id)
    if _posix_supported():
        from . import undo_posix

        return undo_posix.read_receipt(workspace.path, workspace.stat_key, name)
    root = undo_root_path(workspace.path)
    _assert_workspace_stable(workspace)
    data = read_regular_file(receipt_path(root, receipt_id))
    _assert_workspace_stable(workspace)
    return data


def list_receipt_files(workspace: WorkspaceRoot) -> list[str]:
    if _posix_supported():
        from . import undo_posix

        return undo_posix.list_receipts(workspace.path, workspace.stat_key)
    root = undo_root_path(workspace.path)
    if not _exists_or_link(root):
        return []
    _assert_workspace_stable(workspace)
    if is_reparse_point(root) or not stat.S_ISDIR(root.lstat().st_mode):
        raise UndoError("unsafe_path")
    return sorted(path.name for path in root.glob("undo-*.json") if not path.is_symlink())


def write_new_or_same(path: Path, data: bytes) -> str:
    if _exists_or_link(path):
        if read_regular_file(path) == data:
            return "idempotent"
        raise UndoError("conflict")
    fd: int | None = None
    try:
        fd = os.open(path, _write_flags(), 0o600)
        _write_all(fd, data)
        os.fsync(fd)
    except FileExistsError:
        return write_new_or_same(path, data)
    except OSError as exc:
        raise UndoError("io_error") from exc
    finally:
        if fd is not None:
            os.close(fd)
    if read_regular_file(path) != data:
        raise UndoError("io_error")
    return "created"


def _open_regular_for_read(path: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        return os.open(path, flags)
    except OSError as exc:
        raise UndoError("unsafe_path") from exc


def _write_flags() -> int:
    return os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)


def _read_fd(fd: int, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = os.read(fd, min(remaining, 65536))
        if not chunk:
            raise UndoError("io_error")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _write_all(fd: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        written = os.write(fd, data[offset:])
        if written <= 0:
            raise OSError("short write")
        offset += written


def _reject_reserved_target(path: Path, root: Path) -> None:
    rel = os.path.relpath(path, root).replace(os.sep, "/")
    parts = tuple(part.casefold() for part in rel.split("/"))
    if parts[0] == ".git" or parts[:2] == (".canon", "undo") or parts[:2] == ("tests", "fixtures"):
        raise UndoError("unsafe_path")


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


def _workspace_from_root(root: Path) -> WorkspaceRoot:
    try:
        return checked_workspace(str(root))
    except ArtifactError as exc:
        raise UndoError("unsafe_path") from exc


def _receipt_name(receipt_id: str) -> str:
    if not valid_receipt_id(receipt_id):
        raise UndoError("invalid_args")
    return f"{receipt_id}.json"


def _posix_supported() -> bool:
    if os.name == "nt":
        return False
    try:
        from . import undo_posix
    except ImportError:
        return False
    return undo_posix.supported()


def _assert_workspace_stable(workspace: WorkspaceRoot) -> None:
    try:
        info = workspace.path.lstat()
    except OSError as exc:
        raise UndoError("unsafe_path") from exc
    if _stat_key(info) != workspace.stat_key or not stat.S_ISDIR(info.st_mode) or is_reparse_point(workspace.path):
        raise UndoError("unsafe_path")


def _close_fd(fd: int | None) -> None:
    if fd is None:
        return
    try:
        os.close(fd)
    except OSError:
        pass


def _exists_or_link(path: Path) -> bool:
    try:
        return path.exists() or path.is_symlink()
    except OSError:
        return True


def _stat_key(info: os.stat_result) -> tuple[int, int]:
    if os.name == "nt":
        return (info.st_dev & 0xFFFFFFFF, info.st_ino)
    return (info.st_dev, info.st_ino)


__all__ = [
    "checked_receipt_target",
    "ensure_undo_root",
    "list_receipt_files",
    "read_receipt_file",
    "read_regular_file",
    "read_workspace_file",
    "receipt_path",
    "replace_file_guarded",
    "replace_workspace_file",
    "undo_root_path",
    "write_receipt_file",
    "write_new_or_same",
]
