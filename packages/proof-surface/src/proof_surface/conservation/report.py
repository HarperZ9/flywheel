"""Reviewer-facing Markdown report for a conservation proof packet."""

from __future__ import annotations

from typing import Any

from .._boundary import render_boundary
from .._decision import render_decision_summary


def render_report(packet: dict[str, Any]) -> str:
    overall = (packet.get("verdicts") or {}).get("overall", "UNVERIFIABLE")
    transformation = packet.get("transformation") or {}
    invariant = packet.get("invariant") or {}
    negative = packet.get("negative_fixture") or {}
    lines = [
        f"# Conservation Proof Packet `{packet.get('packet_id', '')}`",
        "",
        f"**Verdict: {overall}** -- {packet.get('claim', '')}",
        "",
        f"- **Scope:** {packet.get('scope', '')} - **Domain:** {transformation.get('domain')}",
        f"- **Transformation:** {transformation.get('description')}",
        f"- **Invariant:** `{invariant.get('name')}` ({invariant.get('declared') or 'n/a'})",
    ]
    lines.extend(render_decision_summary(packet.get("decision_summary")))
    lines.extend(["", "## Witnesses", ""])
    lines.append("| Kind | Drift | Tolerance | Conserved |")
    lines.append("| --- | ---: | ---: | --- |")
    for w in packet.get("witnesses") or []:
        if not isinstance(w, dict):
            continue
        conserved = (
            "yes"
            if _num(w.get("drift")) is not None
            and _num(w.get("tolerance")) is not None
            and w["drift"] <= w["tolerance"]
            else "no"
        )
        lines.append(
            f"| {w.get('kind')} | {w.get('drift')} | {w.get('tolerance')} | {conserved} |"
        )
    lines.extend(
        [
            "",
            "## Negative fixture (must break)",
            "",
            f"- {negative.get('description')}: drift {negative.get('drift')} "
            f"> tolerance {negative.get('tolerance')} -> breaks_invariant "
            f"{negative.get('breaks_invariant')}",
            "",
            "_A conservation check must carry a negative fixture that provably breaks "
            "the invariant: a verifier that cannot fail on a known-bad input is not a "
            "verifier._",
        ]
    )
    boundary = packet.get("boundary_fixture")
    if isinstance(boundary, dict):
        lines.extend(
            [
                "",
                "## Boundary fixture (sufficient, not necessary)",
                "",
                f"- {boundary.get('description')}: goal_holds="
                f"{boundary.get('goal_holds')}, condition_holds="
                f"{boundary.get('condition_holds')} -- the goal is reached without the "
                "claimed condition, so the condition is sufficient but not necessary.",
            ]
        )
    lines.extend(render_boundary())
    return "\n".join(lines)


def _num(value: Any) -> Any:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    return None
