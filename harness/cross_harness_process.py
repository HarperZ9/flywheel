"""Bounded Windows process-tree ownership shared by harness adapters."""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Any, Mapping, Sequence

MAX_CAPTURE_BYTES = 1 << 20


@dataclass(frozen=True)
class ProcessOutcome:
    returncode: int
    stdout: str
    stderr: str
    elapsed_ms: int
    timed_out: bool
    malformed_output: bool = False


@dataclass(frozen=True)
class ProcessLaunch:
    argv: tuple[str, ...]
    cwd: Path
    stdin_bytes: bytes = field(repr=False)
    env: Mapping[str, str]
    shell: bool = False
    suspended: bool = True


def _child_env() -> dict[str, str]:
    keep = {
        "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "PATH", "TEMP", "TMP",
        "CODEX_HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "PROGRAMDATA",
        "LANG", "LC_ALL",
    }
    return {key: value for key, value in os.environ.items()
            if key.upper() in keep}


def _windows_job(proc: subprocess.Popen):
    import ctypes
    from ctypes import wintypes

    class Basic(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class Io(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class Extended(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", Io),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateJobObjectW.restype = wintypes.HANDLE
    api.SetInformationJobObject.argtypes = (
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
    api.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    api.CloseHandle.argtypes = (wintypes.HANDLE,)
    job, info = api.CreateJobObjectW(None, None), Extended()
    info.BasicLimitInformation.LimitFlags = 0x2000
    configured = job and api.SetInformationJobObject(
        job, 9, ctypes.byref(info), ctypes.sizeof(info))
    assigned = configured and api.AssignProcessToJobObject(
        job, wintypes.HANDLE(proc._handle))
    if not assigned:
        if job:
            api.CloseHandle(job)
        return None
    return api, job


def _resume_windows(proc: subprocess.Popen) -> bool:
    import ctypes
    api = ctypes.WinDLL("ntdll", use_last_error=True)
    api.NtResumeProcess.argtypes = (ctypes.c_void_p,)
    api.NtResumeProcess.restype = ctypes.c_long
    return api.NtResumeProcess(proc._handle) == 0


def _capture(pipe, bucket: dict[str, Any], key: str) -> None:
    data, overflow = bytearray(), False
    try:
        while chunk := pipe.read(65536):
            room = max(0, MAX_CAPTURE_BYTES - len(data))
            data.extend(chunk[:room])
            overflow |= len(chunk) > room
    except (OSError, ValueError):
        overflow = True
    finally:
        try:
            pipe.close()
        except OSError:
            pass
    bucket[key] = bytes(data), overflow


class OwnedProcess:
    """A suspended process already assigned to a kill-on-close Job Object."""

    def __init__(self, proc: subprocess.Popen, job, stdin_bytes: bytes) -> None:
        self._proc, self._job, self._stdin = proc, job, stdin_bytes
        self._started = time.perf_counter()
        self._captured: dict[str, Any] = {}
        self._readers: list[threading.Thread] = []
        self._writer: threading.Thread | None = None
        self._outcome: ProcessOutcome | None = None
        self._lock = threading.Lock()
        self.suspended = True

    def resume(self) -> bool:
        with self._lock:
            if not self.suspended:
                return self._proc.poll() is None
            self._start_io()
            if not _resume_windows(self._proc):
                self._close_job()
                return False
            self.suspended = False
            return True

    def signal_tree(self) -> bool:
        with self._lock:
            self._close_job()
        try:
            self._proc.wait(timeout=.5)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            try:
                self._proc.wait(timeout=.5)
            except subprocess.TimeoutExpired:
                return False
        return self._proc.poll() is not None

    def wait(self, timeout_s: float) -> ProcessOutcome | None:
        if self._outcome is not None:
            return self._outcome
        try:
            self._proc.wait(timeout=max(0.0, timeout_s))
        except subprocess.TimeoutExpired:
            return None
        with self._lock:
            self._close_job()
        self._join_io()
        self._outcome = self._build_outcome(False)
        return self._outcome

    def close(self) -> None:
        self.signal_tree()

    def _start_io(self) -> None:
        streams = ((self._proc.stdout, "stdout"), (self._proc.stderr, "stderr"))
        self._readers = [threading.Thread(
            target=_capture, args=(pipe, self._captured, key), daemon=True)
            for pipe, key in streams]
        for reader in self._readers:
            reader.start()

        def send() -> None:
            try:
                self._proc.stdin.write(self._stdin)
                self._proc.stdin.close()
            except (BrokenPipeError, OSError, ValueError):
                pass
        self._writer = threading.Thread(target=send, daemon=True)
        self._writer.start()

    def _join_io(self) -> None:
        if self._writer is not None:
            self._writer.join(.25)
        for reader in self._readers:
            reader.join(.5)

    def _close_job(self) -> None:
        if self._job is not None:
            api, handle = self._job
            self._job = None
            api.CloseHandle(handle)
        elif self._proc.poll() is None and self.suspended:
            self._proc.kill()

    def _build_outcome(self, timed_out: bool) -> ProcessOutcome:
        values, malformed = [], False
        for key in ("stdout", "stderr"):
            raw, overflow = self._captured.get(key, (b"", True))
            try:
                values.append(raw.decode("utf-8", "strict"))
            except UnicodeDecodeError:
                values.append("")
                overflow = True
            malformed |= overflow
        elapsed = max(0, round((time.perf_counter() - self._started) * 1000))
        code = -1 if timed_out else int(self._proc.returncode)
        return ProcessOutcome(code, values[0], values[1], elapsed,
                              timed_out, malformed)


def start_owned_process(argv: Sequence[str], *, cwd: Path, stdin_bytes: bytes,
                        env: Mapping[str, str]) -> OwnedProcess:
    if sys.platform.startswith("linux"):
        raise OSError("Linux provider containment unavailable")
    if os.name != "nt":
        raise OSError("robust process containment unavailable")
    options: dict[str, Any] = {
        "cwd": str(cwd), "env": dict(env), "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "shell": False,
        "close_fds": True,
        "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | 0x4,
    }
    proc = subprocess.Popen(tuple(argv), **options)
    job = _windows_job(proc)
    if job is None:
        proc.kill()
        proc.wait(timeout=.5)
        raise OSError("Windows process containment unavailable")
    return OwnedProcess(proc, job, bytes(stdin_bytes))


def run_process(argv: list[str], *, cwd: Path, stdin_text: str,
                timeout_seconds: float) -> ProcessOutcome:
    owned = start_owned_process(argv, cwd=cwd,
                                stdin_bytes=stdin_text.encode("utf-8"),
                                env=_child_env())
    if not owned.resume():
        owned.close()
        raise OSError("Windows suspended process could not be resumed")
    outcome = owned.wait(timeout_seconds)
    if outcome is not None:
        return outcome
    owned.signal_tree()
    owned.wait(.5)
    return owned._build_outcome(True)
