"""Op-aware reconciliation of the Canon context store's records and audit.

The latest audit row for a key decides what the records table must hold: a key
whose latest row is a put must be present and match that row's digest, and a
key whose latest row is a purge must be absent. A record put back under a
purged key is an integrity failure.

A put row's digest is a salted commitment,
sha256("canon.context.put.v1" || 0x00 || salt || envelope), with the 32-byte
salt kept beside the envelope; a purge deletes both, so the audit row confirms
nothing about what the record held. Rows canon 0.3.0 wrote have no salt and
keep sha256(envelope); they still verify, and a purge counts them as legacy
fingerprints. Every purge row has a tombstone, stored at the row's sequence
number, whose sha256 is the row's digest. A tombstone names the key, a reason
code and its ordinal, and holds no content hash.

The schema holds only what canon creates: the records, audit, tombstone and
identity tables, SQLite's own sequence and statistics tables, and the indexes
SQLite makes for their keys. A trigger, a view, an index or a table from
anywhere else fails integrity before any read, write or purge, since a trigger
could copy each deleted row somewhere a purge does not look.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
from dataclasses import dataclass

from .backends.base import record_key
from .backends.sqlite import (
    GENESIS, OP_PURGE, OP_PUT, audit_rows, chain_hash, last_chain, row_is_chained,
)
from .canonical_json import canonical_json_text
from .context_migrate import (
    META_TABLE, TOMBSTONE_TABLE, VERSION_OPS, VERSION_TABLE, columns, table_exists,
)
from .schema import Record

PUT_TAG = b"canon.context.put.v1"
TOMBSTONE_SCHEMA = "canon.context-tombstone/v1"
_SALT = re.compile(r"[0-9a-f]{64}\Z")
CANON_TABLES = frozenset({"records", "audit", "sqlite_sequence", META_TABLE, VERSION_TABLE,
                          TOMBSTONE_TABLE})


class ContextIntegrityError(ValueError):
    """A stored record no longer matches its audit-bound payload."""


@dataclass(frozen=True)
class LiveRow:
    envelope: str
    record: Record
    salt: str | None
    ordinal: int


@dataclass(frozen=True)
class StoreState:
    live: dict[str, LiveRow]
    purged: dict[str, int]
    length: int

    def purged_ids(self) -> set[str]:
        return {key.split("/", 1)[1] for key in self.purged}


def new_salt() -> str:
    return secrets.token_hex(32)


def put_digest(envelope: str, salt: str | None) -> str:
    """The digest a put row holds: plain for a 0.3.0 row, else the commitment."""
    if salt is None:
        return hashlib.sha256(envelope.encode()).hexdigest()
    if not isinstance(salt, str) or _SALT.fullmatch(salt) is None:
        raise ContextIntegrityError("context record salt is malformed")
    material = PUT_TAG + b"\x00" + bytes.fromhex(salt) + envelope.encode()
    return hashlib.sha256(material).hexdigest()


def tombstone_text(key: str, reason_code: str, ordinal: int) -> str:
    return canonical_json_text({"schema": TOMBSTONE_SCHEMA, "key": key,
                                "reason_code": reason_code, "ordinal": ordinal})


def insert_record(conn, record: Record) -> None:
    """A salted put of one record, with its audit row, in the caller's transaction."""
    envelope, salt, key = record.to_json(), new_salt(), record_key(record)
    digest = put_digest(envelope, salt)
    conn.execute("INSERT INTO records(key,scope,id,kind,envelope,sha256,salt) VALUES(?,?,?,?,?,?,?)",
                 (key, record.scope, record.id, record.kind, envelope, digest, salt))
    _seq, prev = last_chain(conn)
    conn.execute("INSERT INTO audit(key, sha256, prev_hash, chain_hash, op) VALUES(?,?,?,?,?)",
                 (key, digest, prev, chain_hash(prev, OP_PUT, key, digest), OP_PUT))


