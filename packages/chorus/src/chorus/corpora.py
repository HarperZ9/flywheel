"""corpora.py -- discover gather corpora under a root as discourse sources.

A gather corpus is a directory holding ``catalog.jsonl`` (and an ``objects/``
store). This lists the corpora under a root (the root itself plus its immediate
subdirectories), each with the count of comment items and the subject they respond
to, so a caller can pick a gathered run to synthesize without knowing the path by
heart. Read-only; a missing root is a named error, never a crash.
"""
from __future__ import annotations

import json
import os


def _summarize(path: str) -> "dict | None":
    """Read one corpus's catalog: count comment items, take the subject title and
    the ref they respond to. Returns None if the catalog cannot be read."""
    cat = os.path.join(path, "catalog.jsonl")
    comments = 0
    subject = ""
    responds_to = ""
    try:
        with open(cat, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("kind") == "comment":
                    comments += 1
                    if not responds_to:
                        responds_to = str(r.get("ref", ""))
                if not subject and r.get("title"):
                    subject = str(r.get("title"))
                if not responds_to and r.get("ref"):
                    responds_to = str(r.get("ref"))
    except OSError:
        return None
    return {
        "path": path.replace("\\", "/"),
        "name": os.path.basename(path.rstrip("/\\")) or path,
        "comments": comments,
        "subject": subject,
        "responds_to": responds_to,
    }


def _is_corpus(path: str) -> bool:
    return os.path.isfile(os.path.join(path, "catalog.jsonl"))


def list_corpora(root: str) -> dict:
    """List gather corpora under ``root`` (the root itself and its immediate
    subdirectories). Returns ``{root, corpora: [...]}`` or a named error."""
    if not root or not os.path.isdir(root):
        return {"error": f"root is not an existing directory: {root}"}
    candidates = [root]
    try:
        candidates += [os.path.join(root, d) for d in sorted(os.listdir(root))]
    except OSError as e:
        return {"error": f"could not read root {root}: {e}"}
    found = []
    for c in candidates:
        if _is_corpus(c):
            s = _summarize(c)
            if s is not None:
                found.append(s)
    return {"root": root.replace("\\", "/"), "corpora": found}
