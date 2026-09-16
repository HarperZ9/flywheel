"""Evaluate decision proposals against independent labels, without execution.

Label and measurement provenance belongs to the caller. A report does not make
synthetic controls into model results or attest that supplied labels are true.
"""
from __future__ import annotations

import math
import statistics

from .evidence_json import canonical_sha256

_RESULT_SCHEMA = "flywheel.decision-result/v1"
_REQUIRED = {"case_id", "declared_choice_ids", "eligible_choice_ids",
             "acceptable_choice_ids", "expect_abstain", "result"}
_OPTIONAL = {"latency_ms", "cost_usd"}
_RESULT_KEYS = {"schema", "disposition", "choice_id", "reason_code",
                "evidence_refs", "request_sha256", "response_sha256",
                "scorer_ref", "does_not_prove"}
_REASON_CODES = {"selected", "abstain", "empty_eligibility",
                 "response_oversize", "malformed_json", "duplicate_key",
                 "invalid_shape", "unknown_choice", "ineligible_choice",
                 "invented_evidence_ref", "invalid_scorer_ref"}
_NULL_RESPONSE_REASONS = {"response_oversize", "invalid_shape"}
_KINDS = ("correct_selections", "wrong_selections", "ineligible_selections",
          "correct_abstentions", "unnecessary_abstentions",
          "missed_abstentions", "rejected_proposals", "invalid_results")
_HEX = set("0123456789abcdef")
_DIGEST0 = "0" * 64
_DIGEST1 = "1" * 64
_CONTROL_DISCLAIMERS = [
    "deterministic controls only, not model quality",
    "no provider call, latency measurement, or competitive benchmark",
    "label truth and authorization remain external to this report",
]


def _ids(value):
    if (not isinstance(value, list) or len(value) > 4096
            or any(not isinstance(x, str) or not x or len(x) > 256
                   for x in value)
            or len(set(value)) != len(value)):
        raise ValueError("invalid choice labels")
    return set(value)


def _measurement(case, name):
    value = case.get(name)
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("invalid observed measurement")
    return value


def _hex_digest(value):
    return type(value) is str and len(value) == 64 and set(value) <= _HEX


def _string_list(value):
    return (type(value) is list and len(value) <= 4096
            and all(type(item) is str and item for item in value)
            and len(set(value)) == len(value))


def _valid_response_digest(value, disposition, reason):
    if value is None:
        return disposition == "abstained" and reason in _NULL_RESPONSE_REASONS
    return _hex_digest(value)


def _valid_result(result):
    if type(result) is not dict or set(result) != _RESULT_KEYS:
        return False
    try:
        canonical_sha256(result)
    except (ValueError, RecursionError):
        return False
    disposition, choice = result["disposition"], result["choice_id"]
    reason = result["reason_code"]
    if result["schema"] != _RESULT_SCHEMA:
        return False
    if type(reason) is not str or reason not in _REASON_CODES:
        return False
    if disposition == "selected":
        if type(choice) is not str or not choice or reason != "selected":
            return False
    elif disposition == "abstained":
        if choice is not None or reason == "selected":
            return False
    else:
        return False
    return (_string_list(result["evidence_refs"])
            and _hex_digest(result["request_sha256"])
            and _valid_response_digest(
                result["response_sha256"], disposition, reason)
            and type(result["scorer_ref"]) is str
            and type(result["does_not_prove"]) is str
            and bool(result["does_not_prove"]))


def _case(case):
    if (not isinstance(case, dict) or not _REQUIRED <= case.keys()
            or case.keys() - (_REQUIRED | _OPTIONAL)):
        raise ValueError("invalid evaluation case fields")
    ref = case["case_id"]
    if not isinstance(ref, str) or not ref or len(ref) > 256:
        raise ValueError("invalid case id")
    declared = _ids(case["declared_choice_ids"])
    eligible = _ids(case["eligible_choice_ids"])
    acceptable = _ids(case["acceptable_choice_ids"])
    expect = case["expect_abstain"]
    if (type(expect) is not bool or not eligible <= declared
            or not acceptable <= eligible or bool(acceptable) == expect):
        raise ValueError("inconsistent evaluation labels")
    latency, cost = _measurement(case, "latency_ms"), _measurement(case, "cost_usd")
    result = case["result"]
    if not _valid_result(result):
        return ref, "invalid_results", False, expect, latency, cost
    choice, disposition = result["choice_id"], result["disposition"]
    reason = result["reason_code"]
    if disposition == "abstained":
        if reason == "empty_eligibility":
            kind = "rejected_proposals" if not eligible else "invalid_results"
            return ref, kind, False, expect, latency, cost
        if reason != "abstain":
            return ref, "rejected_proposals", False, expect, latency, cost
        kind = "correct_abstentions" if expect else "unnecessary_abstentions"
        return ref, kind, False, expect, latency, cost
    if choice not in declared:
        return ref, "invalid_results", False, expect, latency, cost
    if choice not in eligible:
        kind = "ineligible_selections"
    elif expect:
        kind = "missed_abstentions"
    else:
        kind = "correct_selections" if choice in acceptable else "wrong_selections"
    return ref, kind, True, expect, latency, cost


