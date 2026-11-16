"""Windows Job Object launcher for installed-launch process ownership."""
from __future__ import annotations

import ctypes
import os
import subprocess
from ctypes import wintypes
from pathlib import Path
from typing import Mapping

CREATE_SUSPENDED = 0x00000004
CREATE_UNICODE_ENVIRONMENT = 0x00000400
CREATE_NO_WINDOW = 0x08000000
STARTF_USESHOWWINDOW = 0x00000001
STARTF_USESTDHANDLES = 0x00000100
SW_HIDE = 0
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
JOB_OBJECT_BASIC_PROCESS_ID_LIST = 3
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258
WAIT_FAILED = 0xFFFFFFFF
STILL_ACTIVE = 259


class STARTUPINFO(ctypes.Structure):
    _fields_ = (
        ("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR), ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD), ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(wintypes.BYTE)),
        ("hStdInput", wintypes.HANDLE), ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    )


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = (
        ("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD),
    )


class BASIC_LIMITS(ctypes.Structure):
    _fields_ = (
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD), ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD),
    )


class IO_COUNTERS(ctypes.Structure):
    _fields_ = tuple((name, ctypes.c_ulonglong) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
    ))


class EXTENDED_LIMITS(ctypes.Structure):
    _fields_ = (
        ("BasicLimitInformation", BASIC_LIMITS), ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t),
    )


def _kernel():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = (
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.ResumeThread.argtypes = (wintypes.HANDLE,)
    kernel.ResumeThread.restype = wintypes.DWORD
    kernel.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
    kernel.TerminateProcess.restype = wintypes.BOOL
    kernel.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
    kernel.TerminateJobObject.restype = wintypes.BOOL
    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.QueryInformationJobObject.argtypes = (
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD))
    kernel.QueryInformationJobObject.restype = wintypes.BOOL
    return kernel


def _error(action: str) -> str:
    return f"{action}:win32_{ctypes.get_last_error()}"


def _close(kernel, handle) -> bool:
    return not handle or bool(kernel.CloseHandle(handle))


def _environment(env: Mapping[str, str]):
    if not env:
        return None
    items = [f"{k}={v}" for k, v in sorted(env.items(), key=lambda item: item[0].upper())]
    return ctypes.create_unicode_buffer("\0".join(items) + "\0\0")


def _startup(stdout_path: Path, stderr_path: Path):
    import msvcrt

    streams = [open(os.devnull, "rb"), open(stdout_path, "wb"), open(stderr_path, "wb")]
    for stream in streams:
        os.set_handle_inheritable(msvcrt.get_osfhandle(stream.fileno()), True)
    startup = STARTUPINFO()
    startup.cb = ctypes.sizeof(startup)
    startup.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW
    startup.wShowWindow = SW_HIDE
    startup.hStdInput = msvcrt.get_osfhandle(streams[0].fileno())
    startup.hStdOutput = msvcrt.get_osfhandle(streams[1].fileno())
    startup.hStdError = msvcrt.get_osfhandle(streams[2].fileno())
    return startup, streams


