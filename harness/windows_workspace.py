"""windows_workspace.py -- a low-integrity command that may write in the project.

The read-only namespace in `execution_input_protection` labels the project
medium integrity, so a low-integrity child can read it and change nothing.
This one labels the project low integrity for as long as a command runs, so
the child can write there, and labels it medium again when the last such
command ends. Everything else on the disk keeps its own label, which is medium
or higher, and Windows refuses a low-integrity write to it. That holds for a
path reached through `..`, a junction or a symbolic link, because the label is
read from the object the name leads to.

Paths that already exist and must stay closed (git hook folders, the session's
permission files) are labelled medium after the project is opened, so the
child is refused there by the kernel. That label does not stop a rename of the
folder above them, which is why `workspace_guard` also compares their content
after the run.

Known limits, stated because the label is a machine-wide fact:

  - While a command runs, any other low-integrity process of this user can
    write in the project too.
  - A session that is killed mid-command leaves the project labelled low
    until the next command in it runs.
  - Two Flywheel processes in one project do not share the count below. One
    can close the project while the other's command is running; that command
    then fails with access denied, and nothing is left open.
"""
from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from pathlib import Path

from .execution_input_protection import ExecutionInputProtectionUnavailable

__all__ = ["readonly_namespace", "writable_namespace"]

_LOCK = threading.Lock()
_ACTIVE: dict = {}


def _check_layout(source: Path, output: Path) -> None:
    if (source.parent != output.parent or source == output
            or not source.is_dir() or not output.is_dir() or any(output.iterdir())):
        raise ExecutionInputProtectionUnavailable(
            "project and scratch must be distinct sibling directories, scratch empty")


def _acquire(source: Path, closed, label) -> None:
    """Open the project to low-integrity writes; keep `closed` paths shut."""
    key = os.path.normcase(str(source))
    with _LOCK:
        first = not _ACTIVE.get(key)
        _ACTIVE[key] = _ACTIVE.get(key, 0) + 1   # counted first, so release matches
        if first:
            label(source, "LW")
        for path in closed:
            if os.path.lexists(path):
                label(Path(path), "ME")


def _release(source: Path, label) -> None:
    """Close the project again when no writing command is left in it."""
    key = os.path.normcase(str(source))
    with _LOCK:
        left = _ACTIVE.get(key, 1) - 1
        if left > 0:
            _ACTIVE[key] = left
            return
        _ACTIVE.pop(key, None)
        label(source, "ME")


def _close_unless_open(source: Path, label) -> None:
    """Label the project medium, unless a writing command holds it open.

    A read-only run that started while a writing command was still going
    would otherwise close the project under that command.
    """
    with _LOCK:
        if not _ACTIVE.get(os.path.normcase(str(source))):
            label(source, "ME")


@contextmanager
def _namespace(input_root, output_root, closed, writable: bool):
    if os.name != "nt":
        raise ExecutionInputProtectionUnavailable(
            "this host has no Windows integrity labels")
    source = Path(input_root).resolve(strict=True)
    output = Path(output_root).resolve(strict=True)
    _check_layout(source, output)
    try:
        from .windows_low_integrity import (LowIntegrityRunner, _low_token,
                                            _set_integrity)
        runner = LowIntegrityRunner(source, output)
        _set_integrity(output, "LW")
        runner.token = _low_token()
        try:
            if writable:
                _acquire(source, closed, _set_integrity)
            else:
                _close_unless_open(source, _set_integrity)
            yield runner
        finally:
            if writable:
                _release(source, _set_integrity)
            runner.__exit__(None, None, None)
    except ExecutionInputProtectionUnavailable:
        raise
    except Exception as exc:
        raise ExecutionInputProtectionUnavailable(
            f"Windows workspace protection failed ({type(exc).__name__})") from exc


def writable_namespace(input_root, output_root, closed=()):
    """A runner whose child may write in `input_root` and `output_root`.

    `closed` names paths under the project the child may not write. A host
    that cannot set the labels raises ExecutionInputProtectionUnavailable
    before any child exists, the same refusal the read-only namespace gives.
    """
    return _namespace(input_root, output_root, closed, True)


def readonly_namespace(input_root, output_root):
    """A runner whose child may write only in `output_root`.

    The same contract as `protect_execution_namespace`, sharing the count
    above so it never closes the project under a writing command. While such
    a command runs, this child can write in the project as well.
    """
    return _namespace(input_root, output_root, (), False)
