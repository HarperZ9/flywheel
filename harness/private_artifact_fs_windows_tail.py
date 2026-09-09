"""Helper tail for private_artifact_fs_windows kept separate for file gate."""
from __future__ import annotations

import os
from pathlib import Path, PureWindowsPath

from .private_artifact_fs import (
    BUSY,
    CONFLICT,
    NOT_REGULAR,
    UNSAFE_PATH,
    ArtifactIdentity,
    PrivateArtifactError,
)
from . import private_artifact_fs_windows_api as _win


def relative_parts(rel: str | os.PathLike[str]) -> tuple[str, ...]:
    try:
        text = os.fspath(rel)
    except TypeError as exc:
        raise PrivateArtifactError(UNSAFE_PATH) from exc
    if type(text) is not str or not text:
        raise PrivateArtifactError(UNSAFE_PATH)
    path = PureWindowsPath(text)
    if path.is_absolute() or path.drive or path.root:
        raise PrivateArtifactError(UNSAFE_PATH)
    parts = path.parts
    if not parts:
        raise PrivateArtifactError(UNSAFE_PATH)
    for part in parts:
        check_name(part)
    return tuple(parts)


def check_name(name: str) -> None:
    if type(name) is str:
        try:
            encoded = name.encode("utf-16-le")
        except UnicodeEncodeError as exc:
            raise PrivateArtifactError(UNSAFE_PATH) from exc
        if len(encoded) > 0xFFFE:
            raise PrivateArtifactError(UNSAFE_PATH)
    if (
        type(name) is not str
        or name in ("", ".", "..")
        or "/" in name
        or "\\" in name
        or "\0" in name
        or ":" in name
    ):
        raise PrivateArtifactError(UNSAFE_PATH)


def absolute_existing(root: Path) -> Path:
    root = Path(root)
    if not root.is_absolute():
        root = Path.cwd() / root
    if any(part in (".", "..") for part in root.parts[1:]):
        raise PrivateArtifactError(UNSAFE_PATH)
    return root


def handle_identity(handle: int) -> ArtifactIdentity:
    return handle_identity_from_info(_win.handle_info(handle))


def handle_identity_from_info(info) -> ArtifactIdentity:
    return ArtifactIdentity(
        "windows",
        int(info.dwVolumeSerialNumber),
        (int(info.nFileIndexHigh) << 32) | int(info.nFileIndexLow),
    )


def size(info) -> int:
    return (int(info.nFileSizeHigh) << 32) | int(info.nFileSizeLow)


def write_time(info) -> tuple[int, int]:
    return int(info.ftLastWriteTime.dwHighDateTime), int(info.ftLastWriteTime.dwLowDateTime)


def is_reparse(info) -> bool:
    return bool(int(info.dwFileAttributes) & _win.FILE_ATTRIBUTE_REPARSE_POINT)


def is_dir(info) -> bool:
    return bool(int(info.dwFileAttributes) & _win.FILE_ATTRIBUTE_DIRECTORY)


def is_sharing(exc: OSError) -> bool:
    return getattr(exc, "winerror", None) == 32 or getattr(exc, "errno", None) == 32 or (
        bool(exc.args) and exc.args[0] == 32
    )
def raise_open_error(path: Path, exc: OSError) -> None:
    try:
        _identity, is_directory, reparse = path_identity(path)
    except OSError:
        pass
    else:
        if reparse:
            raise PrivateArtifactError(UNSAFE_PATH) from exc
        if is_directory:
            raise PrivateArtifactError(NOT_REGULAR) from exc
    raise PrivateArtifactError(CONFLICT if is_sharing(exc) else UNSAFE_PATH) from exc


def raise_dir_error(exc: OSError) -> None:
    raise PrivateArtifactError(BUSY if is_sharing(exc) else UNSAFE_PATH) from exc


def path_identity(path: Path) -> tuple[ArtifactIdentity, bool, bool]:
    handle = _win.create_file(str(path), _win.GENERIC_READ | _win.SYNCHRONIZE,
                              _win.FILE_SHARE_READ | _win.FILE_SHARE_WRITE |
                              _win.FILE_SHARE_DELETE, _win.OPEN_EXISTING,
                              _win.FILE_FLAG_BACKUP_SEMANTICS |
                              _win.FILE_FLAG_OPEN_REPARSE_POINT)
    try:
        info = _win.handle_info(handle)
        return handle_identity_from_info(info), is_dir(info), is_reparse(info)
    finally:
        _win.close_handle(handle)


def close_handle(handle: int | None) -> None:
    try:
        _win.close_handle(handle)
    except OSError:
        pass


__all__ = [
    "absolute_existing",
    "check_name",
    "close_handle",
    "handle_identity",
    "handle_identity_from_info",
    "is_dir",
    "is_reparse",
    "is_sharing",
    "path_identity",
    "raise_open_error",
    "raise_dir_error",
    "relative_parts",
    "size",
    "write_time",
]
