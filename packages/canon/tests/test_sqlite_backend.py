"""SqliteBackend: the zero-drop reference store with a re-verifiable audit chain.

sqlite is the store the round-trip proof measures the others against: every
kind round-trips field-identical, it declares no drops, and every write appends
to a hash-chained ledger the owner can re-walk. The chain must verify clean
after honest writes and must fail closed the moment a ledger row is altered.
"""
from __future__ import annotations

import sqlite3

import pytest

from canon.backends import SqliteBackend, record_key
from canon.schema import KINDS

from ._helpers import RECORD_FILES, load_dict, load_record


@pytest.mark.parametrize("kind", list(RECORD_FILES))
def test_roundtrip_is_field_identical(tmp_path, kind: str) -> None:
    be = SqliteBackend(tmp_path / "s.sqlite")
    rec = load_record(RECORD_FILES[kind])
    be.put(rec)
    got = be.get(record_key(rec))
    assert got is not None
    assert got.to_dict() == load_dict(RECORD_FILES[kind])


def test_declares_no_drops(tmp_path) -> None:
    assert SqliteBackend(tmp_path / "s.sqlite").declared_drops() == frozenset()


def test_supports_every_kind(tmp_path) -> None:
    assert SqliteBackend(tmp_path / "s.sqlite").supported_kinds() == frozenset(KINDS)


def test_temporal_history_survives(tmp_path) -> None:
    be = SqliteBackend(tmp_path / "s.sqlite")
    rec = load_record(RECORD_FILES["synthesized-persona-l3"])
    be.put(rec)
    got = be.get(record_key(rec))
    assert got.temporal is not None
    assert got.temporal.supersedes == "persona-operator-0003"


def test_get_missing_returns_none(tmp_path) -> None:
    assert SqliteBackend(tmp_path / "s.sqlite").get("global/nope") is None


def test_records_are_returned_sorted_by_key(tmp_path) -> None:
    be = SqliteBackend(tmp_path / "s.sqlite")
    for kind in RECORD_FILES:
        be.put(load_record(RECORD_FILES[kind]))
    keys = [record_key(r) for r in be.records()]
    assert keys == sorted(keys)
    assert len(keys) == len(RECORD_FILES)


def test_verify_chain_ok_after_writes(tmp_path) -> None:
    be = SqliteBackend(tmp_path / "s.sqlite")
    for kind in RECORD_FILES:
        be.put(load_record(RECORD_FILES[kind]))
    result = be.verify_chain()
    assert result == {"ok": True, "length": len(RECORD_FILES)}


def test_reput_upserts_record_but_appends_audit(tmp_path) -> None:
    be = SqliteBackend(tmp_path / "s.sqlite")
    rec = load_record(RECORD_FILES["adr-decision"])
    be.put(rec)
    be.put(rec)
    # One record row (upsert on key), two audit rows (append-only ledger).
    assert len(be.records()) == 1
    assert be.verify_chain() == {"ok": True, "length": 2}


def test_verify_chain_fails_closed_on_tamper(tmp_path) -> None:
    path = tmp_path / "s.sqlite"
    be = SqliteBackend(path)
    for kind in RECORD_FILES:
        be.put(load_record(RECORD_FILES[kind]))
    assert be.verify_chain()["ok"] is True
    # Alter one ledger row's recorded sha; the recomputation must not match.
    con = sqlite3.connect(str(path))
    con.execute("UPDATE audit SET sha256='deadbeef' WHERE seq=1")
    con.commit()
    con.close()
    assert be.verify_chain()["ok"] is False


def test_empty_store_verifies_as_empty_chain(tmp_path) -> None:
    assert SqliteBackend(tmp_path / "s.sqlite").verify_chain() == {"ok": True, "length": 0}
