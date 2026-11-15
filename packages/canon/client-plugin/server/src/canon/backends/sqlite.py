"""backends/sqlite.py -- SqliteBackend: the faithful, audited reference store.

A single SQLite file holds every record verbatim (its canonical to_dict() as
JSON) keyed by (scope, id), and every write is appended to a hash-chained audit
ledger the owner can re-verify -- the same chain discipline flywheel's store
keeps, ported to canon's own table. It holds every kind, loses no field, and
carries the audit chain a FilesBackend drops, so its declared_drops() is empty.
This is the zero-drop backend the round-trip proof (R0) measures the others
against.

Each audit row names its operation. A put keeps the original step,
sha256(prev + key + sha), so a ledger of puts verifies the same under every
reader. A purge, which only the context store writes, binds its op name with a
unit separator. A database written before ops existed has no `op` column and
reads as all puts; nothing here adds the column, so reading changes no schema.
"""
from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from canon.schema import KINDS, Record

from .base import flatten_for_drops, guard_put, record_key

GENESIS = "0" * 64
OP_PUT = "put"
OP_PURGE = "purge"
AUDIT_OPS = (OP_PUT, OP_PURGE)


def chain_hash(prev: str, op: str, key: str, sha: str) -> str:
    """One step of the audit chain for a row with this op."""
    if op == OP_PUT:
        material = prev + key + sha
    elif op == OP_PURGE:
        material = prev + OP_PURGE + "\x1f" + key + sha
    else:
        raise ValueError(f"unknown audit op {op!r}")
    return hashlib.sha256(material.encode()).hexdigest()


def audit_rows(c: sqlite3.Connection) -> list[tuple]:
    """(seq, key, sha256, prev_hash, chain_hash, op) in chain order. A ledger
    without an `op` column holds puts only."""
    columns = {row[1] for row in c.execute("PRAGMA table_info(audit)")}
    op = "op" if "op" in columns else "'put'"
    return c.execute(
        f"SELECT seq, key, sha256, prev_hash, chain_hash, {op} FROM audit ORDER BY seq"
    ).fetchall()


def last_chain(c: sqlite3.Connection) -> tuple[int, str]:
    """(seq, chain_hash) of the newest audit row, or (0, GENESIS)."""
    row = c.execute("SELECT seq, chain_hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
    return (row[0], row[1]) if row else (0, GENESIS)


def row_is_chained(prev: str, key: object, sha: object, prev_hash: object,
                   chain: object, op: object) -> bool:
    """Whether one audit row is well formed and follows `prev`."""
    if not all(isinstance(value, str) for value in (key, sha, prev_hash, chain, op)):
        return False
    return op in AUDIT_OPS and prev_hash == prev and chain == chain_hash(prev, op, key, sha)


class SqliteBackend:
    name = "sqlite"

    def __init__(self, path: "str | Path") -> None:
        self._path = str(path)
        self._init()

    def supported_kinds(self) -> frozenset[str]:
        return frozenset(KINDS)

    def declared_drops(self) -> frozenset[str]:
        return frozenset()

    def flatten(self, record: Record) -> Record:
        return flatten_for_drops(record, self.declared_drops())

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        c = sqlite3.connect(self._path, timeout=10)
        try:
            yield c
            c.commit()
        finally:
            c.close()

    def _init(self) -> None:
        with self._conn() as c:
            c.executescript(
                "CREATE TABLE IF NOT EXISTS records("
                " key TEXT PRIMARY KEY, scope TEXT, id TEXT, kind TEXT,"
                " envelope TEXT, sha256 TEXT, salt TEXT);"
                "CREATE TABLE IF NOT EXISTS audit("
                " seq INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT,"
                " sha256 TEXT, prev_hash TEXT, chain_hash TEXT,"
                " op TEXT NOT NULL DEFAULT 'put');")

    def put(self, record: Record) -> None:
        guard_put(self, record)
        key = record_key(record)
        envelope = record.to_json()
        sha = hashlib.sha256(envelope.encode()).hexdigest()
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO records"
                "(key, scope, id, kind, envelope, sha256) VALUES(?,?,?,?,?,?)",
                (key, record.scope, record.id, record.kind, envelope, sha))
            self._append_audit(c, key, sha)

    def _append_audit(self, c: sqlite3.Connection, key: str, sha: str) -> None:
        """Append a put row. The column list is the original one, so a ledger
        written before ops existed takes the row unchanged."""
        _seq, prev = last_chain(c)
        chain = chain_hash(prev, OP_PUT, key, sha)
        c.execute(
            "INSERT INTO audit(key, sha256, prev_hash, chain_hash)"
            " VALUES(?,?,?,?)", (key, sha, prev, chain))

    def get(self, key: str) -> Record | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT envelope FROM records WHERE key=?", (key,)).fetchone()
        return Record.from_json(row[0]) if row else None

    def records(self) -> list[Record]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT envelope FROM records ORDER BY key").fetchall()
        return [Record.from_json(r[0]) for r in rows]

    def verify_chain(self) -> dict:
        """Walk the audit ledger, recomputing each row's chain hash from the
        prior under the row's op. Returns {ok, length}; ok is False at the
        first mismatch, unknown op or malformed row."""
        with self._conn() as c:
            rows = audit_rows(c)
        prev = GENESIS
        for _seq, key, sha, prev_hash, chain, op in rows:
            if not row_is_chained(prev, key, sha, prev_hash, chain, op):
                return {"ok": False, "length": len(rows)}
            prev = chain
        return {"ok": True, "length": len(rows)}
