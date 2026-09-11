"""Windows implementation for private artifact filesystem custody."""
from __future__ import annotations
from dataclasses import dataclass
import os
from .private_artifact_fs_listing import ArtifactListing
from pathlib import Path, PureWindowsPath
from .private_artifact_fs import BUSY, CLOSED, CONFLICT, IO_ERROR, NOT_FOUND, NOT_REGULAR
from .private_artifact_fs import TOO_LARGE, UNSAFE_PATH, ArtifactIdentity, PrivateArtifactError
from . import private_artifact_fs_windows_api as _win
from .private_artifact_fs_windows_tail import absolute_existing as _absolute_existing, borrowed_descriptor as _borrowed_descriptor
from .private_artifact_fs_windows_tail import check_name as _check_name, close_handle as _close_handle, handle_identity as _handle_identity
from .private_artifact_fs_windows_tail import handle_identity_from_info as _handle_identity_from_info, is_dir as _is_dir, is_reparse as _is_reparse, path_identity as _path_identity
from .private_artifact_fs_windows_tail import raise_dir_error as _raise_dir_error, raise_open_error as _raise_open_error, relative_parts as _relative_parts, size as _size, write_time as _write_time
_READ_DIR_SHARE, _WRITE_DIR_SHARE = _win.FILE_SHARE_READ, _win.FILE_SHARE_READ | _win.FILE_SHARE_WRITE
_READ_SHARE, _TEMP_ATTEMPTS = _win.FILE_SHARE_READ, 8
_DIR_OPTS = _win.FILE_DIRECTORY_FILE | _win.FILE_OPEN_REPARSE_POINT | _win.FILE_SYNCHRONOUS_IO_NONALERT
_FILE_OPTS = _win.FILE_NON_DIRECTORY_FILE | _win.FILE_OPEN_REPARSE_POINT | _win.FILE_SYNCHRONOUS_IO_NONALERT
@dataclass(frozen=True, slots=True)
class _DirCap:
    path: Path
    handle: int
    identity: ArtifactIdentity
def supported() -> bool:
    return _win.supported()
def identity_for_root(root: Path) -> ArtifactIdentity:
    caps = _open_root_chain(root, None)
    try:
        return caps[-1].identity
    finally:
        _close_caps(caps)
class ArtifactRoot(ArtifactListing):
    def __init__(self, root: Path, expected: ArtifactIdentity | None, writable: bool = True) -> None:
        self._root_path = _absolute_existing(root)
        self._expected = expected
        self._caps: list[_DirCap] = []
        self._closed = False
        self._writable, self._dir_share = bool(writable), _WRITE_DIR_SHARE if writable else _READ_DIR_SHARE
    def __enter__(self) -> ArtifactRoot:
        if self._closed:
            raise PrivateArtifactError(CLOSED)
        self._caps = _open_root_chain(self._root_path, self._expected, self._dir_share)
        return self
    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
    def close(self) -> None:
        caps, self._caps = self._caps, []
        _close_caps(caps)
        self._closed = True
    @property
    def identity(self) -> ArtifactIdentity:
        if self._closed or not self._caps: raise PrivateArtifactError(CLOSED)
        return self._caps[-1].identity
    def borrow_descriptor(self):
        if self._closed or not self._caps: raise PrivateArtifactError(CLOSED)
        cap = self._caps[-1]; return _borrowed_descriptor(cap.handle, cap.identity)
    def read_bytes(self, rel: str | os.PathLike[str], *, max_bytes: int) -> bytes:
        if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 0:
            raise PrivateArtifactError(UNSAFE_PATH)
        parts = _relative_parts(rel)
        chain = self._parent_chain(parts[:-1], create=False)
        try:
            return _read_at(chain, parts[-1], max_bytes)
        finally:
            _close_caps(chain[len(self._caps):])
    def write_new_or_same(self, rel: str | os.PathLike[str], data: bytes) -> str:
        if not self._writable: raise PrivateArtifactError(BUSY)
        if type(data) is not bytes:
            raise PrivateArtifactError(UNSAFE_PATH)
        parts = _relative_parts(rel)
        chain = self._parent_chain(parts[:-1], create=True)
        try:
            return _write_new_or_same(chain, parts[-1], data)
        finally:
            _close_caps(chain[len(self._caps):])
    publish_bytes = write_new_or_same
    def _parent_chain(self, parts: tuple[str, ...], *, create: bool) -> list[_DirCap]:
        if self._closed or not self._caps:
            raise PrivateArtifactError(CLOSED)
        base = self._caps
        _verify_chain(base)
        chain = list(base)
        parent = chain[-1]
        try:
            for part in parts:
                child_path = parent.path / part
                try:
                    child = _open_child_dir(parent, part, child_path, self._dir_share)
                except FileNotFoundError:
                    if not create:
                        raise PrivateArtifactError(NOT_FOUND) from None
                    _mkdir(parent, part, self._dir_share)
                    child = _open_child_dir(parent, part, child_path, self._dir_share)
                chain.append(child)
                parent = child
                _verify_chain(chain)
            return chain
        except Exception:
            _close_caps(chain[len(base):])
            raise
