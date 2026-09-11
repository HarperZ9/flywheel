"""Test-only controlled admission for Index registry contention subprocesses."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import time
from typing import Callable

import harness.index_job_registry as registry
import harness.journey_lock as journey_lock

DEFAULT_ADMISSION_TIMEOUT_S = 10.0
DEFAULT_ADMISSION_POLL_S = 0.01
FIRST_SAVE_READY_NAME = ".index-concurrency-admission.first-save-ready"
SECOND_CONTENTION_NAME = ".index-concurrency-admission.second-contention"
FIRST_SAVE_READY_TEXT = "first-save-ready\n"
SECOND_CONTENTION_TEXT = "second-contention\n"


@dataclass(frozen=True)
class AdmissionMarkerPaths:
    first_save_ready: Path
    second_contention: Path


class AdmissionPreconditionError(RuntimeError):
    """The controlled subprocess rendezvous did not observe real contention."""


def marker_paths(run_root: Path | str) -> AdmissionMarkerPaths:
    root = Path(run_root)
    return AdmissionMarkerPaths(
        first_save_ready=root / FIRST_SAVE_READY_NAME,
        second_contention=root / SECOND_CONTENTION_NAME,
    )


def install_admission(
        run_root: Path | str,
        role: str,
        *,
        timeout_s: float = DEFAULT_ADMISSION_TIMEOUT_S,
        poll_s: float = DEFAULT_ADMISSION_POLL_S,
        read_text: Callable[[Path], str] | None = None,
        sleep: Callable[[float], None] | None = None,
) -> None:
    """Install a child-process admission hook for one subprocess role."""
    if timeout_s < 0:
        raise ValueError("timeout_s must not be negative")
    if poll_s < 0:
        raise ValueError("poll_s must not be negative")
    if role == "first":
        _install_first(run_root, timeout_s, poll_s, read_text, sleep)
        return
    if role == "second":
        _install_second(run_root)
        return
    raise ValueError("role must be 'first' or 'second'")


def _install_first(
        run_root: Path | str,
        timeout_s: float,
        poll_s: float,
        read_text: Callable[[Path], str] | None,
        sleep: Callable[[float], None] | None,
) -> None:
    original_save = registry._save_registry
    target_run_root = _resolve(Path(run_root))
    markers = marker_paths(run_root)
    read = read_text or _read_text
    sleeper = sleep or time.sleep

    def admitted_save(save_run_root, rows, *args, **kwargs):
        if _resolve(Path(save_run_root)) != target_run_root:
            return original_save(save_run_root, rows, *args, **kwargs)
        _write_marker(markers.first_save_ready, FIRST_SAVE_READY_TEXT)
        _wait_for_marker(
            markers.second_contention,
            SECOND_CONTENTION_TEXT,
            timeout_s,
            poll_s,
            read,
            sleeper,
        )
        return original_save(save_run_root, rows, *args, **kwargs)

    registry._save_registry = admitted_save


def _install_second(run_root: Path | str) -> None:
    original_try_lock = journey_lock._try_lock
    markers = marker_paths(run_root)
    target_lock_path = _resolve(registry._lock_path(run_root))
    marked = False

    def admitted_try_lock(stream, *args, **kwargs):
        nonlocal marked
        result = original_try_lock(stream, *args, **kwargs)
        if not marked and result is False and _stream_path(stream) == target_lock_path:
            _write_marker(markers.second_contention, SECOND_CONTENTION_TEXT)
            marked = True
        return result

    journey_lock._try_lock = admitted_try_lock


def _wait_for_marker(
        path: Path,
        expected_text: str,
        timeout_s: float,
        poll_s: float,
        read_text: Callable[[Path], str],
        sleep: Callable[[float], None],
) -> None:
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            if read_text(path) == expected_text:
                return
        except (FileNotFoundError, PermissionError):
            pass
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AdmissionPreconditionError(
                f"{path.name} was not written before the first save")
        sleep(min(poll_s, remaining))


def _write_marker(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _stream_path(stream) -> Path | None:
    name = getattr(stream, "name", None)
    if isinstance(name, (str, bytes, os.PathLike)):
        return _resolve(Path(name))
    return None


def _resolve(path: Path) -> Path:
    return path.resolve(strict=False)
