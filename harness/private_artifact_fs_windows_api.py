"""Small Windows file APIs used by private_artifact_fs_windows."""
from __future__ import annotations

import ctypes
import errno
import os
from ctypes import wintypes

DELETE = 0x00010000
FILE_ATTRIBUTE_DIRECTORY = 0x10
FILE_ATTRIBUTE_NORMAL = 0x80
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
FILE_BEGIN = 0
FILE_CREATE = 2
FILE_OPEN = 1
FILE_DELETE_ON_CLOSE = 0x1000
FILE_DIRECTORY_FILE = 0x1
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
FILE_NON_DIRECTORY_FILE = 0x40
FILE_OPEN_REPARSE_POINT = 0x00200000
FILE_SHARE_DELETE = 4
FILE_SHARE_READ = 1
FILE_SHARE_WRITE = 2
FILE_SYNCHRONOUS_IO_NONALERT = 0x20
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
SYNCHRONIZE = 0x00100000
_OBJ_CASE_INSENSITIVE = 0x40
_DUPLICATE_SAME_ACCESS = 2
_STATUS_NAME_COLLISION = 0xC0000035
_STATUS_NAME_NOT_FOUND = 0xC0000034
_ERROR_ALREADY_EXISTS = 183
_ERROR_FILE_EXISTS = 80
_ERROR_FILE_NOT_FOUND = 2
_ERROR_PATH_NOT_FOUND = 3
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

_CloseHandle = None
_CreateFileW = None
_DuplicateHandle = None
_FlushFileBuffers = None
_GetCurrentProcess = None
_GetFileInformationByHandle = None
_NtCreateFile = None
_NtSetInformationFile = None
_ReadFile = None
_RtlNtStatusToDosError = None
_SetFilePointerEx = None
_WriteFile = None


class _UNICODE_STRING(ctypes.Structure):
    _fields_ = [("Length", wintypes.USHORT), ("MaximumLength", wintypes.USHORT),
                ("Buffer", wintypes.LPWSTR)]


class _OBJECT_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Length", wintypes.ULONG), ("RootDirectory", wintypes.HANDLE),
                ("ObjectName", ctypes.POINTER(_UNICODE_STRING)),
                ("Attributes", wintypes.ULONG), ("SecurityDescriptor", wintypes.LPVOID),
                ("SecurityQualityOfService", wintypes.LPVOID)]


class _IO_STATUS_BLOCK(ctypes.Structure):
    _fields_ = [("Status", ctypes.c_ssize_t), ("Information", ctypes.c_size_t)]


class HandleInfo(ctypes.Structure):
    _fields_ = [
        ("dwFileAttributes", wintypes.DWORD), ("ftCreationTime", wintypes.FILETIME),
        ("ftLastAccessTime", wintypes.FILETIME), ("ftLastWriteTime", wintypes.FILETIME),
        ("dwVolumeSerialNumber", wintypes.DWORD), ("nFileSizeHigh", wintypes.DWORD),
        ("nFileSizeLow", wintypes.DWORD), ("nNumberOfLinks", wintypes.DWORD),
        ("nFileIndexHigh", wintypes.DWORD), ("nFileIndexLow", wintypes.DWORD),
    ]


class _RenameInfo(ctypes.Structure):
    _fields_ = [("ReplaceIfExists", wintypes.BOOLEAN),
                ("RootDirectory", wintypes.HANDLE),
                ("FileNameLength", wintypes.DWORD),
                ("FileName", wintypes.WCHAR * 1)]


class _DispositionInfo(ctypes.Structure):
    _fields_ = [("DeleteFile", wintypes.BOOLEAN)]


def supported() -> bool:
    return os.name == "nt" and hasattr(ctypes, "WinDLL")


def create_file(path: str, access: int, share: int, disposition: int, flags: int) -> int:
    _load()
    handle = _CreateFileW(path, access, share, None, disposition, flags, None)
    if handle == _INVALID_HANDLE_VALUE:
        raise _last_error("CreateFileW failed")
    return int(handle)


def duplicate_handle(handle: int) -> int:
    _load()
    process = _GetCurrentProcess()
    duplicate = wintypes.HANDLE()
    ok = _DuplicateHandle(process, wintypes.HANDLE(handle), process, ctypes.byref(duplicate),
                          0, False, _DUPLICATE_SAME_ACCESS)
    if not ok:
        raise _last_error("DuplicateHandle failed")
    return int(duplicate.value)


