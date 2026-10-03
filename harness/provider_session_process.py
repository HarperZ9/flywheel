"""Persistent stdio process ownership for native provider sessions."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import BinaryIO, Mapping, Sequence

from . import cross_harness_process as boundary

CREATE_SUSPENDED = 0x4
CREATE_NO_WINDOW = 0x08000000
DEFAULT_STDERR_LIMIT = 65536


class ProviderSessionProcessError(RuntimeError):
    """Sanitized provider-session process launch failure."""


@dataclass(frozen=True)
class ProviderSessionCleanup:
    pid: int
    returncode: int | None
    exited: bool
    job_closed: bool
    stderr_observed_bytes: int
    stderr_truncated: bool
    stderr_drain_complete: bool
    elapsed_ms: int
    stderr_raw: None = None


class _StderrState:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.observed = 0
        self.truncated = False
        self.lock = threading.Lock()

    def add(self, size: int) -> None:
        with self.lock:
            self.observed += size
            if self.observed > self.limit:
                self.truncated = True

    def snapshot(self) -> tuple[int, bool]:
        with self.lock:
            return self.observed, self.truncated


class ProviderSessionProcess:
    """A resumed process already assigned to a kill-on-close Job Object."""

    def __init__(self, proc: subprocess.Popen, job, *,
                 stderr_limit: int) -> None:
        if proc.stdin is None or proc.stdout is None or proc.stderr is None:
            raise ProviderSessionProcessError("provider process pipes unavailable")
        self._proc = proc
        self._job = job
        self._cond = threading.Condition(threading.Lock())
        self._started = time.perf_counter()
        self._cleanup: ProviderSessionCleanup | None = None
        self._last_cleanup: ProviderSessionCleanup | None = None
        self._closing = False
        self._job_closed = False
        self._stderr = _StderrState(stderr_limit)
        self.stdin: BinaryIO = proc.stdin
        self.stdout: BinaryIO = proc.stdout
        self.pid = int(getattr(proc, "pid", 0) or 0)
        self._stderr_thread = threading.Thread(
            target=_drain_stderr, args=(proc.stderr, self._stderr),
            daemon=True)
        self._stderr_thread.start()

    def close(self, *, timeout_s: float = 2.0) -> ProviderSessionCleanup:
        with self._cond:
            if self._cleanup is not None:
                return self._cleanup
            if self._closing:
                while self._closing:
                    self._cond.wait()
                return self._cleanup or self._last_cleanup
            self._closing = True
        cleanup: ProviderSessionCleanup | None = None
        try:
            cleanup = self._close_once(timeout_s)
        except Exception:
            cleanup = self._failed_cleanup()
        finally:
            if cleanup is None:
                cleanup = self._failed_cleanup()
            with self._cond:
                self._last_cleanup = cleanup
                if _cleanup_complete(cleanup):
                    self._cleanup = cleanup
                self._closing = False
                self._cond.notify_all()
        return cleanup

    def _close_once(self, timeout_s: float) -> ProviderSessionCleanup:
        job_closed = self._close_job_once()
        if not job_closed:
            _terminate(self._proc)
        exited = _wait_or_kill(self._proc, timeout_s)
        self._stderr_thread.join(min(max(float(timeout_s), 0.0), 1.0))
        observed, truncated = self._stderr.snapshot()
        return ProviderSessionCleanup(
            pid=self.pid,
            returncode=self._proc.poll(),
            exited=exited,
            job_closed=job_closed,
            stderr_observed_bytes=observed,
            stderr_truncated=truncated,
            stderr_drain_complete=not self._stderr_thread.is_alive(),
            elapsed_ms=max(0, round((time.perf_counter() - self._started) * 1000)),
        )

    def _failed_cleanup(self) -> ProviderSessionCleanup:
        try:
            observed, truncated = self._stderr.snapshot()
        except Exception:
            observed, truncated = 0, True
        try:
            returncode = self._proc.poll()
        except Exception:
            returncode = None
        return ProviderSessionCleanup(
            pid=self.pid,
            returncode=returncode,
            exited=returncode is not None,
            job_closed=self._job_closed,
            stderr_observed_bytes=observed,
            stderr_truncated=truncated,
            stderr_drain_complete=not self._stderr_thread.is_alive(),
            elapsed_ms=max(0, round((time.perf_counter() - self._started) * 1000)),
        )

    def _close_job_once(self) -> bool:
        if self._job_closed:
            return True
        if self._job is None:
            return False
        api, handle = self._job
        try:
            closed = bool(api.CloseHandle(handle))
        except Exception:
            return False
        if closed:
            self._job = None
            self._job_closed = True
        return closed


def start_provider_session_process(
        argv: Sequence[str], *, cwd: Path | str, env: Mapping[str, str],
        stderr_limit: int = DEFAULT_STDERR_LIMIT, before_resume=None) -> ProviderSessionProcess:
    """Start a persistent stdio provider process inside a Windows Job Object."""
    if os.name != "nt" or not sys.platform.startswith("win"):
        raise ProviderSessionProcessError(
            "provider session process containment unavailable")
    if before_resume is not None and not callable(before_resume):
        raise ProviderSessionProcessError('invalid provider prelaunch check')
    args, cwd_path, env_dict = _validated_launch(argv, cwd, env)
    proc = None
    job = None
    try:
        proc = subprocess.Popen(args, cwd=str(cwd_path), env=env_dict,
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                shell=False, close_fds=True,
                                creationflags=_creation_flags())
        job = boundary._windows_job(proc)
        if job is None:
            _terminate(proc)
            raise ProviderSessionProcessError(
                "provider session process containment unavailable")
        try:
            owned = ProviderSessionProcess(proc, job, stderr_limit=stderr_limit)
        except Exception:
            _close_job(job)
            _close_process_pipes(proc)
            _terminate(proc)
            raise ProviderSessionProcessError(
                "provider session process launch failed") from None
        from .provider_session_prelaunch import verify_before_resume
        verify_before_resume(owned, before_resume)
        if not boundary._resume_windows(proc):
            owned._close_job_once()
            _close_process_pipes(proc)
            _terminate(proc)
            raise ProviderSessionProcessError(
                "provider session process resume failed")
        return owned
    except ProviderSessionProcessError:
        raise
    except Exception:
        if job is not None:
            _close_job(job)
        if proc is not None:
            _terminate(proc)
        raise ProviderSessionProcessError(
            "provider session process launch failed") from None


def _validated_launch(
        argv: Sequence[str], cwd: Path | str,
        env: Mapping[str, str]) -> tuple[tuple[str, ...], Path, dict[str, str]]:
    if isinstance(argv, (str, bytes)) or not argv:
        raise ProviderSessionProcessError("invalid provider process launch")
    args = tuple(str(item) for item in argv)
    if any(not item for item in args):
        raise ProviderSessionProcessError("invalid provider process launch")
    cwd_path = Path(cwd)
    if not cwd_path.is_absolute() or not cwd_path.is_dir():
        raise ProviderSessionProcessError("invalid provider process launch")
    if not isinstance(env, Mapping):
        raise ProviderSessionProcessError("invalid provider process launch")
    env_dict = {str(key): str(value) for key, value in env.items()}
    return args, cwd_path, env_dict


def _creation_flags() -> int:
    return (getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) |
            CREATE_SUSPENDED |
            getattr(subprocess, "CREATE_NO_WINDOW", CREATE_NO_WINDOW))


def _drain_stderr(pipe, state: _StderrState) -> None:
    try:
        while True:
            chunk = getattr(pipe, "read1", pipe.read)(65536)
            if not chunk:
                return
            state.add(len(chunk))
    except Exception:
        state.add(state.limit + 1)
    finally:
        _close_quietly(pipe)


def _wait_or_kill(proc: subprocess.Popen, timeout_s: float) -> bool:
    try:
        proc.wait(timeout=max(float(timeout_s), 0.0))
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except Exception:
            pass
        try:
            proc.wait(timeout=0.5)
        except Exception:
            return proc.poll() is not None
    return proc.poll() is not None


def _cleanup_complete(cleanup: ProviderSessionCleanup) -> bool:
    return (cleanup.exited and cleanup.job_closed and
            cleanup.stderr_drain_complete)


def _close_job(job) -> bool:
    try:
        return bool(job[0].CloseHandle(job[1]))
    except Exception:
        return False


def _terminate(proc) -> None:
    try:
        boundary._terminate_unowned(proc)
    except Exception:
        pass


def _close_quietly(stream) -> None:
    try:
        if stream is not None:
            stream.close()
    except Exception:
        pass


def _close_process_pipes(proc) -> None:
    for stream in (getattr(proc, "stdin", None), getattr(proc, "stdout", None),
                   getattr(proc, "stderr", None)):
        _close_quietly(stream)
