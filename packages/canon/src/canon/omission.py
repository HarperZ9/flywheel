from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import ClassVar

from .canonical_json import canonical_json_text

OMISSION_SCHEMA = "canon.omission/v1"
OMISSION_REASONS = (
    "budget",
    "secret",
    "unsupported-adapter",
    "policy",
    "source-unavailable",
    "parse-failed",
    "invalid",
    "duplicate",
    "stale",
)
OMISSION_DECISIONS = ("omitted", "fail-build", "reference-only")


@dataclass(frozen=True, slots=True)
class Omission:
    reason: str
    count: int
    affected_ids: tuple[str, ...]
    affected_source_refs: tuple[str, ...]
    critical: bool
    decision: str
    does_not_prove: tuple[str, ...] = ()

    schema: ClassVar[str] = OMISSION_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "affected_ids", _tuple_sequence(self.affected_ids))
        object.__setattr__(self, "affected_source_refs", _tuple_sequence(self.affected_source_refs))
        object.__setattr__(self, "does_not_prove", _tuple_sequence(self.does_not_prove))

    def to_dict(self) -> dict:
        return {
            "schema": OMISSION_SCHEMA,
            "reason": self.reason,
            "count": self.count,
            "affected_ids": _json_sequence(self.affected_ids),
            "affected_source_refs": _json_sequence(self.affected_source_refs),
            "critical": self.critical,
            "decision": self.decision,
            "does_not_prove": _json_sequence(self.does_not_prove),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Omission":
        if not isinstance(d, dict):
            raise TypeError(f"omission JSON must be an object, got {type(d).__name__}")
        got = d.get("schema")
        if got != OMISSION_SCHEMA:
            raise ValueError(f"expected schema {OMISSION_SCHEMA!r}, got {got!r}")
        return cls(
            reason=d["reason"],
            count=d["count"],
            affected_ids=d["affected_ids"],
            affected_source_refs=d["affected_source_refs"],
            critical=d["critical"],
            decision=d["decision"],
            does_not_prove=d.get("does_not_prove", ()),
        )

    def to_json(self) -> str:
        return canonical_json_text(self.to_dict())


def validate_omission(omission: Omission) -> list[str]:
    if not isinstance(omission, Omission):
        return ["omission must be an Omission"]
    problems: list[str] = []
    _check_member("reason", omission.reason, OMISSION_REASONS, problems)
    _check_member("decision", omission.decision, OMISSION_DECISIONS, problems)
    _check_count(omission, problems)
    _check_bool("critical", omission.critical, problems)
    _check_string_tuple("affected_ids", omission.affected_ids, problems)
    _check_string_tuple("affected_source_refs", omission.affected_source_refs, problems)
    _check_string_tuple("does_not_prove", omission.does_not_prove, problems)
    if omission.critical is True and omission.decision == "omitted":
        problems.append('critical omissions cannot use decision "omitted"')
    return problems


def _tuple_sequence(value: object) -> object:
    if isinstance(value, list):
        return tuple(copy.deepcopy(item) for item in value)
    if isinstance(value, tuple):
        return tuple(copy.deepcopy(item) for item in value)
    return copy.deepcopy(value)


def _json_sequence(value: object) -> object:
    if isinstance(value, tuple):
        return [copy.deepcopy(item) for item in value]
    if isinstance(value, list):
        return [copy.deepcopy(item) for item in value]
    return copy.deepcopy(value)


def _check_member(name: str, value: object, allowed: tuple[str, ...], problems: list[str]) -> None:
    if value not in allowed:
        problems.append(f"{name} must be one of {list(allowed)}, got {value!r}")


def _check_count(omission: Omission, problems: list[str]) -> None:
    count = omission.count
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        problems.append("count must be a non-negative int")
        return
    if isinstance(omission.affected_ids, tuple) and omission.affected_ids and count != len(omission.affected_ids):
        problems.append("count must match affected_ids when affected_ids are listed")


def _check_bool(name: str, value: object, problems: list[str]) -> None:
    if not isinstance(value, bool):
        problems.append(f"{name} must be bool")


def _check_string_tuple(name: str, value: object, problems: list[str]) -> None:
    if not isinstance(value, tuple):
        problems.append(f"{name} must be a tuple")
        return
    for index, item in enumerate(value):
        if not isinstance(item, str):
            problems.append(f"{name}[{index}] must be a string")
