"""Reviewer-facing Markdown report for a visual-measurement proof packet."""

from __future__ import annotations

from typing import Any

from .._boundary import render_boundary
from .._decision import render_decision_summary


def _short(digest: Any) -> str:
    if isinstance(digest, str) and digest:
        return f"`{digest[:12]}...`"
    return "_none_"


def render_report(packet: dict[str, Any]) -> str:
    verdicts = packet.get("verdicts") or {}
    overall = verdicts.get("overall", "UNVERIFIABLE")
    art = packet.get("artifact") or {}
    color = packet.get("color") or {}
    lines = [
        f"# Visual-Measurement Proof Packet `{packet.get('packet_id', '')}`",
        "",
        f"**Verdict: {overall}** -- {packet.get('claim', '')}",
        "",
        f"- **Scope:** {packet.get('scope', '')}",
        f"- **Read-only:** {packet.get('read_only')} "
        "(non-mutation boundary: no LUT / ICC / DDC change is applied or claimed)",
        _calibration_line(packet.get("calibration_boundary")),
        "",
        "## Artifact",
        "",
        f"- `{art.get('name')}` ({art.get('kind')}, {art.get('width')}x{art.get('height')})"
        f" -- {_short(art.get('sha256'))}",
        "",
        "## Color assumptions",
        "",
        f"- space `{color.get('color_space')}` - transfer `{color.get('transfer')}`"
        f" - white point `{color.get('white_point')}`",
    ]
    lines.extend(render_decision_summary(packet.get("decision_summary")))
    lines.extend(
        [
            "",
            "## Measurements",
            "",
            "| Metric | Value | Target | Deviation | Tolerance | Verdict |",
            "| --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    lines.extend(_measurement_rows(packet))
    lines.extend(_section("Display caveats", packet.get("display_caveats")))
    lines.extend(_section("Uncertainty", packet.get("uncertainty")))
    lines.append("")
    lines.append(
        "_Every verdict is re-derivable: the packet emits a crucible thesis + "
        "measurements so an independent checker recomputes it from the same evidence._"
    )
    lines.extend(render_boundary())
    return "\n".join(lines)


def _calibration_line(cb: Any) -> str:
    if not isinstance(cb, dict):
        return (
            "- **Calibration boundary:** _not declared_ "
            "(no physical display calibration is claimed)"
        )
    return (
        f"- **Calibration boundary:** hardware_measurement_used="
        f"{cb.get('hardware_measurement_used')}, physical_calibration_claim="
        f"{cb.get('physical_calibration_claim')} "
        "(a read-only surface makes no physical-calibration claim)"
    )


def _measurement_rows(packet: dict[str, Any]) -> list[str]:
    verdicts = packet.get("verdicts") or {}
    status_by = {
        pm.get("metric"): pm.get("status")
        for pm in (verdicts.get("per_metric") or [])
        if isinstance(pm, dict)
    }
    rows = []
    for m in packet.get("measurements") or []:
        if not isinstance(m, dict):
            continue
        rows.append(
            f"| {m.get('metric')} | {m.get('value')} {m.get('unit')} | {m.get('target')} "
            f"| {m.get('deviation')} | {m.get('tolerance')} | {status_by.get(m.get('metric'), '?')} |"
        )
    return rows


def _section(title: str, items: Any) -> list[str]:
    out = ["", f"## {title}", ""]
    if isinstance(items, list) and items:
        out.extend(f"- {item}" for item in items)
    else:
        out.append("_none_")
    return out
