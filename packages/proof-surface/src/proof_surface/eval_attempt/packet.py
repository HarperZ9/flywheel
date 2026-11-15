"""Eval-attempt proof packet -- contract v0 (single benchmark attempt).

Harvest of dogfood pass 0085/0096. One benchmark attempt bound to its authority
(who defines correctness), the prompt/model/tool-use it ran with, a replay ref,
an honest boundary block, and a re-derivable verdict. The load-bearing honesty
gate: a `correct` outcome with ground-truth access is contamination, not a pass.

Stdlib-only. Reuses the proof-surface family's neutrality guards verbatim.
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
from ._integrity import validate_auditability, validate_integrity

PACKET_VERSION = "eval-attempt-proof-packet/v0"

OVERALL_VERDICTS = {"MATCH", "DRIFT", "UNVERIFIABLE"}
OUTCOMES = {"correct", "incorrect", "abstained", "error"}

ROOT_FIELDS = {
    "version",
    "packet_id",
    "claim",
    "scope",
    "sources",
    "benchmark",
    "attempt",
    "result",
    "boundaries",
    "failure_labels",
    "verdicts",
    "uncertainty",
    "decision_summary",
}
SOURCE_FIELDS = {"ref", "sha256"}
BENCHMARK_FIELDS = {"benchmark_ref", "task_id", "authority_receipt", "split"}
ATTEMPT_FIELDS = {
    "attempt_id",
    "prompt_ref",
    "model_ref",
    "tool_use",
    "replay_ref",
    "seed",
    "external_model_calls",
    "provider_receipt_ref",
}
TOOL_USE_FIELDS = {"tool", "ref"}
RESULT_FIELDS = {"outcome", "score", "expected_ref"}
REQUIRED_BOUNDARY_FLAGS = ("had_ground_truth", "had_internet", "had_tools")
BOUNDARIES_FIELDS = {*REQUIRED_BOUNDARY_FLAGS, "reasoning_trace_available"}
VERDICTS_FIELDS = {"overall"}

_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def load_packet(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def validate_eval_attempt_packet(data: dict[str, Any]) -> list[Issue]:
    """Validate an eval-attempt proof packet. Returns [] iff valid."""
    issues: list[Issue] = []
    _reject_forbidden(data, "$", issues)
    _reject_authority_language(data, "$", issues)
    reject_unknown(data, "$", ROOT_FIELDS, issues)
    require_const(data, "version", PACKET_VERSION, issues)
    require_text(data, "packet_id", issues)
    require_text(data, "claim", issues)
    require_text(data, "scope", issues)
    _validate_sources(data.get("sources"), issues)
    _validate_benchmark(data.get("benchmark"), issues)
    _validate_attempt(data.get("attempt"), issues)
    _validate_result(data.get("result"), issues)
    _validate_boundaries(data.get("boundaries"), issues)
    validate_integrity(data.get("result"), data.get("boundaries"), issues)
    validate_auditability(
        data.get("result"),
        data.get("boundaries"),
        data.get("attempt"),
        data.get("verdicts"),
        issues,
    )
    _validate_verdicts(data.get("verdicts"), issues)
    _validate_str_list(data.get("uncertainty"), "$.uncertainty", issues)
    validate_failure_labels(data.get("failure_labels"), issues)
    validate_decision_summary(
        data.get("decision_summary"), issues, "$.decision_summary"
    )
    return issues


def validate_eval_attempt_packet_file(path: Path) -> list[Issue]:
    try:
        return validate_eval_attempt_packet(load_packet(path))
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


def _validate_benchmark(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.benchmark", "expected object"))
        return
    reject_unknown(value, "$.benchmark", BENCHMARK_FIELDS, issues)
    for field in ("benchmark_ref", "task_id", "authority_receipt"):
        require_text(value, field, issues, f"$.benchmark.{field}")
    _require_opt_text(value.get("split"), "$.benchmark.split", issues)


def _validate_attempt(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.attempt", "expected object"))
        return
    reject_unknown(value, "$.attempt", ATTEMPT_FIELDS, issues)
    for field in ("attempt_id", "prompt_ref", "model_ref"):
        require_text(value, field, issues, f"$.attempt.{field}")
    _require_opt_text(value.get("replay_ref"), "$.attempt.replay_ref", issues)
    seed = value.get("seed")
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
        issues.append(Issue("$.attempt.seed", "expected integer or null"))
    _validate_tool_use(value.get("tool_use"), issues)
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
                    "a provider receipt requires a disclosed external model "
                    "call count",
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


def _validate_tool_use(value: Any, issues: list[Issue]) -> None:
    if value is None:
        return
    for index, item in enumerate(_as_list(value, "$.attempt.tool_use", issues)):
        path = f"$.attempt.tool_use[{index}]"
        if not isinstance(item, dict):
            issues.append(Issue(path, "expected object"))
            continue
        reject_unknown(item, path, TOOL_USE_FIELDS, issues)
        require_text(item, "tool", issues, f"{path}.tool")
        _require_opt_text(item.get("ref"), f"{path}.ref", issues)


def _validate_result(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.result", "expected object"))
        return
    reject_unknown(value, "$.result", RESULT_FIELDS, issues)
    require_enum(value, "outcome", OUTCOMES, issues, "$.result.outcome")
    score = value.get("score")
    if score is not None and (
        isinstance(score, bool) or not isinstance(score, (int, float))
    ):
        issues.append(Issue("$.result.score", "expected number or null"))
    _require_opt_text(value.get("expected_ref"), "$.result.expected_ref", issues)


def _validate_boundaries(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.boundaries", "expected object"))
        return
    reject_unknown(value, "$.boundaries", BOUNDARIES_FIELDS, issues)
    for field in REQUIRED_BOUNDARY_FLAGS:
        if not isinstance(value.get(field), bool):
            issues.append(Issue(f"$.boundaries.{field}", "expected boolean"))
    trace = value.get("reasoning_trace_available")
    if trace is not None and not isinstance(trace, bool):
        issues.append(
            Issue("$.boundaries.reasoning_trace_available", "expected boolean or null")
        )


def _validate_verdicts(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.verdicts", "expected object"))
        return
    reject_unknown(value, "$.verdicts", VERDICTS_FIELDS, issues)
    require_enum(value, "overall", OVERALL_VERDICTS, issues, "$.verdicts.overall")