def _open_root_chain(root: Path, expected: ArtifactIdentity | None, share: int = _READ_DIR_SHARE) -> list[_DirCap]:
    root = _absolute_existing(root)
    parts = root.parts
    if not parts or not PureWindowsPath(parts[0]).is_absolute():
        raise PrivateArtifactError(UNSAFE_PATH)
    caps: list[_DirCap] = []
    try:
        caps.append(_open_dir_path(Path(parts[0]), share))
        for part in parts[1:]:
            _check_name(part)
            caps.append(_open_child_dir(caps[-1], part, caps[-1].path / part, share))
        if expected is not None and caps[-1].identity != expected:
            raise PrivateArtifactError(UNSAFE_PATH)
        _verify_chain(caps)
        return caps
    except FileNotFoundError:
        _close_caps(caps); raise PrivateArtifactError(NOT_FOUND) from None
    except Exception:
        _close_caps(caps)
        raise
def _open_dir_path(path: Path, share: int = _READ_DIR_SHARE) -> _DirCap:
    try:
        handle = _win.create_file(str(path), _win.GENERIC_READ | _win.SYNCHRONIZE, share, _win.OPEN_EXISTING, _win.FILE_FLAG_BACKUP_SEMANTICS | _win.FILE_FLAG_OPEN_REPARSE_POINT)
    except FileNotFoundError: raise
    except OSError as exc:
        _raise_dir_error(exc)
    return _cap_dir(path, handle)
def _open_child_dir(parent: _DirCap, name: str, path: Path, share: int) -> _DirCap:
    _check_name(name)
    _verify_dir(parent)
    try:
        handle = _win.nt_create_relative(parent.handle, name, _win.GENERIC_READ | _win.SYNCHRONIZE, share, _win.FILE_OPEN, _DIR_OPTS)
    except FileNotFoundError: raise
    except OSError as exc:
        _raise_dir_error(exc)
    return _cap_dir(path, handle)
def _cap_dir(path: Path, handle: int) -> _DirCap:
    try:
        cap = _DirCap(path, handle, _handle_identity(handle))
        _verify_dir(cap)
        return cap
    except OSError as exc:
        _close_handle(handle)
        raise PrivateArtifactError(IO_ERROR) from exc
    except Exception:
        _close_handle(handle)
        raise
def _mkdir(parent: _DirCap, name: str, share: int) -> None:
    _check_name(name)
    _verify_dir(parent)
    try:
        handle = _win.nt_create_relative(parent.handle, name, _win.GENERIC_READ | _win.DELETE | _win.SYNCHRONIZE, share, _win.FILE_CREATE, _DIR_OPTS)
    except FileExistsError:
        return
    except OSError as exc:
        _raise_dir_error(exc)
    _close_handle(handle)
def _read_at(chain: list[_DirCap], name: str, max_bytes: int) -> bytes:
    parent = chain[-1]
    _check_name(name)
    _verify_chain(chain)
    try:
        handle = _win.nt_create_relative(parent.handle, name, _win.GENERIC_READ | _win.SYNCHRONIZE, _READ_SHARE, _win.FILE_OPEN, _FILE_OPTS)
    except FileNotFoundError as exc:
        raise PrivateArtifactError(NOT_FOUND) from exc
    except OSError as exc:
        _raise_open_error(parent.path / name, exc)
    try:
        before = _win.handle_info(handle)
        if _is_reparse(before):
            raise PrivateArtifactError(UNSAFE_PATH)
        if _is_dir(before):
            raise PrivateArtifactError(NOT_REGULAR)
        size = _size(before)
        if size > max_bytes:
            raise PrivateArtifactError(TOO_LARGE)
        data = _win.read_file(handle, max_bytes + 1)
        if len(data) > max_bytes:
            raise PrivateArtifactError(TOO_LARGE)
        after = _win.handle_info(handle)
        if (
            _handle_identity_from_info(before) != _handle_identity_from_info(after)
            or _size(before) != _size(after)
            or _write_time(before) != _write_time(after)
            or _size(before) != len(data)
        ):
            raise PrivateArtifactError(IO_ERROR)
        _verify_chain(chain)
        return data
    finally:
        _close_handle(handle)
