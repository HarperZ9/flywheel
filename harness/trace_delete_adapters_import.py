"""Deletion of imported client transcripts (7.10, FW-10c, I19).

An imported item is its encrypted chunks, manifest and redaction index under
`state/imports/v1/owners/<owner>/<client>/<item_ref>/`, plus its row in the
encrypted index. Before anything is removed, each deleted source is added to
the exclusion list (its keyed source identity, its byte length and a keyed
digest of those bytes), so a crash after the exclusion and before removal
leaves a state where the next import still skips it, and a resumed session
that extends the deleted prefix is skipped as PREVIOUSLY_DELETED_SESSION.
The client's own transcript stays; the report names it and the command that
removes it there.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

_REF = re.compile(r"imp_[0-9a-f]{32}\Z")


def valid_ref(value) -> bool:
    return type(value) is str and _REF.fullmatch(value) is not None


def _store(home: Path, owner: str):
    from .trace_import_items import ImportStore
    return ImportStore(home, owner)


def entries_for(home: Path, owner: str, refs=(), session=None) -> tuple[list[dict], set]:
    """(entries, clients) for the selected imported items."""
    store, state = _store(home, owner), home / "state"
    rows = store.index()
    wanted = set(refs)
    if session:
        wanted |= {r["item_ref"] for r in rows if r["client"] == session["client"]
                   and store.manifest(r["item_ref"]).get("session_id") == session["session_id"]}
    out, clients = [], set()
    for row in rows:
        if row["item_ref"] in wanted:
            folder = store.base / row["client"] / row["item_ref"]
            out.append({"store": "IM", "item": row["item_ref"],
                        "rel": folder.relative_to(state).as_posix()})
            clients.add(row["client"])
    if set(refs) - {e["item"] for e in out}:
        return [], set()
    return out, clients


def exclude(home: Path, owner: str, entries: list[dict]) -> int:
    """Add each deleted source to the exclusion list, once."""
    from .trace_custody_lock import custody_lock
    from .trace_import_exclusion import entries as listed, list_path
    store = _store(home, owner)
    rows = {r["item_ref"]: r for r in store.index()}
    have = {(e["source"], e["n"], e["prefix"]) for e in listed(home, owner)}
    added = 0
    target = list_path(home, owner)
    with custody_lock(home / "state"):
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "ab") as stream:
            for entry in (e for e in entries if e["store"] == "IM"):
                row = rows.get(entry["item"])
                key = (row["source_ref"], row["bytes"], row["content_ref"]) if row else None
                if key and key not in have:
                    stream.write(json.dumps({"source": key[0], "n": key[1], "prefix": key[2]},
                                            sort_keys=True).encode() + b"\n")
                    have.add(key)
                    added += 1
            stream.flush()
            os.fsync(stream.fileno())
    return added


def drop_index_rows(home: Path, owner: str, entries: list[dict]) -> None:
    from .trace_custody_lock import custody_lock
    gone = {e["item"] for e in entries if e["store"] == "IM"}
    if not gone:
        return
    store = _store(home, owner)
    with custody_lock(home / "state"):
        store._write_index([r for r in store.index() if r["item_ref"] not in gone])


def indexed(home: Path, owner: str, entries: list[dict]) -> bool:
    """Whether any deleted import still has a row in the encrypted index."""
    gone = {e["item"] for e in entries if e["store"] == "IM"}
    return bool(gone) and any(r["item_ref"] in gone for r in _store(home, owner).index())
