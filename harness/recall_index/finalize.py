"""Second stage over staged units only: boilerplate, near-duplicates, cards.

This stage never reads transcripts. It strips lines that recur across many
sessions (keeping them where they first appeared), collapses near-duplicate
units with SimHash bands, writes the FTS rows and entity postings, and
makes one card per author ruling, KEEP THIS tag or decision.
"""

import json

from harness.recall_index.simhash import bands, hamming, line_hash, simhash, MAX_HAMMING

BOILER_SESSIONS = 5
SIMHASH_MIN_CHARS = 160
CARD_CHARS = 280
_M64 = (1 << 64) - 1


def _signed(h: int) -> int:
    """SQLite INTEGER is signed 64-bit; store the same bits signed."""
    return h - (1 << 64) if h >> 63 else h


def _strip_boiler(con, uid: str, text: str) -> str:
    kept = []
    for raw in text.splitlines():
        if len(raw.strip()) >= 24:
            row = con.execute("SELECT sessions, first_unit FROM lines WHERE h=?",
                              (line_hash(raw),)).fetchone()
            if row and row[0] >= BOILER_SESSIONS and row[1] != uid:
                continue
        kept.append(raw)
    return "\n".join(kept).strip()


def _near_dup(con, uid: str, h: int) -> str | None:
    seen = set()
    for b in bands(h):
        for (other,) in con.execute("SELECT unit FROM bands WHERE b=? LIMIT 200", (b,)):
            if other in seen or other == uid:
                continue
            seen.add(other)
            row = con.execute("SELECT simhash FROM units WHERE id=?", (other,)).fetchone()
            if row and hamming(row[0] & _M64, h) <= MAX_HAMMING:
                return other
    return None


def _card(con, row: tuple, feats: dict, text: str) -> None:
    uid, scope, session, source, ts, offset, kind = row[:7]
    quote = None
    if feats.get("quotes"):
        quote = feats["quotes"][0]
    elif feats.get("keep") or (kind == "author" and feats.get("ruling")):
        quote = text
    elif feats.get("decisions", 0) >= 2:
        quote = text
    if not quote:
        return
    quote = quote[:CARD_CHARS]
    con.execute("INSERT OR IGNORE INTO cards VALUES(?,?,?,?,?,?,?,?,?,?)",
                ("c" + uid, uid, scope, session, ts, source, offset, kind, quote,
                 json.dumps(feats.get("entities", [])[:12])))


def _finish_unit(con, row: tuple) -> str:
    uid, text, feats_json = row[0], row[8], row[10]
    feats = json.loads(feats_json)
    text = _strip_boiler(con, uid, text)
    if not text:
        con.execute("UPDATE units SET state='boiler' WHERE id=?", (uid,))
        return "boiler"
    h = simhash(text) if len(text) >= SIMHASH_MIN_CHARS else 0
    dup = _near_dup(con, uid, h) if h else None
    if dup:
        con.execute("UPDATE units SET state='dup', dup_of=?, simhash=? WHERE id=?",
                    (dup, _signed(h), uid))
        return "dup"
    ents = feats.get("entities", [])
    con.execute("UPDATE units SET state='live', text=?, simhash=? WHERE id=?", (text, _signed(h), uid))
    con.execute("INSERT INTO fts(uid, text, ents) VALUES(?,?,?)", (uid, text, " ".join(ents)))
    con.executemany("INSERT INTO entities VALUES(?,?)", [(e.lower(), uid) for e in ents])
    if h:
        con.executemany("INSERT INTO bands VALUES(?,?)", [(b, uid) for b in bands(h)])
    _card(con, row, feats, text)
    return "live"


def finalize(con, batch: int = 2000) -> dict:
    """Finish every staged unit, oldest first. Safe to run repeatedly."""
    counts = {"live": 0, "dup": 0, "boiler": 0}
    while True:
        rows = con.execute("SELECT * FROM units WHERE state='new' ORDER BY ts, offset "
                           "LIMIT ?", (batch,)).fetchall()
        if not rows:
            break
        for row in rows:
            counts[_finish_unit(con, row)] += 1
        con.commit()
    counts["cards"] = con.execute("SELECT count(*) FROM cards").fetchone()[0]
    return counts

