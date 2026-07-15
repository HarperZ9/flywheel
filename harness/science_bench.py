"""science_bench.py -- the science workbench: evidence, spec, judgment, one chain.

The mature spin on model-assisted science: the model proposes, the
instruments dispose. One run chains three stages that already exist as
accountable tools:

- gather   arXiv intake with provenance receipts (the gather lane's CLI);
- forge    the question priced as a research PRP: validation gates marked
           by what an external check can run, confidence from that ratio;
- crucible witnessed judgment of the stated claims: a claim with no
           measurement comes back UNVERIFIABLE, sealed, and it STAYS that
           way on the surface -- an unmeasured claim is never accepted.

Every stage failure is a named error while the rest of the run continues,
and the whole run folds into one chain hash a third party can recompute
from the payload. Nothing here fires on its own; a run is a request.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

SCHEMA = "flywheel.science-run/v1"
_TIMEOUT = 120


def _shell(argv: list) -> tuple:
    """Default runner: (rc, stdout). Injectable so tests never shell out."""
    try:
        p = subprocess.run(argv, capture_output=True, text=True,
                           timeout=_TIMEOUT, shell=False)
        return (p.returncode, p.stdout or p.stderr or "")
    except subprocess.TimeoutExpired:
        return (124, f"timed out after {_TIMEOUT}s")
    except OSError as e:
        return (127, f"{type(e).__name__}: {e}")


def _parse_sources(raw: str) -> list:
    """Best-effort catalog extraction; the raw stage payload stays in the
    doc so nothing is lost to this projection."""
    try:
        doc = json.loads(raw)
    except ValueError:
        return []
    items = None
    if isinstance(doc, dict):
        for key in ("items", "catalog", "results", "sources"):
            if isinstance(doc.get(key), list):
                items = doc[key]
                break
    elif isinstance(doc, list):
        items = doc
    out = []
    for it in items or []:
        if isinstance(it, dict):
            out.append({"id": str(it.get("id", "")),
                        "title": str(it.get("title", "")),
                        "url": str(it.get("url", ""))})
    return out


def science_run(question: str, *, claims: "list | None" = None,
                measurements: "list | None" = None,
                max_sources: int = 4, runner=None,
                workdir=None) -> dict:
    """One chained science run. `runner(argv) -> (rc, stdout)` is injectable
    for tests; live runs shell the installed lane CLIs."""
    runner = runner or _shell
    errors: dict = {}

    # Stage 1: gather evidence with provenance.
    rc, raw = runner(["gather", "arxiv", question,
                      "--max-results", str(max_sources), "--json"])
    sources = _parse_sources(raw) if rc == 0 else []
    if rc != 0:
        errors["gather"] = raw.strip()[-300:]

    # Stage 2: forge the research spec (gates priced by checkability).
    digest = "; ".join(f"{s['id']} {s['title']}" for s in sources)
    try:
        from .context_forge import forge_prp
        prp = forge_prp(question, task_type="research",
                        context=f"Sources: {digest}" if digest else "").to_dict()
    except Exception as e:
        prp = {}
        errors["forge"] = f"{type(e).__name__}: {e}"

    # Stage 3: crucible judgment of the stated claims.
    verdicts: list = []
    crucible_note = "skipped: no claims given"
    if claims:
        thesis = {"title": question, "claims": claims}
        wdir = Path(workdir or ".")
        wdir.mkdir(parents=True, exist_ok=True)
        tpath = wdir / "thesis.json"
        tpath.write_text(json.dumps(thesis, indent=1), encoding="utf-8")
        argv = ["crucible", "assess", str(tpath), "--json"]
        if measurements:
            # measurements flip UNVERIFIABLE into witnessed MATCH/DRIFT;
            # crucible's contract: {"measurements": [{claim, deviation,
            # tolerance, method, evidence}]}
            mpath = wdir / "measurements.json"
            mpath.write_text(json.dumps({"measurements": measurements},
                                        indent=1), encoding="utf-8")
            argv += ["--measurements", str(mpath)]
        rc, raw = runner(argv)
        if rc in (0, 255):  # crucible exits nonzero when claims drift; JSON still valid
            try:
                a = json.loads(raw).get("assessment", {})
                verdicts = a.get("verdicts", [])
                crucible_note = a.get("verdict_seal", "")
            except ValueError:
                errors["crucible"] = "assess did not emit JSON"
                crucible_note = "error"
        else:
            errors["crucible"] = raw.strip()[-300:]
            crucible_note = "error"

    # the chain binds EVERYTHING that produced the verdicts: the claims and
    # measurement content (not just statuses, so a widened tolerance moves
    # the hash) and the errors (so an errored run never hashes like a clean
    # one). The payload echoes claims and measurements so a stranger holding
    # only the doc can re-run the judgment.
    chain = hashlib.sha256(json.dumps({
        "question": question,
        "sources": [s["id"] for s in sources],
        "gates": prp.get("validation_gates", []),
        "claims": claims or [],
        "measurements": measurements or [],
        "verdicts": [(v.get("claim_id"), v.get("status")) for v in verdicts],
        "errors": errors,
    }, sort_keys=True).encode()).hexdigest()

    return {"schema": SCHEMA, "question": question, "sources": sources,
            "prp": prp, "claims": claims or [],
            "measurements": measurements or [],
            "verdicts": verdicts, "crucible": crucible_note,
            "errors": errors, "chain_hash": chain,
            "note": "sources carry gather provenance; UNVERIFIABLE claims "
                    "stay unverifiable until a measurement exists; the chain "
                    "hash binds claims, measurements, verdicts, and errors"}
