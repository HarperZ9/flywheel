"""eval_store.py -- persisted run history whose reads re-verify the receipt.

Science and agent runs each return one self-contained doc and, until now,
dropped it: a surface could fire a run but never compare it with the last
one. The store keeps each doc under the run root and holds every read to
the workflow-roster discipline:

- a science run's chain hash is RECOMPUTED from the stored payload at read
  time; a hand-edited verdict or a renamed receipt is served as TAMPERED,
  never as history. `started` rides outside the chain (the science chain
  is deterministic by construction, so a clock cannot live inside it) and
  is display metadata only;
- an agent run is content-addressed: its id is the sha256 of the canonical
  stored doc, so ANY edit -- including to `started` -- moves the id off its
  filename and the row is served as TAMPERED.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

SCIENCE_SCHEMA = "flywheel.science-runs/v1"
AGENT_SCHEMA = "flywheel.agent-runs/v1"


def _canonical(doc: dict) -> str:
    return json.dumps(doc, sort_keys=True, default=str)


def recompute_science_chain(doc: dict) -> str:
    """Re-derive a science run's chain exactly as science_run built it, from
    the stored payload alone. A stranger holding the receipt runs this."""
    return hashlib.sha256(json.dumps({
        "question": doc.get("question"),
        "sources": [s.get("id") for s in doc.get("sources", [])
                    if isinstance(s, dict)],
        "gates": (doc.get("prp") or {}).get("validation_gates", []),
        "claims": doc.get("claims") or [],
        "measurements": doc.get("measurements") or [],
        "verdicts": [(v.get("claim_id"), v.get("status"))
                     for v in doc.get("verdicts", []) if isinstance(v, dict)],
        "errors": doc.get("errors") or {},
    }, sort_keys=True).encode()).hexdigest()


def save_science_run(run_root, doc: dict) -> dict:
    """Persist one science run under its chain hash. Raises on IO failure;
    the caller decides whether persistence is best-effort."""
    d = Path(run_root) / "science" / "runs"
    d.mkdir(parents=True, exist_ok=True)
    stored = dict(doc)
    stored["started"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    out = d / f"{doc['chain_hash'][:16]}.json"
    out.write_text(json.dumps(stored, indent=1, default=str),
                   encoding="utf-8")
    return {"receipt_path": out.name, "chain_hash": doc["chain_hash"]}


def _science_row(p: Path) -> dict:
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"receipt": p.stem, "status": "UNREADABLE", "chain_ok": False}
    counts: dict = {}
    for v in doc.get("verdicts", []):
        if isinstance(v, dict):
            s = str(v.get("status", "?"))
            counts[s] = counts.get(s, 0) + 1
    chain_ok = (recompute_science_chain(doc) == doc.get("chain_hash")
                and p.stem == str(doc.get("chain_hash", ""))[:16])
    errors = doc.get("errors") or {}
    status = ("TAMPERED" if not chain_ok
              else "PARTIAL" if errors else "COMPLETE")
    return {"question": doc.get("question"), "started": doc.get("started"),
            "chain_hash": doc.get("chain_hash"), "chain_ok": chain_ok,
            "verdicts": counts, "n_sources": len(doc.get("sources") or []),
            "n_errors": len(errors), "status": status}


def science_runs(run_root, limit: int = 20) -> dict:
    """History rows, newest first, each chain-reverified at read time."""
    d = Path(run_root) / "science" / "runs"
    files = (sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime,
                    reverse=True)[:max(1, limit)] if d.is_dir() else [])
    runs = [_science_row(p) for p in files]
    return {"schema": SCIENCE_SCHEMA, "runs": runs, "total": len(runs)}


def science_run_detail(run_root, prefix: str) -> dict:
    """The full stored run for one chain prefix, chain-reverified."""
    prefix = (prefix or "").strip().lower()
    if len(prefix) < 4:
        return {"error": "give at least 4 chain-hash characters"}
    d = Path(run_root) / "science" / "runs"
    matches = sorted(d.glob(f"{prefix[:16]}*.json")) if d.is_dir() else []
    if not matches:
        return {"error": f"no science run matching '{prefix[:16]}'"}
    try:
        doc = json.loads(matches[0].read_text(encoding="utf-8"))
    except Exception:
        return {"error": f"receipt unreadable: {matches[0].name}"}
    doc["chain_ok"] = (recompute_science_chain(doc) == doc.get("chain_hash")
                       and matches[0].stem == str(doc.get("chain_hash",
                                                          ""))[:16])
    return doc


def trim_events(events: list, cap: int = 200, text_cap: int = 700) -> list:
    """Trace events fit for storage. The run's beginning is its intent, so
    the FIRST `cap` events survive in order; anything dropped is named in a
    trailing marker — truncation is a fact of the record, never silent. Long
    text fields are capped with a visible ellipsis (tool output arrives
    pre-excerpted from the loop; this is the at-rest guarantee)."""
    out = []
    for e in list(events)[:cap]:
        e = dict(e)
        for k in ("text", "output", "args"):
            v = e.get(k)
            if isinstance(v, str) and len(v) > text_cap:
                e[k] = v[:text_cap] + "…"
        out.append(e)
    dropped = len(events) - len(out)
    if dropped > 0:
        out.append({"type": "truncated", "dropped": dropped})
    return out


def save_agent_run(run_root, doc: dict) -> dict:
    """Persist one agent run content-addressed by its canonical bytes."""
    d = Path(run_root) / "agent_runs"
    d.mkdir(parents=True, exist_ok=True)
    stored = dict(doc)
    stored["started"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    canonical = _canonical(stored)
    rid = hashlib.sha256(canonical.encode()).hexdigest()[:16]
    (d / f"{rid}.json").write_text(canonical, encoding="utf-8")
    return {"run_id": rid, "receipt_path": f"{rid}.json"}


def _agent_intact(p: Path, doc: dict) -> bool:
    return hashlib.sha256(
        _canonical(doc).encode()).hexdigest()[:16] == p.stem


def agent_runs(run_root, limit: int = 20) -> dict:
    """Agent-run history rows, newest first, content-address checked."""
    d = Path(run_root) / "agent_runs"
    files = (sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime,
                    reverse=True)[:max(1, limit)] if d.is_dir() else [])
    runs = []
    for p in files:
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            runs.append({"run_id": p.stem, "status": "UNREADABLE",
                         "intact": False})
            continue
        intact = _agent_intact(p, doc)
        runs.append({"run_id": p.stem, "intact": intact,
                     "status": ("TAMPERED" if not intact else
                                str(doc.get("status", "DONE"))),
                     "goal_excerpt": doc.get("goal_excerpt"),
                     "endpoint": doc.get("endpoint"),
                     "steps": doc.get("steps"),
                     "verified": doc.get("verified"),
                     "duration_s": doc.get("duration_s"),
                     "ttva_s": doc.get("ttva_s"),
                     "started": doc.get("started")})
    return {"schema": AGENT_SCHEMA, "runs": runs, "total": len(runs)}


def agent_run_detail(run_root, run_id: str) -> dict:
    """One full stored agent run, content-address checked."""
    rid = (run_id or "").strip().lower()
    p = Path(run_root) / "agent_runs" / f"{rid}.json"
    if not rid or not p.is_file():
        return {"error": f"no agent run '{rid}'"}
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"error": f"receipt unreadable: {p.name}"}
    doc["intact"] = _agent_intact(p, doc)
    return doc
