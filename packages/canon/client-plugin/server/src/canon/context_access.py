"""Whether other accounts on this machine can read or replace the context database.

canon sets no file permissions of its own. On Windows the database and its
journal inherit the ACL of their folder; on POSIX SQLite creates them with the
process umask applied, whatever the folder allows. On POSIX the check reads
the mode bits. The database is `shared` when its group or other bits
grant anything, or when its directory is writable by group or other, since an
account that can write the directory can replace the file. On Windows access
is governed by ACLs this check does not read, so it reports `not_checked`
rather than a guess.
"""
from __future__ import annotations

import os
from pathlib import Path

OWNER_ONLY = "owner_only"
SHARED = "shared"
NOT_CHECKED = "not_checked"


def file_access(path, *, platform: str = os.name, stat=os.stat) -> str:
    if platform == "nt":
        return NOT_CHECKED
    path = Path(path)
    try:
        file_mode = _mode(stat, path)
        dir_mode = stat(path.parent).st_mode
    except OSError:
        return NOT_CHECKED
    if file_mode & 0o077 or dir_mode & 0o022:
        return SHARED
    return OWNER_ONLY


def _mode(stat, path: Path) -> int:
    try:
        return stat(path).st_mode
    except FileNotFoundError:
        return 0
