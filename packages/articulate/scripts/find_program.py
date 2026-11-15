"""Find a program on the PATH without trusting the working folder.

    find_program("git") -> "/usr/bin/git", or None

On Windows, CreateProcess and shutil.which both look in the current folder
before the PATH, and any PATH entry that is relative or names the working folder
does the same on every system. A repository or a download folder can then hold a
file named git or python3 that runs in place of the real one. This lookup takes
only absolute PATH entries outside the folders to avoid (the working folder by
default) and returns an absolute path, so the caller starts exactly that file.
On Windows it accepts .exe and .com only: a batch file runs through cmd.exe,
which reads its arguments as commands.

Standard library only.
"""
import os
from pathlib import Path

_WINDOWS_SUFFIXES = (".exe", ".com")


def _inside(folder, avoid):
    return any(folder == a or a in folder.parents for a in avoid)


def _candidates(folder, name):
    if os.name != "nt":
        return [folder / name]
    if name.lower().endswith(_WINDOWS_SUFFIXES):
        return [folder / name]
    return [folder / (name + suffix) for suffix in _WINDOWS_SUFFIXES]


def find_program(name, avoid=None):
    """The absolute path of `name` from an absolute PATH entry outside every folder
    in `avoid` (default: the working folder), or None."""
    avoid = [Path(a).resolve() for a in (avoid if avoid is not None else [os.getcwd()])]
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry or not os.path.isabs(entry):
            continue
        try:
            folder = Path(entry).resolve()
        except OSError:
            continue
        if _inside(folder, avoid):
            continue
        for path in _candidates(folder, name):
            if path.is_file() and os.access(path, os.X_OK):
                return str(path)
    return None
