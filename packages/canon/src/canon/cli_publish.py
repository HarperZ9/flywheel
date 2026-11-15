from __future__ import annotations
import ctypes, errno, os, stat
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from . import concurrency_windows_api as _win
from .path_policy import is_reparse_point

_STAGE_PREFIX = ".canon-compile-"
_TEMP_ATTEMPTS = 8
_WIN_FILE_DIRECTORY_FILE = 0x1
_WIN_DIR_SHARE = _win.FILE_SHARE_READ | _win.FILE_SHARE_WRITE | _win.FILE_SHARE_DELETE
_WIN_FILE_SHARE = _win.FILE_SHARE_READ
_WIN_DIR_OPTS = _WIN_FILE_DIRECTORY_FILE | _win.FILE_OPEN_REPARSE_POINT | _win.FILE_SYNCHRONOUS_IO_NONALERT
_WIN_FILE_OPTS = _win.FILE_NON_DIRECTORY_FILE | _win.FILE_OPEN_REPARSE_POINT | _win.FILE_SYNCHRONOUS_IO_NONALERT
_WINDOWS_STAGE_RENAME_WITH_OPEN_ARTIFACTS = False
_FileRenameInformation = 10
_FlushFileBuffers = None
_NtSetInformationFile = None
_RtlNtStatusToDosError = None

class PublishError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code; super().__init__(code)

@dataclass(frozen=True, slots=True)
class _DirCap:
    path: Path; ref: int; key: tuple[int, int]

@dataclass(frozen=True, slots=True)
class _FileCap:
    name: str; ref: int; key: tuple[int, int]; data: bytes

class _RenameInfo(ctypes.Structure):
    _fields_ = [
        ("ReplaceIfExists", wintypes.BOOLEAN), ("RootDirectory", wintypes.HANDLE),
        ("FileNameLength", wintypes.DWORD), ("FileName", wintypes.WCHAR * 1),
    ]
class _IoStatusBlock(ctypes.Structure):
    _fields_ = [("Status", ctypes.c_ssize_t), ("Information", ctypes.c_size_t)]

def publish_new_bundle(target: Path, expected: tuple[tuple[str, bytes], ...], *, workspace_path: Path, workspace_key: tuple[int, int]) -> None:
    _require_safe_backend(); root = _open_root(workspace_path, workspace_key)
    try:
        parent = _open_parent(root, target.parent)
        try:
            _verify_cap_path(root); _verify_cap_path(parent); _ensure_target_absent(parent, target.name)
            _publish_under_parent(root, parent, target.name, expected)
        finally:
            if parent is not root: _close_dir(parent)
    finally:
        _close_dir(root)

def _publish_under_parent(root: _DirCap, parent: _DirCap, target_name: str, expected: tuple[tuple[str, bytes], ...]) -> None:
    stage: _DirCap | None = None; files: tuple[_FileCap, ...] = (); committed = False
    try:
        stage = _create_stage(parent); _verify_publish_caps(root, parent, stage)
        files = _write_stage(root, parent, stage, expected); _verify_publish_caps(root, parent, stage)
        _ensure_target_absent(parent, target_name); _verify_publish_caps(root, parent, stage)
        _verify_stage_files(files); _close_file_caps(files); files = ()
        _rename_stage(parent, stage, target_name)
        try:
            _verify_published_bundle(parent, target_name, expected)
        except PublishError:
            _close_dir(stage); stage = None; _cleanup_bundle_entry(parent, target_name); raise
        committed = True
    except FileExistsError as exc:
        raise PublishError("conflict") from exc
    except PublishError:
        raise
    except OSError as exc:
        raise PublishError("io_error") from exc
    finally:
        if stage is not None:
            _close_file_caps(files)
            if not committed: _cleanup_stage_files(stage, tuple(name for name, _data in expected))
            _close_dir(stage)
            if not committed: _cleanup_stage_entry(parent, stage.path.name)

