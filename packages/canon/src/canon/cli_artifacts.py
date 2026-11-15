from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from .canonical_json import sha256_bytes
from .cli_publish import PublishError, publish_new_bundle
from .path_policy import PathPolicyError, assert_not_protected, is_reparse_point, resolve_under_root
from .source_safe_read import SafeSourceReadError, read_regular_under_root
from .source_state import SourceStateItem

ARTIFACT_NAMES = ("canon.capsule.json", "CANON.md", "readiness-probe.json")
MAX_SOURCE_BYTES = 2 * 1024 * 1024


class ArtifactError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class SourceBytes:
    path: str
    data: bytes

    def item(self) -> SourceStateItem:
        return SourceStateItem(self.path, sha256_bytes(self.data), len(self.data))


@dataclass(frozen=True, slots=True)
class WorkspaceRoot:
    path: Path
    stat_key: tuple[int, int]


def checked_workspace(raw: object) -> WorkspaceRoot:
    if type(raw) is not str or raw == "" or "\0" in raw:
        raise ArtifactError("unsafe_path")
    path = Path(raw)
    try:
        before = path.lstat()
        resolved = path.resolve(strict=True)
        after = path.lstat()
    except OSError as exc:
        raise ArtifactError("unsafe_path") from exc
    if _stat_key(before) != _stat_key(after) or not stat.S_ISDIR(before.st_mode):
        raise ArtifactError("unsafe_path")
    if is_reparse_point(path):
        raise ArtifactError("unsafe_path")
    return WorkspaceRoot(resolved, _stat_key(before))


def read_source_file(raw: object, *, workspace: WorkspaceRoot) -> SourceBytes:
    if type(raw) is not str or raw == "" or "\0" in raw:
        raise ArtifactError("invalid_args")
    _assert_workspace_stable(workspace)
    try:
        resolved = resolve_under_root(raw, root=workspace.path, must_exist=True)
        assert_not_protected(resolved)
    except PathPolicyError as exc:
        if any(v.code == "missing-target" for v in exc.violations):
            raise ArtifactError("source_unreachable") from exc
        raise ArtifactError("unsafe_path") from exc
    _assert_workspace_stable(workspace)
    relative = _relative_text(resolved, workspace.path)
    try:
        data = read_regular_under_root(workspace.path, workspace.stat_key, relative, max_bytes=MAX_SOURCE_BYTES)
    except SafeSourceReadError as exc:
        raise ArtifactError(exc.code) from exc
    return SourceBytes(relative, data)


def publish_artifacts(raw_out: object, *, workspace: WorkspaceRoot, artifacts: dict[str, bytes]) -> str:
    if type(raw_out) is not str or raw_out == "" or "\0" in raw_out:
        raise ArtifactError("unsafe_path")
    _assert_workspace_stable(workspace)
    target = _safe_output_path(raw_out, workspace)
    expected = _artifact_items(artifacts)
    if _exists_or_link(target):
        return _preflight_existing(target, expected)
    try:
        publish_new_bundle(target, expected, workspace_path=workspace.path, workspace_key=workspace.stat_key)
        return "created"
    except PublishError as exc:
        raise ArtifactError(exc.code) from exc
    except FileExistsError as exc:
        raise ArtifactError("conflict") from exc
    except OSError as exc:
        raise ArtifactError("io_error") from exc


def output_relative(raw_out: object, *, workspace: WorkspaceRoot) -> str:
    return _relative_text(_safe_output_path(raw_out, workspace), workspace.path)


def _safe_output_path(raw_out: str, workspace: WorkspaceRoot) -> Path:
    try:
        target = resolve_under_root(raw_out, root=workspace.path)
        assert_not_protected(target)
    except PathPolicyError as exc:
        raise ArtifactError("unsafe_path") from exc
    _assert_workspace_stable(workspace)
    if _exists_or_link(target) and is_reparse_point(target):
        raise ArtifactError("unsafe_path")
    return target


def _assert_workspace_stable(workspace: WorkspaceRoot) -> None:
    try:
        info = workspace.path.lstat()
    except OSError as exc:
        raise ArtifactError("unsafe_path") from exc
    if _stat_key(info) != workspace.stat_key or not stat.S_ISDIR(info.st_mode):
        raise ArtifactError("unsafe_path")
    if is_reparse_point(workspace.path):
        raise ArtifactError("unsafe_path")


def _artifact_items(artifacts: dict[str, bytes]) -> tuple[tuple[str, bytes], ...]:
    if set(artifacts) != set(ARTIFACT_NAMES):
        raise ArtifactError("io_error")
    return tuple((name, artifacts[name]) for name in ARTIFACT_NAMES)


def _preflight_existing(target: Path, expected: tuple[tuple[str, bytes], ...]) -> str:
    try:
        info = target.lstat()
    except OSError as exc:
        raise ArtifactError("unsafe_path") from exc
    if not stat.S_ISDIR(info.st_mode):
        raise ArtifactError("conflict")
    try:
        children = {child.name: child for child in target.iterdir()}
    except OSError as exc:
        raise ArtifactError("unsafe_path") from exc
    if set(children) != {name for name, _data in expected}:
        raise ArtifactError("conflict")
    for name, data in expected:
        if _read_existing_artifact(children[name]) != data:
            raise ArtifactError("conflict")
    return "idempotent"


def _read_existing_artifact(path: Path) -> bytes:
    if is_reparse_point(path):
        raise ArtifactError("unsafe_path")
    try:
        info = path.lstat()
    except OSError as exc:
        raise ArtifactError("unsafe_path") from exc
    if not stat.S_ISREG(info.st_mode):
        raise ArtifactError("conflict")
    return _read_regular_bytes(path)


def _read_regular_bytes(path: Path) -> bytes:
    try:
        before = path.lstat()
    except FileNotFoundError as exc:
        raise ArtifactError("source_unreachable") from exc
    except OSError as exc:
        raise ArtifactError("source_unreachable") from exc
    if not stat.S_ISREG(before.st_mode) or is_reparse_point(path):
        raise ArtifactError("unsafe_path")
    if before.st_size > MAX_SOURCE_BYTES:
        raise ArtifactError("invalid_args")
    fd = _open_regular(path)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or _stat_key(info) != _stat_key(before):
            raise ArtifactError("unsafe_path")
        if info.st_size > MAX_SOURCE_BYTES:
            raise ArtifactError("invalid_args")
        return _read_fd(fd, info.st_size)
    finally:
        os.close(fd)


def _open_regular(path: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        return os.open(path, flags)
    except FileNotFoundError as exc:
        raise ArtifactError("source_unreachable") from exc
    except OSError as exc:
        raise ArtifactError("unsafe_path") from exc


def _read_fd(fd: int, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = os.read(fd, min(remaining, 65536))
        if not chunk:
            raise ArtifactError("source_unreachable")
        chunks.append(chunk)
        remaining -= len(chunk)
    extra = os.read(fd, 1)
    if extra:
        raise ArtifactError("source_unreachable")
    return b"".join(chunks)


def _exists_or_link(path: Path) -> bool:
    try:
        return path.exists() or path.is_symlink()
    except OSError:
        return True


def _relative_text(path: Path, root: Path) -> str:
    try:
        rel = os.path.relpath(path, root)
    except ValueError as exc:
        raise ArtifactError("unsafe_path") from exc
    return rel.replace(os.sep, "/")


def _stat_key(info: os.stat_result) -> tuple[int, int]:
    if os.name == "nt":
        return (info.st_dev & 0xFFFFFFFF, info.st_ino)
    return (info.st_dev, info.st_ino)
