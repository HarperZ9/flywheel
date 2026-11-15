from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import Finding, SweepSummary
from .text_hygiene import secret_rules


def format_text(findings: list[Finding]) -> str:
    if not findings:
        return "No findings."
    lines = []
    for item in findings:
        location = item.path if item.line == 0 else f"{item.path}:{item.line}"
        lines.append(f"{item.severity.upper()} {location} {item.rule}: {item.message}")
    return "\n".join(lines)


def summarize_findings(findings: list[Finding], action_limit: int = 8) -> SweepSummary:
    errors = sum(1 for item in findings if item.severity == "error")
    warnings = sum(1 for item in findings if item.severity == "warning")
    score = max(0, 100 - (errors * 25) - (warnings * 10))
    if errors:
        status = "blocked"
    elif warnings:
        status = "needs-polish"
    else:
        status = "ready"
    return SweepSummary(
        score=score,
        status=status,
        total_findings=len(findings),
        errors=errors,
        warnings=warnings,
        action_items=[_action_text(item) for item in findings[:action_limit]],
    )


def format_summary(summary: SweepSummary) -> str:
    lines = [
        f"score: {summary.score}",
        f"status: {summary.status}",
        f"total_findings: {summary.total_findings}",
        f"errors: {summary.errors}",
        f"warnings: {summary.warnings}",
        "action_items:",
    ]
    if summary.action_items:
        lines.extend(f"- {item}" for item in summary.action_items)
    else:
        lines.append("- none")
    return "\n".join(lines)


def proof_surface_packet(root: Path, findings: list[Finding]) -> dict[str, Any]:
    summary = summarize_findings(findings)
    required_gaps = sum(1 for item in findings if item.rule == "required-file")
    secret_hits = sum(1 for item in findings if item.rule in secret_rules())
    punctuation_hits = sum(1 for item in findings if item.rule == "em-dash")
    delivery_hits = sum(
        1
        for item in findings
        if item.rule.startswith(("readme-", "public-", "developer-"))
    )
    return {
        "proof_surface_version": "0.1",
        "packet_id": f"public-surface-sweeper-{root.resolve().name}",
        "surface": f"{root.resolve().name} public release surface",
        "status": summary.status,
        "claims": [
            {
                "claim": "Required public release files are visible.",
                "evidence": f"required-file findings={required_gaps}",
            },
            {
                "claim": "Secret-shaped values are surfaced before publication.",
                "evidence": f"secret-shaped findings={secret_hits}",
            },
            {
                "claim": "Public text hygiene is checkable.",
                "evidence": f"em-dash findings={punctuation_hits}",
            },
            {
                "claim": "Public and developer delivery are inspectable.",
                "evidence": f"delivery findings={delivery_hits}",
            },
        ],
        "checks": [
            {
                "tool": "public-surface-sweeper",
                "status": _packet_check_status(summary.status),
                "summary": f"score={summary.score}, findings={summary.total_findings}",
            }
        ],
        "action_items": summary.action_items,
    }


def _action_text(item: Finding) -> str:
    location = item.path if item.line == 0 else f"{item.path}:{item.line}"
    return f"{location}: {item.message}"


def _packet_check_status(status: str) -> str:
    if status == "ready":
        return "pass"
    if status == "needs-polish":
        return "warn"
    if status == "blocked":
        return "fail"
    return "unknown"
