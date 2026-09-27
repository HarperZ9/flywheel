"""SP-14, N-29: the checked SQLite scrub. An open reader keeps the WAL, so the
scrub ends DELETE_PENDING with DB_BUSY instead of claiming success; the second
checkpoint empties the WAL; the pages a pending scrub freed hold no deleted
text whatever SQLite's build default for secure_delete. The VACUUM temp-file
check, watched while VACUUM runs, is in test_trace_sqlite_scrub_tempfile.py."""
import os
import sqlite3

import pytest

from harness import trace_sqlite_scrub
from harness.trace_residual_scan import Needles, scan_paths
from harness.trace_sqlite_scrub import scrub
from trace_enc_fakes import long_canary


def _db(path, rows=50):
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, body TEXT)")
    con.executemany("INSERT INTO t(body) VALUES (?)", [("row %d " % i * 40,) for i in range(rows)])
    con.commit()
    con.close()


def _delete_half(con):
    con.execute("DELETE FROM t WHERE id % 2 = 0")


def test_an_open_reader_makes_the_scrub_pending_with_db_busy(tmp_path):
    db = tmp_path / "busy.db"
    _db(db)
    reader = sqlite3.connect(db)
    reader.execute("BEGIN")
    reader.execute("SELECT count(*) FROM t").fetchone()
    try:
        result = scrub(db, _delete_half, retry_s=0.3)
    finally:
        reader.close()
    assert result["state"] == "DELETE_PENDING" and result["reason"] == "DB_BUSY"
    assert result["checkpoint"][0] == 1


def test_a_clean_scrub_empties_the_wal_twice_and_keeps_live_rows(tmp_path):
    db = tmp_path / "clean.db"
    _db(db)
    result = scrub(db, _delete_half)
    assert result["state"] == "SCRUBBED" and result["checkpoint"] == [0, 0, 0]
    wal = db.with_name(db.name + "-wal")
    assert not wal.exists() or wal.stat().st_size == 0
    con = sqlite3.connect(db)
    assert con.execute("SELECT count(*) FROM t").fetchone()[0] == 25
    assert con.execute("PRAGMA freelist_count").fetchone()[0] == 0
    con.close()


def test_a_failing_delete_rolls_back_and_raises(tmp_path):
    db = tmp_path / "rollback.db"
    _db(db)

    def broken(con):
        con.execute("DELETE FROM t WHERE id = 1")
        raise RuntimeError("injected")
    with pytest.raises(RuntimeError):
        scrub(db, broken)
    con = sqlite3.connect(db)
    assert con.execute("SELECT count(*) FROM t").fetchone()[0] == 50
    con.close()


def test_a_rollback_journal_database_is_scrubbed_too(tmp_path):
    db = tmp_path / "journal.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, body TEXT)")
    con.execute("INSERT INTO t(body) VALUES ('x')")
    con.commit()
    con.close()
    result = scrub(db, lambda c: c.execute("DELETE FROM t"))
    assert result["state"] == "SCRUBBED" and result["checkpoint"] is None
    assert not os.path.exists(str(db) + "-journal")


def test_a_pending_scrub_leaves_no_text_in_the_pages_it_freed(tmp_path, monkeypatch):
    """A scrub that stops DB_BUSY never reaches VACUUM, so secure_delete is
    what keeps the deleted text out of the pages the DELETE freed once a later
    checkpoint copies them into the database. secure_delete is a build-time
    default, ON in the Debian and Ubuntu SQLite and OFF in python.org's
    Windows build; the scrub's connection starts with it OFF here on every
    platform, so the scrub has to set it itself."""
    canary = long_canary(seed=23)
    db = tmp_path / "pending.db"
    con = sqlite3.connect(db)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, body TEXT)")
    con.executemany("INSERT INTO t(body) VALUES (?)", [(canary,), ("kept row",)])
    con.commit()
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()
    reader = sqlite3.connect(db)
    reader.execute("BEGIN")
    reader.execute("SELECT count(*) FROM t").fetchone()
    real = sqlite3.connect

    def starts_off(*args, **kwargs):
        opened = real(*args, **kwargs)
        opened.execute("PRAGMA secure_delete=OFF")
        return opened
    monkeypatch.setattr(trace_sqlite_scrub.sqlite3, "connect", starts_off)
    try:
        result = scrub(db, lambda c: c.execute("DELETE FROM t WHERE id = 1"), retry_s=0.3)
    finally:
        monkeypatch.undo()
        reader.close()
    assert result["state"] == "DELETE_PENDING" and result["reason"] == "DB_BUSY"
    con = sqlite3.connect(db)
    assert con.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone() == (0, 0, 0)
    assert con.execute("SELECT body FROM t").fetchall() == [("kept row",)]
    con.close()
    paths = [db, *(db.with_name(db.name + s) for s in ("-wal", "-shm", "-journal"))]
    assert scan_paths(paths, Needles.build([canary]))["total"] == 0
