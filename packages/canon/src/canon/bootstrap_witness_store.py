from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from .canonical_json import sha256_text
from .bootstrap_witness_store_posix import PosixWitnessWriteError, write_once_posix
from .cli_artifacts import WorkspaceRoot
from .path_policy import is_reparse_point, resolve_under_root
from .witness import BootstrapWitness, validate_bootstrap_witness


class BootstrapWitnessStoreError(OSError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class WitnessWrite:
    relative_path: str
    status: str


@dataclass(slots=True)
class _WitnessRoot:
    path: Path
    handle: object | None = None

    def verify_live(self) -> None:
        if self.handle is not None:
            try:
                self.handle.verify_live()
            except Exception as exc:
                raise BootstrapWitnessStoreError("unsafe_path") from exc
            return
        _verify_path_root(self.path)

    def close(self) -> None:
        if self.handle is not None:
            self.handle.close()


def write_bootstrap_witness(
    witness: BootstrapWitness,
    *,
    workspace: WorkspaceRoot,
    state_dir: Path,
    state_root: object | None = None,
) -> WitnessWrite:
    if validate_bootstrap_witness(witness):
        raise BootstrapWitnessStoreError("io_error")
    _assert_workspace_stable(workspace)
    _verify_state_root(state_root)
    root = _witness_root(state_dir, state_root)
    try:
        target = _target_path(root.path, witness.run_id)
        data = witness.to_json().encode("utf-8")
        root.verify_live()
        status = _write_once(root, target.name, data)
        root.verify_live()
        _assert_workspace_stable(workspace)
        return WitnessWrite(_relative_text(target, workspace.path), status)
    finally:
        root.close()


def _witness_root(state_dir: Path, state_root: object | None = None) -> _WitnessRoot:
    if state_root is not None:
        return _witness_root_bound(state_root)
    try:
        root = resolve_under_root("witnesses", root=state_dir)
    except Exception as exc:
        raise BootstrapWitnessStoreError("unsafe_path") from exc
    try:
        if root.exists() or root.is_symlink():
            if is_reparse_point(root):
                raise BootstrapWitnessStoreError("unsafe_path")
            if not stat.S_ISDIR(root.lstat().st_mode):
                raise BootstrapWitnessStoreError("io_error")
        root.mkdir(parents=True, exist_ok=True)
    except BootstrapWitnessStoreError:
        raise
    except OSError as exc:
        raise BootstrapWitnessStoreError("io_error") from exc
    return _WitnessRoot(root)


def _witness_root_bound(state_root: object) -> _WitnessRoot:
    try:
        handle = state_root.open_child_dir("witnesses", create=True)
        if handle is None:
            raise BootstrapWitnessStoreError("unsafe_path")
        return _WitnessRoot(handle.path, handle)
    except BootstrapWitnessStoreError:
        raise
    except Exception as exc:
        _raise_non_dir_witness_child(state_root)
        raise BootstrapWitnessStoreError("unsafe_path") from exc


def _raise_non_dir_witness_child(state_root: object) -> None:
    path = getattr(state_root, "path", None)
    if not isinstance(path, Path):
        return
    try:
        info = (path / "witnesses").lstat()
    except OSError:
        return
    if not stat.S_ISDIR(info.st_mode) and not is_reparse_point(path / "witnesses"):
        raise BootstrapWitnessStoreError("io_error")


def _target_path(root: Path, run_id: str) -> Path:
    digest = sha256_text(run_id).removeprefix("sha256:")
    try:
        return resolve_under_root(f"run-{digest}.json", root=root)
    except Exception as exc:
        raise BootstrapWitnessStoreError("unsafe_path") from exc


def _write_once(root: _WitnessRoot, name: str, data: bytes) -> str:
    if root.handle is not None and os.name != "nt":
        return _write_once_posix(root, name, data)
    root.verify_live()
    status = _write_once_path(root.path / name, data)
    root.verify_live()
    return status


def _write_once_path(path: Path, data: bytes) -> str:
    if path.exists() or path.is_symlink():
        return _existing_status(path, data)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd: int | None = None
    created_key: tuple[int, int] | None = None
    try:
        fd = os.open(path, flags, 0o600)
        created_key = _stat_key(os.fstat(fd))
    except FileExistsError:
        return _existing_status(path, data)
    except OSError as exc:
        raise BootstrapWitnessStoreError("io_error") from exc
    try:
        _write_all(fd, data)
        os.fsync(fd)
        _close_created(fd)
        fd = None
    except OSError as exc:
        if fd is not None:
            _close_silently(fd)
        _cleanup_created(path, created_key)
        raise BootstrapWitnessStoreError("io_error") from exc
    if _read_existing(path) != data:
        _cleanup_created(path, created_key)
        raise BootstrapWitnessStoreError("io_error")
    return "created"


def _write_once_posix(root: _WitnessRoot, name: str, data: bytes) -> str:
    try:
        return write_once_posix(root.handle.ref, name, data, verify=root.verify_live, write_all=_write_all)
    except PosixWitnessWriteError as exc:
        raise BootstrapWitnessStoreError(exc.code) from exc


def _existing_status(path: Path, expected: bytes) -> str:
    if is_reparse_point(path):
        raise BootstrapWitnessStoreError("unsafe_path")
    if _read_existing(path) == expected:
        return "idempotent"
    raise BootstrapWitnessStoreError("conflict")


def _read_existing(path: Path) -> bytes:
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode):
            raise BootstrapWitnessStoreError("conflict")
        data = path.read_bytes()
        after = path.lstat()
    except BootstrapWitnessStoreError:
        raise
    except OSError as exc:
        raise BootstrapWitnessStoreError("io_error") from exc
    if (before.st_dev, before.st_ino, before.st_size) != (after.st_dev, after.st_ino, after.st_size):
        raise BootstrapWitnessStoreError("unsafe_path")
    return data


