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


# The candidate budget each dial position authorizes for a selection loop.
# The dial has two parameters and a route enforces whichever one it actually
# has. `max_steps` names an agent's step ceiling; a selection loop has no
# steps, it has candidates, and `n_candidates` is the parameter that names
# them. Written as a table rather than derived at the call site, so the policy
# and the receipt read from one place. `standard` matches the gateway seat's
# constructed default, so sending the dial's middle position and sending no
# dial at all agree rather than quietly differing.
CANDIDATE_BUDGET: dict = {
    "low":      {"initial_n": 1,  "max_n": 4},
    "standard": {"initial_n": 4,  "max_n": 16},
    "high":     {"initial_n": 8,  "max_n": 32},
    "ultra":    {"initial_n": 16, "max_n": 64},
}


def candidate_budget(effort: dict) -> dict:
    """The candidate budget a resolved dial authorizes. Reads the resolved
    name, so an unknown level that already fell back to standard gets
    standard's budget rather than a second, differently-shaped fallback."""
    name = str(effort.get("name", ""))
    return dict(CANDIDATE_BUDGET.get(name, CANDIDATE_BUDGET["standard"]))


def stamp_candidates(effort: dict, *, initial_n_applied: int,
                     max_n_applied: int, candidates_generated: int) -> dict:
    """Reconcile the receipt with the candidate budget the loop ACTUALLY ran.

    The sibling of `stamp_applied`, for a route whose budget is candidates.
    Calling `stamp_applied` here would assert a step count that nothing
    enforced, which is the exact failure that function exists to prevent, so
    the step fields stay nominal and `applied` names the dimension the run
    really honored.
    """
    nominal = CANDIDATE_BUDGET.get(str(effort.get("name", "")), {})
    out = dict(effort)
    out["applied"] = "candidates"
    out["initial_n"] = nominal.get("initial_n")
    out["max_n"] = nominal.get("max_n")
    out["initial_n_applied"] = int(initial_n_applied)
    out["max_n_applied"] = int(max_n_applied)
    out["max_n_overridden"] = nominal.get("max_n") != int(max_n_applied)
    out["candidates_generated"] = int(candidates_generated)
    out["n_candidates_applied"] = True
    return out


def stamp_unapplied(effort: dict, reason: str) -> dict:
    """The dial was set and nothing spent it. A proof-cache hit answers before
    the loop runs, so reporting a budget there would describe generations that
    never happened. The level stays visible with the reason it went unused."""
    out = dict(effort)
    out["applied"] = "none"
    out["candidates_generated"] = 0
    out["n_candidates_applied"] = False
    out["reason"] = reason
    return out
