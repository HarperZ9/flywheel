"""hypothetical_loop.py -- two-phase hypothetical exploration and ground-return protocol.

Separates unconstrained conceptual/counterfactual exploration ("as if true" and
"as if false" branches in tangential space) from ground-return verification
against empirical measurements, negative caches, and reseating valves.

Nothing in hypothetical space is prematurely pruned or silently promoted as
established fact; every branch carries an explicit epistemic status
(HYPOTHETICAL, CRYSTALLIZED, REFUTED, or UNDECIDED) and a deterministic receipt.

Zero third-party dependencies (stdlib only).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from .evidence_json import canonical_sha256
from .negative_cache import NegativeRecord, query_dead_ends

BRANCH_SCHEMA = "flywheel.hypothetical-branch/v1"
RETURN_SCHEMA = "flywheel.ground-return/v1"


@dataclass(frozen=True)
class HypotheticalBranch:
    branch_id: str
    domain: str
    premise: str
    posture: str  # "as_if_true" | "as_if_false" | "inverted_symmetry" | "cross_domain_recomb"
    relaxed_constraints: tuple[str, ...] = ()
    predictions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        if self.posture not in ("as_if_true", "as_if_false", "inverted_symmetry", "cross_domain_recomb"):
            raise ValueError(f"unknown hypothetical posture: {self.posture!r}")
        payload = {
            "schema": BRANCH_SCHEMA,
            "branch_id": self.branch_id,
            "domain": self.domain.strip().lower(),
            "premise": self.premise.strip(),
            "posture": self.posture,
            "status": "HYPOTHETICAL",
            "relaxed_constraints": list(self.relaxed_constraints),
            "predictions": list(self.predictions),
        }
        payload["branch_sha256"] = canonical_sha256(payload)
        return payload


def open_counterfactual_pair(
    *,
    base_id: str,
    domain: str,
    premise: str,
    relaxed_constraints: Iterable[str] = (),
    true_predictions: Iterable[str] = (),
    false_predictions: Iterable[str] = (),
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create paired 'as_if_true' and 'as_if_false' hypothetical branches."""
    relaxed = tuple(relaxed_constraints)
    b_true = HypotheticalBranch(
        branch_id=f"{base_id}:true",
        domain=domain,
        premise=premise,
        posture="as_if_true",
        relaxed_constraints=relaxed,
        predictions=tuple(true_predictions),
    ).to_dict()
    b_false = HypotheticalBranch(
        branch_id=f"{base_id}:false",
        domain=domain,
        premise=premise,
        posture="as_if_false",
        relaxed_constraints=relaxed,
        predictions=tuple(false_predictions),
    ).to_dict()
    return b_true, b_false


def return_to_ground(
    branch: dict[str, Any],
    *,
    evaluator: Callable[[dict[str, Any]], dict[str, Any]],
    negative_cache: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Test a hypothetical branch against empirical measurement and the negative cache.

    `evaluator(branch)` returns:
      {"verdict": "MATCH" | "DRIFT" | "UNVERIFIABLE",
       "measurement_sha256": str,
       "detail": str,
       "parameters": dict}
    """
    prior = (
        query_dead_ends(
            negative_cache,
            domain=branch["domain"],
            hypothesis=branch["premise"],
        )
        if negative_cache is not None
        else {"verdict": "NOVEL", "hit_count": 0, "hits": []}
    )
    eval_out = evaluator(branch)
    verdict = str(eval_out.get("verdict", "UNVERIFIABLE")).upper()
    meas_sha = str(eval_out.get("measurement_sha256", ""))
    detail = str(eval_out.get("detail", ""))
    params = dict(eval_out.get("parameters") or {})

    if verdict == "MATCH" and meas_sha:
        status = "CRYSTALLIZED"
        new_negative = None
    elif verdict == "DRIFT" and meas_sha:
        status = "REFUTED"
        new_negative = NegativeRecord(
            record_id=f"neg:{branch['branch_id']}",
            domain=branch["domain"],
            hypothesis=branch["premise"],
            failure_mode=detail or "refuted on ground return",
            parameters=params,
            measurement_sha256=meas_sha,
        ).to_dict()
    else:
        status = "UNDECIDED"
        new_negative = None

    record = {
        "schema": RETURN_SCHEMA,
        "branch_id": branch["branch_id"],
        "branch_sha256": branch["branch_sha256"],
        "domain": branch["domain"],
        "posture": branch["posture"],
        "prior_negative_cache": prior["verdict"],
        "prior_hit_count": prior["hit_count"],
        "ground_verdict": verdict,
        "status": status,
        "measurement_sha256": meas_sha,
        "detail": detail,
        "new_negative_record": new_negative,
    }
    record["return_sha256"] = canonical_sha256(record)
    return record
