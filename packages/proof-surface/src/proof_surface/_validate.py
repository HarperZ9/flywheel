"""Shared validation primitives for the proof-surface contract family.

One source of truth for the small hand-rolled, stdlib-only validators used by the
packet, work-record, and witness-receipt contracts. Each validator returns a list
of Issue(path, message); an empty list means valid. additionalProperties:false is
expressed via reject_unknown().
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Issue:
    path: str
    message: str


def reject_unknown(
    data: dict[str, Any], path: str, allowed: set[str], issues: list[Issue]
) -> None:
    for field in sorted(set(data) - allowed):
        issues.append(Issue(f"{path}.{field}", "unexpected field"))


def require_const(
    data: dict[str, Any],
    field: str,
    expected: Any,
    issues: list[Issue],
    path: str | None = None,
) -> None:
    if data.get(field) != expected:
        issues.append(Issue(path or f"$.{field}", f"expected {expected!r}"))


def require_text(
    data: dict[str, Any], field: str, issues: list[Issue], path: str | None = None
) -> None:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        issues.append(Issue(path or f"$.{field}", "expected non-empty string"))


def require_enum(
    data: dict[str, Any],
    field: str,
    allowed: set[str],
    issues: list[Issue],
    path: str | None = None,
) -> None:
    value = data.get(field)
    if value not in allowed:
        choices = ", ".join(sorted(allowed))
        issues.append(Issue(path or f"$.{field}", f"expected one of: {choices}"))
