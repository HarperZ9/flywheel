"""Byte-safe capture, timeout, and atomic staging for acceptance receipts."""

from __future__ import annotations

import ctypes
import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from time import monotonic


TIMEOUT_EXIT_CODE = 124
LAUNCH_EXIT_CODE = 127
STREAM_JOIN_GRACE_SECONDS = 2.0
_SENSITIVE_NAME = re.compile(
    r"(?:AUTHORIZATION|API[_-]?KEY|ACCESS[_-]?KEY|SECRET|TOKEN|PASSWORD|PASSWD|CREDENTIAL|PRIVATE[_-]?KEY)",
    re.IGNORECASE,
)
_SENSITIVE_ASSIGNMENT = re.compile(
    br"\b(authorization|api[_-]?key|access[_-]?key|secret|token|password|passwd|credential)"
    br"(\s*[:=]\s*)([^\s,;]+)",
    re.IGNORECASE,
)
_BEARER = re.compile(br"\bBearer\s+[^\s,;]+", re.IGNORECASE)
_PRIVATE_KEY = re.compile(
    br"-----BEGIN [^-\r\n]*PRIVATE KEY-----.*?(?:-----END [^-\r\n]*PRIVATE KEY-----|\Z)",
    re.DOTALL,
)


def sensitive_name(name: str) -> bool:
    return bool(_SENSITIVE_NAME.search(name))


def _marker(secrets: list[bytes]) -> bytes:
    for candidate in (b"<redacted>", b"[masked]", b"***", b""):
        if all(secret not in candidate for secret in secrets):
            return candidate
    return b""


def redact_bytes(data: bytes, secrets: list[bytes]) -> tuple[bytes, int]:
    marker = _marker(secrets)
    redacted = data
    replacements = 0
    for secret in sorted({item for item in secrets if item}, key=len, reverse=True):
        count = redacted.count(secret)
        if count:
            redacted = redacted.replace(secret, marker)
            replacements += count
    redacted, count = _PRIVATE_KEY.subn(marker, redacted)
    replacements += count
    redacted, count = _BEARER.subn(b"Bearer " + marker, redacted)
    replacements += count

    def assignment(match: re.Match[bytes]) -> bytes:
        return match.group(1) + match.group(2) + marker

    redacted, count = _SENSITIVE_ASSIGNMENT.subn(assignment, redacted)
    return redacted, replacements + count


def redact_text(text: str, secrets: list[bytes]) -> tuple[str, int]:
    redacted, count = redact_bytes(text.encode("utf-8"), secrets)
    return redacted.decode("utf-8"), count


def argv_secret_values(argv: list[str]) -> list[bytes]:
    values: set[bytes] = set()
    for index, item in enumerate(argv):
        option, separator, value = item.partition("=")
        if option.startswith("-") and sensitive_name(option):
            candidate = value if separator else (argv[index + 1] if index + 1 < len(argv) else "")
            if candidate:
                values.add(candidate.encode("utf-8"))
    return sorted(values, key=len, reverse=True)


def redact_argv(argv: list[str], secrets: list[bytes]) -> tuple[list[str], int]:
    marker = _marker(secrets).decode("ascii")
    output: list[str] = []
    replacements = 0
    hide_next = False
    for item in argv:
        if hide_next:
            output.append(marker)
            replacements += 1
            hide_next = False
            continue
        option, separator, _value = item.partition("=")
        if option.startswith("-") and sensitive_name(option):
            output.append(f"{option}={marker}" if separator else option)
            replacements += int(bool(separator))
            hide_next = not separator
            continue
        value, count = redact_text(item, secrets)
        output.append(value)
        replacements += count
    return output, replacements


def _read_stream(pipe, keep_bytes: int, sink: dict[str, object]) -> None:
    """Drain a child pipe into `sink`, publishing as it goes.

    Two properties matter on the timeout path, where the child is killed and
    this thread may never reach its end:

      - `read1` returns what the OS already has instead of blocking until the
        full request or EOF, so a line the child flushed before it was killed
        is captured when it is written, not lost waiting for more,
      - the sink is updated after every chunk, so whatever was read is
        readable by the caller even while this thread is still running or is
        torn down mid-read. Publishing only at the end discarded exactly the
        evidence a timeout receipt exists to preserve.
    """
    captured = bytearray()
    observed = 0
    # read1 is the BufferedReader single-syscall read; fall back for any
    # pipe object that does not offer it.
    read = getattr(pipe, "read1", None) or pipe.read
    try:
        while True:
            chunk = read(65_536)
            if not chunk:
                break
            observed += len(chunk)
            remaining = keep_bytes - len(captured)
            if remaining > 0:
                captured.extend(chunk[:remaining])
            sink["captured"] = bytes(captured)
            sink["observed"] = observed
    except (OSError, ValueError):
        pass
    finally:
        try:
            pipe.close()
        except OSError:
            pass
        sink["captured"] = bytes(captured)
        sink["observed"] = observed


