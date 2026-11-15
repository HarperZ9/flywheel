"""Human-gap check for acts that cannot be synthesized by a tool.

The gate can record that a human act is required and can check whether external
operator attestation evidence was supplied. It does not perform authorship,
re-derivation, viva defense, or any other human-owned act.
"""

from __future__ import annotations

import re
from typing import Any

from ._validate import Issue, reject_unknown, require_text


PASS = "pass"
UNKNOWN = "unknown"
NOT_APPLICABLE = "not-applicable"

HUMAN_GAP_FIELDS = {
    "requires_human_act",
    "act_kind",
    "evidence_label",
    "evidence_digest",
    "operator_attested",
}
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


def validate_human_gap(value: Any, issues: list[Issue]) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        issues.append(Issue("$.human_gap", "expected object"))
        return

    reject_unknown(value, "$.human_gap", HUMAN_GAP_FIELDS, issues)
    flag = value.get("requires_human_act")
    if not isinstance(flag, bool):
        issues.append(Issue("$.human_gap.requires_human_act", "expected boolean"))
    require_text(value, "act_kind", issues, "$.human_gap.act_kind")

    if "evidence_label" in value:
        require_text(value, "evidence_label", issues, "$.human_gap.evidence_label")
    if "evidence_digest" in value:
        digest = value["evidence_digest"]
        if not isinstance(digest, str) or not _HEX64_RE.match(digest):
            issues.append(
                Issue(
                    "$.human_gap.evidence_digest",
                    "expected 64-char lowercase hex digest",
                )
            )
    if "operator_attested" in value and not isinstance(
        value["operator_attested"], bool
    ):
        issues.append(Issue("$.human_gap.operator_attested", "expected boolean"))


def check_human_gap(value: dict[str, Any] | None) -> tuple[str, list[str]]:
    if value is None or value.get("requires_human_act") is False:
        return NOT_APPLICABLE, []

    act_kind = str(value.get("act_kind") or "human act")
    missing: list[str] = []
    if value.get("operator_attested") is not True:
        missing.append("operator attestation")
    if not value.get("evidence_label"):
        missing.append("evidence label")
    if not value.get("evidence_digest"):
        missing.append("evidence digest")

    if missing:
        return UNKNOWN, [
            "human gap open: "
            f"{act_kind} requires external human evidence; missing {', '.join(missing)}"
        ]
    return PASS, []
