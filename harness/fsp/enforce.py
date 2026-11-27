"""The enforcement interface between a device model and the work it governs.

``apply`` takes the whole desired state (throughput level, halted workload
tags, failed-closed flag) and returns the halted tags still running. The
demo's implementation governs only child processes the demo started.
"""

from __future__ import annotations

from typing import Protocol


class Enforcer(Protocol):
    def apply(self, state: dict) -> list[str]: ...


class NullEnforcer:
    """Records the state it was asked to apply; used in tests and drills."""

    def __init__(self) -> None:
        self.state = {"level": 100, "halted_tags": set(), "failed_closed": False}
        self.history: list[dict] = []

    def apply(self, state: dict) -> list[str]:
        self.state = {"level": state["level"], "halted_tags": set(state["halted_tags"]),
                      "failed_closed": state["failed_closed"]}
        self.history.append(dict(self.state))
        return []
