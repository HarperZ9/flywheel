"""Typed boundary between cross-harness orchestration and adapters."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
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


_SECRET_KEY = re.compile(r"(?:authorization|credential|password|secret|token|api[_ -]?key)", re.I)
_SECRET_VALUE = re.compile(r"(?i)(authorization\s*:\s*bearer\s+|(?:token|api[_ -]?key|password|secret)\s*[:=]\s*)\S+")


def sanitize_evidence(value: Any) -> Any:
    """Remove secret-shaped keys and reject values canonical JSON cannot encode."""
    if isinstance(value, dict):
        return {str(key): "[REDACTED]" if _SECRET_KEY.search(str(key)) else sanitize_evidence(item)
                for key, item in value.items()}
    if isinstance(value, list): return [sanitize_evidence(item) for item in value]
    if isinstance(value, float) and (value != value or abs(value) == float("inf")): raise ValueError("nonfinite adapter evidence")
    if isinstance(value, str): return _SECRET_VALUE.sub(lambda match: match.group(1) + "[REDACTED]", value)
    return value if isinstance(value, (int, float, bool, type(None))) else sanitize_evidence(str(value))


def validate_elapsed_ms(value: Any) -> int:
    if type(value) is not int or value < 0: raise ValueError("elapsed_ms must be a finite nonnegative integer")
    return value


def metric_null_reasons(metrics: dict[str, Any]) -> dict[str, str]:
    reasons = {}
    if "latency_ms" not in metrics: reasons["latency"] = "attempt_did_not_report_latency"
    if not metrics.get("usage"): reasons["usage"] = "provider_usage_unavailable"
    reasons["cost"] = "provider_cost_unavailable"
    if not metrics.get("resource_observation"): reasons["resource"] = "resource_observation_unavailable"
    return reasons
