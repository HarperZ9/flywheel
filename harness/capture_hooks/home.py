"""Find FLYWHEEL_HOME without trusting the environment (7.1, SP-03, N-34).

A repository can set environment variables for the hooks a client runs in it
(a settings `env` block), so the home is not read from `FLYWHEEL_HOME`. It
comes from, in order: an explicit `--home` on the mount line (code in a
settings file, like the hook command itself), the pointer file the gateway
writes at start in a per-user folder located through the operating system,
or the profile folder plus `.flywheel`. `FLYWHEEL_HOME` is read only to
compare: a different value refuses with HOME_MISMATCH.

A home inside a git work tree is refused with HOME_IN_WORKTREE, so a
repository cannot make the spool land in files that get committed. A `--home`
inside the current working directory is refused the same way. The profile
default is exempt from the working-directory rule only: an owner who starts a
session in the profile folder would otherwise lose every capture.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

POINTER_SCHEMA = "flywheel.home-pointer/v1"
_LOCAL_APPDATA = "F1B32785-6FBA-4FCF-9D55-7B8E7F157091"
_PROFILE = "5E6C858F-0E22-4760-9AFE-EA3317B67173"


def _known_folder(guid_text: str) -> Path | None:
    import ctypes
    from ctypes import wintypes
    import uuid

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]
    value = uuid.UUID(guid_text)
    guid = GUID(value.fields[0], value.fields[1], value.fields[2],
                (ctypes.c_ubyte * 8)(*value.bytes[8:]))
    shell = ctypes.WinDLL("shell32")
    ole = ctypes.WinDLL("ole32")
    shell.SHGetKnownFolderPath.argtypes = (ctypes.POINTER(GUID), wintypes.DWORD,
                                           wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p))
    shell.SHGetKnownFolderPath.restype = ctypes.c_long
    ole.CoTaskMemFree.argtypes = (ctypes.c_void_p,)
    out = ctypes.c_void_p()
    if shell.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(out)) != 0:
        return None
    try:
        return Path(ctypes.wstring_at(out.value))
    finally:
        ole.CoTaskMemFree(out)


def profile_dir() -> Path | None:
    if sys.platform == "win32":
        return _known_folder(_PROFILE)
    import pwd
    return Path(pwd.getpwuid(os.getuid()).pw_dir)


def pointer_path() -> Path | None:
    """Where the gateway writes the home pointer, found through the OS."""
    if sys.platform == "win32":
        base = _known_folder(_LOCAL_APPDATA)
        return base / "flywheel" / "home.json" if base else None
    profile = profile_dir()
    return profile / ".local" / "state" / "flywheel" / "home.json" if profile else None


def read_pointer(path: Path | None = None) -> Path | None:
    path = path or pointer_path()
    try:
        doc = json.loads(path.read_bytes()) if path else None
    except (OSError, ValueError):
        return None
    home = doc.get("home") if type(doc) is dict and doc.get("schema") == POINTER_SCHEMA else None
    return Path(home) if type(home) is str and os.path.isabs(home) else None


def _norm(path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def _within(child: str, parent: str) -> bool:
    return child == parent or child.startswith(parent.rstrip(os.sep) + os.sep)


def _is_git_marker(entry: Path) -> bool:
    """A `.git` directory with a HEAD, or a `.git` file naming a gitdir, as git
    itself requires. A stray `.git` folder without HEAD is not a work tree."""
    try:
        if entry.is_dir():
            return (entry / "HEAD").is_file()
        with open(entry, "rb") as stream:
            return stream.read(8) == b"gitdir: "
    except OSError:
        return False


def in_git_worktree(path: Path) -> bool:
    current = Path(_norm(path))
    for candidate in (current, *list(current.parents)[:64]):
        if os.path.lexists(candidate / ".git") and _is_git_marker(candidate / ".git"):
            return True
    return False


def resolve_home(arg_home, environ, cwd, *, pointer: Path | None = None
                 ) -> tuple[Path | None, str | None]:
    """(home, refusal code or None). A refusal still names the resolved home,
    except when no home can be found at all."""
    explicit = bool(arg_home)
    if explicit:
        home = Path(os.path.abspath(str(arg_home)))
    else:
        home = read_pointer(pointer)
        if home is None:
            profile = profile_dir()
            home = profile / ".flywheel" if profile else None
    if home is None:
        return None, "HOME_UNRESOLVED"
    if in_git_worktree(home) or explicit and _within(_norm(home), _norm(cwd)):
        return home, "HOME_IN_WORKTREE"
    stated = environ.get("FLYWHEEL_HOME")
    if stated and _norm(stated) != _norm(home):
        return home, "HOME_MISMATCH"
    return home, None
