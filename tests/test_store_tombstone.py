"""F-22, N-26, EN-B4: an entity removed from store.db leaves an audit row of
op `forget_entity`, so the chain still verifies and verify_records expects
the row to be absent. After the checked scrub the removed text is in no
database file; without the scrub it stays in a free page. A v1 receipt's
earlier audit rows remain and are counted as legacy fingerprints."""
import sqlite3

import pytest

from harness import store
from harness.store_tombstone import forget_entities
from harness.trace_residual_scan import Needles, scan_paths
from trace_enc_fakes import long_canary, plain_delete

CANARY = long_canary(seed=31, size=12 * 1024)


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    return tmp_path


def _v1_receipt(home):
    return store.put_entity("turn-receipt", {
        "schema": "flywheel.turn-receipt/v1", "prompt_sha256": "a" * 64,
        "degraded": [{"url": "https://example.invalid/x", "reason": CANARY}]}, home=home)["eid"]


def _db_files(home):
    return [home / name for name in ("store.db", "store.db-wal", "store.db-shm",
                                     "store.db-journal")]


def test_forgetting_keeps_both_verifiers_green(home):
    eid = _v1_receipt(home)
    kept = store.put_entity("note", {"text": "kept note"}, home=home)["eid"]
    result = forget_entities(home, [eid], "owner_request")
    assert result["state"] == "SCRUBBED" and result["forgotten"] == 1
    assert store.verify_chain(home=home)["ok"]
    assert store.verify_records(home=home)["ok"]
    assert store.get_entity(eid, home=home) is None and store.get_entity(kept, home=home)
    audit = store.latest_audit_for_ref(eid, home=home)
    assert audit["op"] == "forget_entity" and audit["chain_hash_ok"]


def test_the_scrub_removes_the_text_from_every_database_file(home):
    eid = _v1_receipt(home)
    forget_entities(home, [eid], "owner_request")
    assert scan_paths(_db_files(home), Needles.build([CANARY]))["total"] == 0


def test_control_without_the_scrub_the_text_stays_in_a_free_page(home):
    """The DELETE runs with secure_delete and auto_vacuum set off, since
    either one would clear the freed page the scan has to find."""
    eid = _v1_receipt(home)
    plain_delete(home / "store.db", "DELETE FROM entities WHERE eid = ?", (eid,))
    assert scan_paths(_db_files(home), Needles.build([CANARY]))["total"] > 0


def test_a_v1_row_is_counted_as_a_legacy_fingerprint_and_v2_is_not(home):
    v1 = _v1_receipt(home)
    v2 = store.put_entity("turn-receipt", {"schema": "flywheel.turn-receipt/v2"},
                          eid="tr2_" + "1" * 24, home=home)["eid"]
    result = forget_entities(home, [v1, v2], "owner_request")
    assert result["legacy_fingerprint"] == 1


def test_a_forgotten_row_that_reappears_is_reported(home):
    eid = _v1_receipt(home)
    row = sqlite3.connect(home / "store.db").execute(
        "SELECT eid, kind, project, data, sha256, created FROM entities WHERE eid=?",
        (eid,)).fetchone()
    forget_entities(home, [eid], "owner_request")
    con = sqlite3.connect(home / "store.db")
    con.execute("INSERT INTO entities VALUES (?,?,?,?,?,?)", row)
    con.commit()
    con.close()
    broken = store.verify_records(home=home)["broken"]
    assert [b["reason"] for b in broken] == ["forgotten record is present"]


def test_forgetting_an_entity_with_relations_keeps_verify_records_green(home):
    """S19: a relation naming the entity goes with it and gets its own
    forget_entity row, so verify_records does not read it as a deletion."""
    eid = _v1_receipt(home)
    other = store.put_entity("note", {"text": "related note"}, home=home)["eid"]
    store.put_relation(eid, other, "cites")
    forget_entities(home, [eid], "owner_request")
    assert store.verify_records(home=home)["ok"], store.verify_records(home=home)
    assert store.verify_chain(home=home)["ok"]


def test_a_rerun_adds_no_duplicate_forget_rows(home):
    """A DB_BUSY retry forgets the same ids again; the audit gets one row each."""
    eid = _v1_receipt(home)
    forget_entities(home, [eid], "owner_request")
    forget_entities(home, [eid], "owner_request")
    con = sqlite3.connect(home / "store.db")
    rows = con.execute("SELECT COUNT(*) FROM audit WHERE op='forget_entity' AND ref=?",
                       (eid,)).fetchone()[0]
    con.close()
    assert rows == 1


def test_only_turn_receipts_can_be_selected_for_deletion(home):
    from harness.trace_delete_plan import PlanError, make_plan
    note = store.put_entity("note", {"text": "not a trace"}, home=home)["eid"]
    with pytest.raises(PlanError) as refused:
        make_plan(home, "owner_" + "a" * 32, {"receipt_eids": [note]}, save=False)
    assert refused.value.code == "INVALID_SELECTION"
    with pytest.raises(PlanError) as missing:
        make_plan(home, "owner_" + "a" * 32, {"receipt_eids": ["f" * 24]}, save=False)
    assert missing.value.code == "NOT_FOUND"
