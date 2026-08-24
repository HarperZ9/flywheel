"""gateway_operation_shape.py -- per-action shape validation.

Extracted from gateway_operation.py to keep that module under its
ceiling. One function, pure: given an action and its canonical snapshot,
raise ValueError on any shape this gateway refuses. Field-type rules
live here so the canonicalization core stays about digests, refs, and
scopes.
"""
from __future__ import annotations

from .gateway_operation import PROPOSAL_REF_PATTERN, OPERATION_REF_PATTERN, _text


def validate_operation_shape(action: str, value: dict) -> None:
    text_fields = {"model", "goal", "endpoint", "workflow", "profile", "root",
                   "test_cmd", "name", "tool", "detail", "prompt",
                   "solution_sig", "context", "intent_source",
                   "architecture_source", "prp_id"}
    if any(key in value and not _text(value[key]) for key in text_fields):
        raise ValueError
    if action == "embeddings.create":
        items = value["input"]
        if type(items) is list:
            if not items or any(not _text(item) for item in items):
                raise ValueError
        elif not _text(items):
            raise ValueError
    if action == "forge.create":
        for list_field in ("examples", "documentation"):
            if list_field in value and type(value[list_field]) is not list:
                raise ValueError
    if action == "chat.complete":
        messages = value["messages"]
        if (type(messages) is not list or not messages
                or any(type(item) is not dict
                       or set(item) != {"role", "content"}
                       or item["role"] not in {"system", "user", "assistant"}
                       or type(item["content"]) is not str for item in messages)):
            raise ValueError
    for name in ("stream", "allow_write", "allow_exec", "enabled"):
        if name in value and type(value[name]) is not bool:
            raise ValueError
    if "max_steps" in value and (type(value["max_steps"]) is not int
                                 or not 1 <= value["max_steps"] <= 12):
        raise ValueError
    if ("timeout_ms" in value and (type(value["timeout_ms"]) is not int
                                   or not 1 <= value["timeout_ms"] <= 30_000)):
        raise ValueError
    if ("operation_ref" in value and OPERATION_REF_PATTERN.fullmatch(
            value["operation_ref"]) is None):
        raise ValueError
    if (action == "forge.recheck"
            and PROPOSAL_REF_PATTERN.fullmatch(value["prp_id"]) is None):
        raise ValueError
    if "arguments" in value and type(value["arguments"]) is not dict:
        raise ValueError
