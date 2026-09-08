"""Native local endpoint usage retention helpers."""
from __future__ import annotations

from typing import Any

OLLAMA_USAGE_FIELDS = frozenset({
    "prompt_eval_count",
    "prompt_eval_cached_count",
    "eval_count",
    "prompt_eval_duration",
    "eval_duration",
    "load_duration",
    "total_duration",
})
OLLAMA_USAGE_INVALID = (
    "OLLAMA_USAGE_INVALID: a native usage field is not a nonnegative integer"
)


def ollama_native_usage(response: dict[str, Any]) -> dict[str, Any] | None:
    usage: dict[str, Any] = {}
    invalid = False
    for field in sorted(OLLAMA_USAGE_FIELDS):
        if field not in response:
            continue
        value = response[field]
        if type(value) is int and value >= 0:
            usage[field] = value
        else:
            invalid = True
    if invalid:
        usage["native_usage_refused"] = OLLAMA_USAGE_INVALID
    return usage or None
