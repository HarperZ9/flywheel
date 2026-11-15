"""The generic SQLite backend, which stores authored blocks, verifies as it did.

Only the context store writes purge rows and salted commitments. What this
backend writes is still a put row with a plain sha256 of the envelope, chained
by sha256(prev + key + sha), so canon 0.3.0 verifies it; a database 0.3.0 wrote
verifies here with no schema change; and the op-aware walk fails closed on an
op it does not know or a malformed row instead of raising.
"""
from __future__ import annotations

import hashlib
import sqlite3

from canon.backends import SqliteBackend, record_key

from ._helpers import RECORD_FILES, load_record
from ._context_fixtures import rows

_RECORDS = [load_record(path) for path in RECORD_FILES.values()]


def _old_verify(db) -> bool:
    """The chain walk of SqliteBackend.verify_chain in 0.3.0."""
    prev = "0" * 64
    for key, sha, prev_hash, chain in rows(
            db, "SELECT key, sha256, prev_hash, chain_hash FROM audit ORDER BY seq"):
        if prev_hash != prev or chain != hashlib.sha256((prev + key + sha).encode()).hexdigest():
            return False
        prev = chain
    return True


def _old_blocks_db(db, records) -> None:
    """A blocks database as 0.3.0's SqliteBackend.put leaves it."""
    con = sqlite3.connect(str(db))
    con.executescript(
        "CREATE TABLE records(key TEXT PRIMARY KEY, scope TEXT, id TEXT, kind TEXT,"
        " envelope TEXT, sha256 TEXT);"
        "CREATE TABLE audit(seq INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT,"
        " sha256 TEXT, prev_hash TEXT, chain_hash TEXT);")
    prev = "0" * 64
    for record in records:
        envelope = record.to_json()
        sha = hashlib.sha256(envelope.encode()).hexdigest()
        key = record_key(record)
        chain = hashlib.sha256((prev + key + sha).encode()).hexdigest()
        con.execute("INSERT OR REPLACE INTO records VALUES(?,?,?,?,?,?)",
                    (key, record.scope, record.id, record.kind, envelope, sha))
        con.execute("INSERT INTO audit(key, sha256, prev_hash, chain_hash) VALUES(?,?,?,?)",
                    (key, sha, prev, chain))
        prev = chain
    con.commit()
    con.close()


def _columns(db, table):
    return {row[1] for row in rows(db, f"PRAGMA table_info({table})")}


def test_a_blocks_database_written_by_0_3_0_verifies_with_no_schema_change(tmp_path) -> None:
    db = tmp_path / "blocks.sqlite"
    _old_blocks_db(db, _RECORDS)

    backend = SqliteBackend(db)

    assert backend.verify_chain() == {"ok": True, "length": len(_RECORDS)}
    assert [record_key(r) for r in backend.records()] == sorted(record_key(r) for r in _RECORDS)
    assert "op" not in _columns(db, "audit")
    assert "salt" not in _columns(db, "records")


def test_puts_keep_the_plain_digest_and_the_original_chain_formula(tmp_path) -> None:
    db = tmp_path / "blocks.sqlite"
    backend = SqliteBackend(db)
    for record in _RECORDS:
        backend.put(record)

    envelopes = dict(rows(db, "SELECT key, envelope FROM records"))
    for key, sha, op in rows(db, "SELECT key, sha256, op FROM audit"):
        assert sha == hashlib.sha256(envelopes[key].encode()).hexdigest()
        assert op == "put"
    assert {salt for (salt,) in rows(db, "SELECT salt FROM records")} == {None}
    assert _old_verify(db) is True
    assert backend.verify_chain() == {"ok": True, "length": len(_RECORDS)}


def test_new_puts_on_a_0_3_0_blocks_database_stay_readable_by_0_3_0(tmp_path) -> None:
    db = tmp_path / "blocks.sqlite"
    _old_blocks_db(db, _RECORDS[:2])
    backend = SqliteBackend(db)

    backend.put(_RECORDS[2])

    assert backend.verify_chain() == {"ok": True, "length": 3}
    assert _old_verify(db) is True
    assert "op" not in _columns(db, "audit")


def test_an_unknown_op_or_a_malformed_row_fails_the_chain_closed(tmp_path) -> None:
    db = tmp_path / "blocks.sqlite"
    backend = SqliteBackend(db)
    for record in _RECORDS[:2]:
        backend.put(record)

    con = sqlite3.connect(str(db))
    con.execute("UPDATE audit SET op='erase' WHERE seq=1")
    con.commit()
    assert backend.verify_chain() == {"ok": False, "length": 2}

    con.execute("UPDATE audit SET op='put', key=NULL WHERE seq=1")
    con.commit()
    con.close()
    assert backend.verify_chain() == {"ok": False, "length": 2}
