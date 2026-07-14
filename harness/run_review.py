"""run_review.py -- the reviewability projection of a witnessed agent run.

The industry split this serves: expert reviewers want to know what the
model did and why; learners inherit endings without middles. Every agent
run already carries a hash-chained ledger -- this module projects it into
the terms a senior reviewer checks first:

- edited_unread     files the run edited without ever reading first
                    (the classic "went too far" scar);
- unverified_edits  edits no oracle covered afterwards (nothing green ran
                    after the change);
- failed_calls      the retry scars, kept visible -- where the first cut
                    was not deep enough;
- reviewability     re-derivable arithmetic over those named signals.

Everything here is a FACT from the ledger. No generated narrative is ever
mixed in; if a surface wants prose on top, it must label the prose as
prose. That separation is the whole point.
"""
from __future__ import annotations

import json

SCHEMA = "flywheel.run-review/v1"

_READ_TOOLS = {"read_file"}
_WRITE_TOOLS = {"write_file", "edit_file"}


def _field(entry, name, default=None):
    if isinstance(entry, dict):
        return entry.get(name, default)
    return getattr(entry, name, default)


def _parse_call(content: str) -> tuple:
    name, _, rest = (content or "").partition(" ")
    try:
        args = json.loads(rest) if rest else {}
    except ValueError:
        args = {}
    return name, args if isinstance(args, dict) else {}


def _patch_paths(patch: str) -> list:
    return [line[6:].strip() for line in (patch or "").splitlines()
            if line.startswith("+++ b/")]


def run_review(entries: list) -> dict:
    """Project ledger entries (dicts or Entry objects) into the review doc."""
    reads: set = set()
    writes: list = []            # (order, path)
    failed_calls = 0
    last_green_run = -1
    n_calls = 0
    order = 0
    pending_call = None
    for entry in entries:
        kind = _field(entry, "kind", "")
        if kind == "tool_call":
            order += 1
            n_calls += 1
            pending_call = _parse_call(_field(entry, "content", ""))
            name, args = pending_call
            if name in _READ_TOOLS and args.get("path"):
                reads.add(str(args["path"]))
            elif name in _WRITE_TOOLS and args.get("path"):
                writes.append((order, str(args["path"]), str(args["path"]) in reads))
            elif name == "apply_patch":
                for p in _patch_paths(args.get("patch") or args.get("diff") or ""):
                    writes.append((order, p, p in reads))
        elif kind == "tool_result":
            meta = _field(entry, "meta", {}) or {}
            if meta.get("ok") is False:
                failed_calls += 1
            if meta.get("tool") == "run" and meta.get("ok") is True:
                last_green_run = order

    edited_unread = sorted({p for _, p, was_read in writes if not was_read})
    unverified = sorted({p for o, p, _ in writes if o > last_green_run})
    n_writes = len(writes)
    read_ratio = (sum(1 for _, _, r in writes if r) / n_writes) if n_writes else 1.0
    verified_ratio = (sum(1 for o, _, _ in writes if o <= last_green_run)
                      / n_writes) if n_writes else 1.0
    clean_ratio = (1.0 - failed_calls / n_calls) if n_calls else 1.0
    score = round(0.4 * read_ratio + 0.4 * verified_ratio + 0.2 * clean_ratio, 4)
    return {
        "schema": SCHEMA,
        "edited_unread": edited_unread,
        "unverified_edits": unverified,
        "failed_calls": failed_calls,
        "files_read": sorted(reads),
        "files_edited": sorted({p for _, p, _ in writes}),
        "reviewability": score,
        "signals": {
            "read_before_write_ratio": round(read_ratio, 4),
            "verified_edit_ratio": round(verified_ratio, 4),
            "clean_call_ratio": round(clean_ratio, 4),
            "weights": {"read": 0.4, "verified": 0.4, "clean": 0.2},
        },
        "note": "facts from the witnessed ledger only; any prose a surface "
                "adds on top must be labeled as prose",
    }
