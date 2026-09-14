from __future__ import annotations

from typing import Any

REPORT_SCHEMA = "flywheel.inspect-scorer-unit-analysis/v1"
PYTHON_TEST_UNIT = "python_test_function_definition"
DRIFT_REASONS = {"source_hash_mismatch", "source_byte_length_mismatch", "pointer_missing", "source_value_mismatch",
                 "span_out_of_range", "span_source_value_mismatch", "span_source_value_sha256_mismatch",
                 "duplicate_unit_id", "duplicate_definition_name", "overlapping_selector", "omitted_definition_without_exclusion",
                 "selector_completeness_unverified", "claimed_intended_unit_backed_only_by_sample_count", "partial_mapping",
                 "exclusion_reason_missing", "unsupported_declared_intended_unit", "unsupported_mapped_definition_unit",
                 "unsupported_aggregation_input_unit"}


def analysis(contracts: list[dict], reasons: list[str], refs: list[dict] | None = None) -> dict:
    out = {"schema": REPORT_SCHEMA, "semantic_verification": "UNVERIFIABLE",
           "contracts": contracts, "does_not_prove": [
               "Mapping consistency does not prove scorer correctness.",
               "A many-to-one row score does not establish per-definition score coverage."]}
    if reasons and not contracts:
        out["reason_codes"] = reasons
    if refs:
        out["source_pointers"] = unique_refs(refs)
    return out


def walk_refs(value: object):
    if type(value) is dict:
        if type(value.get("json_pointer")) is str and "source_value" in value:
            yield value
        for item in value.values():
            yield from walk_refs(item)
    elif type(value) is list:
        for item in value:
            yield from walk_refs(item)


def pointer_value(value: Any, pointer: str) -> Any:
    if type(pointer) is not str or not pointer.startswith("/"):
        raise ValueError("bad pointer")
    for part in pointer.split("/")[1:]:
        key = part.replace("~1", "/").replace("~0", "~")
        value = value[int(key)] if type(value) is list else value[key]
    return value


def overlaps(spans: list[tuple[str, int, int, object]]) -> int:
    count = 0
    for index, left in enumerate(spans):
        for right in spans[index + 1:]:
            same = left[0] == right[0]
            overlap = left[1] < right[2] and right[1] < left[2]
            identical = left[:3] == right[:3] and left[3] == right[3]
            if same and overlap and not identical:
                count += 1
    return count


def unique_refs(refs: list[dict]) -> list[dict]:
    out, seen = [], set()
    for ref in refs:
        key = (ref.get("json_pointer"), repr(ref.get("source_value")))
        if key not in seen:
            seen.add(key); out.append(ref)
    return out
