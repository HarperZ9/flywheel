"""Re-emit a partial adjudication summary as a full re-derivable record.

The early adjudication summaries displayed four seals whose preimage
(measurement rows with timestamps, margins, grounds, started_at) was never
persisted, so no stranger could recompute them: decorative seals. This script
re-derives the assessment through crucible from the SAME on-disk thesis and
the SAME measurement values under the SAME frozen rule, with an injected
zero clock so the record replays byte-exact forever. Verdict statuses are
asserted unchanged against the old summary before anything is written: this
is a preimage repair, never a rescue.

Usage: python scripts/emit_full_adjudication.py docs/claims/<folder>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from crucible.assess import assess, recheck_assessment
from crucible.claim import make_claim
from crucible.thesis import make_thesis
from crucible.verdict import Measurement

_CLOCK = lambda: 0.0  # noqa: E731 - injected so the record replays


def emit(base: Path) -> dict:
    tj = json.loads((base / "thesis.json").read_text(encoding="utf-8"))
    mj = json.loads((base / "adjudication-measurements.json").read_text(encoding="utf-8"))
    old = json.loads((base / "adjudication.json").read_text(encoding="utf-8"))

    claims = [make_claim(c["text"], c.get("falsification", ""), id=c.get("id"))
              for c in tj["claims"]]
    sha = {c.id: c.sha256 for c in claims}
    thesis = make_thesis(tj["title"], claims, clock=_CLOCK)
    ms = [Measurement(m["claim"], sha[m["claim"]], m.get("deviation"),
                      m.get("tolerance", 0.0), m.get("method", ""), 0.0,
                      tuple(m.get("evidence", ())))
          for m in mj["measurements"]]
    record, verdicts = assess(thesis, ms, clock=_CLOCK)

    old_status = {v["claim_id"]: v["status"] for v in old.get("verdicts", [])}
    new_status = {v.claim_id: v.status for v in verdicts}
    if old_status != new_status:
        raise SystemExit(f"refusing to write: verdicts changed {old_status} -> "
                         f"{new_status}. A preimage repair must not move a verdict.")

    check = recheck_assessment(thesis, record)
    if not all(check.get(k) for k in ("seals_ok", "thesis_ok", "verdicts_rederive")):
        raise SystemExit(f"refusing to write: re-derivation failed {check}")

    doc = {
        "schema": "flywheel.adjudication/v2",
        "assessment": record.to_dict(),
        "evidence": old.get("evidence", []),
        "note": old.get("note", ""),
        "regenerated": ("full re-derivable record emitted 2026-07-15; the "
                        "earlier summary displayed seals whose preimage was "
                        "never persisted. Same thesis, same measurement "
                        "values, same frozen rule, injected zero clock; "
                        "verdict statuses asserted unchanged before writing."),
    }
    (base / "adjudication.json").write_text(json.dumps(doc, indent=1) + "\n",
                                            encoding="utf-8")
    return {"folder": str(base), "verdicts": new_status,
            "assessment_seal": record.seal, "thesis_seal": record.thesis_seal}


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        print(json.dumps(emit(Path(arg)), indent=1))
