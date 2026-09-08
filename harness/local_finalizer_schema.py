"""JSON schema builder for the local finalizer experiment envelope."""
from __future__ import annotations

from typing import Any


def _field_schema(name: str) -> dict[str, Any]:
    if name in {"task_id"}:
        return {"type": "string"}
    if name in {"input_sha256s", "receipt_input_sha256s"}:
        return {"type": "object", "additionalProperties": {"type": "string"}}
    if name == "selected":
        return {"type": "array", "items": {"type": "string"}}
    if name in {"total_cost_usd", "total_value"}:
        return {"type": "number"}
    if name == "measurements":
        return {"type": "array", "items": {"type": "object", "required": ["measurement_id", "value", "denominator", "interval_95"],
                "additionalProperties": False, "properties": {"measurement_id": {"type": "string"}, "value": {"type": "number"},
                "denominator": {"type": "number"}, "interval_95": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "number"}}}}}
    if name == "claim_verdicts":
        return {"type": "array", "items": {"type": "object", "required": ["claim_id", "verdict", "evidence"],
                "additionalProperties": False, "properties": {"claim_id": {"type": "string"},
                "verdict": {"type": "string", "enum": ["supported", "unverifiable"]},
                "evidence": {"type": "array", "items": {"type": "string"}}}}}
    if name == "contradictions":
        return {"type": "array", "items": {"type": "object", "required": ["records"], "additionalProperties": False,
                "properties": {"records": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "string"}}}}}
    return {"type": "array"} if name.endswith("s") else {"type": ["string", "number", "object", "array", "boolean", "null"]}


def schema_for_task(task: dict[str, Any]) -> dict[str, Any]:
    props, required = {}, []
    fields = list(task.get("oracle", {}).get("required_json_fields", []))
    for name in task.get("expected_artifacts", []):
        required.append(str(name))
        if str(name).endswith(".md"):
            props[str(name)] = {"type": "string"}
        elif fields:
            props[str(name)] = {"type": "object", "required": fields, "additionalProperties": False,
                                "properties": {field: _field_schema(str(field)) for field in fields}}
        else:
            props[str(name)] = {"type": "object"}
    return {"type": "object", "required": ["artifacts"], "additionalProperties": False,
            "properties": {"artifacts": {"type": "object", "required": required,
                           "additionalProperties": False, "properties": props}}}
