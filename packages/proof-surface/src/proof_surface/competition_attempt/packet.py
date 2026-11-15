"""Competition-attempt proof packet -- contract v0 (competition/judge attempt).

Harvest of the SAIR competition dogfood cluster: 0136 (the competition-attempt
pattern), 0137 (hermetic fixture; prompt instructions must never be parsed as
answers), 0138 (source-pinned judge-repo adapter), 0139 (fenced Stage-2 rung).
A single competition attempt binds the challenge to a source-pinned judge
repository observation, discloses its hosted-model usage with the eval-attempt
hermeticity rule verbatim, records how the answer was extracted, and carries a
closed certificate ladder whose verdict may only cite layers that actually
EXECUTED. Stdlib-only; reuses the family's neutrality guards verbatim.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .._decision import validate_decision_summary
from .._failure import validate_failure_labels
from .._validate import Issue, reject_unknown, require_const, require_enum, require_text
from ..authorization_receipt import _reject_forbidden
from ..witness_receipt import _reject_authority_language
from ._gates import (
    validate_answer_extraction,
    validate_certificate_layers,
    validate_verdict_citation,
)

PACKET_VERSION = "competition-attempt-proof-packet/v0"

OVERALL_VERDICTS = {"MATCH", "DRIFT", "UNVERIFIABLE"}

ROOT_FIELDS = {
    "version",
    "packet_id",
    "claim",
    "scope",
    "sources",
    "challenge",
    "attempt",
    "answer_extraction",
    "certificate_layers",
    "failure_labels",
    "verdicts",
    "uncertainty",
    "decision_summary",
}
SOURCE_FIELDS = {"ref", "sha256"}
CHALLENGE_FIELDS = {"challenge_ref", "stage", "judge_repo"}
JUDGE_REPO_FIELDS = {"repo_ref", "head_sha", "observed_files", "files_digest"}
ATTEMPT_FIELDS = {
    "attempt_id",
    "model_ref",
    "external_model_calls",
    "provider_receipt_ref",
}
VERDICTS_FIELDS = {"overall", "cited_layers"}

_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_HEX40 = re.compile(r"[0-9a-f]{40}\Z")


def load_packet(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def validate_competition_attempt_packet(data: dict[str, Any]) -> list[Issue]:
    """Validate a competition-attempt proof packet. Returns [] iff valid."""
    issues: list[Issue] = []
    _reject_forbidden(data, "$", issues)
    _reject_authority_language(data, "$", issues)
    reject_unknown(data, "$", ROOT_FIELDS, issues)
    require_const(data, "version", PACKET_VERSION, issues)
    require_text(data, "packet_id", issues)
    require_text(data, "claim", issues)
    require_text(data, "scope", issues)
    _validate_sources(data.get("sources"), issues)
    _validate_challenge(data.get("challenge"), issues)
    _validate_attempt(data.get("attempt"), issues)
    validate_answer_extraction(data.get("answer_extraction"), issues)
    validate_certificate_layers(data.get("certificate_layers"), issues)
    _validate_verdicts(data.get("verdicts"), issues)
    validate_verdict_citation(
        data.get("certificate_layers"), data.get("verdicts"), issues
    )
    _validate_str_list(data.get("uncertainty"), "$.uncertainty", issues)
    validate_failure_labels(data.get("failure_labels"), issues)
    validate_decision_summary(
        data.get("decision_summary"), issues, "$.decision_summary"
    )
    return issues


def validate_competition_attempt_packet_file(path: Path) -> list[Issue]:
    try:
        return validate_competition_attempt_packet(load_packet(path))
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        return [Issue("$", str(exc))]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _require_opt_text(value: Any, path: str, issues: list[Issue]) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        issues.append(Issue(path, "expected non-empty string or null"))


def _as_list(value: Any, path: str, issues: list[Issue]) -> list[Any]:
    if not isinstance(value, list):
        issues.append(Issue(path, "expected array"))
        return []
    return value


def _validate_str_list(value: Any, path: str, issues: list[Issue]) -> None:
    for index, item in enumerate(_as_list(value, path, issues)):
        if not isinstance(item, str) or not item.strip():
            issues.append(Issue(f"{path}[{index}]", "expected non-empty string"))


def _validate_sources(value: Any, issues: list[Issue]) -> None:
    for index, item in enumerate(_as_list(value, "$.sources", issues)):
        path = f"$.sources[{index}]"
        if not isinstance(item, dict):
            issues.append(Issue(path, "expected object"))
            continue
        reject_unknown(item, path, SOURCE_FIELDS, issues)
        require_text(item, "ref", issues, f"{path}.ref")
        sha = item.get("sha256")
        if not isinstance(sha, str) or not _HEX64.fullmatch(sha):
            issues.append(
                Issue(f"{path}.sha256", "expected 64-char lowercase hex digest")
            )


def _validate_challenge(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.challenge", "expected object"))
        return
    reject_unknown(value, "$.challenge", CHALLENGE_FIELDS, issues)
    require_text(value, "challenge_ref", issues, "$.challenge.challenge_ref")
    require_text(value, "stage", issues, "$.challenge.stage")
    _validate_judge_repo(value.get("judge_repo"), issues)


def _validate_judge_repo(value: Any, issues: list[Issue]) -> None:
    """0138: the judge repository is observed source-pinned, never assumed."""
    path = "$.challenge.judge_repo"
    if not isinstance(value, dict):
        issues.append(
            Issue(path, "expected object (the source-pinned judge observation)")
        )
        return
    reject_unknown(value, path, JUDGE_REPO_FIELDS, issues)
    require_text(value, "repo_ref", issues, f"{path}.repo_ref")
    head = value.get("head_sha")
    if not isinstance(head, str) or not _HEX40.fullmatch(head):
        issues.append(
            Issue(f"{path}.head_sha", "expected 40-char lowercase hex commit sha")
        )
    observed = value.get("observed_files")
    if not isinstance(observed, int) or isinstance(observed, bool) or observed <= 0:
        issues.append(Issue(f"{path}.observed_files", "expected an integer > 0"))
    digest = value.get("files_digest")
    if not isinstance(digest, str) or not _HEX64.fullmatch(digest):
        issues.append(
            Issue(f"{path}.files_digest", "expected 64-char lowercase hex digest")
        )


def _validate_attempt(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.attempt", "expected object"))
        return
    reject_unknown(value, "$.attempt", ATTEMPT_FIELDS, issues)
    require_text(value, "attempt_id", issues, "$.attempt.attempt_id")
    require_text(value, "model_ref", issues, "$.attempt.model_ref")
    _validate_hermeticity(value, issues)


def _validate_hermeticity(value: dict[str, Any], issues: list[Issue]) -> None:
    """Hosted-model disclosure (dogfood 0137/0138): when an attempt speaks
    about its external model calls, the claim must be evidence-consistent.
    A hermetic claim (0 calls) citing a provider receipt is a contradiction;
    a nonzero count without a receipt is a claim with no evidence surface;
    a receipt without a disclosed count is undisclosed external usage."""
    calls = value.get("external_model_calls")
    receipt = value.get("provider_receipt_ref")
    _require_opt_text(receipt, "$.attempt.provider_receipt_ref", issues)
    if calls is None:
        if receipt is not None:
            issues.append(
                Issue(
                    "$.attempt.external_model_calls",
                    "a provider receipt requires a disclosed external model call count",
                )
            )
        return
    if isinstance(calls, bool) or not isinstance(calls, int) or calls < 0:
        issues.append(
            Issue(
                "$.attempt.external_model_calls",
                "expected a non-negative integer",
            )
        )
        return
    if calls == 0 and receipt is not None:
        issues.append(
            Issue(
                "$.attempt.external_model_calls",
                "a hermetic attempt (0 external model calls) cannot cite a "
                "provider receipt",
            )
        )
    if calls > 0 and receipt is None:
        issues.append(
            Issue(
                "$.attempt.provider_receipt_ref",
                "an external-model claim requires a provider receipt "
                "reference (redacted evidence is admissible; absence is not)",
            )
        )


def _validate_verdicts(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.verdicts", "expected object"))
        return
    reject_unknown(value, "$.verdicts", VERDICTS_FIELDS, issues)
    require_enum(value, "overall", OVERALL_VERDICTS, issues, "$.verdicts.overall")
