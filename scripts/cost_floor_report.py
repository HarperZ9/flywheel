"""cost_floor_report.py -- cost receipts for every call in a logged run.

Reads a flywheel.effort-gate-log/v1 file (per-call wall time and provider token
counts) and writes one receipt per call plus a summary, checked against the bar
in project-docs/records/cost-floor/DECISION.md.

  python scripts/cost_floor_report.py project-docs/records/search-effort-gate/live-hard_v2.json \
      --params 14770033664 --weight-bytes 8988111146 --hardware rtx-4090
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.cost_floor import ModelProfile, receipt, summarize  # noqa: E402


def calls(doc: dict) -> list[dict]:
    out = []
    for row in doc["rows"]:
        if "excluded" in row:
            continue
        out += [row["single_cost"]] + list(row["cost"])
    return out


def report(docs: list[dict], model: ModelProfile, hardware: str) -> dict:
    timed, untimed = [], 0
    for doc in docs:
        for c in calls(doc):
            if c.get("completion_tokens") is None:
                untimed += 1
                continue
            timed.append(receipt(c["secs"], int(c.get("prompt_tokens") or 0),
                                 int(c["completion_tokens"]), model, hardware))
    s = summarize(timed)
    decode = sum(r["phases"]["decode_s"] for r in timed)
    s["decode_share_of_floor"] = round(decode / s["floor_s"], 4) if s["floor_s"] else None
    s["untimed_calls"] = untimed
    s["bar"] = {"coverage": untimed == 0 and len(timed) > 0,
                "measured_at_or_above_floor": s["below_floor"] == 0}
    return {"summary": s, "example": timed[0] if timed else None}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--params", type=int, required=True)
    ap.add_argument("--weight-bytes", type=int, required=True)
    ap.add_argument("--hardware", default="rtx-4090")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    docs = [json.loads(Path(p).read_text(encoding="utf-8")) for p in a.logs]
    out = report(docs, ModelProfile(a.params, a.weight_bytes), a.hardware)
    text = json.dumps(out, indent=1)
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if all(out["summary"]["bar"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