def _write_all(fd: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        written = os.write(fd, data[offset:])
        if written <= 0:
            raise OSError("short witness write")
        offset += written


def _close_created(fd: int) -> None:
    os.close(fd)


def _close_silently(fd: int) -> None:
    try:
        os.close(fd)
    except OSError:
        pass


def _cleanup_created(path: Path, expected_key: tuple[int, int] | None) -> None:
    if expected_key is None:
        return
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or is_reparse_point(path) or _stat_key(info) != expected_key:
            raise BootstrapWitnessStoreError("io_error")
        path.unlink()
    except FileNotFoundError:
        return
    except BootstrapWitnessStoreError:
        raise
    except OSError as exc:
        raise BootstrapWitnessStoreError("io_error") from exc


def _verify_state_root(state_root: object | None) -> None:
    if state_root is None:
        return
    try:
        state_root.verify_live()
    except BootstrapWitnessStoreError:
        raise
    except Exception as exc:
        raise BootstrapWitnessStoreError("unsafe_path") from exc


def _assert_workspace_stable(workspace: WorkspaceRoot) -> None:
    try:
        info = workspace.path.lstat()
    except OSError as exc:
        raise BootstrapWitnessStoreError("unsafe_path") from exc
    if _stat_key(info) != workspace.stat_key or not stat.S_ISDIR(info.st_mode):
        raise BootstrapWitnessStoreError("unsafe_path")
    if is_reparse_point(workspace.path):
        raise BootstrapWitnessStoreError("unsafe_path")


def _verify_path_root(path: Path) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise BootstrapWitnessStoreError("unsafe_path") from exc
    if not stat.S_ISDIR(info.st_mode) or is_reparse_point(path):
        raise BootstrapWitnessStoreError("unsafe_path")


def _relative_text(path: Path, root: Path) -> str:
    try:
        return os.path.relpath(path, root).replace(os.sep, "/")
    except ValueError as exc:
        raise BootstrapWitnessStoreError("unsafe_path") from exc


def _stat_key(info: os.stat_result) -> tuple[int, int]:
    if os.name == "nt":
        return (info.st_dev & 0xFFFFFFFF, info.st_ino)
    return (info.st_dev, info.st_ino)


__all__ = ["BootstrapWitnessStoreError", "WitnessWrite", "write_bootstrap_witness"]
