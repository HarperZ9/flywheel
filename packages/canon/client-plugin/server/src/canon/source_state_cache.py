from __future__ import annotations
from collections.abc import Mapping, Sequence
import errno
import json
import os
from pathlib import Path
import stat
import tempfile
from . import concurrency_windows_api as _win
from .canonical_json import CanonicalJSONError, canonical_json_text, sha256_text
from .path_policy import PathPolicyError, resolve_under_root
from .source_state import SourceStateError, SourceStateItem, assert_source_state, source_state_sha256

_CACHE_PREFIX = "sha256:"
_HEX = frozenset("0123456789abcdef")
_BUNDLES = "bundles"
_CURRENT = "current.json"
_TEMP_ATTEMPTS = 8
_WIN_FILE_DIRECTORY_FILE = 0x1
class SourceStateCacheError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code; super().__init__(f"{code}: {message}")
class SourceStateCache:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
    @staticmethod
    def key_for(source_items: Sequence[SourceStateItem], *, adapter_id: str, profile: str, budget: str, compiler_version: str, offline: bool) -> str:
        payload = {
            "adapter_id": _exact("adapter_id", adapter_id, str),
            "budget": _exact("budget", budget, str),
            "compiler_version": _exact("compiler_version", compiler_version, str),
            "offline": _exact("offline", offline, bool),
            "profile": _exact("profile", profile, str),
            "source_state_sha256": source_state_sha256(_snapshot_items(source_items)),
        }
        return sha256_text(canonical_json_text(payload))
    @staticmethod
    def assert_current(expected_sha256: str, current_items: Sequence[SourceStateItem]) -> None:
        assert_source_state(expected_sha256, _snapshot_items(current_items))
    def get(self, cache_key: str) -> dict[str, object] | None:
        digest = _cache_digest(cache_key)
        if self._root_missing(): return None
        _require_safe_backend()
        root_h = _open_root(self._root)
        try:
            path = self._entry_path(digest)
            return _read_object(root_h, (_BUNDLES,), path.name, "cache-entry", required=False)
        finally: _close_root(root_h)
    def put(self, cache_key: str, bundle: object) -> Path:
        digest = _cache_digest(cache_key)
        body = _canonical_text(_snapshot_bundle(bundle), code="invalid-cache-bundle")
        pointer = _canonical_text({"cache_key": cache_key}, code="invalid-cache-bundle")
        _require_safe_backend()
        try: self._root.mkdir(parents=True, exist_ok=True)
        except OSError as exc: raise SourceStateCacheError("invalid-cache-root", "cache root is invalid") from exc
        root_h = _open_root(self._root)
        try:
            self._safe_path(_CURRENT); path = self._entry_path(digest)
            _win_put(root_h, self._root, path, body, pointer) if os.name == "nt" else _posix_put(root_h, path.name, body, pointer)
            return path
        finally: _close_root(root_h)
    def current(self) -> dict[str, object] | None:
        if self._root_missing(): return None
        _require_safe_backend()
        root_h = _open_root(self._root)
        try:
            path = self._current_path()
            pointer = _read_object(root_h, (), path.name, "current-pointer", required=False)
            if pointer is None: return None
            key = _current_key(pointer)
            entry = self._entry_path(_cache_digest(key))
            current = _read_object(root_h, (_BUNDLES,), entry.name, "cache-entry", required=False)
            if current is None: raise SourceStateCacheError("missing-current-entry", "current entry is missing")
            return current
        finally: _close_root(root_h)
    def _entry_path(self, digest: str) -> Path:
        return self._safe_path(Path(_BUNDLES) / f"{digest}.json")
    def _current_path(self) -> Path:
        return self._safe_path(_CURRENT)
    def _safe_path(self, relative: str | Path) -> Path:
        try: return resolve_under_root(relative, root=self._root)
        except PathPolicyError as exc: raise SourceStateCacheError("unsafe-cache-path", "cache path is unsafe") from exc
    def _root_missing(self) -> bool:
        try: return not self._root.exists() and not self._root.is_symlink()
        except OSError: return False
def _snapshot_items(items: object) -> tuple[SourceStateItem, ...]:
    try: return tuple(items)  # type: ignore[arg-type]
    except Exception as exc: raise SourceStateError("invalid-source-state", "items must be a sequence") from exc
def _exact(name: str, value: object, typ: type) -> object:
    if type(value) is not typ: raise SourceStateCacheError("invalid-cache-dimension", f"{name} has invalid type")
    return value