class WindowsJobProcess:
    def __init__(self, kernel, process, job):
        self.kernel = kernel
        self.process = process
        self.job = job
        self.pid = int(process.dwProcessId)
        self.handles_closed = False

    def terminate_and_verify(self, timeout_ms: int = 5000) -> dict:
        terminated = bool(self.kernel.TerminateJobObject(self.job, 1)) if self.job else False
        wait_code = self.kernel.WaitForSingleObject(self.job, timeout_ms) if terminated else WAIT_FAILED
        active_pids, query_error = self.active_pids()
        closed = self.close()
        ok = terminated and wait_code == WAIT_OBJECT_0 and not active_pids and not query_error and closed
        return {
            "state": "PASS" if ok else "FAIL",
            "job_terminated": terminated,
            "job_wait_result": _wait_name(wait_code),
            "job_active_pids_after": active_pids,
            "job_query_error": query_error,
            "job_handles_closed": closed,
        }

    def active_pids(self) -> tuple[list[int], str]:
        if not self.job:
            return [], "job_handle_missing"
        capacity = 16
        while capacity <= 4096:
            info_type = _pid_list_type(capacity)
            info = info_type()
            size, returned = ctypes.sizeof(info), wintypes.DWORD()
            ok = self.kernel.QueryInformationJobObject(
                self.job, JOB_OBJECT_BASIC_PROCESS_ID_LIST, ctypes.byref(info),
                size, ctypes.byref(returned))
            if not ok:
                return [], _error("job_query_failed")
            assigned = int(info.NumberOfAssignedProcesses)
            count = int(info.NumberOfProcessIdsInList)
            if count >= assigned:
                return [int(info.ProcessIdList[i]) for i in range(count)], ""
            capacity = max(capacity * 2, assigned)
        return [], "job_query_too_many_processes"

    def close(self) -> bool:
        if self.handles_closed:
            return True
        ok = _close(self.kernel, self.process.hThread)
        ok = _close(self.kernel, self.process.hProcess) and ok
        ok = _close(self.kernel, self.job) and ok
        self.process.hThread = self.process.hProcess = self.job = None
        self.handles_closed = ok
        return ok


def start_windows_job_process(exe: Path, args: list[str], env: Mapping[str, str],
                              cwd: Path, stdout: Path, stderr: Path):
    if os.name != "nt":
        return None, "job_object_unavailable:not_windows"
    kernel = _kernel()
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        return None, _error("job_create_failed")
    limits = EXTENDED_LIMITS()
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel.SetInformationJobObject(
            job, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(limits),
            ctypes.sizeof(limits)):
        _close(kernel, job)
        return None, _error("job_limit_failed")
    process = PROCESS_INFORMATION()
    streams = []
    try:
        startup, streams = _startup(stdout, stderr)
        command = ctypes.create_unicode_buffer(subprocess.list2cmdline([str(exe), *args]))
        environment = _environment(env)
        create = kernel.CreateProcessW
        create.argtypes = (
            wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
            wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p, wintypes.LPCWSTR,
            ctypes.POINTER(STARTUPINFO), ctypes.POINTER(PROCESS_INFORMATION))
        create.restype = wintypes.BOOL
        flags = CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT | CREATE_NO_WINDOW
        if not create(str(exe), command, None, None, True, flags,
                      ctypes.cast(environment, ctypes.c_void_p) if environment else None,
                      str(cwd), ctypes.byref(startup), ctypes.byref(process)):
            return None, _error("process_create_failed")
        if not kernel.AssignProcessToJobObject(job, process.hProcess):
            kernel.TerminateProcess(process.hProcess, 1)
            kernel.WaitForSingleObject(process.hProcess, 5000)
            _close(kernel, process.hThread)
            _close(kernel, process.hProcess)
            _close(kernel, job)
            return None, _error("job_assign_failed")
        previous = kernel.ResumeThread(process.hThread)
        if previous != 1:
            kernel.TerminateJobObject(job, 1)
            kernel.WaitForSingleObject(process.hProcess, 5000)
            _close(kernel, process.hThread)
            _close(kernel, process.hProcess)
            _close(kernel, job)
            return None, _error("process_resume_failed")
        return WindowsJobProcess(kernel, process, job), ""
    finally:
        for stream in streams:
            stream.close()
        if not process.dwProcessId:
            _close(kernel, job)


def _pid_list_type(capacity: int):
    class JOBOBJECT_BASIC_PROCESS_ID_LIST(ctypes.Structure):
        _fields_ = (
            ("NumberOfAssignedProcesses", wintypes.DWORD),
            ("NumberOfProcessIdsInList", wintypes.DWORD),
            ("ProcessIdList", ctypes.c_size_t * capacity),
        )
    return JOBOBJECT_BASIC_PROCESS_ID_LIST


def _wait_name(code: int) -> str:
    if code == WAIT_OBJECT_0:
        return "WAIT_OBJECT_0"
    if code == WAIT_TIMEOUT:
        return "WAIT_TIMEOUT"
    if code == WAIT_FAILED:
        return "WAIT_FAILED"
    return str(int(code))
