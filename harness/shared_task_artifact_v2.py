"""shared_task_artifact/v2: closed pre-oracle scorecard artifact checker."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable

SHARED_TASK_CHECKER_ID = "shared_task_artifact/v2"
PRE_ORACLE_STATES = {
    "execution_state": "returned",
    "oracle_state": "not_run",
    "receipt_state": "not_emitted",
}
LIMITATION_TEXT = {
    "does_not_prove_provider_superiority": "This attempt does not prove provider superiority.",
    "does_not_prove_cross_harness_comparison": "This attempt does not prove a Codex-vs-Flywheel comparison.",
    "does_not_prove_final_no_failure_completion": "This pre-oracle artifact does not prove final no-failure completion.",
}
_REQUIRED_FIELDS = {
    "task_id", "input_sha256s", "raw_prompt_sha256", "tool_policy_sha256",
    "raw_artifact_path", "receipt_path", "pre_oracle_failure_modes",
    "claim_bindings",
}
_FINAL_TOP_LEVEL = {"status", "primary_outcome", "execution_state", "oracle_state", "receipt_state"}
_SUPPORTED_TYPES = {"artifact_binding", "limitation", "pre_oracle_attempt_facts"}
_EXPECTED_CLAIMS = {
    "pre_oracle_attempt_state": ("pre_oracle_attempt_facts", "attempt", "scorecard_core.orthogonal_states"),
    "raw_artifact_binding": ("artifact_binding", "raw_artifact", "scorecard_core.raw_artifact_sha256"),
    "receipt_binding": ("artifact_binding", "receipt", "scorecard_core.receipt_sha256"),
    "provider_superiority_boundary": ("limitation", "attempt", "shared_task_artifact/v2.closed_limitations"),
    "cross_harness_comparison_boundary": ("limitation", "attempt", "shared_task_artifact/v2.closed_limitations"),
    "final_completion_boundary": ("limitation", "attempt", "shared_task_artifact/v2.closed_limitations"),
}
_ARTIFACT_BINDINGS = {
    "raw_artifact_binding": ("raw_artifact_path", "raw_artifact_sha256"),
    "receipt_binding": ("receipt_path", "receipt_sha256"),
}
_LIMITATION_CLAIMS = {
    "provider_superiority_boundary": "does_not_prove_provider_superiority",
    "cross_harness_comparison_boundary": "does_not_prove_cross_harness_comparison",
    "final_completion_boundary": "does_not_prove_final_no_failure_completion",
}
_FINAL_VALUES = {"pass", "passed", "verified", "completed", "complete", "success", "succeeded"}
_COMPARISON_TEXT = re.compile(
    r"\b(?:both\s+harnesses|identical\s+controls|pure\s+harness\s+ablation|"
    r"same\s+(?:model\s+behavior|controls?|answers?|outputs?|results?)|"
    r"equivalent\s+(?:behavior|answers?|outputs?|results?))\b",
    re.I,
)
_FINAL_TEXT = re.compile(r"\b(?:completed\s+with\s+no\s+failures?|no\s+failures?)\b", re.I)


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _rows(value: Any, field: str, malformed) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise malformed(f"{field}_type_invalid")
    return value


def _strings(value: Any, field: str, malformed) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise malformed(f"{field}_type_invalid")
    return value


def _claim_map(report: dict[str, Any], malformed) -> dict[str, dict[str, Any]]:
    rows = _rows(report.get("claim_bindings"), "claim_bindings", malformed)
    claims: dict[str, dict[str, Any]] = {}
    for row in rows:
        claim_id = row.get("claim_id")
        if not isinstance(claim_id, str) or not claim_id or claim_id in claims:
            continue
        claims[claim_id] = row
    return claims


def render_shared_task_markdown_v2(report: dict[str, Any]) -> str:
    """Render the verifier-owned canonical Markdown for a participant report."""
    claims = _claim_map(report, ValueError)
    facts = claims["pre_oracle_attempt_state"]["facts"]
    limitations = [_LIMITATION_CLAIMS[key] for key in (
        "provider_superiority_boundary", "cross_harness_comparison_boundary", "final_completion_boundary")]
    lines = [
        f"# {report['task_id']}", "",
        "## Bound inputs",
        f"- input_sha256s: {_json(report['input_sha256s'])}",
        f"- raw_prompt_sha256: {_json(report['raw_prompt_sha256'])}",
        f"- tool_policy_sha256: {_json(report['tool_policy_sha256'])}", "",
        "## Bound attempt artifacts",
        f"- raw_artifact_path: {_json(report['raw_artifact_path'])}",
        f"- receipt_path: {_json(report['receipt_path'])}", "",
        "## Pre-oracle states",
        f"- execution_state: {_json(facts['execution_state'])}",
        f"- oracle_state: {_json(facts['oracle_state'])}",
        f"- receipt_state: {_json(facts['receipt_state'])}",
        f"- pre_oracle_failure_modes: {_json(facts['pre_oracle_failure_modes'])}", "",
        "## Claim bindings",
        "- pre_oracle_attempt_state: pre_oracle_attempt_facts from scorecard_core.orthogonal_states",
        "- raw_artifact_binding: artifact_binding from raw_artifact_path to scorecard_core.raw_artifact_sha256",
        "- receipt_binding: artifact_binding from receipt_path to scorecard_core.receipt_sha256",
        "", "## Closed limitations",
    ]
    lines.extend(f"- {item}: {LIMITATION_TEXT[item]}" for item in limitations)
    return "\n".join(lines) + "\n"

def _producer_template() -> list[str]:
    return [
        "# {task_id}", "", "## Bound inputs", "- input_sha256s: {input_sha256s}",
        "- raw_prompt_sha256: {raw_prompt_sha256}", "- tool_policy_sha256: {tool_policy_sha256}", "",
        "## Bound attempt artifacts", "- raw_artifact_path: {raw_artifact_path}", "- receipt_path: {receipt_path}", "",
        "## Pre-oracle states", "- execution_state: {execution_state}", "- oracle_state: {oracle_state}",
        "- receipt_state: {receipt_state}", "- pre_oracle_failure_modes: {pre_oracle_failure_modes}", "",
        "## Claim bindings", "- pre_oracle_attempt_state: pre_oracle_attempt_facts from scorecard_core.orthogonal_states",
        "- raw_artifact_binding: artifact_binding from raw_artifact_path to scorecard_core.raw_artifact_sha256",
        "- receipt_binding: artifact_binding from receipt_path to scorecard_core.receipt_sha256", "", "## Closed limitations",
        "- does_not_prove_provider_superiority: This attempt does not prove provider superiority.",
        "- does_not_prove_cross_harness_comparison: This attempt does not prove a Codex-vs-Flywheel comparison.",
        "- does_not_prove_final_no_failure_completion: This pre-oracle artifact does not prove final no-failure completion.",
    ]


def _producer_claim_bindings_template() -> list[dict[str, Any]]:
    facts = {"execution_state": "{harness_values.orthogonal_states.execution_state}", "oracle_state": "{harness_values.orthogonal_states.oracle_state}", "receipt_state": "{harness_values.orthogonal_states.receipt_state}", "pre_oracle_failure_modes": "{harness_values.pre_oracle_failure_modes}"}
    rows = [{
        "claim_id": "pre_oracle_attempt_state", "claim_type": "pre_oracle_attempt_facts",
        "subject": "attempt", "authority": "scorecard_core.orthogonal_states", "facts": facts,
    }]
    rows.extend({
        "claim_id": key, "claim_type": "artifact_binding", "subject": subject,
        "authority": authority, "path_field": fields[0], "sha256_field": fields[1],
    } for key, (_, subject, authority) in _EXPECTED_CLAIMS.items() if key in _ARTIFACT_BINDINGS
        for fields in [_ARTIFACT_BINDINGS[key]])
    rows.extend({
        "claim_id": key, "claim_type": "limitation", "subject": "attempt",
        "authority": _EXPECTED_CLAIMS[key][2], "limitation_id": value,
    } for key, value in _LIMITATION_CLAIMS.items())
    return rows


def _fixture_codes(fixture: dict[str, Any], malformed) -> None:
    if fixture.get("schema") != "harness.cross-harness-fixture.shared-task-facts/v2":
        raise malformed("fixture_schema_invalid")
    if sorted(_strings(fixture.get("supported_claim_types"), "supported_claim_types", malformed)) != sorted(_SUPPORTED_TYPES):
        raise malformed("supported_claim_types_invalid")
    if sorted(_strings(fixture.get("supported_claim_ids"), "supported_claim_ids", malformed)) != sorted(_EXPECTED_CLAIMS):
        raise malformed("supported_claim_ids_invalid")
    if sorted(_strings(fixture.get("limitation_ids"), "limitation_ids", malformed)) != sorted(LIMITATION_TEXT):
        raise malformed("limitation_ids_invalid")
    if fixture.get("markdown_render_profile") != "shared_task_artifact_v2_pre_oracle":
        raise malformed("markdown_render_profile_invalid")
    contract = fixture.get("participant_contract")
    verifier = fixture.get("verifier_contract")
    if not isinstance(contract, dict) or contract.get("schema") != "harness.cross-harness-fixture.shared-task-artifact-v2-participant/v1":
        raise malformed("participant_contract_invalid")
    required = {"schema", "context_path", "fixture_path", "produces_json_fields", "json_serialization", "claim_bindings", "markdown_template"}
    if (
        set(contract) != required or contract.get("context_path") != "benchmark/context.json"
        or contract.get("fixture_path") != "benchmarks/fixtures/cross-harness/shared-task-facts-v2.json"
        or contract.get("produces_json_fields") != sorted(_REQUIRED_FIELDS)
        or contract.get("json_serialization") != 'json.dumps(sort_keys=True,separators=(",",":"),ensure_ascii=False)'
        or contract.get("claim_bindings") != _producer_claim_bindings_template()
        or contract.get("markdown_template") != _producer_template()
    ):
        raise malformed("participant_contract_invalid")
    if verifier != {"schema": "harness.cross-harness-fixture.shared-task-artifact-v2-verifier/v1", "computes_evidence": ["verifier_markdown_render_sha256"], "hash": {"algorithm": "sha256", "encoding": "utf-8", "preimage": "canonical Markdown render from participant JSON"}, "compares": ["submitted_markdown_bytes", "canonical_markdown_render"]}:
        raise malformed("participant_contract_invalid")


def _top_level_codes(report: dict[str, Any], malformed) -> list[str]:
    missing = _REQUIRED_FIELDS - set(report)
    if missing:
        raise malformed("shared_task_v2_required_field_missing")
    extras = set(report) - _REQUIRED_FIELDS
    codes = []
    if extras & _FINAL_TOP_LEVEL:
        codes.append("final_status_claim_not_available")
    if extras - _FINAL_TOP_LEVEL:
        codes.append("unsupported_report_field")
    for field in ("raw_artifact_path", "receipt_path"):
        if not isinstance(report.get(field), str) or not report[field]:
            raise malformed(f"{field}_type_invalid")
    from harness.cross_harness_oracles import _digest
    for field in ("raw_prompt_sha256", "tool_policy_sha256"):
        _digest(report.get(field), field)
    _strings(report.get("pre_oracle_failure_modes"), "pre_oracle_failure_modes", malformed)
    return codes


def _claim_codes(report: dict[str, Any], context, malformed) -> list[str]:
    rows = _rows(report.get("claim_bindings"), "claim_bindings", malformed)
    codes: list[str] = []
    claims: dict[str, dict[str, Any]] = {}
    for row in rows:
        for field in ("claim_id", "claim_type", "subject", "authority"):
            if not isinstance(row.get(field), str) or not row[field]:
                raise malformed(f"{field}_type_invalid")
        claim_id, claim_type = row["claim_id"], row["claim_type"]
        expected = _EXPECTED_CLAIMS.get(claim_id)
        if claim_type not in _SUPPORTED_TYPES:
            codes.append("unsupported_claim_type")
        if expected is None or expected[0] != claim_type or claim_id in claims:
            codes.append("unsupported_claim_id")
        if expected and row.get("subject") != expected[1]:
            codes.append("claim_subject_out_of_scope")
        if expected and row.get("authority") != expected[2]:
            codes.append("claim_authority_mismatch")
        claims[claim_id] = row
        if claim_type == "pre_oracle_attempt_facts":
            allowed = {"claim_id", "claim_type", "subject", "authority", "facts"}
            if set(row) - allowed:
                codes.append("unsupported_claim_field")
            codes.extend(_pre_oracle_fact_codes(row.get("facts"), context, malformed))
        elif claim_type == "artifact_binding":
            allowed = {"claim_id", "claim_type", "subject", "authority", "path_field", "sha256_field"}
            if set(row) - allowed:
                codes.append("unsupported_claim_field")
            if expected and (row.get("path_field"), row.get("sha256_field")) != _ARTIFACT_BINDINGS.get(claim_id):
                codes.append("claim_authority_mismatch")
        elif claim_type == "limitation":
            allowed = {"claim_id", "claim_type", "subject", "authority", "limitation_id"}
            if any(key in row for key in ("value", "text", "label", "description", "summary")):
                codes.append("unsupported_limitation_value")
            if set(row) - allowed - {"value", "text", "label", "description", "summary"}:
                codes.append("unsupported_claim_field")
            if not isinstance(row.get("limitation_id"), str) or row["limitation_id"] not in LIMITATION_TEXT:
                codes.append("unsupported_limitation_id")
            if expected and row.get("limitation_id") != _LIMITATION_CLAIMS.get(claim_id):
                codes.append("claim_authority_mismatch")
    if set(claims) != set(_EXPECTED_CLAIMS):
        codes.append("claim_bindings_missing")
    return codes


def _pre_oracle_fact_codes(value: Any, context, malformed) -> list[str]:
    if not isinstance(value, dict):
        raise malformed("pre_oracle_facts_type_invalid")
    expected_keys = set(PRE_ORACLE_STATES) | {"pre_oracle_failure_modes"}
    if set(value) != expected_keys:
        if set(value) & {"status", "primary_outcome"}:
            return ["final_status_claim_not_available"]
        raise malformed("pre_oracle_facts_type_invalid")
    _strings(value.get("pre_oracle_failure_modes"), "pre_oracle_failure_modes", malformed)
    if any(type(value.get(axis)) is not str for axis in PRE_ORACLE_STATES):
        raise malformed("pre_oracle_facts_type_invalid")
    if any(value.get(axis) in _FINAL_VALUES for axis in PRE_ORACLE_STATES):
        return ["final_status_claim_not_available"]
    states = context.scorecard_core.get("orthogonal_states")
    expected = {**PRE_ORACLE_STATES, "pre_oracle_failure_modes": []}
    if states != PRE_ORACLE_STATES or value != expected:
        return ["pre_oracle_status_claim_mismatch"]
    return []


def _text_codes(texts: Iterable[str]) -> list[str]:
    joined = "\n".join(texts)
    codes = []
    if _COMPARISON_TEXT.search(joined):
        codes.append("comparison_claim_out_of_scope")
    if _FINAL_TEXT.search(joined):
        codes.append("final_status_claim_not_available")
    return codes


def shared_task_artifact_v2(context, report, texts, fixture, checked):
    """Validate the shared-task diagnostic without accepting freeform claims."""
    from harness.cross_harness_oracles import _Malformed, _shared

    _fixture_codes(fixture, _Malformed)
    codes = _top_level_codes(report, _Malformed)
    legacy = dict(report)
    legacy["failure_modes"] = report["pre_oracle_failure_modes"]
    codes.extend("pre_oracle_failure_modes_mismatch" if code == "failure_modes_mismatch" else code
                 for code in _shared(context, legacy, texts, fixture, checked))
    codes.extend(_claim_codes(report, context, _Malformed))
    structural = set(codes)
    markdown_texts = [text for name, text in texts.items() if name.endswith(".md")]
    codes.extend(_text_codes(markdown_texts))
    if not structural & {
        "unsupported_claim_field", "unsupported_claim_type", "unsupported_claim_id",
        "unsupported_limitation_id", "unsupported_limitation_value", "claim_bindings_missing",
        "claim_subject_out_of_scope", "claim_authority_mismatch",
        "pre_oracle_status_claim_mismatch", "final_status_claim_not_available",
        "unsupported_report_field",
    }:
        expected = render_shared_task_markdown_v2(report)
        metrics = {"verifier_markdown_render_sha256": _sha_text(expected)}
        actual = next(text for text in markdown_texts).replace("\r\n", "\n")
        if actual != expected:
            codes.append("markdown_render_mismatch")
        return codes, metrics
    return codes
