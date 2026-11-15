"""The byte-level half of a context purge: scrub the SQLite files, then scan them.

The purge connection sets secure_delete, so SQLite overwrites deleted content
with zeros, and keeps temporary storage in memory, so VACUUM writes no
transient copy of the database to the temp directory. After the purge commits,
VACUUM rebuilds the file from the live rows. A database another tool switched
to WAL is checkpointed with TRUNCATE before and after VACUUM, both results are
reported, and a reader that holds the WAL open is reported, since its snapshot
keeps the old pages.

A purge marks the store scrub-pending in the transaction that removes the
rows and clears the mark once VACUUM and the checkpoints have run. A purge
interrupted between its commit and its scrub leaves the mark, and the next
confirmed purge, even one with nothing left to remove, runs the scrub.

The residual scan then reads the database and its -journal, -wal and -shm
files and looks for the purged values in the forms a record envelope stores
them, encoded as the database stores text (UTF-8, or UTF-16 when another tool
created the file that way). Values shorter than 16 bytes are checked only by their rows being gone.
Longer values are cut into 16-byte windows; any run of at least
`min_detectable_bytes` of a purged value left in those files is found, and
occurrences that rows the purge kept still account for are not residue.

Counting those occurrences is where a kept record that quotes the purged text
costs time: every window it quotes is found. A few found windows are counted
one at a time at C speed; past `_DIRECT_WINDOWS` of them, one pass over every
offset of the files and of the kept text counts them all, so the work stays
linear in the bytes read.
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
import time
from pathlib import Path

from .context_migrate import META_TABLE, TOMBSTONE_TABLE, table_exists

WINDOW = 16
SCRUB_MARK = "scrub_pending"
_MAX_NEEDLES = 1_000_000
_MAX_STEPS = 10_000_000
_DIRECT_WINDOWS = 256
_SIDECARS = (("database", ""), ("journal", "-journal"), ("wal", "-wal"), ("shm", "-shm"))
_KEPT_TABLES = ("records", "audit", TOMBSTONE_TABLE)
_CODECS = {"utf-8": "utf-8", "utf-16le": "utf-16-le", "utf-16be": "utf-16-be"}
_IDENTIFIER_KEYS = frozenset({"event_record_id", "source_ids", "responds_to"})
_RECORD_ID = re.compile(r"context-event-[0-9a-f]{64}")
# Never a byte of UTF-8 or of a JSON-escaped form, so no window of a purged
# value can span two kept values joined by it.
_SEPARATOR = b"\xff"


def scrub_connection(path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=10)
    conn.execute("PRAGMA secure_delete=ON")
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn


def scrub_database(conn, busy_retry_seconds: float) -> dict:
    """VACUUM after the purge's commit, with checked checkpoints in WAL mode."""
    mode = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()
    result = {"journal_mode": mode, "vacuum": "done", "wal_checkpoint_before": "not_needed",
              "wal_checkpoint": "not_needed"}
    if mode == "wal":
        result["wal_checkpoint_before"] = _checkpoint(conn, busy_retry_seconds)
    try:
        conn.execute("VACUUM")
    except sqlite3.OperationalError as exc:
        busy = any(word in str(exc).lower() for word in ("locked", "busy"))
        result["vacuum"] = "skipped_database_busy" if busy else "failed"
    if mode == "wal":
        result["wal_checkpoint"] = _checkpoint(conn, busy_retry_seconds)
    return result


def scrub_complete(scrub: dict) -> bool:
    """Whether VACUUM ran and no WAL still holds pages it could not checkpoint."""
    return scrub["vacuum"] == "done" and scrub["wal_checkpoint"] in ("done", "not_needed")


def mark_scrub_pending(conn) -> None:
    """Set the mark inside the purge's own write transaction."""
    conn.execute(f"INSERT OR REPLACE INTO {META_TABLE}(key,value) VALUES(?,?)", (SCRUB_MARK, "1"))


def scrub_pending(conn) -> bool:
    row = conn.execute(f"SELECT 1 FROM {META_TABLE} WHERE key=?", (SCRUB_MARK,)).fetchone()
    return row is not None


def clear_scrub_mark(conn) -> None:
    conn.execute(f"DELETE FROM {META_TABLE} WHERE key=?", (SCRUB_MARK,))
    conn.commit()


def _checkpoint(conn, budget: float) -> str:
    deadline = time.monotonic() + max(0.0, budget)
    while True:
        busy, log, done = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        if busy == 0 and log == done:
            return "done"
        if time.monotonic() >= deadline:
            return "busy"
        time.sleep(0.05)


