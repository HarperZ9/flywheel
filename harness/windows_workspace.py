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
after the run. `opened` names folders outside the project that are opened the
same way: the git folders a linked worktree writes to.

A label is a fact on disk that outlives this process, so three things close
it. The last command to end labels the folders medium. A handler registered
with `atexit` does the same when the interpreter exits with a command still
counted. And every opened project has a record under the Flywheel home, which
`sweep` reads when the next session starts and closes whatever a killed
process left. A close that fails puts a hold on the project
(`workspace_marks.hold`), so commands stay read-only until a person has looked.

Known limits:

  - While a command runs, any other low-integrity process of this user can
    write in the project too.
  - Two Flywheel processes in one project do not share the count below. One
    can close the project while the other's command is running; that command
    then fails with access denied, and nothing is left open.
"""
from __future__ import annotations

import atexit
import logging
import os
import threading
from contextlib import contextmanager
from pathlib import Path

from . import workspace_marks
from .execution_input_protection import ExecutionInputProtectionUnavailable

__all__ = ["readonly_namespace", "sweep", "writable_namespace"]

log = logging.getLogger(__name__)
_LOCK = threading.Lock()
_ACTIVE: dict = {}
_AT_EXIT = []


def _check_layout(source: Path, output: Path) -> None:
    if (source.parent != output.parent or source == output
            or not source.is_dir() or not output.is_dir() or any(output.iterdir())):
        raise ExecutionInputProtectionUnavailable(
            "project and scratch must be distinct sibling directories, scratch empty")


def _shut(entry: dict, label) -> list:
    """Label every folder of `entry` medium; hold the project if one stayed open."""
    errors = []
    for path in [entry["source"], *entry["opened"]]:
        try:
            label(Path(path), "ME")
        except Exception as exc:     # every folder is tried; the failure is recorded
            log.warning("could not close %s to the sandbox", path, exc_info=True)
            errors.append(f"{path}: {exc}")
    if errors:
        workspace_marks.hold(entry["source"], "Windows could not close the project to "
                             f"the sandbox after a command ({errors[0]})", entry["state"])
    else:
        workspace_marks.mark_closed(entry["source"], entry["state"])
    return errors


def _close_all(label=None) -> None:
    """Close every project this process still holds open. Runs at exit."""
    if label is None:
        from .windows_low_integrity import _set_integrity as label
    with _LOCK:
        entries = list(_ACTIVE.values())
        _ACTIVE.clear()
    for entry in entries:
        _shut(entry, label)


def _acquire(source: Path, closed, label, opened=(), state=None) -> None:
    """Open the project to low-integrity writes; keep `closed` paths shut."""
    key = os.path.normcase(str(source))
    with _LOCK:
        entry = _ACTIVE.get(key)
        if entry is None:
            entry = _ACTIVE[key] = {"count": 0, "source": source, "state": state,
                                    "opened": [Path(path) for path in opened]}
        entry["count"] += 1          # counted first, so release always matches
        if not _AT_EXIT:
            atexit.register(_close_all)
            _AT_EXIT.append(True)
        if entry["count"] == 1:
            workspace_marks.mark_open(source, [source, *entry["opened"]], state)
            for path in [source, *entry["opened"]]:
                label(path, "LW")
        for path in closed:
            if os.path.lexists(path):
                label(Path(path), "ME")


def _release(source: Path, label) -> None:
    """Close the project again when no writing command is left in it."""
    key = os.path.normcase(str(source))
    with _LOCK:
        entry = _ACTIVE.get(key)
        if entry is None:
            return
        entry["count"] -= 1
        if entry["count"] > 0:
            return
        del _ACTIVE[key]
    _shut(entry, label)


def _close_unless_open(source: Path, label) -> None:
    """Label the project medium, unless a writing command holds it open.

    A read-only run that started while a writing command was still going
    would otherwise close the project under that command. A folder this
    account cannot label is accepted when it carries no low label: with no
    label it is medium already, and the child cannot write it.
    """
    from .windows_label import is_low
    with _LOCK:
        if _ACTIVE.get(os.path.normcase(str(source))):
            return
        try:
            label(source, "ME")
        except ExecutionInputProtectionUnavailable:
            if is_low(source):
                raise


def sweep(state=None, label=None) -> int:
    """Close folders a dead process left open; returns how many records it read.

    Called when a session starts. A record written by this process is left
    alone. Another live session's record is closed too: its running command
    then fails with access denied, which is the safe way to be wrong.
    """
    records = [(path, record) for path, record in workspace_marks.left_open(state)
               if record.get("pid") != os.getpid()]
    if not records:
        return 0
    if label is None:
        from .windows_low_integrity import _set_integrity as label
    for path, record in records:
        folders = [Path(p) for p in record.get("paths", []) if os.path.isdir(p)]
        if folders:
            _shut({"source": folders[0], "opened": folders[1:], "state": state}, label)
        try:                         # the record names its own file; the root may be gone
            path.unlink()
        except OSError:
            log.warning("could not remove %s", path, exc_info=True)
    return len(records)


@contextmanager
def _namespace(input_root, output_root, closed, writable: bool, opened=(), state=None):
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
                _acquire(source, closed, _set_integrity, opened, state)
            else:
                _close_unless_open(source, _set_integrity)
            yield runner
        finally:
            try:
                if writable:
                    _release(source, _set_integrity)
            finally:
                runner.__exit__(None, None, None)
    except ExecutionInputProtectionUnavailable:
        raise
    except Exception as exc:
        raise ExecutionInputProtectionUnavailable(
            f"Windows workspace protection failed ({type(exc).__name__})") from exc


def writable_namespace(input_root, output_root, closed=(), opened=(), state=None):
    """A runner whose child may write in `input_root`, `opened` and `output_root`.

    `closed` names paths under the project the child may not write. A host
    that cannot set the labels raises ExecutionInputProtectionUnavailable
    before any child exists, the same refusal the read-only namespace gives.
    """
    return _namespace(input_root, output_root, closed, True, opened, state)


def readonly_namespace(input_root, output_root):
    """A runner whose child may write only in `output_root`.

    The same contract as `protect_execution_namespace`, sharing the count
    above so it never closes the project under a writing command. While such
    a command runs, this child can write in the project as well.
    """
    return _namespace(input_root, output_root, (), False)
