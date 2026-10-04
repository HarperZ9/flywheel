"""lean_sandbox_win.py -- the Windows half of harness/lean_sandbox.py.

Starts the compile with a restricted low-integrity token (the helpers in
harness/windows_low_integrity.py), suspended, inside a job object that carries
the memory, CPU time, process count and UI limits, then resumes it. Assigning
the job before the first instruction runs means no child the candidate starts
escapes the limits. Closing the job kills whatever is left.
"""
from __future__ import annotations

import ctypes
import subprocess
from ctypes import wintypes
from pathlib import Path

from . import windows_low_integrity as wli

JOB_OBJECT_LIMIT_JOB_TIME = 0x00000004
JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION = 0x00000400
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_BASIC_ACCOUNTING = 1
JOB_BASIC_UI_RESTRICTIONS = 4
JOB_EXTENDED_LIMITS = 9
#: Desktop, display settings, exit windows, global atoms, user handles, read
#: and write clipboard, system parameters.
UI_LIMIT_ALL = 0xFF


class BASIC_ACCOUNTING(ctypes.Structure):
    _fields_ = (("TotalUserTime", ctypes.c_longlong),
                ("TotalKernelTime", ctypes.c_longlong),
                ("ThisPeriodTotalUserTime", ctypes.c_longlong),
                ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
                ("TotalPageFaultCount", wintypes.DWORD),
                ("TotalProcesses", wintypes.DWORD),
                ("ActiveProcesses", wintypes.DWORD),
                ("TotalTerminatedProcesses", wintypes.DWORD))


_k = wli.kernel
_k.QueryInformationJobObject.argtypes = (
    wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD))
_k.QueryInformationJobObject.restype = wintypes.BOOL


def _job(lim: dict):
    handle = _k.CreateJobObjectW(None, None)
    if not handle:
        wli._error("cannot create the compile job")
    ext = wli.EXTENDED_LIMITS()
    basic = ext.BasicLimitInformation
    basic.LimitFlags = (JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                        | JOB_OBJECT_LIMIT_JOB_MEMORY
                        | JOB_OBJECT_LIMIT_JOB_TIME
                        | JOB_OBJECT_LIMIT_ACTIVE_PROCESS
                        | JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION)
    basic.PerJobUserTimeLimit = lim["cpu_seconds"] * 10_000_000
    basic.ActiveProcessLimit = lim["active_processes"]
    ext.JobMemoryLimit = lim["memory_mb"] * 1024 * 1024
    ui = wintypes.DWORD(UI_LIMIT_ALL)
    if not _k.SetInformationJobObject(handle, JOB_EXTENDED_LIMITS,
                                      ctypes.byref(ext), ctypes.sizeof(ext)) \
            or not _k.SetInformationJobObject(handle, JOB_BASIC_UI_RESTRICTIONS,
                                              ctypes.byref(ui),
                                              ctypes.sizeof(ui)):
        wli._close(handle)
        wli._error("cannot set the compile job's limits")
    return handle


def _accounting(job) -> dict:
    ext, acct = wli.EXTENDED_LIMITS(), BASIC_ACCOUNTING()
    out = {"peak_memory_mb": None, "cpu_user_seconds": None}
    if _k.QueryInformationJobObject(job, JOB_EXTENDED_LIMITS, ctypes.byref(ext),
                                    ctypes.sizeof(ext), None):
        out["peak_memory_mb"] = round(ext.PeakJobMemoryUsed / 1048576, 1)
    if _k.QueryInformationJobObject(job, JOB_BASIC_ACCOUNTING,
                                    ctypes.byref(acct), ctypes.sizeof(acct),
                                    None):
        out["cpu_user_seconds"] = round(acct.TotalUserTime / 1e7, 2)
    return out


def _create(token, argv, env, cwd, startup, process):
    command = ctypes.create_unicode_buffer(subprocess.list2cmdline(argv))
    environment = wli._environment(env)
    flags = (wli.CREATE_SUSPENDED | wli.CREATE_UNICODE_ENVIRONMENT
             | wli.CREATE_NO_WINDOW)
    create = wli.advapi.CreateProcessAsUserW
    create.argtypes = (wintypes.HANDLE, wintypes.LPCWSTR, wintypes.LPWSTR,
                       ctypes.c_void_p, ctypes.c_void_p, wintypes.BOOL,
                       wintypes.DWORD, ctypes.c_void_p, wintypes.LPCWSTR,
                       ctypes.POINTER(wli.STARTUPINFO),
                       ctypes.POINTER(wli.PROCESS_INFORMATION))
    create.restype = wintypes.BOOL
    if not create(token, argv[0], command, None, None, True, flags,
                  ctypes.cast(environment, ctypes.c_void_p), str(cwd),
                  ctypes.byref(startup), ctypes.byref(process)):
        wli._error("cannot start the sandboxed compile")


def run(argv: list, *, writable: Path, cwd: Path, timeout: int, env: dict,
        lim: dict, stdout_path: Path, stderr_path: Path) -> tuple:
    """(exit code, accounting). 124 on a wall-clock timeout. Raises
    ExecutionInputProtectionUnavailable when a limit cannot be applied."""
    if not argv or not Path(argv[0]).is_absolute():
        wli._error("the sandboxed compile needs an absolute program path", 0)
    wli._set_integrity(writable, "LW")
    token = wli._low_token()
    job = _job(lim)
    process, streams = wli.PROCESS_INFORMATION(), []
    try:
        streams, f_in, f_out, f_err = wli._open_streams(stdout_path,
                                                        stderr_path)
        _create(token, argv, env, cwd, wli._startup_info(f_in, f_out, f_err),
                process)
        if not _k.AssignProcessToJobObject(job, process.hProcess):
            _k.TerminateProcess(process.hProcess, 1)
            wli._error("cannot assign the compile to its job")
        if _k.ResumeThread(process.hThread) == 0xFFFFFFFF:
            _k.TerminateJobObject(job, 1)
            wli._error("cannot resume the sandboxed compile")
        waited = _k.WaitForSingleObject(process.hProcess, timeout * 1000)
        if waited == wli.WAIT_TIMEOUT:
            _k.TerminateJobObject(job, 124)
            _k.WaitForSingleObject(process.hProcess, 10_000)
            return 124, _accounting(job)
        if waited != wli.WAIT_OBJECT_0:
            _k.TerminateJobObject(job, 1)
            wli._error("cannot wait for the sandboxed compile")
        code = wintypes.DWORD()
        if not _k.GetExitCodeProcess(process.hProcess, ctypes.byref(code)):
            wli._error("cannot read the sandboxed compile's exit code")
        acct = _accounting(job)
        _k.TerminateJobObject(job, code.value or 1)
        return int(code.value), acct
    finally:
        wli._close(process.hThread)
        wli._close(process.hProcess)
        wli._close(job)
        wli._close(token)
        for stream in streams:
            stream.close()
