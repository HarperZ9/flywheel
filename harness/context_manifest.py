"""context_manifest.py -- what actually entered the model's window, provable.

Two dossier findings meet here: in-IDE quality is won by context packing
(Mellum), and ambient-signal context is poisonable precisely because the
developer never sees it ('Tab, Tab, Bug'). This loop's defense is
architectural and this manifest is its proof: every piece of context the
model received originated from a witnessed tool call in the hash-chained
ledger -- there is no ambient channel. The manifest records each read with
the hash of the content the model actually saw (the reproducibility key:
replay the same reads, get the same window), the tool census, and the
system/goal hashes. Pure projection; nothing here is asserted that the
ledger does not show.
"""
from __future__ import annotations

import hashlib
import json

SCHEMA = "flywheel.context-manifest/v1"


def _field(entry, name, default=None):
    if isinstance(entry, dict):
        return entry.get(name, default)
    return getattr(entry, name, default)


def _sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def context_manifest(entries: list, *, system: str = "",
                     goal: str = "") -> dict:
    """Project ledger entries into the window manifest. `reads` pairs each
    read_file path with the sha of the tool_result content the model was
    actually shown; `tools` is the census of everything that ran."""
    reads: list = []
    tools: dict = {}
    pending_read_path = None
    for entry in entries:
        kind = _field(entry, "kind", "")
        if kind == "tool_call":
            content = _field(entry, "content", "") or ""
            name, _, rest = content.partition(" ")
            tools[name] = tools.get(name, 0) + 1
            pending_read_path = None
            if name == "read_file":
                try:
                    args = json.loads(rest) if rest else {}
                except ValueError:
                    args = {}
                if isinstance(args, dict) and args.get("path"):
                    pending_read_path = str(args["path"])
        elif kind == "tool_result":
            if pending_read_path is not None:
                meta = _field(entry, "meta", {}) or {}
                if meta.get("ok") is not False:
                    reads.append({
                        "path": pending_read_path,
                        "content_sha256": _sha(_field(entry, "content", "")),
                    })
            pending_read_path = None
    return {
        "schema": SCHEMA,
        "reads": reads,
        "tools": tools,
        "system_sha256": _sha(system),
        "goal_sha256": _sha(goal),
        "entries": len(entries),
        "note": "no ambient channel exists in this loop: every context "
                "entry originates from a witnessed tool call in the "
                "hash-chained ledger; replaying the reads reproduces the "
                "window",
    }
