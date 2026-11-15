"""Assemble a rollout-receipt packet with a derived, default-deny promotion.

The overall verdict IS the verifier's verdict (the verifier judges; the packet
records). Promotion is derived, never asserted: promote only when the verifier
said MATCH and admission said allow; reject on DRIFT or block; hold otherwise.
Reward score, verifier verdict, admission, and promotion stay separate records.
"""

from __future__ import annotations

from typing import Any

from .._decision import derive_decision_summary
from .packet import PACKET_VERSION


def _promotion(verdict: str, admission_decision: str) -> dict[str, str]:
    if verdict == "MATCH" and admission_decision == "allow":
        return {
            "decision": "promote",
            "reason": "verifier verdict MATCH and admission allow",
        }
    if verdict == "DRIFT" or admission_decision == "block":
        return {
            "decision": "reject",
            "reason": "verifier verdict DRIFT or admission block",
        }
    return {
        "decision": "hold",
        "reason": "verifier verdict or admission decision is not conclusive",
    }


def build_rollout_receipt_packet(
    *,
    sources: list[dict[str, Any]],
    rollout: dict[str, Any],
    reward: dict[str, Any],
    verifier: dict[str, Any],
    admission: dict[str, Any],
    claim: str,
    scope: str,
    packet_id: str,
    uncertainty: list[str] | None = None,
    failure_labels: list[str] | None = None,
    compute_lease: dict[str, Any] | None = None,
) -> dict[str, Any]:
    verdict = verifier.get("verdict", "UNVERIFIABLE")
    admission_decision = admission.get("decision", "escalate")
    overall = (
        verdict if verdict in {"MATCH", "DRIFT", "UNVERIFIABLE"} else "UNVERIFIABLE"
    )
    packet = {
        "version": PACKET_VERSION,
        "packet_id": packet_id,
        "claim": claim,
        "scope": scope,
        "sources": [dict(s) for s in sources],
        "rollout": dict(rollout),
        "reward": dict(reward),
        "verifier": dict(verifier),
        "admission": dict(admission),
        "promotion": _promotion(overall, admission_decision),
        "verdicts": {"overall": overall},
        "uncertainty": list(uncertainty or []),
        "decision_summary": derive_decision_summary(overall),
    }
    if compute_lease is not None:
        packet["compute_lease"] = dict(compute_lease)
    if failure_labels is not None:
        packet["failure_labels"] = list(failure_labels)
    return packet


def to_crucible_inputs(packet: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Emit crucible's (thesis, measurements) file contract for re-derivation."""
    rollout = packet.get("rollout", {}) or {}
    verifier = packet.get("verifier", {}) or {}
    text = (
        f"Rollout {rollout.get('rollout_id')} verified {verifier.get('verdict')} "
        f"by {rollout.get('verifier_ref')}."
    )
    thesis = {
        "title": f"Rollout-receipt proof packet {packet.get('packet_id', '')}",
        "disposition": "publishable",
        "claims": [
            {
                "text": text,
                "falsification": "the verifier verdict or its evidence does not hold.",
            }
        ],
    }
    verdict = verifier.get("verdict")
    rows = [
        {
            "claim": text,
            "deviation": 0.0 if verdict == "MATCH" else 1.0,
            "tolerance": 0.5,
            "method": "verifier",
            "evidence": list(verifier.get("evidence") or []),
        }
    ]
    return thesis, {"measurements": rows}
