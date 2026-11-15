"""File IO for `canon handoff` and `canon switch`, with every failure named.

A file that cannot be read as UTF-8 text, a path whose parent is a file, a
permission error, a destination that already exists: each becomes a refusal
with a stable failure code, so a `--json` caller always gets a result object
and never a traceback. A link found on the way to an instruction file is
refused again at write time, and a file `switch --create` makes is opened in
exclusive mode, so a link or a file planted between the plan and the write
makes the write fail rather than land somewhere else.
"""
from __future__ import annotations

import os
from pathlib import Path

from .cli_workspace_common import CommandFailure
from .workspace.switch_host import SwitchRefused, safe_path


def read_text(path: str) -> str | None:
    """The file's text, or None when nothing is there. A dangling link is not
    'nothing': it is refused, like any path canon cannot read as text."""
    if not os.path.lexists(path):
        return None
    try:
        with open(path, encoding="utf-8", newline="") as handle:
            return handle.read()
    except UnicodeDecodeError as exc:
        raise SwitchRefused("conflict", f"{path}: not a UTF-8 text file") from exc
    except (IsADirectoryError, NotADirectoryError, FileNotFoundError) as exc:
        raise SwitchRefused("unsafe_path", f"{path}: not a readable file ({exc})") from exc
    except OSError as exc:
        raise CommandFailure("io_error", f"cannot read {path}: {exc}") from exc


def instruction_writer(root: str, *, create: bool):
    """A write function for one instruction file under `root`."""
    def write(path: str, text: str) -> None:
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise CommandFailure("io_error", f"cannot create the folder for {path}: {exc}") from exc
        safe_path(path, root)
        try:
            with open(path, "x" if create else "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
        except FileExistsError as exc:
            raise SwitchRefused("conflict", f"{path} appeared while the switch was planned; "
                                            "nothing was written, run it again") from exc
        except OSError as exc:
            raise CommandFailure("io_error", f"cannot write {path}: {exc}") from exc
    return write


def check_new_files(paths: list[str]) -> None:
    """Refuse before anything is written when a destination exists or its
    folder does not."""
    for path in paths:
        if os.path.lexists(path):
            raise CommandFailure("conflict", f"{path} already exists; not overwritten")
        if not Path(path).parent.is_dir():
            raise CommandFailure("io_error", f"the folder for {path} does not exist")


def write_new_files(pairs: list[tuple[str, str]]) -> None:
    """Write each (path, text) as a new file, or none of them. Every
    destination is checked first (it must not exist and its folder must), and
    a file already written is removed when a later one fails."""
    check_new_files([path for path, _ in pairs])
    written: list[str] = []
    try:
        for path, text in pairs:
            with open(path, "x", encoding="utf-8", newline="") as handle:
                handle.write(text)
            written.append(path)
    except OSError as exc:
        for path in written:
            os.remove(path)
        raise CommandFailure("io_error", f"cannot write {path}: {exc}; nothing was kept") from exc