def scan_values(records) -> tuple[list[str], int]:
    """The distinct purged values a scan looks for, and how many distinct
    values were too short to look for."""
    values, short = set(), set()
    for record in records:
        leaves = list(_leaves(record.data))
        leaves += [record.provenance.source_hash, record.provenance.native_id,
                   record.provenance.session_id]
        for value in leaves:
            if not isinstance(value, str) or not value or _RECORD_ID.fullmatch(value):
                continue
            (short if len(value.encode("utf-8")) < WINDOW else values).add(value)
    return sorted(values), len(short)


def text_codec(conn) -> str:
    """The codec SQLite stores this database's text in. Another tool can create
    the file as UTF-16 before canon first opens it."""
    name = str(conn.execute("PRAGMA encoding").fetchone()[0])
    return _CODECS.get(name.lower(), "utf-8")


def residual_scan(path, values: list[str], live_values: list[bytes], short: int,
                  codec: str = "utf-8") -> dict:
    """Count windows of purged values that the files hold beyond the live rows."""
    files = [(name, Path(str(path) + suffix)) for name, suffix in _SIDECARS
             if Path(str(path) + suffix).exists()]
    blobs = [(name, file.read_bytes()) for name, file in files]
    forms = [form for value in values for form in _forms(value, codec)]
    stride = max(1, math.ceil(sum(len(form) for form in forms) / _MAX_NEEDLES))
    step = _coprime(max(1, math.ceil(sum(len(data) for _, data in blobs) / _MAX_STEPS)), stride)
    needles = {form[i:i + WINDOW] for form in forms for i in _offsets(len(form), stride)}
    found = _found(blobs, needles, step)
    in_files = _counts([data for _, data in blobs], found)
    # A UTF-16 value can hold any byte, so no separator is safe to join on.
    kept_text = [_SEPARATOR.join(live_values)] if codec == "utf-8" else live_values
    in_live = _counts(kept_text, found)
    hits = sum(max(0, in_files[window] - in_live[window]) for window in found)
    kept = sum(min(in_files[window], in_live[window]) for window in found)
    return {"files": [name for name, _ in files], "encoding": codec, "windows": len(needles),
            "min_detectable_bytes": stride * step + WINDOW - 1, "hits": hits,
            "kept_record_matches": kept, "short_values_checked_structurally": short}


def live_values(conn, codec: str = "utf-8") -> list[bytes]:
    """The text of the kept records, the audit rows and the tombstones, for
    subtracting what is kept. Text in any other table counts as residue."""
    out = []
    for table in _KEPT_TABLES:
        if not table_exists(conn, table):
            continue
        for row in conn.execute(f"SELECT * FROM {table}"):
            out.extend(value.encode(codec) for value in row if isinstance(value, str))
    return out


def _counts(blobs: list[bytes], windows: set[bytes]) -> dict[bytes, int]:
    """How often each window occurs in the blobs. The branch depends only on
    how many windows there are, so the files and the kept text, which share
    one window set, are always counted the same way."""
    if len(windows) <= _DIRECT_WINDOWS:
        return {window: sum(blob.count(window) for blob in blobs) for window in windows}
    counts = dict.fromkeys(windows, 0)
    for blob in blobs:
        for i in range(len(blob) - WINDOW + 1):
            window = blob[i:i + WINDOW]
            if window in counts:
                counts[window] += 1
    return counts


def _leaves(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key not in _IDENTIFIER_KEYS:
                yield from _leaves(item)
    elif isinstance(value, list):
        for item in value:
            yield from _leaves(item)
    elif isinstance(value, str):
        yield value


def _forms(value: str, codec: str = "utf-8") -> list[bytes]:
    """The JSON-escaped form a record envelope can store and the raw text, in
    the database's own text encoding."""
    stored = json.dumps(value)[1:-1].encode(codec)
    raw = value.encode(codec)
    return [stored] if raw == stored else [stored, raw]


def _offsets(length: int, stride: int):
    if length < WINDOW:
        return []
    starts = list(range(0, length - WINDOW + 1, stride))
    if starts[-1] != length - WINDOW:
        starts.append(length - WINDOW)
    return starts


def _coprime(step: int, stride: int) -> int:
    while math.gcd(step, stride) != 1:
        step += 1
    return step


def _found(blobs, needles, step) -> set[bytes]:
    found = set()
    for _name, data in blobs:
        for i in range(0, len(data) - WINDOW + 1, step):
            window = data[i:i + WINDOW]
            if window in needles:
                found.add(window)
    return found
