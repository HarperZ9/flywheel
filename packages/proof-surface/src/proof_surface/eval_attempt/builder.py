"""Assemble an eval-attempt packet and derive the verdict honestly.

correct + clean -> MATCH; incorrect -> DRIFT; abstained / error -> UNVERIFIABLE.
A `correct` outcome that had ground-truth access is contamination: it is never
scored MATCH -- the verdict falls to UNVERIFIABLE and the validator rejects the
packet outright.
"""

from __future__ import annotations

from typing import Any

from .._decision import derive_decision_summary
from ._integrity import has_audit_surface
from .packet import PACKET_VERSION


def _derive_verdict(
    result: dict[str, Any], boundaries: dict[str, Any], attempt: dict[str, Any]
) -> str:
    outcome = result.get("outcome")
    if outcome == "correct":
        if boundaries.get("had_ground_truth") is True:
            return "UNVERIFIABLE"
        if not has_audit_surface(boundaries, attempt):
            # Latent reasoning + no replay ref: nothing a checker can inspect.
            return "UNVERIFIABLE"
        return "MATCH"
    if outcome == "incorrect":
        return "DRIFT"
    return "UNVERIFIABLE"


def build_eval_attempt_packet(
    *,
    sources: list[dict[str, Any]],
    benchmark: dict[str, Any],
    attempt: dict[str, Any],
    result: dict[str, Any],
    boundaries: dict[str, Any],
    claim: str,
    scope: str,
    packet_id: str,
    uncertainty: list[str] | None = None,
    failure_labels: list[str] | None = None,
) -> dict[str, Any]:
    overall = _derive_verdict(result, boundaries, attempt)
    packet = {
        "version": PACKET_VERSION,
        "packet_id": packet_id,
        "claim": claim,
        "scope": scope,
        "sources": [dict(s) for s in sources],
        "benchmark": dict(benchmark),
        "attempt": dict(attempt),
        "result": dict(result),
        "boundaries": dict(boundaries),
        "verdicts": {"overall": overall},
        "uncertainty": list(uncertainty or []),
        "decision_summary": derive_decision_summary(overall),
    }
    if failure_labels is not None:
        packet["failure_labels"] = list(failure_labels)
    return packet


def to_crucible_inputs(packet: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Emit crucible's (thesis, measurements) file contract for re-derivation."""
    benchmark = packet.get("benchmark", {}) or {}
    result = packet.get("result", {}) or {}
    text = (
        f"Attempt on {benchmark.get('benchmark_ref')} task "
        f"{benchmark.get('task_id')} was {result.get('outcome')} under authority "
        f"{benchmark.get('authority_receipt')}."
    )
    thesis = {
        "title": f"Eval-attempt proof packet {packet.get('packet_id', '')}",
        "disposition": "publishable",
        "claims": [
            {
                "text": text,
                "falsification": "the recorded outcome is contaminated or unreplayable.",
            }
        ],
    }
    overall = (packet.get("verdicts") or {}).get("overall")
    rows = [
        {
            "claim": text,
            "deviation": 0.0 if overall == "MATCH" else 1.0,
            "tolerance": 0.5,
            "method": "benchmark-attempt",
            "evidence": [
                f"replay_ref={packet.get('attempt', {}).get('replay_ref', '')}"
            ],
        }
    ]
    return thesis, {"measurements": rows}
