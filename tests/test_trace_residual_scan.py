"""EN-C9, I4 (c): the residual scan finds a long canary's 16-byte windows in
every encoding the design names, including inside a SQLite overflow page a
plain DELETE left behind, finds none after the scrub, and does not count text
that rows the deletion keeps still hold."""
import base64
import json
import sqlite3
import unicodedata

import pytest

from harness.trace_residual_scan import Needles, scan_bytes, scan_paths
from harness.trace_sqlite_scrub import scrub
from trace_enc_fakes import long_canary


@pytest.fixture
def canary():
    return long_canary(seed=11)


def _forms(text):
    raw = text.encode("utf-8")
    yield "utf8", raw
    yield "utf16", text.encode("utf-16-le")
    yield "json", json.dumps(text).encode("utf-8")
    for shift in range(3):
        yield f"base64-{shift}", base64.b64encode(b"x" * shift + raw)
    yield "nfc", unicodedata.normalize("NFC", text).encode("utf-8")
    yield "nfd", unicodedata.normalize("NFD", text).encode("utf-8")


def test_every_form_of_the_canary_is_found(canary):
    needles = Needles.build([canary])
    for name, blob in _forms(canary):
        framed = b"\x00" * 7 + blob[1000:4000] + b"\xff" * 5
        assert scan_bytes(framed, needles) > 0, name


def test_unrelated_bytes_give_no_hit(canary):
    needles = Needles.build([canary])
    assert scan_bytes(long_canary(seed=99).encode(), needles) == 0


def test_a_short_value_is_found_whole_and_flagged_structural():
    short = "SHORT-CANARY-0123456789ab"
    needles = Needles.build([short])
    assert scan_bytes(b"prefix " + short.encode() + b" suffix", needles) == 1
    tiny = Needles.build(["tiny"])
    assert tiny.structural_only == 1 and scan_bytes(b"tiny tiny", tiny) == 0


def _db_with_deleted_canary(path, canary, *, scrubbed):
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, body TEXT)")
    con.execute("INSERT INTO t(body) VALUES (?)", (canary,))
    con.execute("INSERT INTO t(body) VALUES ('kept row')")
    con.commit()
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()
    if scrubbed:
        return scrub(path, lambda c: c.execute("DELETE FROM t WHERE id = 1"))
    con = sqlite3.connect(path)
    con.execute("DELETE FROM t WHERE id = 1")
    con.commit()
    con.close()
    return None


def test_a_plain_delete_leaves_the_canary_in_free_pages(tmp_path, canary):
    db = tmp_path / "plain.db"
    _db_with_deleted_canary(db, canary, scrubbed=False)
    hits = scan_paths([db, db.with_name(db.name + "-wal")], Needles.build([canary]))
    assert hits["total"] > 0


def test_the_scrub_leaves_nothing_behind(tmp_path, canary):
    db = tmp_path / "scrubbed.db"
    result = _db_with_deleted_canary(db, canary, scrubbed=True)
    assert result["state"] == "SCRUBBED", result
    paths = [db, *(db.with_name(db.name + s) for s in ("-wal", "-shm", "-journal"))]
    assert scan_paths(paths, Needles.build([canary]))["total"] == 0
    con = sqlite3.connect(db)
    assert con.execute("SELECT body FROM t").fetchall() == [("kept row",)]
    con.close()


def test_text_the_kept_rows_still_hold_is_subtracted(canary):
    deleted = canary[:2000]
    kept = canary[:2000] + " and more"
    needles = Needles.build([deleted], live=[kept])
    assert scan_bytes(kept.encode(), needles) == 0
    assert needles.subtracted > 0


def test_the_report_names_files_by_label_and_never_quotes(tmp_path, canary):
    target = tmp_path / "store.db"
    target.write_bytes(canary.encode())
    report = scan_paths([target], Needles.build([canary]), labels={target: "S7 store.db"})
    assert report["per_file"] == {"S7 store.db": report["total"]} and report["total"] > 0
    assert canary[:32] not in json.dumps(report)
