"""POSIX implementation for private artifact filesystem custody."""
from __future__ import annotations
from dataclasses import dataclass
import os
from .private_artifact_fs_listing import ArtifactListing
from pathlib import Path
import stat
from .private_artifact_fs import (
    BUSY,
    CLOSED,
    CONFLICT,
    IO_ERROR,
    NOT_FOUND,
    NOT_REGULAR,
    TOO_LARGE,
    UNSAFE_PATH,
    ArtifactIdentity,
    PrivateArtifactError,
)
from .private_artifact_fs_posix_tail import (
    absolute_existing as _absolute_existing,
    borrowed_descriptor as _borrowed_descriptor,
    check_name as _check_name,
    close_fd as _close_fd,
    fsync_dir as _fsync_dir,
    identity as _identity,
    link_fd_to_name as _link_fd_to_name,
    open_anonymous_tmp as _open_anonymous_tmp,
    read_flags as _read_flags,
    relative_parts as _relative_parts,
    write_all as _write_all,
)
from .private_artifact_fs_mount import admit_fd_mount as _admit_fd_mount
from .private_artifact_fs_mount import supported as _mount_admission_supported
@dataclass(frozen=True, slots=True)
class _DirCap:
    path: Path
    fd: int
    identity: ArtifactIdentity
def supported() -> bool:
    return (
        os.name != "nt"
        and os.open in os.supports_dir_fd
        and os.mkdir in os.supports_dir_fd
        and os.unlink in os.supports_dir_fd
        and os.link in os.supports_dir_fd
        and all(hasattr(os, name) for name in ("O_DIRECTORY", "O_NOFOLLOW"))
        and _mount_admission_supported()
    )
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
        self._writable = bool(writable)
    def __enter__(self) -> ArtifactRoot:
        if self._closed:
            raise PrivateArtifactError(CLOSED)
        self._caps = _open_root_chain(self._root_path, self._expected)
        return self
    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
    def close(self) -> None:
        caps, self._caps = self._caps, []
        _close_caps(caps)
        self._closed = True
    @property
    def identity(self) -> ArtifactIdentity:
        return self._active_caps()[-1].identity
    def borrow_descriptor(self):
        cap = self._active_caps()[-1]
        return _borrowed_descriptor(cap.fd, cap.identity)
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
        if not self._writable:
            raise PrivateArtifactError(BUSY)
        if type(data) is not bytes:
            raise PrivateArtifactError(UNSAFE_PATH)
        parts = _relative_parts(rel)
        chain = self._parent_chain(parts[:-1], create=True)
        try:
            return _write_new_or_same(chain, parts[-1], data)
        finally:
            _close_caps(chain[len(self._caps):])
    publish_bytes = write_new_or_same
    def _active_caps(self) -> list[_DirCap]:
        if self._closed or not self._caps:
            raise PrivateArtifactError(CLOSED)
        return self._caps
    def _parent_chain(self, parts: tuple[str, ...], *, create: bool) -> list[_DirCap]:
        base = self._active_caps()
        _verify_chain(base)
        chain = list(base)
        parent = chain[-1]
        try:
            for part in parts:
                child_path = parent.path / part
                try:
                    child = _open_dir(parent, part, child_path)
                except FileNotFoundError:
                    if not create:
                        raise PrivateArtifactError(NOT_FOUND) from None
                    _mkdir(parent, part)
                    child = _open_dir(parent, part, child_path)
                chain.append(child)
                parent = child
                _verify_chain(chain)
            return chain
        except Exception:
            _close_caps(chain[len(base):])
            raise
def _open_root_chain(root: Path, expected: ArtifactIdentity | None) -> list[_DirCap]:
    if not supported():
        raise PrivateArtifactError(UNSAFE_PATH)
    root = _absolute_existing(root)
    parts = root.parts
    if not parts or parts[0] != "/":
        raise PrivateArtifactError(UNSAFE_PATH)
    caps: list[_DirCap] = []
    try:
        caps.append(_open_dir_path(Path("/")))
        for part in parts[1:]:
            _check_name(part)
            caps.append(_open_dir(caps[-1], part, caps[-1].path / part))
        if expected is not None and caps[-1].identity != expected:
            raise PrivateArtifactError(UNSAFE_PATH)
        _verify_chain(caps)
        return caps
    except FileNotFoundError:
        _close_caps(caps)
        raise PrivateArtifactError(NOT_FOUND) from None
    except Exception:
        _close_caps(caps)
        raise
def _open_dir(parent: _DirCap, name: str, path: Path) -> _DirCap:
    _check_name(name)
    _verify_dir(parent)
    return _open_dir_path(path, name, parent.fd)
