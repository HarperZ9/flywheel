"""risk_review.py -- risk tiers for machine edits, from signals not vibes.

The dossier's review finding with the sharpest edge: complexity, not
provenance labels, drives wrongful acceptance -- reviewers wave through
wrong code exactly where it is hardest to read (ACM 10.1145/3808165), and
AI redundancy is masked by positive sentiment (arXiv 2601.21276). So every
edit an agent makes carries mechanical signals -- lines added, nesting
depth, branching density, duplicate lines -- a documented weighted risk,
and a tier. High-tier edits DEMAND a stronger receipt (oracle coverage
plus full-coverage attestation); the demand is data a surface can enforce,
not a judgment this module makes. Signals come from the ledger only.
"""
from __future__ import annotations

import json

SCHEMA = "flywheel.risk-review/v1"

_WEIGHTS = {"size": 0.25, "depth": 0.35, "branch": 0.25, "dupes": 0.15}
# Normalization ceilings: a signal at or past the ceiling scores 1.0.
_CEILING = {"size": 120.0, "depth": 6.0, "branch": 0.35, "dupes": 10.0}
_BRANCH_TOKENS = ("if ", "elif ", "else:", "for ", "while ", "except",
                  "case ", "and ", "or ")


def _field(entry, name, default=None):
    if isinstance(entry, dict):
        return entry.get(name, default)
    return getattr(entry, name, default)


def _signals(text: str) -> dict:
    lines = [l for l in (text or "").splitlines() if l.strip()]
    n = len(lines)
    depth = 0
    branches = 0
    seen: dict = {}
    dupes = 0
    for l in lines:
        indent = len(l) - len(l.lstrip(" "))
        depth = max(depth, indent // 4 + 1)
        s = l.strip()
        branches += sum(1 for t in _BRANCH_TOKENS if t in s)
        if len(s) > 8:
            seen[s] = seen.get(s, 0) + 1
    dupes = sum(c - 1 for c in seen.values() if c > 1)
    return {"lines_added": n, "max_depth": depth,
            "branch_density": round(branches / n, 4) if n else 0.0,
            "duplicate_lines": dupes}


def _risk(sig: dict) -> float:
    parts = {
        "size": min(1.0, sig["lines_added"] / _CEILING["size"]),
        "depth": min(1.0, sig["max_depth"] / _CEILING["depth"]),
        "branch": min(1.0, sig["branch_density"] / _CEILING["branch"]),
        "dupes": min(1.0, sig["duplicate_lines"] / _CEILING["dupes"]),
    }
    return round(sum(_WEIGHTS[k] * v for k, v in parts.items()), 4)


def _tier(risk: float) -> str:
    return "high" if risk >= 0.55 else "elevated" if risk >= 0.3 else "low"


def _edit_content(name: str, args: dict) -> "tuple | None":
    if name == "write_file" and args.get("path"):
        return str(args["path"]), args.get("content", "")
    if name == "edit_file" and args.get("path"):
        return str(args["path"]), args.get("new", "")
    if name == "apply_patch":
        patch = args.get("patch") or args.get("diff") or ""
        added = "\n".join(l[1:] for l in patch.splitlines()
                          if l.startswith("+") and not l.startswith("+++"))
        paths = [l[6:].strip() for l in patch.splitlines()
                 if l.startswith("+++ b/")]
        return (paths[0] if paths else "(patch)"), added
    return None


def risk_review(entries: list) -> dict:
    """Project the ledger's edits into risk rows plus the demands table."""
    edits = []
    for entry in entries:
        if _field(entry, "kind", "") != "tool_call":
            continue
        content = _field(entry, "content", "") or ""
        name, _, rest = content.partition(" ")
        try:
            args = json.loads(rest) if rest else {}
        except ValueError:
            args = {}
        if not isinstance(args, dict):
            continue
        hit = _edit_content(name, args)
        if hit is None:
            continue
        path, text = hit
        sig = _signals(text)
        risk = _risk(sig)
        edits.append({"path": path, "tool": name, **sig,
                      "risk": risk, "tier": _tier(risk)})
    demands = [
        {"path": e["path"], "tier": e["tier"],
         "requires": "stronger receipt: oracle-covered edit plus "
                     "full-coverage attestation"}
        for e in edits if e["tier"] == "high"]
    return {"schema": SCHEMA, "edits": edits, "demands": demands,
            "weights": _WEIGHTS, "ceilings": _CEILING,
            "tiers": {"high": 0.55, "elevated": 0.3},
            "note": "signals from the ledger only; the demand is data a "
                    "surface enforces, not a verdict this module renders"}