def _cache_digest(cache_key: object) -> str:
    if type(cache_key) is not str or not cache_key.startswith(_CACHE_PREFIX) or len(cache_key) != 71: _invalid_cache_key()
    digest = cache_key[len(_CACHE_PREFIX):]
    if any(ch not in _HEX for ch in digest): _invalid_cache_key()
    return digest
def _invalid_cache_key() -> None:
    raise SourceStateCacheError("invalid-cache-key", "cache key must be sha256:<64 lowercase hex>")
def _snapshot_bundle(bundle: object) -> dict[str, object]:
    try: value = _snapshot_json(bundle)
    except SourceStateCacheError: raise
    except Exception as exc: raise SourceStateCacheError("invalid-cache-bundle", "bundle is invalid") from exc
    if type(value) is not dict: raise SourceStateCacheError("invalid-cache-bundle", "bundle must be a JSON object")
    return value
def _snapshot_json(value: object) -> object:
    if isinstance(value, Mapping):
        out: dict[str, object] = {}
        for key, item in tuple(value.items()):
            if type(key) is not str or key in out: raise SourceStateCacheError("invalid-cache-bundle", "bundle is invalid")
            out[key] = _snapshot_json(item)
        return out
    if isinstance(value, (list, tuple)): return [_snapshot_json(item) for item in tuple(value)]
    if value is None or type(value) in (str, bool, int, float): return value
    raise SourceStateCacheError("invalid-cache-bundle", "bundle is invalid")
def _canonical_text(value: dict[str, object], *, code: str) -> str:
    try: return canonical_json_text(value)
    except CanonicalJSONError as exc: raise SourceStateCacheError(code, "bundle is invalid") from exc
def _require_safe_backend() -> None:
    ok = _win.supported() if os.name == "nt" else _posix_supported()
    if not ok: raise SourceStateCacheError("unsafe-cache-path", "safe cache primitive unavailable")
def _kind_or_missing(path: Path, *, role: str, want, noun: str) -> bool:
    try: st = path.lstat()
    except FileNotFoundError: return False
    except OSError as exc: raise SourceStateCacheError("unsafe-cache-path", "cache path is unsafe") from exc
    if not want(st.st_mode): raise SourceStateCacheError(f"nonregular-{role}", f"cache path is not a {noun}")
    return True
def _regular_file_or_missing(path: Path, *, role: str) -> bool:
    return _kind_or_missing(path, role=role, want=stat.S_ISREG, noun="regular file")
def _read_object(root_h: int, parent: tuple[str, ...], name: str, role: str, *, required: bool = True) -> dict[str, object] | None:
    try:
        data = _win_read(root_h, parent, name, role) if os.name == "nt" else _posix_read(root_h, parent, name, role)
        if data is None and not required: return None
        if data is None: raise SourceStateCacheError("corrupt-cache-entry", "cache entry is corrupt")
        text = data.decode("utf-8"); value = json.loads(text)
    except SourceStateCacheError: raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc: raise SourceStateCacheError("corrupt-cache-entry", "cache entry is corrupt") from exc
    if type(value) is not dict or text != _canonical_text(value, code="corrupt-cache-entry"): raise SourceStateCacheError("corrupt-cache-entry", "cache entry is corrupt")
    return value
def _current_key(pointer: dict[str, object]) -> str:
    if set(pointer) != {"cache_key"}: raise SourceStateCacheError("corrupt-cache-entry", "cache entry is corrupt")
    try: _cache_digest(pointer["cache_key"])
    except SourceStateCacheError as exc: raise SourceStateCacheError("corrupt-cache-entry", "cache entry is corrupt") from exc
    return pointer["cache_key"]  # type: ignore[return-value]

def _open_root(root: Path) -> int:
    try: st = root.lstat()
    except OSError as exc: raise SourceStateCacheError("unsafe-cache-path", "cache path is unsafe") from exc
    if not stat.S_ISDIR(st.st_mode): raise SourceStateCacheError("unsafe-cache-path", "cache path is unsafe")
    handle = _win_open_dir(root) if os.name == "nt" else _posix_open_dir(root)
    try:
        _verify_root_identity(st, handle); return handle
    except Exception:
        _close_root(handle); raise
def _verify_root_identity(st: os.stat_result, handle: int) -> None:
    if os.name == "nt":
        info = _win.handle_info(handle); attrs = int(info.dwFileAttributes)
        index = (int(info.nFileIndexHigh) << 32) | int(info.nFileIndexLow)
        same = (st.st_dev & 0xFFFFFFFF) == int(info.dwVolumeSerialNumber) and index == st.st_ino and attrs & _win.FILE_ATTRIBUTE_DIRECTORY and not attrs & _win.FILE_ATTRIBUTE_REPARSE_POINT
    else:
        info = os.fstat(handle); same = (info.st_dev, info.st_ino) == (st.st_dev, st.st_ino)
    if not same: raise SourceStateCacheError("unsafe-cache-path", "cache root identity changed")
