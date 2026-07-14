"""provenance_trace.py -- line-level provenance in the Agent-Trace shape.

OSS governance is moving proof-of-work from human self-disclosure to
tool-level transparency (arXiv 2603.26487): machine-readable, line-level
attribution of AI contributions with a link to the generating
conversation. This module emits that record from the witnessed ledger:
every machine-authored edit carries its path, author, the hash of the
content the model wrote, hunk line ranges where the diff format supplies
them, and the run's ledger checkpoint as the conversation link. Where line
numbers are unknowable (edit_file's old/new replacement), hunks is null --
an honest unknown beats an invented span.
"""
from __future__ import annotations

import hashlib
import json

SCHEMA = "flywheel.provenance-trace/v1"


def _field(entry, name, default=None):
    if isinstance(entry, dict):
        return entry.get(name, default)
    return getattr(entry, name, default)


def _sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _patch_attributions(patch: str) -> list:
    """Per-file hunk ranges from unified-diff headers (+start,count)."""
    out: dict = {}
    current = None
    for line in (patch or "").splitlines():
        if line.startswith("+++ b/"):
            current = line[6:].strip()
            out.setdefault(current, {"added": [], "hunks": []})
        elif line.startswith("@@") and current:
            try:
                plus = line.split("+", 1)[1].split(" ")[0]
                start, _, count = plus.partition(",")
                s = int(start)
                n = int(count) if count else 1
                out[current]["hunks"].append([s, s + max(n, 1) - 1])
            except (ValueError, IndexError):
                pass
        elif current and line.startswith("+") and not line.startswith("+++"):
            out[current]["added"].append(line[1:])
    return [{"path": p, "content_sha256": _sha("\n".join(v["added"])),
             "hunks": v["hunks"] or None} for p, v in out.items()]


def provenance_trace(entries: list, *, checkpoint: str = "",
                     author: str = "model") -> dict:
    """Project the ledger's edits into Agent-Trace-shaped attributions."""
    attributions: list = []
    for entry in entries:
        if _field(entry, "kind", "") != "tool_call":
            continue
        content = _field(entry, "content", "") or ""
        name, _, rest = content.partition(" ")
        try:
            args = json.loads(rest) if rest else {}
        except ValueError:
            args = {}
        if not isinstance(args, dict):
            continue
        if name == "write_file" and args.get("path"):
            text = args.get("content", "")
            n = len(text.splitlines()) or 1
            attributions.append({"path": str(args["path"]), "tool": name,
                                 "author": author,
                                 "content_sha256": _sha(text),
                                 "hunks": [[1, n]]})
        elif name == "edit_file" and args.get("path"):
            attributions.append({"path": str(args["path"]), "tool": name,
                                 "author": author,
                                 "content_sha256": _sha(args.get("new", "")),
                                 "hunks": None})
        elif name == "apply_patch":
            for row in _patch_attributions(
                    args.get("patch") or args.get("diff") or ""):
                attributions.append({**row, "tool": name, "author": author})
    return {"schema": SCHEMA, "attributions": attributions,
            "conversation": checkpoint,
            "note": "machine-readable line-level attribution (Agent-Trace "
                    "shape); hunks is null where the format cannot supply "
                    "line numbers -- an honest unknown, never an invented "
                    "span"}
