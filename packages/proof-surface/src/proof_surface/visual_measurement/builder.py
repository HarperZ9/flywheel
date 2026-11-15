"""Assemble a visual-measurement proof packet and attach a re-derivable verdict.

Metrics arrive as data (the shape Build Color / Calibrate Pro produce) so this
stays zero-dependency and never mutates a display. Each metric's deviation is
computed as |value - target|; the verdict uses the shared crucible-faithful rule.
"""

from __future__ import annotations

from typing import Any

from .._decision import derive_decision_summary
from .._verdict import combine_overall, verdict_for_measurement
from .packet import PACKET_VERSION


def build_visual_measurement_packet(
    *,
    artifact: dict[str, Any],
    color: dict[str, Any],
    metrics: list[dict[str, Any]],
    claim: str,
    scope: str,
    packet_id: str,
    display_caveats: list[str] | None = None,
    calibration_boundary: dict[str, Any] | None = None,
    failure_labels: list[str] | None = None,
) -> dict[str, Any]:
    measurements: list[dict[str, Any]] = []
    per_metric: list[dict[str, Any]] = []
    statuses: list[str] = []
    for m in metrics:
        deviation = abs(float(m["value"]) - float(m["target"]))
        tolerance = float(m["tolerance"])
        status = verdict_for_measurement(deviation, tolerance)
        statuses.append(status)
        measurements.append(
            {
                "metric": m["metric"],
                "value": m["value"],
                "unit": m["unit"],
                "target": m["target"],
                "tolerance": tolerance,
                "deviation": deviation,
                "method": m.get("method", "measured"),
                "evidence": list(m.get("evidence") or [artifact.get("sha256", "")]),
            }
        )
        per_metric.append({"metric": m["metric"], "status": status})

    overall = combine_overall(statuses)
    packet = {
        "version": PACKET_VERSION,
        "packet_id": packet_id,
        "claim": claim,
        "scope": scope,
        "artifact": dict(artifact),
        "color": dict(color),
        "read_only": True,
        "measurements": measurements,
        "display_caveats": list(display_caveats or []),
        "calibration_boundary": dict(calibration_boundary)
        if calibration_boundary is not None
        else {"hardware_measurement_used": False, "physical_calibration_claim": False},
        "verdicts": {"overall": overall, "per_metric": per_metric},
        "uncertainty": [],
        "decision_summary": derive_decision_summary(overall),
    }
    if failure_labels is not None:
        packet["failure_labels"] = list(failure_labels)
    return packet


def to_crucible_inputs(packet: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Emit crucible's (thesis, measurements) file contract for re-derivation."""
    claims = []
    rows = []
    for m in packet.get("measurements", []):
        text = (
            f"Metric {m['metric']} measured {m['value']} {m['unit']} is within "
            f"tolerance {m['tolerance']} of target {m['target']}."
        )
        claims.append(
            {
                "text": text,
                "falsification": "the measured deviation exceeds the stated tolerance.",
            }
        )
        rows.append(
            {
                "claim": text,
                "deviation": m["deviation"],
                "tolerance": m["tolerance"],
                "method": m["method"],
                "evidence": m["evidence"],
            }
        )
    thesis = {
        "title": f"Visual-measurement proof packet {packet.get('packet_id', '')}",
        "disposition": "publishable",
        "claims": claims,
    }
    return thesis, {"measurements": rows}
