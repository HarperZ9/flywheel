from __future__ import annotations
import errno
import os
import stat
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from . import concurrency_windows_api as _win
from .canonical_json import canonical_json_text
from .path_policy import PathPolicyError, assert_not_protected, is_reparse_point, resolve_under_root
CONFIG_SCHEMA = "canon.init-state/v1"
STATE_DIRS = ("cache", "witnesses", "undo")
CONFIG_NAME = "config.json"
_RESERVED_STATE_PARTS = frozenset({
    "agents.md", "claude.md", "soul.md", "gemini.md", "codex.md",
    ".chatgpt", ".claude", ".codex", ".vscode", ".idea", ".cursor",
    ".windsurf", ".opencode", ".github", ".git",
})
_TEMP_ATTEMPTS = 8
_WIN_FILE_DIRECTORY_FILE = 0x1
_WIN_SHARE = _win.FILE_SHARE_READ | _win.FILE_SHARE_WRITE
_WIN_DIR_OPTS = _WIN_FILE_DIRECTORY_FILE | _win.FILE_OPEN_REPARSE_POINT | _win.FILE_SYNCHRONOUS_IO_NONALERT
_WIN_FILE_OPTS = _win.FILE_OPEN_REPARSE_POINT | _win.FILE_SYNCHRONOUS_IO_NONALERT
@dataclass(frozen=True, slots=True)
class InitReport:
    ok: bool; failure_code: str; message: str; data: dict[str, object]
@dataclass(frozen=True, slots=True)
class _Plan:
    workspace: Path; state_dir: Path; state_rel: str
    state_parts: tuple[str, ...]; entries: tuple[str, ...]; config: bytes
@dataclass(frozen=True, slots=True)
class _DirCap:
    path: Path; ref: int
class _InitFailure(Exception):
    def __init__(self, code: str) -> None:
        self.code = code; super().__init__(code)
def run_init(*, workspace: str, state_dir: str | None, apply: bool) -> InitReport:
    try:
        plan = _build_plan(workspace, state_dir)
        if not apply: return _ok("preview ready", _data("preview", plan))
        _apply_plan(plan); return _ok("initialized canon state", _data("apply", plan))
    except _InitFailure as exc:
        return _fail(exc.code)
    except (OSError, PathPolicyError):
        return _fail("unsafe_path")
def _build_plan(workspace: object, state_dir: object) -> _Plan:
    workspace_path = _workspace_path(_text(workspace))
    state_raw = ".canon" if state_dir is None else _text(state_dir)
    try:
        state_path = resolve_under_root(state_raw, root=workspace_path); assert_not_protected(state_path)
    except PathPolicyError as exc:
        raise _InitFailure("unsafe_path") from exc
    rel = _relative_text(state_path, workspace_path); parts = tuple(Path(rel).parts)
    if not parts or any(part in ("", ".", "..") for part in parts): raise _InitFailure("unsafe_path")
    _reject_reserved_parts(parts)
    config = canonical_json_text(_config_payload(parts)).encode("utf-8")
    return _Plan(workspace_path, state_path, rel, parts, _entries(rel), config)
def _apply_plan(plan: _Plan) -> None:
    _require_safe_backend(); workspace = _open_dir(plan.workspace)
    try:
        parent = _open_parent(workspace, plan)
        try:
            _mkdir_child(parent, plan.state_parts[-1]); state = _open_child(parent, plan.state_parts[-1], plan.state_dir)
        finally:
            _close_if_child(parent, workspace)
        try:
            exists = _preflight_config(state, plan.config)
            for child in STATE_DIRS:
                _mkdir_child(state, child); _close(_open_child(state, child, plan.state_dir / child))
            if not exists:
                try: _publish_config(state, plan)
                except OSError as exc: raise _InitFailure("io_error") from exc
        finally:
            _close(state)
    finally:
        _close(workspace)
def _preflight_config(state: _DirCap, config: bytes) -> bool:
    existing = _read_config(state)
    if existing is None: return False
    if existing != config: raise _InitFailure("conflict")
    return True
def _publish_config(state: _DirCap, plan: _Plan) -> None:
    try:
        if os.name == "nt": _win_publish_config(plan.state_dir, plan.config)
        else: _posix_publish_config(state.ref, plan.config)
    except _InitFailure:
        raise
    except OSError as exc:
        raise _InitFailure("io_error") from exc
def _workspace_path(raw: str) -> Path:
    path = Path(raw)
    try:
        info = path.lstat(); resolved = path.resolve(strict=True); after = path.lstat()
    except OSError as exc:
        raise _InitFailure("unsafe_path") from exc
    if _stat_key(info) != _stat_key(after): raise _InitFailure("unsafe_path")
    if not stat.S_ISDIR(info.st_mode) or is_reparse_point(path): raise _InitFailure("unsafe_path")
    return resolved
def _text(value: object) -> str:
    if type(value) is not str or value == "" or "\0" in value: raise _InitFailure("unsafe_path")
    return value
