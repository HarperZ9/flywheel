from __future__ import annotations

import os
import re
import stat
import time
from pathlib import Path

from . import concurrency_capability as _caps
from . import concurrency_lock_backend as _backend
from . import concurrency_posix as _posix
from . import concurrency_windows as _win
from .concurrency_errors import LockError

_LOCK_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_RESERVED = frozenset(
    {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
)


def validate_lock_name(name: object) -> str:
    if not isinstance(name, str) or name in ("", ".", ".."):
        raise LockError("invalid-lock-name", "name must be non-empty text")
    if "\0" in name or has_control(name) or _LOCK_NAME_RE.fullmatch(name) is None:
        raise LockError("invalid-lock-name", name)
    if name.endswith(".") or name.split(".", 1)[0].casefold() in _RESERVED:
        raise LockError("invalid-lock-name", name)
    return name


def resolve_lock_root(root: object) -> Path:
    path = coerce_path(root, role="lock-root")
    if is_reparse_point(path):
        raise LockError("lock-reparse", str(path))
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise LockError("invalid-lock-root", str(path)) from exc
    except (OSError, RuntimeError, ValueError) as exc:
        raise LockError("invalid-lock-root", str(exc)) from exc
    if not resolved.is_dir():
        raise LockError("invalid-lock-root", str(resolved))
    return resolved


def prepare_lock_dir(root: Path) -> Path:
    lock_dir = root / ".canon-locks"
    if exists_or_link(lock_dir) and is_reparse_point(lock_dir):
        raise LockError("lock-reparse", str(lock_dir))
    try:
        lock_dir.mkdir(mode=0o700, exist_ok=True)
    except OSError as exc:
        raise LockError("lock-root", str(exc)) from exc
    if is_reparse_point(lock_dir) or not lock_dir.is_dir():
        raise LockError("lock-reparse", str(lock_dir))
    return lock_dir


def new_lock_token() -> str:
    return f"{os.getpid()}:{time.monotonic_ns()}"


def write_new_lock(lock_dir: Path, lock_name: str, token: str) -> tuple[Path, _caps.LockCapability]:
    snapshot = _lock_dir_snapshot(lock_dir)
    lock_path = lock_dir / lock_name
    if _can_use_windows_lock():
        return lock_path, _backend.write_windows(lock_dir, lock_name, token, snapshot, _verify_lock_dir)
    if _can_use_dir_fd_lock():
        return lock_path, _backend.write_posix(lock_dir, lock_name, token, snapshot, _verify_lock_dir)
    raise LockError("lock-unsupported", "stable lock primitive unavailable")


def register_lock(owner: object, capability: _caps.LockCapability) -> None:
    _caps.register(owner, capability)


def discard_lock(capability: _caps.LockCapability) -> None:
    try:
        _backend.delete_capability(capability)
    except LockError:
        _backend.close_capability(capability)


def release_lock(owner: object, root: object, name: object, token: object, path: object) -> None:
    checked_name = validate_lock_name(name)
    if not isinstance(token, str) or token == "" or has_control(token):
        raise LockError("invalid-lock", "token must be non-empty text")
    root_path = coerce_path(root, role="lock-root")
    lock_path = coerce_path(path, role="lock-path")
    _assert_release_target(root_path, checked_name, lock_path)
    capability = _registered_capability(owner, root_path, checked_name, token, lock_path)
    if capability.released:
        return
    try:
        _backend.verify_capability(capability)
    except LockError:
        _close_and_unregister(owner, capability)
        raise
    try:
        _backend.delete_capability(capability)
        _caps.mark_released(owner, capability)
    except _backend.RetryableReleaseError:
        raise
    except LockError:
        _close_and_unregister(owner, capability)
        raise


def coerce_path(value: object, *, role: str) -> Path:
    try:
        raw = os.fspath(value)
    except TypeError as exc:
        raise LockError(f"invalid-{role}", type(value).__name__) from exc
    if not isinstance(raw, str) or raw == "" or "\0" in raw:
        raise LockError(f"invalid-{role}", str(raw))
    return Path(raw)


def has_control(value: str) -> bool:
    return any(ord(ch) < 32 or ord(ch) == 127 for ch in value)


def exists_or_link(path: Path) -> bool:
    try:
        return path.exists() or path.is_symlink()
    except OSError:
        return True


def is_reparse_point(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        attrs = getattr(path.lstat(), "st_file_attributes", None)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return bool(attrs & _REPARSE_POINT) if attrs is not None else False


def _registered_capability(
    owner: object,
    root: Path,
    name: str,
    token: str,
    path: Path,
) -> _caps.LockCapability:
    capability = _caps.lookup(owner)
    if capability is None:
        raise LockError("lock-stale", "lock is not registered")
    if not _caps.metadata_matches(capability, root=root, name=name, token=token, path=path):
        _close_and_unregister(owner, capability)
        raise LockError("lock-stale", "lock metadata changed")
    return capability


def _close_and_unregister(owner: object, capability: _caps.LockCapability) -> None:
    _backend.close_capability(capability)
    _caps.unregister(owner)


def _can_use_dir_fd_lock() -> bool:
    return _posix.supported()


def _can_use_windows_lock() -> bool:
    return os.name == "nt" and _win.supported()


def _lock_dir_snapshot(lock_dir: Path) -> tuple[Path, int, int]:
    if is_reparse_point(lock_dir):
        raise LockError("lock-reparse", str(lock_dir))
    try:
        resolved = lock_dir.resolve(strict=True)
        info = lock_dir.lstat()
    except FileNotFoundError as exc:
        raise LockError("lock-reparse", str(lock_dir)) from exc
    except OSError as exc:
        raise LockError("lock-root", str(exc)) from exc
    if not stat.S_ISDIR(info.st_mode):
        raise LockError("lock-reparse", str(lock_dir))
    return (resolved, info.st_dev, info.st_ino)


def _verify_lock_dir(lock_dir: Path, snapshot: tuple[Path, int, int]) -> None:
    if _lock_dir_snapshot(lock_dir) != snapshot:
        raise LockError("lock-reparse", str(lock_dir))


def _assert_release_target(root: Path, name: str, lock_path: Path) -> None:
    lock_dir = root / ".canon-locks"
    expected_name = f"{name}.lock"
    if lock_path.name != expected_name or not _is_under(lock_path, lock_dir):
        raise LockError("lock-escape", str(lock_path))


def _is_under(path: Path, root: Path) -> bool:
    try:
        root_text = os.path.normcase(os.path.abspath(root))
        path_text = os.path.normcase(os.path.abspath(path))
        return os.path.commonpath((root_text, path_text)) == root_text
    except (OSError, RuntimeError, TypeError, ValueError):
        return False


def _read_lock_token(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise LockError("lock-release", str(exc)) from exc
