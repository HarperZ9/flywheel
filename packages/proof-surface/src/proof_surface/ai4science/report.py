"""Reviewer-facing Markdown report for an AI4Science claim-to-experiment packet."""

from __future__ import annotations

from typing import Any

from .._boundary import render_boundary
from .._decision import render_decision_summary


def render_report(packet: dict[str, Any]) -> str:
    overall = (packet.get("verdicts") or {}).get("overall", "UNVERIFIABLE")
    protocol = packet.get("protocol") or {}
    measurement = packet.get("measurement") or {}
    reproduction = packet.get("reproduction") or {}
    objections = packet.get("reviewer_objections") or []
    open_count = sum(
        1 for o in objections if isinstance(o, dict) and o.get("status") == "open"
    )
    lines = [
        f"# AI4Science Claim-to-Experiment Packet `{packet.get('packet_id', '')}`",
        "",
        f"**Verdict: {overall} -- promotion {packet.get('promotion')}** -- "
        f"{packet.get('claim', '')}",
        "",
        f"- **Scope:** {packet.get('scope', '')} - **Domain:** {packet.get('domain')}",
        f"- **Claim:** {packet.get('scientific_claim')}",
        f"- **Protocol:** `{protocol.get('protocol_ref')}` "
        f"(runtime `{protocol.get('workflow_runtime')}`, "
        f"reproducible {protocol.get('reproducible')})",
        f"- **Measurement:** measured={measurement.get('measured')} "
        f"(value {measurement.get('value')} {measurement.get('unit') or ''})",
        f"- **Reproduction:** {reproduction.get('status')}",
        f"- **Negative result:** {packet.get('negative_result')}",
        f"- **Reviewer objections:** {len(objections)} ({open_count} open)",
    ]
    lines.extend(render_decision_summary(packet.get("decision_summary")))
    lines.extend(
        [
            "",
            "_Promotion is default-conservative: an unmeasured claim never reaches "
            "MEASURED, a non-reproduced claim never reaches REPRODUCED, and an open "
            "reviewer objection blocks peer-reviewed promotion. A single packet can "
            "never reach a promoted discovery._",
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