def _reject_reserved_parts(parts: tuple[str, ...]) -> None:
    if any(_normalized_part(part) in _RESERVED_STATE_PARTS for part in parts): raise _InitFailure("unsafe_path")
def _normalized_part(part: str) -> str:
    return unicodedata.normalize("NFKC", part).rstrip(" .").casefold()
def _config_payload(parts: tuple[str, ...]) -> dict[str, object]:
    return {"canon_schema": CONFIG_SCHEMA, "workspace": {"relative_from_state_dir": "/".join(".." for _ in parts)}}
def _entries(state_rel: str) -> tuple[str, ...]:
    return tuple(f"{state_rel}/{name}" for name in (*STATE_DIRS, CONFIG_NAME))
def _data(mode: str, plan: _Plan) -> dict[str, object]:
    return {"mode": mode, "state_dir": plan.state_rel, "would_create": list(plan.entries)}
def _ok(message: str, data: dict[str, object]) -> InitReport:
    return InitReport(True, "ok", message, data)
def _fail(code: str) -> InitReport:
    message = {"conflict": "canon state conflict", "io_error": "canon init I/O failed"}.get(code, "unsafe init path")
    return InitReport(False, code, message, {"mode": "error"})
def _relative_text(path: Path, root: Path) -> str:
    try: rel = os.path.relpath(path, root)
    except ValueError as exc: raise _InitFailure("unsafe_path") from exc
    return rel.replace(os.sep, "/")
def _require_safe_backend() -> None:
    ok = _win.supported() if os.name == "nt" else _posix_supported()
    if not ok: raise _InitFailure("unsafe_path")
def _posix_supported() -> bool:
    required = (os.open, os.mkdir, os.unlink, os.link, os.stat)
    return os.name != "nt" and all(fn in os.supports_dir_fd for fn in required) and hasattr(os, "pread") and all(hasattr(os, name) for name in ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK"))
def _open_dir(path: Path) -> _DirCap:
    try: info = path.lstat()
    except OSError as exc: raise _InitFailure("unsafe_path") from exc
    if not stat.S_ISDIR(info.st_mode) or is_reparse_point(path): raise _InitFailure("unsafe_path")
    ref = _win_open_dir(path) if os.name == "nt" else _posix_open_dir(path)
    try:
        _verify_dir(info, ref); return _DirCap(path, ref)
    except Exception:
        _close_ref(ref); raise
def _open_parent(root: _DirCap, plan: _Plan) -> _DirCap:
    cap = root
    for index, part in enumerate(plan.state_parts[:-1]):
        previous = cap
        try: cap = _open_child(previous, part, plan.workspace.joinpath(*plan.state_parts[: index + 1]))
        finally:
            if previous is not root: _close(previous)
    return cap
def _open_child(parent: _DirCap, name: str, path: Path) -> _DirCap:
    try:
        ref = _win_open_child(parent.ref, name) if os.name == "nt" else _posix_open_dir(name, parent.ref)
        info = path.lstat(); _verify_dir(info, ref); return _DirCap(path, ref)
    except FileNotFoundError as exc:
        raise _InitFailure("unsafe_path") from exc
    except OSError as exc:
        raise _InitFailure("unsafe_path") from exc
def _mkdir_child(parent: _DirCap, name: str) -> None:
    try:
        if os.name == "nt": _win_mkdir_child(parent.ref, name)
        else: os.mkdir(name, 0o700, dir_fd=parent.ref)
    except FileExistsError:
        return
    except OSError as exc:
        raise _InitFailure("io_error") from exc
def _read_config(state: _DirCap) -> bytes | None:
    try: return _win_read_config(state.ref) if os.name == "nt" else _posix_read_config(state.ref)
    except FileNotFoundError: return None
    except _InitFailure: raise
    except OSError as exc: raise _InitFailure("unsafe_path") from exc
def _posix_open_dir(path: str | Path, dir_fd: int | None = None) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    return os.open(path, flags) if dir_fd is None else os.open(path, flags, dir_fd=dir_fd)
def _posix_read_config(dir_fd: int) -> bytes | None:
    try: before = os.stat(CONFIG_NAME, dir_fd=dir_fd, follow_symlinks=False)
    except FileNotFoundError: return None
    if not stat.S_ISREG(before.st_mode):
        raise _InitFailure("unsafe_path" if stat.S_ISLNK(before.st_mode) else "conflict")
    try: fd = os.open(CONFIG_NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dir_fd)
    except OSError as exc:
        raise _InitFailure("unsafe_path") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or _stat_key(info) != _stat_key(before): raise _InitFailure("conflict")
        return os.pread(fd, info.st_size, 0)
    finally:
        os.close(fd)
def _posix_publish_config(dir_fd: int, data: bytes) -> None:
    temp = _create_posix_temp(dir_fd, data)
    try:
        os.link(temp, CONFIG_NAME, src_dir_fd=dir_fd, dst_dir_fd=dir_fd, follow_symlinks=False)
    except FileExistsError as exc:
        if _posix_read_config(dir_fd) == data: return
        raise _InitFailure("conflict") from exc
    finally:
        _posix_unlink(dir_fd, temp)
def _create_posix_temp(dir_fd: int, data: bytes) -> str:
    for _attempt in range(_TEMP_ATTEMPTS):
        name = f".{CONFIG_NAME}.{os.urandom(8).hex()}.tmp"
        try: fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=dir_fd)
        except FileExistsError: continue
        try:
            try:
                _write_all(fd, data); os.fsync(fd)
            finally:
                os.close(fd)
        except OSError:
            _posix_unlink(dir_fd, name); raise
        return name
    raise OSError(errno.EEXIST, "temp name collision")
