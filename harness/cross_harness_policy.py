"""Shared tool-policy identity for cross-harness attempts."""
from __future__ import annotations
from typing import Any

SHARED_TOOL_POLICY = {
    "version": "cross-harness-read-only/v1", "allow_read": True,
    "allow_write": False, "allow_exec": False, "allow_mcp": False,
    "max_steps": 6, "max_output_tokens": 2048,
}
COMPACT_BUDGET_ADAPTER_IDS = frozenset({"flywheel_router/v1", "openai_compatible_local/v1"})
COMPACTION_RECEIPT_NUMERIC_KEYS = frozenset({"token_budget", "tokens_before", "tokens_after", "budget_floor_tokens"})
def nonnegative_policy_int(policy: dict[str, Any], key: str, default: int = 0) -> int:
    value = policy.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0: raise ValueError(f"{key} must be a non-negative integer")
    return value
def tool_policy_for(*, compact_budget: int = 0) -> dict[str, Any]:
    policy = dict(SHARED_TOOL_POLICY); compact_budget = nonnegative_policy_int({"compact_budget": compact_budget}, "compact_budget")
    if compact_budget: policy["compact_budget"] = compact_budget
    return policy
def compaction_receipt_numeric_allowed(schema: Any, key: str, value: Any) -> bool:
    return schema == "flywheel.compaction/v1" and key in COMPACTION_RECEIPT_NUMERIC_KEYS and type(value) is int and value >= 0
def attempt_metrics(elapsed_ms: int, usage: dict[str, Any], resource: Any, policy: dict[str, Any],
                    adapter_id: str = "") -> dict[str, Any]:
    metrics = {"latency_ms": elapsed_ms, "usage": usage, "resource_observation": resource}
    compact_supported = not adapter_id or adapter_id in COMPACT_BUDGET_ADAPTER_IDS
    if "compact_budget" in policy:
        metrics["compact_budget_requested"] = policy["compact_budget"]
        metrics["compact_budget_control_state"] = "requested"
        if not compact_supported:
            metrics["compact_budget_control_state"] = "unsupported_adapter"
    if isinstance(resource, dict):
        if "compact_budget" in resource and compact_supported:
            metrics["compact_budget"] = resource["compact_budget"]
            metrics["compact_budget_control_state"] = "applied"
        elif "compact_budget" in resource: metrics["compact_budget_reported_unsupported"] = resource["compact_budget"]
        if "last_compaction" in resource and compact_supported: metrics["last_compaction"] = resource["last_compaction"]
        elif "last_compaction" in resource: metrics["last_compaction_reported_unsupported"] = resource["last_compaction"]
    return metrics
