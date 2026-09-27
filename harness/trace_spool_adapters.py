"""Export and delete adapters for the capture spool (store S14).

The spool holds metadata only: reason codes, session ids, prompt keys and
times. A suppression record's working directory is DPAPI ciphertext that no
other machine can read, so export leaves it out and keeps the count.
"""
from __future__ import annotations

from pathlib import Path

from .capture_hooks import spool


def export_records(home) -> list[dict]:
    out = [{**r, "kind": "failure"} for r in spool.failures(Path(home))]
    for record in spool.suppressions(Path(home)):
        kept = {k: v for k, v in record.items() if k != "cwd_protected"}
        out.append({**kept, "kind": "suppression"})
    return out


def delete_all(home) -> dict:
    """Remove the spool by handle: a junction or link inside it is removed as
    a link and its target keeps its files."""
    from .trace_meta_adapters import remove_tree
    return {"removed": remove_tree(spool.spool_dir(Path(home)))}
