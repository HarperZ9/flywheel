"""Bounded private source-context store I/O."""
from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
import os

from .evidence_json import canonical_bytes, strict_load_json
from .operation_grants import _secure_owner_only
from .source_context_error import SourceContextError

MAX_PRIVATE_BYTES = 1_000_000


def _guard_dir(path: Path):
    if os.name != "nt" or not Path(path).exists():
        return nullcontext()
    from .source_context_windows import SourceContextWindowsGuard
    return SourceContextWindowsGuard(path)


def _read_bounded(path: Path, max_bytes: int) -> bytes:
    try:
        if os.name == "nt":
            from .source_context_windows import read_guarded_file
            return read_guarded_file(path, max_bytes=max_bytes)
        with Path(path).open("rb") as stream:
            data = stream.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise SourceContextError("SOURCE_CONTEXT_STORE_CORRUPT")
        return data
    except SourceContextError:
        raise
    except OSError:
        raise SourceContextError("SOURCE_CONTEXT_STORE_CORRUPT") from None


def _json_file(path: Path, *, max_bytes: int = MAX_PRIVATE_BYTES) -> dict:
    try:
        return strict_load_json(_read_bounded(path, max_bytes),
                                max_bytes=max_bytes, max_depth=24)
    except SourceContextError:
        raise
    except Exception:
        raise SourceContextError("SOURCE_CONTEXT_STORE_CORRUPT") from None


def _write_once(path: Path, value: dict) -> None:
    data = canonical_bytes(value)
    if len(data) > MAX_PRIVATE_BYTES:
        raise SourceContextError("SOURCE_CONTEXT_STORE_COMMIT_FAILED")
    path.parent.mkdir(parents=True, exist_ok=True)
    _secure_owner_only(path.parent, directory=True)
    _write_once_under_guard(path, data)


def _write_once_under_guard(path: Path, data: bytes) -> None:
    if path.exists():
        if _read_bounded(path, MAX_PRIVATE_BYTES) != data:
            raise SourceContextError("SOURCE_CONTEXT_REF_COLLISION")
        _secure_owner_only(path, directory=False)
        return
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        _secure_owner_only(tmp, directory=False)
        try:
            os.link(tmp, path)
        except FileExistsError:
            if _read_bounded(path, MAX_PRIVATE_BYTES) != data:
                raise SourceContextError("SOURCE_CONTEXT_REF_COLLISION")
        finally:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass
        if _read_bounded(path, MAX_PRIVATE_BYTES) != data:
            raise SourceContextError("SOURCE_CONTEXT_STORE_COMMIT_FAILED")
        _secure_owner_only(path, directory=False)
    except SourceContextError:
        raise
    except OSError:
        raise SourceContextError("SOURCE_CONTEXT_DURABILITY_UNAVAILABLE") from None

