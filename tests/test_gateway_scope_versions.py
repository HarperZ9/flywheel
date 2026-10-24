"""Gateway records written before the scope migration still validate.

The v1 projection and effect-evidence records name their list with the older
key and keep their v1 entries; v2 records name it `scope`. Each version is read
with its own vocabulary, and a record that mixes them fails.
"""
import json
from pathlib import Path

import pytest

from harness.evidence_json import canonical_sha256
from harness.gateway_agent_projection import (
    SCHEMA, SCHEMA_V1, SCOPE, projection, validate_projection)
from harness.gateway_agent_trace import AgentTrace, TraceLedger
from harness.gateway_effect_evidence import (
    SCHEMA as EFFECT_V2, SCHEMA_V1 as EFFECT_V1, EffectEvidenceError,
    derive_effect_evidence, validate_effect_evidence)
from harness.scope import LEGACY_SCOPE_KEY

FIXTURES = Path(__file__).parent / "fixtures"
OWNER, JOURNEY, OP = "owner_" + "a" * 32, "jrn_" + "b" * 32, "op_" + "c" * 32


def _binding(value):
    return {k: value[k] for k in ("operation_ref", "journey_ref", "trace_ref")}


@pytest.mark.parametrize("name", ["cancelled", "completed", "failed", "running"])
def test_kept_v1_projection_fixtures_still_validate(name):
    value = json.loads((FIXTURES / "native_agent_trace" / f"{name}.json")
                       .read_text(encoding="utf-8"))
    assert value["schema"] == SCHEMA_V1 and LEGACY_SCOPE_KEY in value
    base = {k: v for k, v in value.items()
            if k not in {"effect_evidence", "run_outcome", "projection_sha256"}}
    base["projection_sha256"] = canonical_sha256(base)
    validate_projection(base, _binding(value))


def test_v2_projection_names_scope_and_rejects_the_older_key():
    binding = {"operation_ref": OP, "journey_ref": JOURNEY, "trace_ref": "agt_" + "d" * 32}
    value = projection(binding, "completed", 0, "e" * 64)
    assert value["schema"] == SCHEMA and value["scope"] == SCOPE
    assert LEGACY_SCOPE_KEY not in value
    mixed = dict(value)
    mixed[LEGACY_SCOPE_KEY] = mixed.pop("scope")
    mixed.pop("projection_sha256")
    mixed["projection_sha256"] = canonical_sha256(mixed)
    with pytest.raises(ValueError):
        validate_projection(mixed, binding)


def test_effect_evidence_v1_recomputes_and_v2_carries_scope_label(tmp_path):
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, OP)
    TraceLedger(trace).append("tool_result", "private", {
        "tool": "write_file", "ok": True, "edited": {"a.txt": "a" * 64}})
    args = {"trace_ref": trace.ref, "terminal_state": "cancelled",
            "terminal_basis_event_type": "cancel_requested",
            "terminal_basis_event_sha256": "d" * 64}
    records = trace.read()
    new = derive_effect_evidence(records, **args)
    assert new["schema"] == EFFECT_V2
    assert new["scope_label"] == "owner_private_trace_prefix" and new["scope"]
    old = derive_effect_evidence(records, schema=EFFECT_V1, **args)
    assert old["scope"] == "owner_private_trace_prefix" and old[LEGACY_SCOPE_KEY]
    validate_effect_evidence(records, submitted=old, **args)
    validate_effect_evidence(records, submitted=new, **args)
    mixed = dict(old, schema=EFFECT_V2)
    with pytest.raises(EffectEvidenceError):
        validate_effect_evidence(records, submitted=mixed, **args)


def test_a_v1_runner_context_still_hands_off():
    from harness.continuation_agent_handoff import _runner
    from harness.continuation_context import RUNNER_CONTEXT_SCHEMA_V1
    runner = {"schema": RUNNER_CONTEXT_SCHEMA_V1, "root": "r", "goal": "g",
              "selected_files": [], LEGACY_SCOPE_KEY: ["selected context is complete"]}
    assert _runner({"runner_context": runner}) is runner
