"""store.py -- the verifiable enterprise substrate (stdlib sqlite3, zero-dep).

A persistent entity/relation store where every record is content-addressed
and every write is appended to a hash-chained audit ledger the owner can
re-verify. This is the backbone under projects, memory, and the knowledge
graph: it is not bigger than an enterprise data platform, it is
self-verifying -- a tampered record or a rewritten history is detectable by
walking the chain, which those platforms do not hand the customer.

Entities and relations carry a `project` scope so one store holds many
workspaces. The DB lives at FLYWHEEL_HOME/store.db; a fresh connection per
call keeps it correct under the threaded gateway. Values are the caller's;
nothing here reaches outside the file."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

_GENESIS = "0" * 64


def _db_path() -> Path:
    home = os.environ.get("FLYWHEEL_HOME") or os.path.join(
        os.path.expanduser("~"), ".flywheel")
    return Path(home) / "store.db"


@contextmanager
def _conn():
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(path), timeout=10)
    try:
        c.execute("PRAGMA journal_mode=WAL")
        _init(c)
        yield c
        c.commit()
    finally:
        c.close()


def _init(c: sqlite3.Connection) -> None:
    c.executescript("""
    CREATE TABLE IF NOT EXISTS entities(
        eid TEXT PRIMARY KEY, kind TEXT, project TEXT,
        data TEXT, sha256 TEXT, created REAL);
    CREATE TABLE IF NOT EXISTS relations(
        rid TEXT PRIMARY KEY, src TEXT, dst TEXT, kind TEXT,
        project TEXT, sha256 TEXT, created REAL);
    CREATE TABLE IF NOT EXISTS audit(
        seq INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, op TEXT,
        ref TEXT, sha256 TEXT, prev_hash TEXT, chain_hash TEXT);
    CREATE INDEX IF NOT EXISTS ix_ent_kind ON entities(kind, project);
    CREATE INDEX IF NOT EXISTS ix_rel_src ON relations(src);
    """)


def _sha(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def _append_audit(c: sqlite3.Connection, op: str, ref: str, sha: str) -> str:
    row = c.execute("SELECT chain_hash FROM audit ORDER BY seq DESC "
                    "LIMIT 1").fetchone()
    prev = row[0] if row else _GENESIS
    chain = hashlib.sha256((prev + op + ref + sha).encode()).hexdigest()
    c.execute("INSERT INTO audit(ts, op, ref, sha256, prev_hash, chain_hash) "
              "VALUES(?,?,?,?,?,?)", (time.time(), op, ref, sha, prev, chain))
    return chain


def put_entity(kind: str, data: dict, *, project: str = "",
               eid: "str | None" = None) -> dict:
    """Store an entity. The receipt is its content hash; the same content
    under the same id re-derives the same hash."""
    kind = (kind or "").strip()
    if not kind:
        return {"error": "provide a non-empty 'kind'"}
    sha = _sha({"kind": kind, "project": project, "data": data})
    eid = (eid or sha[:24]).strip()
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO entities"
                  "(eid, kind, project, data, sha256, created) "
                  "VALUES(?,?,?,?,?,?)",
                  (eid, kind, project, json.dumps(data, default=str), sha,
                   time.time()))
        chain = _append_audit(c, "put_entity", eid, sha)
    return {"eid": eid, "kind": kind, "sha256": sha, "chain_hash": chain}


def get_entity(eid: str) -> "dict | None":
    with _conn() as c:
        row = c.execute("SELECT eid, kind, project, data, sha256, created "
                        "FROM entities WHERE eid=?", (eid,)).fetchone()
    if not row:
        return None
    return {"eid": row[0], "kind": row[1], "project": row[2],
            "data": json.loads(row[3]), "sha256": row[4], "created": row[5]}


def query_entities(*, kind: "str | None" = None, project: "str | None" = None,
                   limit: int = 200, offset: int = 0) -> list:
    clauses, params = [], []
    if kind:
        clauses.append("kind=?")
        params.append(kind)
    if project:
        clauses.append("project=?")
        params.append(project)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with _conn() as c:
        rows = c.execute(
            "SELECT eid, kind, project, sha256, created FROM entities" + where +
            " ORDER BY created DESC LIMIT ? OFFSET ?",
            params + [max(1, min(limit, 1000)), max(0, offset)]
        ).fetchall()
    return [{"eid": r[0], "kind": r[1], "project": r[2], "sha256": r[3],
             "created": r[4]} for r in rows]


def query_all_entities(*, kind: "str | None" = None,
                       project: "str | None" = None,
                       chunk: int = 500) -> list:
    """Every matching entity, paged until exhausted, so a caller does not
    silently compute over only the newest page. Newest first."""
    out, offset = [], 0
    while True:
        page = query_entities(kind=kind, project=project, limit=chunk,
                              offset=offset)
        out.extend(page)
        if len(page) < chunk:
            return out
        offset += chunk


def put_relation(src: str, dst: str, kind: str, *, project: str = "") -> dict:
    if not (src and dst and kind):
        return {"error": "provide 'src', 'dst', and 'kind'"}
    sha = _sha({"src": src, "dst": dst, "kind": kind, "project": project})
    rid = sha[:24]
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO relations"
                  "(rid, src, dst, kind, project, sha256, created) "
                  "VALUES(?,?,?,?,?,?,?)",
                  (rid, src, dst, kind, project, sha, time.time()))
        chain = _append_audit(c, "put_relation", rid, sha)
    return {"rid": rid, "sha256": sha, "chain_hash": chain}


def relations_of(eid: str) -> list:
    with _conn() as c:
        rows = c.execute("SELECT rid, src, dst, kind, project FROM relations "
                         "WHERE src=? OR dst=?", (eid, eid)).fetchall()
    return [{"rid": r[0], "src": r[1], "dst": r[2], "kind": r[3],
             "project": r[4]} for r in rows]


def audit_tail(n: int = 50) -> list:
    with _conn() as c:
        rows = c.execute("SELECT seq, ts, op, ref, sha256, chain_hash "
                         "FROM audit ORDER BY seq DESC LIMIT ?",
                         (max(1, min(n, 500)),)).fetchall()
    return [{"seq": r[0], "ts": r[1], "op": r[2], "ref": r[3],
             "sha256": r[4], "chain_hash": r[5]} for r in rows]


def verify_chain() -> dict:
    """Walk the audit ledger recomputing every chain hash. A tampered row or
    a deleted/inserted one breaks the recomputation at that seq."""
    with _conn() as c:
        rows = c.execute("SELECT seq, op, ref, sha256, prev_hash, chain_hash "
                         "FROM audit ORDER BY seq ASC").fetchall()
    prev = _GENESIS
    for seq, op, ref, sha, prev_hash, chain in rows:
        if prev_hash != prev:
            return {"ok": False, "checked": seq, "broken_at": seq,
                    "reason": "prev_hash discontinuity"}
        recomputed = hashlib.sha256((prev + op + ref + sha).encode()).hexdigest()
        if recomputed != chain:
            return {"ok": False, "checked": seq, "broken_at": seq,
                    "reason": "chain_hash mismatch"}
        prev = chain
    return {"ok": True, "checked": len(rows), "head": prev}


def verify_records() -> dict:
    """Re-check that stored records still match their content hash. The
    audit chain (verify_chain) proves the LEDGER was not rewritten; this
    proves the RECORDS the ledger attests were not edited underneath it.
    A directly-edited entity or relation, sha256 column left intact,
    passes verify_chain but is caught here: the content is re-hashed and
    compared to both the stored column and the audit row that committed
    it."""
    broken = []
    with _conn() as c:
        committed = {}
        for op, ref, sha in c.execute(
                "SELECT op, ref, sha256 FROM audit ORDER BY seq ASC"):
            committed[(op, ref)] = sha       # latest wins
        for eid, kind, project, data, sha in c.execute(
                "SELECT eid, kind, project, data, sha256 FROM entities"):
            recomputed = _sha({"kind": kind, "project": project,
                               "data": json.loads(data)})
            audit_sha = committed.get(("put_entity", eid))
            if recomputed != sha or (audit_sha is not None
                                     and audit_sha != sha):
                broken.append({"ref": eid, "table": "entities",
                               "reason": "content no longer matches its "
                                         "committed hash"})
        for rid, src, dst, kind, project, sha in c.execute(
                "SELECT rid, src, dst, kind, project, sha256 FROM relations"):
            recomputed = _sha({"src": src, "dst": dst, "kind": kind,
                               "project": project})
            audit_sha = committed.get(("put_relation", rid))
            if recomputed != sha or (audit_sha is not None
                                     and audit_sha != sha):
                broken.append({"ref": rid, "table": "relations",
                               "reason": "content no longer matches its "
                                         "committed hash"})
    return {"ok": not broken, "checked": len(committed), "broken": broken,
            "note": "re-derives each record's content hash and compares to "
                    "the column and the audit row; catches a tamper that "
                    "verify_chain cannot see"}


def stats() -> dict:
    with _conn() as c:
        ent = c.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        rel = c.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
        aud = c.execute("SELECT COUNT(*) FROM audit").fetchone()[0]
        kinds = c.execute("SELECT kind, COUNT(*) FROM entities GROUP BY kind "
                          "ORDER BY 2 DESC LIMIT 12").fetchall()
        projects = c.execute("SELECT DISTINCT project FROM entities "
                             "WHERE project<>''").fetchall()
    return {"schema": "flywheel.store/v1", "entities": ent, "relations": rel,
            "audit_entries": aud,
            "kinds": {k: n for k, n in kinds},
            "projects": [p[0] for p in projects],
            "note": "every record content-addressed; the audit ledger is "
                    "hash-chained and owner-verifiable"}
