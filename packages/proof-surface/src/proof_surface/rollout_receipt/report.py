"""Reviewer-facing Markdown report for a rollout-receipt proof packet."""

from __future__ import annotations

from typing import Any

from .._boundary import render_boundary
from .._decision import render_decision_summary


def _short(digest: Any) -> str:
    if isinstance(digest, str) and digest:
        return f"`{digest[:12]}...`"
    return "_none_"


def render_report(packet: dict[str, Any]) -> str:
    overall = (packet.get("verdicts") or {}).get("overall", "UNVERIFIABLE")
    rollout = packet.get("rollout") or {}
    reward = packet.get("reward") or {}
    verifier = packet.get("verifier") or {}
    admission = packet.get("admission") or {}
    promotion = packet.get("promotion") or {}
    lines = [
        f"# Rollout-Receipt Proof Packet `{packet.get('packet_id', '')}`",
        "",
        f"**Verdict: {overall}** -- {packet.get('claim', '')}",
        "",
        f"- **Scope:** {packet.get('scope', '')}",
        f"- **Rollout:** `{rollout.get('rollout_id')}` "
        f"(policy `{rollout.get('policy_ref')}`, checkpoint `{rollout.get('checkpoint_ref')}`)",
        f"- **Reward:** score {reward.get('score')} (model `{reward.get('model_ref')}`, "
        f"digest {_short(rollout.get('reward_digest'))})",
        f"- **Sandbox:** `{rollout.get('sandbox_receipt')}` "
        f"- **Dataset mutation:** `{rollout.get('dataset_mutation_ref')}`",
    ]
    lines.extend(render_decision_summary(packet.get("decision_summary")))
    lines.extend(
        [
            "",
            "## Separate records",
            "",
            f"- **Verifier verdict:** {verifier.get('verdict')} "
            f"(`{rollout.get('verifier_ref')}`)",
            f"- **Admission:** {admission.get('decision')}",
            f"- **Promotion:** {promotion.get('decision')} -- {promotion.get('reason')}",
            "",
            "_Reward score, verifier verdict, admission, and promotion are kept "
            "distinct: promotion is default-deny, granted only on a MATCH verifier "
            "and an allow admission._",
        ]
    )
    lines.extend(_render_list("Uncertainty", packet.get("uncertainty")))
    lines.extend(render_boundary())
    return "\n".join(lines)


def _render_list(title: str, items: Any) -> list[str]:
    out = ["", f"## {title}", ""]
    if isinstance(items, list) and items:
        out.extend(f"- {item}" for item in items)
    else:
        out.append("_none_")
    return out
