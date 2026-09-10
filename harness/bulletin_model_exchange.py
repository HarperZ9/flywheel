"""Created-only private records using the existing pinned filesystem custody."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .private_artifact_fs import ArtifactIdentity, open_artifact_root

_NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,120}(?:\.[a-z0-9]{1,10})?\Z")
_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(10)),
             *(f"lpt{i}" for i in range(10))}


class ExchangeError(RuntimeError):
    """A private record could not be admitted; errors contain no record data."""


def _name(value: str) -> None:
    if (type(value) is not str or not _NAME.fullmatch(value)
            or value.split(".")[0] in _RESERVED):
        raise ExchangeError("invalid_record_name")


class PrivateExchange:
    """Fresh run only; no replay, recursive discovery, cleanup or overwrite.

    Custody and file-data flush come from private_artifact_fs. An unclean run
    cannot be resumed. This does not authenticate a hostile same-user process.
    """

    def __init__(self, custody, path: Path):
        self._custody = custody
        self._path = path

    @property
    def path(self):
        return self._path

    @classmethod
    def create(cls, path: Path) -> "PrivateExchange":
        if not path.is_absolute() or str(path).startswith("\\\\"):
            raise ExchangeError("absolute_local_root_required")
        try:
            # Admit and pin the existing parent before creating any child path.
            with open_artifact_root(path.parent):
                path.mkdir(exist_ok=False)
                custody = open_artifact_root(path)
                custody.__enter__()
                return cls(custody, path)
        except Exception as exc:
            raise ExchangeError("fresh_root_required") from exc

    def __enter__(self):
        return self

    @classmethod
    def attach(cls, path: Path, *, expected: ArtifactIdentity) -> "PrivateExchange":
        """An owned child joins the current parent's fresh root, never resumes it."""
        if type(expected) is not ArtifactIdentity:
            raise ExchangeError("parent_identity_required")
        try:
            custody = open_artifact_root(path, expected=expected)
            custody.__enter__()
            return cls(custody, path)
        except Exception as exc:
            raise ExchangeError("parent_identity_mismatch") from exc

    @property
    def identity(self):
        return self._custody.identity

    def __exit__(self, *args):
        self.close()

    def close(self) -> None:
        self._custody.close()

    def put(self, name: str, data: bytes, *, max_bytes: int) -> str:
        _name(name)
        if type(data) is not bytes or type(max_bytes) is not int or not 0 <= len(data) <= max_bytes:
            raise ExchangeError("invalid_record_bytes")
        try:
            outcome = self._custody.write_new_or_same(name, data)
            if outcome != "created":
                raise ExchangeError("record_exists")
        except Exception as exc:
            raise ExchangeError("record_write_failed") from exc
        return hashlib.sha256(data).hexdigest()

    def read(self, name: str, *, max_bytes: int, expected_sha256: str | None = None) -> bytes:
        _name(name)
        if type(max_bytes) is not int or max_bytes < 0:
            raise ExchangeError("invalid_record_limit")
        try:
            data = self._custody.read_bytes(name, max_bytes=max_bytes)
        except Exception as exc:
            raise ExchangeError("record_read_failed") from exc
        if expected_sha256 is not None and hashlib.sha256(data).hexdigest() != expected_sha256:
            raise ExchangeError("record_digest_mismatch")
        return data
