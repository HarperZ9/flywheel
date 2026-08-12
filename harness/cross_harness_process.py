"""Bounded, contained subprocess execution for cross-harness providers."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat
import subprocess
import sys
import threading
import time
from typing import Any, Callable
from .cross_harness_linux import prepare_linux_cgroup, run_linux_process

MAX_CAPTURE_BYTES = 1 << 20


@dataclass(frozen=True)
class ProcessOutcome:
    returncode: int
    stdout: str
    stderr: str
    output_text: str
    elapsed_ms: int
    timed_out: bool
    malformed_output: bool = False


def _child_env() -> dict[str, str]:
    keep = {
        "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "PATH", "TEMP", "TMP",
        "CODEX_HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "PROGRAMDATA",
        "LANG", "LC_ALL",
    }
    return {key: value for key, value in os.environ.items() if key.upper() in keep}


def _windows_job(proc: subprocess.Popen):
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    class Basic(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class Io(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
        )]

    class Extended(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", Basic), ("IoInfo", Io),
            ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateJobObjectW.restype = wintypes.HANDLE
    api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    job, info = api.CreateJobObjectW(None, None), Extended()
    info.BasicLimitInformation.LimitFlags = 0x2000  # kill every member on close
    configured = job and api.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
    assigned = configured and api.AssignProcessToJobObject(job, wintypes.HANDLE(proc._handle))
    if not assigned:
        if job:
            api.CloseHandle(job)
        return None
    return api, job


def _resume_windows(proc: subprocess.Popen) -> bool:
    if os.name != "nt":
        return True
    import ctypes
    api = ctypes.WinDLL("ntdll", use_last_error=True)
    api.NtResumeProcess.argtypes = [ctypes.c_void_p]
    api.NtResumeProcess.restype = ctypes.c_long
    return api.NtResumeProcess(proc._handle) == 0


def _stop_tree(proc: subprocess.Popen, job=None) -> None:
    if job:
        try:
            job[0].CloseHandle(job[1])
        except OSError:
            pass
    elif proc.poll() is None:
        proc.kill()
    try:
        proc.wait(timeout=.5)
    except subprocess.TimeoutExpired:
        proc.kill()


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


def _decode(raw: bytes) -> tuple[str, bool]:
    try:
        return raw.decode("utf-8", "strict"), False
    except UnicodeDecodeError:
        return "", True


def _remove_stage(path: Path) -> bool:
    try:
        mode = path.lstat().st_mode
        if stat.S_ISDIR(mode) and not stat.S_ISLNK(mode):
            path.rmdir()
        else:
            path.unlink()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return True


def _read_stage(path: Path) -> tuple[bytes, bool]:
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode) or before.st_nlink != 1:
            return b"", True
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                return b"", True
            with os.fdopen(descriptor, "rb", closefd=False) as handle:
                raw = handle.read(MAX_CAPTURE_BYTES + 1)
            return raw[:MAX_CAPTURE_BYTES], len(raw) > MAX_CAPTURE_BYTES
        finally:
            os.close(descriptor)
    except FileNotFoundError:
        return b"", False
    except OSError:
        return b"", True


def run_process(argv: list[str], *, cwd: Path, stdin_text: str, timeout_seconds: float,
                output_path: Path, sanitizer: Callable[[Any], Any]) -> ProcessOutcome:
    linux = sys.platform.startswith("linux")
    if os.name != "nt" and not linux:
        raise OSError("robust process containment unavailable")
    if not _remove_stage(output_path):
        raise OSError("provider output staging path is not safely removable")
    options: dict[str, Any] = {
        "cwd": str(cwd), "env": _child_env(), "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "shell": False,
    }
    group = prepare_linux_cgroup() if linux else None
    if os.name == "nt" and not linux:
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | 0x4  # CREATE_SUSPENDED
    else:
        argv = group.wrap(argv)
    started = time.perf_counter()
    try:
        proc = subprocess.Popen(argv, **options)
    except Exception:
        if group: group.kill_and_remove()
        raise
    job = _windows_job(proc)
    if os.name == "nt" and not linux and job is None:
        _stop_tree(proc)
        _remove_stage(output_path)
        raise OSError("Windows process containment unavailable")
    if os.name == "nt" and not linux and not _resume_windows(proc):
        _stop_tree(proc, job)
        _remove_stage(output_path)
        raise OSError("Windows suspended process could not be resumed")

    try:
        if linux:
            captured, timed_out = run_linux_process(proc, group, stdin_text.encode("utf-8"), started + timeout_seconds)
        else:
            captured, timed_out = _run_windows_process(proc, job, stdin_text, started + timeout_seconds)
    except Exception:
        _remove_stage(output_path)
        raise

    output_raw, output_over = _read_stage(output_path)
    cleanup_ok = _remove_stage(output_path)
    stdout, stdout_over = captured.get("stdout", (b"", True))
    stderr, stderr_over = captured.get("stderr", (b"", True))
    stdout_text, bad_stdout = _decode(stdout)
    stderr_text, bad_stderr = _decode(stderr)
    output_text, bad_output = _decode(output_raw)
    malformed = stdout_over or stderr_over or output_over or bad_stdout or bad_stderr or bad_output or not cleanup_ok
    elapsed = max(0, round((time.perf_counter() - started) * 1000))
    return ProcessOutcome(proc.returncode if not timed_out else -1, stdout_text, stderr_text,
                          sanitizer(output_text), elapsed, timed_out, malformed)


def _run_windows_process(proc: subprocess.Popen, job, stdin_text: str, deadline: float) -> tuple[dict[str, Any], bool]:
    captured: dict[str, Any] = {}
    streams = ((proc.stdout, "stdout"), (proc.stderr, "stderr"))
    readers = [threading.Thread(target=_capture, args=(pipe, captured, key), daemon=True)
               for pipe, key in streams]
    for reader in readers:
        reader.start()

    def send_stdin() -> None:
        try:
            proc.stdin.write(stdin_text.encode("utf-8"))
            proc.stdin.close()
        except (BrokenPipeError, OSError, ValueError):
            pass

    writer = threading.Thread(target=send_stdin, daemon=True)
    writer.start()
    try:
        remaining = max(.001, deadline - time.perf_counter())
        proc.wait(timeout=remaining)
        timed_out = False
    except subprocess.TimeoutExpired:
        timed_out = True
    _stop_tree(proc, job)
    try:
        proc.stdin.close()
    except (OSError, ValueError):
        pass
    writer.join(.25)
    for reader, pipe, key in zip(readers, (proc.stdout, proc.stderr), ("stdout", "stderr")):
        reader.join(.5)
        if reader.is_alive():
            captured.setdefault(key, (b"", True))
            try:
                pipe.close()
            except (OSError, ValueError):
                pass
            reader.join(.25)

    return captured, timed_out
