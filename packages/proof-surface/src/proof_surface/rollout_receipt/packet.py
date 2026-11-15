"""Rollout-receipt proof packet -- contract v0 (RL / post-training runs).

Harvest of research/rl-scaling-receipt-spine.md. A post-training run packet that
keeps reward score, verifier verdict, admission policy, and promotion decision as
SEPARATE records. Default-deny: a model is promoted only if the verifier said
MATCH and admission said allow. Stdlib-only; reuses the family neutrality guards.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .._compute_lease import validate_compute_lease
from .._decision import validate_decision_summary
from .._failure import validate_failure_labels
from .._validate import Issue, reject_unknown, require_const, require_enum, require_text
from ..authorization_receipt import _reject_forbidden
from ..witness_receipt import _reject_authority_language

PACKET_VERSION = "rollout-receipt-proof-packet/v0"

OVERALL_VERDICTS = {"MATCH", "DRIFT", "UNVERIFIABLE"}
ADMISSION_DECISIONS = {"allow", "block", "escalate", "require_review"}
PROMOTION_DECISIONS = {"promote", "hold", "reject"}

ROOT_FIELDS = {
    "version",
    "packet_id",
    "claim",
    "scope",
    "sources",
    "rollout",
    "reward",
    "verifier",
    "admission",
    "promotion",
    "compute_lease",
    "failure_labels",
    "verdicts",
    "uncertainty",
    "decision_summary",
}
SOURCE_FIELDS = {"ref", "sha256"}
ROLLOUT_FIELDS = {
    "rollout_id",
    "policy_ref",
    "checkpoint_ref",
    "verifier_ref",
    "reward_digest",
    "sandbox_receipt",
    "dataset_mutation_ref",
}
REWARD_FIELDS = {"score", "model_ref"}
VERIFIER_FIELDS = {"verdict", "evidence"}
ADMISSION_FIELDS = {"decision", "reasons"}
PROMOTION_FIELDS = {"decision", "reason"}
VERDICTS_FIELDS = {"overall"}

_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def load_packet(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def validate_rollout_receipt_packet(data: dict[str, Any]) -> list[Issue]:
    """Validate a rollout-receipt proof packet. Returns [] iff valid."""
    issues: list[Issue] = []
    _reject_forbidden(data, "$", issues)
    _reject_authority_language(data, "$", issues)
    reject_unknown(data, "$", ROOT_FIELDS, issues)
    require_const(data, "version", PACKET_VERSION, issues)
    require_text(data, "packet_id", issues)
    require_text(data, "claim", issues)
    require_text(data, "scope", issues)
    _validate_sources(data.get("sources"), issues)
    _validate_rollout(data.get("rollout"), issues)
    _validate_reward(data.get("reward"), issues)
    _validate_verifier(data.get("verifier"), issues)
    _validate_admission(data.get("admission"), issues)
    _validate_promotion(data.get("promotion"), issues)
    validate_compute_lease(
        data.get("compute_lease"), "external", "$.compute_lease", issues
    )
    _validate_verdicts(data.get("verdicts"), issues)
    _validate_str_list(data.get("uncertainty"), "$.uncertainty", issues)
    _validate_default_deny(data, issues)
    _validate_verdict_consistency(data, issues)
    validate_failure_labels(data.get("failure_labels"), issues)
    validate_decision_summary(
        data.get("decision_summary"), issues, "$.decision_summary"
    )
    return issues


def validate_rollout_receipt_packet_file(path: Path) -> list[Issue]:
    try:
        return validate_rollout_receipt_packet(load_packet(path))
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        return [Issue("$", str(exc))]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _require_hex64(value: Any, path: str, issues: list[Issue]) -> None:
    if not isinstance(value, str) or not _HEX64.fullmatch(value):
        issues.append(Issue(path, "expected 64-char lowercase hex digest"))


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
        _require_hex64(item.get("sha256"), f"{path}.sha256", issues)


def _validate_rollout(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.rollout", "expected object"))
        return
    reject_unknown(value, "$.rollout", ROLLOUT_FIELDS, issues)
    for field in ("rollout_id", "policy_ref", "checkpoint_ref", "verifier_ref"):
        require_text(value, field, issues, f"$.rollout.{field}")
    _require_hex64(value.get("reward_digest"), "$.rollout.reward_digest", issues)
    for field in ("sandbox_receipt", "dataset_mutation_ref"):
        _require_opt_text(value.get(field), f"$.rollout.{field}", issues)


def _validate_reward(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.reward", "expected object"))
        return
    reject_unknown(value, "$.reward", REWARD_FIELDS, issues)
    score = value.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        issues.append(Issue("$.reward.score", "expected number"))
    _require_opt_text(value.get("model_ref"), "$.reward.model_ref", issues)


def _validate_verifier(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.verifier", "expected object"))
        return
    reject_unknown(value, "$.verifier", VERIFIER_FIELDS, issues)
    require_enum(value, "verdict", OVERALL_VERDICTS, issues, "$.verifier.verdict")
    _validate_str_list(value.get("evidence"), "$.verifier.evidence", issues)


def _validate_admission(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.admission", "expected object"))
        return
    reject_unknown(value, "$.admission", ADMISSION_FIELDS, issues)
    require_enum(value, "decision", ADMISSION_DECISIONS, issues, "$.admission.decision")
    _validate_str_list(value.get("reasons"), "$.admission.reasons", issues)


def _validate_promotion(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.promotion", "expected object"))
        return
    reject_unknown(value, "$.promotion", PROMOTION_FIELDS, issues)
    require_enum(value, "decision", PROMOTION_DECISIONS, issues, "$.promotion.decision")
    require_text(value, "reason", issues, "$.promotion.reason")


def _validate_verdicts(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.verdicts", "expected object"))
        return
    reject_unknown(value, "$.verdicts", VERDICTS_FIELDS, issues)
    require_enum(value, "overall", OVERALL_VERDICTS, issues, "$.verdicts.overall")


def _validate_default_deny(data: dict[str, Any], issues: list[Issue]) -> None:
    """A promote is admissible only with a MATCH verifier and an allow admission."""
    promotion = data.get("promotion")
    verifier = data.get("verifier")
    admission = data.get("admission")
    if not isinstance(promotion, dict) or promotion.get("decision") != "promote":
        return
    verdict = verifier.get("verdict") if isinstance(verifier, dict) else None
    decision = admission.get("decision") if isinstance(admission, dict) else None
    if verdict != "MATCH" or decision != "allow":
        issues.append(
            Issue(
                "$.promotion",
                "a promote decision requires a MATCH verifier verdict and an allow "
                "admission decision",
            )
        )


def _validate_verdict_consistency(data: dict[str, Any], issues: list[Issue]) -> None:
    """The overall verdict is the verifier's verdict -- the two may not disagree."""
    verdicts = data.get("verdicts")
    verifier = data.get("verifier")
    overall = verdicts.get("overall") if isinstance(verdicts, dict) else None
    verdict = verifier.get("verdict") if isinstance(verifier, dict) else None
    if (
        overall in OVERALL_VERDICTS
        and verdict in OVERALL_VERDICTS
        and overall != verdict
    ):
        issues.append(
            Issue(
                "$.verdicts.overall",
                f"overall {overall!r} must mirror the verifier verdict {verdict!r}",
            )
        )
