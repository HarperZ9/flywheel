"""Windows owner-only DACL helpers."""
from __future__ import annotations

from pathlib import Path


def _raise(message: str) -> None:
    raise OSError(message)


def current_token_user_sid() -> str:
    import ctypes
    from ctypes import wintypes

    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    class SID_AND_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("Sid", wintypes.LPVOID), ("Attributes", wintypes.DWORD)]
    class TOKEN_USER(ctypes.Structure):
        _fields_ = [("User", SID_AND_ATTRIBUTES)]
    advapi.OpenProcessToken.argtypes = (wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE))
    advapi.OpenProcessToken.restype = wintypes.BOOL
    advapi.GetTokenInformation.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD))
    advapi.GetTokenInformation.restype = wintypes.BOOL
    advapi.ConvertSidToStringSidW.argtypes = (wintypes.LPVOID, ctypes.POINTER(wintypes.LPWSTR))
    advapi.ConvertSidToStringSidW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = (ctypes.c_void_p,)
    token = wintypes.HANDLE()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
        _raise("current token open failed")
    try:
        needed = wintypes.DWORD()
        advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(needed))
        if not needed.value:
            _raise("current token query failed")
        buffer = ctypes.create_string_buffer(needed.value)
        if not advapi.GetTokenInformation(token, 1, buffer, needed, ctypes.byref(needed)):
            _raise("current token query failed")
        sid_pointer = ctypes.cast(buffer, ctypes.POINTER(TOKEN_USER)).contents.User.Sid
        text = wintypes.LPWSTR()
        if not advapi.ConvertSidToStringSidW(sid_pointer, ctypes.byref(text)):
            _raise("current token SID conversion failed")
        try:
            value = text.value
        finally:
            kernel.LocalFree(text)
    finally:
        kernel.CloseHandle(token)
    if type(value) is not str or not value.startswith("S-1-"):
        _raise("current token SID is invalid")
    return value


def apply_windows_owner_only(path: Path, *, directory: bool) -> None:
    import ctypes
    from ctypes import wintypes

    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    convert = advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW
    convert.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p)
    convert.restype = wintypes.BOOL
    render = advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW
    render.argtypes = (ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(wintypes.LPWSTR), ctypes.c_void_p)
    render.restype = wintypes.BOOL
    set_security = advapi.SetFileSecurityW
    set_security.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p)
    set_security.restype = wintypes.BOOL
    get_security = advapi.GetFileSecurityW
    get_security.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD))
    get_security.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = (ctypes.c_void_p,)
    user_sid = current_token_user_sid()
    flags = "OICI" if directory else ""
    sddl = f"D:P(A;{flags};FA;;;OW)(A;{flags};FA;;;{user_sid})"
    descriptor, expected_text = ctypes.c_void_p(), wintypes.LPWSTR()
    if not convert(sddl, 1, ctypes.byref(descriptor), None):
        _raise("security descriptor conversion failed")
    try:
        if not render(descriptor, 1, 4, ctypes.byref(expected_text), None):
            _raise("security descriptor rendering failed")
        if not set_security(str(path), 0x80000004, descriptor):
            _raise("security descriptor application failed")
        needed = wintypes.DWORD()
        get_security(str(path), 4, None, 0, ctypes.byref(needed))
        if not needed.value:
            _raise("security descriptor verification failed")
        actual_descriptor = ctypes.create_string_buffer(needed.value)
        if not get_security(str(path), 4, actual_descriptor, needed, ctypes.byref(needed)):
            _raise("security descriptor verification failed")
        actual_text = wintypes.LPWSTR()
        if not render(actual_descriptor, 1, 4, ctypes.byref(actual_text), None):
            _raise("security descriptor verification failed")
        try:
            if actual_text.value != expected_text.value:
                _raise("security descriptor verification failed")
        finally:
            kernel.LocalFree(actual_text)
    finally:
        if expected_text:
            kernel.LocalFree(expected_text)
        kernel.LocalFree(descriptor)
