"""parity.py -- the capability matrix, witnessed not asserted.

Every Flywheel row names a WITNESS inside this repo (a module, a route
string in the gateway source, a test file) and the audit CHECKS it: a row
whose witness is missing reports ABSENT, so the matrix can fail. Competitor
cells are dated DECLARATIONS from public docs and configs, never
measurements; they are labeled as such and carry no verdict weight. The
summary names both what is uniquely witnessed here and where the field is
ahead -- the gap list is the point, not the scoreboard."""
from __future__ import annotations

import re
from pathlib import Path

from .parity_rows import ROWS

REPO = Path(__file__).resolve().parent.parent

DECLARED_ON = "2026-09-03"

# Re-exported so `parity.ROWS` stays the one name callers and tests reach
# for. parity_matrix reads it off this module at call time, which is what
# lets a test swap in a row with a missing witness and watch the audit fail.
__all__ = ["ROWS", "DECLARED_ON", "parity_matrix"]


def _route_witnessed(ref: str, src: str) -> bool:
    """A route witness must find the route SERVED, not merely mentioned.

    `ref in src` cannot tell a call site from a definition, so a handler that
    is only ever called audits as present: `live-agent-stream` reported
    WITNESSED for months on the strength of `self._sse_agent(...)` at its one
    call site, while no such method existed and the route raised
    AttributeError on first use. A matrix that cannot catch that is the
    theater its own tests warn about.

    An HTTP path is witnessed by a dispatch comparison against it. A bare
    identifier is witnessed by a `def`.
    """
    if ref.startswith("/"):
        quoted = (f'"{ref}"', f"'{ref}'")
        return any(
            f"== {q}" in src or f"=={q}" in src
            or f".startswith({q}" in src or f"{q}:" in src or f"{q}," in src
            for q in quoted)
    return bool(re.search(rf"^\s*(?:async\s+)?def\s+{re.escape(ref)}\s*\(",
                          src, re.M))


def _check_witness(kind: str, ref: str, gateway_src: str) -> bool:
    if kind == "module" or kind == "test":
        return (REPO / ref).is_file()
    if kind == "route":
        return _route_witnessed(ref, gateway_src)
    return False


def parity_matrix() -> dict:
    """Audit every row's witnesses against this repo, right now."""
    gateway_src = (REPO / "harness" / "gateway.py").read_text(
        encoding="utf-8", errors="replace")
    rows = []
    witnessed = absent = 0
    unique = []
    gaps = []
    for r in ROWS:
        checks = [{"kind": k, "ref": ref,
                   "present": _check_witness(k, ref, gateway_src)}
                  for k, ref in r["witnesses"]]
        ok = all(c["present"] for c in checks)
        witnessed += ok
        absent += not ok
        competitors = {c: r[c] for c in ("codex", "cursor", "claude-code")}
        if ok and not any(v is True for v in competitors.values()):
            unique.append(r["key"])
        if not ok and any(v is True for v in competitors.values()):
            gaps.append(r["key"])
        rows.append({"key": r["key"], "desc": r["desc"],
                     "flywheel": "WITNESSED" if ok else "ABSENT",
                     "checks": checks, "competitors": competitors})
    return {"schema": "flywheel.parity/v1",
            "declared_on": DECLARED_ON,
            "note": "flywheel cells are audited against this repo at read "
                    "time; competitor cells are dated declarations from "
                    "public docs and configs, not measurements",
            "rows": rows,
            "summary": {"witnessed": witnessed, "absent": absent,
                        "uniquely_witnessed": unique, "gaps": gaps}}
