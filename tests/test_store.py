"""The store must be content-addressed and tamper-evident: identical content
re-derives one hash, the audit chain verifies, and any row rewrite breaks it
at that seq. Isolated per test via FLYWHEEL_HOME."""

import sqlite3

import pytest

from harness import store


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))


def test_entity_roundtrip_and_content_address():
    r1 = store.put_entity("service", {"name": "gateway", "port": 8799},
                          project="flywheel")
    got = store.get_entity(r1["eid"])
    assert got["data"]["port"] == 8799
    assert got["sha256"] == r1["sha256"]
    # Same content, same id -> same hash (content-addressed).
    r2 = store.put_entity("service", {"name": "gateway", "port": 8799},
                          project="flywheel", eid=r1["eid"])
    assert r2["sha256"] == r1["sha256"]


def test_query_and_relations():
    a = store.put_entity("module", {"n": "a"}, project="p")
    b = store.put_entity("module", {"n": "b"}, project="p")
    store.put_relation(a["eid"], b["eid"], "imports", project="p")
    mods = store.query_entities(kind="module", project="p")
    assert len(mods) == 2
    rels = store.relations_of(a["eid"])
    assert len(rels) == 1 and rels[0]["kind"] == "imports"


def test_audit_chain_verifies():
    for i in range(5):
        store.put_entity("t", {"i": i})
    v = store.verify_chain()
    assert v["ok"] is True
    assert v["checked"] == 5


def test_tampering_a_record_breaks_the_chain():
    for i in range(4):
        store.put_entity("t", {"i": i})
    # Rewrite one audit row's payload directly, as a tamper would.
    path = store._db_path()
    con = sqlite3.connect(str(path))
    con.execute("UPDATE audit SET sha256='tampered' WHERE seq=2")
    con.commit()
    con.close()
    v = store.verify_chain()
    assert v["ok"] is False
    assert v["broken_at"] == 2


def test_verify_records_catches_a_directly_edited_entity():
    """verify_chain proves the ledger consistent, but a tamper that edits
    entities.data while leaving entities.sha256 and every audit row intact
    passes it. verify_records re-derives the content hash and catches it."""
    e = store.put_entity("doc", {"body": "original"})
    assert store.verify_records()["ok"] is True
    path = store._db_path()
    con = sqlite3.connect(str(path))
    con.execute("UPDATE entities SET data=? WHERE eid=?",
                ('{"body": "tampered"}', e["eid"]))
    con.commit()
    con.close()
    # the audit chain still verifies (it never re-reads the record)...
    assert store.verify_chain()["ok"] is True
    # ...but the record check catches the content divergence
    r = store.verify_records()
    assert r["ok"] is False
    assert e["eid"] in [b["ref"] for b in r["broken"]]


def test_verify_records_clean_on_an_untouched_store():
    for i in range(3):
        store.put_entity("t", {"i": i})
    store.put_relation("t", "u", "rel")
    r = store.verify_records()
    assert r["ok"] is True and r["broken"] == []


def test_stats_and_empty_kind_refused():
    store.put_entity("a", {})
    store.put_entity("a", {"x": 1})
    store.put_entity("b", {})
    s = store.stats()
    assert s["entities"] == 3
    assert s["kinds"]["a"] == 2
    assert "error" in store.put_entity("", {})