def nt_create_relative(handle: int, name: str, access: int, share: int,
                       disposition: int, options: int) -> int:
    _load()
    name_obj, _buffer = _object_name(name)
    attrs = _OBJECT_ATTRIBUTES(ctypes.sizeof(_OBJECT_ATTRIBUTES),
                               wintypes.HANDLE(handle), ctypes.pointer(name_obj),
                               _OBJ_CASE_INSENSITIVE, None, None)
    ios = _IO_STATUS_BLOCK()
    child = wintypes.HANDLE()
    status = _NtCreateFile(ctypes.byref(child), access, ctypes.byref(attrs),
                           ctypes.byref(ios), None, FILE_ATTRIBUTE_NORMAL, share,
                           disposition, options, None, 0)
    if status < 0:
        _raise_nt(status, name)
    return int(child.value)


def write_file(handle: int, data: bytes) -> None:
    _load()
    if not data:
        return
    written = wintypes.DWORD()
    buffer = ctypes.create_string_buffer(data)
    ok = _WriteFile(wintypes.HANDLE(handle), buffer, len(data), ctypes.byref(written), None)
    if not ok:
        raise _last_error("WriteFile failed")
    if written.value != len(data):
        raise OSError(errno.EIO, "short write")


def read_file(handle: int, size: int) -> bytes:
    _load()
    if not _SetFilePointerEx(wintypes.HANDLE(handle), ctypes.c_longlong(0), None, FILE_BEGIN):
        raise _last_error("SetFilePointerEx failed")
    if size <= 0:
        return b""
    read = wintypes.DWORD()
    buffer = ctypes.create_string_buffer(size)
    ok = _ReadFile(wintypes.HANDLE(handle), buffer, size, ctypes.byref(read), None)
    if not ok:
        raise _last_error("ReadFile failed")
    return buffer.raw[: read.value]


def handle_info(handle: int) -> HandleInfo:
    _load()
    info = HandleInfo()
    if not _GetFileInformationByHandle(wintypes.HANDLE(handle), ctypes.byref(info)):
        raise _last_error("GetFileInformationByHandle failed")
    return info


def flush(handle: int) -> None:
    _load()
    if not _FlushFileBuffers(wintypes.HANDLE(handle)):
        raise _last_error("FlushFileBuffers failed")


def rename(handle: int, parent: int, target: str) -> None:
    _load()
    encoded = target.encode("utf-16-le")
    size = _RenameInfo.FileName.offset + len(encoded)
    buffer = ctypes.create_string_buffer(size)
    info = _RenameInfo.from_buffer(buffer)
    info.ReplaceIfExists = False
    info.RootDirectory = wintypes.HANDLE(parent)
    info.FileNameLength = len(encoded)
    ctypes.memmove(ctypes.addressof(buffer) + _RenameInfo.FileName.offset,
                   encoded, len(encoded))
    ios = _IO_STATUS_BLOCK()
    status = _NtSetInformationFile(wintypes.HANDLE(handle), ctypes.byref(ios),
                                   buffer, size, 10)
    if status < 0:
        _raise_nt(status, target)


def delete_on_close(handle: int) -> None:
    _load()
    info = _DispositionInfo(True)
    ios = _IO_STATUS_BLOCK()
    status = _NtSetInformationFile(wintypes.HANDLE(handle), ctypes.byref(ios),
                                   ctypes.byref(info), ctypes.sizeof(info), 13)
    if status < 0:
        _raise_nt(status, "")


def close_handle(handle: int | None) -> None:
    if handle is None:
        return
    _load()
    if not _CloseHandle(wintypes.HANDLE(handle)):
        raise _last_error("CloseHandle failed")