def _rate(numerator, denominator):
    return numerator / denominator if denominator else None


def _input_hash(value):
    try:
        return canonical_sha256(value), None
    except (ValueError, RecursionError):
        return None, "input_not_canonical_json"


def evaluate_cases(cases: list[dict]) -> dict:
    """Report labeled correctness separately from syntactic/eligibility validity."""
    if not isinstance(cases, list) or len(cases) > 100_000:
        raise ValueError("evaluation cases must be a bounded list")
    counts = dict.fromkeys(_KINDS, 0)
    counts.update(total=len(cases), selected=0, abstained=0, expected_abstentions=0)
    seen, rows, latencies, costs = set(), [], [], []
    for case in cases:
        ref, kind, selected, expect, latency, cost = _case(case)
        if ref in seen:
            raise ValueError("duplicate evaluation case id")
        seen.add(ref)
        counts[kind] += 1
        counts["selected"] += int(selected)
        counts["abstained"] += int(kind in {"correct_abstentions", "unnecessary_abstentions"})
        counts["expected_abstentions"] += int(expect)
        rows.append({"case_id": ref, "outcome": kind})
        if latency is not None:
            latencies.append(latency)
        if cost is not None:
            costs.append(cost)
    total, selected = counts["total"], counts["selected"]
    correct = counts["correct_selections"] + counts["correct_abstentions"]
    input_sha256, input_sha256_error = _input_hash(cases)
    denominators = {
        "selection_coverage": total,
        "selective_accuracy": selected,
        "overall_correct_fraction": total,
        "abstention_precision": counts["abstained"],
        "abstention_recall": counts["expected_abstentions"],
    }
    return {
        "schema": "flywheel.decision-evaluation/v1",
        "input_sha256": input_sha256,
        "input_sha256_error": input_sha256_error,
        "counts": counts,
        "metric_denominators": denominators,
        "metrics": {
            "selection_coverage": _rate(selected, total),
            "selective_accuracy": _rate(counts["correct_selections"], selected),
            "overall_correct_fraction": _rate(correct, total),
            "abstention_precision": _rate(counts["correct_abstentions"], counts["abstained"]),
            "abstention_recall": _rate(counts["correct_abstentions"], counts["expected_abstentions"]),
        },
        "measurements": {
            "latency_observed_cases": len(latencies),
            "cost_observed_cases": len(costs),
            "latency_ms_p50": statistics.median(latencies) if latencies else None,
            "latency_ms_p95": sorted(latencies)[math.ceil(.95 * len(latencies)) - 1] if latencies else None,
            "cost_usd_observed_sum": sum(costs) if costs else None,
            "measurement_coverage_complete": bool(total) and len(latencies) == len(costs) == total,
            "method": "caller_supplied_measurements; p95_nearest_rank",
        },
        "cases": rows,
        "does_not_prove": [
            "independence or semantic truth of caller-supplied labels",
            "caller-supplied result authenticity or mounted gateway admission",
            "authenticity of caller-supplied latency and cost measurements",
            "model quality unless cases contain actual held-out model outputs",
            "authorization, safe execution, or superiority to another router",
        ],
    }


def _control_result(choice, *, reason_code=None):
    reason = reason_code or ("abstain" if choice is None else "selected")
    return {
        "schema": _RESULT_SCHEMA,
        "disposition": "abstained" if choice is None else "selected",
        "choice_id": choice,
        "reason_code": reason,
        "evidence_refs": [],
        "request_sha256": _DIGEST0,
        "response_sha256": _DIGEST1,
        "scorer_ref": "synthetic-control",
        "does_not_prove": "synthetic control fixture only",
    }


def _control_case(ref, choice, *, expect_abstain=False, reason_code=None):
    return {
        "case_id": ref,
        "declared_choice_ids": ["search", "reason", "remote"],
        "eligible_choice_ids": ["search", "reason"],
        "acceptable_choice_ids": [] if expect_abstain else ["search"],
        "expect_abstain": expect_abstain,
        "result": _control_result(choice, reason_code=reason_code),
    }


def synthetic_control_report() -> dict:
    """Return deterministic offline controls with no provider calls."""
    controls = {
        "correct": evaluate_cases([_control_case("correct", "search")]),
        "wrong_but_valid": evaluate_cases([_control_case("wrong", "reason")]),
        "ineligible": evaluate_cases([_control_case("ineligible", "remote")]),
        "abstain_all": evaluate_cases([
            _control_case("abstain-one", None),
            _control_case("abstain-two", None),
        ]),
        "rejected_when_abstention_expected": evaluate_cases([
            _control_case(
                "rejected-abstain", None, expect_abstain=True,
                reason_code="unknown_choice"),
        ]),
    }
    return {
        "schema": "flywheel.decision-control-report/v1",
        "methodology": "deterministic synthetic controls; no provider calls",
        "controls": controls,
        "does_not_prove": list(_CONTROL_DISCLAIMERS),
    }
