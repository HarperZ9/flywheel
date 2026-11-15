"""Shared N-instance replication gate (harvest of dogfood pass 0145).

Portable finding: a single-instance MATCH is never a generalization/scale claim.
A scale claim requires the SAME contract to replay across two or more independent
instances, all MATCH, with per-instance warnings preserved -- never dropped.

The ``replication`` object is optional; a packet without it validates unchanged.
When present it is an object::

    {
      "instances": [
        {"instance_id": str, "verdict": "MATCH"|"DRIFT"|"UNVERIFIABLE",
         "warnings": [str, ...]?},
        ...
      ],
      "generalization_claim": bool
    }

Gate: if ``generalization_claim`` is true, require two or more instances AND every
instance verdict == MATCH. A generalization_claim with fewer than two instances,
or with any non-MATCH instance, is rejected. Warnings are preserved, never
dropped: the validator only reads, it never mutates the packet.

Shared across the family; wired into ``model_eval`` and ``ai4science`` first.
"""

from __future__ import annotations

from typing import Any

from ._validate import Issue, reject_unknown, require_enum, require_text

INSTANCE_VERDICTS = {"MATCH", "DRIFT", "UNVERIFIABLE"}

REPLICATION_FIELDS = {"instances", "generalization_claim"}
INSTANCE_FIELDS = {"instance_id", "verdict", "warnings"}


def validate_replication(
    value: Any, issues: list[Issue], path: str = "$.replication"
) -> None:
    """Validate an optional replication object. Absent or None is valid."""
    if value is None:
        return
    if not isinstance(value, dict):
        issues.append(Issue(path, "expected object"))
        return
    reject_unknown(value, path, REPLICATION_FIELDS, issues)
    verdicts = _validate_instances(value.get("instances"), f"{path}.instances", issues)
    _validate_generalization_claim(value, verdicts, path, issues)


def _validate_instances(value: Any, path: str, issues: list[Issue]) -> list[str]:
    if not isinstance(value, list) or not value:
        issues.append(Issue(path, "expected a non-empty array of instances"))
        return []
    verdicts: list[str] = []
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(item, dict):
            issues.append(Issue(item_path, "expected object"))
            continue
        reject_unknown(item, item_path, INSTANCE_FIELDS, issues)
        require_text(item, "instance_id", issues, f"{item_path}.instance_id")
        require_enum(item, "verdict", INSTANCE_VERDICTS, issues, f"{item_path}.verdict")
        _validate_warnings(item.get("warnings"), f"{item_path}.warnings", issues)
        verdict = item.get("verdict")
        if isinstance(verdict, str):
            verdicts.append(verdict)
    return verdicts


def _validate_warnings(value: Any, path: str, issues: list[Issue]) -> None:
    if value is None:
        return
    if not isinstance(value, list):
        issues.append(Issue(path, "expected an array of warning strings or null"))
        return
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            issues.append(Issue(f"{path}[{index}]", "expected non-empty string"))


def _validate_generalization_claim(
    value: dict[str, Any], verdicts: list[str], path: str, issues: list[Issue]
) -> None:
    claim = value.get("generalization_claim")
    if not isinstance(claim, bool):
        issues.append(Issue(f"{path}.generalization_claim", "expected boolean"))
        return
    if not claim:
        return
    if len(verdicts) < 2:
        issues.append(
            Issue(
                f"{path}.generalization_claim",
                "a generalization claim requires two or more replayed instances "
                f"(got {len(verdicts)})",
            )
        )
    non_match = [v for v in verdicts if v != "MATCH"]
    if non_match:
        issues.append(
            Issue(
                f"{path}.generalization_claim",
                "a generalization claim requires every instance verdict to be MATCH "
                f"(got non-MATCH: {sorted(set(non_match))})",
            )
        )
