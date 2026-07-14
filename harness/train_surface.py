"""train_surface.py -- read-only views for the training-harness lane.

The Train workspace watches the local-model flywheel: the verified-inference
duel (does the harness beat using a model raw?), the closed loop audit, and
the training supervisor. Everything here is observation; training START stays
operator-gated. The duel summary reads whatever rows exist -- a completed
scorecard or an in-progress partial -- and is honest that a partial is
partial."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_DUEL_DIR = REPO / "artifacts" / "duels"


def _rate(rows: list, key: str) -> float:
    n = len(rows)
    return round(sum(1 for r in rows if r.get(key)) / n, 4) if n else 0.0


def duel_summary() -> dict:
    """Summarize the newest duel: single-shot (a model used raw) vs the
    Flywheel best-of-N verified loop, plus self-test and consensus arms.
    Reads a completed .json or an in-progress .partial.jsonl."""
    if not _DUEL_DIR.is_dir():
        return {"schema": "flywheel.duel-summary/v1", "status": "none",
                "note": "no duel has been run; the harness-lift measurement "
                        "is available but unrun"}
    completed = sorted(_DUEL_DIR.glob("*.json"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
    partials = sorted(_DUEL_DIR.glob("*.partial.jsonl"),
                      key=lambda p: p.stat().st_mtime, reverse=True)
    rows: list = []
    status = "none"
    source = ""
    if completed:
        try:
            doc = json.loads(completed[0].read_text(encoding="utf-8"))
            rows = doc.get("rows", doc.get("results", []))
            status = "complete"
            source = completed[0].name
        except (OSError, ValueError):
            pass
    if not rows and partials:
        try:
            rows = [json.loads(x) for x in
                    partials[0].read_text(encoding="utf-8").splitlines()
                    if x.strip()]
            status = "partial"
            source = partials[0].name
        except (OSError, ValueError):
            pass
    if not rows:
        return {"schema": "flywheel.duel-summary/v1", "status": "none",
                "note": "duel artifacts present but unreadable"}
    single = _rate(rows, "single")
    ext = _rate(rows, "ext")
    return {"schema": "flywheel.duel-summary/v1", "status": status,
            "source": source, "n_tasks": len(rows),
            "single_rate": single, "verified_rate": ext,
            "self_rate": _rate(rows, "self"), "consensus_rate": _rate(rows, "cons"),
            "harness_lift": round(ext - single, 4),
            "rescued": [r.get("task_id") for r in rows
                        if r.get("ext") and not r.get("single")],
            "note": "single = a model used raw (existing-solution baseline); "
                    "verified = the Flywheel best-of-N loop over the SAME "
                    "model; the lift is the harness's contribution. "
                    + ("PARTIAL: not all tasks measured yet."
                       if status == "partial" else "")}


def loop_status() -> dict:
    """Run the loop-closure self-audit and return its verdict. Executes real
    handoffs in a temp dir, so this is on-demand, not a poll."""
    from harness.loop_closure import measure_loop
    with tempfile.TemporaryDirectory() as tmp:
        m = measure_loop(Path(tmp))
    return {"schema": "flywheel.loop-status/v1",
            "n_handoffs": m["n_handoffs"], "n_closed": m["n_closed"],
            "closure_fraction": m["closure_fraction"],
            "fully_closed": m["fully_closed"],
            "open_links": m["open_links"],
            "executed_links": m["executed_links"]}
