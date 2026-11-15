from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from importlib import resources
from pathlib import Path
from typing import Any

DEFAULT_SCHEMA = resources.files(__package__) / "schema.json"
MAX_MESSAGE_LENGTH = 240
REDACTION_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bASIA[0-9A-Z]{16}\b"),
    re.compile(r"\bghp_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"(?i)\b(bearer|token|api[_-]?key|password|secret)\s*[:=]\s*\S+"),
    re.compile(r"\b[A-Za-z]:\\[^\s'\"<>]+"),
    re.compile(r"(?<!\w)/(?:Users|home|tmp|dev|var|etc)/[^\s'\"<>]+"),
)


@dataclass(frozen=True)
class ValidationError:
    path: str
    message: str


def scrub_text(value: str, max_length: int = MAX_MESSAGE_LENGTH) -> str:
    text = value.replace("\x00", " ")
    for pattern in REDACTION_PATTERNS:
        text = pattern.sub("<redacted>", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_length:
        text = text[: max_length - 3].rstrip() + "..."
    return text


def _safe_repr(value: Any) -> str:
    return repr(scrub_text(value) if isinstance(value, str) else value)


def load_schema(path: str | Path = DEFAULT_SCHEMA) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Schema root must be a JSON object")
    return data


def load_envelope(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Envelope root must be a JSON object")
    return data


def validate_envelope(envelope: dict[str, Any], schema: dict[str, Any]) -> list[ValidationError]:
    errors: list[ValidationError] = []
    _validate_value("$", envelope, schema, errors)
    _validate_reference_dates(envelope, errors)
    return errors


def _validate_reference_dates(envelope: dict[str, Any], errors: list[ValidationError]) -> None:
    references = envelope.get("references")
    if not isinstance(references, list):
        return
    for index, item in enumerate(references):
        if not isinstance(item, dict):
            continue
        value = item.get("retrieved_at")
        if not isinstance(value, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None:
            continue
        try:
            date.fromisoformat(value)
        except ValueError:
            errors.append(ValidationError(f"$.references[{index}].retrieved_at", "expected valid calendar date"))


def _validate_object(
    path: str,
    value: dict[str, Any],
    rules: dict[str, Any],
    errors: list[ValidationError],
) -> None:
    properties = rules.get("properties", {})
    required = rules.get("required", [])

    for field in required:
        if field not in value:
            errors.append(ValidationError(f"{path}.{field}", "missing required field"))

    if rules.get("additionalProperties") is False:
        allowed = set(properties)
        for field in value:
            if field not in allowed:
                errors.append(ValidationError(f"{path}.{field}", "unexpected field"))

    for field, child_rules in properties.items():
        if field in value and isinstance(child_rules, dict):
            _validate_value(f"{path}.{field}", value[field], child_rules, errors)


def _validate_array(
    path: str,
    value: list[Any],
    rules: dict[str, Any],
    errors: list[ValidationError],
) -> None:
    min_items = int(rules.get("minItems", 0))
    if len(value) < min_items:
        errors.append(ValidationError(path, f"expected at least {min_items} item(s)"))

    item_rules = rules.get("items", {})
    if isinstance(item_rules, dict):
        for index, item in enumerate(value):
            _validate_value(f"{path}[{index}]", item, item_rules, errors)


def _validate_value(
    path: str,
    value: Any,
    rules: dict[str, Any],
    errors: list[ValidationError],
) -> None:
    expected_type = rules.get("type")

    if expected_type == "object":
        if not isinstance(value, dict):
            errors.append(ValidationError(path, f"expected object, got {type(value).__name__}"))
            return
        _validate_object(path, value, rules, errors)
    elif expected_type == "array":
        if not isinstance(value, list):
            errors.append(ValidationError(path, f"expected array, got {type(value).__name__}"))
            return
        _validate_array(path, value, rules, errors)
    elif expected_type == "string":
        if not isinstance(value, str):
            errors.append(ValidationError(path, f"expected string, got {type(value).__name__}"))
            return
        if len(value) < int(rules.get("minLength", 0)):
            errors.append(ValidationError(path, "expected non-empty string"))
        pattern = rules.get("pattern")
        if isinstance(pattern, str) and re.fullmatch(pattern, value) is None:
            errors.append(ValidationError(path, f"expected string matching pattern {pattern!r}"))

    if "enum" in rules and value not in rules["enum"]:
        allowed = ", ".join(str(item) for item in rules["enum"])
        errors.append(ValidationError(path, f"invalid value {_safe_repr(value)}; expected one of: {allowed}"))

    if "const" in rules and value != rules["const"]:
        errors.append(ValidationError(path, f"invalid value {_safe_repr(value)}; expected {rules['const']!r}"))
