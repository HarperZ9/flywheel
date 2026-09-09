"""Source-context identity bridge for retained private artifact roots."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Iterable

from .source_context_error import SourceContextError


def path_sha(path: Path) -> str:
    text = os.path.normcase(os.path.abspath(str(Path(path))))
    return hashlib.sha256(text.encode("utf-8", "strict")).hexdigest()


def current_identity(path: Path) -> dict:
    try:
        from .private_artifact_fs import root_identity
        return identity_dict(Path(path), root_identity(path))
    except SourceContextError:
        raise
    except Exception as exc:
        raise source_error(exc, read=True) from None


def identity_dict(path: Path, identity, *, guarded_components: int | None = None
                  ) -> dict:
    value = {"platform": identity.platform, "device": int(identity.device),
             "inode": int(identity.inode), "path_sha256": path_sha(Path(path))}
    if identity.platform == "windows":
        value["volume_serial"] = int(identity.device)
        value["file_index"] = int(identity.inode)
    if guarded_components is not None:
        value["guarded_components"] = guarded_components
    return value


def artifact_identity(value: dict):
    try:
        from .private_artifact_fs import ArtifactIdentity
    except Exception as exc:
        raise source_error(exc, read=True) from None
    try:
        platform = value["platform"]
        if platform == "windows" and "device" not in value:
            device, inode = value["volume_serial"], value["file_index"]
        else:
            device, inode = value["device"], value["inode"]
        if (type(platform) is not str or platform not in ("posix", "windows")
                or type(device) is not int or type(inode) is not int
                or isinstance(device, bool) or isinstance(inode, bool)):
            raise TypeError
        return ArtifactIdentity(platform, device, inode)
    except (KeyError, TypeError):
        raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE") from None


def usable_artifact_identity(value: object) -> bool:
    if type(value) is not dict:
        return False
    if type(value.get("path_sha256")) is not str:
        return False
    expected = "windows" if os.name == "nt" else "posix"
    if value.get("platform") != expected:
        return False
    if expected == "windows":
        return all(type(value.get(key)) is int and not isinstance(value.get(key), bool)
                   for key in ("volume_serial", "file_index"))
    return all(type(value.get(key)) is int and not isinstance(value.get(key), bool)
               for key in ("device", "inode"))


def cap_identity_rows(cap) -> tuple[dict, ...]:
    caps = getattr(cap, "_caps", None)
    if not isinstance(caps, list) or not caps:
        return (identity_dict(Path(getattr(cap, "_root_path", ".")), cap.identity),)
    return tuple(identity_dict(row.path, row.identity) for row in caps)


def source_error(exc: Exception, *, read: bool = False,
                 collision: bool = False) -> SourceContextError:
    code = getattr(exc, "code", None)
    if code == "BUSY":
        return SourceContextError("SOURCE_CONTEXT_AUTHORITY_BUSY")
    if code == "CONFLICT" or collision:
        return SourceContextError("SOURCE_CONTEXT_REF_COLLISION")
    if code in {"TOO_LARGE", "NOT_REGULAR"}:
        return SourceContextError("SOURCE_CONTEXT_STORE_CORRUPT")
    if code == "IO_ERROR":
        return SourceContextError(
            "SOURCE_CONTEXT_STORE_CORRUPT" if read
            else "SOURCE_CONTEXT_DURABILITY_UNAVAILABLE")
    if code in {"UNSUPPORTED_OS", "UNSUPPORTED_FS", "UNSAFE_PATH", "NOT_FOUND", "CLOSED"}:
        return SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")
    if isinstance(exc, SourceContextError):
        return exc
    return SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")


def state_row(rows: Iterable[dict], state_root: Path) -> dict:
    wanted = path_sha(Path(state_root))
    for row in rows:
        if row.get("path_sha256") == wanted:
            return dict(row)
    raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")


def assert_supported_private_root(path: Path) -> None:
    try:
        from .private_artifact_fs import root_identity
        root_identity(Path(path))
    except SourceContextError:
        raise
    except Exception as exc:
        raise source_error(exc, read=True) from None
