"""Reviewer-facing Markdown report for a research-claim proof packet."""

from __future__ import annotations

from typing import Any

from .._boundary import render_boundary
from .._decision import render_decision_summary


def render_report(packet: dict[str, Any]) -> str:
    verdicts = packet.get("verdicts") or {}
    overall = verdicts.get("overall", "UNVERIFIABLE")
    lines = [
        f"# Research-Claim Proof Packet `{packet.get('packet_id', '')}`",
        "",
        f"**Verdict: {overall} - Promotion: {packet.get('promotion', '')}** "
        f"-- {packet.get('claim', '')}",
        "",
        f"- **Scope:** {packet.get('scope', '')}",
        "",
        "## Statement",
        "",
        f"> {packet.get('statement', '')}",
    ]
    lines.extend(render_decision_summary(packet.get("decision_summary")))
    lines.extend(_sources(packet.get("sources")))
    lines.extend(_attempts(packet.get("attempts")))
    lines.extend(_checks(packet))
    lines.extend(_section("Uncertainty", packet.get("uncertainty")))
    lines.append("")
    lines.append(
        "_Verdict re-derivable via crucible from the emitted thesis + measurements. "
        "A failed or UNVERIFIABLE packet still preserves the sources, attempts, and "
        "next checks -- a negative result is evidence, not a discarded run._"
    )
    lines.extend(render_boundary())
    return "\n".join(lines)


def _sources(sources: Any) -> list[str]:
    out = ["", "## Sources", ""]
    if isinstance(sources, list) and sources:
        for s in sources:
            if not isinstance(s, dict):
                continue
            extra = f" <{s.get('url')}>" if s.get("url") else ""
            digest = f" (`{str(s.get('sha256'))[:12]}...`)" if s.get("sha256") else ""
            out.append(f"- {s.get('ref')}{extra}{digest}")
    else:
        out.append("_none_")
    return out


def _attempts(attempts: Any) -> list[str]:
    out = ["", "## Attempts", ""]
    if isinstance(attempts, list) and attempts:
        for a in attempts:
            if not isinstance(a, dict):
                continue
            notes = f": {a.get('notes')}" if a.get("notes") else ""
            out.append(
                f"- `{a.get('attempt_id')}` {a.get('method')} -> {a.get('result')}{notes}"
            )
    else:
        out.append("_none_")
    return out


def _checks(packet: dict[str, Any]) -> list[str]:
    verdicts = packet.get("verdicts") or {}
    status_by = {
        pc.get("checker"): pc.get("status")
        for pc in (verdicts.get("per_check") or [])
        if isinstance(pc, dict)
    }
    out = ["", "## Checks", "", "| Checker | Status | Verdict |", "| --- | --- | --- |"]
    for c in packet.get("checks") or []:
        if not isinstance(c, dict):
            continue
        out.append(
            f"| {c.get('checker')} | {c.get('status')} | {status_by.get(c.get('checker'), '?')} |"
        )
    return out


def _section(title: str, items: Any) -> list[str]:
    out = ["", f"## {title}", ""]
    if isinstance(items, list) and items:
        out.extend(f"- {item}" for item in items)
    else:
        out.append("_none_")
    return out
