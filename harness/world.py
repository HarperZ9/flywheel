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

REPO = Path(__file__).resolve().parent.parent
DEFAULT_RUN_ROOT = Path("E:/local-model-run")

MATCH = "MATCH"
DRIFT = "DRIFT"
UNVERIFIABLE = "UNVERIFIABLE"


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


def project_world(run_root: Path | str = DEFAULT_RUN_ROOT,
                  repo_root: Path | str = REPO) -> dict:
    """Compose the projected world with a root hash over its parts' fingerprints."""
    from . import superproject
    from .findings import project_findings

    roster = _safe(superproject.roster, {})
    spine = _safe(superproject.spine, {})
    findings = _safe(lambda: project_findings(run_root), {"root_hash": "MISSING"})
    cursor = _cursor(repo_root)

    fingerprints = [
        json.dumps(roster, sort_keys=True, default=str),
        json.dumps(spine, sort_keys=True, default=str),
        str(findings.get("root_hash", "MISSING")),
        json.dumps(cursor, sort_keys=True, default=str),
    ]
    root_hash = _sha("|".join(fingerprints))
    return {
        "schema": "flywheel.projected-world/v1",
        "root_hash": root_hash,
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


if __name__ == "__main__":
    import sys
    print(json.dumps(project_world(
        run_root=sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RUN_ROOT), indent=1))
