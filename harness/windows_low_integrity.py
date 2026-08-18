"""Minimal ctypes launcher for a Windows low-integrity verifier process."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess

from .execution_input_protection import ExecutionInputProtectionUnavailable

TOKEN_ASSIGN_PRIMARY = 0x0001
TOKEN_DUPLICATE = 0x0002
TOKEN_QUERY = 0x0008
TOKEN_ADJUST_DEFAULT = 0x0080
TOKEN_ADJUST_SESSIONID = 0x0100
DISABLE_MAX_PRIVILEGE = 0x0001
SE_GROUP_INTEGRITY = 0x00000020
TOKEN_INTEGRITY_LEVEL = 25
SE_FILE_OBJECT = 1
LABEL_SECURITY_INFORMATION = 0x00000010
CREATE_SUSPENDED = 0x00000004
CREATE_UNICODE_ENVIRONMENT = 0x00000400
CREATE_NO_WINDOW = 0x08000000
STARTF_USESTDHANDLES = 0x00000100
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
WAIT_OBJECT_0, WAIT_TIMEOUT = 0, 258


class SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = (("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD))


class TOKEN_MANDATORY_LABEL(ctypes.Structure):
    _fields_ = (("Label", SID_AND_ATTRIBUTES),)


class STARTUPINFO(ctypes.Structure):
    _fields_ = (("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR), ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD), ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(wintypes.BYTE)),
        ("hStdInput", wintypes.HANDLE), ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE))


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = (("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
                ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD))


class BASIC_LIMITS(ctypes.Structure):
    _fields_ = (("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong), ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD), ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD))


class IO_COUNTERS(ctypes.Structure):
    _fields_ = tuple((name, ctypes.c_ulonglong) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount"))


class EXTENDED_LIMITS(ctypes.Structure):
    _fields_ = (("BasicLimitInformation", BASIC_LIMITS),
        ("IoInfo", IO_COUNTERS), ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t))


kernel = ctypes.WinDLL("kernel32", use_last_error=True)
advapi = ctypes.WinDLL("advapi32", use_last_error=True)
kernel.GetCurrentProcess.argtypes = (); kernel.GetCurrentProcess.restype = wintypes.HANDLE
kernel.CloseHandle.argtypes = (wintypes.HANDLE,); kernel.CloseHandle.restype = wintypes.BOOL
kernel.LocalFree.argtypes = (ctypes.c_void_p,); kernel.LocalFree.restype = ctypes.c_void_p
kernel.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
kernel.CreateJobObjectW.restype = wintypes.HANDLE
kernel.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int,
                                            ctypes.c_void_p, wintypes.DWORD)
kernel.SetInformationJobObject.restype = wintypes.BOOL
kernel.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
kernel.AssignProcessToJobObject.restype = wintypes.BOOL
kernel.ResumeThread.argtypes = (wintypes.HANDLE,); kernel.ResumeThread.restype = wintypes.DWORD
kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
kernel.WaitForSingleObject.restype = wintypes.DWORD
kernel.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
kernel.TerminateJobObject.restype = wintypes.BOOL
kernel.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
kernel.TerminateProcess.restype = wintypes.BOOL
kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
kernel.GetExitCodeProcess.restype = wintypes.BOOL
advapi.OpenProcessToken.argtypes = (wintypes.HANDLE, wintypes.DWORD,
                                     ctypes.POINTER(wintypes.HANDLE))
advapi.OpenProcessToken.restype = wintypes.BOOL
advapi.CreateRestrictedToken.argtypes = (wintypes.HANDLE, wintypes.DWORD,
    wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
    wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(wintypes.HANDLE))
advapi.CreateRestrictedToken.restype = wintypes.BOOL
advapi.ConvertStringSidToSidW.argtypes = (wintypes.LPCWSTR,
                                           ctypes.POINTER(ctypes.c_void_p))
advapi.ConvertStringSidToSidW.restype = wintypes.BOOL
advapi.GetLengthSid.argtypes = (ctypes.c_void_p,); advapi.GetLengthSid.restype = wintypes.DWORD
advapi.SetTokenInformation.argtypes = (wintypes.HANDLE, ctypes.c_int,
                                        ctypes.c_void_p, wintypes.DWORD)
advapi.SetTokenInformation.restype = wintypes.BOOL


def _error(action: str, code: int | None = None):
    value = ctypes.get_last_error() if code is None else code
    raise ExecutionInputProtectionUnavailable(f"{action} (windows error {value})")


def _close(handle) -> None:
    if handle:
        kernel.CloseHandle(handle)


def _set_integrity(path: Path, label: str) -> None:
    descriptor = ctypes.c_void_p(); size = wintypes.DWORD()
    convert = advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW
    convert.argtypes = (wintypes.LPCWSTR, wintypes.DWORD,
                        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD))
    convert.restype = wintypes.BOOL
    if not convert(f"S:(ML;OICI;NW;;;{label})", 1,
                   ctypes.byref(descriptor), ctypes.byref(size)):
        _error("cannot create integrity descriptor")
    try:
        sacl = ctypes.c_void_p(); present = wintypes.BOOL(); defaulted = wintypes.BOOL()
        get_sacl = advapi.GetSecurityDescriptorSacl
        get_sacl.argtypes = (ctypes.c_void_p, ctypes.POINTER(wintypes.BOOL),
                             ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.BOOL))
        get_sacl.restype = wintypes.BOOL
        if not get_sacl(descriptor, ctypes.byref(present), ctypes.byref(sacl),
                        ctypes.byref(defaulted)) or not present.value:
            _error("cannot read integrity descriptor")
        set_info = advapi.SetNamedSecurityInfoW
        set_info.argtypes = (wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
        set_info.restype = wintypes.DWORD
        code = set_info(str(path), SE_FILE_OBJECT, LABEL_SECURITY_INFORMATION,
                        None, None, None, sacl)
        if code:
            _error("cannot label execution namespace", code)
    finally:
        kernel.LocalFree(descriptor)


def _low_token():
    current = wintypes.HANDLE(); restricted = wintypes.HANDLE()
    access = (TOKEN_ASSIGN_PRIMARY | TOKEN_DUPLICATE | TOKEN_QUERY
              | TOKEN_ADJUST_DEFAULT | TOKEN_ADJUST_SESSIONID)
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), access,
                                   ctypes.byref(current)):
        _error("cannot open process token")
    try:
        if not advapi.CreateRestrictedToken(current, DISABLE_MAX_PRIVILEGE,
                0, None, 0, None, 0, None, ctypes.byref(restricted)):
            _error("cannot create restricted token")
    finally:
        _close(current)
    sid = ctypes.c_void_p()
    if not advapi.ConvertStringSidToSidW("S-1-16-4096", ctypes.byref(sid)):
        _close(restricted); _error("cannot create low-integrity SID")
    try:
        label = TOKEN_MANDATORY_LABEL(SID_AND_ATTRIBUTES(sid, SE_GROUP_INTEGRITY))
        length = advapi.GetLengthSid(sid)
        if not advapi.SetTokenInformation(restricted, TOKEN_INTEGRITY_LEVEL,
                ctypes.byref(label), ctypes.sizeof(label) + length):
            _close(restricted); restricted = None
            _error("cannot lower verifier token")
    finally:
        kernel.LocalFree(sid)
    return restricted


def _job():
    handle = kernel.CreateJobObjectW(None, None)
    if not handle:
        _error("cannot create verifier job")
    limits = EXTENDED_LIMITS()
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel.SetInformationJobObject(handle, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits), ctypes.sizeof(limits)):
        _close(handle); _error("cannot constrain verifier job")
    return handle


def _environment(env: dict) -> ctypes.Array:
    entries = [f"{key}={value}" for key, value in sorted(env.items(),
                                                          key=lambda item: item[0].upper())]
    return ctypes.create_unicode_buffer("\0".join(entries) + "\0\0")


class LowIntegrityRunner:
    def __init__(self, source: Path, output: Path):
        self.source, self.output, self.token = source, output, None

    def __enter__(self):
        _set_integrity(self.source, "ME")
        _set_integrity(self.output, "LW")
        self.token = _low_token()
        return self

    def __exit__(self, *_):
        _close(self.token); self.token = None

    def run(self, argv: list[str], *, env: dict, timeout_seconds: int) -> int:
        if not self.token or not argv or Path(argv[0]).resolve() != Path(argv[0]):
            raise ExecutionInputProtectionUnavailable("protected argv is not absolute")
        job = _job(); process = PROCESS_INFORMATION(); nulls = []
        try:
            for mode in ("rb", "wb", "wb"):
                stream = open(os.devnull, mode); nulls.append(stream)
                os.set_handle_inheritable(__import__("msvcrt").get_osfhandle(stream.fileno()), True)
            startup = STARTUPINFO(); startup.cb = ctypes.sizeof(startup)
            startup.dwFlags = STARTF_USESTDHANDLES
            startup.hStdInput = __import__("msvcrt").get_osfhandle(nulls[0].fileno())
            startup.hStdOutput = __import__("msvcrt").get_osfhandle(nulls[1].fileno())
            startup.hStdError = __import__("msvcrt").get_osfhandle(nulls[2].fileno())
            command = ctypes.create_unicode_buffer(subprocess.list2cmdline(argv))
            environment = _environment(env)
            flags = CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT | CREATE_NO_WINDOW
            create = advapi.CreateProcessAsUserW
            create.argtypes = (wintypes.HANDLE, wintypes.LPCWSTR, wintypes.LPWSTR,
                ctypes.c_void_p, ctypes.c_void_p, wintypes.BOOL, wintypes.DWORD,
                ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(STARTUPINFO),
                ctypes.POINTER(PROCESS_INFORMATION))
            create.restype = wintypes.BOOL
            if not create(self.token, argv[0], command, None, None, True, flags,
                    ctypes.cast(environment, ctypes.c_void_p), str(self.source),
                    ctypes.byref(startup), ctypes.byref(process)):
                _error("cannot create low-integrity verifier")
            if not kernel.AssignProcessToJobObject(job, process.hProcess):
                kernel.TerminateProcess(process.hProcess, 1)
                _error("cannot assign verifier job")
            if kernel.ResumeThread(process.hThread) == 0xFFFFFFFF:
                kernel.TerminateJobObject(job, 1); _error("cannot resume verifier")
            waited = kernel.WaitForSingleObject(process.hProcess,
                                                 timeout_seconds * 1000)
            if waited == WAIT_TIMEOUT:
                kernel.TerminateJobObject(job, 124)
                kernel.WaitForSingleObject(process.hProcess, 10_000)
                return 124
            if waited != WAIT_OBJECT_0:
                kernel.TerminateJobObject(job, 1); _error("cannot wait for verifier")
            code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(process.hProcess, ctypes.byref(code)):
                _error("cannot read verifier exit code")
            kernel.TerminateJobObject(job, code.value or 1)
            return int(code.value)
        finally:
            _close(process.hThread); _close(process.hProcess); _close(job)
            for stream in nulls:
                stream.close()
