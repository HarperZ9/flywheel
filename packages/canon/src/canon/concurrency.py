from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import concurrency_lock as _locks
from .source_state import SourceStateItem, assert_source_state

LockError = _locks.LockError
LockError.__module__ = __name__


@dataclass(frozen=True, slots=True, weakref_slot=True)
class RunLock:
    root: Path
    name: str
    token: str
    path: Path

    def __post_init__(self) -> None:
        if not isinstance(self.root, Path) or not isinstance(self.path, Path):
            raise LockError("invalid-lock", "root and path must be Path")
        _locks.validate_lock_name(self.name)
        if not isinstance(self.token, str) or self.token == "" or _locks.has_control(self.token):
            raise LockError("invalid-lock", "token must be non-empty text")


def acquire_run_lock(root: str | Path, name: str) -> RunLock:
    checked_name = _locks.validate_lock_name(name)
    root_path = _locks.resolve_lock_root(root)
    lock_dir = _locks.prepare_lock_dir(root_path)
    token = _locks.new_lock_token()
    lock_path, capability = _locks.write_new_lock(lock_dir, f"{checked_name}.lock", token)
    try:
        lock = RunLock(root=root_path, name=checked_name, token=token, path=lock_path)
    except Exception:
        _locks.discard_lock(capability)
        raise
    _locks.register_lock(lock, capability)
    return lock


def release_run_lock(lock: RunLock) -> None:
    if type(lock) is not RunLock:
        raise LockError("invalid-lock", "lock must be RunLock")
    _locks.release_lock(lock, lock.root, lock.name, lock.token, lock.path)


def guarded_commit(
    expected_source_state: str,
    current_items: tuple[SourceStateItem, ...],
    commit: Callable[[], object],
) -> object:
    assert_source_state(expected_source_state, current_items)
    if not callable(commit):
        raise LockError("invalid-commit", "commit must be callable")
    return commit()
