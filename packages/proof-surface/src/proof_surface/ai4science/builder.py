"""Assemble an AI4Science packet and derive the promotion rung + verdict.

Promotion is derived conservatively, never asserted: REPRODUCED needs a
measurement AND independent reproduction AND no open objection; MEASURED needs a
measurement; else HYPOTHESIS. The verdict falls to DRIFT on a negative result or
a failed reproduction, MATCH once reproduced, UNVERIFIABLE otherwise.
"""

from __future__ import annotations

from typing import Any

from .._decision import derive_decision_summary
from .packet import PACKET_VERSION


def _has_open_objection(objections: list[dict[str, Any]]) -> bool:
    return any(o.get("status") == "open" for o in objections if isinstance(o, dict))


def _derive_promotion(
    measurement: dict[str, Any], reproduction: dict[str, Any], has_open: bool
) -> str:
    measured = measurement.get("measured") is True
    reproduced = reproduction.get("status") == "INDEPENDENTLY_REPRODUCED"
    if measured and reproduced and not has_open:
        return "REPRODUCED"
    if measured:
        return "MEASURED"
    return "HYPOTHESIS"


def _derive_verdict(
    promotion: str, reproduction: dict[str, Any], negative: bool
) -> str:
    if negative or reproduction.get("status") == "FAILED_REPRODUCTION":
        return "DRIFT"
    if promotion in {"REPRODUCED", "PEER_REVIEWED"}:
        return "MATCH"
    return "UNVERIFIABLE"


def build_ai4science_packet(
    *,
    sources: list[dict[str, Any]],
    domain: str,
    scientific_claim: str,
    agent_actions: list[dict[str, Any]],
    protocol: dict[str, Any],
    measurement: dict[str, Any],
    reproduction: dict[str, Any],
    reviewer_objections: list[dict[str, Any]],
    negative_result: bool,
    claim: str,
    scope: str,
    packet_id: str,
    uncertainty: list[str] | None = None,
    failure_labels: list[str] | None = None,
    replication: dict[str, Any] | None = None,
) -> dict[str, Any]:
    has_open = _has_open_objection(reviewer_objections)
    promotion = _derive_promotion(measurement, reproduction, has_open)
    overall = _derive_verdict(promotion, reproduction, negative_result)
    packet = {
        "version": PACKET_VERSION,
        "packet_id": packet_id,
        "claim": claim,
        "scope": scope,
        "sources": [dict(s) for s in sources],
        "domain": domain,
        "scientific_claim": scientific_claim,
        "agent_actions": [dict(a) for a in agent_actions],
        "protocol": dict(protocol),
        "measurement": dict(measurement),
        "reproduction": dict(reproduction),
        "reviewer_objections": [dict(o) for o in reviewer_objections],
        "negative_result": negative_result,
        "promotion": promotion,
        "verdicts": {"overall": overall},
        "uncertainty": list(uncertainty or []),
        "decision_summary": derive_decision_summary(overall),
    }
    if failure_labels is not None:
        packet["failure_labels"] = list(failure_labels)
    if replication is not None:
        packet["replication"] = replication
    return packet


def to_crucible_inputs(packet: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Emit crucible's (thesis, measurements) file contract for re-derivation."""
    reproduction = packet.get("reproduction", {}) or {}
    text = (
        f"Claim '{packet.get('scientific_claim')}' reached promotion "
        f"{packet.get('promotion')} with reproduction {reproduction.get('status')}."
    )
    thesis = {
        "title": f"AI4Science claim-to-experiment packet {packet.get('packet_id', '')}",
        "disposition": "publishable",
        "claims": [
            {
                "text": text,
                "falsification": "the measurement or reproduction evidence does not hold.",
            }
        ],
    }
    overall = (packet.get("verdicts") or {}).get("overall")
    rows = [
        {
            "claim": text,
            "deviation": 0.0 if overall == "MATCH" else 1.0,
            "tolerance": 0.5,
            "method": "claim-to-experiment",
            "evidence": [f"reproduction={reproduction.get('status')}"],
        }
    ]
    return thesis, {"measurements": rows}