def _write_stage(root: _DirCap, parent: _DirCap, stage: _DirCap, expected: tuple[tuple[str, bytes], ...]) -> tuple[_FileCap, ...]:
    files: list[_FileCap] = []
    try:
        for name, data in expected:
            _verify_publish_caps(root, parent, stage); files.append(_write_file(stage, name, data))
        return tuple(files)
    except Exception:
        _close_file_caps(tuple(files)); raise

def _verify_publish_caps(root: _DirCap, parent: _DirCap, stage: _DirCap) -> None:
    _verify_cap_path(root); _verify_cap_path(parent); _verify_cap_path(stage)

def _open_root(path: Path, expected_key: tuple[int, int]) -> _DirCap:
    if not _is_safe_dir_path(path): raise PublishError("unsafe_path")
    ref = _win_open_dir(path)
    cap = _DirCap(path, ref, _handle_key(ref))
    try:
        if cap.key != expected_key: raise PublishError("unsafe_path")
        _verify_cap_path(cap); return cap
    except Exception:
        _close_dir(cap); raise

def _open_parent(root: _DirCap, parent: Path) -> _DirCap:
    try: rel = parent.relative_to(root.path)
    except ValueError as exc: raise PublishError("unsafe_path") from exc
    cap = root
    for index, part in enumerate(rel.parts):
        _check_child_name(part); next_path = root.path.joinpath(*rel.parts[: index + 1])
        child = _open_child_dir(cap, part, next_path)
        if cap is not root: _close_dir(cap)
        cap = child
    return cap

def _open_child_dir(parent: _DirCap, name: str, path: Path) -> _DirCap:
    try:
        ref = _win_open_child(parent.ref, name)
        cap = _DirCap(path, ref, _handle_key(ref)); _verify_cap_path(cap); return cap
    except FileNotFoundError as exc:
        raise PublishError("unsafe_path") from exc
    except OSError as exc:
        raise PublishError("unsafe_path") from exc
    except Exception:
        if "ref" in locals(): _close_ref(ref)
        raise

def _create_stage(parent: _DirCap) -> _DirCap:
    for _attempt in range(_TEMP_ATTEMPTS):
        name = f"{_STAGE_PREFIX}{os.urandom(8).hex()}.tmp"
        try:
            ref = _win_create_stage(parent.ref, name)
            stage = _DirCap(parent.path / name, ref, _handle_key(ref)); _verify_cap_path(stage); return stage
        except FileExistsError:
            continue
        except Exception:
            if "stage" in locals(): _cleanup_bad_stage(parent, stage)
            elif "ref" in locals(): _close_ref(ref); _cleanup_stage_entry(parent, name)
            raise
    raise PublishError("io_error")

def _cleanup_bad_stage(parent: _DirCap, stage: _DirCap) -> None:
    try: _cleanup_stage_files(stage, ()); _close_dir(stage); _cleanup_stage_entry(parent, stage.path.name)
    except OSError: pass

def _write_file(stage: _DirCap, name: str, data: bytes) -> _FileCap:
    _check_child_name(name)
    return _win_write_file(stage, name, data)

def _win_write_file(stage: _DirCap, name: str, data: bytes) -> _FileCap:
    access = _win.GENERIC_READ | _win.GENERIC_WRITE | _win.SYNCHRONIZE
    handle = _win.nt_create_relative(stage.ref, name, access, _WIN_FILE_SHARE, _win.FILE_CREATE, _WIN_FILE_OPTS)
    try:
        cap = _FileCap(name, handle, _handle_key(handle), data)
        _verify_file_cap(cap, check_bytes=False)
        _verify_cap_path(stage); _win.write_file(handle, data); _win_flush(handle)
        _verify_file_cap(cap); return cap
    except Exception:
        _close_ref(handle); raise

def _verify_stage_files(files: tuple[_FileCap, ...]) -> None:
    for file in files: _verify_file_cap(file)

