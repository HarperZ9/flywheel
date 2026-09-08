"""Descriptor-bound file opening for local read_file."""
from __future__ import annotations

from dataclasses import dataclass
import os
import stat
import sys

PATH_ESCAPED = "[error] read_file_path_escaped (escapes root)"
OPEN_FAILED = "[error] read_file_open_failed"
NOT_REGULAR = "[error] read_file_not_regular"
SOURCE_DRIFT = "[error] read_file_source_drift"
HANDLE_PATH_UNSUPPORTED = "[error] read_file_handle_path_unsupported"


@dataclass(frozen=True)
class ConfinedReadHandle:
    fd: int
    st: os.stat_result


def open_confined_read_handle(root: str, target: str) -> ConfinedReadHandle | str:
    opened = _open_readonly(target)
    if isinstance(opened, str):
        return opened
    fd = opened
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            os.close(fd)
            return NOT_REGULAR
        bound = _opened_handle_inside_root(fd, root)
        if bound is None:
            os.close(fd)
            return HANDLE_PATH_UNSUPPORTED
        if not bound:
            os.close(fd)
            return PATH_ESCAPED
        try:
            path_st = os.stat(target)
        except OSError:
            os.close(fd)
            return SOURCE_DRIFT
        if not _same_open_snapshot(st, path_st):
            os.close(fd)
            return SOURCE_DRIFT
        return ConfinedReadHandle(fd, st)
    except Exception:
        os.close(fd)
        raise


def _open_readonly(target: str) -> int | str:
    flags = os.O_RDONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        return os.open(target, flags)
    except OSError:
        return OPEN_FAILED


def _opened_handle_inside_root(fd: int, root: str) -> bool | None:
    handle_path = _opened_handle_path(fd)
    if handle_path is None:
        return None
    root_cmp = _canonical_compare_path(root)
    handle_cmp = _canonical_compare_path(handle_path)
    if root_cmp is None or handle_cmp is None:
        return None
    try:
        return os.path.commonpath([root_cmp, handle_cmp]) == root_cmp
    except ValueError:
        return False


def _opened_handle_path(fd: int) -> str | None:
    if os.name == "nt":
        return _windows_handle_path(fd)
    if sys.platform == "darwin":
        return _darwin_handle_path(fd)
    return _proc_fd_path(fd)


def _windows_handle_path(fd: int) -> str | None:
    try:
        import ctypes
        import msvcrt
        from ctypes import wintypes
    except ImportError:
        return None
    try:
        handle = msvcrt.get_osfhandle(fd)
    except OSError:
        return None
    if handle == -1:
        return None
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_final = kernel32.GetFinalPathNameByHandleW
    get_final.argtypes = [
        wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    get_final.restype = wintypes.DWORD
    size = 260
    while size <= 32768:
        buf = ctypes.create_unicode_buffer(size)
        copied = get_final(wintypes.HANDLE(handle), buf, size, 0)
        if copied == 0:
            return None
        if copied < size:
            return buf.value
        size = copied + 1
    return None


def _darwin_handle_path(fd: int) -> str | None:
    try:
        import fcntl
    except ImportError:
        return None
    cmd = getattr(fcntl, "F_GETPATH", 50)
    try:
        raw = fcntl.fcntl(fd, cmd, b"\0" * 1024)
    except OSError:
        return None
    if not isinstance(raw, (bytes, bytearray)):
        return None
    path, separator, _ = bytes(raw).partition(b"\0")
    if not separator or not path.startswith(b"/"):
        return None
    try:
        return path.decode("utf-8", "surrogateescape")
    except UnicodeDecodeError:
        return None


def _proc_fd_path(fd: int) -> str | None:
    proc = f"/proc/self/fd/{fd}"
    if not os.path.exists(proc):
        return None
    try:
        path = os.readlink(proc)
    except OSError:
        return None
    if not os.path.isabs(path) or path.endswith(" (deleted)"):
        return None
    return path


def _canonical_compare_path(path: str) -> str | None:
    if os.name == "nt":
        return _windows_compare_path(path)
    return os.path.normcase(os.path.normpath(os.path.realpath(path)))


def _windows_compare_path(path: str) -> str | None:
    stripped = _strip_windows_namespace(path)
    if stripped is None:
        return None
    if _is_windows_volume_path(stripped):
        return os.path.normcase(os.path.normpath(stripped))
    real = os.path.realpath(stripped)
    volume_path = _windows_volume_compare_path(real)
    if volume_path is not None:
        return volume_path
    return os.path.normcase(os.path.normpath(real))


def _strip_windows_namespace(path: str) -> str | None:
    path = path.replace("/", "\\")
    upper = path.upper()
    if upper.startswith("\\\\?\\UNC\\"):
        return "\\\\" + path[8:]
    if upper.startswith("\\\\?\\") or upper.startswith("\\\\.\\"):
        rest = path[4:]
        if len(rest) >= 3 and rest[1:3] == ":\\":
            return rest
        if rest.upper().startswith("UNC\\"):
            return "\\\\" + rest[4:]
        if rest.upper().startswith("VOLUME{"):
            return "\\\\?\\" + rest
        return None
    if upper.startswith("\\??\\UNC\\"):
        return "\\\\" + path[8:]
    if upper.startswith("\\??\\"):
        rest = path[4:]
        if len(rest) >= 3 and rest[1:3] == ":\\":
            return rest
        if rest.upper().startswith("VOLUME{"):
            return "\\\\?\\" + rest
        return None
    return path


def _is_windows_volume_path(path: str) -> bool:
    return path.upper().startswith("\\\\?\\VOLUME{")


def _is_windows_unc_path(path: str) -> bool:
    return path.startswith("\\\\") and not _is_windows_volume_path(path)


def _windows_volume_compare_path(path: str) -> str | None:
    if _is_windows_unc_path(path):
        return None
    volume_root = _windows_volume_path_name(path)
    if not volume_root:
        return None
    volume_name = _windows_volume_name(volume_root)
    if not volume_name:
        return None
    try:
        suffix = os.path.relpath(path, volume_root)
    except ValueError:
        return None
    base = volume_name.rstrip("\\")
    combined = base if suffix in ("", ".") else base + "\\" + suffix
    return os.path.normcase(os.path.normpath(combined))


def _windows_volume_path_name(path: str) -> str | None:
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return None
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_volume_path = kernel32.GetVolumePathNameW
    get_volume_path.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
    get_volume_path.restype = wintypes.BOOL
    buf = ctypes.create_unicode_buffer(32768)
    if not get_volume_path(path, buf, len(buf)):
        return None
    return buf.value


def _windows_volume_name(volume_root: str) -> str | None:
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return None
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_volume_name = kernel32.GetVolumeNameForVolumeMountPointW
    get_volume_name.argtypes = [
        wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
    get_volume_name.restype = wintypes.BOOL
    buf = ctypes.create_unicode_buffer(260)
    if not get_volume_name(volume_root, buf, len(buf)):
        return None
    return buf.value


def _same_open_snapshot(left, right) -> bool:
    return (int(left.st_dev), int(left.st_ino), int(left.st_size),
            int(left.st_mtime_ns)) == (
            int(right.st_dev), int(right.st_ino), int(right.st_size),
            int(right.st_mtime_ns))
