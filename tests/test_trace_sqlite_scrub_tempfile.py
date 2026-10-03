"""SP-14: VACUUM must not write a transient copy of the database (deleted rows
included) into the temporary directory, even for a moment. The directory is
watched while VACUUM runs, with a small page cache so the default temp store
would spill to a file; the control shows the watch sees that file."""
import sqlite3
import threading

import pytest

from harness import trace_sqlite_scrub
from harness.trace_sqlite_scrub import scrub


def _db(path, rows=6000):
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, body TEXT)")
    con.execute("CREATE INDEX t_body ON t(body)")
    con.executemany("INSERT INTO t(body) VALUES (?)", [("row %d " % i * 60,) for i in range(rows)])
    con.commit()
    con.close()


def _watched_scrub(tmp_path, monkeypatch, *, drop_memory_store: bool) -> set:
    scratch = tmp_path / "scanned-temp"
    scratch.mkdir()
    for name in ("TMP", "TEMP", "SQLITE_TMPDIR"):
        monkeypatch.setenv(name, str(scratch))
    seen: set = set()

    class Spy(sqlite3.Connection):
        def execute(self, sql, *args):
            if drop_memory_store and sql == "PRAGMA temp_store=MEMORY":
                sql = "PRAGMA temp_store=DEFAULT"
            if sql != "VACUUM":
                return super().execute(sql, *args)
            super().execute("PRAGMA cache_size=5")
            done = threading.Event()

            def watch():
                while not done.is_set():
                    seen.update(p.name for p in scratch.iterdir())
            watcher = threading.Thread(target=watch)
            watcher.start()
            try:
                return super().execute(sql, *args)
            finally:
                done.set()
                watcher.join()
    real = sqlite3.connect
    monkeypatch.setattr(trace_sqlite_scrub.sqlite3, "connect",
                        lambda *a, **k: real(*a, factory=Spy, **k))
    db = tmp_path / "vacuum.db"
    _db(db)
    assert scrub(db, lambda con: con.execute("DELETE FROM t WHERE id % 2 = 0"))["state"] == \
        "SCRUBBED"
    return seen


def test_no_transient_file_appears_while_vacuum_runs(tmp_path, monkeypatch):
    assert _watched_scrub(tmp_path, monkeypatch, drop_memory_store=False) == set()


def test_control_the_default_temp_store_is_seen_by_the_watch(tmp_path, monkeypatch):
    seen = _watched_scrub(tmp_path, monkeypatch, drop_memory_store=True)
    if not seen:
        pytest.skip("this SQLite build kept the VACUUM copy in memory; the watch is unproven")
    assert any(name.startswith("etilqs_") for name in seen)