def _verify_published_bundle(parent: _DirCap, target_name: str, expected: tuple[tuple[str, bytes], ...]) -> None:
    published = _open_child_dir(parent, target_name, parent.path / target_name)
    try:
        _verify_cap_path(parent); _verify_cap_path(published)
        if set(os.listdir(published.path)) != {name for name, _data in expected}: raise PublishError("unsafe_path")
        for name, data in expected: _verify_published_file(published, name, data)
        _verify_cap_path(parent); _verify_cap_path(published)
    finally:
        _close_dir(published)

def _verify_published_file(parent: _DirCap, name: str, data: bytes) -> None:
    _check_child_name(name)
    ref = _win.nt_create_relative(parent.ref, name, _win.GENERIC_READ | _win.SYNCHRONIZE, _WIN_FILE_SHARE, _win.FILE_OPEN, _WIN_FILE_OPTS)
    try:
        _verify_file_cap(_FileCap(name, ref, _handle_key(ref), data))
    finally:
        _close_ref(ref)

def _verify_file_cap(file: _FileCap, *, check_bytes: bool = True) -> None:
    info = _win.handle_info(file.ref); attrs = int(info.dwFileAttributes)
    if attrs & _win.FILE_ATTRIBUTE_DIRECTORY or attrs & _win.FILE_ATTRIBUTE_REPARSE_POINT: raise PublishError("unsafe_path")
    if _handle_key(file.ref) != file.key: raise PublishError("unsafe_path")
    size = (int(info.nFileSizeHigh) << 32) | int(info.nFileSizeLow)
    if check_bytes and (size != len(file.data) or _win.read_file(file.ref, size) != file.data):
        raise PublishError("unsafe_path")

def _rename_stage(parent: _DirCap, stage: _DirCap, target_name: str) -> None:
    _check_child_name(target_name)
    _win_rename_by_handle(stage.ref, parent.ref, target_name)

def _ensure_target_absent(parent: _DirCap, name: str) -> None:
    _check_child_name(name)
    if not _exists_or_link(parent.path / name): return
    if is_reparse_point(parent.path / name): raise PublishError("unsafe_path")
    raise PublishError("conflict")

def _verify_cap_path(cap: _DirCap) -> None:
    if not _is_safe_dir_path(cap.path): raise PublishError("unsafe_path")
    if _path_key(cap.path) != cap.key or _handle_key(cap.ref) != cap.key: raise PublishError("unsafe_path")

def _is_safe_dir_path(path: Path) -> bool:
    try: info = path.lstat()
    except OSError: return False
    return stat.S_ISDIR(info.st_mode) and not is_reparse_point(path)

def _path_key(path: Path) -> tuple[int, int]:
    try: return _stat_key(path.lstat())
    except OSError as exc: raise PublishError("unsafe_path") from exc

def _handle_key(ref: int) -> tuple[int, int]:
    info = _win.handle_info(ref)
    return (int(info.dwVolumeSerialNumber), (int(info.nFileIndexHigh) << 32) | int(info.nFileIndexLow))

def _win_create_stage(parent_ref: int, name: str) -> int:
    access = _win.GENERIC_READ | _win.DELETE | _win.SYNCHRONIZE
    return _win.nt_create_relative(parent_ref, name, access, _WIN_DIR_SHARE, _win.FILE_CREATE, _WIN_DIR_OPTS)

def _win_open_dir(path: Path) -> int:
    flags = _win.FILE_FLAG_BACKUP_SEMANTICS | _win.FILE_FLAG_OPEN_REPARSE_POINT
    return _win.create_file(str(path), _win.GENERIC_READ | _win.SYNCHRONIZE, _WIN_DIR_SHARE, _win.OPEN_EXISTING, flags)

def _win_open_child(parent_ref: int, name: str) -> int:
    return _win.nt_create_relative(parent_ref, name, _win.GENERIC_READ | _win.SYNCHRONIZE, _WIN_DIR_SHARE, _win.FILE_OPEN, _WIN_DIR_OPTS)

