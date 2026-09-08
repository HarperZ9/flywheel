"""Semantic result scoring for the source-only KV oracle checker."""
from __future__ import annotations

import math
from typing import Any

from harness.cross_harness_oracle_support import _Malformed, _strings


def _no_nonfinite(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _no_nonfinite(item) for key, item in value.items())
    if isinstance(value, list):
        return all(_no_nonfinite(item) for item in value)
    return True


def _json_equal(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is right
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left is right
    if isinstance(left, int) or isinstance(right, int):
        return (
            isinstance(left, int)
            and not isinstance(left, bool)
            and isinstance(right, int)
            and not isinstance(right, bool)
            and left == right
        )
    if isinstance(left, float) or isinstance(right, float):
        return isinstance(left, float) and isinstance(right, float) and left == right
    if isinstance(left, str) or isinstance(right, str):
        return isinstance(left, str) and isinstance(right, str) and left == right
    if isinstance(left, list) or isinstance(right, list):
        return (
            isinstance(left, list)
            and isinstance(right, list)
            and len(left) == len(right)
            and all(_json_equal(a, b) for a, b in zip(left, right))
        )
    if isinstance(left, dict) or isinstance(right, dict):
        return (
            isinstance(left, dict)
            and isinstance(right, dict)
            and set(left) == set(right)
            and all(_json_equal(left[key], right[key]) for key in left)
        )
    return False


def _argv_flags(answer: Any) -> set[str]:
    if not isinstance(answer, dict):
        return set()
    argv = answer.get("argv")
    if not isinstance(argv, list) or any(not isinstance(item, str) for item in argv):
        return set()
    return {item for item in argv if item.startswith("--")}


def _score_result(
    observed: dict[str, Any],
    expected: dict[str, Any],
    source_ids: set[str],
    citation_order: str,
) -> list[str]:
    if not _no_nonfinite(observed):
        raise _Malformed("result_nonfinite")
    if citation_order not in {"unordered_set", "ordered_array"}:
        raise _Malformed("citation_order_invalid")

    codes: list[str] = []
    verdict = expected["verdict"]
    if observed.get("task_id") != expected["task_id"]:
        codes.append("task_id_mismatch")
    if observed.get("verdict") != verdict:
        codes.append("verdict_mismatch")
        return codes

    if verdict == "UNVERIFIABLE":
        required_keys = {
            "task_id",
            "verdict",
            "answer",
            "missing_evidence",
            "claims_not_made",
            "citations",
        }
        if "missing_evidence" not in observed:
            codes.append("missing_evidence_missing")
            return codes
        if "claims_not_made" not in observed:
            codes.append("claims_not_made_missing")
            return codes
    else:
        required_keys = {"task_id", "verdict", "answer", "citations"}

    if set(observed) != required_keys:
        codes.append("response_shape_mismatch")
    if not _json_equal(observed.get("answer"), expected.get("answer")):
        codes.append("answer_mismatch")
    if _argv_flags(observed.get("answer")) - _argv_flags(expected.get("answer")):
        codes.append("forbidden_claim_or_flag")

    if verdict == "UNVERIFIABLE":
        if not _json_equal(observed.get("missing_evidence"), expected.get("missing_evidence")):
            codes.append("missing_evidence_mismatch")
        if not _json_equal(observed.get("claims_not_made"), expected.get("claims_not_made")):
            codes.append("claims_not_made_mismatch")

    citations = observed.get("citations")
    if not isinstance(citations, list) or any(not isinstance(item, str) for item in citations):
        codes.append("citations_type_invalid")
    else:
        if len(set(citations)) != len(citations):
            codes.append("citation_duplicate")
        if any(item not in source_ids for item in citations):
            codes.append("citation_unknown")
        expected_citations = _strings(expected.get("citations"), "expected_citations")
        if citation_order == "ordered_array":
            if citations != expected_citations:
                codes.append("citations_mismatch")
        elif set(citations) != set(expected_citations):
            codes.append("citations_mismatch")
    return codes
