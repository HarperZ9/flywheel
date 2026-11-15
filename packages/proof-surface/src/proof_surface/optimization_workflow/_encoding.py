"""Constraint-encoding vocabulary, shared by the primary solver and its branches.

How each constraint was encoded for the solver (pass 0101/0103). Surrogate
encodings can present an infeasible optimum as solved and may not self-certify
feasibility -- and, per pass 0103, a surrogate that merely matches one fixture is
still promotion-blocked as a general reduction.
"""

from __future__ import annotations

CONSTRAINT_ENCODINGS = {
    "exact",
    "inequality_native",
    "equality_native",
    "slack_variable",
    "penalty",
    "equality_penalty",
    "externally_enforced",
}
SURROGATE_ENCODINGS = {"penalty", "equality_penalty"}
