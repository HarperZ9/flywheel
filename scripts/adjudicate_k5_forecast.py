"""Adjudicate the sealed k=5 rival forecasts against the landed bench.

The rule was frozen before the bench existed
(docs/claims/2026-07-14-passk-forecast/README.md): score BOTH
pre-registered models by absolute error against the measured wrapped
best-of-5 pass rate of ollama:telos-coder-14b on hard_v2; whichever
errs more is the falsified one; a miss by both is two falsifications,
not a draw. This script only computes and writes; it cannot rescue.

  python scripts/adjudicate_k5_forecast.py --artifact artifacts/uplift/<file>.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ORACLE_SHA = "0b898a620223a06eeeee4244bd6e6935c53eecd4b742d9d220bdd5a96d91a89d"
_DEFAULT_BASE = Path("docs/claims/2026-07-14-passk-forecast")


def _seal_ok(doc: dict) -> bool:
    """Re-derive the forecast seal (sha256 over the canonical doc minus the
    seal field, exactly as passn_model sealed it) and compare."""
    body = {k: v for k, v in doc.items() if k != "seal"}
    recomputed = hashlib.sha256(
        json.dumps(body, sort_keys=True).encode()).hexdigest()
    return recomputed == doc.get("seal")


def sealed_constants(base: "str | Path" = _DEFAULT_BASE) -> dict:
    """Read the adjudication constants FROM the sealed record at run time
    instead of hand-retyping them. The re-typed constants were lossy: the
    rounded band [0.595, 0.737] is wider at BOTH ends than the sealed
    [0.5952, 0.7365], so a measured rate of 0.5951 read INSIDE the script yet
    OUTSIDE the seal. This verifies the forecast seal, takes het/interval/iid
    unrounded from the record, re-derives the claim shas from the sealed thesis
    (as emit_full_adjudication does), and asserts the pinned oracle hash is
    bound verbatim in the interval claim text."""
    base = Path(base)
    forecast = json.loads(
        (base / "FORECAST-14B-K5.json").read_text(encoding="utf-8"))
    if not _seal_ok(forecast):
        raise SystemExit(f"REFUSED: forecast record seal does not verify "
                         f"at {base}; a tampered record cannot adjudicate")
    het = forecast["expected_pass_rate"]
    het_lo, het_hi = forecast["interval_95"]
    iid = forecast["iid_baseline"]["expected_pass_rate"]
    tj = json.loads((base / "thesis.json").read_text(encoding="utf-8"))
    from crucible.claim import make_claim
    claims = {c["id"]: make_claim(c["text"], c.get("falsification", ""),
                                  id=c.get("id")).sha256
              for c in tj["claims"]}
    interval_text = next(c["text"] for c in tj["claims"]
                         if c["id"] == "c-14b-k5-interval")
    if ORACLE_SHA not in interval_text:
        raise SystemExit("REFUSED: the pinned oracle hash is not bound in the "
                         "sealed interval claim text")
    return {"het": het, "het_lo": het_lo, "het_hi": het_hi, "iid": iid,
            "claims": claims, "oracle_sha": ORACLE_SHA}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", required=True)
    ap.add_argument("--claims-dir", default=str(_DEFAULT_BASE),
                    help="the sealed forecast folder the constants derive from")
    ap.add_argument("--out",
                    default="docs/claims/2026-07-14-passk-forecast/"
                            "adjudication-measurements.json")
    a = ap.parse_args()
    sc = sealed_constants(a.claims_dir)
    HET, HET_LO, HET_HI, IID = sc["het"], sc["het_lo"], sc["het_hi"], sc["iid"]
    CLAIMS = sc["claims"]
    doc = json.loads(Path(a.artifact).read_text(encoding="utf-8"))
    if doc.get("oracle", {}).get("source_sha256") != ORACLE_SHA:
        print("REFUSED: artifact oracle hash does not match the sealed "
              "judge; the forecast is pinned to hard_v2 as sealed")
        return 2
    wrapped = next((r for r in doc.get("rows", [])
                    if r.get("arm") == "wrapped"
                    and r.get("provider") == "ollama:telos-coder-14b"
                    and r.get("n_candidates") == 5), None)
    if wrapped is None:
        print("REFUSED: no wrapped best-of-5 telos-coder-14b row")
        return 2
    measured = wrapped["passes"] / wrapped["graded"]
    err_het = abs(measured - HET)
    err_iid = abs(measured - IID)
    in_interval = HET_LO <= measured <= HET_HI
    rows = [
        {"claim_id": "c-14b-k5-interval",
         "claim_sha256": CLAIMS["c-14b-k5-interval"],
         "deviation": round(abs(measured - HET), 4),
         "tolerance": round(HET_HI - HET, 4),
         "method": f"measured wrapped best-of-5 = {wrapped['passes']}/"
                   f"{wrapped['graded']} = {measured:.4f}; sealed interval "
                   f"[{HET_LO}, {HET_HI}]; inside = {in_interval}",
         "evidence": [a.artifact]},
        {"claim_id": "c-14b-k5-het-beats-iid",
         "claim_sha256": CLAIMS["c-14b-k5-het-beats-iid"],
         "deviation": 0.0 if err_het < err_iid else round(
             err_het - err_iid, 4),
         "tolerance": 0.0,
         "method": f"err(het)={err_het:.4f} vs err(iid)={err_iid:.4f}; "
                   "het wins iff strictly smaller",
         "evidence": [a.artifact]},
        {"claim_id": "c-14b-k5-iid-beats-het",
         "claim_sha256": CLAIMS["c-14b-k5-iid-beats-het"],
         "deviation": 0.0 if err_iid < err_het else round(
             err_iid - err_het, 4),
         "tolerance": 0.0,
         "method": f"err(iid)={err_iid:.4f} vs err(het)={err_het:.4f}; "
                   "iid wins iff strictly smaller",
         "evidence": [a.artifact]},
    ]
    Path(a.out).write_text(json.dumps({"measurements": rows}, indent=1),
                           encoding="utf-8")
    print(f"measured wrapped best-of-5: {measured:.4f} "
          f"({wrapped['passes']}/{wrapped['graded']})")
    print(f"interval [{HET_LO}, {HET_HI}]: "
          f"{'INSIDE' if in_interval else 'OUTSIDE'}")
    print(f"err het {err_het:.4f} | err iid {err_iid:.4f} -> "
          f"{'het' if err_het < err_iid else 'iid'} errs less; "
          f"the other is falsified")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
