"""Reviewer-facing Markdown report for an optimization-workflow proof packet."""

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
    problem = packet.get("problem") or {}
    space = packet.get("candidate_space") or {}
    baseline = packet.get("baseline") or {}
    solver = packet.get("solver") or {}
    boundary = packet.get("boundary") or {}
    lines = [
        f"# Optimization-Workflow Proof Packet `{packet.get('packet_id', '')}`",
        "",
        f"**Verdict: {overall}** -- {packet.get('claim', '')}",
        "",
        f"- **Scope:** {packet.get('scope', '')}",
        f"- **Problem:** {problem.get('sense')} `{problem.get('objective')}`",
        f"- **Constraints:** {', '.join(problem.get('constraints') or []) or '_none_'}",
        f"- **Candidate space:** {space.get('variables')} vars, "
        f"{space.get('evaluated')} evaluated "
        f"({space.get('feasible')} feasible / {space.get('infeasible')} infeasible)",
        f"- **Exact baseline:** {baseline.get('objective_value')} "
        f"(`{baseline.get('method')}`, digest {_short(baseline.get('candidate_digest'))})",
    ]
    lines.extend(render_decision_summary(packet.get("decision_summary")))
    lines.extend(
        [
            "",
            "## Solver branch",
            "",
            f"- `{solver.get('branch_id')}` ({solver.get('method')}) -- "
            f"status {solver.get('status')}",
            f"- objective {solver.get('objective_value')}; "
            f"constraints {solver.get('constraint_status')}"
            f" ({solver.get('constraint_encoding') or 'unspecified'} encoding); "
            f"tolerance {solver.get('tolerance')}",
            f"- selected: {', '.join(solver.get('selected') or []) or '_none_'}",
            "",
            "## Boundary",
            "",
            f"- quantum_advantage_claim={boundary.get('quantum_advantage_claim')}, "
            f"hardware_execution_claim={boundary.get('hardware_execution_claim')} "
            "(an exact/toy solve claims neither hardware execution nor quantum advantage)",
        ]
    )
    lines.extend(_render_branches(packet.get("solver_branches")))
    lines.extend(_render_list("Uncertainty", packet.get("uncertainty")))
    lines.append("")
    lines.append(
        "_The verdict is re-derivable: the packet emits a crucible thesis + "
        "measurements so an independent checker recomputes the solver-vs-baseline "
        "obligation from the same evidence._"
    )
    lines.extend(render_boundary())
    return "\n".join(lines)


def _render_branches(branches: Any) -> list[str]:
    if not isinstance(branches, list) or not branches:
        return []
    out = ["", "## Comparison branches", ""]
    for b in branches:
        if not isinstance(b, dict):
            continue
        runtime = f" [{b.get('runtime')}]" if b.get("runtime") else ""
        gap = b.get("gap")
        gap_txt = f", gap {gap}" if gap is not None else ""
        enc = (
            f", encoding {b.get('constraint_encoding')}"
            if b.get("constraint_encoding")
            else ""
        )
        blocked = " PROMOTION-BLOCKED" if b.get("promotion_blocked") else ""
        out.append(
            f"- `{b.get('branch_id')}` ({b.get('method')}){runtime} -- "
            f"{b.get('status')}; objective {b.get('objective_value')}{gap_txt}; "
            f"vs baseline {b.get('baseline_match')}{enc}{blocked}"
        )
    return out


def _render_list(title: str, items: Any) -> list[str]:
    out = ["", f"## {title}", ""]
    if isinstance(items, list) and items:
        out.extend(f"- {item}" for item in items)
    else:
        out.append("_none_")
    return out
