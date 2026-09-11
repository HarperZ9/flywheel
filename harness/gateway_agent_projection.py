"""Content-free public projections of owner-private native agent records."""
from __future__ import annotations

import re

from .evidence_json import canonical_sha256
from .gateway_secret_boundary import validate_no_raw_secrets

SCHEMA = "flywheel.gateway-agent-projection/v1"
OMISSIONS = ["PRIVATE_CONTENT", "CREDENTIAL_VALUES", "UPSTREAM_OUTPUT_LIMITS"]
LIMITS = ["NOT_SEMANTIC_TRUTH", "NOT_UNLIMITED_TOOL_OUTPUT",
          "ACCEPTED_PREFIX_ONLY_UNTIL_COMPLETED"]


def projection(binding: dict, state: str, count: int, head: str,
               *, runtime: dict | None = None, reason: str | None = None) -> dict:
    if state not in {"running", "completed", "failed", "cancelled"}:
        raise ValueError("invalid trace state")
    value = {"schema": SCHEMA, "operation_ref": binding["operation_ref"],
        "journey_ref": binding["journey_ref"], "state": state,
        "trace_ref": binding["trace_ref"], "record_count": count,
        "trace_head_sha256": head, "omissions": list(OMISSIONS),
        "does_not_prove": list(LIMITS)}
    if runtime is not None:
        value["runtime"] = runtime_facts(runtime)
    if reason is not None:
        from .gateway_agent_failures import AGENT_FAILURES
        if reason not in AGENT_FAILURES | {"EXTERNAL_ACTION_FAILED", "OPERATION_INTERRUPTED"}:
            raise ValueError("invalid trace failure")
        value["reason"] = reason
    validate_no_raw_secrets(value)
    value["projection_sha256"] = canonical_sha256(value)
    return value


def runtime_facts(environment: dict) -> dict:
    """Admit typed runtime facts, never arbitrary platform/provider strings."""
    python = environment.get("python")
    platform = environment.get("platform")
    machine = environment.get("machine")
    return {"python": python if type(python) is str and re.fullmatch(
                r"[0-9]{1,2}\.[0-9]{1,2}\.[0-9]{1,3}", python) else None,
            "system": next((name for name in ("Windows", "Linux", "Darwin")
                if type(platform) is str and platform.startswith(name + "-")), None),
            "architecture": machine if machine in (
                "AMD64", "x86_64", "arm64", "aarch64", "x86", "i686") else None}


def validate_projection(value: dict, binding: dict) -> None:
    count, head = value.get("record_count"), value.get("trace_head_sha256")
    if (type(count) is not int or not 0 <= count <= 2048
            or type(head) is not str or re.fullmatch(r"[0-9a-f]{64}", head) is None):
        raise ValueError("invalid trace projection")
    expected = projection(binding, value.get("state"), count, head,
                          reason=value.get("reason"))
    if "runtime" in value:
        facts = value["runtime"]
        if type(facts) is not dict or set(facts) != {"python", "system", "architecture"}:
            raise ValueError("invalid runtime projection")
        checked = runtime_facts({"python": facts["python"],
            "platform": str(facts["system"]) + "-", "machine": facts["architecture"]})
        if facts != checked:
            raise ValueError("invalid runtime projection")
        expected["runtime"] = checked
        expected.pop("projection_sha256")
        expected["projection_sha256"] = canonical_sha256(expected)
    if value != expected:
        raise ValueError("invalid trace projection")
