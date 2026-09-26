"""Deletion plans (7.10, I4): a selection becomes the closure to delete.

A selection names gateway trace refs, captured turn refs, or a client and
session id; nothing else, and never a path. The plan lists every entry
(store, item, path relative to the state root), the v2 receipts, the keys to
destroy per store, the copies outside reach (the model provider for a
gateway trace, the client's own transcript for a captured turn, backups) and
the residue to expect, and binds them in a plan digest over sorted refs.
The selection is saved under its digest so apply can recompute the plan
and refuse one that drifted.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re

from .evidence_json import canonical_bytes, canonical_sha256
from .trace_delete_adapters_enc import (session_pending, session_turns, trace_entries,
                                        turn_entries, valid_trace_ref, valid_turn_ref)

_SESSION = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")
REMEDIES = {"claude-code": "claude project purge", "codex": "remove the rollout in Codex"}


class PlanError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def validate(selection) -> dict:
    ok = type(selection) is dict and set(selection) <= {"trace_refs", "turn_refs", "session"}
    traces, turns = selection.get("trace_refs", []), selection.get("turn_refs", [])
    session = selection.get("session")
    ok = ok and type(traces) is list and all(valid_trace_ref(r) for r in traces)
    ok = ok and type(turns) is list and all(valid_turn_ref(r) for r in turns)
    ok = ok and (session is None or type(session) is dict and set(session) == {
        "client", "session_id"} and session["client"] in REMEDIES
        and type(session["session_id"]) is str and _SESSION.fullmatch(session["session_id"]))
    if not ok or not (traces or turns or session):
        raise PlanError("INVALID_SELECTION")
    return selection


def _plans(home, owner: str) -> Path:
    return Path(home) / "state" / "trace-deletions" / "v1" / "owners" / owner / "plans"


def _collect(home: Path, owner: str, selection: dict) -> tuple[list, list, set]:
    entries, receipts, clients = [], [], set()
    for ref in selection.get("trace_refs", []):
        found = trace_entries(home / "state", owner, ref)
        if not found:
            raise PlanError("NOT_FOUND")
        entries += found
    turns = list(selection.get("turn_refs", []))
    session = selection.get("session")
    if session:
        turns += session_turns(home, owner, session["client"], session["session_id"])
        entries += session_pending(home, owner, session["client"], session["session_id"])
        clients.add(session["client"])
    for ref in turns:
        found, eids = turn_entries(home, owner, ref)
        if not found:
            raise PlanError("NOT_FOUND")
        entries, receipts = entries + found, receipts + eids
        clients.add("claude-code" if "/claude-code/" in found[0]["rel"] else "codex")
    unique = {(e["store"], e["item"]): e for e in entries}
    return sorted(unique.values(), key=lambda e: (e["store"], e["item"])), sorted(set(receipts)), \
        clients


def make_plan(home, owner: str, selection, *, save: bool = True) -> dict:
    home, selection = Path(home), validate(selection)
    entries, receipts, clients = _collect(home, owner, selection)
    keys: dict[str, list[str]] = {}
    for entry in entries:
        keys.setdefault(entry["store"], []).append(entry["item"])
    out_of_reach = {"backups": 1}
    if keys.get("S1"):
        out_of_reach["provider"] = 1
    if clients:
        out_of_reach["client_transcript"] = len(clients)
    digest = canonical_sha256({"schema": "flywheel.trace-delete-plan/v1", "owner_ref": owner,
                               "entries": [[e["store"], e["item"]] for e in entries],
                               "receipts": receipts})
    plan = {"schema": "flywheel.trace-delete-plan/v1", "plan_digest": digest,
            "entries": entries, "receipts": receipts, "keys": keys,
            "counts": {store: len(items) for store, items in keys.items()},
            "out_of_reach": out_of_reach,
            "remedies": {c: REMEDIES[c] for c in sorted(clients)},
            "residue_forecast": {"ciphertext_freed_clusters": len(entries)}}
    if save:
        folder = _plans(home, owner)
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        (folder / f"{digest}.json").write_bytes(canonical_bytes(
            {"schema": "flywheel.trace-delete-selection/v1", "selection": selection,
             "created_at": stamp}))
    return plan


def load_selection(home, owner: str, digest: str) -> dict:
    if type(digest) is not str or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise PlanError("PLAN_NOT_FOUND")
    try:
        return json.loads((_plans(home, owner) / f"{digest}.json").read_bytes())["selection"]
    except (OSError, ValueError, KeyError):
        raise PlanError("PLAN_NOT_FOUND") from None


def drop_selection(home, owner: str, digest: str) -> None:
    (_plans(home, owner) / f"{digest}.json").unlink(missing_ok=True)