def _write_all(fd: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        written = os.write(fd, data[offset:])
        if written <= 0: raise OSError(errno.EIO, "init write made no progress")
        offset += written
def _posix_unlink(dir_fd: int, name: str) -> None:
    try: os.unlink(name, dir_fd=dir_fd)
    except FileNotFoundError: return
def _win_open_dir(path: Path) -> int:
    return _win_checked_dir(_win.create_file(str(path), _win.GENERIC_READ, _WIN_SHARE, _win.OPEN_EXISTING, _win.FILE_FLAG_BACKUP_SEMANTICS | _win.FILE_FLAG_OPEN_REPARSE_POINT))
def _win_open_child(dir_ref: int, name: str) -> int:
    return _win_checked_dir(_win.nt_create_relative(dir_ref, name, _win.GENERIC_READ | _win.SYNCHRONIZE, _WIN_SHARE, _win.FILE_OPEN, _WIN_DIR_OPTS))
def _win_mkdir_child(dir_ref: int, name: str) -> None:
    handle = _win.nt_create_relative(dir_ref, name, _win.GENERIC_READ | _win.SYNCHRONIZE, _WIN_SHARE, _win.FILE_CREATE, _WIN_DIR_OPTS)
    _win.close_handle(handle)
def _win_checked_dir(handle: int) -> int:
    try:
        attrs = int(_win.handle_info(handle).dwFileAttributes)
        if not attrs & _win.FILE_ATTRIBUTE_DIRECTORY or attrs & _win.FILE_ATTRIBUTE_REPARSE_POINT:
            raise OSError(errno.ELOOP, "init directory is unsafe")
        return handle
    except Exception:
        _win.close_handle(handle); raise
def _win_read_config(dir_ref: int) -> bytes | None:
    handle = _win.nt_create_relative(dir_ref, CONFIG_NAME, _win.GENERIC_READ | _win.SYNCHRONIZE, _WIN_SHARE, _win.FILE_OPEN, _WIN_FILE_OPTS)
    try:
        info = _win.handle_info(handle); attrs = int(info.dwFileAttributes)
        if attrs & _win.FILE_ATTRIBUTE_REPARSE_POINT: raise _InitFailure("unsafe_path")
        if attrs & _win.FILE_ATTRIBUTE_DIRECTORY: raise _InitFailure("conflict")
        return _win.read_file(handle, (int(info.nFileSizeHigh) << 32) | int(info.nFileSizeLow))
    finally:
        _win.close_handle(handle)
def _win_publish_config(state_dir: Path, data: bytes) -> None:
    temp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=state_dir, prefix=f".{CONFIG_NAME}.", suffix=".tmp", delete=False) as handle:
            temp = Path(handle.name); handle.write(data); handle.flush(); os.fsync(handle.fileno())
        os.rename(temp, state_dir / CONFIG_NAME)
    except FileExistsError as exc:
        raise _InitFailure("conflict") from exc
    finally:
        if temp is not None: _cleanup_temp(temp)
def _cleanup_temp(path: Path) -> None:
    try: path.unlink(missing_ok=True)
    except OSError: return
def _verify_dir(info: os.stat_result, ref: int) -> None:
    if os.name == "nt":
        handle_info = _win.handle_info(ref); attrs = int(handle_info.dwFileAttributes)
        index = (int(handle_info.nFileIndexHigh) << 32) | int(handle_info.nFileIndexLow)
        same = (info.st_dev & 0xFFFFFFFF) == int(handle_info.dwVolumeSerialNumber) and index == info.st_ino
        if not same or not attrs & _win.FILE_ATTRIBUTE_DIRECTORY or attrs & _win.FILE_ATTRIBUTE_REPARSE_POINT:
            raise _InitFailure("unsafe_path")
        return
    if _stat_key(os.fstat(ref)) != _stat_key(info): raise _InitFailure("unsafe_path")
def _stat_key(info: os.stat_result) -> tuple[int, int]:
    return (info.st_dev, info.st_ino)
def _close_if_child(cap: _DirCap, root: _DirCap) -> None:
    if cap is not root: _close(cap)
def _close(cap: _DirCap) -> None:
    _close_ref(cap.ref)
def _close_ref(ref: int) -> None:
    if os.name == "nt": _win.close_handle(ref)
    else: os.close(ref)
__all__ = ["CONFIG_SCHEMA", "InitReport", "run_init"]
