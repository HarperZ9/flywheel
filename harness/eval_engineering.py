"""eval_engineering.py -- the evaluation-engineering facet, named.

An eval is a criterion made executable, and evaluation engineering is
the discipline of building evals as calibrated instruments: admission
gates that reject vacuous tests, oracle-strength audits that measure
whether the judge can refuse, sealed predictions adjudicated without
narrative rescue, version-pinned lanes so old artifacts stay comparable,
honest nulls kept as first-class results, and disagreement witnessed
instead of averaged away.

This module is the facet's falsifier: a register that reports each
instrument from its live receipt on disk or in the store. A missing
artifact reads absent, never fabricated -- if the instruments rot, the
register says so. Served at GET /api/instruments; the discipline's
long form is docs/EVALUATION-ENGINEERING.md.
"""
from __future__ import annotations

import json
from pathlib import Path

SCHEMA = "flywheel.instrument-register/v1"


def _latest(pattern_dir: Path, prefix: str) -> "Path | None":
    if not pattern_dir.is_dir():
        return None
    hits = sorted(p for p in pattern_dir.glob(prefix + "*.json"))
    return hits[-1] if hits else None


def _load(path: "Path | None") -> "dict | None":
    if path is None:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _admission_gates() -> dict:
    try:
        from . import task_curator
        gates = ("reference_passes", "oracle_can_fail", "deterministic",
                 "no_solution_leak", "edge_coverage", "dedup")
        return {"name": "admission_gates", "present": True,
                "summary": f"6 gates, min {task_curator.MIN_TESTS} hidden "
                           "tests; a task enters a lane only through them",
                "receipt": "harness/task_curator.py"}
    except Exception as e:
        return {"name": "admission_gates", "present": False,
                "summary": f"curator not importable: {type(e).__name__}",
                "receipt": ""}


def _oracle_strength(root: Path) -> dict:
    path = _latest(root / "artifacts" / "audit", "oracle_strength_")
    doc = _load(path)
    if not doc:
        return {"name": "oracle_strength", "present": False,
                "summary": "no audit artifact; the oracles' floor is "
                           "unmeasured", "receipt": ""}
    return {"name": "oracle_strength", "present": True,
            "summary": f"{doc.get('hard_flags', '?')} hard flags, "
                       f"{doc.get('review_flags', '?')} mutant reviews, "
                       f"{doc.get('clean', '?')}/{doc.get('n_tasks', '?')} "
                       "clean under the non-solution battery",
            "receipt": str(path)}


def _sealed_claims(root: Path) -> dict:
    claims_dir = root / "docs" / "claims"
    theses, match, drift, unver, unsealed = 0, 0, 0, 0, 0
    if claims_dir.is_dir():
        for d in sorted(claims_dir.iterdir()):
            if not d.is_dir():
                continue
            if (d / "thesis.json").is_file():
                theses += 1
            adj = _load(d / "adjudication.json") or {}
            if not adj.get("verdicts"):
                continue
            # an adjudication is authoritative only if it carries its seals
            # (thesis + verdict + measurement); an unsealed / hand-edited
            # adjudication is NOT counted as a verdict, so it cannot launder
            # a flipped result past the register as "no rescue"
            # seals may be top-level (our adjudication summaries) or nested
            # under 'assessment' (crucible's native Assessment.to_dict shape)
            inner = adj.get("assessment") if isinstance(
                adj.get("assessment"), dict) else {}
            sealed = all((adj.get(k) or inner.get(k)) for k in
                         ("thesis_seal", "verdict_seal", "measurement_seal"))
            if not sealed:
                unsealed += 1
                continue
            for v in adj.get("verdicts", []):
                s = v.get("status", "")
                match += s == "MATCH"
                drift += s == "DRIFT"
                unver += s == "UNVERIFIABLE"
    present = theses > 0
    return {"name": "sealed_claims", "present": present,
            "match": match, "drift": drift, "unverifiable": unver,
            "unsealed_adjudications": unsealed,
            "summary": (f"{theses} sealed theses; adjudicated verdicts from "
                        f"SEALED files only: {match} MATCH, {drift} DRIFT, "
                        f"{unver} UNVERIFIABLE; {unsealed} unsealed "
                        "adjudication(s) not counted, no rescue" if present
                        else "no sealed claims on record"),
            "receipt": str(claims_dir) if present else ""}


def _uplift_lanes(root: Path) -> dict:
    updir = root / "artifacts" / "uplift"
    runs = [_load(p) for p in sorted(updir.glob("uplift_*.json"))] \
        if updir.is_dir() else []
    runs = [r for r in runs if r]
    if not runs:
        return {"name": "uplift_lanes", "present": False, "runs": 0,
                "nulls_kept": 0,
                "summary": "no uplift artifacts", "receipt": ""}
    keys = sorted({r.get("comparison_key", "") for r in runs})
    nulls = sum(1 for r in runs for d in r.get("deltas", [])
                if d.get("includes_zero") is True)
    return {"name": "uplift_lanes", "present": True, "runs": len(runs),
            "nulls_kept": nulls,
            "summary": f"{len(runs)} runs over keys {keys}; "
                       f"{nulls} interval(s) including zero kept as "
                       "honest nulls",
            "receipt": str(updir)}


def _tension_ledger() -> dict:
    try:
        from .tension_ledger import tension_ledger
        led = tension_ledger()
        return {"name": "tension_ledger", "present": led["count"] > 0,
                "entries": led["count"], "tensions": led["tensions"],
                "summary": f"{led['count']} measurement pairs banked, "
                           f"{led['tensions']} in tension, sources frozen",
                "receipt": "GET /api/tension"}
    except Exception as e:
        return {"name": "tension_ledger", "present": False, "entries": 0,
                "tensions": 0,
                "summary": f"store unavailable: {type(e).__name__}",
                "receipt": ""}


def _invention_sweeps(root: Path) -> dict:
    path = _latest(root / "artifacts" / "invention", "conjecture_sweep_")
    doc = _load(path)
    if not doc:
        return {"name": "invention_sweeps", "present": False,
                "summary": "no sweep artifact", "receipt": ""}
    return {"name": "invention_sweeps", "present": True,
            "summary": f"{doc.get('accepted_total', '?')} kernel-accepted "
                       f"of {doc.get('grammar_size', '?')} proposed; "
                       f"{doc.get('declared_total', 0)} declared",
            "receipt": str(path)}


def instrument_register(root: "str | Path | None" = None) -> dict:
    """Every instrument of the discipline, read from its live receipt."""
    root = Path(root) if root else Path(__file__).resolve().parents[1]
    instruments = [
        _admission_gates(),
        _oracle_strength(root),
        _sealed_claims(root),
        _uplift_lanes(root),
        _tension_ledger(),
        _invention_sweeps(root),
    ]
    return {"schema": SCHEMA,
            "instruments": instruments,
            "present_count": sum(1 for i in instruments if i["present"]),
            "total": len(instruments),
            "note": "an eval is a criterion made executable; this register "
                    "reads each instrument's live receipt and reports "
                    "absence honestly -- if the instruments rot, it says so"}
