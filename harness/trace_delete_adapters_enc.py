"""Deletion closures for the encrypted stores (7.10, FW-07a).

Each adapter turns a selection into entries `{store, item, rel}`: the item
whose key is destroyed and the path, relative to the state root, that is
removed. A gateway trace is its record and checkpoint folder (store S1). A
captured turn brings its pending prompt record, which holds the prompt's
salt and, with content capture on, its text; the capture snapshots its
freeze envelope names (S8b); and its v2 receipt in `store.db`, which the
plaintext adapter removes. Refs come from file headers and encrypted
records; no path is taken from a request.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

_TRACE = re.compile(r"agt_[0-9a-f]{32}\Z")
_TURN = re.compile(r"turn_[0-9a-f]{32}\Z")


def _first_record_ref(directory: Path) -> str | None:
    """The trace ref, from the encrypted header or the plaintext record."""
    from .trace_enc import is_encrypted, parse
    try:
        raw = (directory / "00000000.json").read_bytes()
        return parse(raw)[0]["item"] if is_encrypted(raw) else json.loads(raw).get("trace_ref")
    except (OSError, ValueError, KeyError, AttributeError):
        return None


def trace_entries(state: Path, owner: str, trace_ref: str) -> list[dict]:
    base = state / "gateway-agent-traces" / "v1" / "owners" / owner
    for directory in sorted(base.iterdir()) if base.is_dir() else []:
        if directory.is_dir() and _first_record_ref(directory) == trace_ref:
            return [{"store": "S1", "item": trace_ref,
                     "rel": directory.relative_to(state).as_posix(),
                     "operation": directory.name}]
    return []


def _turn_store(home: Path, owner: str):
    from .trace_turn_store import TurnStore
    return TurnStore(home, owner)


def turn_entries(home: Path, owner: str, turn_ref: str) -> tuple[list[dict], list[str]]:
    """(entries, receipt eids) for one captured turn and what goes with it."""
    store, state = _turn_store(home, owner), home / "state"
    path = next(iter(store.base.glob(f"*/*/{turn_ref}.enc")), None)
    if path is None:
        return [], []
    doc = store.read_turn(turn_ref)
    entries = [{"store": "CT", "item": turn_ref, "rel": path.relative_to(state).as_posix()}]
    for pending_path, pending in store._pendings(doc.get("session_ref")):
        if turn_ref in pending.get("turn_refs", []):
            entries.append({"store": "CT", "item": pending_path.stem,
                            "rel": pending_path.relative_to(state).as_posix()})
            entries += _snapshots(state, owner, pending.get("freeze"))
    entries += _snapshots(state, owner, doc.get("freeze"))
    return entries, [doc["receipt_eid"]] if doc.get("receipt_eid") else []


def _snapshots(state: Path, owner: str, envelope) -> list[dict]:
    base = state / "capture-snapshots" / "v1" / "owners" / owner
    out = []
    for source in (envelope or {}).get("sources", []):
        path = base / f"{source['snap_ref']}.enc"
        if path.exists():
            out.append({"store": "S8b", "item": source["snap_ref"],
                        "rel": path.relative_to(state).as_posix()})
    return out


def session_turns(home: Path, owner: str, client: str, session_id: str) -> list[str]:
    store = _turn_store(home, owner)
    session_ref = store._session_ref(client, session_id)
    return [t["turn_ref"] for t in store.turns()
            if store.read_turn(t["turn_ref"]).get("session_ref") == session_ref]


def turn_sessions(home: Path, owner: str, turn_refs) -> set[str]:
    """Keyed session refs of these captured turns, leaving out turns that had
    no session id (their ref would match every session-less source)."""
    from .trace_turn_receipt import keyed_ref
    store = _turn_store(home, owner)
    refs = set()
    for ref in turn_refs:
        try:
            doc = store.read_turn(ref)
        except FileNotFoundError:
            continue
        client = "claude-code" if "/claude-code/" in _turn_rel(store, ref) else "codex"
        if doc.get("session_ref") and doc["session_ref"] != keyed_ref(
                store.keystore.custody_key(), "session", client, "none"):
            refs.add(doc["session_ref"])
    return refs


def _turn_rel(store, turn_ref: str) -> str:
    path = next(iter(store.base.glob(f"*/*/{turn_ref}.enc")), None)
    return path.as_posix() if path else ""


def session_pending(home: Path, owner: str, client: str, session_id: str) -> list[dict]:
    """Unpaired pending prompts of a session: they hold a prompt too."""
    store, state = _turn_store(home, owner), home / "state"
    session_ref = store._session_ref(client, session_id)
    return [{"store": "CT", "item": path.stem, "rel": path.relative_to(state).as_posix()}
            for path, pending in store._pendings(session_ref) if not pending.get("turn_refs")]


def valid_trace_ref(value) -> bool:
    return type(value) is str and _TRACE.fullmatch(value) is not None


def valid_turn_ref(value) -> bool:
    return type(value) is str and _TURN.fullmatch(value) is not None
