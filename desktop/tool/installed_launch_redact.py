"""Redaction for installed-launch receipt values.

A receipt may be attached to a pull request or a release, so it names no local
account and no local path:

- the install root is replaced in any letter case, wherever it appears;
- a drive path anywhere in a value, quoted or bare, is replaced;
- a value equal to the account running the check, and the installer's
  ``Inno Setup: User`` value, read ``<user>``.
"""
from __future__ import annotations

import getpass
import os
import re

USER = "<user>"
LOCAL_PATH = "<redacted-local-path>"
ACCOUNT_KEYS = frozenset({"Inno Setup: User"})
_QUOTED_DRIVE_PATH = re.compile(r'"[A-Za-z]:[\\/][^"]*"')
_BARE_DRIVE_PATH = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/][^\s\"',;|]*")


def account_names() -> frozenset[str]:
    """The names this process runs under, lower case, for comparison."""
    names = {os.environ.get(key, "") for key in ("USERNAME", "USER", "LOGNAME", "LNAME")}
    try:
        names.add(getpass.getuser())
    except (KeyError, OSError):
        pass                       # no account name is resolvable; the env names stand
    return frozenset(name.strip().lower() for name in names if name.strip())


def redact_text(value: str, root: str) -> str:
    """``value`` with the install root, drive paths and the account name masked."""
    if value.strip().lower() in account_names():
        return USER
    if len(value) > 2 and value[1] == ":" and value[2] in ("\\", "/") \
            and root.lower() not in value.lower():
        return LOCAL_PATH
    if root and root.lower() in value.lower():
        value = re.sub(re.escape(root), "<install_root>", value, flags=re.IGNORECASE)
        value = value.replace("\\", "/")
    value = _QUOTED_DRIVE_PATH.sub('"' + LOCAL_PATH + '"', value)
    return _BARE_DRIVE_PATH.sub(LOCAL_PATH, value)
