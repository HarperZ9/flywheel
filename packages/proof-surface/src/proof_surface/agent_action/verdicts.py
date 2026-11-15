"""Crucible verdict bridge for the agent-action packet.

Two faces, one rule:

* ``attach_verdicts`` fills the packet's verdict layer using an embedded
  ``verdict_for_measurement`` that is faithful to crucible's pure semantics, so
  the packet is self-contained and runnable with zero dependencies.
* ``to_crucible_inputs`` emits crucible's exact thesis/measurements file
  contract so real crucible (an optional peer, published as ``crucible-bench``)
  can independently re-derive the same verdict from the same evidence.

The mapping from admission + effect evidence to a measurement:

    deny        -> deviation 1.0, tolerance 0.5   (DRIFT: a side effect ran
                                                    without a valid grant)
    needs-human -> deviation None                 (UNVERIFIABLE: unresolved)
    allow + observed after-state -> deviation 0.0 (MATCH: admitted and verified)
    allow + no after-state       -> deviation None(UNVERIFIABLE: fail-closed)
"""

from __future__ import annotations

from typing import Any

from .._decision import derive_decision_summary
from .._verdict import combine_overall, verdict_for_measurement

_TOLERANCE = 0.5


def _by_action_id(entries: Any) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict) and isinstance(entry.get("action_id"), str):
                out.setdefault(entry["action_id"], entry)
    return out


def _measurement(
    admission: dict[str, Any], side_effect: dict[str, Any]
) -> dict[str, Any]:
    """Turn one action's admission + effect evidence into a measurement row."""
    decision = admission.get("decision")
    reasons = admission.get("reasons") or []
    if decision == "deny":
        return {
            "deviation": 1.0,
            "tolerance": _TOLERANCE,
            "method": "admission-check",
            "evidence": ["decision=deny", *reasons],
        }
    if decision == "needs-human":
        return {
            "deviation": None,
            "tolerance": _TOLERANCE,
            "method": "admission-check",
            "evidence": ["decision=needs-human", *reasons],
        }
    # allow: verified iff we observed an after-state digest
    after = side_effect.get("after_digest")
    if isinstance(after, str) and after:
        before = side_effect.get("before_digest")
        evidence = [e for e in (before, after) if isinstance(e, str) and e]
        return {
            "deviation": 0.0,
            "tolerance": _TOLERANCE,
            "method": "effect-verify",
            "evidence": evidence or ["after=" + after],
        }
    return {
        "deviation": None,
        "tolerance": _TOLERANCE,
        "method": "effect-verify",
        "evidence": ["no observed after-state"],
    }


def _iter_measured_actions(packet: dict[str, Any]):
    admission = _by_action_id(packet.get("admission"))
    side_effects = _by_action_id(packet.get("side_effects"))
    for action in packet.get("actions", []):
        if not isinstance(action, dict):
            continue
        aid = action.get("action_id")
        m = _measurement(admission.get(aid, {}), side_effects.get(aid, {}))
        yield action, m


def attach_verdicts(packet: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the packet with its verdict layer computed."""
    per_action = []
    statuses = []
    for action, m in _iter_measured_actions(packet):
        status = verdict_for_measurement(m["deviation"], m["tolerance"])
        statuses.append(status)
        per_action.append({"action_id": action.get("action_id"), "status": status})

    result = dict(packet)
    overall = combine_overall(statuses)
    result["verdicts"] = {"overall": overall, "per_action": per_action}
    result["decision_summary"] = derive_decision_summary(
        overall,
        missing_evidence=result.get("uncertainty")
        if overall == "UNVERIFIABLE"
        else None,
    )
    return result


def _claim_text(action: dict[str, Any]) -> str:
    return (
        f"Action {action.get('action_id')} "
        f"({action.get('action_kind')} on {action.get('target')}) "
        f"was admitted under its grant and its effect was verified."
    )


_FALSIFICATION = (
    "the admission decision was not 'allow', or the after-state digest is "
    "absent (the effect could not be observed)."
)


def to_crucible_inputs(packet: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Emit crucible's (thesis, measurements) file contract for re-derivation."""
    claims = []
    measurements = []
    for action, m in _iter_measured_actions(packet):
        text = _claim_text(action)
        claims.append({"text": text, "falsification": _FALSIFICATION})
        measurements.append(
            {
                "claim": text,
                "deviation": m["deviation"],
                "tolerance": m["tolerance"],
                "method": m["method"],
                "evidence": m["evidence"],
            }
        )
    thesis = {
        "title": f"Agent-action proof packet {packet.get('packet_id', '')}",
        "disposition": "publishable",
        "claims": claims,
    }
    return thesis, {"measurements": measurements}
