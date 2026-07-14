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
import json
import sys
from pathlib import Path

HET = 0.666
HET_LO, HET_HI = 0.595, 0.737
IID = 0.759
ORACLE_SHA = "0b898a620223a06eeeee4244bd6e6935c53eecd4b742d9d220bdd5a96d91a89d"
CLAIMS = {
    "c-14b-k5-interval":
        "633c6a73a7e4c3c091e39dedce3a003e0a0537b7d22ce92b2955712357872e88",
    "c-14b-k5-het-beats-iid":
        "4e655d6481601e2fed831d22732c514fb112ccd0565cbc571a0ee3083d1a211c",
    "c-14b-k5-iid-beats-het":
        "9b91597ec8e55a0eb36d8194bd27021a95f871faa11c719c6b2abfdfeed33232",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", required=True)
    ap.add_argument("--out",
                    default="docs/claims/2026-07-14-passk-forecast/"
                            "adjudication-measurements.json")
    a = ap.parse_args()
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
