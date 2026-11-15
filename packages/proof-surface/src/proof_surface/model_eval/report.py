"""Reviewer-facing Markdown report for a model-eval proof packet."""

from __future__ import annotations

from typing import Any

from .._boundary import render_boundary
from .._decision import render_decision_summary


def render_report(packet: dict[str, Any]) -> str:
    verdicts = packet.get("verdicts") or {}
    overall = verdicts.get("overall", "UNVERIFIABLE")
    decision = packet.get("decision") or {}
    model = packet.get("model") or {}
    eval_set = packet.get("eval_set") or {}
    objective = packet.get("objective") or {}

    cfg = model.get("config_hash")
    cfg_note = f" cfg `{str(cfg)[:12]}...`" if cfg else ""
    size = eval_set.get("size")
    size_note = f", {size} items" if size is not None else ""

    lines = [
        f"# Model-Eval Proof Packet `{packet.get('packet_id', '')}`",
        "",
        f"**Decision: {str(decision.get('outcome', '')).upper()} - Verdict: {overall}** "
        f"-- {packet.get('claim', '')}",
        "",
        f"- **Reason:** {decision.get('reason', '')}",
        f"- **Scope:** {packet.get('scope', '')}",
        f"- **Model:** `{model.get('id')}` ({model.get('provider')}){cfg_note}",
        f"- **Eval set:** {eval_set.get('name')} (`{eval_set.get('ref')}`{size_note})",
        f"- **Objective:** {objective.get('name')} -- {objective.get('summary')}",
    ]
    lines.extend(render_decision_summary(packet.get("decision_summary")))
    lines.extend(
        [
            "",
            "## Metrics",
            "",
            "| Metric | Value | Target | Dir | Deviation | Tolerance | Verdict |",
            "| --- | ---: | ---: | --- | ---: | ---: | --- |",
        ]
    )
    lines.extend(_metric_rows(packet))
    lines.extend(_section("Uncertainty", packet.get("uncertainty")))
    lines.append("")
    lines.append(
        "_Default-deny: a model is promoted only if the overall verdict is MATCH. "
        "The verdict is re-derivable via crucible from the emitted thesis + measurements._"
    )
    lines.extend(render_boundary())
    return "\n".join(lines)


def _metric_rows(packet: dict[str, Any]) -> list[str]:
    verdicts = packet.get("verdicts") or {}
    status_by = {
        pm.get("metric"): pm.get("status")
        for pm in (verdicts.get("per_metric") or [])
        if isinstance(pm, dict)
    }
    rows = []
    for m in packet.get("metrics") or []:
        if not isinstance(m, dict):
            continue
        unit = f" {m.get('unit')}" if m.get("unit") else ""
        rows.append(
            f"| {m.get('metric')} | {m.get('value')}{unit} | {m.get('target')} "
            f"| {m.get('direction')} | {m.get('deviation')} | {m.get('tolerance')} "
            f"| {status_by.get(m.get('metric'), '?')} |"
        )
    return rows


def _section(title: str, items: Any) -> list[str]:
    out = ["", f"## {title}", ""]
    if isinstance(items, list) and items:
        out.extend(f"- {item}" for item in items)
    else:
        out.append("_none_")
    return out
