"""budget.py: run one command with a wall-clock limit and a memory limit.

Windows: the process is put in a Job Object with a job-wide memory limit and
kill-on-close; at the time limit the whole job (the process and everything it
started) is terminated, and the job's peak memory is read back. The process is
assigned to the job right after it starts, so a child it spawns in its first
instant can escape the job; plexus's own tools do not do that.
POSIX: the process gets RLIMIT_AS in its own session; at the time limit the
session is killed. Peak memory is the child's ru_maxrss. macOS refuses
RLIMIT_AS, so there the limit is recorded with memory_enforced false.
Output goes straight to files, so a chatty tool cannot block on a full pipe.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

_MB = 1024 * 1024


def _win_job(memory_mb: int):
    import ctypes
    from ctypes import wintypes as wt

    class BASIC(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wt.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wt.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wt.DWORD), ("SchedulingClass", wt.DWORD)]

    class IO(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in ("r", "w", "o", "rb", "wb", "ob")]

    class EXT(ctypes.Structure):
        _fields_ = [("Basic", BASIC), ("Io", IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.restype = wt.HANDLE
    k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wt.LPCWSTR]
    k32.SetInformationJobObject.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD]
    k32.QueryInformationJobObject.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD, ctypes.c_void_p]
    k32.AssignProcessToJobObject.argtypes = [wt.HANDLE, wt.HANDLE]
    k32.TerminateJobObject.argtypes = [wt.HANDLE, wt.UINT]
    k32.CloseHandle.argtypes = [wt.HANDLE]
    job = k32.CreateJobObjectW(None, None)
    if not job:
        raise OSError(ctypes.get_last_error(), "CreateJobObject failed")
    info = EXT()
    info.Basic.LimitFlags = 0x200 | 0x2000          # JOB_MEMORY | KILL_ON_JOB_CLOSE
    info.JobMemoryLimit = memory_mb * _MB
    if not k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
        raise OSError(ctypes.get_last_error(), "SetInformationJobObject failed")

    def peak() -> float:
        q = EXT()
        k32.QueryInformationJobObject(job, 9, ctypes.byref(q), ctypes.sizeof(q), None)
        return q.PeakJobMemoryUsed / _MB

    return k32, job, peak


def run(argv: list, *, cwd: "str | None", env: "dict | None", time_s: float, memory_mb: int,
        stdout_path: str, stderr_path: str) -> dict:
    """Run argv under the budget. Never raises for the tool's own failure."""
    res = {"exit_code": None, "seconds": 0.0, "timed_out": False, "memory_limit_mb": memory_mb,
           "memory_enforced": True,
           "peak_mb": None, "memory_exceeded": False, "error": ""}
    full_env = dict(os.environ)
    full_env.update(env or {})
    t0 = time.perf_counter()
    with open(stdout_path, "wb") as out, open(stderr_path, "wb") as err:
        try:
            if sys.platform == "win32":
                _run_windows(argv, cwd, full_env, time_s, memory_mb, out, err, res)
            else:
                _run_posix(argv, cwd, full_env, time_s, memory_mb, out, err, res)
        except (OSError, ValueError, subprocess.SubprocessError) as e:
            res["error"] = f"could not start: {type(e).__name__}: {e}"
    res["seconds"] = round(time.perf_counter() - t0, 3)
    if res["peak_mb"] is not None:
        res["peak_mb"] = round(res["peak_mb"], 1)
        res["memory_exceeded"] = res["peak_mb"] >= 0.97 * memory_mb
    return res


def _run_windows(argv, cwd, env, time_s, memory_mb, out, err, res):
    k32, job, peak = _win_job(memory_mb)
    try:
        proc = subprocess.Popen(argv, cwd=cwd, env=env, stdout=out, stderr=err,
                                stdin=subprocess.DEVNULL,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        k32.AssignProcessToJobObject(job, int(proc._handle))
        try:
            res["exit_code"] = proc.wait(timeout=time_s)
        except subprocess.TimeoutExpired:
            res["timed_out"] = True
            k32.TerminateJobObject(job, 1)
            res["exit_code"] = proc.wait(timeout=10)
        res["peak_mb"] = peak()
    finally:
        k32.CloseHandle(job)


def _run_posix(argv, cwd, env, time_s, memory_mb, out, err, res):
    import resource
    import signal

    def limit():                                      # runs in the child before exec
        resource.setrlimit(resource.RLIMIT_AS, (memory_mb * _MB, memory_mb * _MB))

    enforce = sys.platform != "darwin"                # macOS refuses RLIMIT_AS
    res["memory_enforced"] = enforce
    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdout=out, stderr=err,
                            stdin=subprocess.DEVNULL, start_new_session=True,
                            preexec_fn=limit if enforce else None)
    deadline = time.monotonic() + time_s
    while True:
        pid, status, usage = os.wait4(proc.pid, os.WNOHANG)
        if pid:
            proc.returncode = os.waitstatus_to_exitcode(status)
            break
        if time.monotonic() >= deadline:
            res["timed_out"] = True
            os.killpg(proc.pid, signal.SIGKILL)
            pid, status, usage = os.wait4(proc.pid, 0)
            proc.returncode = os.waitstatus_to_exitcode(status)
            break
        time.sleep(0.02)
    res["exit_code"] = proc.returncode
    scale = 1 if sys.platform == "darwin" else 1024      # bytes on macOS, KiB on Linux
    res["peak_mb"] = usage.ru_maxrss * scale / _MB