def _load() -> None:
    global _CloseHandle, _CreateFileW, _DuplicateHandle, _FlushFileBuffers
    global _GetCurrentProcess, _GetFileInformationByHandle
    global _NtCreateFile, _NtSetInformationFile, _ReadFile, _RtlNtStatusToDosError
    global _SetFilePointerEx, _WriteFile
    if _CreateFileW is not None:
        return
    if not supported():
        raise OSError(errno.ENOSYS, "Windows file API unavailable")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
    _CloseHandle = kernel32.CloseHandle
    _CloseHandle.argtypes = [wintypes.HANDLE]
    _CloseHandle.restype = wintypes.BOOL
    _CreateFileW = kernel32.CreateFileW
    _CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                             wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
                             wintypes.HANDLE]
    _CreateFileW.restype = wintypes.HANDLE
    _DuplicateHandle = kernel32.DuplicateHandle
    _DuplicateHandle.argtypes = [wintypes.HANDLE, wintypes.HANDLE, wintypes.HANDLE,
                                 ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD,
                                 wintypes.BOOL, wintypes.DWORD]
    _DuplicateHandle.restype = wintypes.BOOL
    _FlushFileBuffers = kernel32.FlushFileBuffers
    _FlushFileBuffers.argtypes = [wintypes.HANDLE]
    _FlushFileBuffers.restype = wintypes.BOOL
    _GetFileInformationByHandle = kernel32.GetFileInformationByHandle
    _GetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.POINTER(HandleInfo)]
    _GetFileInformationByHandle.restype = wintypes.BOOL
    _GetCurrentProcess = kernel32.GetCurrentProcess
    _GetCurrentProcess.restype = wintypes.HANDLE
    _ReadFile = kernel32.ReadFile
    _ReadFile.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                          ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
    _ReadFile.restype = wintypes.BOOL
    _SetFilePointerEx = kernel32.SetFilePointerEx
    _SetFilePointerEx.argtypes = [wintypes.HANDLE, ctypes.c_longlong,
                                  ctypes.POINTER(ctypes.c_longlong), wintypes.DWORD]
    _SetFilePointerEx.restype = wintypes.BOOL
    _WriteFile = kernel32.WriteFile
    _WriteFile.argtypes = [wintypes.HANDLE, wintypes.LPCVOID, wintypes.DWORD,
                           ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
    _WriteFile.restype = wintypes.BOOL
    _NtCreateFile = ntdll.NtCreateFile
    _NtCreateFile.argtypes = [ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD,
                              ctypes.POINTER(_OBJECT_ATTRIBUTES),
                              ctypes.POINTER(_IO_STATUS_BLOCK), wintypes.LPVOID,
                              wintypes.ULONG, wintypes.ULONG, wintypes.ULONG,
                              wintypes.ULONG, wintypes.LPVOID, wintypes.ULONG]
    _NtCreateFile.restype = wintypes.LONG
    _NtSetInformationFile = ntdll.NtSetInformationFile
    _NtSetInformationFile.argtypes = [wintypes.HANDLE, ctypes.POINTER(_IO_STATUS_BLOCK),
                                      wintypes.LPVOID, wintypes.ULONG, wintypes.ULONG]
    _NtSetInformationFile.restype = wintypes.LONG
    _RtlNtStatusToDosError = ntdll.RtlNtStatusToDosError
    _RtlNtStatusToDosError.argtypes = [wintypes.LONG]
    _RtlNtStatusToDosError.restype = wintypes.ULONG


def _object_name(name: str) -> tuple[_UNICODE_STRING, ctypes.Array[ctypes.c_wchar]]:
    encoded = name.encode("utf-16-le")
    if len(encoded) > 0xFFFE:
        raise OSError(errno.ENAMETOOLONG, "Windows object name too long")
    buffer = ctypes.create_unicode_buffer(name)
    maximum = ctypes.sizeof(buffer)
    if maximum > 0xFFFF:
        raise OSError(errno.ENAMETOOLONG, "Windows object name too long")
    return _UNICODE_STRING(len(encoded), maximum,
                           ctypes.cast(buffer, wintypes.LPWSTR)), buffer


def _raise_nt(status: int, name: str) -> None:
    unsigned = status & 0xFFFFFFFF
    dos = int(_RtlNtStatusToDosError(status))
    if unsigned == _STATUS_NAME_COLLISION or dos in (_ERROR_ALREADY_EXISTS, _ERROR_FILE_EXISTS):
        raise FileExistsError(dos, "file exists", name)
    if unsigned == _STATUS_NAME_NOT_FOUND or dos in (_ERROR_FILE_NOT_FOUND, _ERROR_PATH_NOT_FOUND):
        raise FileNotFoundError(dos, "file not found", name)
    raise OSError(dos, f"NtCreateFile failed: 0x{unsigned:08x}", name)


def _last_error(message: str) -> OSError:
    return OSError(ctypes.get_last_error(), message)
