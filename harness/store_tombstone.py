"""Removing entities from store.db without breaking its audit chain (7.10, F-22).

Each removed entity gets an audit row of op `forget_entity` whose `sha256` is
the digest of a canonical tombstone (`ref`, `reason_code`), so the chain
formula `sha256(prev + op + ref + sha)` is unchanged and `verify_chain` still
walks it; `verify_records` treats a ref whose latest audit op is
`forget_entity` as expected to be absent. A relation that names a removed
entity is removed with it and gets its own `forget_entity` row, so
`verify_records` does not read it as an attested record that vanished. A ref
whose latest audit row is already `forget_entity` gets no second one, so a
rerun after DB_BUSY does not add duplicates. Rows go in one transaction through
the checked scrub (secure_delete, truncating checkpoints, VACUUM with the
temp store in memory). A v1 receipt's ref is content-derived and its earlier
`put_entity` row keeps the ref and the full digest; that row stays, because
the audit table is append-only, and is counted as a legacy fingerprint. A v2
receipt's ref is random and its digest covers only commitments.
"""
from __future__ import annotations

from pathlib import Path

from .evidence_json import canonical_sha256
from .trace_sqlite_scrub import scrub


def tombstone_digest(ref: str, reason_code: str) -> str:
    return canonical_sha256({"schema": "flywheel.store-tombstone/v1", "ref": ref,
                             "reason_code": reason_code})


def forget_entities(home, eids, reason_code: str) -> dict:
    from .store import _append_audit, _conn
    path = Path(home) / "store.db"
    with _conn(home=home):
        pass  # create the schema if the database is new
    eids = sorted(set(eids))
    legacy = {"count": 0}

    def forget(con, ref: str) -> None:
        latest = con.execute("SELECT op FROM audit WHERE ref=? ORDER BY seq DESC LIMIT 1",
                             (ref,)).fetchone()
        if not latest or latest[0] != "forget_entity":
            _append_audit(con, "forget_entity", ref, tombstone_digest(ref, reason_code))

    def delete(con):
        for eid in eids:
            legacy["count"] += 0 if eid.startswith("tr2_") else min(1, con.execute(
                "SELECT COUNT(*) FROM audit WHERE op='put_entity' AND ref=?",
                (eid,)).fetchone()[0])
            rids = [row[0] for row in con.execute(
                "SELECT rid FROM relations WHERE src=? OR dst=?", (eid, eid))]
            con.execute("DELETE FROM entities WHERE eid=?", (eid,))
            con.execute("DELETE FROM relations WHERE src=? OR dst=?", (eid, eid))
            for rid in rids:
                forget(con, rid)
            forget(con, eid)
    result = scrub(path, delete)
    return {**result, "forgotten": len(eids), "legacy_fingerprint": legacy["count"]}


RECEIPT_KINDS = ("turn-receipt",)


def kinds(home, eids) -> dict:
    """{eid: kind} for the eids that exist in store.db."""
    from .store import _conn
    if not (Path(home) / "store.db").exists():
        return {}
    with _conn(home=home) as c:
        rows = [c.execute("SELECT eid, kind FROM entities WHERE eid=?", (eid,)).fetchone()
                for eid in eids]
    return {row[0]: row[1] for row in rows if row}


def entity_texts(home, eids) -> list[str]:
    """The stored JSON of each entity, for the deletion's scan set."""
    from .store import _conn
    with _conn(home=home) as c:
        rows = [c.execute("SELECT data FROM entities WHERE eid=?", (eid,)).fetchone()
                for eid in eids]
    return [row[0] for row in rows if row]


def live_texts(home, excluding) -> list[str]:
    from .store import _conn
    with _conn(home=home) as c:
        return [row[1] for row in c.execute("SELECT eid, data FROM entities")
                if row[0] not in set(excluding)]
