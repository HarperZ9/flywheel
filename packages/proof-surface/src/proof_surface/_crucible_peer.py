"""Crucible as an explicit optional peer.

When crucible (published as ``crucible-bench``) is importable, ``assess_with_crucible``
runs it in-process and returns a sealed, re-derivable assessment agreeing with the
packet's embedded verdict. When it is absent, this returns None and the stdlib
validator still fully gates admission -- removing crucible weakens seal
re-derivability, it never opens the gate. Stdlib-only; crucible is imported lazily.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def crucible_available() -> bool:
    try:
        import crucible  # noqa: F401

        return True
    except Exception:
        return False


def assess_with_crucible(
    thesis_data: dict[str, Any], measurements_data: dict[str, Any]
) -> dict[str, Any] | None:
    """Return {overall, counts, seal} from real crucible, or None if unavailable."""
    try:
        import crucible
    except Exception:
        return None
    try:
        claims = [
            crucible.make_claim(c["text"], c.get("falsification", ""))
            for c in thesis_data.get("claims", [])
        ]
        thesis = crucible.make_thesis(
            thesis_data.get("title", "proof-surface peer"),
            claims,
            clock=lambda: 0.0,
            disposition=thesis_data.get("disposition", "publishable"),
        )
        by_text = {c.text: c for c in claims}
        measurements = []
        for row in measurements_data.get("measurements", []):
            claim = by_text.get(row.get("claim"))
            if claim is None:
                continue
            measurements.append(
                crucible.Measurement(
                    claim.id,
                    claim.sha256,
                    row.get("deviation"),
                    float(row.get("tolerance", 0.0)),
                    row.get("method", ""),
                    0.0,
                    tuple(row.get("evidence", ())),
                )
            )
        assessment, verdicts = crucible.assess(thesis, measurements)
        counts = {
            "match": sum(1 for v in verdicts if v.status == "MATCH"),
            "drift": sum(1 for v in verdicts if v.status == "DRIFT"),
            "unverifiable": sum(1 for v in verdicts if v.status == "UNVERIFIABLE"),
        }
        overall = (
            "UNVERIFIABLE"
            if counts["unverifiable"]
            else "DRIFT"
            if counts["drift"]
            else "MATCH"
        )
        return {
            "overall": overall,
            "counts": counts,
            "seal": getattr(assessment, "seal", None),
        }
    except Exception:
        return None


def write_peer_assessment(
    out_dir: str | Path, thesis_data: dict[str, Any], measurements_data: dict[str, Any]
) -> str | None:
    """Write crucible-assessment.json if crucible is present; return the seal or None."""
    result = assess_with_crucible(thesis_data, measurements_data)
    if result is None:
        return None
    (Path(out_dir) / "crucible-assessment.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result.get("seal")
