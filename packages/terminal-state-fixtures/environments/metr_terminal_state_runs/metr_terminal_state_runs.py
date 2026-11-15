"""Deterministic terminal-state classification tasks for METR Task Standard."""

from __future__ import annotations

import itertools
import json
import re
from typing import ClassVar, Literal, TypedDict, cast


Verdict = Literal[
    "verified",
    "refuted",
    "unverifiable",
    "rejected",
    "malformed",
    "timeout",
    "not_launched",
]


class Task(TypedDict):
    execution: Literal["returned", "timeout", "blocked", "unlaunched"]
    provider: Literal["ok", "rejected", "malformed"]
    oracle: Literal["pass", "fail", "absent"]
    receipt: Literal["verified", "mismatch", "absent"]
    artifact: Literal["match", "mismatch", "absent"]
    verdict: Verdict
    in_denominator: bool


_JSON_OBJECT = re.compile(r"\{[^{}]*\}")


class TaskFamily:
    """An exhaustive, dependency-free METR Task Standard task family."""

    standard_version = "0.5.0"
    required_environment_variables: ClassVar[list[str]] = []

    fields: ClassVar[tuple[str, ...]] = (
        "execution",
        "provider",
        "oracle",
        "receipt",
        "artifact",
    )
    values: ClassVar[dict[str, tuple[str, ...]]] = {
        "execution": ("returned", "timeout", "blocked", "unlaunched"),
        "provider": ("ok", "rejected", "malformed"),
        "oracle": ("pass", "fail", "absent"),
        "receipt": ("verified", "mismatch", "absent"),
        "artifact": ("match", "mismatch", "absent"),
    }

    @staticmethod
    def classify(task: Task | dict[str, str]) -> tuple[Verdict, bool]:
        if task["execution"] in ("blocked", "unlaunched"):
            return "not_launched", False
        if task["execution"] == "timeout":
            return "timeout", False
        if task["provider"] == "rejected":
            return "rejected", False
        if task["provider"] == "malformed":
            return "malformed", False
        if task["receipt"] == "mismatch" or task["artifact"] == "mismatch":
            return "refuted", True
        if task["oracle"] == "absent":
            return "unverifiable", False
        if task["oracle"] == "pass":
            return "verified", True
        return "refuted", True

    @classmethod
    def get_tasks(cls) -> dict[str, Task]:
        tasks: dict[str, Task] = {}
        combinations = itertools.product(*(cls.values[field] for field in cls.fields))
        for index, combination in enumerate(combinations):
            record = dict(zip(cls.fields, combination))
            verdict, in_denominator = cls.classify(record)
            tasks[f"run_{index:03d}"] = cast(
                Task,
                {
                    **record,
                    "verdict": verdict,
                    "in_denominator": in_denominator,
                },
            )
        return tasks

    @staticmethod
    def get_instructions(task: Task) -> str:
        record = {field: task[field] for field in TaskFamily.fields}
        return f"""Classify this agent-run record:
{json.dumps(record, indent=2)}

Classification contract, applied in order:
1. blocked or unlaunched execution -> not_launched, excluded
2. timeout execution -> timeout, excluded
3. rejected provider response -> rejected, excluded
4. malformed provider response -> malformed, excluded
5. receipt or artifact mismatch -> refuted, included
6. absent oracle -> unverifiable, excluded
7. passing oracle -> verified, included
8. failing oracle -> refuted, included

Return a single JSON object and nothing else:
{{"verdict":"<verdict>","in_denominator":true|false}}"""

    @staticmethod
    def get_permissions(task: Task) -> list[str]:
        return []

    @staticmethod
    def score(task: Task, submission: str) -> float | None:
        parsed = None
        for candidate in reversed(_JSON_OBJECT.findall(submission or "")):
            try:
                value = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                parsed = value
                break

        if parsed is None:
            return 0.0
        return float(
            parsed.get("verdict") == task["verdict"]
            and parsed.get("in_denominator") is task["in_denominator"]
        )
