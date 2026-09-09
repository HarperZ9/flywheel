"""Private artifact filesystem custody primitive."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Mapping

UNSUPPORTED_OS = "UNSUPPORTED_OS"
UNSUPPORTED_FS = "UNSUPPORTED_FS"
UNSAFE_PATH = "UNSAFE_PATH"
NOT_FOUND = "NOT_FOUND"
NOT_REGULAR = "NOT_REGULAR"
TOO_LARGE = "TOO_LARGE"
CONFLICT = "CONFLICT"
IO_ERROR = "IO_ERROR"
BUSY = "BUSY"
CLOSED = "CLOSED"


class PrivateArtifactError(RuntimeError):
    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        super().__init__(message or code)


@dataclass(frozen=True, slots=True)
class ArtifactIdentity:
    platform: str
    device: int
    inode: int

    def to_json_dict(self) -> dict[str, int | str]:
        return {"platform": self.platform, "device": self.device, "inode": self.inode}

    @classmethod
    def from_json_dict(cls, value: Mapping[str, object]) -> ArtifactIdentity:
        try:
            platform = value["platform"]
            device = value["device"]
            inode = value["inode"]
        except (KeyError, TypeError) as exc:
            raise PrivateArtifactError(UNSAFE_PATH) from exc
        if type(platform) is not str or platform not in ("posix", "windows"):
            raise PrivateArtifactError(UNSAFE_PATH)
        if type(device) is not int or type(inode) is not int:
            raise PrivateArtifactError(UNSAFE_PATH)
        return cls(platform, device, inode)


@dataclass(frozen=True, slots=True)
class BorrowedDescriptor:
    platform: str
    identity: ArtifactIdentity
    fd: int | None = None
    handle: int | None = None


def supported() -> bool:
    backend = _backend()
    return bool(backend and backend.supported())


def root_identity(root: str | os.PathLike[str]) -> ArtifactIdentity:
    backend = _require_backend()
    return backend.identity_for_root(Path(root))


def open_artifact_root(
    root: str | os.PathLike[str],
    *,
    expected: ArtifactIdentity | None = None,
    writable: bool = True,
) -> Any:
    backend = _require_backend()
    return backend.ArtifactRoot(Path(root), expected, writable)


def _backend() -> Any | None:
    if os.name == "nt":
        from . import private_artifact_fs_windows as backend
    else:
        from . import private_artifact_fs_posix as backend
    return backend if backend.supported() else None


def _require_backend() -> Any:
    backend = _backend()
    if backend is None:
        raise PrivateArtifactError(UNSUPPORTED_OS)
    return backend


__all__ = [
    "ArtifactIdentity",
    "BorrowedDescriptor",
    "BUSY",
    "CLOSED",
    "CONFLICT",
    "IO_ERROR",
    "NOT_FOUND",
    "NOT_REGULAR",
    "PrivateArtifactError",
    "TOO_LARGE",
    "UNSUPPORTED_FS",
    "UNSAFE_PATH",
    "UNSUPPORTED_OS",
    "open_artifact_root",
    "root_identity",
    "supported",
]