def _open_dir_path(path: Path, name: str | None = None, dir_fd: int | None = None) -> _DirCap:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(name if name is not None else path, flags, dir_fd=dir_fd)
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise PrivateArtifactError(UNSAFE_PATH) from exc
    try:
        cap = _DirCap(path, fd, _identity(os.fstat(fd)))
        _verify_dir(cap)
        return cap
    except OSError as exc:
        _close_fd(fd)
        raise PrivateArtifactError(IO_ERROR) from exc
    except Exception:
        _close_fd(fd)
        raise
def _mkdir(parent: _DirCap, name: str) -> None:
    _check_name(name)
    _verify_dir(parent)
    try:
        os.mkdir(name, 0o700, dir_fd=parent.fd)
        _fsync_dir(parent.fd)
    except FileExistsError:
        return
    except OSError as exc:
        raise PrivateArtifactError(UNSAFE_PATH) from exc
def _read_at(chain: list[_DirCap], name: str, max_bytes: int) -> bytes:
    parent = chain[-1]
    _check_name(name)
    _verify_chain(chain)
    try:
        fd = os.open(name, _read_flags(), dir_fd=parent.fd)
    except FileNotFoundError as exc:
        raise PrivateArtifactError(NOT_FOUND) from exc
    except OSError as exc:
        raise PrivateArtifactError(UNSAFE_PATH) from exc
    try:
        before = os.fstat(fd)
        _admit_fd_mount(fd)
        if not stat.S_ISREG(before.st_mode):
            raise PrivateArtifactError(NOT_REGULAR)
        if before.st_size > max_bytes:
            raise PrivateArtifactError(TOO_LARGE)
        data = _read_fd_bounded(fd, max_bytes)
        after = os.fstat(fd)
        if (
            _identity(before) != _identity(after)
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or before.st_ctime_ns != after.st_ctime_ns
            or before.st_size != len(data)
        ):
            raise PrivateArtifactError(IO_ERROR)
        _verify_chain(chain)
        return data
    finally:
        _close_fd(fd)
def _write_new_or_same(chain: list[_DirCap], name: str, data: bytes) -> str:
    status = _existing_status(chain, name, data, required=False)
    if status is not None:
        return status
    parent = chain[-1]
    fd: int | None = None
    try:
        fd, _temp_id = _write_temp(chain, name, data)
        try:
            _replace_temp(parent, fd, name)
        except FileExistsError:
            _close_fd(fd)
            fd = None
            return _existing_status(chain, name, data, required=True) or _conflict()
        _fsync_dir(parent.fd)
        _close_fd(fd)
        fd = None
        if _read_at(chain, name, len(data)) != data:
            raise PrivateArtifactError(IO_ERROR)
        return "created"
    except PrivateArtifactError:
        raise
    except OSError as exc:
        raise PrivateArtifactError(IO_ERROR) from exc
    finally:
        _close_fd(fd)
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
def _write_temp(chain: list[_DirCap], final_name: str, data: bytes) -> tuple[int, ArtifactIdentity]:
    parent = chain[-1]
    _check_name(final_name)
    _verify_chain(chain)
    fd: int | None = None
    try:
        fd = _open_anonymous_tmp(parent.fd)
        _admit_fd_mount(fd)
        ident = _identity(os.fstat(fd))
        _write_all(fd, data)
        os.fsync(fd)
        return fd, ident
    except Exception:
        _close_fd(fd)
        raise
def _replace_temp(parent: _DirCap, fd: int, name: str) -> None:
    _check_name(name)
    _verify_dir(parent)
    _link_fd_to_name(fd, parent.fd, name)
def _read_fd_bounded(fd: int, max_bytes: int) -> bytes:
    data = os.read(fd, max_bytes + 1)
    if len(data) > max_bytes:
        raise PrivateArtifactError(TOO_LARGE)
    return data
def _verify_chain(caps: list[_DirCap]) -> None:
    if not caps:
        raise PrivateArtifactError(UNSAFE_PATH)
    for cap in caps:
        _verify_dir(cap)
def _verify_dir(cap: _DirCap) -> None:
    try:
        current = cap.path.lstat()
        opened = os.fstat(cap.fd)
    except OSError as exc:
        raise PrivateArtifactError(UNSAFE_PATH) from exc
    if not stat.S_ISDIR(current.st_mode) or _identity(current) != cap.identity:
        raise PrivateArtifactError(UNSAFE_PATH)
    if not stat.S_ISDIR(opened.st_mode) or _identity(opened) != cap.identity:
        raise PrivateArtifactError(UNSAFE_PATH)
    _admit_fd_mount(cap.fd)
def _conflict() -> str:
    raise PrivateArtifactError(CONFLICT)
def _close_caps(caps: list[_DirCap]) -> None:
    for cap in reversed(caps):
        _close_fd(cap.fd)
__all__ = ["ArtifactRoot", "identity_for_root", "supported"]
