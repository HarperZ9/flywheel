"""effort.py -- one knob, and the receipt the knob's inventors forgot.

Amp's Dial (2026-07-09) replaced a zoo of modes with a single effort
level; the import keeps the knob and adds the record: the resolved effort
-- name and every parameter it set -- is stamped into the run receipt, so
a low-effort result and an ultra-effort result are comparable artifacts
rather than indistinguishable outputs. Unknown levels fall back to
standard with the fallback NAMED in the receipt, never silently.
"""
from __future__ import annotations

EFFORTS: dict = {
    "low":      {"max_steps": 4,  "n_candidates": 1},
    "standard": {"max_steps": 8,  "n_candidates": 2},
    "high":     {"max_steps": 12, "n_candidates": 3},
    "ultra":    {"max_steps": 12, "n_candidates": 5},
}


def resolve_effort(name: str) -> dict:
    """The dial position as a named, receipt-ready parameter set."""
    key = (name or "").strip().lower()
    if key in EFFORTS:
        return {"name": key, **EFFORTS[key]}
    return {"name": "standard", **EFFORTS["standard"],
            "note": f"unknown effort '{name}'; standard used and named"}


def stamp_applied(effort: dict, *, max_steps_applied: int,
                  n_candidates_applied: bool = False) -> dict:
    """Reconcile the receipt with what the run ACTUALLY enforced. A caller can
    override max_steps past the dial, and this route does not fan out n
    candidates, so the receipt must not assert the dial's nominal values as if
    they were applied. Records the applied step budget, flags an override when
    it differs from the dial, and marks whether n_candidates was applied."""
    out = dict(effort)
    out["max_steps_applied"] = int(max_steps_applied)
    out["max_steps_overridden"] = int(max_steps_applied) != int(effort.get("max_steps", max_steps_applied))
    out["n_candidates_applied"] = bool(n_candidates_applied)
    return out
