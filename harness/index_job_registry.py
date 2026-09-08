"""Cross-process registry for durable Index workspace-map jobs."""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import threading
import time
from typing import Any, Iterator
from uuid import uuid4

from .journey_lock import ExclusiveJourneyLock, JourneyLockBusy, fsync_directory

SCHEMA = "flywheel.index-workspace-map-job/v1"
DEFAULT_LOCK_TIMEOUT_S = 2.0


class IndexRegistryError(RuntimeError):
    """Fixed, host-detail-free failure for Index job registry mutations."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class IndexRegistryBusy(IndexRegistryError):
    def __init__(self) -> None:
        super().__init__("INDEX_REGISTRY_BUSY")


class IndexRegistryCommitFailed(IndexRegistryError):
    def __init__(self) -> None:
        super().__init__("INDEX_REGISTRY_COMMIT_FAILED")


def registry_path(run_root: Path | str) -> Path:
    return Path(run_root) / "index-workspace-map-jobs.json"


def _lock_path(run_root: Path | str) -> Path:
    path = registry_path(run_root)
    return path.with_name(f".{path.name}.lock")


def _registry(run_root: Path | str) -> dict[str, dict[str, Any]]:
    path = registry_path(run_root)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    rows = doc.get("roots") if isinstance(doc, dict) else None
    return rows if isinstance(rows, dict) else {}


def _retry_windows_permission(deadline: float) -> None:
    if os.name != "nt" or time.monotonic() >= deadline:
        raise IndexRegistryBusy() from None
    time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))


def _replace_with_retry(source: Path, target: Path) -> None:
    deadline = time.monotonic() + DEFAULT_LOCK_TIMEOUT_S
    while True:
        try:
            os.replace(source, target)
            return
        except PermissionError:
            _retry_windows_permission(deadline)


def _fsync_file_with_retry(path: Path) -> None:
    deadline = time.monotonic() + DEFAULT_LOCK_TIMEOUT_S
    while True:
        try:
            with path.open("r+b") as stream:
                os.fsync(stream.fileno())
            return
        except PermissionError:
            _retry_windows_permission(deadline)


def _save_registry(run_root: Path | str,
                   rows: dict[str, dict[str, Any]]) -> None:
    path = registry_path(run_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.{uuid4().hex}.tmp")
    try:
        with tmp.open("xb") as stream:
            stream.write(json.dumps(
                {"schema": SCHEMA, "roots": rows},
                indent=1,
                sort_keys=True,
            ).encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        _replace_with_retry(tmp, path)
        _fsync_file_with_retry(path)
        fsync_directory(path.parent)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


@contextmanager
def locked_registry(
    run_root: Path | str,
    timeout_s: float = DEFAULT_LOCK_TIMEOUT_S,
) -> Iterator[dict[str, dict[str, Any]]]:
    try:
        with ExclusiveJourneyLock.acquire(_lock_path(run_root), timeout_s):
            rows = _registry(run_root)
            yield rows
            _save_registry(run_root, rows)
    except JourneyLockBusy:
        raise IndexRegistryBusy() from None
    except IndexRegistryBusy:
        raise
    except (OSError, ValueError, TypeError):
        raise IndexRegistryCommitFailed() from None
