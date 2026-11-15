"""ledger.py -- what canon wrote into each instruction region.

A region on disk can differ from what canon would render now for two reasons:
the records changed since canon wrote it (the file is stale), or a person or
another tool edited the region in place. Only the first is safe to overwrite.
Telling them apart needs what canon wrote, so `switch` records it, per project:

    projects/<project_id>/renders.json
    {"schema": "canon.render-ledger/v1", "seq": 7,
     "surfaces": {"<checkout>:CLAUDE.md": {"target": "claude-code", "seq": 7,
                  "sha256": "...", "interior": "...", "owners": {"voice": "prj_..."}}},
     "history": {"CLAUDE.md": [{"sha256": "...", "interior": "..."}]}}

A project can have several checkouts (clones, worktrees), each with its own
file, so the last render is kept per checkout: `<checkout>` is a path-clean
digest of the checkout root. `history` keeps the last interiors canon wrote to
a surface from any checkout; a region equal to one of them is a stale render,
not an edit, whichever checkout wrote it or whichever branch restored it.
`owners` names the project (or `global`) each rendered block belongs to, so an
edit of a block another project owns is never proposed as this project's.
`seq` numbers renders, so a decision on an edit is tied to the render it was
made against. `receipt` is the switch receipt for that render, which names
every record the brief left out. The interior is canon's own render of records
that already passed the secret checks.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from canon.versions import PIN_RENDER_LEDGER
from canon.workspace.store import ProjectStore, StoreError, write_atomic

LEDGER_SCHEMA = PIN_RENDER_LEDGER.kind_tag
LEDGER_FILE = "renders.json"
HISTORY_LIMIT = 16
GLOBAL_OWNER = "global"


@dataclass(frozen=True, slots=True)
class Render:
    interior: str
    seq: int
    owners: dict


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load(store: ProjectStore) -> dict:
    path = store.project_dir() / LEDGER_FILE
    if not path.is_file():
        return {"schema": LEDGER_SCHEMA, "seq": 0, "surfaces": {}, "history": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != LEDGER_SCHEMA or not isinstance(data.get("surfaces"), dict):
        raise StoreError(f"{LEDGER_FILE} is not a {LEDGER_SCHEMA} ledger")
    data.setdefault("seq", 0)
    data.setdefault("history", {})
    return data


def _checked(entry: dict, where: str) -> str:
    if _sha(entry["interior"]) != entry["sha256"]:
        raise StoreError(f"{LEDGER_FILE} entry for {where} fails its digest")
    return entry["interior"]


def last_render(store: ProjectStore, relative_path: str, checkout: str) -> Render | None:
    """What canon last wrote to this surface in this checkout, or None. A
    ledger entry whose digest does not match its text is refused."""
    entry = _load(store)["surfaces"].get(f"{checkout}:{relative_path}")
    if entry is None:
        return None
    return Render(_checked(entry, relative_path), int(entry.get("seq", 0)),
                  dict(entry.get("owners", {})))


def known_renders(store: ProjectStore, relative_path: str) -> list[str]:
    """Every interior canon still remembers writing to this surface, from any
    checkout, oldest first."""
    return [_checked(h, relative_path)
            for h in _load(store)["history"].get(relative_path, [])]


def record_render_unlocked(store: ProjectStore, relative_path: str, target: str,
                           interior: str, *, checkout: str, owners: dict,
                           receipt: dict | None = None) -> None:
    """Record a render and, when given, the switch receipt that lists what the
    brief left out. The caller holds the project lock, so the file write and
    this ledger write happen under one lock."""
    store.ensure_manifest()
    data = _load(store)
    data["seq"] = int(data["seq"]) + 1
    data["surfaces"][f"{checkout}:{relative_path}"] = {
        "target": target, "seq": data["seq"], "sha256": _sha(interior),
        "interior": interior, "owners": dict(sorted(owners.items())),
        "receipt": receipt}
    history = [h for h in data["history"].get(relative_path, []) if h["interior"] != interior]
    history.append({"sha256": _sha(interior), "interior": interior})
    data["history"][relative_path] = history[-HISTORY_LIMIT:]
    write_atomic(store.project_dir() / LEDGER_FILE,
                 json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n")


def record_render(store: ProjectStore, relative_path: str, target: str, interior: str,
                  *, checkout: str, owners: dict, receipt: dict | None = None) -> None:
    with store.locked():
        record_render_unlocked(store, relative_path, target, interior,
                               checkout=checkout, owners=owners, receipt=receipt)
