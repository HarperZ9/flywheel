"""The index file: one SQLite database, FTS5 for text, plain tables for the rest.

Unit ids are content addresses: sha256 over source, offset, kind and text,
cut to 24 hex characters. The same input always yields the same ids.
"""

import hashlib
import json
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources(
  path TEXT PRIMARY KEY, scope TEXT, session TEXT, head_sha TEXT,
  done_offset INTEGER, size INTEGER, units INTEGER, skipped INTEGER);
CREATE TABLE IF NOT EXISTS units(
  id TEXT PRIMARY KEY, scope TEXT, session TEXT, source TEXT, ts TEXT,
  offset INTEGER, kind TEXT, score REAL, text TEXT, meta TEXT, feats TEXT,
  simhash INTEGER, dup_of TEXT, state TEXT);
CREATE INDEX IF NOT EXISTS units_state ON units(state);
CREATE TABLE IF NOT EXISTS skipped(
  source TEXT, offset INTEGER, kind TEXT, reason TEXT);
CREATE TABLE IF NOT EXISTS lines(
  h INTEGER PRIMARY KEY, sessions INTEGER, first_unit TEXT, last_session TEXT);
CREATE TABLE IF NOT EXISTS bands(b INTEGER, unit TEXT);
CREATE INDEX IF NOT EXISTS bands_b ON bands(b);
CREATE TABLE IF NOT EXISTS entities(entity TEXT, unit TEXT);
CREATE INDEX IF NOT EXISTS entities_e ON entities(entity);
CREATE TABLE IF NOT EXISTS cards(
  id TEXT PRIMARY KEY, unit TEXT, scope TEXT, session TEXT, ts TEXT,
  source TEXT, offset INTEGER, kind TEXT, quote TEXT, entities TEXT);
CREATE TABLE IF NOT EXISTS calls(tuid TEXT PRIMARY KEY, unit TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(
  uid UNINDEXED, text, ents, tokenize="unicode61 tokenchars '-_'");
CREATE VIRTUAL TABLE IF NOT EXISTS fts_vocab USING fts5vocab(fts, row);
"""


def open_db(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.executescript("PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;")
    con.executescript(SCHEMA)
    return con


def unit_id(source: str, offset: int, kind: str, text: str, seq: int) -> str:
    h = hashlib.sha256(f"{source}\0{offset}\0{seq}\0{kind}\0{text}".encode("utf-8", "replace"))
    return h.hexdigest()[:24]


def source_state(con: sqlite3.Connection, path: str) -> tuple[str, int] | None:
    row = con.execute("SELECT head_sha, done_offset FROM sources WHERE path=?",
                      (path,)).fetchone()
    return (row[0], row[1]) if row else None


def drop_source(con: sqlite3.Connection, path: str) -> None:
    """Forget a source whose head changed: it was rewritten, not appended."""
    ids = [r[0] for r in con.execute("SELECT id FROM units WHERE source=?", (path,))]
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        marks = ",".join("?" * len(chunk))
        for table, col in (("fts", "uid"), ("entities", "unit"), ("bands", "unit"),
                           ("cards", "unit")):
            con.execute(f"DELETE FROM {table} WHERE {col} IN ({marks})", chunk)
    con.execute("DELETE FROM units WHERE source=?", (path,))
    con.execute("DELETE FROM skipped WHERE source=?", (path,))
    con.execute("DELETE FROM sources WHERE path=?", (path,))


def put_unit(con: sqlite3.Connection, row: dict) -> None:
    con.execute(
        "INSERT OR IGNORE INTO units VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (row["id"], row["scope"], row["session"], row["source"], row["ts"],
         row["offset"], row["kind"], row["score"], row["text"],
         json.dumps(row["meta"], sort_keys=True), json.dumps(row["feats"], sort_keys=True),
         0, None, "new"))


def put_skip(con: sqlite3.Connection, source: str, offset: int, kind: str,
             reason: str) -> None:
    con.execute("INSERT INTO skipped VALUES(?,?,?,?)", (source, offset, kind, reason))


def save_source(con: sqlite3.Connection, path: str, scope: str, session: str,
                head_sha: str, done: int, size: int, units: int, skipped: int) -> None:
    con.execute(
        "INSERT INTO sources VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET "
        "head_sha=excluded.head_sha, done_offset=excluded.done_offset, size=excluded.size, "
        "units=sources.units+excluded.units, skipped=sources.skipped+excluded.skipped",
        (path, scope, session, head_sha, done, size, units, skipped))
