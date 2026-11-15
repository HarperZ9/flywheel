"""Assemble a competition-attempt packet and derive the verdict honestly.

MATCH only if the judge-verdict layer EXECUTED and passed; DRIFT if it
EXECUTED and failed; UNVERIFIABLE otherwise (a fenced or absent judge). The
verdict cites only EXECUTED layers, so a passing verdict with zero executed
layers is impossible by construction: with nothing executed, the judge did
not execute either, and MATCH is not derivable.
"""

from __future__ import annotations

from typing import Any

from .._decision import derive_decision_summary
from ._gates import JUDGE_LAYER, executed_layer_names
from .packet import PACKET_VERSION


def _derive_verdict(layers: list[dict[str, Any]]) -> str:
    judge = next(
        (
            item
            for item in layers
            if isinstance(item, dict) and item.get("layer") == JUDGE_LAYER
        ),
        None,
    )
    if judge is None or judge.get("status") != "EXECUTED":
        return "UNVERIFIABLE"
    if judge.get("passing") is True:
        return "MATCH"
    if judge.get("passing") is False:
        return "DRIFT"
    return "UNVERIFIABLE"


def build_competition_attempt_packet(
    *,
    sources: list[dict[str, Any]],
    challenge: dict[str, Any],
    attempt: dict[str, Any],
    answer_extraction: dict[str, Any],
    certificate_layers: list[dict[str, Any]],
    claim: str,
    scope: str,
    packet_id: str,
    uncertainty: list[str] | None = None,
    failure_labels: list[str] | None = None,
) -> dict[str, Any]:
    layers = [dict(layer) for layer in certificate_layers]
    overall = _derive_verdict(layers)
    packet = {
        "version": PACKET_VERSION,
        "packet_id": packet_id,
        "claim": claim,
        "scope": scope,
        "sources": [dict(s) for s in sources],
        "challenge": dict(challenge),
        "attempt": dict(attempt),
        "answer_extraction": dict(answer_extraction),
        "certificate_layers": layers,
        "verdicts": {
            "overall": overall,
            # Only what EXECUTED is citable: tier inflation is structurally
            # impossible for a built packet.
            "cited_layers": sorted(executed_layer_names(layers)),
        },
        "uncertainty": list(uncertainty or []),
        "decision_summary": derive_decision_summary(overall),
    }
    if failure_labels is not None:
        packet["failure_labels"] = list(failure_labels)
    return packet


def to_crucible_inputs(packet: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Emit crucible's (thesis, measurements) file contract for re-derivation."""
    challenge = packet.get("challenge", {}) or {}
    judge_repo = challenge.get("judge_repo", {}) or {}
    attempt = packet.get("attempt", {}) or {}
    overall = (packet.get("verdicts") or {}).get("overall")
    cited = (packet.get("verdicts") or {}).get("cited_layers") or []
    text = (
        f"Attempt {attempt.get('attempt_id')} on {challenge.get('challenge_ref')} "
        f"stage {challenge.get('stage')} reached verdict {overall} against judge "
        f"repo {judge_repo.get('repo_ref')} at {str(judge_repo.get('head_sha'))[:12]}."
    )
    thesis = {
        "title": f"Competition-attempt proof packet {packet.get('packet_id', '')}",
        "disposition": "publishable",
        "claims": [
            {
                "text": text,
                "falsification": (
                    "the judge-verdict layer did not execute and pass, or the "
                    "verdict cites a layer that did not execute."
                ),
            }
        ],
    }
    rows = [
        {
            "claim": text,
            "deviation": 0.0 if overall == "MATCH" else 1.0,
            "tolerance": 0.5,
            "method": "competition-judge-verdict",
            "evidence": [f"cited_layers={','.join(cited)}"],
        }
    ]
    return thesis, {"measurements": rows}
