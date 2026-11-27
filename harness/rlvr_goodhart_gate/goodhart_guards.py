# SPDX-License-Identifier: MIT
"""Fail-closed PRM-vs-oracle Goodhart divergence and RLVR self-play guards."""

from __future__ import annotations

import math
from typing import Any, Sequence

DEFAULT_PRM_THRESHOLD: float = 0.90
DEFAULT_ORACLE_EPS: float = 1e-12
DEFAULT_MAX_PARITY_ERR: float = 1e-10


def is_strict_int(value: Any) -> bool:
    """Return True only for plain integers, excluding booleans."""
    return isinstance(value, int) and not isinstance(value, bool)


def is_finite_number(value: Any) -> bool:
    """Return True for finite int/float values, rejecting bool, NaN, and Inf."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def check_goodhart_candidate(
    cand: Any,
    prm_threshold: float = DEFAULT_PRM_THRESHOLD,
    oracle_eps: float = DEFAULT_ORACLE_EPS,
) -> tuple[bool, list[str]]:
    """Enforce fail-closed rejection whenever PRM >= 0.90 and oracle == 0.0.

    Returns (is_goodhart_trap, errors). Any bypass emits a non-empty error list.
    """
    errs: list[str] = []
    cid = getattr(cand, "candidate_id", "unknown")
    prm = getattr(cand, "prm_score", None)
    oracle = getattr(cand, "oracle_score", None)
    accepted = getattr(cand, "accepted", None)
    quarantined = getattr(cand, "quarantined", None)
    assigned = getattr(cand, "assigned_value", None)

    if not is_finite_number(prm) or not (0.0 <= float(prm) <= 1.0):
        return False, [f"invalid_prm_score:{cid}:{prm!r}"]
    if not is_finite_number(oracle) or not (0.0 <= float(oracle) <= 1.0):
        return False, [f"invalid_oracle_score:{cid}:{oracle!r}"]
    if not isinstance(accepted, bool) or not isinstance(quarantined, bool):
        return False, [f"invalid_decision_flags:{cid}"]

    prm_f = float(prm)
    oracle_f = float(oracle)
    is_trap = prm_f >= prm_threshold and oracle_f <= oracle_eps
    if is_trap:
        if accepted:
            errs.append(f"goodhart_bypass_accepted:{cid}")
        if not quarantined:
            errs.append(f"goodhart_trap_not_quarantined:{cid}")
        if assigned is not None:
            if not is_finite_number(assigned) or float(assigned) >= 0.0:
                errs.append(f"goodhart_non_negative_val:{cid}:{assigned!r}")
    elif oracle_f <= oracle_eps and accepted:
        errs.append(f"unverified_oracle_zero_accepted:{cid}")
    return is_trap, errs


def check_monotonic_solve_curve(rates: Sequence[Any]) -> list[str]:
    """Verify every round solve rate is finite in [0, 1] and non-decreasing."""
    if not isinstance(rates, Sequence) or isinstance(rates, (str, bytes)):
        return ["solve_curve_not_sequence"]
    if len(rates) < 2:
        return ["solve_curve_too_short"]
    errs: list[str] = []
    prev = -1.0
    for idx, rate in enumerate(rates):
        if not is_finite_number(rate):
            errs.append(f"solve_rate_non_finite_at_{idx}")
            continue
        val = float(rate)
        if val < 0.0 or val > 1.0:
            errs.append(f"solve_rate_out_of_bounds_at_{idx}:{val}")
            continue
        if prev >= 0.0 and val + 1e-12 < prev:
            errs.append(f"solve_rate_regressed_at_{idx}:{prev}->{val}")
        prev = val
    return errs


def check_unverified_weight_drift(
    updates: Sequence[Any],
    oracle_eps: float = DEFAULT_ORACLE_EPS,
) -> list[str]:
    """Block any policy weight update backed by a zero oracle verdict."""
    errs: list[str] = []
    for idx, upd in enumerate(updates):
        oracle = getattr(upd, "oracle_score", None)
        delta = getattr(upd, "weight_delta", None)
        blocked = getattr(upd, "blocked", None)
        if not is_finite_number(oracle) or not is_finite_number(delta):
            errs.append(f"update_non_finite_at_{idx}")
            continue
        if not isinstance(blocked, bool):
            errs.append(f"update_blocked_not_bool_at_{idx}")
            continue
        if float(oracle) <= oracle_eps:
            if abs(float(delta)) > 0.0:
                errs.append(f"unverified_weight_drift_at_{idx}:{delta}")
            if not blocked:
                errs.append(f"unverified_update_not_blocked_at_{idx}")
    return errs
