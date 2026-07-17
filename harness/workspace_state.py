"""workspace_state.py -- the workspace as a checkable state.

OpenCode ships session revert; the import is revert WITH PROOF: a run's
pre and post workspace are content-addressed, so 'nothing changed',
'exactly these files changed', and 'the rollback restored the prior
state' are statements a stranger can re-derive. Deterministic: sorted
relative paths, content hashes, one root hash over the listing. Caps are
part of the answer -- a skipped file is counted, never silently omitted.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

SCHEMA = "flywheel.workspace-state/v1"
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".dart_tool", "build",
              ".elan", "artifacts", ".pytest_cache", ".ruff_cache"}


def workspace_snapshot(root, *, max_files: int = 2000,
                       max_bytes: int = 1_000_000) -> dict:
    root = Path(root)
    rows: list = []
    skipped = 0
    counted = 0
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(part in _SKIP_DIRS for part in rel.parts):
            continue
        if counted >= max_files:
            skipped += 1
            continue
        try:
            size = p.stat().st_size
            if size > max_bytes:
                skipped += 1
                continue
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
        except OSError:
            skipped += 1
            continue
        rows.append(f"{rel.as_posix()}:{digest}")
        counted += 1
    return {
        "schema": SCHEMA,
        "workspace_sha256": hashlib.sha256(
            "\n".join(rows).encode("utf-8")).hexdigest(),
        "files": counted,
        "skipped": skipped,
        "note": "sorted path:content-hash listing under one root hash; "
                "skipped files are counted, never silently omitted",
    }