def _close_root(handle: int) -> None:
    _win.close_handle(handle) if os.name == "nt" else os.close(handle)
def _posix_supported() -> bool:
    return os.name != "nt" and os.open in os.supports_dir_fd and os.mkdir in os.supports_dir_fd and os.rename in os.supports_dir_fd and os.unlink in os.supports_dir_fd and hasattr(os, "pread") and all(hasattr(os, n) for n in ("O_DIRECTORY", "O_NOFOLLOW"))
def _posix_open_dir(path: str | Path, dir_fd: int | None = None) -> int:
    try: return os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW) if dir_fd is None else os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dir_fd)
    except FileNotFoundError: raise
    except NotADirectoryError as exc: raise SourceStateCacheError("nonregular-cache-directory", "cache path is not a directory") from exc
    except OSError as exc: raise SourceStateCacheError("unsafe-cache-path", "cache path is unsafe") from exc
def _posix_put(root_fd: int, entry_name: str, body: str, pointer: str) -> None:
    try: os.mkdir(_BUNDLES, 0o700, dir_fd=root_fd)
    except FileExistsError: pass
    except OSError as exc: raise SourceStateCacheError("unsafe-cache-path", "cache path is unsafe") from exc
    bundle_fd = _posix_open_dir(_BUNDLES, root_fd)
    try: _posix_write(bundle_fd, entry_name, body, "write-cache-entry", "cache-entry")
    finally: os.close(bundle_fd)
    _posix_write(root_fd, _CURRENT, pointer, "write-current-pointer", "current-pointer")
def _posix_write(dir_fd: int, name: str, text: str, code: str, role: str) -> None:
    _posix_existing_regular(dir_fd, name, role); data = text.encode("utf-8")
    for _attempt in range(_TEMP_ATTEMPTS):
        temp = f".{name}.{os.urandom(8).hex()}.tmp"
        try: fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=dir_fd)
        except FileExistsError: continue
        try:
            _posix_write_all(fd, data); os.fsync(fd); os.close(fd)
            os.rename(temp, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd); return
        except OSError as exc:
            try: os.close(fd)
            except OSError: pass
            _posix_unlink(dir_fd, temp); raise SourceStateCacheError(code, "cache write failed") from exc
    raise SourceStateCacheError(code, "cache write failed")
def _posix_existing_regular(dir_fd: int, name: str, role: str) -> None:
    try: fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dir_fd)
    except FileNotFoundError: return
    except OSError as exc: raise SourceStateCacheError("unsafe-cache-path", "cache path is unsafe") from exc
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode): raise SourceStateCacheError(f"nonregular-{role}", "cache path is not a regular file")
    finally: os.close(fd)
def _posix_read(root_fd: int, parent: tuple[str, ...], name: str, role: str) -> bytes | None:
    parent_fd = None
    try:
        dir_fd = root_fd
        if parent:
            try: parent_fd = _posix_open_dir(parent[0], root_fd)
            except FileNotFoundError: return None
            dir_fd = parent_fd
        return _posix_read_at(dir_fd, name, role)
    finally:
        if parent_fd is not None: os.close(parent_fd)
def _posix_read_at(dir_fd: int, name: str, role: str) -> bytes | None:
    try: fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dir_fd)
    except FileNotFoundError: return None
    except OSError as exc:
        code = "unsafe-cache-path" if exc.errno in (errno.ELOOP, errno.ENOTDIR) else "corrupt-cache-entry"
        raise SourceStateCacheError(code, "cache path is unsafe") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode): raise SourceStateCacheError(f"nonregular-{role}", "cache path is not a regular file")
        return _posix_pread_all(fd, info.st_size)
    finally: os.close(fd)
