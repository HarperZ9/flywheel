"""What a presence prompt says, built from the plan itself (7.15, I17).

The owner approves what the prompt shows, so the prompt must show what the
operation does. The text is built here, on the side that runs the operation,
from the saved plan, the export grant or the settings file whose digest is
being confirmed. It never comes from the caller. A digest this module cannot
describe is refused (PRESENCE_UNDESCRIBED), so no prompt reads as a bare
digest prefix.
"""
from __future__ import annotations

import os
from pathlib import Path
import threading

_REMEMBERED: dict[tuple[str, str], str] = {}
_LOCK = threading.Lock()


def remember(kind: str, digest: str, text: str) -> None:
    """A summary this process built when it planned the operation (bench)."""
    with _LOCK:
        _REMEMBERED[(kind, digest)] = text


def _names() -> dict[str, str]:
    from .trace_inventory import stores
    return {s.id: s.name for s in stores()}


def delete_summary(home, owner: str, digest: str, *, verb: str = "Delete") -> str:
    from .trace_delete_plan import load_selection, make_plan
    selection = load_selection(home, owner, digest)
    plan = make_plan(home, owner, selection, save=False)
    names = _names()
    counts = "; ".join(f"{names.get(s, s)}: {n}" for s, n in sorted(plan["counts"].items()))
    lines = [f"{verb} {len(plan['entries'])} items ({counts})."]
    session = selection.get("session")
    if session:
        lines.append(f"Whole session {session['session_id']} of {session['client']}.")
    if plan["remedies"]:
        lines.append("Clients: " + ", ".join(sorted(plan["remedies"])) + ".")
    whole = _whole_custody(home, owner, plan)
    if whole:
        lines.append(whole)
    lines.append(f"Plan {digest}.")
    return " ".join(lines)


def _whole_custody(home, owner: str, plan: dict) -> str:
    from .trace_retention import items
    held: dict[str, int] = {}
    for item in items(home, owner):
        held[item["store"]] = held.get(item["store"], 0) + 1
    every = [s for s, n in held.items() if n and plan["counts"].get(s) == n]
    names = _names()
    return ("This is every item you hold in: " + ", ".join(names.get(s, s) for s in sorted(every))
            + ".") if every else ""


def export_summary(out, options: dict) -> str:
    full = {"redact": True, "redact_personal": False, "zip": False, **options}
    where = os.path.realpath(os.path.abspath(str(out)))
    mode = ("NOT redacted: credentials are written as stored" if not full["redact"] else
            "credentials and personal data redacted" if full["redact_personal"] else
            "credentials redacted")
    shape = " as one .zip file" if full["zip"] else ""
    return f"Write a plaintext copy of your traces to {where}{shape}; {mode}."


def _export(home, owner: str, digest: str) -> str | None:
    import json
    from .trace_export import export_digest
    from .trace_export_dest import grant_folder
    folder = grant_folder(home, owner)
    for path in sorted(folder.glob("xgr_*.json")) if folder.is_dir() else []:
        try:
            doc = json.loads(path.read_bytes())
            if export_digest(doc["destination"], doc["options"]) == digest:
                return export_summary(doc["destination"], doc["options"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return None


def _settings(home, owner: str, kind: str, digest: str) -> str | None:
    if kind == "capture_settings":
        from .trace_capture_settings import data_flow, digest as value, read_file
        doc, _ = read_file(home)
        if doc is not None and value(doc) == digest:
            return "Adopt these capture settings. " + " ".join(data_flow(doc, home=home))
    if kind == "retention_adopt":
        from .trace_retention import describe, digest as value, read_file
        doc, _ = read_file(home)
        if doc is not None and value(doc) == digest:
            return "Adopt this retention policy: " + describe(doc)
    if kind == "presence_method":
        from .trace_presence import METHODS, method_digest
        for method in METHODS:
            if method_digest(method) == digest:
                return f"Change the presence method to {method}."
    return None


def describe(home, owner: str, kind: str, digest: str) -> str:
    """The prompt text for `kind` bound to `digest`; raises PresenceError."""
    from .trace_delete_plan import PlanError
    from .trace_presence import PresenceError
    home = Path(home)
    text = None
    with _LOCK:
        text = _REMEMBERED.get((kind, digest))
    try:
        if text is None and kind == "delete_apply":
            text = delete_summary(home, owner, digest)
        elif text is None and kind == "retention_apply":
            text = delete_summary(home, owner, digest, verb="Retention deletes")
        elif text is None and kind in ("export", "export_allow_sync_root"):
            text = _export(home, owner, digest)
            if text and kind == "export_allow_sync_root":
                text = "Allow a destination under a sync folder. " + text
        elif text is None:
            text = _settings(home, owner, kind, digest)
    except PlanError:
        text = None
    if not text:
        raise PresenceError("PRESENCE_UNDESCRIBED")
    return text
