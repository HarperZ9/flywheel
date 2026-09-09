"""Bounded private source-context store I/O."""
from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
import os

from .evidence_json import canonical_bytes, strict_load_json
from .operation_grants import _secure_owner_only
from .source_context_error import SourceContextError
from .source_context_identity import (
    artifact_identity, assert_supported_private_root, source_error,
    usable_artifact_identity,
)

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


def _json_file(path: Path, *, max_bytes: int = MAX_PRIVATE_BYTES,
               state_root: Path | None = None,
               expected_root_identity: dict | None = None) -> dict:
    try:
        if state_root is not None:
            assert_supported_private_root(Path(state_root))
        if _use_artifact_io(expected_root_identity):
            if state_root is None:
                raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")
            data = _artifact_read(
                Path(state_root), Path(path), expected_root_identity, max_bytes)
            return strict_load_json(data, max_bytes=max_bytes, max_depth=24)
        with _guard_store_anchor(state_root, path):
            return strict_load_json(_read_bounded(Path(path), max_bytes),
                                    max_bytes=max_bytes, max_depth=24)
    except SourceContextError:
        raise
    except Exception:
        raise SourceContextError("SOURCE_CONTEXT_STORE_CORRUPT") from None


def _write_once(path: Path, value: dict, *,
                state_root: Path | None = None,
                expected_root_identity: dict | None = None) -> None:
    data = canonical_bytes(value)
    if len(data) > MAX_PRIVATE_BYTES:
        raise SourceContextError("SOURCE_CONTEXT_STORE_COMMIT_FAILED")
    path = Path(path)
    if state_root is not None:
        assert_supported_private_root(Path(state_root))
    if _use_artifact_io(expected_root_identity):
        if state_root is None:
            raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")
        _artifact_write(Path(state_root), path, expected_root_identity, data)
        return
    if state_root is None:
        path.parent.mkdir(parents=True, exist_ok=True)
        _secure_owner_only(path.parent, directory=True)
        _write_once_under_guard(path, data)
        return
    _prepare_store_parent(Path(state_root), path.parent)
    with _guard_store_anchor(Path(state_root), path):
        _write_once_under_guard(path, data)


def _guard_store_anchor(state_root: Path | None, path: Path):
    if state_root is None:
        return nullcontext()
    anchor = _store_anchor(Path(state_root), Path(path))
    if os.name != "nt":
        return nullcontext()
    if not anchor.exists():
        raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")
    return _guard_dir(anchor)


def _prepare_store_parent(state_root: Path, parent: Path) -> None:
    _store_anchor(state_root, parent)
    _ensure_private_tree(state_root, parent)


def _ensure_private_tree(state_root: Path, target: Path) -> None:
    if not _same_or_under(target, state_root):
        raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")
    current, target_abs = Path(os.path.abspath(str(state_root))), Path(os.path.abspath(str(target)))
    if not current.is_dir():
        raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")
    _verify_dir(current)
    for part in Path(os.path.relpath(str(target_abs), str(current))).parts:
        current = current / part
        if not current.exists():
            _verify_dir(current.parent)
            try:
                current.mkdir()
            except FileExistsError:
                pass
        _verify_dir(current)
        _secure_owner_only(current, directory=True)
        _verify_dir(current)


def _verify_dir(path: Path) -> None:
    if os.name == "nt":
        with _guard_dir(path):
            return
    if not Path(path).is_dir():
        raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")


def _store_anchor(state_root: Path, path: Path) -> Path:
    source = Path(state_root) / "source-context"
    for anchor in (source / "v1", source / "admissions"):
        if _same_or_under(path, anchor):
            return anchor
    raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")


def _same_or_under(path: Path, root: Path) -> bool:
    try:
        path_text = os.path.normcase(os.path.abspath(str(Path(path))))
        root_text = os.path.normcase(os.path.abspath(str(Path(root))))
        return os.path.commonpath((path_text, root_text)) == root_text
    except (OSError, ValueError):
        return False


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


def _use_artifact_io(expected_root_identity: dict | None) -> bool:
    return usable_artifact_identity(expected_root_identity)


def _relative_to_state(state_root: Path, path: Path) -> Path:
    if not _same_or_under(path, state_root):
        raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")
    try:
        return Path(os.path.relpath(
            os.path.abspath(str(path)), os.path.abspath(str(state_root))))
    except ValueError:
        raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE") from None


def _artifact_read(state_root: Path, path: Path, expected: dict,
                   max_bytes: int) -> bytes:
    try:
        from .private_artifact_fs import PrivateArtifactError, open_artifact_root
    except Exception as exc:
        raise source_error(exc, read=True) from None
    try:
        with open_artifact_root(
                state_root, expected=artifact_identity(expected),
                writable=False) as root:
            return root.read_bytes(_relative_to_state(state_root, path),
                                   max_bytes=max_bytes)
    except SourceContextError:
        raise
    except PrivateArtifactError as exc:
        raise source_error(exc, read=True) from None


def _artifact_write(state_root: Path, path: Path, expected: dict,
                    data: bytes) -> None:
    try:
        from .private_artifact_fs import PrivateArtifactError, open_artifact_root
    except Exception as exc:
        raise source_error(exc, read=False) from None
    try:
        with open_artifact_root(
                state_root, expected=artifact_identity(expected),
                writable=True) as root:
            root.write_new_or_same(_relative_to_state(state_root, path), data)
    except SourceContextError:
        raise
    except PrivateArtifactError as exc:
        raise source_error(exc, read=False) from None

