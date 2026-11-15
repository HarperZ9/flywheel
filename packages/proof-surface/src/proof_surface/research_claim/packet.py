"""Research-claim proof packet -- contract v0 (pipeline-math++).

Joins source refs, a formal statement, prover/checker attempts, verification
checks, a re-derivable verdict, and a promotion-ladder rung. Its defining honest
property: a failed or unverifiable attempt still produces a *valid* packet that
preserves sources, attempts, and next checks -- a negative result is evidence,
not a discarded run.

The promotion ladder deliberately excludes PROMOTED_LAW: a single packet can
reach CRUCIBLE_MATCH or LAW_CANDIDATE, never a promoted law (that needs
independent reproduction and review). Stdlib-only.
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
from ._evidence_gates import validate_evidence_gates
from ._refutation import validate_refutation_gate

PACKET_VERSION = "research-claim-proof-packet/v0"

OVERALL_VERDICTS = {"MATCH", "DRIFT", "UNVERIFIABLE"}
ATTEMPT_RESULTS = {"proved", "refuted", "incomplete", "bounded", "failed"}
CHECK_STATUSES = {"pass", "fail", "unverifiable"}
# Promotion ladder reachable by a single packet (PROMOTED_LAW is reserved).
PROMOTIONS = {
    "SOURCE_LEAD",
    "HYPOTHESIS",
    "IDENTITY",
    "PROBE_MATCH",
    "CRUCIBLE_MATCH",
    "UNVERIFIABLE",
    "LAW_CANDIDATE",
    "REFUTED",
}

ROOT_FIELDS = {
    "version",
    "packet_id",
    "claim",
    "scope",
    "statement",
    "sources",
    "attempts",
    "checks",
    "verdicts",
    "promotion",
    "uncertainty",
    "decision_summary",
    "formal",
    "failure_labels",
    "declared_branches",
    "witness_tier",
    "evidence_classes",
}
SOURCE_FIELDS = {"ref", "sha256", "url", "availability"}
# Honest retrievability (research/mycology-network-intelligence.md provenance
# boundary): record what could lawfully be obtained, never pretend a paywalled
# or unretrievable source was read.
SOURCE_AVAILABILITY = {
    "open",
    "abstract-only",
    "publisher-blocked",
    "author-copy",
    "unverifiable-from-local-corpus",
}
ATTEMPT_FIELDS = {"attempt_id", "method", "result", "artifact_ref", "notes"}
CHECK_FIELDS = {"checker", "status", "evidence", "notes"}
VERDICTS_FIELDS = {"overall", "per_check"}
PER_CHECK_FIELDS = {"checker", "status"}
REPLAY_STATUSES = {"NOT_RUN", "BLOCKED", "PASSED", "FAILED"}
FORMAL_FIELDS = {
    "kernel_checked",
    "compiled_replay_status",
    "axioms",
    "toolchain",
    "source_sha256",
    "unresolved_sorry",
    "counterexample_found",
}

_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def load_packet(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def validate_research_claim_packet(data: dict[str, Any]) -> list[Issue]:
    """Validate a research-claim proof packet. Returns [] iff valid."""
    issues: list[Issue] = []
    _reject_forbidden(data, "$", issues)
    _reject_authority_language(data, "$", issues)
    reject_unknown(data, "$", ROOT_FIELDS, issues)
    require_const(data, "version", PACKET_VERSION, issues)
    require_text(data, "packet_id", issues)
    require_text(data, "claim", issues)
    require_text(data, "scope", issues)
    require_text(data, "statement", issues)
    _validate_sources(data.get("sources"), issues)
    _validate_attempts(data.get("attempts"), issues)
    _validate_checks(data.get("checks"), issues)
    _validate_verdicts(data.get("verdicts"), issues)
    require_enum(data, "promotion", PROMOTIONS, issues)
    _validate_str_list(data.get("uncertainty"), "$.uncertainty", issues)
    _validate_formal(data.get("formal"), issues)
    validate_refutation_gate(data, issues)
    _validate_consistency(data, issues)
    validate_failure_labels(data.get("failure_labels"), issues)
    validate_decision_summary(
        data.get("decision_summary"), issues, "$.decision_summary"
    )
    validate_evidence_gates(data, issues)
    return issues


def validate_research_claim_packet_file(path: Path) -> list[Issue]:
    try:
        return validate_research_claim_packet(load_packet(path))
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        return [Issue("$", str(exc))]


# --- helpers --------------------------------------------------------------- #


def _require_opt_text(value: Any, path: str, issues: list[Issue]) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        issues.append(Issue(path, "expected non-empty string or null"))


def _as_list(value: Any, path: str, issues: list[Issue]) -> list[Any]:
    if not isinstance(value, list):
        issues.append(Issue(path, "expected array"))
        return []
    return value


def _validate_sources(value: Any, issues: list[Issue]) -> None:
    for index, item in enumerate(_as_list(value, "$.sources", issues)):
        path = f"$.sources[{index}]"
        if not isinstance(item, dict):
            issues.append(Issue(path, "expected object"))
            continue
        reject_unknown(item, path, SOURCE_FIELDS, issues)
        require_text(item, "ref", issues, f"{path}.ref")
        sha = item.get("sha256")
        if sha is not None and (not isinstance(sha, str) or not _HEX64.fullmatch(sha)):
            issues.append(
                Issue(f"{path}.sha256", "expected 64-char lowercase hex digest or null")
            )
        _require_opt_text(item.get("url"), f"{path}.url", issues)
        availability = item.get("availability")
        if availability is not None and availability not in SOURCE_AVAILABILITY:
            issues.append(
                Issue(
                    f"{path}.availability",
                    f"expected one of {sorted(SOURCE_AVAILABILITY)} or null",
                )
            )


def _validate_attempts(value: Any, issues: list[Issue]) -> None:
    for index, item in enumerate(_as_list(value, "$.attempts", issues)):
        path = f"$.attempts[{index}]"
        if not isinstance(item, dict):
            issues.append(Issue(path, "expected object"))
            continue
        reject_unknown(item, path, ATTEMPT_FIELDS, issues)
        require_text(item, "attempt_id", issues, f"{path}.attempt_id")
        require_text(item, "method", issues, f"{path}.method")
        require_enum(item, "result", ATTEMPT_RESULTS, issues, f"{path}.result")
        _require_opt_text(item.get("artifact_ref"), f"{path}.artifact_ref", issues)
        _require_opt_text(item.get("notes"), f"{path}.notes", issues)


def _validate_checks(value: Any, issues: list[Issue]) -> None:
    for index, item in enumerate(_as_list(value, "$.checks", issues)):
        path = f"$.checks[{index}]"
        if not isinstance(item, dict):
            issues.append(Issue(path, "expected object"))
            continue
        reject_unknown(item, path, CHECK_FIELDS, issues)
        require_text(item, "checker", issues, f"{path}.checker")
        require_enum(item, "status", CHECK_STATUSES, issues, f"{path}.status")
        _validate_str_list(item.get("evidence"), f"{path}.evidence", issues)
        _require_opt_text(item.get("notes"), f"{path}.notes", issues)


def _validate_verdicts(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.verdicts", "expected object"))
        return
    reject_unknown(value, "$.verdicts", VERDICTS_FIELDS, issues)
    require_enum(value, "overall", OVERALL_VERDICTS, issues, "$.verdicts.overall")
    for index, item in enumerate(
        _as_list(value.get("per_check"), "$.verdicts.per_check", issues)
    ):
        path = f"$.verdicts.per_check[{index}]"
        if not isinstance(item, dict):
            issues.append(Issue(path, "expected object"))
            continue
        reject_unknown(item, path, PER_CHECK_FIELDS, issues)
        require_text(item, "checker", issues, f"{path}.checker")
        require_enum(item, "status", OVERALL_VERDICTS, issues, f"{path}.status")


def _validate_formal(value: Any, issues: list[Issue]) -> None:
    """A PASSED kernel replay must disclose its axioms, toolchain, and source binding."""
    if value is None:
        return
    if not isinstance(value, dict):
        issues.append(Issue("$.formal", "expected object"))
        return
    reject_unknown(value, "$.formal", FORMAL_FIELDS, issues)
    if not isinstance(value.get("kernel_checked"), bool):
        issues.append(Issue("$.formal.kernel_checked", "expected boolean"))
    require_enum(
        value,
        "compiled_replay_status",
        REPLAY_STATUSES,
        issues,
        "$.formal.compiled_replay_status",
    )
    axioms = value.get("axioms", [])
    if not isinstance(axioms, list) or any(
        not isinstance(a, str) or not a.strip() for a in axioms
    ):
        issues.append(Issue("$.formal.axioms", "expected array of non-empty strings"))
    sha = value.get("source_sha256")
    if sha is not None and (not isinstance(sha, str) or not _HEX64.fullmatch(sha)):
        issues.append(
            Issue(
                "$.formal.source_sha256",
                "expected 64-char lowercase hex digest or null",
            )
        )
    if value.get("compiled_replay_status") == "PASSED" and not (
        value.get("kernel_checked") and axioms and value.get("toolchain") and sha
    ):
        issues.append(
            Issue(
                "$.formal",
                "a PASSED kernel replay must disclose kernel_checked, a non-empty axiom "
                "set, toolchain, and source_sha256",
            )
        )


def _validate_str_list(value: Any, path: str, issues: list[Issue]) -> None:
    for index, item in enumerate(_as_list(value, path, issues)):
        if not isinstance(item, str) or not item.strip():
            issues.append(Issue(f"{path}[{index}]", "expected non-empty string"))


def _dict_field(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _checker_names(value: Any) -> list[str]:
    items = value if isinstance(value, list) else []
    return [n for c in items if isinstance(n := _dict_field(c).get("checker"), str)]


def _validate_consistency(data: dict[str, Any], issues: list[Issue]) -> None:
    checker_names = _checker_names(data.get("checks"))
    per_check = _dict_field(data.get("verdicts")).get("per_check")
    verdict_names = [v.get("checker") for v in per_check or [] if isinstance(v, dict)]
    for name in sorted(set(checker_names)):
        count = verdict_names.count(name)
        if count == 0:
            issues.append(
                Issue("$.verdicts.per_check", f"no verdict for check {name!r}")
            )
        elif count > 1:
            issues.append(
                Issue("$.verdicts.per_check", f"multiple verdicts for check {name!r}")
            )
    if isinstance(per_check, list):
        for index, v in enumerate(per_check):
            if isinstance(v, dict) and v.get("checker") not in set(checker_names):
                issues.append(
                    Issue(
                        f"$.verdicts.per_check[{index}].checker",
                        f"references unknown check {v.get('checker')!r}",
                    )
                )
