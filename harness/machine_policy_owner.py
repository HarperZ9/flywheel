"""machine_policy_owner.py -- who is allowed to have written a policy file.

A setting that outranks the operator's own environment is worth reading only if
the operator's own account could not have written it. That is an ownership and
permission question, it is asked differently on every platform, and it is asked
here so no caller has to know how.

The POSIX rule is a pure function over `os.stat_result`, so it is testable on
any host: a Windows run can assert what a root-owned but group-writable file
would be refused for without needing root, or POSIX, to build one. Windows
keeps ownership outside the stat and the fields that remain describe nothing,
which is why the platform is a parameter rather than something read here. A
Windows stat read as though it were a POSIX one reports `st_uid` 0 and passes.

Both halves refuse when they cannot answer. An unresolved question about who
wrote a security policy is not a yes.
"""
from __future__ import annotations

import ctypes
from pathlib import Path

__all__ = ["ADMIN_SIDS", "insecure_reason", "owner_problem",
           "windows_owner_problem"]

#: Mode bits that put a file within reach of somebody other than its owner.
WORLD_WRITABLE = 0o002
GROUP_WRITABLE = 0o020

#: The two accounts a machine-wide setting on Windows can belong to. An
#: elevated process creates objects owned by the Administrators group by
#: default, and the service account owns what it writes, so a file owned by
#: anything else was written by somebody who did not need elevation.
ADMIN_SIDS = frozenset({
    "S-1-5-32-544",   # BUILTIN\Administrators
    "S-1-5-18",       # NT AUTHORITY\SYSTEM
})


def insecure_reason(info, *, posix: bool) -> str | None:
    """Why this file may not carry a machine-wide policy. None means it may.

    `info` is an `os.stat_result` for the policy file or for the directory
    holding it. Callers check both: a file nobody else can write is still
    replaceable by anyone who can write the directory it sits in.
    """
    if not posix:
        return "ownership is not readable from a stat on this platform"
    if info.st_uid != 0:
        return f"owned by uid {info.st_uid}, not root"
    if info.st_mode & WORLD_WRITABLE:
        return "world-writable"
    if info.st_mode & GROUP_WRITABLE:
        return "group-writable"
    return None


def windows_owner_problem(path: Path) -> str | None:
    """Why this Windows path may not carry a policy. None means it may.

    Ownership is asked of the security API rather than inferred from the path.
    `%ProgramData%` grants ordinary users the right to create files, so a
    policy file appearing at the administrator's path is not by itself evidence
    that an administrator put it there.
    """
    owner = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    status = advapi.GetNamedSecurityInfoW(
        ctypes.c_wchar_p(str(path)),
        1,                       # SE_FILE_OBJECT
        1,                       # OWNER_SECURITY_INFORMATION
        ctypes.byref(owner), None, None, None,
        ctypes.byref(descriptor))
    if status != 0:
        return f"owner lookup failed with error {status}"
    try:
        text = ctypes.c_wchar_p()
        if not advapi.ConvertSidToStringSidW(owner, ctypes.byref(text)):
            return f"owner SID unreadable, error {ctypes.get_last_error()}"
        try:
            sid = text.value or ""
        finally:
            ctypes.WinDLL("kernel32").LocalFree(text)
    finally:
        ctypes.WinDLL("kernel32").LocalFree(descriptor)
    if sid not in ADMIN_SIDS:
        return f"owned by {sid}, not an administrative account"
    return None


def owner_problem(path: Path, *, platform: str) -> str | None:
    """The platform's own answer for one path, file or directory.

    A missing path is not this function's failure to report. The caller decides
    what an absent policy means, and it means something different from a policy
    that is present and unowned.
    """
    target = Path(path)
    if not target.exists():
        return None
    if platform == "win32":
        return windows_owner_problem(target)
    return insecure_reason(target.stat(), posix=True)
