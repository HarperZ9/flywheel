"""Current-user DPAPI for the few bytes a hook must keep (SP-34).

A suppression record names the working directory where capture was switched
off, so the owner can find it. On Windows that name is encrypted with DPAPI
in current-user scope before it touches disk; elsewhere the hook omits it and
counts only. Standard library only (ctypes).
"""
from __future__ import annotations

import sys

ENTROPY = b"flywheel.capture.suppression.v1"


def available() -> bool:
    return sys.platform == "win32"


_BLOB = None


def _blob_type():
    global _BLOB
    if _BLOB is None:
        import ctypes
        from ctypes import wintypes

        class BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD),
                        ("pbData", ctypes.POINTER(ctypes.c_char))]
        _BLOB = BLOB
    return _BLOB


def _blob(data: bytes):
    import ctypes
    buffer = ctypes.create_string_buffer(data, len(data))
    blob = _blob_type()
    return blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def _call(name: str, data: bytes, entropy: bytes) -> bytes:
    import ctypes
    from ctypes import wintypes
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    blob = _blob_type()
    source, keep_a = _blob(data)
    extra, keep_b = _blob(entropy)
    out = blob()
    fn = getattr(crypt, name)
    fn.argtypes = [ctypes.POINTER(blob), ctypes.c_void_p, ctypes.POINTER(blob),
                   ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(blob)]
    fn.restype = wintypes.BOOL
    ui_forbidden = 0x1
    if not fn(ctypes.byref(source), None, ctypes.byref(extra), None, None, ui_forbidden,
              ctypes.byref(out)):
        raise OSError(ctypes.get_last_error(), f"{name} failed")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel.LocalFree.argtypes = (ctypes.c_void_p,)
        kernel.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))
        del keep_a, keep_b


def protect(data: bytes, entropy: bytes = ENTROPY) -> bytes:
    return _call("CryptProtectData", data, entropy)


def unprotect(data: bytes, entropy: bytes = ENTROPY) -> bytes:
    return _call("CryptUnprotectData", data, entropy)
