"""The one way the harness turns a program name into the file it starts.

Windows starts a bare name such as ``git`` or ``pip`` from the current folder
before PATH. ``shutil.which`` and ``cmd.exe`` do the same, and a relative,
drive-relative (``C:tools``) or linked PATH entry can lead back into that folder
on any platform. A program planted in a checkout, a task folder or a download
folder then answers to a trusted name. Every bare-name lookup the harness makes
goes through the vendored safe_spawn helper instead (``harness/_vendor``,
byte-identical to release 1.0.1 and pinned by ``VENDORED.sha256``): it walks only
absolute PATH entries that reach no working folder, refuses a name holding a
colon, and on Windows prefers a ``.exe`` anywhere on PATH over a batch shim.

- ``resolve(name)``: the absolute path, or ``ProgramUnavailable`` (a
  ``FileNotFoundError``, so existing "not installed" handling still applies).
- ``which(name)``: the same lookup, None instead of raising.
- ``argv(command)``: the command with its program resolved. A batch target
  (``.cmd``, ``.bat``) whose arguments hold cmd.exe metacharacters raises
  ``ProgramRefused`` before anything starts.
- ``shell_env(env)``: the environment for a ``shell=True`` child. PATH keeps what
  the lookup keeps, and on Windows ``NoDefaultCurrentDirectoryInExePath=1`` stops
  cmd.exe searching the working folder first.
- ``system_tool(name)``: a Windows system program from the System32 folder.

Which PATH is read follows subprocess. On Windows CreateProcess searches the
parent's PATH, so the lookup reads the parent's. On POSIX subprocess searches the
PATH it hands the child, so the lookup reads that one.
"""
from __future__ import annotations

import ntpath
import os
from typing import Mapping, Sequence

from ._vendor import safe_spawn

NO_CWD_SEARCH = safe_spawn.NO_CWD_SEARCH
_STARTABLE = (".exe", ".com", ".cmd", ".bat")


class ProgramUnavailable(FileNotFoundError):
    """No safe file answers to the name. ``code`` is safe_spawn's reason
    (``NOT_FOUND``, ``BAD_PATH``, ``BAD_OVERRIDE``); ``filename`` is the name
    asked for, never a resolved path."""

    def __init__(self, name: str, code: str, message: str) -> None:
        super().__init__(2, message, name)
        self.code = code


class ProgramRefused(OSError):
    """The program resolved, and starting it with these arguments was refused."""

    def __init__(self, name: str, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.filename = name


def _windows() -> bool:
    return os.name == "nt"


def _search_env(env: Mapping[str, str] | None) -> Mapping[str, str] | None:
    """The environment whose PATH the lookup walks (see the module docstring)."""
    if env is None or _windows():
        return None
    if "PATH" in env:
        return env
    return {**env, "PATH": safe_spawn.POSIX_FALLBACK_PATH}


def resolve(name, *, cwd=None, env: Mapping[str, str] | None = None,
            override_var: str | None = None) -> str:
    """The absolute file ``name`` starts, or ProgramUnavailable.

    ``name`` is a bare name or an absolute path. ``cwd`` is the folder the child
    will run in; PATH entries reaching it are skipped as well as the caller's.
    On Windows a name that already carries ``.exe``, ``.com``, ``.cmd`` or
    ``.bat`` must resolve to a file with that extension.
    """
    text = os.fspath(name)
    stem, ext = ntpath.splitext(text)
    exact = _windows() and ext.lower() in _STARTABLE and not ("/" in text or "\\" in text)
    folder = None if cwd is None else os.fspath(cwd)
    try:
        found = safe_spawn.resolve(stem if exact else text, override_var,
                                   _search_env(env), cwd=folder)
    except safe_spawn.SpawnRefused as exc:
        raise ProgramUnavailable(os.path.basename(text), exc.code, str(exc)) from None
    if exact and ntpath.splitext(found)[1].lower() != ext.lower():
        raise ProgramUnavailable(os.path.basename(text), "NOT_FOUND",
                                 f"{os.path.basename(text)} was not found on PATH")
    return found


def which(name, *, cwd=None, env: Mapping[str, str] | None = None) -> str | None:
    """``resolve`` that answers None where it would raise: a drop-in for
    ``shutil.which`` that never finds a copy in the working folder."""
    try:
        return resolve(name, cwd=cwd, env=env)
    except ProgramUnavailable:
        return None


def argv(command: Sequence, *, cwd=None, env: Mapping[str, str] | None = None) -> list[str]:
    """``command`` with its program resolved to an absolute path.

    Raises ProgramUnavailable when no safe file answers, and ProgramRefused when
    the program is a Windows batch file and an argument holds a character cmd.exe
    would read as a command.
    """
    parts = [os.fspath(part) for part in command]
    if not parts:
        raise ProgramUnavailable("", "NOT_FOUND", "no program was named")
    exe = resolve(parts[0], cwd=cwd, env=env)
    out = [exe, *parts[1:]]
    if safe_spawn.is_batch(exe) and any(safe_spawn.cmd_unsafe(part) for part in out):
        raise ProgramRefused(os.path.basename(parts[0]), "UNSAFE_ARGUMENT",
                             f"{os.path.basename(parts[0])} is a batch file and an "
                             "argument holds characters cmd.exe would reinterpret")
    return out


def shell_env(env: Mapping[str, str] | None = None, *, cwd=None) -> dict[str, str]:
    """``env`` (default: this process's) for a ``shell=True`` child.

    Every variable stays. PATH keeps only the entries ``resolve`` would walk, so
    the shell's own lookup skips the working folder, and on Windows the shell is
    told not to search the working folder before PATH.
    """
    base = dict(os.environ if env is None else env)
    folder = None if cwd is None else os.fspath(cwd)
    return safe_spawn.child_env(allow=tuple(base), environ=base, cwd=folder)


def path_folders(value: str) -> list[str]:
    """The folders in PATH value ``value`` that ``resolve`` would walk, as real
    folders: absolute entries that reach no working folder, in order."""
    windows = _windows()
    admit = safe_spawn._reach_test(None, windows)
    return [folder for _, folder in safe_spawn._path_entries(value, windows, admit)]


def system_tool(name: str) -> str:
    """The Windows system program ``name`` (for example ``taskkill.exe``).

    Read from ``%SystemRoot%\\System32`` first, then through the guarded lookup,
    so no folder earlier on PATH and no working folder can answer for it.
    """
    root = safe_spawn._get(os.environ, "SystemRoot") or "C:\\Windows"
    candidate = ntpath.join(root, "System32", name)
    if os.path.isfile(candidate):
        return candidate
    return resolve(name)
