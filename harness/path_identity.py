"""Path checks that hold for Windows device, UNC and alias spellings.

A string prefix test on ``os.path.realpath`` misses a path spelled through the
Win32 device namespace (``\\\\?\\C:\\...``, ``\\\\?\\GLOBALROOT\\...``), the NT
object prefix (``\\??\\C:\\...``) or a loopback admin share
(``\\\\localhost\\C$\\...``): realpath keeps the prefix, so the spelling never
matches ``C:\\...`` and a guarded folder reads as outside. A remote UNC value
also opens an SMB session, which can carry the user's NTLM credentials, with no
network grant. Two rules close both:

- ``device_or_unc``: on Windows, a value that starts with two separators or
  with ``\\??\\`` is refused outright, as a tool argument and in the granted
  settings (the Node choice and the local model's project folder). The server
  behind a share controls the file's bytes, size and time stamp, so no pin
  taken from it holds at launch. ``remote_drive`` refuses a drive letter
  mapped to a share the same way.
- ``inside``: containment is decided by identity as well as by string. The
  target's existing ancestors are compared with ``os.path.samefile``, so a
  junction, a hard-linked folder or another spelling of the same folder counts.
- ``reserved_device_name``: Windows opens a device, not a file, for a path
  component whose base name is ``CON``, ``PRN``, ``AUX``, ``NUL``, ``CONIN$``,
  ``CONOUT$``, ``COM1``-``COM9`` or ``LPT1``-``LPT9`` (and the superscript 1, 2
  and 3 forms), in any folder and with any extension: ``C:\\docs\\CON.md`` is
  the console. A read tool pointed at a serial or console device can block
  until its timeout. The rule mirrors gather 1.9.1's own ``localpath._reserved``.
"""
from __future__ import annotations

import ntpath
import os
import re

_WINDOWS = os.name == "nt"
_SEPARATORS = ("\\", "/")
_SPLIT = re.compile(r"[\\/]+")
_DRIVE = re.compile(r"^[A-Za-z]:")
# COM0 and LPT0 stay ordinary file names, so they are not refused.
_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
    | {f"{port}{n}" for port in ("COM", "LPT") for n in "123456789\u00b9\u00b2\u00b3"})


def device_or_unc(value: str, *, windows: bool | None = None) -> bool:
    """True for a Windows device-namespace, NT-object or UNC spelling."""
    if not (_WINDOWS if windows is None else windows):
        return False
    text = value.strip()
    if len(text) >= 2 and text[0] in _SEPARATORS and text[1] in _SEPARATORS:
        return True
    return len(text) >= 4 and text[0] in _SEPARATORS and text[1:3] == "??" \
        and text[3] in _SEPARATORS


def reserved_device_name(value: str, *, windows: bool | None = None) -> bool:
    """True when a component of a Windows path names a reserved device.

    The base name before any dot or colon, trimmed of spaces, is compared:
    ``CON``, ``nul.txt``, ``AUX . .``, ``COM1:`` all match, ``COM0`` and
    ``CONTRIBUTING.md`` do not. On Windows every value is read this way;
    elsewhere only Windows-style text (a backslash or a drive prefix) is, so a
    POSIX file named ``con.md`` stays a file."""
    text = value.strip()
    if not ((_WINDOWS if windows is None else windows) or "\\" in text or _DRIVE.match(text)):
        return False
    tail = ntpath.splitdrive(text)[1]
    return any(part.split(".", 1)[0].split(":", 1)[0].strip(" ").upper() in _RESERVED
               for part in _SPLIT.split(tail) if part)


_DRIVE_REMOTE = 4                 # GetDriveTypeW: a drive letter mapped to a share


def _drive_type(root: str) -> int:
    import ctypes
    return int(ctypes.windll.kernel32.GetDriveTypeW(root))  # type: ignore[attr-defined]


def remote_drive(value: str, *, windows: bool | None = None,
                 drive_type=None) -> bool:
    """True for a Windows path on a drive letter mapped to a network share.

    Only the drive root is asked about (``GetDriveTypeW``), which reads the
    local drive mapping and opens nothing on the share."""
    if not (_WINDOWS if windows is None else windows):
        return False
    text = value.strip()
    if len(text) < 2 or text[1] != ":" or not text[0].isascii() or not text[0].isalpha():
        return False
    if drive_type is None:
        if os.name != "nt":
            return False
        drive_type = _drive_type
    return drive_type(text[0].upper() + ":\\") == _DRIVE_REMOTE


def _string_inside(target: str, base: str) -> bool:
    target, base = os.path.normcase(target), os.path.normcase(base)
    return target == base or target.startswith(base.rstrip("\\/") + os.sep)


def _same(left: str, right: str) -> bool:
    try:
        return os.path.samefile(left, right)
    except (OSError, ValueError):
        return False


def inside(target: str, base: str) -> bool:
    """True when ``target`` is ``base`` or sits under it, by string after
    realpath or by the identity of one of its existing ancestors."""
    if _string_inside(target, base):
        return True
    if not os.path.exists(base):
        return False
    current = target
    while True:
        if os.path.exists(current) and _same(current, base):
            return True
        parent = os.path.dirname(current)
        if not parent or parent == current:
            return False
        current = parent
