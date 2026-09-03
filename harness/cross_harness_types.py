"""Typed boundary between cross-harness orchestration and adapters."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Protocol

MODEL_IDENTITY_FIELDS = ("model_id", "model_display_name", "requested_model_reference", "model_observed", "model_observation_basis")
MODEL_OBSERVATION_BASES = frozenset({"structured_provider_event", "structured_provider_response"})
HISTORICAL_IDENTITY_SCHEMAS = frozenset({"harness.adapter-runtime-matrix/v1", "harness.cross-harness-task-scorecard/v1"})


def model_observation_pair_error(observed: Any, basis: Any) -> str:
    """Return a stable error for an impossible v2 observation attestation pair."""
    if not isinstance(observed, str) or not isinstance(basis, str):
        return "model_observation_pair_not_strings"
    if basis == "unknown":
        return "" if observed == "" else "unknown_observation_must_be_empty"
    if basis in MODEL_OBSERVATION_BASES:
        return "" if observed.strip() else "structured_observation_must_be_nonempty"
    return "unsupported_model_observation_basis"


def project_model_identity(row: dict[str, Any], *, source_schema: str = "") -> dict[str, str]:
    """Project one exact identity shape; ambiguous current/legacy rows fail closed."""
    present = tuple(field for field in MODEL_IDENTITY_FIELDS if field in row)
    if "target_model" in row and present: raise ValueError("mixed legacy and v2 model identity")
    if present and len(present) != len(MODEL_IDENTITY_FIELDS): raise ValueError("partial v2 model identity")
    if present:
        return {"identity_schema": "v2", **{field: str(row.get(field, "")) for field in MODEL_IDENTITY_FIELDS}}
    if "target_model" not in row: raise ValueError("model identity missing")
    schema, legacy = source_schema or str(row.get("schema", "")), row.get("target_model")
    if schema not in HISTORICAL_IDENTITY_SCHEMAS: raise ValueError("historical v1 model identity schema mismatch")
    if not isinstance(legacy, str) or not legacy.strip(): raise ValueError("historical v1 target_model missing")
    return {"identity_schema": "historical_v1", "model_id": legacy, "model_display_name": "",
            "requested_model_reference": legacy, "model_observed": "",
            "model_observation_basis": "historical_v1_unrecorded"}


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
    requested_model_reference: str
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
    model_observation_basis: str = "unknown"


class CrossHarnessAdapter(Protocol):
    role: str
    adapter_id: str

    def enforcement(self, request: AttemptRequest) -> EnforcementResult: ...
    def availability(self, request: AttemptRequest) -> AvailabilityResult: ...
    def execute(self, request: AttemptRequest) -> AdapterResult: ...


_SECRET_KEY = re.compile(r"(?:authorization|credential|password|secret|token|api[_ -]?key)", re.I)
_SECRET_VALUE = re.compile(r"(?i)(authorization\s*:\s*bearer\s+|(?:token|api[_ -]?key|password|secret)\s*[:=]\s*)\S+")
_USAGE_COUNT_KEYS = frozenset({
    "accepted_prediction_tokens", "audio_tokens", "cache_creation_input_tokens",
    "cache_read_input_tokens", "cached_input_tokens", "cached_tokens",
    "completion_tokens", "input_tokens", "output_tokens", "prompt_tokens",
    "reasoning_output_tokens", "reasoning_tokens", "rejected_prediction_tokens",
    "total_tokens",
})
_USAGE_DETAIL_KEYS = frozenset({"input_tokens_details", "output_tokens_details"})


def _usage_secret_field_allowed(key: str, value: Any, in_usage: bool) -> bool:
    return in_usage and ((key in _USAGE_COUNT_KEYS and type(value) is int)
                         or (key in _USAGE_DETAIL_KEYS and isinstance(value, dict)))


def sanitize_evidence(value: Any, _in_usage: bool = False) -> Any:
    """Remove secret-shaped keys and reject values canonical JSON cannot encode.

    Only recognized integer count fields inside a ``usage`` block pass the
    secret-key filter. Numeric credentials and token-shaped fields elsewhere
    still redact; recognized input/output detail objects remain traversable.
    """
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            name = str(key); child_in_usage = _in_usage or name == "usage"
            cleaned[name] = ("[REDACTED]" if _SECRET_KEY.search(name)
                             and not _usage_secret_field_allowed(name, item, _in_usage)
                             else sanitize_evidence(item, child_in_usage))
        return cleaned
    if isinstance(value, list): return [sanitize_evidence(item, _in_usage) for item in value]
    if isinstance(value, float) and (value != value or abs(value) == float("inf")): raise ValueError("nonfinite adapter evidence")
    if isinstance(value, str): return _SECRET_VALUE.sub(lambda match: match.group(1) + "[REDACTED]", value)
    return value if isinstance(value, (int, float, bool, type(None))) else sanitize_evidence(str(value))


def validate_elapsed_ms(value: Any) -> int:
    if type(value) is not int or value < 0: raise ValueError("elapsed_ms must be a finite nonnegative integer")
    return value


def _reported_cost(metrics: dict[str, Any]) -> bool:
    """Did the provider itself put a cost figure on this attempt?

    Only the provider's own number counts. Nothing here prices tokens, so a
    harness that reports no cost keeps its null reason rather than acquiring a
    figure this repository computed for it."""
    observation = metrics.get("resource_observation")
    if not isinstance(observation, dict): return False
    value = observation.get("provider_reported_cost_usd")
    return not isinstance(value, bool) and isinstance(value, (int, float))


def metric_null_reasons(metrics: dict[str, Any]) -> dict[str, str]:
    reasons = {}
    if "latency_ms" not in metrics: reasons["latency"] = "attempt_did_not_report_latency"
    if not metrics.get("usage"): reasons["usage"] = "provider_usage_unavailable"
    if not _reported_cost(metrics): reasons["cost"] = "provider_cost_unavailable"
    if not metrics.get("resource_observation"): reasons["resource"] = "resource_observation_unavailable"
    return reasons
