"""review.py -- the reviewability projection of a witnessed agent run (zero-dep).

Every run already carries a hash-chained ledger. This projects it into the terms a
senior reviewer checks first, as FACTS from the ledger, never generated narrative:

- run_review(entries): process signals --
    edited_unread     files edited without ever being read first;
    unverified_edits  edits no passing acceptance check covered afterwards;
    failed_calls      the retry scars, kept visible;
    gate_denials      policy verdicts (a receipt, not a stumble);
    reviewability     re-derivable arithmetic over read-before-write, verified, clean.
- risk_review(entries): per-edit complexity signals (lines, nesting, branching,
    duplicate lines) -> a weighted risk and a tier; a high tier DEMANDS a stronger
    receipt. The demand is data a surface enforces, not a verdict this module renders.

Ported from the flywheel engine's run_review/risk_review, adapted to relay: the
verification event is relay's acceptance `check` entry (relay verifies the whole edit
set once, at the end), and relay has no apply_patch.
"""
from __future__ import annotations

import json

from .local_tools import edited_targets

RUN_SCHEMA = "relay.run-review/v1"
RISK_SCHEMA = "relay.risk-review/v1"

_READ_TOOLS = {"read_file"}


def _field(entry, name, default=None):
    if isinstance(entry, dict):
        return entry.get(name, default)
    return getattr(entry, name, default)


def _parse_call(content: str) -> tuple:
    name, _, rest = (content or "").partition(" ")
    try:
        args = json.loads(rest) if rest else {}
    except ValueError:
        args = {}
    return name, args if isinstance(args, dict) else {}


def run_review(entries: list) -> dict:
    """Project ledger entries (dicts or Entry objects) into the review doc."""
    reads: set = set()
    writes: list = []            # (order, path, was_read)
    failed_calls = 0
    gate_denials: list = []
    last_green = -1
    n_calls = 0
    order = 0
    for entry in entries:
        kind = _field(entry, "kind", "")
        if kind == "tool_call":
            order += 1
            n_calls += 1
            name, args = _parse_call(_field(entry, "content", ""))
            if name in _READ_TOOLS and args.get("path"):
                reads.add(str(args["path"]))
            else:
                for path, _new in edited_targets(name, args):
                    writes.append((order, path, path in reads))
        elif kind == "tool_result":
            meta = _field(entry, "meta", {}) or {}
            content = _field(entry, "content", "") or ""
            if content.startswith("[gate]"):
                gate_denials.append({"tool": str(meta.get("tool", "")),
                                     "rule": content.strip()[:200]})
            elif meta.get("ok") is False:
                failed_calls += 1
        elif kind == "check":
            # relay's acceptance check verifies the whole edit set at once: a PASS
            # marks every edit made before it as verified.
            if (_field(entry, "meta", {}) or {}).get("ok") is True:
                last_green = order

    edited_unread = sorted({p for _, p, was_read in writes if not was_read})
    unverified = sorted({p for o, p, _ in writes if o > last_green})
    n_writes = len(writes)
    read_ratio = (sum(1 for _, _, r in writes if r) / n_writes) if n_writes else 1.0
    verified_ratio = (sum(1 for o, _, _ in writes if o <= last_green)
                      / n_writes) if n_writes else 1.0
    clean_ratio = (1.0 - failed_calls / n_calls) if n_calls else 1.0
    score = round(0.4 * read_ratio + 0.4 * verified_ratio + 0.2 * clean_ratio, 4)
    return {
        "schema": RUN_SCHEMA,
        "edited_unread": edited_unread,
        "unverified_edits": unverified,
        "failed_calls": failed_calls,
        "gate_denials": gate_denials,
        "files_read": sorted(reads),
        "files_edited": sorted({p for _, p, _ in writes}),
        "reviewability": score,
        "signals": {
            "read_before_write_ratio": round(read_ratio, 4),
            "verified_edit_ratio": round(verified_ratio, 4),
            "clean_call_ratio": round(clean_ratio, 4),
            "weights": {"read": 0.4, "verified": 0.4, "clean": 0.2},
        },
        "note": "facts from the witnessed ledger only; any prose a surface adds on "
                "top must be labeled as prose",
    }


_RISK_WEIGHTS = {"size": 0.25, "depth": 0.35, "branch": 0.25, "dupes": 0.15}
_RISK_CEILING = {"size": 120.0, "depth": 6.0, "branch": 0.35, "dupes": 10.0}
_BRANCH_TOKENS = ("if ", "elif ", "else:", "for ", "while ", "except",
                  "case ", "and ", "or ")


def _signals(text: str) -> dict:
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    n = len(lines)
    depth = 0
    branches = 0
    seen: dict = {}
    for ln in lines:
        indent = len(ln) - len(ln.lstrip(" "))
        depth = max(depth, indent // 4 + 1)
        s = ln.strip()
        branches += sum(1 for t in _BRANCH_TOKENS if t in s)
        if len(s) > 8:
            seen[s] = seen.get(s, 0) + 1
    dupes = sum(c - 1 for c in seen.values() if c > 1)
    return {"lines_added": n, "max_depth": depth,
            "branch_density": round(branches / n, 4) if n else 0.0,
            "duplicate_lines": dupes}


def _risk(sig: dict) -> float:
    parts = {
        "size": min(1.0, sig["lines_added"] / _RISK_CEILING["size"]),
        "depth": min(1.0, sig["max_depth"] / _RISK_CEILING["depth"]),
        "branch": min(1.0, sig["branch_density"] / _RISK_CEILING["branch"]),
        "dupes": min(1.0, sig["duplicate_lines"] / _RISK_CEILING["dupes"]),
    }
    return round(sum(_RISK_WEIGHTS[k] * v for k, v in parts.items()), 4)


def _tier(risk: float) -> str:
    return "high" if risk >= 0.55 else "elevated" if risk >= 0.3 else "low"


def risk_review(entries: list) -> dict:
    """Project the ledger's edits into risk rows plus the demands table."""
    edits = []
    for entry in entries:
        if _field(entry, "kind", "") != "tool_call":
            continue
        name, args = _parse_call(_field(entry, "content", ""))
        for path, text in edited_targets(name, args):
            sig = _signals(text)
            risk = _risk(sig)
            edits.append({"path": path, "tool": name, **sig,
                          "risk": risk, "tier": _tier(risk)})
    demands = [
        {"path": e["path"], "tier": e["tier"],
         "requires": "stronger receipt: an acceptance check covering this edit"}
        for e in edits if e["tier"] == "high"]
    return {"schema": RISK_SCHEMA, "edits": edits, "demands": demands,
            "weights": _RISK_WEIGHTS, "ceilings": _RISK_CEILING,
            "tiers": {"high": 0.55, "elevated": 0.3},
            "note": "signals from the ledger only; the demand is data a surface "
                    "enforces, not a verdict this module renders"}