def append_purge(conn, key: str, reason_code: str) -> int:
    """Append a purge row and its tombstone for `key`; returns the ordinal."""
    seq, prev = last_chain(conn)
    seq += 1
    text = tombstone_text(key, reason_code, seq)
    digest = hashlib.sha256(text.encode()).hexdigest()
    conn.execute(
        "INSERT INTO audit(seq, key, sha256, prev_hash, chain_hash, op) VALUES(?,?,?,?,?,?)",
        (seq, key, digest, prev, chain_hash(prev, OP_PURGE, key, digest), OP_PURGE))
    conn.execute(f"INSERT INTO {TOMBSTONE_TABLE}(seq, tombstone) VALUES(?,?)", (seq, text))
    return seq


def verified_state(conn, version) -> StoreState:
    """Reconcile records, audit and tombstones in the caller's snapshot."""
    check_schema(conn)
    latest, purges, length = _walk_chain(conn)
    _check_tombstones(conn, purges)
    live = _check_records(conn, latest)
    if (purges or any(row.salt is not None for row in live.values())) and version != VERSION_OPS:
        raise ContextIntegrityError("context store version marker is older than its rows")
    purged = {key: seq for key, (op, _sha, seq) in latest.items() if op == OP_PURGE}
    return StoreState(live, purged, length)


def check_schema(conn) -> None:
    """Refuse any schema object canon did not create."""
    for kind, name, table in conn.execute("SELECT type, name, tbl_name FROM sqlite_master"):
        if kind == "table" and (name in CANON_TABLES or name.startswith("sqlite_stat")):
            continue
        if kind == "index" and name.startswith("sqlite_autoindex_") and table in CANON_TABLES:
            continue
        raise ContextIntegrityError("context store schema holds an object canon did not create")


def _walk_chain(conn):
    latest, purges, prev = {}, [], GENESIS
    rows = audit_rows(conn)
    for seq, key, sha, prev_hash, chain, op in rows:
        if not row_is_chained(prev, key, sha, prev_hash, chain, op):
            raise ContextIntegrityError("context audit chain integrity failed")
        prev, latest[key] = chain, (op, sha, seq)
        if op == OP_PURGE:
            purges.append((seq, key, sha))
    return latest, purges, len(rows)


def _check_tombstones(conn, purges) -> None:
    stored = {}
    if table_exists(conn, TOMBSTONE_TABLE):
        stored = dict(conn.execute(f"SELECT seq, tombstone FROM {TOMBSTONE_TABLE}").fetchall())
    if set(stored) != {seq for seq, _key, _sha in purges}:
        raise ContextIntegrityError("context tombstones and purge rows differ")
    for seq, key, sha in purges:
        text = stored[seq]
        if not isinstance(text, str) or hashlib.sha256(text.encode()).hexdigest() != sha \
                or not _is_tombstone(text, key, seq):
            raise ContextIntegrityError("context tombstone does not match its purge row")


def _is_tombstone(text: str, key: str, seq: int) -> bool:
    """Whether `text` is, byte for byte, the tombstone canon writes for this
    key and ordinal: the four fields in canonical form and nothing else."""
    try:
        body = json.loads(text)
    except (ValueError, RecursionError):
        return False
    if not isinstance(body, dict) or set(body) != {"schema", "key", "reason_code", "ordinal"}:
        return False
    reason = body["reason_code"]
    return isinstance(reason, str) and text == tombstone_text(key, reason, seq)


def _check_records(conn, latest) -> dict[str, LiveRow]:
    salt = "salt" if "salt" in columns(conn, "records") else "NULL"
    rows = conn.execute(
        f"SELECT key, envelope, sha256, {salt} FROM records ORDER BY key").fetchall()
    if {row[0] for row in rows} != {key for key, (op, _, _) in latest.items() if op == OP_PUT}:
        raise ContextIntegrityError("context records and audit keys differ")
    live = {}
    for key, envelope, digest, row_salt in rows:
        if not all(isinstance(value, str) for value in (key, envelope, digest)):
            raise ContextIntegrityError("context record contains malformed fields")
        if put_digest(envelope, row_salt) != digest or latest[key][1] != digest:
            raise ContextIntegrityError("stored context payload integrity failed")
        try:
            record = Record.from_json(envelope)
        except Exception as exc:
            raise ContextIntegrityError("context store integrity failed") from exc
        live[key] = LiveRow(envelope, record, row_salt, latest[key][2])
    return live
