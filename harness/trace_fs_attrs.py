"""File-system attributes for custody: integrity label, not-indexed, sync roots.

Label (SP-12). Low-integrity processes can read medium files by default, so
labeling only the token left store.db, chat history, the spool and exports
readable to a sandboxed child. The medium No-Read-Up label is set on
FLYWHEEL_HOME with object and container inheritance; `SetNamedSecurityInfoW`
propagates it to entries that already exist, and new ones inherit it. A
marker records that the walk ran, so it runs once.

Not indexed (N-17). Custody directories and export directories get
FILE_ATTRIBUTE_NOT_CONTENT_INDEXED, so Windows Search does not copy their
text into its index. Whether new files inherit it is unknown, so writers set
it per file where they can.

Sync roots (G6). A path under the OneDrive variables, or under a Dropbox,
Google Drive or iCloudDrive folder, is reported as synced. It is a heuristic
and says so.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

LABEL_MARKER = ".custody-label-v1"
_TREE_SDDL = "S:(ML;OICI;NRNWNX;;;ME)"
_NOT_INDEXED = 0x2000
_SYNC_WORDS = ("dropbox", "google drive", "googledrive", "icloud drive", "iclouddrive")


def _set_label(path: Path, sddl: str) -> None:
    import ctypes
    from ctypes import wintypes
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    convert = advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW
    convert.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p),
                        ctypes.POINTER(wintypes.DWORD))
    get_sacl = advapi.GetSecurityDescriptorSacl
    get_sacl.argtypes = (ctypes.c_void_p, ctypes.POINTER(wintypes.BOOL),
                         ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.BOOL))
    set_info = advapi.SetNamedSecurityInfoW
    set_info.argtypes = (wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
    set_info.restype = wintypes.DWORD
    kernel.LocalFree.argtypes = (ctypes.c_void_p,)
    descriptor, size = ctypes.c_void_p(), wintypes.DWORD()
    if not convert(sddl, 1, ctypes.byref(descriptor), ctypes.byref(size)):
        raise OSError(ctypes.get_last_error(), "cannot build the custody label")
    try:
        sacl, present, defaulted = ctypes.c_void_p(), wintypes.BOOL(), wintypes.BOOL()
        if not get_sacl(descriptor, ctypes.byref(present), ctypes.byref(sacl),
                        ctypes.byref(defaulted)):
            raise OSError(ctypes.get_last_error(), "cannot read the custody label")
        code = set_info(str(path), 1, 0x10, None, None, None, sacl)
        if code:
            raise OSError(code, "cannot label the custody tree")
    finally:
        kernel.LocalFree(descriptor)


def label_tree(home) -> bool:
    """Label FLYWHEEL_HOME and everything under it once. True when it ran now."""
    home = Path(home)
    marker = home / LABEL_MARKER
    if sys.platform != "win32" or marker.exists() or not home.is_dir():
        return False
    _set_label(home, _TREE_SDDL)
    marker.write_bytes(b"flywheel.custody-label/v1\n")
    return True


def set_not_indexed(path) -> bool:
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetFileAttributesW.argtypes = (wintypes.LPCWSTR,)
    kernel.GetFileAttributesW.restype = wintypes.DWORD
    kernel.SetFileAttributesW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD)
    current = kernel.GetFileAttributesW(str(path))
    if current == 0xFFFFFFFF:
        raise OSError(ctypes.get_last_error(), "cannot read attributes")
    if current & _NOT_INDEXED:
        return True
    if not kernel.SetFileAttributesW(str(path), current | _NOT_INDEXED):
        raise OSError(ctypes.get_last_error(), "cannot set the not-indexed attribute")
    return True


def is_not_indexed(path) -> bool | None:
    if sys.platform != "win32":
        return None
    return bool(getattr(os.stat(path), "st_file_attributes", 0) & _NOT_INDEXED)


def sync_root(path, environ=None) -> str | None:
    """The sync client a path sits under, by variables and folder names."""
    environ = os.environ if environ is None else environ
    text = os.path.normcase(os.path.abspath(str(path)))
    for name in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        root = environ.get(name)
        if root and (text + os.sep).startswith(os.path.normcase(os.path.abspath(root)) + os.sep):
            return "OneDrive"
    lowered = text.lower()
    for word in _SYNC_WORDS:
        if word in lowered:
            return word
    parts = [p.lower() for p in Path(text).parts]
    return "OneDrive" if any(p.startswith("onedrive") for p in parts) else None
