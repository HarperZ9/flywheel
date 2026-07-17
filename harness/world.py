"""world.py -- the projected world: one re-derivable, root-hashed document the
person and the model both read (SUPERAPP.md subsystem c).

The forward reconcile is a projection: conserve the criterion, discard the rest.
The projected world is that conserved image of the system's state -- the subset
both parties perceive identically because both RE-DERIVE it rather than trust a
report. It composes four things that already exist and are individually verified:

  roster    superproject.roster()/spine() -- the flagship composition graph
  findings  findings.project_findings()   -- receipt-bound metrics, already root-hashed
  cursor    STATE.md head                 -- where the work is right now

and carries its OWN root hash over their fingerprints, so `verify_world()` can
re-compose and detect DRIFT: change any composed part -- a receipt, the roster, the
cursor -- and the world's root hash moves. The world snapshot is itself a receipt,
and the check can fail. Graceful: a missing part is reported honestly, not faked.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import merkle
from .run_paths import run_root_default

REPO = Path(__file__).resolve().parent.parent
DEFAULT_RUN_ROOT = Path(run_root_default())

MATCH = "MATCH"
DRIFT = "DRIFT"
UNVERIFIABLE = "UNVERIFIABLE"
_PART_ORDER = ("roster", "spine", "findings", "cursor")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def _cursor(repo_root: Path) -> dict:
    """The work cursor: STATE.md's last-updated line + current top section."""
    p = Path(repo_root) / "STATE.md"
    if not p.is_file():
        return {"present": False}
    head = p.read_text(encoding="utf-8", errors="replace").splitlines()[:40]
    updated = next((ln.split(":", 1)[1].strip() for ln in head
                    if ln.lower().startswith("last updated")), "")
    section = next((ln.lstrip("# ").strip() for ln in head if ln.startswith("## ")), "")
    return {"present": True, "last_updated": updated, "top_section": section,
            "head_hash": _sha("\n".join(head))[:16]}


def _safe(fn, default):
    try:
        return fn()
    except Exception as e:
        return {"error": str(e), **(default if isinstance(default, dict) else {})}


def _world_fingerprints(roster, spine, findings, cursor) -> list:
    """The four part fingerprints, in _PART_ORDER, exactly as the roots hash over."""
    return [
        json.dumps(roster, sort_keys=True, default=str),
        json.dumps(spine, sort_keys=True, default=str),
        str(findings.get("root_hash", "MISSING")),
        json.dumps(cursor, sort_keys=True, default=str),
    ]


def project_world(run_root: Path | str = DEFAULT_RUN_ROOT,
                  repo_root: Path | str = REPO) -> dict:
    """Compose the projected world with a root hash over its parts' fingerprints."""
    from . import superproject
    from .findings import project_findings

    roster = _safe(superproject.roster, {})
    spine = _safe(superproject.spine, {})
    findings = _safe(lambda: project_findings(run_root), {"root_hash": "MISSING"})
    cursor = _cursor(repo_root)

    fingerprints = _world_fingerprints(roster, spine, findings, cursor)
    root_hash = _sha("|".join(fingerprints))
    return {
        "schema": "flywheel.projected-world/v1",
        "root_hash": root_hash,
        # Merkle root over the same part fingerprints: proves ONE part is in the
        # world with a log-n audit path (world_inclusion_proof), not just the whole.
        "merkle_root": merkle.root_hex([f.encode() for f in fingerprints]),
        "roster": roster,
        "spine": spine,
        "findings": {
            "root_hash": findings.get("root_hash"),
            "measured": findings.get("measured"),
            "pending": findings.get("pending"),
            "items": findings.get("findings"),
        },
        "cursor": cursor,
        "note": "re-derivable: verify_world() recomposes and returns DRIFT if any "
                "part moved. Both the person and the model read this, not a report.",
    }


def verify_world(doc: dict, run_root: Path | str = DEFAULT_RUN_ROOT,
                 repo_root: Path | str = REPO) -> str:
    """Recompose the world and compare root hashes. MATCH if identical, DRIFT if a
    composed part moved, UNVERIFIABLE if the doc carries no root hash."""
    if not isinstance(doc, dict) or "root_hash" not in doc:
        return UNVERIFIABLE
    fresh = project_world(run_root, repo_root)
    return MATCH if fresh["root_hash"] == doc["root_hash"] else DRIFT


def _doc_fingerprints(doc: dict) -> list:
    return _world_fingerprints(
        doc.get("roster", {}), doc.get("spine", {}),
        {"root_hash": (doc.get("findings") or {}).get("root_hash", "MISSING")},
        doc.get("cursor", {}))


def world_inclusion_proof(doc: dict, part: str) -> dict:
    """A log-n audit path proving `part` (roster|spine|findings|cursor) is in the
    world's merkle_root, verifiable without the rest of the doc."""
    if part not in _PART_ORDER:
        raise ValueError(f"part must be one of {_PART_ORDER}")
    fps = _doc_fingerprints(doc)
    leaves = [f.encode() for f in fps]
    idx = _PART_ORDER.index(part)
    return {"part": part, "index": idx, "size": len(leaves), "leaf": fps[idx],
            "proof": [h.hex() for h in merkle.inclusion_proof(leaves, idx)]}


def verify_world_part(doc: dict, proof: dict) -> bool:
    """Recompute the merkle_root from one part + its audit path; True iff it matches
    the doc's merkle_root, so a stranger checks one part without the whole world."""
    root = doc.get("merkle_root", "")
    if not root.startswith("sha256:"):
        return False
    try:
        root_bytes = bytes.fromhex(root.split(":", 1)[1])
        path = [bytes.fromhex(h) for h in proof["proof"]]
    except (ValueError, KeyError, TypeError):
        return False
    return merkle.verify_inclusion(proof["leaf"].encode(), proof["index"],
                                   proof["size"], path, root_bytes)


if __name__ == "__main__":
    import sys
    print(json.dumps(project_world(
        run_root=sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RUN_ROOT), indent=1))
