"""The checked SQLite scrub every store the deletion engine touches uses
(7.10, SP-14, N-29, EN-C10).

1. `busy_timeout=5000`, `secure_delete=ON`, `temp_store=MEMORY`. With the
   default temp store, VACUUM wrote an `etilqs_*` transient database into the
   temporary directory, outside custody (experiment X10). secure_delete
   zeroes the pages the DELETE frees, so a scrub that stops DELETE_PENDING
   before VACUUM still keeps the deleted text out of them once a later
   checkpoint copies them into the database. Its default is chosen when
   SQLite is built (ON in Debian and Ubuntu, OFF in python.org's Windows
   build), so the scrub sets it on its own connection.
2. `BEGIN IMMEDIATE`; the caller deletes rows and appends its audit rows;
   commit, or roll back and re-raise.
3. For WAL databases, `wal_checkpoint(TRUNCATE)` must return (0, 0, 0) and
   leave the WAL empty. An open reader makes it return busy and keep the WAL
   (experiment X9); the scrub retries under backoff and then stops with
   DELETE_PENDING and DB_BUSY instead of claiming success.
4. VACUUM, then a second checked checkpoint, because in WAL mode VACUUM writes
   the whole database through the WAL.

The clusters that a truncated WAL, an unlinked rollback journal or a shrunk
database file release still hold old bytes. That residue is named by the
caller's report as `freed_clusters`; nothing here can reach it.
"""
from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import time


def _checkpoint(con, wal: Path, retry_s: float, sleep) -> list[int] | None:
    deadline = time.monotonic() + retry_s
    delay = 0.05
    while True:
        result = list(con.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone())
        empty = not wal.exists() or wal.stat().st_size == 0
        if result == [0, 0, 0] and empty:
            return result
        if time.monotonic() >= deadline:
            raise _Pending("DB_BUSY", result)
        sleep(delay)
        delay = min(delay * 2, 1.0)


class _Pending(Exception):
    def __init__(self, reason: str, checkpoint=None) -> None:
        super().__init__(reason)
        self.reason, self.checkpoint = reason, checkpoint


def _delete(con, delete) -> None:
    con.execute("BEGIN IMMEDIATE")
    try:
        delete(con)
    except BaseException:
        con.execute("ROLLBACK")
        raise
    con.execute("COMMIT")


def scrub(db_path, delete, *, retry_s: float = 30.0, sleep=time.sleep) -> dict:
    """Run `delete(connection)` in one transaction, then scrub. Returns
    {"state": "SCRUBBED" | "DELETE_PENDING", "reason"?, "checkpoint"}."""
    path = Path(db_path)
    wal = path.with_name(path.name + "-wal")
    con = sqlite3.connect(str(path), timeout=5, isolation_level=None)
    try:
        for pragma in ("busy_timeout=5000", "secure_delete=ON", "temp_store=MEMORY"):
            con.execute(f"PRAGMA {pragma}")
        is_wal = con.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        _delete(con, delete)
        checkpoint = _checkpoint(con, wal, retry_s, sleep) if is_wal else None
        con.execute("VACUUM")
        if is_wal:
            checkpoint = _checkpoint(con, wal, retry_s, sleep)
        return {"state": "SCRUBBED", "checkpoint": checkpoint}
    except _Pending as pending:
        return {"state": "DELETE_PENDING", "reason": pending.reason,
                "checkpoint": pending.checkpoint}
    except sqlite3.OperationalError as exc:
        if "out of memory" in str(exc).lower():
            return {"state": "DELETE_PENDING", "reason": "SCRUB_NOMEM", "checkpoint": None}
        if "locked" in str(exc).lower() or "busy" in str(exc).lower():
            return {"state": "DELETE_PENDING", "reason": "DB_BUSY", "checkpoint": None}
        raise
    finally:
        con.close()


def journal_residue(db_path) -> bool:
    """Whether a rollback journal file is present beside the database now."""
    return os.path.exists(str(db_path) + "-journal")
