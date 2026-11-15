"""A context put stores a hiding commitment instead of a plain digest.

A new row keeps sha256("canon.context.put.v1" || 0x00 || salt || envelope) with
a fresh 32-byte salt beside its envelope, and the audit row keeps the same
value. A purge deletes the row and its salt, so what the audit keeps no longer
confirms a guess of what the row held. Rows written by 0.3.0 keep their plain
digests, still verify, and are counted as residue when purged.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
import sys

import pytest

import canon.backends.sqlite as sqlite_backend
import canon.canonical_json as canonical_json
import canon.context_audit as context_audit
import canon.context_purge as context_purge
import canon.context_records as context_records
from canon.context_purge import select
from canon.context_store import ContextIntegrityError, ContextStore

from ._context_fixtures import PROJECT, WORKSPACE, db_files, prompt_payload, rows, short_canary
from ._legacy_context_0_3_0 import create_legacy_store, legacy_health

_TAG = b"canon.context.put.v1\x00"


def _execute(db, sql, params=()):
    con = sqlite3.connect(str(db))
    con.execute(sql, params)
    con.commit()
    con.close()


def _version(db):
    return rows(db, "SELECT value FROM context_store_identity_version")[0][0]


def test_a_new_put_audit_row_holds_no_plain_envelope_digest(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    ContextStore(db).ingest(prompt_payload("turn-1", "Salted prompt text"))
    records = rows(db, "SELECT key, envelope, sha256, salt FROM records")
    audit = dict(rows(db, "SELECT key, sha256 FROM audit"))
    data = b"".join(path.read_bytes() for path in db_files(db))

    assert len(records) == 3
    assert len({salt for *_, salt in records}) == 3
    for key, envelope, digest, salt in records:
        plain = hashlib.sha256(envelope.encode()).hexdigest()
        assert re.fullmatch(r"[0-9a-f]{64}", salt)
        assert digest == hashlib.sha256(_TAG + bytes.fromhex(salt) + envelope.encode()).hexdigest()
        assert audit[key] == digest != plain
        assert plain[:12].encode() not in data
        assert bytes.fromhex(plain)[:6] not in data


def test_verification_recomputes_the_digest_from_the_salt(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    store = ContextStore(db)
    store.ingest(prompt_payload("turn-1", "Salted prompt text"))
    key, salt = rows(db, "SELECT key, salt FROM records ORDER BY key LIMIT 1")[0]
    flipped = ("1" if salt[0] == "0" else "0") + salt[1:]

    for bad in (flipped, "not-a-salt", None):
        _execute(db, "UPDATE records SET salt=? WHERE key=?", (bad, key))
        assert store.verify_chain()["ok"] is False
        with pytest.raises(ContextIntegrityError):
            store.query(WORKSPACE, PROJECT, "salted")

    _execute(db, "UPDATE records SET salt=? WHERE key=?", (salt, key))
    assert store.verify_chain() == {"ok": True, "length": 3}


def test_the_first_salted_put_raises_the_identity_version(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    store = ContextStore(db)
    store.identity()
    store.query(WORKSPACE, PROJECT, "nothing stored yet")
    assert _version(db) == "1"
    assert legacy_health(db)["ok"] is True

    store.ingest(prompt_payload("turn-1", "Salted prompt text"))

    assert _version(db) == "2"
    assert legacy_health(db) == {"ok": False, "configured": True,
                                 "reason": "context store identity invalid"}


def test_a_version_marker_older_than_its_rows_fails_integrity(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    store = ContextStore(db)
    store.ingest(prompt_payload("turn-1", "Salted prompt text"))

    _execute(db, "UPDATE context_store_identity_version SET value='1'")

    assert store.verify_chain()["ok"] is False
    with pytest.raises(ContextIntegrityError):
        store.query(WORKSPACE, PROJECT, "salted")


def test_rows_written_by_0_3_0_verify_beside_salted_rows(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    legacy = create_legacy_store(db, [prompt_payload("turn-1", "Legacy prompt text")])[0]
    store = ContextStore(db)
    fresh = store.ingest(prompt_payload("turn-2", "Salted prompt text"))["event_record_id"]

    salts = dict(rows(db, "SELECT id, salt FROM records"))
    assert salts[legacy] is None
    assert re.fullmatch(r"[0-9a-f]{64}", salts[fresh])
    assert store.verify_chain() == {"ok": True, "length": 6}
    for record_id in (legacy, fresh):
        assert store.get(WORKSPACE, PROJECT, record_id)["status"] == "found_in_searched_sources"


class _DigestSpy:
    """Stands in for `hashlib` inside the modules that write context digests
    and records every (input, output) pair, so the test can ask which digests
    were computed over the canary."""

    def __init__(self) -> None:
        self.calls: list[tuple[bytes, str]] = []

    def sha256(self, data: bytes = b"") -> "_SpyHash":
        return _SpyHash(self, data)


class _SpyHash:
    def __init__(self, spy: _DigestSpy, data: bytes) -> None:
        self._spy, self._data, self._hash = spy, bytearray(data), hashlib.sha256(data)

    def update(self, data: bytes) -> None:
        self._data += data
        self._hash.update(data)

    def hexdigest(self) -> str:
        out = self._hash.hexdigest()
        self._spy.calls.append((bytes(self._data), out))
        return out

    def digest(self) -> bytes:
        return bytes.fromhex(self.hexdigest())


def _hashing_modules() -> list:
    """Every loaded canon module that computes digests through `hashlib`, so a
    digest added to any of them later is spied on too."""
    loaded = [module for name, module in sorted(sys.modules.items())
              if name.startswith("canon.") and getattr(module, "hashlib", None) is hashlib]
    for required in (context_records, context_audit, context_purge, sqlite_backend,
                     canonical_json):
        assert required in loaded
    return loaded


def test_no_digest_of_purged_content_survives_but_commitments_whose_salt_is_gone(
        tmp_path, monkeypatch) -> None:
    spy = _DigestSpy()
    for module in _hashing_modules():
        monkeypatch.setattr(module, "hashlib", spy)
    canary = short_canary()
    db = tmp_path / "context.sqlite"
    store = ContextStore(db)
    prompt = store.ingest(prompt_payload("turn-3", f"Prompt {canary}"))["event_record_id"]
    store.ingest(prompt_payload("turn-4", "A kept prompt about the weather"))
    recorded = {out: data for data, out in spy.calls if canary.encode() in data}
    before = b"".join(path.read_bytes() for path in db_files(db))
    assert recorded and any(out.encode() in before for out in recorded)

    selection = select(event_id=prompt)
    plan = store.purge_plan(WORKSPACE, PROJECT, selection)
    store.purge(WORKSPACE, PROJECT, selection, confirm_plan_sha256=plan["plan_sha256"])

    after = b"".join(path.read_bytes() for path in db_files(db))
    for out, data in recorded.items():
        present = out[:12].encode() in after or bytes.fromhex(out)[:6] in after
        if not present:
            continue
        assert data.startswith(_TAG), "a plain digest of purged content survived"
        salt = data[len(_TAG):len(_TAG) + 32]
        assert salt.hex().encode() not in after and salt not in after
