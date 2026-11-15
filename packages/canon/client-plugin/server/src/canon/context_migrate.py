"""Identity and schema migration for the Canon context store.

The identity marker, `context_store_identity_version`, says what a reader has
to understand before it may read the database. Version 1 is the shape canon
0.3.0 writes: put rows with plain sha256 digests. Version 2 adds purge rows,
their tombstones, and salted puts. The first purge or salted put raises the
marker to 2 inside its own transaction, so canon 0.3.0 and older refuse the
database as "identity invalid" instead of reading a purge row as tampering.
Reading never raises the marker.

CREATE TABLE IF NOT EXISTS never adds a column to a table that exists, so a
database from before version 2 gets the audit `op` column, the record `salt`
column and the tombstone table here, by ALTER TABLE, the first time this
version writes to it. The caller holds the write transaction, so two writers
cannot both add a column.
"""
from __future__ import annotations

import re
import secrets


class ContextStoreIdentityError(ValueError):
    """The caller's bound store identity does not match this Canon store."""


META_TABLE = "context_store_meta"
VERSION_TABLE = "context_store_identity_version"
TOMBSTONE_TABLE = "context_tombstones"
STORE_ID_KEY = "store_id"
VERSION_KEY = "schema_version"
VERSION_PLAIN = "1"
VERSION_OPS = "2"
READABLE_VERSIONS = (VERSION_PLAIN, VERSION_OPS)
_STORE_ID = re.compile(r"ctxstore_[0-9a-f]{32}\Z")
_INVALID = "context store identity invalid"


def store_identity(conn, *, create):
    """(store_id, version). A new or never-migrated store gets an identity at
    version 1 when `create` is set; any other missing or malformed part of an
    established identity fails closed rather than being minted again."""
    meta_exists = table_exists(conn, META_TABLE)
    version_exists = table_exists(conn, VERSION_TABLE)
    if not meta_exists:
        if version_exists:
            raise ContextStoreIdentityError(_INVALID)
        if not create:
            raise ContextStoreIdentityError("context store identity missing")
        return _create_identity(conn), VERSION_PLAIN
    if not version_exists:
        raise ContextStoreIdentityError(_INVALID)
    version = _single_value(conn, VERSION_TABLE, VERSION_KEY)
    if version not in READABLE_VERSIONS:
        raise ContextStoreIdentityError(_INVALID)
    store_id = _single_value(conn, META_TABLE, STORE_ID_KEY)
    if not valid_store_id(store_id):
        raise ContextStoreIdentityError(_INVALID)
    return store_id, version


def read_version(conn):
    """The marker's value, or None when there is no single readable marker.
    For a verification that must neither create nor refuse an identity."""
    if not table_exists(conn, VERSION_TABLE):
        return None
    try:
        return _single_value(conn, VERSION_TABLE, VERSION_KEY)
    except ContextStoreIdentityError:
        return None


def prepare_write(conn) -> None:
    """Bring the database to version 2 inside the caller's write transaction."""
    if "op" not in columns(conn, "audit"):
        conn.execute("ALTER TABLE audit ADD COLUMN op TEXT NOT NULL DEFAULT 'put'")
    if "salt" not in columns(conn, "records"):
        conn.execute("ALTER TABLE records ADD COLUMN salt TEXT")
    conn.execute(f"CREATE TABLE IF NOT EXISTS {TOMBSTONE_TABLE}("
                 "seq INTEGER PRIMARY KEY, tombstone TEXT NOT NULL)")
    conn.execute(f"UPDATE {VERSION_TABLE} SET value=? WHERE key=?", (VERSION_OPS, VERSION_KEY))


def columns(conn, table) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def table_exists(conn, name) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def valid_store_id(value) -> bool:
    return isinstance(value, str) and _STORE_ID.fullmatch(value) is not None


def checked_expected_store_id(value):
    if value is None:
        return None
    if not valid_store_id(value):
        raise ContextStoreIdentityError("expected_store_id is invalid")
    return value


def compare_store_id(actual, expected) -> None:
    if expected is not None and actual != expected:
        raise ContextStoreIdentityError("context store identity mismatch")


def _create_identity(conn) -> str:
    conn.execute(f"CREATE TABLE {VERSION_TABLE}(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute(f"INSERT INTO {VERSION_TABLE}(key,value) VALUES(?,?)",
                 (VERSION_KEY, VERSION_PLAIN))
    conn.execute(f"CREATE TABLE {META_TABLE}(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    store_id = "ctxstore_" + secrets.token_hex(16)
    conn.execute(f"INSERT INTO {META_TABLE}(key,value) VALUES(?,?)", (STORE_ID_KEY, store_id))
    return store_id


def _single_value(conn, table, key):
    try:
        rows = conn.execute(f"SELECT value FROM {table} WHERE key=?", (key,)).fetchall()
    except Exception as exc:
        raise ContextStoreIdentityError(_INVALID) from exc
    if len(rows) != 1:
        raise ContextStoreIdentityError(_INVALID)
    return rows[0][0]
