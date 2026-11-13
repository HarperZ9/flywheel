"""windows_label.py -- what this account may do to a folder's integrity label.

Changing a mandatory label goes through `SetNamedSecurityInfoW` with
`LABEL_SECURITY_INFORMATION`, and Windows opens the folder with the
`WRITE_OWNER` right to do it. Modify does not include that right; Full control
does. Owning the folder does not grant it either: an owner gets `READ_CONTROL`
and `WRITE_DAC` and nothing more. No narrower right is enough.

So a folder on a second drive, where the account usually has Modify through
Authenticated Users, cannot be labelled. `can_label` asks the same question
the label change would, by opening the folder with `WRITE_OWNER` and nothing
else. `is_low` reads the label, which needs `READ_CONTROL` only: a folder with
no label is medium, and a low-integrity command cannot write to it whether or
not this account could have labelled it.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

WRITE_OWNER = 0x00080000
SHARE_ALL = 0x7
OPEN_EXISTING = 3
BACKUP_SEMANTICS = 0x02000000        # needed to open a folder at all
SE_FILE_OBJECT = 1
LABEL_SECURITY_INFORMATION = 0x10
MEDIUM_RID = 0x2000


def can_label(path) -> bool:
    """True when this account can open `path` with WRITE_OWNER."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                   ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                   wintypes.HANDLE)
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel.CreateFileW(str(path), WRITE_OWNER, SHARE_ALL, None, OPEN_EXISTING,
                                BACKUP_SEMANTICS, None)
    if handle in (None, wintypes.HANDLE(-1).value):
        return False
    kernel.CloseHandle(handle)
    return True


def label_rid(path) -> "int | None":
    """The integrity level on `path` (0x1000 low, 0x2000 medium), or None for no label."""
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = (ctypes.c_void_p,)
    read = advapi.GetNamedSecurityInfoW
    read.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                     ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
                     ctypes.POINTER(ctypes.c_void_p))
    read.restype = wintypes.DWORD
    sacl, descriptor = ctypes.c_void_p(), ctypes.c_void_p()
    code = read(str(path), SE_FILE_OBJECT, LABEL_SECURITY_INFORMATION, None, None, None,
                ctypes.byref(sacl), ctypes.byref(descriptor))
    if code:
        raise OSError(f"cannot read the integrity label (windows error {code})")
    try:
        if not sacl.value:
            return None
        # ACL: revision, pad, size (2), ace count (2), pad (2). Then the ACE:
        # header (4), mask (4), and the SID, whose last sub-authority is the level.
        if not ctypes.c_ushort.from_address(sacl.value + 4).value:
            return None
        sid = sacl.value + 8 + 8
        count = ctypes.c_ubyte.from_address(sid + 1).value
        return ctypes.c_ulong.from_address(sid + 8 + 4 * (count - 1)).value
    finally:
        kernel.LocalFree(descriptor)


def is_low(path) -> bool:
    """True when `path` carries a label below medium, so a low child could write it."""
    level = label_rid(path)
    return level is not None and level < MEDIUM_RID
