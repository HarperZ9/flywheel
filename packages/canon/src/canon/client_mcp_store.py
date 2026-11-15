"""Existing ContextStore query semantics with a non-initializing read connection.

Reads deserialize a bounded, stable snapshot of the database file into memory.
The read path never opens the live SQLite path, so it never creates a sidecar
file, takes a lock, mints identity or migrates schema. A WAL-mode store is read
by applying the committed frames of its write-ahead log to the snapshot in
memory. While a writer holds a rollback journal, or a file changes during the
copy, the read retries until SNAPSHOT_RETRY_SECONDS have passed and is then
refused as busy. Python's SQLite must provide deserialize().
"""
from contextlib import contextmanager
from pathlib import Path
import os
import sqlite3
import time

from .context_audit import verified_state
from .context_migrate import compare_store_id, store_identity
from .context_store import ContextStore
from .path_policy import is_reparse_point, is_windows_ads_path
from .sqlite_wal import (ROLLBACK_HEADER, SQLITE_MAGIC, WAL_HEADER, open_shared,
                         wal_image)

MAX_SNAPSHOT_BYTES = 256 * 1024 * 1024
SNAPSHOT_RETRY_SECONDS = 5.0
_BUSY = "context database stayed busy with another writer; try again"


class SnapshotBusy(ValueError):
    """A writer was active for the whole retry window."""


class _Retry(Exception):
    """A transient state seen during one snapshot attempt."""


def checked_path(path):
    """Reject linked components before resolve and again before each connection.

    These checks do not eliminate concurrent filesystem replacement races and
    are not an OS sandbox against another process running as the same account.
    """
    path = Path(path)
    if not path.is_absolute() or is_windows_ads_path(path):
        raise ValueError("context database requires an absolute ordinary file path")
    if any(is_reparse_point(part) for part in (path, *path.parents)):
        raise ValueError("context database path contains a linked component")
    return path


def _stat_key(info):
    # Windows 3.12 fstat and stat can disagree on ctime (creation/change time).
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _sidecar(path, suffix):
    side = Path(str(path) + suffix)
    if is_reparse_point(side):
        raise ValueError("context database sidecar is a linked file")
    return side


def _path_key(path):
    try:
        return _stat_key(path.stat())
    except FileNotFoundError:
        return None
    except PermissionError:
        # Windows refuses access to a file whose deletion is still pending.
        raise _Retry() from None


def _hot_journal(path):
    """A rollback journal with a live header means a writer may be mid-commit."""
    try:
        with open_shared(_sidecar(path, "-journal")) as stream:
            head = stream.read(1)
    except FileNotFoundError:
        return False
    except PermissionError:
        return True  # a journal the writer is deleting on Windows; retry
    return head not in (b"", b"\x00")


def _read(path, limit, optional=False):
    """File bytes and a stat key, or (None, None) for a missing optional file."""
    try:
        stream = open_shared(path)
    except FileNotFoundError:
        if optional:
            return None, None
        raise
    except PermissionError:
        # A WAL that a closing writer is deleting refuses access on Windows.
        if optional:
            raise _Retry() from None
        raise
    with stream:
        before = os.fstat(stream.fileno())
        if before.st_size > limit or not (optional or before.st_size):
            raise ValueError("client snapshot must be nonempty and at most 256 MiB")
        # Request only the bytes fstat reported, plus one to see growth. Asking
        # for the whole bound allocates 256 MiB per read, which on Windows
        # costs ~50 ms and widens the window in which a writer forces a retry.
        data = stream.read(before.st_size + 1)
        after = os.fstat(stream.fileno())
    if _stat_key(before) != _stat_key(after) or len(data) != before.st_size:
        raise _Retry()
    return data, _stat_key(after)


