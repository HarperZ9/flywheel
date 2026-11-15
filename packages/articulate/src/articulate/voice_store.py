"""Where voice profiles live on this computer, and how they are saved, read,
listed and deleted.

The store is one folder: --dir, else ARTICULATE_VOICE_DIR, else the user's
local data folder (%LOCALAPPDATA%\\articulate\\voice on Windows,
$XDG_DATA_HOME/articulate/voice elsewhere). On first save it writes a
.gitignore holding *, so a store inside a repository never gets committed.
Saves go through a temporary file and os.replace, so a profile is never half
written. Only the command line saves or deletes; the MCP tools only read.
"""
import json
import os
import pathlib
import re
import tempfile

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
RESERVED = frozenset({"identity"})  # identity.json holds the owner record


def store_dir(directory=None, environ=None):
    env = os.environ if environ is None else environ
    if directory:
        return pathlib.Path(directory)
    if env.get("ARTICULATE_VOICE_DIR"):
        return pathlib.Path(env["ARTICULATE_VOICE_DIR"])
    if os.name == "nt":
        base = env.get("LOCALAPPDATA") or str(pathlib.Path.home() / "AppData" / "Local")
    else:
        base = env.get("XDG_DATA_HOME") or str(pathlib.Path.home() / ".local" / "share")
    return pathlib.Path(base) / "articulate" / "voice"


def profile_path(name, directory=None):
    if isinstance(name, str) and name.lower() in RESERVED:
        raise ValueError(f"{name!r} is reserved in the voice store; pick another name")
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise ValueError("a voice name is 1 to 64 letters, digits, - or _, starting with a "
                         "letter or digit")
    return store_dir(directory) / (name + ".json")


def save(profile, name, directory=None):
    """Write the profile atomically and return its path."""
    path = profile_path(name, directory)
    folder = path.parent
    folder.mkdir(parents=True, exist_ok=True)
    ignore = folder / ".gitignore"
    if not ignore.exists():
        ignore.write_text("*\n", encoding="utf-8")
    fd, tmp = tempfile.mkstemp(prefix=".voice-", suffix=".tmp", dir=str(folder))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(profile, fh, indent=2, sort_keys=True, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return path


def load(name, directory=None):
    path = profile_path(name, directory)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        raise FileNotFoundError(f"no voice profile named {name!r} in your local voice store; "
                                "build one with articulate voice learn") from None


def delete(name, directory=None):
    """Remove the profile and return the path removed."""
    path = profile_path(name, directory)
    if not path.is_file():
        raise FileNotFoundError(f"no voice profile named {name!r} in your local voice store")
    path.unlink()
    return path


def names(directory=None):
    folder = store_dir(directory)
    if not folder.is_dir():
        return []
    return sorted(p.stem for p in folder.glob("*.json")
                  if _NAME.fullmatch(p.stem) and p.stem.lower() not in RESERVED)
