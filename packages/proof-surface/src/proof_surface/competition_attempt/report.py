"""Reviewer-facing Markdown report for a competition-attempt proof packet."""

from __future__ import annotations

from typing import Any

from .._boundary import render_boundary
from .._decision import render_decision_summary


def _attempt_line(attempt: dict[str, Any]) -> str:
    """One-line attempt disclosure, honest about undisclosed hosted-model usage."""
    head = f"- **Attempt:** {attempt.get('attempt_id')} on {attempt.get('model_ref')}"
    calls = attempt.get("external_model_calls")
    if calls is None:
        return head + " -- hosted-model usage undisclosed"
    receipt = attempt.get("provider_receipt_ref")
    suffix = f" (receipt: {receipt})" if receipt else ""
    return head + f" -- external model calls: {calls}{suffix}"


def _layer_rows(layers: Any) -> list[str]:
    """The certificate-ladder table body: one row per layer, EXECUTED or fenced."""
    rows: list[str] = []
    for layer in layers or []:
        if not isinstance(layer, dict):
            continue
        evidence = layer.get("evidence_ref") or layer.get("probe_evidence") or ""
        passing = layer.get("passing")
        rows.append(
            f"| {layer.get('layer')} | {layer.get('status')} "
            f"| {'-' if passing is None else passing} | {evidence} |"
        )
    return rows


def render_report(packet: dict[str, Any]) -> str:
    verdicts = packet.get("verdicts") or {}
    overall = verdicts.get("overall", "UNVERIFIABLE")
    challenge = packet.get("challenge") or {}
    judge_repo = challenge.get("judge_repo") or {}
    extraction = packet.get("answer_extraction") or {}
    lines = [
        f"# Competition-Attempt Proof Packet `{packet.get('packet_id', '')}`",
        "",
        f"**Verdict: {overall}** -- {packet.get('claim', '')}",
        "",
        f"- **Scope:** {packet.get('scope', '')}",
        f"- **Challenge:** {challenge.get('challenge_ref')} "
        f"(stage: {challenge.get('stage')})",
        f"- **Judge repo (source-pinned):** {judge_repo.get('repo_ref')} at "
        f"`{str(judge_repo.get('head_sha'))[:12]}`, "
        f"{judge_repo.get('observed_files')} file(s), files digest "
        f"`{str(judge_repo.get('files_digest'))[:16]}...`",
        _attempt_line(packet.get("attempt") or {}),
        f"- **Answer extraction:** {extraction.get('method')} from "
        f"{extraction.get('extracted_ref')} "
        f"(injection_checked: {extraction.get('injection_checked')})",
        f"- **Cited layers:** "
        f"{', '.join(verdicts.get('cited_layers') or []) or 'none'}",
    ]
    lines.extend(render_decision_summary(packet.get("decision_summary")))
    lines.extend(["", "## Certificate layers", ""])
    lines.append("| Layer | Status | Passing | Evidence / probe |")
    lines.append("| --- | --- | --- | --- |")
    lines.extend(_layer_rows(packet.get("certificate_layers")))
    lines.extend(
        [
            "",
            "_The verdict may only cite layers that EXECUTED; an "
            "UNAVAILABLE_FENCED layer must cite the probe that proved the "
            "fence, and MATCH is only derivable from an executed, passing "
            "judge verdict._",
        ]
    )
    lines.extend(render_boundary())
    return "\n".join(lines)
