"""Render proof-surface JSON artifacts as a concise Markdown handoff report.

This adapter validates against the shared ``proof-surface`` contract package
(the single source of truth for the packet and witness-receipt shapes) and emits
reviewer-facing Markdown. It does not certify, trust, approve, sign, upload, or
enforce anything.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from proof_surface import PACKET_VERSION
from proof_surface import validate_packet as validate_packet_shared
from proof_surface import validate_witness_receipt as validate_witness_receipt_shared

STATUS_ORDER = {"blocked": 3, "needs-polish": 2, "unknown": 1, "ready": 0}
AUTHORITY_PATTERNS = (
    (
        "authority-token",
        re.compile(
            r"(?<![A-Z0-9_])"
            r"(?:TRUSTED|APPROVED|SAFE|ALLOWED|PERMITTED|AUTHORIZED|CERTIFIED|COMPLIANT)"
            r"(?![A-Z0-9_])"
        ),
    ),
    ("trusted", re.compile(r"\btrust(?:ed|worthy)?\b", re.IGNORECASE)),
    ("approved", re.compile(r"\bapprov(?:e|es|ed|al)\b", re.IGNORECASE)),
    ("authorized", re.compile(r"\bauthori[sz](?:e|es|ed|ation)\b", re.IGNORECASE)),
    ("certified", re.compile(r"\bcertif(?:y|ies|ied|ication)\b", re.IGNORECASE)),
    ("compliant", re.compile(r"\bcomplian(?:t|ce)\b", re.IGNORECASE)),
    ("safe-for-release", re.compile(r"\bsafe\s+(?:to|for)\b", re.IGNORECASE)),
    ("permitted", re.compile(r"\bpermit(?:s|ted)?\b", re.IGNORECASE)),
    ("allowed", re.compile(r"\ballow(?:s|ed)?\b", re.IGNORECASE)),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render proof-surface packet or witness receipt JSON as Markdown."
    )
    parser.add_argument("artifacts", nargs="+", type=Path, help="JSON artifacts.")
    parser.add_argument(
        "--title",
        default="Proof Surface Handoff Report",
        help="Markdown report title.",
    )
    return parser


def load_artifact(path: Path) -> tuple[str, dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    if data.get("proof_surface_version") == PACKET_VERSION:
        validate_packet(path, data)
        return "packet", data
    if "receipt_id" in data and "verdict" in data:
        validate_receipt(path, data)
        return "witness_receipt", data
    raise ValueError(f"{path} is not a proof-surface packet or witness receipt")


def validate_packet(path: Path, data: dict[str, Any]) -> None:
    """Validate a proof-surface packet via the shared contract, then sweep for
    authority-shaped wording in this adapter's reviewer-facing text fields.

    Structural validation (field sets, status enum, version const, claim/check/
    action shapes) is delegated to ``proof_surface.validate_packet`` -- the single
    source of truth for the packet contract. The case-insensitive authority-
    language rejection is this adapter's own concern and is layered on top: the
    shared packet validator deliberately does not editorialize free text.
    """
    issues = [f"{issue.path} {issue.message}" for issue in validate_packet_shared(data)]
    sweep_packet_authority_language(data, issues)
    if issues:
        raise ValueError(f"{path} packet validation failed: " + "; ".join(issues))


def validate_receipt(path: Path, data: dict[str, Any]) -> None:
    """Validate an EMET witness receipt via the shared consumer-side validator.

    ``proof_surface.validate_witness_receipt`` mirrors EMET's witness-receipt
    shape, enforces the closed verdict lattice, and recursively rejects EMET's
    forbidden authority tokens across all free-text fields. This adapter adds its
    own case-insensitive authority-language sweep over the notes field for the
    reviewer-facing report.
    """
    issues = [f"{issue.path} {issue.message}" for issue in validate_witness_receipt_shared(data)]
    reject_authority_language(data.get("notes"), "$.notes", issues)
    if issues:
        raise ValueError(f"{path} receipt validation failed: " + "; ".join(issues))


def sweep_packet_authority_language(data: dict[str, Any], issues: list[str]) -> None:
    """Reject authority-shaped wording in the packet's reviewer-facing text."""
    reject_authority_language(data.get("surface"), "$.surface", issues)
    for index, item in enumerate(array(data.get("claims"))):
        if isinstance(item, dict):
            reject_authority_language(item.get("claim"), f"$.claims[{index}].claim", issues)
            reject_authority_language(item.get("evidence"), f"$.claims[{index}].evidence", issues)
    for index, item in enumerate(array(data.get("checks"))):
        if isinstance(item, dict):
            reject_authority_language(item.get("summary"), f"$.checks[{index}].summary", issues)
    for index, item in enumerate(array(data.get("action_items"))):
        reject_authority_language(item, f"$.action_items[{index}]", issues)


def reject_authority_language(value: Any, path: str, issues: list[str]) -> None:
    if not isinstance(value, str):
        return
    for label, pattern in AUTHORITY_PATTERNS:
        if pattern.search(value):
            issues.append(f"{path} contains authority-shaped wording: {label}")


