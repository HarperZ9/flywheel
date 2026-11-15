from __future__ import annotations

from dataclasses import dataclass

SEVERITY_ORDER = {"info": 0, "warning": 1, "error": 2}


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    severity: str
    message: str


@dataclass(frozen=True)
class SweepSummary:
    score: int
    status: str
    total_findings: int
    errors: int
    warnings: int
    action_items: list[str]
