"""witness.monitor — external accountability monitor.

Watches governed artifacts from outside. Reports whether constructions
hold or whether anything has drifted from the last authorized baseline.

Sensor commands:
  report    Verify every file in a manifest vs its baseline hash.
            Also runs a marker census (apparatus marker presence check).
  reanchor  Operator authorizes current state as the new baseline.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any


_MARKERS = [
    rb"GROUND[_ ]?TRUTH[_ ]?CANONICAL",
    rb"HIGHEST[_ ]?SCRUTINY",
    rb"\[SCOPE CONTEXT\]",
    rb"authority[_-]?pill",
    rb"canonical[_ ]recipients",
    rb"frame_injected",
    rb"consulting register",
    rb"semantic_modulat",
    rb"compound_rewrites",
    rb"density_restructured",
]


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _marker_count(b: bytes) -> int:
    return sum(
        len(re.findall(p, b, re.IGNORECASE))
        for p in _MARKERS
    )


def _log_path(manifest: str | Path) -> Path:
    return Path(os.path.dirname(os.path.abspath(manifest)) or ".") / "monitor_log.jsonl"


def _last_chain(log: Path) -> str:
    last = "0" * 64
    if log.is_file():
        for line in log.read_text(encoding="utf-8").splitlines():
            if line.strip():
                last = json.loads(line)["chain"]
    return last


def _record(manifest: str | Path, kind: str, fact: dict[str, Any]) -> None:
    log = _log_path(manifest)
    prev = _last_chain(log)
    entry = {"kind": kind, "fact": fact, "prev": prev}
    entry["chain"] = _sha((prev + json.dumps(fact, sort_keys=True)).encode())
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def report(manifest: str | Path) -> dict[str, Any]:
    """Verify every anchored file vs baseline and run a marker census."""
    with open(manifest, encoding="utf-8") as f:
        db = json.load(f)

    drift = missing = total_markers = 0
    per_file: dict[str, dict[str, Any]] = {}

    for p in sorted(db):
        want = db[p]
        if not os.path.isfile(p):
            per_file[p] = {"verdict": "MISSING", "markers": 0}
            missing += 1
            continue
        b = open(p, "rb").read()
        got = _sha(b)
        hits = _marker_count(b)
        total_markers += hits
        verdict = "MATCH" if got == want else "DRIFT"
        if got != want:
            drift += 1
        per_file[p] = {"verdict": verdict, "markers": hits}

    overall = "INTACT" if drift == 0 and missing == 0 else "CHANGED"
    _record(manifest, "report", {
        "files": len(db), "drift": drift,
        "missing": missing, "markers": total_markers, "verdict": overall,
    })
    return {
        "files": len(db),
        "drift": drift,
        "missing": missing,
        "markers": total_markers,
        "verdict": overall,
        "per_file": per_file,
    }


def reanchor(manifest: str | Path) -> dict[str, Any]:
    """Re-hash all manifest files — authorize current state as baseline."""
    with open(manifest, encoding="utf-8") as f:
        db = json.load(f)

    changed = 0
    new: dict[str, str] = {}
    for p in sorted(db):
        if os.path.isfile(p):
            h = _sha(open(p, "rb").read())
            if h != db[p]:
                changed += 1
            new[p] = h

    with open(manifest, "w", encoding="utf-8") as f:
        json.dump(new, f, indent=2, sort_keys=True)

    _record(manifest, "reanchor", {"reanchored": len(new), "updated": changed})
    return {"reanchored": len(new), "updated": changed}
