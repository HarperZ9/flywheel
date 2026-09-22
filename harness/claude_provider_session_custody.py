"""Permission custody helpers for Claude provider-session turns."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def observed_tool_use_ids(event) -> set[str]:
    raw = getattr(event, "raw", None)
    seen: set[str] = set()
    _collect_tool_uses(raw, seen)
    return seen


def control_tool_use_id(control) -> str:
    request = getattr(control, "request", {})
    if not isinstance(request, Mapping):
        return ""
    value = request.get("tool_use_id")
    return value if isinstance(value, str) and value else ""


class ToolUseCustody:
    """One-turn, single-use custody for Claude permission tool ids."""

    def __init__(self, *, allow_unobserved_first: bool):
        self.allow_unobserved_first = allow_unobserved_first
        self.observed: set[str] = set()
        self.pending: set[str] = set()
        self.answered: set[str] = set()

    def observe(self, event) -> None:
        self.observed.update(observed_tool_use_ids(event))

    def admit_control(self, control) -> tuple[bool, str]:
        tool_use_id = control_tool_use_id(control)
        if not tool_use_id:
            return False, "unbound_control_request"
        if tool_use_id in self.pending or tool_use_id in self.answered:
            return False, "duplicate_tool_use_id"
        if tool_use_id not in self.observed and not self.allow_unobserved_first:
            return False, "unbound_control_request"
        self.pending.add(tool_use_id)
        return True, ""

    def answer_control(self, control) -> None:
        tool_use_id = control_tool_use_id(control)
        if tool_use_id:
            self.pending.discard(tool_use_id)
            self.answered.add(tool_use_id)


def _collect_tool_uses(value: Any, seen: set[str]) -> None:
    if isinstance(value, Mapping):
        block_type = value.get("type")
        block_id = value.get("id")
        if block_type == "tool_use" and isinstance(block_id, str) and block_id:
            seen.add(block_id)
        for item in value.values():
            _collect_tool_uses(item, seen)
    elif isinstance(value, list):
        for item in value:
            _collect_tool_uses(item, seen)
