from __future__ import annotations

import os
import stat
from pathlib import Path

from .cli_artifacts import WorkspaceRoot
from .path_policy import PathPolicyError, assert_operational_surface_path, is_reparse_point
from .undo_io import read_regular_file

RESCUE_ARTIFACT_NAMES = ("CANON.md", "canon.capsule.json", "readiness-probe.json", "rescue.evidence.json")


class RescueOutputError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def publish_rescue_artifacts(
    raw_out: object,
    *,
    workspace: WorkspaceRoot,
    artifacts: dict[str, bytes],
    reserved_labels: tuple[str, ...],
) -> tuple[str, str]:
    path = _checked_output_dir(raw_out, workspace, reserved_labels)
    expected = _artifact_items(artifacts)
    if not _exists_or_link(path):
        raise RescueOutputError("unsafe_path")
    return _relative_text(path, workspace.path), _preflight_existing(path, expected)


def _checked_output_dir(raw_out: object, workspace: WorkspaceRoot, reserved_labels: tuple[str, ...]) -> Path:
    if type(raw_out) is not str or raw_out == "" or "\0" in raw_out:
        raise RescueOutputError("unsafe_path")
    _assert_workspace_stable(workspace)
    try:
        path = assert_operational_surface_path(raw_out, root=workspace.path)
    except PathPolicyError as exc:
        raise RescueOutputError("unsafe_path") from exc
    _reject_reserved(path, workspace.path, reserved_labels)
    _assert_workspace_stable(workspace)
    if _exists_or_link(path) and is_reparse_point(path):
        raise RescueOutputError("unsafe_path")
    return path


def _artifact_items(artifacts: dict[str, bytes]) -> tuple[tuple[str, bytes], ...]:
    if set(artifacts) != set(RESCUE_ARTIFACT_NAMES):
        raise RescueOutputError("io_error")
    return tuple((name, artifacts[name]) for name in RESCUE_ARTIFACT_NAMES)


def _preflight_existing(path: Path, expected: tuple[tuple[str, bytes], ...]) -> str:
    try:
        info = path.lstat()
    except OSError as exc:
        raise RescueOutputError("unsafe_path") from exc
    if not stat.S_ISDIR(info.st_mode):
        raise RescueOutputError("conflict")
    try:
        children = {child.name: child for child in path.iterdir()}
    except OSError as exc:
        raise RescueOutputError("unsafe_path") from exc
    if set(children) != {name for name, _data in expected}:
        raise RescueOutputError("conflict")
    for name, data in expected:
        if _read_child(children[name]) != data:
            raise RescueOutputError("conflict")
    return "idempotent"


def _read_child(path: Path) -> bytes:
    try:
        return read_regular_file(path)
    except Exception as exc:
        code = getattr(exc, "code", None)
        if code in ("unsafe_path", "io_error"):
            raise RescueOutputError(code) from exc
        raise RescueOutputError("conflict") from exc


def _reject_reserved(path: Path, root: Path, reserved_labels: tuple[str, ...]) -> None:
    rel = _relative_text(path, root)
    parts = tuple(part.casefold() for part in rel.split("/"))
    if parts[0] == ".git" or parts[:2] == (".canon", "undo") or parts[:2] == ("tests", "fixtures"):
        raise RescueOutputError("unsafe_path")
    if rel in reserved_labels:
        raise RescueOutputError("unsafe_path")


def _assert_workspace_stable(workspace: WorkspaceRoot) -> None:
    try:
        info = workspace.path.lstat()
    except OSError as exc:
        raise RescueOutputError("unsafe_path") from exc
    if _stat_key(info) != workspace.stat_key or not stat.S_ISDIR(info.st_mode) or is_reparse_point(workspace.path):
        raise RescueOutputError("unsafe_path")


def _exists_or_link(path: Path) -> bool:
    try:
        return path.exists() or path.is_symlink()
    except OSError:
        return True


def _relative_text(path: Path, root: Path) -> str:
    try:
        return os.path.relpath(path, root).replace(os.sep, "/")
    except ValueError as exc:
        raise RescueOutputError("unsafe_path") from exc


def _stat_key(info: os.stat_result) -> tuple[int, int]:
    if os.name == "nt":
        return (info.st_dev & 0xFFFFFFFF, info.st_ino)
    return (info.st_dev, info.st_ino)


__all__ = ["RESCUE_ARTIFACT_NAMES", "RescueOutputError", "publish_rescue_artifacts"]