def text(value: Any, default: str = "unknown") -> str:
    return value if isinstance(value, str) and value else default


def array(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def aggregate_status(packets: list[dict[str, Any]]) -> str:
    if not packets:
        return "unknown"
    return max(
        (text(packet.get("status")) for packet in packets),
        key=lambda status: STATUS_ORDER.get(status, STATUS_ORDER["unknown"]),
    )


def count_items(packets: list[dict[str, Any]], field: str) -> int:
    return sum(len(array(packet.get(field))) for packet in packets)


def render_summary(
    lines: list[str],
    packets: list[dict[str, Any]],
    receipts: list[dict[str, Any]],
) -> None:
    lines.extend(
        [
            "## Summary",
            "",
            "| Field | Value |",
            "| --- | --- |",
            f"| Packets | {len(packets)} |",
            f"| Witness receipts | {len(receipts)} |",
            f"| Aggregate status | {aggregate_status(packets)} |",
            f"| Claims | {count_items(packets, 'claims')} |",
            f"| Checks | {count_items(packets, 'checks')} |",
            f"| Action items | {count_items(packets, 'action_items')} |",
            "",
        ]
    )


def render_packet(lines: list[str], path: Path, packet: dict[str, Any]) -> None:
    lines.extend(
        [
            f"## {text(packet.get('surface'))}",
            "",
            "| Field | Value |",
            "| --- | --- |",
            f"| Packet | {text(packet.get('packet_id'))} |",
            f"| Status | {text(packet.get('status'))} |",
            f"| Source | `{path.as_posix()}` |",
            "",
            "### Claims",
            "",
        ]
    )
    claims = array(packet.get("claims"))
    lines.extend(render_claim(claim) for claim in claims) if claims else lines.append("- none")
    lines.extend(["", "### Checks", ""])
    checks = array(packet.get("checks"))
    lines.extend(render_check(check) for check in checks) if checks else lines.append("- none")
    lines.extend(["", "### Action Items", ""])
    actions = array(packet.get("action_items"))
    lines.extend(f"- {text(action)}" for action in actions) if actions else lines.append("- none")
    lines.append("")


def render_receipt(lines: list[str], path: Path, receipt: dict[str, Any]) -> None:
    witness = receipt.get("witness") if isinstance(receipt.get("witness"), dict) else {}
    evidence = receipt.get("evidence") if isinstance(receipt.get("evidence"), dict) else {}
    lines.extend(
        [
            f"## Witness Receipt: {text(receipt.get('receipt_id'))}",
            "",
            "| Field | Value |",
            "| --- | --- |",
            f"| Verdict | {text(receipt.get('verdict'))} |",
            f"| Witness | {text(witness.get('implementation'))} |",
            f"| Check | {text(witness.get('check'))} |",
            f"| Source | `{path.as_posix()}` |",
            f"| Exit code | {text(str(evidence.get('exit_code', 'unknown')))} |",
            "",
            "### Subject",
            "",
        ]
    )
    subjects = array(receipt.get("subject"))
    lines.extend(render_subject(item) for item in subjects) if subjects else lines.append("- none")
    lines.extend(["", "### Evidence", ""])
    lines.append(f"- stdout verdict line: {text(evidence.get('stdout_verdict_line'))}")
    lines.append(f"- notes: {text(receipt.get('notes'))}")
    lines.append("")


def render_claim(claim: Any) -> str:
    if not isinstance(claim, dict):
        return f"- {text(claim)}"
    return f"- {text(claim.get('claim'))} Evidence: {text(claim.get('evidence'))}"


def render_check(check: Any) -> str:
    if not isinstance(check, dict):
        return f"- {text(check)}"
    return (
        f"- {text(check.get('tool'))}: {text(check.get('status'))}. "
        f"{text(check.get('summary'))}"
    )


def render_subject(subject: Any) -> str:
    if not isinstance(subject, dict):
        return f"- {text(subject)}"
    digest = subject.get("digest") if isinstance(subject.get("digest"), dict) else {}
    return f"- {text(subject.get('name'))}: sha256={text(digest.get('sha256'))}"


def render_report(title: str, artifact_paths: list[Path]) -> str:
    title_issues: list[str] = []
    reject_authority_language(title, "$.title", title_issues)
    if title_issues:
        raise ValueError("report title validation failed: " + "; ".join(title_issues))

    artifacts = [(path, *load_artifact(path)) for path in artifact_paths]
    packets = [data for _, kind, data in artifacts if kind == "packet"]
    receipts = [data for _, kind, data in artifacts if kind == "witness_receipt"]
    lines = [
        f"# {title}",
        "",
        "This report summarizes proof-surface artifacts. It is an evidence handoff,",
        "not a certification, safety verdict, or authority claim.",
        "",
    ]
    render_summary(lines, packets, receipts)
    for path, kind, data in artifacts:
        if kind == "packet":
            render_packet(lines, path, data)
        else:
            render_receipt(lines, path, data)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        print(render_report(args.title, args.artifacts))
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0
