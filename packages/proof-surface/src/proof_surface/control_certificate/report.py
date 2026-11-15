"""Reviewer-facing Markdown report for a control-certificate proof packet."""

from __future__ import annotations

from typing import Any

from .._boundary import render_boundary
from .._decision import render_decision_summary


def render_report(packet: dict[str, Any]) -> str:
    overall = (packet.get("verdicts") or {}).get("overall", "UNVERIFIABLE")
    system = packet.get("system") or {}
    certificate = packet.get("certificate") or {}
    negative = packet.get("negative_fixture") or {}
    sim_to_real = packet.get("sim_to_real") or {}
    lines = [
        f"# Control-Certificate Proof Packet `{packet.get('packet_id', '')}`",
        "",
        f"**Verdict: {overall}** -- {packet.get('claim', '')}",
        "",
        f"- **Scope:** {packet.get('scope', '')} - **Domain:** {system.get('domain')}",
        f"- **System:** {system.get('description')} (regime: {system.get('regime')})",
        f"- **Certificate:** {certificate.get('kind')} `{certificate.get('name')}` "
        f"({certificate.get('declared') or 'n/a'}) -- provenance: "
        f"{certificate.get('provenance')}"
        + (
            f" ({certificate.get('provenance_ref')})"
            if certificate.get("provenance_ref")
            else ""
        ),
        f"- **Trajectory:** {(packet.get('trajectory') or {}).get('samples')} "
        f"sample(s), log sha256 "
        f"{str((packet.get('trajectory') or {}).get('log_sha256'))[:16]}...",
    ]
    lines.extend(render_decision_summary(packet.get("decision_summary")))
    lines.extend(["", "## Witnessed conditions", ""])
    lines.append("| Condition | Residual | Tolerance | Holds |")
    lines.append("| --- | ---: | ---: | --- |")
    for w in packet.get("witnesses") or []:
        if not isinstance(w, dict):
            continue
        holds = (
            "yes"
            if _num(w.get("residual")) is not None
            and _num(w.get("tolerance")) is not None
            and w["residual"] <= w["tolerance"]
            else "no"
        )
        lines.append(
            f"| {w.get('condition')} | {w.get('residual')} | {w.get('tolerance')} "
            f"| {holds} |"
        )
    lines.extend(
        [
            "",
            "## Negative fixture (must violate)",
            "",
            f"- {negative.get('description')}: condition {negative.get('condition')} "
            f"residual {negative.get('residual')} > tolerance "
            f"{negative.get('tolerance')} -> violates_certificate "
            f"{negative.get('violates_certificate')}",
            "",
            "_A certificate check must carry a negative fixture that provably "
            "violates it: a verifier that cannot fail on a known-unstable input is "
            "not a verifier._",
            "",
            "## Sim-to-real boundary",
            "",
            f"- hardware_validity_claim: {sim_to_real.get('hardware_validity_claim')}"
            f" - hardware_evidence: "
            f"{', '.join(sim_to_real.get('hardware_evidence') or []) or 'none'}",
            "",
            "_Verified in simulation is not verified on hardware; a hardware "
            "validity claim requires hardware evidence and a hardware regime._",
        ]
    )
    lines.extend(render_boundary())
    return "\n".join(lines)


def _num(value: Any) -> Any:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    return None
