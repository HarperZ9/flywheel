#!/usr/bin/env python3
"""build_demos_index.py — generate demos/index.json from the demo recordings.

The showcase gallery must never be hand-maintained: a new recording appears in
the shell the moment this manifest is regenerated (SUPERAPP.md increment 1).
Deterministic: content derives only from the demo transcripts on disk (their
own recorded timestamps), never from the wall clock.

Falsifier: drop a new demos/<name>/transcript.json + player.html, regenerate,
and the manifest gains an entry; if the gallery still lacks the tile after
reload, increment 1 is broken.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

DEMOS = Path(__file__).resolve().parent.parent / "demos"
OUT = DEMOS / "index.json"

# Curated display copy for the known shots, in gallery order. Unknown demo
# dirs are appended alphabetically with copy derived from their transcript.
CURATED = [
    ("harness-first-run", "local-model harness",
     "Propose, verify against an oracle, witness a re-checkable receipt.",
     "the engine"),
    ("telos-showcase", "telos",
     "The reconciler that takes the stage: perceive, check, carry proof.",
     "primary engine"),
    ("index-showcase", "index",
     "A faithful map of a codebase, with a verified-wiki you can trust.", None),
    ("forum-showcase", "forum",
     "Accountable multi-agent orchestration over a replayable causal ledger.", None),
    ("gather-showcase", "gather",
     "Research intake with a source receipt and a re-verifiable corpus.", None),
    ("crucible-showcase", "crucible",
     "A judgment organ: register, steelman, measure, refine, witness.", None),
    ("mneme-showcase", "mneme",
     "Accountable agent memory: remember, recall, and prove provenance.", None),
    ("relay-showcase", "relay",
     "A zero-dependency agent that reaches local and frontier endpoints with failover.", None),
    ("plexus-showcase", "plexus",
     "Cross-tool capability discovery and auto-wiring, so the spine composes.", None),
    ("local-model-showcase", "local-model CLI",
     "The harness command line and its receipts, end to end.", None),
]


def _entry(demo_dir: Path, name: str, role: str, badge: str | None) -> dict | None:
    tpath = demo_dir / "transcript.json"
    ppath = demo_dir / "player.html"
    if not (tpath.exists() and ppath.exists()):
        return None
    t = json.loads(tpath.read_text(encoding="utf-8"))
    entry = {
        "id": demo_dir.name,
        "player": f"{demo_dir.name}/player.html",
        "name": name,
        "role": role,
        "step_count": t.get("step_count"),
        "total_duration_ms": t.get("total_duration_ms"),
        "recorded_utc": t.get("timestamp_utc"),
        "receipt_sha256": t.get("receipt_sha256"),
        "transcript_sha256": hashlib.sha256(tpath.read_bytes()).hexdigest(),
    }
    if badge:
        entry["badge"] = badge
    return entry


def main() -> int:
    curated_ids = {c[0] for c in CURATED}
    demos: list[dict] = []
    for did, name, role, badge in CURATED:
        e = _entry(DEMOS / did, name, role, badge)
        if e:
            demos.append(e)
    for d in sorted(p for p in DEMOS.iterdir() if p.is_dir()):
        if d.name in curated_ids:
            continue
        t = d / "transcript.json"
        if not t.exists():
            continue
        meta = json.loads(t.read_text(encoding="utf-8"))
        e = _entry(d, meta.get("name", d.name),
                   f"Recorded shot: {meta.get('name', d.name)}.", None)
        if e:
            demos.append(e)
    doc = {"schema": "flywheel.demos-index/v1",
           "source": "scripts/build_demos_index.py",
           "demo_count": len(demos), "demos": demos}
    OUT.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(demos)} demos)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