def _posix_write_all(fd: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        written = os.write(fd, data[offset:])
        if written <= 0: raise OSError(errno.EIO, "cache write made no progress")
        offset += written
def _posix_pread_all(fd: int, size: int) -> bytes:
    out: list[bytes] = []; offset = 0
    while offset < size:
        chunk = os.pread(fd, size - offset, offset)
        if not chunk: break
        out.append(chunk); offset += len(chunk)
    return b"".join(out)
def _posix_unlink(dir_fd: int, name: str) -> None:
    try: os.unlink(name, dir_fd=dir_fd)
    except FileNotFoundError: pass
def _win_put(root_h: int, root: Path, bundle_path: Path, body: str, pointer: str) -> None:
    bundle_dir = root / _BUNDLES
    try: bundle_dir.mkdir(exist_ok=True)
    except OSError as exc: raise SourceStateCacheError("unsafe-cache-path", "cache path is unsafe") from exc
    bundle_h = _win_open_dir((root_h, _BUNDLES))
    try: _win_write_path(bundle_path, body, "write-cache-entry", "cache-entry")
    finally: _win.close_handle(bundle_h)
    _win_write_path(root / _CURRENT, pointer, "write-current-pointer", "current-pointer")
def _win_open_dir(path: Path | tuple[int, str]) -> int:
    try:
        if isinstance(path, tuple):
            handle = _win.nt_create_relative(path[0], path[1], _win.GENERIC_READ, _win.FILE_SHARE_READ | _win.FILE_SHARE_WRITE, _win.FILE_OPEN, _WIN_FILE_DIRECTORY_FILE | _win.FILE_OPEN_REPARSE_POINT)
        else:
            handle = _win.create_file(str(path), _win.GENERIC_READ, _win.FILE_SHARE_READ | _win.FILE_SHARE_WRITE, _win.OPEN_EXISTING, _win.FILE_FLAG_BACKUP_SEMANTICS | _win.FILE_FLAG_OPEN_REPARSE_POINT)
    except FileNotFoundError: raise
    except OSError as exc:
        if getattr(exc, "errno", None) in (errno.ENOTDIR, 267): raise SourceStateCacheError("nonregular-cache-directory", "cache path is not a directory") from exc
        raise SourceStateCacheError("unsafe-cache-path", "cache path is unsafe") from exc
    try:
        attrs = _win.handle_info(handle).dwFileAttributes
        if not attrs & _win.FILE_ATTRIBUTE_DIRECTORY or attrs & _win.FILE_ATTRIBUTE_REPARSE_POINT: raise SourceStateCacheError("unsafe-cache-path", "cache path is unsafe")
        return handle
    except Exception:
        _win.close_handle(handle); raise
def _win_write_path(target: Path, text: str, code: str, role: str) -> None:
    _regular_file_or_missing(target, role=role); temp_path: Path | None = None
    for _attempt in range(_TEMP_ATTEMPTS):
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=target.parent, prefix=f".{target.name}.", suffix=".tmp", delete=False) as handle:
                temp_path = Path(handle.name); handle.write(text); handle.flush(); os.fsync(handle.fileno())
            os.replace(temp_path, target); return
        except FileExistsError as exc:
            _cleanup_temp(temp_path)
            if temp_path is not None: raise SourceStateCacheError(code, "cache write failed") from exc
            continue
        except OSError as exc:
            _cleanup_temp(temp_path); raise SourceStateCacheError(code, "cache write failed") from exc
    raise SourceStateCacheError(code, "cache write failed")
def _win_read(root_h: int, parent: tuple[str, ...], name: str, role: str) -> bytes | None:
    parent_h = None
    try:
        dir_h = root_h
        if parent:
            try: parent_h = _win_open_dir((root_h, parent[0]))
            except FileNotFoundError: return None
            dir_h = parent_h
        return _win_read_at(dir_h, name, role)
    finally:
        if parent_h is not None: _win.close_handle(parent_h)
def _win_read_at(dir_h: int, name: str, role: str) -> bytes | None:
    try: handle = _win.nt_create_relative(dir_h, name, _win.GENERIC_READ | _win.SYNCHRONIZE, _win.FILE_SHARE_READ | _win.FILE_SHARE_WRITE | _win.FILE_SHARE_DELETE, _win.FILE_OPEN, _win.FILE_NON_DIRECTORY_FILE | _win.FILE_OPEN_REPARSE_POINT | _win.FILE_SYNCHRONOUS_IO_NONALERT)
    except FileNotFoundError: return None
    except OSError as exc: raise SourceStateCacheError("unsafe-cache-path", "cache path is unsafe") from exc
    try:
        info = _win.handle_info(handle); attrs = int(info.dwFileAttributes)
        if attrs & _win.FILE_ATTRIBUTE_REPARSE_POINT: raise SourceStateCacheError("unsafe-cache-path", "cache path is unsafe")
        if attrs & _win.FILE_ATTRIBUTE_DIRECTORY: raise SourceStateCacheError(f"nonregular-{role}", "cache path is not a regular file")
        return _win.read_file(handle, (int(info.nFileSizeHigh) << 32) | int(info.nFileSizeLow))
    finally: _win.close_handle(handle)
def _cleanup_temp(path: Path | None) -> None:
    if path is None: return
    try: path.unlink(missing_ok=True)
    except OSError: pass
