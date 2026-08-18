"""Retired prepared-pytest route retained only as a fail-closed entrypoint."""
from __future__ import annotations

from .execution_input_protection import ExecutionInputProtectionUnavailable
from .python_execution_containment import DETAIL, REASON


def verify_prepared(oracle, argv, task, input_refs):
    """Refuse before inspecting inputs or invoking candidate-controlled JUnit."""
    raise ExecutionInputProtectionUnavailable(f"{REASON}: {DETAIL}")
