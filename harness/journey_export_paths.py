"""Artifact path admission for Journey export.

Split out of journey_export_tx because these functions answer a different
question. Everything here decides whether a caller-supplied reference names a
place under state custody, before any transaction exists. The rest of that
module is about the transaction record itself.

The rule the whole file serves: a reference arrives as text from a request, and
the only paths it may reach are ones already inside the state root. Every check
here is written to refuse rather than to resolve, and links are treated as
escapes rather than followed, because a resolved symlink is how a contained
path stops being contained.
"""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath, PureWindowsPath

from .journey_lock import fsync_directory
from .operation_grants import _secure_owner_only

def _canonical_ref(value: object, *, allow_dot: bool) -> str:
    if type(value) is not str or not value or "\\" in value or "\x00" in value:
        raise ValueError("artifact reference is invalid")
    posix, windows = PurePosixPath(value), PureWindowsPath(value)
    if (value.lower().startswith("file:") or posix.is_absolute()
            or windows.is_absolute() or windows.drive or ".." in posix.parts
            or value != posix.as_posix() or not allow_dot and value == "."):
        raise ValueError("artifact reference is invalid")
    return value

def _is_reparse(path: Path) -> bool:
    return path.is_symlink() or bool(
        getattr(path.lstat(), "st_file_attributes", 0) & 0x400)

def path_present(path: Path) -> bool:
    """Report directory entries without following a broken reparse target."""
    return os.path.lexists(path)

def _check_ancestors(root: Path, relative: str) -> None:
    current = root
    for part in PurePosixPath(relative).parts:
        current = current / part
        if not path_present(current):
            continue
        if _is_reparse(current):
            raise ValueError("artifact path contains a link or reparse point")

def artifact_root_path(state_root: Path, root_ref: object) -> tuple[Path, str]:
    """Admit one existing artifact directory beneath state custody."""
    ref = _canonical_ref(root_ref, allow_dot=True)
    state = Path(state_root).resolve(strict=True)
    if _is_reparse(state):
        raise ValueError("state root is a link or reparse point")
    _check_ancestors(state, ref)
    root = (state / Path(ref)).resolve(strict=True)
    try:
        contained = os.path.commonpath((os.path.normcase(str(state)),
            os.path.normcase(str(root)))) == os.path.normcase(str(state))
    except ValueError:
        contained = False
    if not contained or not root.is_dir() or _is_reparse(root):
        raise ValueError("artifact root is invalid")
    return root, ref

def packet_target_path(root: Path, packet_ref: object) -> tuple[Path, str]:
    """Admit an absent-or-owned packet selector without following links."""
    ref = _canonical_ref(packet_ref, allow_dot=False)
    _check_ancestors(root, ref)
    target = root.joinpath(*PurePosixPath(ref).parts)
    try:
        candidate = target.resolve(strict=False)
        contained = os.path.commonpath((os.path.normcase(str(root)),
            os.path.normcase(str(candidate)))) == os.path.normcase(str(root))
    except (OSError, RuntimeError, ValueError):
        contained = False
    if not contained:
        raise ValueError("packet target escapes artifact root")
    return target, ref

def prepare_target_parent(root: Path, target: Path) -> None:
    """Create and flush only missing ancestors of one admitted target."""
    current = root
    for part in target.relative_to(root).parts[:-1]:
        parent, current = current, current / part
        if path_present(current):
            if not current.is_dir() or _is_reparse(current):
                raise ValueError("packet target ancestor is invalid")
            continue
        current.mkdir(); _secure_owner_only(current, directory=True)
        fsync_directory(parent)
