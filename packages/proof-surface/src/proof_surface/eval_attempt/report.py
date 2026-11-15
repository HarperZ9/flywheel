"""Reviewer-facing Markdown report for an eval-attempt proof packet."""

from __future__ import annotations

from typing import Any

from .._boundary import render_boundary
from .._decision import render_decision_summary


def render_report(packet: dict[str, Any]) -> str:
    overall = (packet.get("verdicts") or {}).get("overall", "UNVERIFIABLE")
    benchmark = packet.get("benchmark") or {}
    attempt = packet.get("attempt") or {}
    result = packet.get("result") or {}
    boundaries = packet.get("boundaries") or {}
    tools = ", ".join(
        f"`{t.get('tool')}`"
        for t in (attempt.get("tool_use") or [])
        if isinstance(t, dict)
    )
    lines = [
        f"# Eval-Attempt Proof Packet `{packet.get('packet_id', '')}`",
        "",
        f"**Verdict: {overall}** -- {packet.get('claim', '')}",
        "",
        f"- **Scope:** {packet.get('scope', '')}",
        f"- **Benchmark:** `{benchmark.get('benchmark_ref')}` task "
        f"`{benchmark.get('task_id')}` (authority `{benchmark.get('authority_receipt')}`)",
        f"- **Attempt:** `{attempt.get('attempt_id')}` -- model "
        f"`{attempt.get('model_ref')}`, prompt `{attempt.get('prompt_ref')}`, "
        f"replay `{attempt.get('replay_ref')}`",
        f"- **Tools used:** {tools or '_none_'}",
        f"- **Outcome:** {result.get('outcome')} (score {result.get('score')})",
        f"- **Boundaries:** had_ground_truth={boundaries.get('had_ground_truth')}, "
        f"had_internet={boundaries.get('had_internet')}, "
        f"had_tools={boundaries.get('had_tools')} "
        "(a correct outcome with ground-truth access is contamination, not a pass)",
    ]
    lines.extend(render_decision_summary(packet.get("decision_summary")))
    lines.extend(_render_list("Uncertainty", packet.get("uncertainty")))
    lines.append("")
    lines.append(
        "_The verdict is re-derivable: the packet emits a crucible thesis + "
        "measurements so an independent checker recomputes the outcome from the "
        "same evidence._"
    )
    lines.extend(render_boundary())
    return "\n".join(lines)


def _render_list(title: str, items: Any) -> list[str]:
    out = ["", f"## {title}", ""]
    if isinstance(items, list) and items:
        out.extend(f"- {item}" for item in items)
    else:
        out.append("_none_")
    return out
