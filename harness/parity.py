"""parity.py -- the capability matrix, witnessed not asserted.

Every Flywheel row names a WITNESS inside this repo (a module, a route
string in the gateway source, a test file) and the audit CHECKS it: a row
whose witness is missing reports ABSENT, so the matrix can fail. Competitor
cells are dated DECLARATIONS from public docs and configs, never
measurements; they are labeled as such and carry no verdict weight. The
summary names both what is uniquely witnessed here and where the field is
ahead -- the gap list is the point, not the scoreboard.

A row is uniquely witnessed only when EVERY peer cell reads False. Two
weaker rules were in place before and both inflated the count. The star
used to survive a peer cell of "partial", so a capability three products
part-ship counted as one nobody declares. It also used to survive a cell
nobody had read, because absence and ignorance shared one value. `None`
now means not determined, it suppresses the star, and the count on the
published page fell when that landed.

The row set is a choice this project made, so an empty gap list cannot be
read on its own: no row means no gap, whatever the peers ship. The capability
areas found in the peers' own page indexes that no row here scores are named
in `parity_coverage`, with a disposition and a reason for each, and the counts
ride along in the summary."""
from __future__ import annotations

import re
from pathlib import Path

from .parity_coverage import coverage_summary
from .parity_peers import PEER_KEYS, PEERS, VALUES, declarations_for
from .parity_rows import ROWS

REPO = Path(__file__).resolve().parent.parent

#: The newest peer read date, derived rather than typed, so the date on the
#: page cannot outlive the reading it stands for.
DECLARED_ON = max(p["read_on"] for p in PEERS)

# Re-exported so `parity.ROWS` stays the one name callers and tests reach
# for. parity_matrix reads it off this module at call time, which is what
# lets a test swap in a row with a missing witness and watch the audit fail.
__all__ = ["ROWS", "PEERS", "PEER_KEYS", "VALUES", "DECLARED_ON",
           "parity_matrix"]


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


def _audit_row(row: dict, gateway_src: str) -> dict:
    checks = [{"kind": k, "ref": ref,
               "present": _check_witness(k, ref, gateway_src)}
              for k, ref in row["witnesses"]]
    ok = all(c["present"] for c in checks)
    return {"key": row["key"], "desc": row["desc"],
            "flywheel": "WITNESSED" if ok else "ABSENT",
            "checks": checks, "competitors": declarations_for(row["key"])}


def parity_matrix() -> dict:
    """Audit every row's witnesses against this repo, right now."""
    gateway_src = (REPO / "harness" / "gateway.py").read_text(
        encoding="utf-8", errors="replace")
    rows = [_audit_row(r, gateway_src) for r in ROWS]
    witnessed = sum(r["flywheel"] == "WITNESSED" for r in rows)
    unique, gaps, undetermined = [], [], []
    for r in rows:
        ok = r["flywheel"] == "WITNESSED"
        cells = r["competitors"].values()
        # Every cell literally False. A "partial" is a declaration and an
        # unread cell is not evidence, so neither one earns the star.
        if ok and all(v is False for v in cells):
            unique.append(r["key"])
        if not ok and any(v is True for v in cells):
            gaps.append(r["key"])
        if any(v is None for v in cells):
            undetermined.append(r["key"])
    return {"schema": "flywheel.parity/v2",
            "declared_on": DECLARED_ON,
            "peers": [dict(p) for p in PEERS],
            "note": "flywheel cells are audited against this repo at read "
                    "time; peer cells are dated declarations from public "
                    "docs and source, not measurements, and a null cell "
                    "means nobody here has read that surface",
            "rows": rows,
            "summary": {"witnessed": witnessed,
                        "absent": len(rows) - witnessed,
                        "uniquely_witnessed": unique, "gaps": gaps,
                        "undetermined": undetermined,
                        # An empty gap list is a statement about rows that
                        # exist. `parity_coverage` names what the peers ship
                        # that no row scores, so the denominator this project
                        # chose travels with the result it produces.
                        "coverage": coverage_summary()}}
