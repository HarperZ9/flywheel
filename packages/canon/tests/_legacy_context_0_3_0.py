"""The context store as canon 0.3.0 reads and writes it, frozen for tests.

The identity check and the chain walk below are copied from
`src/canon/context_store.py` at release 0.3.0 (commit 078758b), with only the
`self` parameter removed. `legacy_health` follows the 0.3.0
`canon.context.health` tool: the identity first, then the chain. The tests use
it to ask what an older reader does with a database this version wrote, and to
build a database the way 0.3.0 left it: no `op` column, no `salt` column, and
plain sha256 digests of each envelope in the audit rows.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import sqlite3
from pathlib import Path

from canon.backends.base import record_key
from canon.context_records import make_records
from canon.schema import Record

_META_TABLE = "context_store_meta"
_VERSION_TABLE = "context_store_identity_version"
_STORE_ID_KEY = "store_id"
_VERSION_KEY = "schema_version"
_IDENTITY_VERSION = "1"
_STORE_ID = re.compile(r"ctxstore_[0-9a-f]{32}\Z")


class LegacyIdentityError(ValueError):
    pass


class LegacyIntegrityError(ValueError):
    pass


def create_legacy_store(db: Path, payloads: list[dict]) -> list[str]:
    """Write `payloads` as 0.3.0 would: its schema, its identity marker and its
    unsalted digests. Returns the event record ids."""
    con = sqlite3.connect(str(db))
    try:
        con.executescript(
            "CREATE TABLE IF NOT EXISTS records("
            " key TEXT PRIMARY KEY, scope TEXT, id TEXT, kind TEXT,"
            " envelope TEXT, sha256 TEXT);"
            "CREATE TABLE IF NOT EXISTS audit("
            " seq INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT,"
            " sha256 TEXT, prev_hash TEXT, chain_hash TEXT);")
        con.execute("BEGIN IMMEDIATE")
        _store_id(con, create=True)
        ids = [_legacy_ingest(con, payload) for payload in payloads]
        con.commit()
        return ids
    finally:
        con.close()


def _legacy_ingest(con, payload: dict) -> str:
    records = make_records(payload)
    for record in records:
        envelope = record.to_json()
        digest = hashlib.sha256(envelope.encode()).hexdigest()
        key = record_key(record)
        con.execute("INSERT INTO records(key,scope,id,kind,envelope,sha256) VALUES(?,?,?,?,?,?)",
                    (key, record.scope, record.id, record.kind, envelope, digest))
        row = con.execute("SELECT chain_hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        prev = row[0] if row else "0" * 64
        chain = hashlib.sha256((prev + key + digest).encode()).hexdigest()
        con.execute("INSERT INTO audit(key, sha256, prev_hash, chain_hash) VALUES(?,?,?,?)",
                    (key, digest, prev, chain))
    return records[0].id


def legacy_health(db: Path) -> dict:
    """What `canon.context.health` in 0.3.0 reports for this database."""
    con = sqlite3.connect(str(db), timeout=10)
    try:
        con.execute("BEGIN IMMEDIATE")
        store_id = _store_id(con, create=True)
        con.commit()
        con.execute("BEGIN")
        length = con.execute("SELECT COUNT(*) FROM audit").fetchone()[0]
        try:
            _verified_rows(con)
            audit = {"ok": True, "length": length}
        except LegacyIntegrityError:
            audit = {"ok": False, "length": length}
        return {"ok": audit["ok"], "configured": True, "audit": audit, "store_id": store_id}
    except LegacyIdentityError as exc:
        return {"ok": False, "configured": True, "reason": str(exc)}
    finally:
        con.close()


def _store_id(conn, *, create):
    meta_exists = _table_exists(conn, _META_TABLE)
    version_exists = _table_exists(conn, _VERSION_TABLE)
    if not meta_exists:
        if version_exists:
            raise LegacyIdentityError("context store identity invalid")
        if not create:
            raise LegacyIdentityError("context store identity missing")
        conn.execute(f"CREATE TABLE {_VERSION_TABLE}(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute(f"INSERT INTO {_VERSION_TABLE}(key,value) VALUES(?,?)",
                     (_VERSION_KEY, _IDENTITY_VERSION))
        conn.execute(f"CREATE TABLE {_META_TABLE}(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        store_id = "ctxstore_" + secrets.token_hex(16)
        conn.execute(f"INSERT INTO {_META_TABLE}(key,value) VALUES(?,?)", (_STORE_ID_KEY, store_id))
        return store_id
    if not version_exists:
        raise LegacyIdentityError("context store identity invalid")
    try:
        versions = conn.execute(
            f"SELECT value FROM {_VERSION_TABLE} WHERE key=?",
            (_VERSION_KEY,),
        ).fetchall()
    except Exception as exc:
        raise LegacyIdentityError("context store identity invalid") from exc
    if versions != [(_IDENTITY_VERSION,)]:
        raise LegacyIdentityError("context store identity invalid")
    try:
        rows = conn.execute(
            f"SELECT value FROM {_META_TABLE} WHERE key=?",
            (_STORE_ID_KEY,),
        ).fetchall()
    except Exception as exc:
        raise LegacyIdentityError("context store identity invalid") from exc
    if len(rows) != 1 or not _valid_store_id(rows[0][0]):
        raise LegacyIdentityError("context store identity invalid")
    return rows[0][0]


def _verified_rows(conn):
    """Reconcile payloads and audit in one snapshot, including missing rows."""
    previous, latest = "0" * 64, {}
    for key, digest, prev_hash, chain in conn.execute(
            "SELECT key,sha256,prev_hash,chain_hash FROM audit ORDER BY seq"):
        if not all(isinstance(value, str) for value in (key, digest, prev_hash, chain)):
            raise LegacyIntegrityError("context audit contains malformed fields")
        expected = hashlib.sha256((previous + key + digest).encode()).hexdigest()
        if previous != prev_hash or expected != chain:
            raise LegacyIntegrityError("context audit chain integrity failed")
        previous, latest[key] = chain, digest
    rows = conn.execute("SELECT key,envelope,sha256 FROM records ORDER BY key").fetchall()
    if {row[0] for row in rows} != set(latest):
        raise LegacyIntegrityError("context records and audit keys differ")
    for key, envelope, digest in rows:
        if not all(isinstance(value, str) for value in (key, envelope, digest)):
            raise LegacyIntegrityError("context record contains malformed fields")
        if hashlib.sha256(envelope.encode()).hexdigest() != digest or latest[key] != digest:
            raise LegacyIntegrityError("stored context payload integrity failed")
        try:
            Record.from_json(envelope)
        except Exception as exc:
            raise LegacyIntegrityError("context store integrity failed") from exc
    return rows


def _valid_store_id(value):
    return isinstance(value, str) and _STORE_ID.fullmatch(value) is not None


def _table_exists(conn, name):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (name,)).fetchone() is not None