def _windows_job(process: subprocess.Popen) -> tuple[object, object] | None:
    if os.name != "nt":
        return None
    from ctypes import wintypes

    class BasicLimits(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
        )]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimits), ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return None
    limits = ExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    configured = kernel32.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits))
    assigned = configured and kernel32.AssignProcessToJobObject(job, wintypes.HANDLE(int(process._handle)))
    if not assigned:
        kernel32.CloseHandle(job)
        return None
    return kernel32, job


def _close_job(job: tuple[object, object] | None) -> None:
    if job:
        job[0].CloseHandle(job[1])


def _terminate_tree(process: subprocess.Popen, job: tuple[object, object] | None) -> None:
    if job:
        job[0].TerminateJobObject(job[1], TIMEOUT_EXIT_CODE)
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5, check=False,
        )
        try:
            os.kill(process.pid, signal.CTRL_BREAK_EVENT)
        except (OSError, ValueError):
            pass
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass
    if process.poll() is None:
        process.kill()


def _join_until(threads: list[threading.Thread], deadline: float) -> bool:
    for thread in threads:
        thread.join(max(0.0, deadline - monotonic()))
    return not any(thread.is_alive() for thread in threads)


def capture_command(argv: list[str], cwd: Path, timeout_seconds: float, keep_bytes: int) -> dict[str, object]:
    stdout_sink: dict[str, object] = {"captured": b"", "observed": 0}
    stderr_sink: dict[str, object] = {"captured": b"", "observed": 0}
    options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    try:
        process = subprocess.Popen(
            argv, cwd=cwd, env=dict(os.environ), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            shell=False, **options,
        )
    except (OSError, ValueError) as exc:
        error = f"{type(exc).__name__}: {exc}".encode("utf-8", errors="replace")
        return {"exit_code": LAUNCH_EXIT_CODE, "child_exit_code": None, "outcome": "LAUNCH_FAILED",
                "timed_out": False, "launch_error": True, "stdout": stdout_sink,
                "stderr": {"captured": error, "observed": len(error)}, "capture_complete": True}

    assert process.stdout is not None and process.stderr is not None
    job = _windows_job(process)
    threads = [threading.Thread(target=_read_stream, args=(pipe, keep_bytes, sink), daemon=True)
               for pipe, sink in ((process.stdout, stdout_sink), (process.stderr, stderr_sink))]
    for thread in threads:
        thread.start()
    deadline = monotonic() + timeout_seconds
    timed_out = False
    try:
        try:
            process.wait(timeout=max(0.001, deadline - monotonic()))
        except subprocess.TimeoutExpired:
            timed_out = True
        if not timed_out and not _join_until(threads, deadline):
            timed_out = True
        if timed_out:
            _terminate_tree(process, job)
            try:
                process.wait(timeout=STREAM_JOIN_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
            _join_until(threads, monotonic() + STREAM_JOIN_GRACE_SECONDS)
        capture_complete = not any(thread.is_alive() for thread in threads)
        if not capture_complete:
            for pipe in (process.stdout, process.stderr):
                try:
                    pipe.close()
                except OSError:
                    pass
            _join_until(threads, monotonic() + 0.25)
            capture_complete = not any(thread.is_alive() for thread in threads)
    finally:
        _close_job(job)
    return {"exit_code": TIMEOUT_EXIT_CODE if timed_out else int(process.returncode or 0),
            "child_exit_code": process.returncode, "outcome": "TIMED_OUT" if timed_out else "EXITED",
            "timed_out": timed_out, "launch_error": False, "stdout": stdout_sink,
            "stderr": stderr_sink, "capture_complete": capture_complete}


@contextmanager
def staged_receipt_directory(final: Path):
    if final.exists():
        raise FileExistsError(f"receipt already exists: {final}")
    final.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{final.name}.tmp-", dir=final.parent))
    published = False
    try:
        yield stage
        if final.exists():
            raise FileExistsError(f"receipt already exists: {final}")
        os.rename(stage, final)
        published = True
    finally:
        if not published and stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
