"""stress_rest_loop.py -- Adaptive loop-depth allocation and witnessed sleep consolidation.

Combines two stdlib-only control primitives for local-first looped inference:
  1. allocate_loop_depth: continuously scales recurrent pass depth with
     surprise/prediction error under a hard compute budget (Inkling-2-style).
  2. plan_sleep_consolidation: compiles a manifold_memory capsule, verifies
     offline provenance against known source hashes, and emits an explicit
     ADMIT/REJECT promotion plan against a frozen baseline score without
     silent self-modification.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping, Sequence

from harness.manifold_memory import (
    DEFAULT_BUDGET_SLOTS,
    MANIFOLD_LINEAR,
    VERDICT_MATCH,
    ManifoldRecord,
    compile_memory_capsule,
    verify_capsule_provenance,
)

LOOP_DEPTH_SCHEMA = "flywheel.stress-rest-loop-depth/v1"
SLEEP_PLAN_SCHEMA = "flywheel.stress-rest-sleep-plan/v1"

DECISION_ADMIT = "ADMIT"
DECISION_REJECT = "REJECT"


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _seal(payload: dict[str, Any]) -> dict[str, Any]:
    body = {k: v for k, v in payload.items() if k != "receipt_sha256"}
    body["receipt_sha256"] = _canonical_sha256(body)
    return body


def verify_stress_rest_receipt(record: Mapping[str, Any]) -> bool:
    """Re-derive receipt_sha256 offline for any stress-rest-loop record."""
    if not isinstance(record, Mapping):
        return False
    expected = record.get("receipt_sha256")
    if not isinstance(expected, str) or len(expected) != 64:
        return False
    body = {k: v for k, v in record.items() if k != "receipt_sha256"}
    try:
        return _canonical_sha256(body) == expected
    except (TypeError, ValueError):
        return False


def _require_finite_number(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def _require_int(name: str, value: Any, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def allocate_loop_depth(
    surprise: float,
    *,
    min_depth: int = 1,
    max_depth: int = 8,
    budget_remaining: int = 100,
) -> dict[str, Any]:
    """Scale recurrent pass depth continuously with surprise under a hard compute budget."""
    s = _require_finite_number("surprise", surprise)
    if s < 0.0:
        raise ValueError("surprise must be >= 0.0")
    lo = _require_int("min_depth", min_depth, minimum=1)
    hi = _require_int("max_depth", max_depth, minimum=1)
    if hi < lo:
        raise ValueError("max_depth must be >= min_depth")
    budget = _require_int("budget_remaining", budget_remaining, minimum=0)

    normalized = 1.0 - math.exp(-2.0 * s)
    continuous = lo + (hi - lo) * normalized
    requested = max(lo, min(hi, int(round(continuous))))
    allocated = min(requested, budget)
    budget_capped = allocated < requested
    budget_after = budget - allocated

    return _seal(
        {
            "schema": LOOP_DEPTH_SCHEMA,
            "surprise": round(s, 12),
            "normalized_surprise": round(normalized, 12),
            "continuous_depth": round(continuous, 12),
            "requested_depth": requested,
            "allocated_depth": allocated,
            "min_depth": lo,
            "max_depth": hi,
            "budget_remaining": budget,
            "budget_after": budget_after,
            "budget_capped": budget_capped,
        }
    )


def _promotion_decision(
    provenance: Mapping[str, Any], base: float, cand: float
) -> tuple[str, str]:
    verdict = str(provenance.get("verdict", ""))
    if verdict != VERDICT_MATCH:
        return DECISION_REJECT, f"rejected: capsule provenance verdict is {verdict} ({provenance.get('reason', '')})"
    if cand < base:
        return DECISION_REJECT, f"rejected: candidate_score {cand:.6g} regressed below baseline_score {base:.6g}"
    return DECISION_ADMIT, f"admitted: provenance MATCH and candidate_score {cand:.6g} >= baseline_score {base:.6g}"


def plan_sleep_consolidation(
    records: Sequence[ManifoldRecord],
    *,
    baseline_score: float,
    candidate_score: float,
    source_hashes: Mapping[str, str],
    budget_slots: int = DEFAULT_BUDGET_SLOTS,
    query_manifold: str | None = None,
    query_coords: Sequence[float] | float | None = None,
) -> dict[str, Any]:
    """Compile a witnessed memory capsule and emit an ADMIT/REJECT consolidation plan."""
    base = _require_finite_number("baseline_score", baseline_score)
    cand = _require_finite_number("candidate_score", candidate_score)
    slots = _require_int("budget_slots", budget_slots, minimum=0)
    manifold = query_manifold or (records[0].manifold if records else MANIFOLD_LINEAR)
    coords = query_coords if query_coords is not None else (records[0].coords if records else (0.0,))
    capsule = compile_memory_capsule(records, manifold, coords, budget_slots=slots)
    provenance = verify_capsule_provenance(capsule, source_hashes)
    decision, reason = _promotion_decision(provenance, base, cand)
    return _seal({
        "schema": SLEEP_PLAN_SCHEMA,
        "decision": decision,
        "admitted": decision == DECISION_ADMIT,
        "self_modified": False,
        "baseline_score": round(base, 12),
        "candidate_score": round(cand, 12),
        "score_delta": round(cand - base, 12),
        "provenance_verdict": str(provenance.get("verdict", "")),
        "capsule_sha256": capsule["capsule_sha256"],
        "slot_count": capsule["slot_count"],
        "budget_slots": slots,
        "provenance": provenance,
        "capsule": capsule,
        "reason": reason,
    })