def _write_new_or_same(chain: list[_DirCap], name: str, data: bytes) -> str:
    status = _existing_status(chain, name, data, required=False)
    if status is not None:
        return status
    parent = chain[-1]
    temp = ""
    temp_id: ArtifactIdentity | None = None
    handle: int | None = None
    try:
        temp, temp_id, handle = _write_temp(chain, name, data)
        try:
            _replace_temp(parent, handle, name)
        except FileExistsError:
            _close_handle(handle)
            handle = None
            _cleanup_file(parent, temp, temp_id)
            return _existing_status(chain, name, data, required=True) or _conflict()
        _close_handle(handle)
        handle = None
        if _read_at(chain, name, len(data)) != data:
            raise PrivateArtifactError(IO_ERROR)
        return "created"
    except PrivateArtifactError:
        _close_handle(handle)
        _cleanup_file(parent, temp, temp_id)
        raise
    except OSError as exc:
        _close_handle(handle)
        _cleanup_file(parent, temp, temp_id)
        raise PrivateArtifactError(IO_ERROR) from exc
def _existing_status(chain: list[_DirCap], name: str, data: bytes, *, required: bool) -> str | None:
    try:
        current = _read_at(chain, name, len(data))
    except PrivateArtifactError as exc:
        if exc.code == NOT_FOUND and not required:
            return None
        if exc.code in (TOO_LARGE, NOT_REGULAR, UNSAFE_PATH):
            raise PrivateArtifactError(CONFLICT) from exc
        raise
    if current == data:
        return "idempotent"
    raise PrivateArtifactError(CONFLICT)
def _write_temp(chain: list[_DirCap], final_name: str, data: bytes) -> tuple[str, ArtifactIdentity, int]:
    parent = chain[-1]
    access = _win.GENERIC_READ | _win.GENERIC_WRITE | _win.DELETE | _win.SYNCHRONIZE
    share = _win.FILE_SHARE_READ | _win.FILE_SHARE_DELETE
    for _attempt in range(_TEMP_ATTEMPTS):
        temp = f".{final_name}.{os.urandom(8).hex()}.tmp"
        handle: int | None = None
        try:
            _verify_chain(chain)
            handle = _win.nt_create_relative(parent.handle, temp, access, share, _win.FILE_CREATE, _FILE_OPTS)
            ident = _handle_identity(handle)
            _win.write_file(handle, data)
            _win.flush(handle)
            current, is_dir, reparse = _path_identity(parent.path / temp)
            if current != ident or is_dir or reparse:
                raise PrivateArtifactError(UNSAFE_PATH)
            return temp, ident, handle
        except FileExistsError:
            _close_handle(handle)
            continue
        except Exception:
            if handle is not None:
                try:
                    _win.delete_on_close(handle)
                except OSError:
                    pass
            _close_handle(handle)
            raise
    raise PrivateArtifactError(IO_ERROR)
def _replace_temp(parent: _DirCap, handle: int, name: str) -> None:
    _check_name(name)
    _verify_dir(parent)
    _win.rename(handle, parent.handle, name)
def _cleanup_file(parent: _DirCap, name: str, expected: ArtifactIdentity | None) -> None:
    if not name or expected is None:
        return
    handle: int | None = None
    try:
        handle = _win.nt_create_relative(parent.handle, name, _win.GENERIC_READ | _win.DELETE | _win.SYNCHRONIZE, _WRITE_DIR_SHARE, _win.FILE_OPEN, _FILE_OPTS)
        info = _win.handle_info(handle)
        if _handle_identity_from_info(info) == expected and not _is_dir(info) and not _is_reparse(info):
            _win.delete_on_close(handle)
    except OSError:
        return
    finally:
        _close_handle(handle)
def _verify_chain(caps: list[_DirCap]) -> None:
    if not caps:
        raise PrivateArtifactError(UNSAFE_PATH)
    for cap in caps:
        _verify_dir(cap)
def _verify_dir(cap: _DirCap) -> None:
    try:
        current, is_dir, reparse = _path_identity(cap.path)
        opened = _win.handle_info(cap.handle)
    except OSError as exc:
        _raise_dir_error(exc)
    if current != cap.identity or not is_dir or reparse:
        raise PrivateArtifactError(UNSAFE_PATH)
    if _handle_identity_from_info(opened) != cap.identity:
        raise PrivateArtifactError(UNSAFE_PATH)
    if not _is_dir(opened) or _is_reparse(opened):
        raise PrivateArtifactError(UNSAFE_PATH)
def _close_caps(caps: list[_DirCap]) -> None:
    for cap in reversed(caps):
        _close_handle(cap.handle)
def _conflict() -> str:
    raise PrivateArtifactError(CONFLICT)
