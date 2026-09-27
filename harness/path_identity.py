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
"""
from __future__ import annotations

import os

_WINDOWS = os.name == "nt"
_SEPARATORS = ("\\", "/")


def device_or_unc(value: str, *, windows: bool | None = None) -> bool:
    """True for a Windows device-namespace, NT-object or UNC spelling."""
    if not (_WINDOWS if windows is None else windows):
        return False
    text = value.strip()
    if len(text) >= 2 and text[0] in _SEPARATORS and text[1] in _SEPARATORS:
        return True
    return len(text) >= 4 and text[0] in _SEPARATORS and text[1:3] == "??" \
        and text[3] in _SEPARATORS


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
