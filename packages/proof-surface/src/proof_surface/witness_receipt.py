"""Witness-receipt validator -- consumer-side, mirrors EMET's published shape.

EMET (the byte-witness spine) stays self-contained and stdlib-only for
independent re-derivability, so it is NOT a dependency of this package. This
validator MIRRORS EMET's witness-receipt schema and closed verdict lattice so
that consuming tools can validate EMET receipts without importing EMET.

The verdict is constrained to EMET's closed lattice (witness facts only). A
best-effort, case-sensitive lexical denylist additionally rejects authority
tokens in free-text fields. The denylist is a guard, not a proof of neutrality.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ._validate import Issue, reject_unknown, require_enum, require_text

# EMET's closed witness verdict lattice (mirrored from emet/adapters).
WITNESS_VERDICTS = {
    "MATCH",
    "DRIFT",
    "UNVERIFIABLE",
    "COHERENT",
    "VIEW_DIFFERS_FROM_SOURCE",
    "CORROBORATED",
    "QUARANTINE_READ_PATH_DIVERGENCE",
}
# Authority tokens a witness receipt must never assert.  Strict SUPERSET of
# EMET's FORBIDDEN set (verdict.py): EMET's {TRUSTED, APPROVED, SAFE, ALLOWED,
# PERMITTED, AUTHORIZED, BLESSED, VERIFIED_AUTHORITY} plus CERTIFIED, COMPLIANT.
# Being a superset means anything EMET blocks, this consumer-side validator
# also blocks -- never the reverse.
FORBIDDEN_AUTHORITY_TOKENS = {
    "TRUSTED",
    "APPROVED",
    "SAFE",
    "ALLOWED",
    "PERMITTED",
    "AUTHORIZED",
    "BLESSED",
    "VERIFIED_AUTHORITY",
    "CERTIFIED",
    "COMPLIANT",
}
ROOT_FIELDS = {"receipt_id", "verdict", "witness", "subject", "evidence", "notes"}
WITNESS_FIELDS = {"implementation", "spec_version", "self_sha256", "check"}
SUBJECT_FIELDS = {"name", "digest"}
DIGEST_FIELDS = {"sha256"}
EVIDENCE_FIELDS = {"exit_code", "stdout_verdict_line"}

_SHA256_RE = re.compile(r"[0-9a-f]{64}")


def load_receipt(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def validate_witness_receipt(data: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    reject_unknown(data, "$", ROOT_FIELDS, issues)
    require_text(data, "receipt_id", issues)
    require_enum(data, "verdict", WITNESS_VERDICTS, issues)
    _validate_witness(data.get("witness"), issues)
    _validate_subject(data.get("subject"), issues)
    _validate_evidence(data.get("evidence"), issues)
    if "notes" in data and not isinstance(data["notes"], str):
        issues.append(Issue("$.notes", "expected string"))
    _reject_authority_language(data, "$", issues)
    return issues


def validate_witness_receipt_file(path: Path) -> list[Issue]:
    try:
        return validate_witness_receipt(load_receipt(path))
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        return [Issue("$", str(exc))]


def _token_present(token: str, text: str) -> bool:
    # Case-insensitive; word boundary excludes underscore so 'AUTHORIZED_role'
    # and lowercase 'trusted' are both caught.
    return (
        re.search(
            r"(?<![A-Za-z0-9])" + re.escape(token) + r"(?![A-Za-z0-9])",
            text,
            re.IGNORECASE,
        )
        is not None
    )


def _reject_authority_language(node: Any, path: str, issues: list[Issue]) -> None:
    if isinstance(node, str):
        for token in sorted(FORBIDDEN_AUTHORITY_TOKENS):
            if _token_present(token, node):
                issues.append(Issue(path, f"forbidden authority token: {token}"))
    elif isinstance(node, dict):
        for key, value in node.items():
            # Scan KEYS as well as values -- an authority word must not hide as a
            # field name. (reject_unknown blocks unknown keys upstream; this is a
            # complete, defence-in-depth guard regardless of caller.)
            if isinstance(key, str):
                _reject_authority_language(key, f"{path}.<key:{key}>", issues)
            _reject_authority_language(value, f"{path}.{key}", issues)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _reject_authority_language(value, f"{path}[{index}]", issues)


def _validate_witness(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.witness", "expected object"))
        return
    reject_unknown(value, "$.witness", WITNESS_FIELDS, issues)
    require_text(value, "implementation", issues, "$.witness.implementation")
    require_text(value, "spec_version", issues, "$.witness.spec_version")
    require_text(value, "self_sha256", issues, "$.witness.self_sha256")
    require_text(value, "check", issues, "$.witness.check")


def _validate_subject(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, list):
        issues.append(Issue("$.subject", "expected array"))
        return
    if not value:
        issues.append(Issue("$.subject", "expected at least 1 item(s)"))
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            issues.append(Issue(f"$.subject[{index}]", "expected object"))
            continue
        reject_unknown(item, f"$.subject[{index}]", SUBJECT_FIELDS, issues)
        require_text(item, "name", issues, f"$.subject[{index}].name")
        digest = item.get("digest")
        if not isinstance(digest, dict):
            issues.append(Issue(f"$.subject[{index}].digest", "expected object"))
        else:
            reject_unknown(digest, f"$.subject[{index}].digest", DIGEST_FIELDS, issues)
            sha = digest.get("sha256")
            if not isinstance(sha, str) or not _SHA256_RE.fullmatch(sha):
                issues.append(
                    Issue(
                        f"$.subject[{index}].digest.sha256",
                        "expected 64-char lowercase hex sha256",
                    )
                )


def _validate_evidence(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.evidence", "expected object"))
        return
    reject_unknown(value, "$.evidence", EVIDENCE_FIELDS, issues)
    exit_code = value.get("exit_code")
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        issues.append(Issue("$.evidence.exit_code", "expected integer"))
    if not isinstance(value.get("stdout_verdict_line"), str):
        issues.append(Issue("$.evidence.stdout_verdict_line", "expected string"))