def _attempt(path):
    if _hot_journal(path):
        raise _Retry()
    data, key = _read(path, MAX_SNAPSHOT_BYTES)
    if data[:16] != SQLITE_MAGIC or data[18:20] not in (ROLLBACK_HEADER, WAL_HEADER):
        raise ValueError("context database is not a SQLite database")
    wal_path = _sidecar(path, "-wal")
    wal, wal_key = None, None
    if data[18:20] == WAL_HEADER:
        wal, wal_key = _read(wal_path, MAX_SNAPSHOT_BYTES - len(data), optional=True)
    checked_path(path)
    if _hot_journal(path) or _path_key(path) != key:
        raise _Retry()
    if data[18:20] == WAL_HEADER and _path_key(wal_path) != wal_key:
        raise _Retry()
    return wal_image(data, wal) if data[18:20] == WAL_HEADER else data


def _snapshot(path):
    deadline = time.monotonic() + SNAPSHOT_RETRY_SECONDS
    delay = 0.005
    while True:
        try:
            return _attempt(path)
        except _Retry:
            if time.monotonic() >= deadline:
                raise SnapshotBusy(_BUSY) from None
            time.sleep(delay)
            delay = min(delay * 2, 0.1)


def _read_connection(path):
    data = _snapshot(path)
    conn = sqlite3.connect(":memory:")
    try:
        conn.deserialize(data)
        conn.execute("PRAGMA query_only=ON")
        return conn
    except Exception:
        conn.close()
        raise


def table_names(path):
    """Table names of an existing SQLite file, read without creating any file.

    A rollback-journal file, or a WAL file whose -wal and -shm both exist, is
    read through a read-only SQLite connection, which creates nothing there. A
    WAL file missing either sidecar has no open connection: it is read from a
    memory snapshot, or, above the snapshot bound, as immutable.
    """
    path = checked_path(path)
    with open_shared(path) as stream:
        head = stream.read(100)
    if head[:16] != SQLITE_MAGIC:
        raise sqlite3.DatabaseError("file is not a database")
    sidecars = [_sidecar(path, suffix).exists() for suffix in ("-wal", "-shm")]
    uri = path.resolve().as_uri() + "?mode=ro"
    if head[18:20] != WAL_HEADER or all(sidecars):
        conn = sqlite3.connect(uri, uri=True, timeout=10)
    elif path.stat().st_size + _wal_size(path) <= MAX_SNAPSHOT_BYTES:
        conn = _read_connection(path)
    else:
        conn = sqlite3.connect(uri + "&immutable=1", uri=True)
    try:
        return {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def _wal_size(path):
    try:
        return _sidecar(path, "-wal").stat().st_size
    except FileNotFoundError:
        return 0


class ClientBackend:
    def __init__(self, path, writable=False):
        self._path = str(path)
        self.writable = writable

    @contextmanager
    def _conn(self):
        path = checked_path(self._path)
        if self.writable:
            conn = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=10)
        else:
            conn = _read_connection(path)
        try:
            yield conn
            if self.writable:
                conn.commit()
        finally:
            conn.close()


class ClientStore(ContextStore):
    """Reuse Canon's audited ingest/query/get without its initializing constructor."""

    def __init__(self, path, writable=False):
        self._backend = ClientBackend(path, writable)

    def identity(self):
        with self._backend._conn() as conn:
            conn.execute("BEGIN")
            return store_identity(conn, create=False)[0]

    def _records(self, workspace, project, expected_store_id=None):
        with self._backend._conn() as conn:
            conn.execute("BEGIN")
            store_id, version = store_identity(conn, create=False)
            compare_store_id(store_id, expected_store_id)
            state = verified_state(conn, version)
        records = [row.record for key, row in sorted(state.live.items())
                   if (row.record.data.get("workspace_id"), row.record.data.get("project_id"))
                   == (workspace, project) and row.record.data.get("event_record_id")]
        return records, store_id, state.purged_ids()

    def get(self, *args, **kwargs):
        result = super().get(*args, **kwargs)
        if "record" not in result:
            # Tombstones contain no scope; do not reveal a foreign purged id.
            result.pop("purged", None)
        return result

    def health(self, expected):
        with self._backend._conn() as conn:
            conn.execute("BEGIN")
            store_id, version = store_identity(conn, create=False)
            compare_store_id(store_id, expected)
            verified_state(conn, version)
        return {"ok": True, "store_id": store_id, "server": "canon-client",
                "does_not_prove": ["audit integrity does not establish source truth",
                                   "this launch grants access, not caller authentication"]}
