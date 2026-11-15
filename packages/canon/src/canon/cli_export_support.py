from __future__ import annotations

import io
import os
from pathlib import Path
from typing import TextIO

from .cli_artifacts import WorkspaceRoot
from .path_policy import PathPolicyError, assert_operational_surface_path


class ExportCliError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def checked_region_path(raw: object, workspace: WorkspaceRoot, *, expected: str) -> Path:
    path = checked_output_path(raw, workspace)
    if relative_path(path, workspace.path) != expected:
        raise ExportCliError("conflict")
    return path


def checked_output_path(raw: object, workspace: WorkspaceRoot) -> Path:
    try:
        path = assert_operational_surface_path(raw, root=workspace.path)
    except PathPolicyError as exc:
        raise ExportCliError("unsafe_path") from exc
    _reject_reserved(path, workspace.path)
    return path


def write_stdout(stdout: TextIO, text: str) -> None:
    if isinstance(stdout, io.TextIOWrapper):
        stdout.flush()
        stdout.buffer.write(text.encode("utf-8"))
        stdout.buffer.flush()
        return
    stdout.write(text)


def relative_path(path: Path, root: Path) -> str:
    try:
        return os.path.relpath(path, root).replace(os.sep, "/")
    except ValueError as exc:
        raise ExportCliError("unsafe_path") from exc


def _reject_reserved(path: Path, root: Path) -> None:
    parts = tuple(part.casefold() for part in relative_path(path, root).split("/"))
    if parts[0] == ".git" or parts[:2] == (".canon", "undo") or parts[:2] == ("tests", "fixtures"):
        raise ExportCliError("unsafe_path")


__all__ = [
    "ExportCliError",
    "checked_output_path",
    "checked_region_path",
    "relative_path",
    "write_stdout",
]
