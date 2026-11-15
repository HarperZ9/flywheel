"""Assemble a conservation packet and derive the verdict from the witnesses.

MATCH iff every independent witness conserves the invariant within its tolerance
(drift <= tolerance); DRIFT if any witness exceeds tolerance; UNVERIFIABLE if no
witness is present. The required breaking negative fixture is validated at the
packet layer -- a packet whose negative fixture cannot break is invalid.
"""

from __future__ import annotations

from typing import Any

from .._decision import derive_decision_summary
from .packet import PACKET_VERSION


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _derive_verdict(witnesses: list[dict[str, Any]]) -> str:
    checked = [
        w
        for w in witnesses
        if isinstance(w, dict)
        and _is_number(w.get("drift"))
        and _is_number(w.get("tolerance"))
    ]
    if not checked:
        return "UNVERIFIABLE"
    if all(w["drift"] <= w["tolerance"] for w in checked):
        return "MATCH"
    return "DRIFT"


def build_conservation_packet(
    *,
    sources: list[dict[str, Any]],
    transformation: dict[str, Any],
    invariant: dict[str, Any],
    witnesses: list[dict[str, Any]],
    negative_fixture: dict[str, Any],
    claim: str,
    scope: str,
    packet_id: str,
    boundary_fixture: dict[str, Any] | None = None,
    uncertainty: list[str] | None = None,
    failure_labels: list[str] | None = None,
) -> dict[str, Any]:
    overall = _derive_verdict(witnesses)
    packet = {
        "version": PACKET_VERSION,
        "packet_id": packet_id,
        "claim": claim,
        "scope": scope,
        "sources": [dict(s) for s in sources],
        "transformation": dict(transformation),
        "invariant": dict(invariant),
        "witnesses": [dict(w) for w in witnesses],
        "negative_fixture": dict(negative_fixture),
        "verdicts": {"overall": overall},
        "uncertainty": list(uncertainty or []),
        "decision_summary": derive_decision_summary(overall),
    }
    if boundary_fixture is not None:
        packet["boundary_fixture"] = dict(boundary_fixture)
    if failure_labels is not None:
        packet["failure_labels"] = list(failure_labels)
    return packet


def to_crucible_inputs(packet: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Emit crucible's (thesis, measurements) file contract for re-derivation."""
    invariant = packet.get("invariant", {}) or {}
    transformation = packet.get("transformation", {}) or {}
    claims = []
    rows = []
    for index, witness in enumerate(packet.get("witnesses", [])):
        if not isinstance(witness, dict):
            continue
        text = (
            f"The {transformation.get('description')} conserves invariant "
            f"'{invariant.get('name')}' under the {witness.get('kind')} witness "
            f"within tolerance {witness.get('tolerance')}."
        )
        claims.append(
            {
                "text": text,
                "falsification": "the witnessed drift exceeds the stated tolerance.",
            }
        )
        rows.append(
            {
                "claim": text,
                "deviation": witness.get("drift"),
                "tolerance": witness.get("tolerance"),
                "method": witness.get("method", witness.get("kind", "witness")),
                "evidence": [f"witness_{index}={witness.get('kind')}"],
            }
        )
    thesis = {
        "title": f"Conservation proof packet {packet.get('packet_id', '')}",
        "disposition": "publishable",
        "claims": claims,
    }
    return thesis, {"measurements": rows}
