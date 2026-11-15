"""Assemble a model-eval proof packet with a re-derivable verdict + default-deny
promotion decision.

Deviation is directional: maximize -> how far below target, minimize -> how far
above, within -> absolute distance. The verdict uses the shared crucible-faithful
rule; a model is promoted only when the overall verdict is MATCH.
"""

from __future__ import annotations

from typing import Any

from .._decision import derive_decision_summary
from .._verdict import combine_overall, verdict_for_measurement
from .packet import PACKET_VERSION

_OUTCOME = {"MATCH": "promote", "DRIFT": "reject", "UNVERIFIABLE": "needs-human"}
_REASON = {
    "promote": "all gated metrics met their objective within tolerance",
    "reject": "at least one metric drifted outside its tolerance",
    "needs-human": "at least one metric could not be verified",
}


def _deviation(value: Any, target: Any, direction: str) -> float:
    v = float(value)
    t = float(target)
    if direction == "maximize":
        return max(0.0, t - v)
    if direction == "minimize":
        return max(0.0, v - t)
    return abs(v - t)


def build_model_eval_packet(
    *,
    model: dict[str, Any],
    eval_set: dict[str, Any],
    objective: dict[str, Any],
    metrics: list[dict[str, Any]],
    claim: str,
    scope: str,
    packet_id: str,
    uncertainty: list[str] | None = None,
    failure_labels: list[str] | None = None,
    replication: dict[str, Any] | None = None,
) -> dict[str, Any]:
    norm_metrics: list[dict[str, Any]] = []
    per_metric: list[dict[str, Any]] = []
    statuses: list[str] = []
    for m in metrics:
        direction = m.get("direction", "within")
        deviation = _deviation(m["value"], m["target"], direction)
        tolerance = float(m["tolerance"])
        status = verdict_for_measurement(deviation, tolerance)
        statuses.append(status)
        entry = {
            "metric": m["metric"],
            "value": m["value"],
            "target": m["target"],
            "direction": direction,
            "tolerance": tolerance,
            "deviation": deviation,
            "method": m.get("method", "measured"),
            "evidence": list(m.get("evidence") or []),
        }
        if m.get("unit"):
            entry["unit"] = m["unit"]
        norm_metrics.append(entry)
        per_metric.append({"metric": m["metric"], "status": status})

    overall = combine_overall(statuses)
    outcome = _OUTCOME[overall]
    packet = {
        "version": PACKET_VERSION,
        "packet_id": packet_id,
        "claim": claim,
        "scope": scope,
        "model": dict(model),
        "eval_set": dict(eval_set),
        "objective": dict(objective),
        "metrics": norm_metrics,
        "decision": {"outcome": outcome, "reason": _REASON[outcome]},
        "verdicts": {"overall": overall, "per_metric": per_metric},
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
    claims = []
    rows = []
    for m in packet.get("metrics", []):
        text = (
            f"Metric {m['metric']} ({m['direction']} target {m['target']}) "
            f"is within tolerance {m['tolerance']}."
        )
        claims.append(
            {
                "text": text,
                "falsification": "the metric deviates beyond the stated tolerance.",
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
        "title": f"Model-eval proof packet {packet.get('packet_id', '')}",
        "disposition": "publishable",
        "claims": claims,
    }
    return thesis, {"measurements": rows}
