"""Assemble a research-claim proof packet with a re-derivable verdict.

Each verification check's categorical status maps to a crucible measurement:
pass -> deviation 0 (MATCH), fail -> deviation 1 (DRIFT), unverifiable -> deviation
None (UNVERIFIABLE, fail-closed). A failed or unverifiable run still yields a valid
packet that preserves the sources, attempts, and evidence.
"""

from __future__ import annotations

from typing import Any

from .._decision import derive_decision_summary
from .._verdict import combine_overall, verdict_for_measurement
from ._refutation import has_standing_counterexample
from .packet import PACKET_VERSION

_TOLERANCE = 0.5


def _check_measurement(status: str) -> tuple[float | None, float]:
    if status == "pass":
        return 0.0, _TOLERANCE
    if status == "fail":
        return 1.0, _TOLERANCE
    return None, _TOLERANCE  # unverifiable / unknown -> fail-closed


def _derive_promotion(
    overall: str, attempts: list[dict[str, Any]], formal: dict[str, Any] | None
) -> str:
    """A standing counterexample outranks any fixture-level pass: the derived
    rung is REFUTED, never a positive promotion."""
    if has_standing_counterexample({"attempts": attempts, "formal": formal or {}}):
        return "REFUTED"
    return "CRUCIBLE_MATCH" if overall == "MATCH" else "UNVERIFIABLE"


def _normalize_checks(
    checks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    """Map each check to its (per_check verdict, status, normalized entry)."""
    per_check: list[dict[str, Any]] = []
    statuses: list[str] = []
    norm_checks: list[dict[str, Any]] = []
    for c in checks:
        deviation, tolerance = _check_measurement(c.get("status", ""))
        status = verdict_for_measurement(deviation, tolerance)
        statuses.append(status)
        per_check.append({"checker": c["checker"], "status": status})
        entry = {
            "checker": c["checker"],
            "status": c["status"],
            "evidence": list(c.get("evidence") or []),
        }
        if c.get("notes"):
            entry["notes"] = c["notes"]
        norm_checks.append(entry)
    return per_check, statuses, norm_checks


def build_research_claim_packet(
    *,
    statement: str,
    sources: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
    checks: list[dict[str, Any]],
    claim: str,
    scope: str,
    packet_id: str,
    uncertainty: list[str] | None = None,
    promotion: str | None = None,
    formal: dict[str, Any] | None = None,
    failure_labels: list[str] | None = None,
    declared_branches: list[dict[str, Any]] | None = None,
    witness_tier: dict[str, Any] | None = None,
    evidence_classes: list[str] | None = None,
) -> dict[str, Any]:
    per_check, statuses, norm_checks = _normalize_checks(checks)
    overall = combine_overall(statuses)
    resolved_promotion = promotion or _derive_promotion(overall, attempts, formal)
    packet = {
        "version": PACKET_VERSION,
        "packet_id": packet_id,
        "claim": claim,
        "scope": scope,
        "statement": statement,
        "sources": [dict(s) for s in sources],
        "attempts": [dict(a) for a in attempts],
        "checks": norm_checks,
        "verdicts": {"overall": overall, "per_check": per_check},
        "promotion": resolved_promotion,
        "uncertainty": list(uncertainty or []),
        "decision_summary": derive_decision_summary(
            overall,
            missing_evidence=list(uncertainty or [])
            if overall == "UNVERIFIABLE"
            else None,
        ),
        **({"formal": formal} if formal is not None else {}),
    }
    if failure_labels is not None:
        packet["failure_labels"] = list(failure_labels)
    _attach_evidence_gate_fields(
        packet, declared_branches, witness_tier, evidence_classes
    )
    return packet


def _attach_evidence_gate_fields(
    packet: dict[str, Any],
    declared_branches: list[dict[str, Any]] | None,
    witness_tier: dict[str, Any] | None,
    evidence_classes: list[str] | None,
) -> None:
    """Attach the optional family evidence-gate fields when supplied."""
    if declared_branches is not None:
        packet["declared_branches"] = [dict(b) for b in declared_branches]
    if witness_tier is not None:
        packet["witness_tier"] = dict(witness_tier)
    if evidence_classes is not None:
        packet["evidence_classes"] = list(evidence_classes)


def to_crucible_inputs(packet: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Emit crucible's (thesis, measurements) file contract for re-derivation."""
    claims = []
    rows = []
    for c in packet.get("checks", []):
        deviation, tolerance = _check_measurement(c.get("status", ""))
        text = f"The statement holds under the {c['checker']} check."
        claims.append(
            {"text": text, "falsification": "the check status is not 'pass'."}
        )
        rows.append(
            {
                "claim": text,
                "deviation": deviation,
                "tolerance": tolerance,
                "method": c["checker"],
                "evidence": list(c.get("evidence") or []),
            }
        )
    thesis = {
        "title": f"Research-claim proof packet {packet.get('packet_id', '')}",
        "disposition": "publishable",
        "claims": claims,
    }
    return thesis, {"measurements": rows}
