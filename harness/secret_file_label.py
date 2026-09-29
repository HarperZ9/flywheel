"""Keep a secret file unreadable from a lower-integrity Windows process.

The Windows command sandbox (windows_low_integrity.py) runs a command at low
integrity. Windows' default mandatory policy is No-Write-Up only, so a low
integrity process can still read an ordinary medium-integrity file in the
operator's profile, including the gateway bearer token. A medium mandatory
label carrying No-Read-Up, No-Write-Up and No-Execute-Up closes that: the
operator's own medium-integrity processes read the file as before, and a
low-integrity process is refused at open.

This is a Windows mechanism. On POSIX the command sandbox hides the token
through the credential denylist in sandbox_protected_paths.py instead.
"""
from __future__ import annotations

import os
from pathlib import Path

_SDDL = "S:(ML;;NRNWNX;;;ME)"
_SE_FILE_OBJECT = 1
_LABEL_SECURITY_INFORMATION = 0x00000010


def protect_from_lower_integrity(path: str | Path) -> None:
    """Apply the medium No-Read-Up label to ``path``. Raise OSError on failure.

    A no-op on non-Windows hosts."""
    if os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    convert = advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW
    convert.argtypes = (wintypes.LPCWSTR, wintypes.DWORD,
                        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD))
    convert.restype = wintypes.BOOL
    get_sacl = advapi.GetSecurityDescriptorSacl
    get_sacl.argtypes = (ctypes.c_void_p, ctypes.POINTER(wintypes.BOOL),
                         ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.BOOL))
    get_sacl.restype = wintypes.BOOL
    set_info = advapi.SetNamedSecurityInfoW
    set_info.argtypes = (wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
    set_info.restype = wintypes.DWORD
    kernel.LocalFree.argtypes = (ctypes.c_void_p,)
    kernel.LocalFree.restype = ctypes.c_void_p
    descriptor, size = ctypes.c_void_p(), wintypes.DWORD()
    if not convert(_SDDL, 1, ctypes.byref(descriptor), ctypes.byref(size)):
        raise OSError(ctypes.get_last_error(), "cannot build the integrity label")
    try:
        sacl, present, defaulted = ctypes.c_void_p(), wintypes.BOOL(), wintypes.BOOL()
        if not get_sacl(descriptor, ctypes.byref(present), ctypes.byref(sacl),
                        ctypes.byref(defaulted)) or not present.value:
            raise OSError(ctypes.get_last_error(), "cannot read the integrity label")
        code = set_info(str(path), _SE_FILE_OBJECT, _LABEL_SECURITY_INFORMATION,
                        None, None, None, sacl)
        if code:
            raise OSError(code, "cannot label the file", str(path))
    finally:
        kernel.LocalFree(descriptor)


def has_lower_integrity_label(path: str | Path) -> bool | None:
    """Whether ``path`` carries the medium No-Read-Up label; None off Windows
    or when the label cannot be read."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    get_info = advapi.GetNamedSecurityInfoW
    get_info.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.POINTER(ctypes.c_void_p))
    get_info.restype = wintypes.DWORD
    render = advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW
    render.argtypes = (ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                       ctypes.POINTER(wintypes.LPWSTR), ctypes.c_void_p)
    render.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = (ctypes.c_void_p,)
    descriptor = ctypes.c_void_p()
    if get_info(str(path), _SE_FILE_OBJECT, _LABEL_SECURITY_INFORMATION, None, None, None,
                None, ctypes.byref(descriptor)):
        return None
    try:
        text = wintypes.LPWSTR()
        if not render(descriptor, 1, _LABEL_SECURITY_INFORMATION, ctypes.byref(text), None):
            return None
        try:
            import re
            match = re.search(r"\(ML;[^;]*;([A-Z]*);;;(ME|HI|SI)\)", text.value or "")
            flags = match.group(1) if match else ""
            return "NR" in [flags[i:i + 2] for i in range(0, len(flags), 2)]
        finally:
            kernel.LocalFree(text)
    finally:
        kernel.LocalFree(descriptor)