def _win_rename_by_handle(stage_ref: int, parent_ref: int, target_name: str) -> None:
    _load_win_rename_api(); encoded = target_name.encode("utf-16-le")
    size = _RenameInfo.FileName.offset + len(encoded); buffer = ctypes.create_string_buffer(size)
    info = _RenameInfo.from_buffer(buffer); info.ReplaceIfExists = False; info.RootDirectory = wintypes.HANDLE(parent_ref)
    info.FileNameLength = len(encoded)
    ctypes.memmove(ctypes.addressof(buffer) + _RenameInfo.FileName.offset, encoded, len(encoded))
    ios = _IoStatusBlock()
    status = _NtSetInformationFile(wintypes.HANDLE(stage_ref), ctypes.byref(ios), buffer, size, _FileRenameInformation)
    if status >= 0: return
    error = int(_RtlNtStatusToDosError(status))
    if error in (80, 183): raise FileExistsError(error, "compile target exists", target_name)
    raise OSError(error, f"NtSetInformationFile rename failed: 0x{status & 0xFFFFFFFF:08x}")

def _win_flush(handle: int) -> None:
    _load_win_rename_api()
    if not _FlushFileBuffers(wintypes.HANDLE(handle)): raise OSError(ctypes.get_last_error(), "FlushFileBuffers failed")

def _load_win_rename_api() -> None:
    global _FlushFileBuffers, _NtSetInformationFile, _RtlNtStatusToDosError
    if _NtSetInformationFile is not None: return
    if not _win.supported(): raise OSError(errno.ENOSYS, "Windows publication primitive unavailable")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
    _NtSetInformationFile = ntdll.NtSetInformationFile
    _NtSetInformationFile.argtypes = [wintypes.HANDLE, ctypes.POINTER(_IoStatusBlock), wintypes.LPVOID, wintypes.ULONG, wintypes.ULONG]
    _NtSetInformationFile.restype = wintypes.LONG
    _RtlNtStatusToDosError = ntdll.RtlNtStatusToDosError
    _RtlNtStatusToDosError.argtypes = [wintypes.LONG]; _RtlNtStatusToDosError.restype = wintypes.ULONG
    _FlushFileBuffers = kernel32.FlushFileBuffers
    _FlushFileBuffers.argtypes = [wintypes.HANDLE]; _FlushFileBuffers.restype = wintypes.BOOL

def _require_safe_backend() -> None:
    if os.name != "nt" or not _win.supported():
        raise PublishError("unsafe_path")

def _cleanup_bundle_entry(parent: _DirCap, target_name: str) -> None:
    try:
        for child in (parent.path / target_name).iterdir():
            try: child.rmdir() if child.is_dir() and not is_reparse_point(child) else child.unlink(missing_ok=True)
            except OSError: pass
        (parent.path / target_name).rmdir()
    except OSError: pass

def _cleanup_stage_files(stage: _DirCap, names: tuple[str, ...]) -> None:
    for name in names:
        try:
            (stage.path / name).unlink(missing_ok=True)
        except OSError: pass

def _close_file_caps(files: tuple[_FileCap, ...]) -> None:
    for file in files:
        try: _close_ref(file.ref)
        except OSError: pass

def _cleanup_stage_entry(parent: _DirCap, stage_name: str) -> None:
    try:
        (parent.path / stage_name).rmdir()
    except OSError: pass

def _check_child_name(name: str) -> None:
    if type(name) is not str or name in ("", ".", "..") or "/" in name or "\\" in name or "\0" in name: raise PublishError("unsafe_path")

def _exists_or_link(path: Path) -> bool:
    try: return path.exists() or path.is_symlink()
    except OSError: return True

def _close_dir(cap: _DirCap) -> None:
    _close_ref(cap.ref)

def _close_ref(ref: int) -> None:
    _win.close_handle(ref)

def _stat_key(info: os.stat_result) -> tuple[int, int]:
    return (info.st_dev & 0xFFFFFFFF, info.st_ino)

__all__ = ["PublishError", "publish_new_bundle"]
