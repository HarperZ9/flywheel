"""Deletion plans (7.10, I4): a selection becomes the closure to delete.

A selection names gateway trace refs, captured turn refs, imported item refs,
a client and session id, store.db receipt ids, fold index note refs or
legacy run ids; nothing else, and never a path. A session covers its
captured turns and its imported transcripts. The plan lists every entry (store, item,
where it lives), the keys to destroy per encrypted store, the copies outside
reach (the model provider for a gateway trace, the client's own transcript,
backups), the residue to expect, and the stores no deletion covers yet, and
binds the entries in a plan digest over sorted refs. The selection is saved
under its digest so apply can recompute the plan and refuse one that drifted.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re

from .evidence_json import canonical_bytes, canonical_sha256
from .trace_delete_adapters_enc import (session_pending, session_turns, trace_entries,
                                        turn_entries, valid_trace_ref, valid_turn_ref)
from .trace_delete_adapters_import import entries_for as import_entries, valid_ref
from .trace_delete_adapters_plain import (PROFILE_NOTE, selection_entries, trace_closure,
                                          valid)

_SESSION = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")
REMEDIES = {"claude-code": "claude project purge", "codex": "remove the rollout in Codex"}
ENCRYPTED = ("S1", "CT", "S8b", "IM")
_LISTS = {"trace_refs": valid_trace_ref, "turn_refs": valid_turn_ref, "import_refs": valid_ref,
          "receipt_eids": lambda v: valid("receipt_eids", v),
          "note_refs": lambda v: valid("note_refs", v),
          "legacy_runs": lambda v: valid("legacy_runs", v)}


class PlanError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def validate(selection) -> dict:
    ok = type(selection) is dict and set(selection) <= {*_LISTS, "session"}
    for key, check in _LISTS.items():
        items = selection.get(key, []) if ok else None
        ok = ok and type(items) is list and all(check(v) for v in items)
    session = selection.get("session") if ok else None
    ok = ok and (session is None or type(session) is dict and set(session) == {
        "client", "session_id"} and session["client"] in REMEDIES
        and type(session["session_id"]) is str and _SESSION.fullmatch(session["session_id"]))
    if not ok or not any(selection.get(k) for k in (*_LISTS, "session")):
        raise PlanError("INVALID_SELECTION")
    return selection


def _plans(home, owner: str) -> Path:
    return Path(home) / "state" / "trace-deletions" / "v1" / "owners" / owner / "plans"


def roots_for(home) -> dict:
    from .trace_inventory_scan import resolve_roots
    home = Path(home)
    return {"home": home, "state": home / "state", "run": resolve_roots()["run"]}


def _encrypted(home: Path, owner: str, selection: dict) -> tuple[list, list, set]:
    entries, receipts, clients = [], [], set()
    for ref in selection.get("trace_refs", []):
        found = trace_entries(home / "state", owner, ref)
        if not found:
            raise PlanError("NOT_FOUND")
        entries += found
    turns, session = list(selection.get("turn_refs", [])), selection.get("session")
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
    imported, import_clients = import_entries(home, owner, selection.get("import_refs", []),
                                              session)
    if selection.get("import_refs") and not imported:
        raise PlanError("NOT_FOUND")
    return entries + imported, receipts, clients | import_clients


def _collect(home: Path, owner: str, selection: dict, roots: dict) -> tuple[list, list, set]:
    entries, receipts, clients = _encrypted(home, owner, selection)
    for entry in [e for e in entries if e["store"] == "S1"]:
        entries += trace_closure(home / "state", owner, entry)
    entries += selection_entries(roots, selection, receipts)
    unique = {(e["store"], e["item"]): e for e in entries}
    return sorted(unique.values(), key=lambda e: (e["store"], e["item"])), \
        sorted(set(receipts)), clients


def _not_covered() -> list[str]:
    from .trace_inventory import Gap, stores
    return sorted(s.id for s in stores() if isinstance(s.delete, Gap))


def _forecast(home: Path, entries: list[dict]) -> dict:
    encrypted = [e for e in entries if e["store"] in ENCRYPTED]
    plain = [e for e in entries if e["store"] not in ENCRYPTED]
    forecast = {"ciphertext_freed_clusters": len(encrypted)}
    if plain:
        forecast["freed_clusters"] = len(plain)
    legacy = [e for e in plain if e["store"] == "S7" and not e["item"].startswith("tr2_")]
    if legacy:
        forecast["legacy_fingerprint"] = len(legacy)
    from .trace_delete_adapters_plain import legacy_snapshots
    kept = legacy_snapshots(home, entries)
    if kept:
        forecast["legacy_snapshots_kept"] = kept
    return forecast


def make_plan(home, owner: str, selection, *, save: bool = True, roots=None) -> dict:
    home, selection = Path(home), validate(selection)
    roots = roots or roots_for(home)
    entries, receipts, clients = _collect(home, owner, selection, roots)
    keys: dict[str, list[str]] = {}
    for entry in (e for e in entries if e["store"] in ENCRYPTED):
        keys.setdefault(entry["store"], []).append(entry["item"])
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["store"]] = counts.get(entry["store"], 0) + 1
    out_of_reach = {"backups": 1, **({"provider": 1} if keys.get("S1") else {}),
                    **({"client_transcript": len(clients)} if clients else {})}
    digest = canonical_sha256({"schema": "flywheel.trace-delete-plan/v1", "owner_ref": owner,
                               "entries": [[e["store"], e["item"]] for e in entries],
                               "receipts": receipts})
    plan = {"schema": "flywheel.trace-delete-plan/v1", "plan_digest": digest,
            "entries": entries, "receipts": receipts, "keys": keys, "counts": counts,
            "out_of_reach": out_of_reach, "remedies": {c: REMEDIES[c] for c in sorted(clients)},
            "residue_forecast": _forecast(home, entries), "not_covered": _not_covered(),
            "notes": [PROFILE_NOTE] if any(e["store"] == "S6" for e in entries) else []}
    if save:
        _save(home, owner, digest, selection)
    return plan


def _save(home: Path, owner: str, digest: str, selection: dict) -> None:
    folder = _plans(home, owner)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    (folder / f"{digest}.json").write_bytes(canonical_bytes(
        {"schema": "flywheel.trace-delete-selection/v1", "selection": selection,
         "created_at": stamp}))


def load_selection(home, owner: str, digest: str) -> dict:
    if type(digest) is not str or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise PlanError("PLAN_NOT_FOUND")
    try:
        return json.loads((_plans(home, owner) / f"{digest}.json").read_bytes())["selection"]
    except (OSError, ValueError, KeyError):
        raise PlanError("PLAN_NOT_FOUND") from None


def drop_selection(home, owner: str, digest: str) -> None:
    (_plans(home, owner) / f"{digest}.json").unlink(missing_ok=True)
