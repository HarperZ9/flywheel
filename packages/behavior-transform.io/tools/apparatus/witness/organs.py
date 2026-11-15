"""witness.organs — temporal perception layer (sensor only).

Perception commands:
  watch    Anchor a baseline snapshot of a set of paths at a moment
  observe  Report UNCHANGED / DRIFTED / NEW / GONE since the baseline

The apparatus uses these to witness the state of governed targets
before and after inoculation.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _raw(p: str | Path) -> bytes:
    with open(p, "rb") as f:
        return f.read()


def _git_stamp() -> str:
    try:
        o = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        return o.stdout.strip() or "no-head"
    except Exception:
        return "no-git"


def watch(manifest: str | Path, paths: list[str | Path]) -> dict[str, Any]:
    """Anchor a baseline snapshot of the given paths."""
    db: dict[str, Any] = {"at": _git_stamp(), "artifacts": {}}
    for p in paths:
        p = os.path.normpath(str(p))
        if os.path.isfile(p):
            h = _sha(_raw(p))
            db["artifacts"][p] = h
    with open(manifest, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, sort_keys=True)
    return {"watched": len(db["artifacts"]), "at": db["at"], "artifacts": db["artifacts"]}


def observe(manifest: str | Path, paths: list[str | Path]) -> dict[str, Any]:
    """Report state changes since the watch baseline."""
    if os.path.exists(manifest):
        with open(manifest, encoding="utf-8") as f:
            db = json.load(f)
    else:
        db = {"artifacts": {}}

    known = db.get("artifacts", {})
    results: dict[str, str] = {}
    changed = 0

    for p in paths:
        p = os.path.normpath(str(p))
        if not os.path.isfile(p):
            results[p] = "GONE"
            changed += 1
            continue
        cur = _sha(_raw(p))
        was = known.get(p)
        if was is None:
            results[p] = "NEW"
            changed += 1
        elif cur == was:
            results[p] = "UNCHANGED"
        else:
            results[p] = "DRIFTED"
            changed += 1

    return {
        "results": results,
        "changed": changed,
        "since": db.get("at", "unknown"),
    }


confirm = observe
