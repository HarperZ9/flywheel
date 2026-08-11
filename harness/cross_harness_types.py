"""Typed boundary between cross-harness orchestration and adapters."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class AttemptRequest:
    run_id: str
    phase: str
    task_set_id: str
    task_id: str
    prompt: str
    raw_prompt_sha256: str
    provider_role: str
    harness_id: str
    adapter_id: str
    model_id: str
    workspace_root: Path
    workspace_snapshot_sha256: str
    input_sha256s: dict[str, str]
    tool_policy: dict[str, Any]
    tool_policy_sha256: str
    repetition: int
    cache_state: str
    timeout_seconds: int
    artifact_dir: Path


@dataclass(frozen=True)
class AvailabilityResult:
    available: bool
    failure_class: str
    detail: str
    evidence: dict[str, Any]


@dataclass(frozen=True)
class EnforcementResult:
    description: dict[str, Any]
    description_sha256: str
    verification_state: str
    equivalence_class: str


@dataclass(frozen=True)
class AdapterResult:
    execution_state: str
    output_text: str
    tool_trace: list[dict[str, Any]]
    elapsed_ms: int
    model_observed: str
    randomness_control: str
    failure_class: str
    failure_detail: str
    resource_observation: dict[str, Any]
    usage: dict[str, Any]
    observed_capabilities: list[str]
    policy_violations: list[str]


class CrossHarnessAdapter(Protocol):
    role: str
    adapter_id: str

    def enforcement(self, request: AttemptRequest) -> EnforcementResult: ...
    def availability(self, request: AttemptRequest) -> AvailabilityResult: ...
    def execute(self, request: AttemptRequest) -> AdapterResult: ...
