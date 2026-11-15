"""Organ receipt bundle: a compact interchange spine across sibling organs.

The bundle ties RAW health receipts, EMET witness receipts, Sensorium provenance
receipts, coherence observations, and proof-surface gate decisions together by
digest and reference, and carries the flagship receipt kinds (crucible
assessments, forum routes, index context envelopes, gather corpora, learn
receipts, and TADR classification/control receipts) over the same spine.
RECEIPT_KINDS stays a closed set: an entry
claiming any kind outside it is rejected. It intentionally does not embed heavy
payloads or grant authority; it is a reviewer/tool handoff contract.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ._validate import Issue, reject_unknown, require_const, require_enum, require_text
from .work_record import FORBIDDEN_FIELDS

ORGAN_BUNDLE_VERSION = "0.1"

RECEIPT_KINDS = {
    "coherence-observation",
    "crucible-assessment",
    "emet-witness",
    "forum-route",
    "gather-corpus",
    "index-context-envelope",
    "learn-lesson",
    "learn-receipt",
    "proof-surface-gate",
    "provenance-receipt",
    "raw-health",
    "tadr-classification",
    "tadr-control",
}
ENTRY_STATUSES = {
    "allow",
    "deny",
    "fail",
    "needs-human",
    "not-applicable",
    "pass",
    "unknown",
    "unverified",
    "warn",
}
EDGE_RELATIONS = {
    "corroborates",
    "derived-from",
    "gates",
    "observed-after",
}

ROOT_FIELDS = {
    "organ_bundle_version",
    "bundle_id",
    "generated_at",
    "subject",
    "entries",
    "edges",
    "notes",
}
ENTRY_FIELDS = {
    "entry_id",
    "organ_id",
    "receipt_kind",
    "status",
    "payload_sha256",
    "summary",
    "payload_ref",
}
EDGE_FIELDS = {"from", "to", "relation"}

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ZERO_SHA256 = "0" * 64


def load_organ_receipt_bundle(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def validate_organ_receipt_bundle(data: Any) -> list[Issue]:
    if not isinstance(data, dict):
        return [Issue("$", "expected object")]

    issues: list[Issue] = []
    _reject_forbidden(data, "$", issues)
    reject_unknown(data, "$", ROOT_FIELDS, issues)
    require_const(data, "organ_bundle_version", ORGAN_BUNDLE_VERSION, issues)
    require_text(data, "bundle_id", issues)
    require_text(data, "generated_at", issues)
    require_text(data, "subject", issues)
    entry_ids = _validate_entries(data.get("entries"), issues)
    _validate_edges(data.get("edges"), entry_ids, issues)
    if "notes" in data and not isinstance(data["notes"], str):
        issues.append(Issue("$.notes", "expected string"))
    return issues


def validate_organ_receipt_bundle_file(path: Path) -> list[Issue]:
    try:
        return validate_organ_receipt_bundle(load_organ_receipt_bundle(path))
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        return [Issue("$", str(exc))]


def _reject_forbidden(node: Any, path: str, issues: list[Issue]) -> None:
    if isinstance(node, dict):
        for key in sorted(node):
            child = f"{path}.{key}"
            if key in FORBIDDEN_FIELDS:
                issues.append(Issue(child, "forbidden authorization-suppression field"))
            _reject_forbidden(node[key], child, issues)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _reject_forbidden(item, f"{path}[{index}]", issues)


def _validate_entries(value: Any, issues: list[Issue]) -> set[str]:
    entry_ids: set[str] = set()
    if not isinstance(value, list):
        issues.append(Issue("$.entries", "expected array"))
        return entry_ids
    if not value:
        issues.append(Issue("$.entries", "expected at least 1 item(s)"))
        return entry_ids

    for index, item in enumerate(value):
        path = f"$.entries[{index}]"
        if not isinstance(item, dict):
            issues.append(Issue(path, "expected object"))
            continue
        reject_unknown(item, path, ENTRY_FIELDS, issues)
        require_text(item, "entry_id", issues, f"{path}.entry_id")
        require_text(item, "organ_id", issues, f"{path}.organ_id")
        require_enum(
            item, "receipt_kind", RECEIPT_KINDS, issues, f"{path}.receipt_kind"
        )
        require_enum(item, "status", ENTRY_STATUSES, issues, f"{path}.status")
        require_text(item, "summary", issues, f"{path}.summary")
        if "payload_ref" in item:
            require_text(item, "payload_ref", issues, f"{path}.payload_ref")
        digest = item.get("payload_sha256")
        if (
            not isinstance(digest, str)
            or not _SHA256_RE.fullmatch(digest)
            or digest == _ZERO_SHA256
        ):
            issues.append(
                Issue(
                    f"{path}.payload_sha256",
                    "expected nonzero 64-char lowercase hex sha256",
                )
            )
        entry_id = item.get("entry_id")
        if isinstance(entry_id, str) and entry_id.strip():
            if entry_id in entry_ids:
                issues.append(Issue(f"{path}.entry_id", "duplicate entry_id"))
            entry_ids.add(entry_id)
    return entry_ids


def _validate_edges(value: Any, entry_ids: set[str], issues: list[Issue]) -> None:
    if value is None:
        return
    if not isinstance(value, list):
        issues.append(Issue("$.edges", "expected array"))
        return
    for index, item in enumerate(value):
        path = f"$.edges[{index}]"
        if not isinstance(item, dict):
            issues.append(Issue(path, "expected object"))
            continue
        reject_unknown(item, path, EDGE_FIELDS, issues)
        require_text(item, "from", issues, f"{path}.from")
        require_text(item, "to", issues, f"{path}.to")
        require_enum(item, "relation", EDGE_RELATIONS, issues, f"{path}.relation")
        if item.get("from") not in entry_ids:
            issues.append(Issue(f"{path}.from", "expected existing entry_id"))
        if item.get("to") not in entry_ids:
            issues.append(Issue(f"{path}.to", "expected existing entry_id"))
