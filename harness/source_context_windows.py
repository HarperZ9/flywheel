"""Windows directory guard for protected Gather path handoff."""
from __future__ import annotations

from pathlib import Path
import ctypes
import hashlib
import os

from .source_context_store import SourceContextError

FILE_LIST_DIRECTORY = 0x00000001
FILE_ADD_FILE = 0x00000002
FILE_ADD_SUBDIRECTORY = 0x00000004
FILE_READ_ATTRIBUTES = 0x00000080
FILE_WRITE_ATTRIBUTES = 0x00000100
SYNCHRONIZE = 0x00100000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004
OPEN_EXISTING = 3
FILE_ATTRIBUTE_DIRECTORY = 0x00000010
FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_INVALID = ctypes.c_void_p(-1).value
_BUSY = {5, 32, 33}


class _WinHandle:
    def __init__(self, handle: int, path: Path) -> None:
        self.handle, self.path = handle, Path(path)

    def close(self) -> None:
        if self.handle not in (None, _INVALID):
            ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(
                ctypes.c_void_p(self.handle))
            self.handle = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


class _FileTime(ctypes.Structure):
    _fields_ = [("dwLowDateTime", ctypes.c_ulong),
                ("dwHighDateTime", ctypes.c_ulong)]


class _FileInformation(ctypes.Structure):
    _fields_ = [
        ("dwFileAttributes", ctypes.c_ulong),
        ("ftCreationTime", _FileTime),
        ("ftLastAccessTime", _FileTime),
        ("ftLastWriteTime", _FileTime),
        ("dwVolumeSerialNumber", ctypes.c_ulong),
        ("nFileSizeHigh", ctypes.c_ulong),
        ("nFileSizeLow", ctypes.c_ulong),
        ("nNumberOfLinks", ctypes.c_ulong),
        ("nFileIndexHigh", ctypes.c_ulong),
        ("nFileIndexLow", ctypes.c_ulong),
    ]


def _win32_path(path: Path) -> str:
    value = os.path.abspath(str(path))
    if value.startswith("\\\\?\\"):
        raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")
    if value.startswith("\\\\.\\"):
        raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")
    if value.startswith("\\\\"):
        raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")
    return "\\\\?\\" + value


def _create_file_handle(path: Path, access: int, share: int,
                        disposition: int, flags: int, *,
                        busy_code: str = "SOURCE_CONTEXT_AUTHORITY_BUSY"):
    if os.name != "nt":
        raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = (ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong,
                       ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong,
                       ctypes.c_void_p)
    create.restype = ctypes.c_void_p
    handle = create(_win32_path(Path(path)), access, share, None,
                    disposition, flags, None)
    if handle == _INVALID:
        error = ctypes.get_last_error()
        if error in _BUSY:
            raise SourceContextError(busy_code)
        raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")
    return _WinHandle(handle, Path(path))


def _identity(handle: _WinHandle) -> dict:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    info = _FileInformation()
    ok = kernel.GetFileInformationByHandle(
        ctypes.c_void_p(handle.handle), ctypes.byref(info))
    if not ok:
        raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")
    attrs = int(info.dwFileAttributes)
    if not attrs & FILE_ATTRIBUTE_DIRECTORY:
        raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")
    if attrs & FILE_ATTRIBUTE_REPARSE_POINT:
        raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")
    return {"platform": "windows",
            "volume_serial": int(info.dwVolumeSerialNumber),
            "file_index": (int(info.nFileIndexHigh) << 32)
                          | int(info.nFileIndexLow),
            "attributes": attrs}


def _components(path: Path) -> list[Path]:
    absolute = Path(os.path.abspath(str(path)))
    text = str(absolute)
    if not absolute.is_absolute() or "::" in text:
        raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")
    if any(part in ("", ".", "..") or ":" in part
           for part in absolute.parts[1:]):
        raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")
    current = Path(absolute.anchor)
    paths = [current]
    for part in absolute.parts[1:]:
        current = current / part
        paths.append(current)
    return paths


class SourceContextWindowsGuard:
    """Hold read-share-only handles over every path component during Gather."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._components: list[Path] = []
        self._handles: list[_WinHandle] = []
        self._identities: list[dict] = []

    def __enter__(self):
        if os.name != "nt":
            raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")
        try:
            self._components = _components(self.path)
            for component in self._components:
                handle = _create_file_handle(
                    component,
                    FILE_LIST_DIRECTORY | FILE_READ_ATTRIBUTES | SYNCHRONIZE,
                    FILE_SHARE_READ, OPEN_EXISTING,
                    FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT)
                self._handles.append(handle)
                self._identities.append(_identity(handle))
            self.revalidate()
            return self
        except Exception:
            self.close()
            raise

    def __exit__(self, *_args) -> bool:
        self.close()
        return False

    def close(self) -> None:
        while self._handles:
            self._handles.pop().close()

    def revalidate(self) -> None:
        if [_identity(handle) for handle in self._handles] != self._identities:
            raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")

    def identity(self) -> dict:
        self.revalidate()
        return dict(self._identities[-1], guarded_components=len(self._identities))

    def identities(self) -> list[dict]:
        self.revalidate()
        rows = []
        for path, identity in zip(self._components, self._identities):
            rows.append(dict(identity, path_sha256=_path_sha(path)))
        return rows


def _path_sha(path: Path) -> str:
    text = os.path.normcase(os.path.abspath(str(path)))
    return hashlib.sha256(text.encode("utf-8", "strict")).hexdigest()
