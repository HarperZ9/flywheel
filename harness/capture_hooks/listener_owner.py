"""Is the listener on the endpoint's port the owner's gateway? (7.1, SP-02)

Before a hook connects, it checks who is listening. On Windows it reads the
TCP listener table with owning process ids, requires every listener that
would accept a connection to the endpoint's address and port to be the
process the endpoint file names, and requires that process to run as the
hook's own user: a process the hook cannot open, which includes every process
of another account, gives LISTENER_NOT_OWNER. On Linux it requires the
listening socket's uid to be the hook's uid. On macOS there is no check and
the server proof carries the guarantee. Standard library only (ctypes).
"""
from __future__ import annotations

import ipaddress
import os
import socket
import struct
import sys

_LISTENER_TABLE = 3  # TCP_TABLE_OWNER_PID_LISTENER
_QUERY_LIMITED = 0x1000
_STILL_ACTIVE = 259


def method() -> str:
    if sys.platform == "win32":
        return "windows-owner-pid"
    if sys.platform.startswith("linux"):
        return "linux-uid"
    return "none"


def _windows_rows(family: int) -> list[tuple[str, int, int]]:
    import ctypes
    from ctypes import wintypes
    iphlp = ctypes.WinDLL("iphlpapi")
    iphlp.GetExtendedTcpTable.argtypes = (ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD),
                                          wintypes.BOOL, wintypes.ULONG, ctypes.c_int,
                                          wintypes.ULONG)
    iphlp.GetExtendedTcpTable.restype = wintypes.DWORD
    size = wintypes.DWORD(0)
    iphlp.GetExtendedTcpTable(None, ctypes.byref(size), False, family, _LISTENER_TABLE, 0)
    for _ in range(4):
        buffer = ctypes.create_string_buffer(size.value + 4096)
        size = wintypes.DWORD(len(buffer))
        if iphlp.GetExtendedTcpTable(buffer, ctypes.byref(size), False, family,
                                     _LISTENER_TABLE, 0) == 0:
            return _parse_rows(buffer.raw, family)
    raise OSError("listener table unavailable")


def _parse_rows(raw: bytes, family: int) -> list[tuple[str, int, int]]:
    count = struct.unpack_from("<I", raw, 0)[0]
    rows, width = [], (24 if family == socket.AF_INET else 56)
    for index in range(count):
        base = 4 + index * width
        if family == socket.AF_INET:
            addr = socket.inet_ntoa(raw[base + 4:base + 8])
            port = struct.unpack_from(">H", raw, base + 8)[0]
            pid = struct.unpack_from("<I", raw, base + 20)[0]
        else:
            addr = str(ipaddress.IPv6Address(raw[base:base + 16]))
            port = struct.unpack_from(">H", raw, base + 20)[0]
            pid = struct.unpack_from("<I", raw, base + 52)[0]
        rows.append((addr, port, pid))
    return rows


def _windows_same_user(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    advapi.OpenProcessToken.argtypes = (wintypes.HANDLE, wintypes.DWORD,
                                        ctypes.POINTER(wintypes.HANDLE))
    advapi.GetTokenInformation.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                           wintypes.DWORD, ctypes.POINTER(wintypes.DWORD))
    advapi.EqualSid.argtypes = (ctypes.c_void_p, ctypes.c_void_p)

    def user_sid(process):
        token = wintypes.HANDLE()
        if not advapi.OpenProcessToken(process, 0x0008, ctypes.byref(token)):
            return None
        try:
            buffer, needed = ctypes.create_string_buffer(512), wintypes.DWORD()
            if not advapi.GetTokenInformation(token, 1, buffer, 512, ctypes.byref(needed)):
                return None
            return buffer, ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]
        finally:
            kernel.CloseHandle(token)
    handle = kernel.OpenProcess(_QUERY_LIMITED, False, pid)
    if not handle:
        return False
    try:
        theirs, mine = user_sid(handle), user_sid(kernel.GetCurrentProcess())
        return bool(theirs and mine and advapi.EqualSid(theirs[1], mine[1]))
    finally:
        kernel.CloseHandle(handle)


def _matching(rows, host: str, port: int):
    wildcard = "0.0.0.0" if ":" not in host else "::"
    return [pid for addr, p, pid in rows if p == port and addr in (host, wildcard)]


def _windows_check(host: str, port: int, pid: int) -> str | None:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    try:
        owners = _matching(_windows_rows(family), host, port)
    except OSError:
        return "LISTENER_MISMATCH"
    if not owners:
        return "GATEWAY_NOT_RUNNING"
    if any(owner != pid for owner in owners):
        return "LISTENER_MISMATCH"
    return None if _windows_same_user(pid) else "LISTENER_NOT_OWNER"


def _linux_rows(host: str) -> list[tuple[str, int, int]]:
    name = "/proc/net/tcp6" if ":" in host else "/proc/net/tcp"
    rows = []
    with open(name, encoding="ascii") as table:
        for line in table.readlines()[1:]:
            parts = line.split()
            if len(parts) < 8 or parts[3] != "0A":
                continue
            addr_hex, port_hex = parts[1].split(":")
            raw = bytes.fromhex(addr_hex)
            raw = b"".join(raw[i:i + 4][::-1] for i in range(0, len(raw), 4))
            rows.append((str(ipaddress.ip_address(raw)), int(port_hex, 16), int(parts[7])))
    return rows


def _linux_check(host: str, port: int) -> str | None:
    try:
        uids = _matching(_linux_rows(host), host, port)
    except (OSError, ValueError):
        return "LISTENER_MISMATCH"
    if not uids:
        return "GATEWAY_NOT_RUNNING"
    return None if all(uid == os.getuid() for uid in uids) else "LISTENER_NOT_OWNER"


def check_listener(host: str, port: int, pid: int) -> str | None:
    """None when the listener checks out, else the reason code."""
    if method() == "windows-owner-pid":
        return _windows_check(host, port, pid)
    if method() == "linux-uid":
        return _linux_check(host, port)
    return None


def pid_alive(pid) -> bool:
    if type(pid) is not int or pid <= 0:
        return False
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    handle = kernel.OpenProcess(_QUERY_LIMITED, False, pid)
    if not handle:
        return ctypes.get_last_error() == 5  # access denied: it exists
    try:
        code = wintypes.DWORD()
        kernel.GetExitCodeProcess(handle, ctypes.byref(code))
        return code.value == _STILL_ACTIVE
    finally:
        kernel.CloseHandle(handle)
