"""Assemble a control-certificate packet and derive the verdict from witnesses.

MATCH iff every witnessed condition holds within its tolerance (residual <=
tolerance); DRIFT if any condition fails; UNVERIFIABLE if nothing was
witnessed. The required violating negative fixture, kind completeness, and the
sim-to-real boundary are validated at the packet layer -- a packet whose
fixture cannot violate the certificate is invalid.
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
        and _is_number(w.get("residual"))
        and _is_number(w.get("tolerance"))
    ]
    if not checked:
        return "UNVERIFIABLE"
    if all(w["residual"] <= w["tolerance"] for w in checked):
        return "MATCH"
    return "DRIFT"


def build_control_certificate_packet(
    *,
    sources: list[dict[str, Any]],
    system: dict[str, Any],
    certificate: dict[str, Any],
    witnesses: list[dict[str, Any]],
    negative_fixture: dict[str, Any],
    trajectory: dict[str, Any],
    claim: str,
    scope: str,
    packet_id: str,
    sim_to_real: dict[str, Any] | None = None,
    uncertainty: list[str] | None = None,
    failure_labels: list[str] | None = None,
) -> dict[str, Any]:
    overall = _derive_verdict(witnesses)
    declared_certificate = dict(certificate)
    # Fail-closed provenance: an undeclared certificate origin is the weakest
    # tier (author-asserted), never an upgrade to synthesized or verified.
    declared_certificate.setdefault("provenance", "author-asserted")
    packet = {
        "version": PACKET_VERSION,
        "packet_id": packet_id,
        "claim": claim,
        "scope": scope,
        "sources": [dict(s) for s in sources],
        "system": dict(system),
        "certificate": declared_certificate,
        "witnesses": [dict(w) for w in witnesses],
        "negative_fixture": dict(negative_fixture),
        "trajectory": dict(trajectory),
        "sim_to_real": dict(sim_to_real)
        if sim_to_real is not None
        else {"hardware_validity_claim": False, "hardware_evidence": []},
        "verdicts": {"overall": overall},
        "uncertainty": list(uncertainty or []),
        "decision_summary": derive_decision_summary(overall),
    }
    if failure_labels is not None:
        packet["failure_labels"] = list(failure_labels)
    return packet


def to_crucible_inputs(packet: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Emit crucible's (thesis, measurements) file contract for re-derivation."""
    system = packet.get("system", {}) or {}
    certificate = packet.get("certificate", {}) or {}
    claims = []
    rows = []
    for index, witness in enumerate(packet.get("witnesses", [])):
        if not isinstance(witness, dict):
            continue
        text = (
            f"The {system.get('description')} satisfies condition "
            f"'{witness.get('condition')}' of the {certificate.get('kind')} "
            f"certificate '{certificate.get('name')}' within tolerance "
            f"{witness.get('tolerance')}."
        )
        claims.append(
            {
                "text": text,
                "falsification": "the witnessed residual exceeds the stated tolerance.",
            }
        )
        rows.append(
            {
                "claim": text,
                "deviation": witness.get("residual"),
                "tolerance": witness.get("tolerance"),
                "method": witness.get("method", witness.get("condition", "witness")),
                "evidence": [f"witness_{index}={witness.get('condition')}"],
            }
        )
    thesis = {
        "title": f"Control-certificate proof packet {packet.get('packet_id', '')}",
        "disposition": "publishable",
        "claims": claims,
    }
    return thesis, {"measurements": rows}
