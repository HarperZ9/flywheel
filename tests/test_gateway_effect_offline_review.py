from __future__ import annotations

import json

import pytest

from harness.evidence_json import canonical_sha256
from harness.gateway_agent_trace import AgentTrace, TraceLedger
from harness.gateway_effect_offline import (
    build_gateway_effect_component,
    trace_export_preview,
    verify_gateway_effect_component,
)
from harness.gateway_operation_process import WorkerOutcome
from harness.gateway_operations import cancel_operation, start_operation
from harness.gateway_operation_recovery import LIFECYCLE
from tests.test_gateway_operations import (
    Factory,
    JOURNEY,
    OWNER,
    Process,
    _authorized,
    _cancel_raw,
    _service,
)
from tests.test_gateway_operation_recovery import OPERATION, _events, _queued, _started


def _lifecycle(root, ref):
    return [
        event for event in _events(root)
        if event["event_type"] in LIFECYCLE
        and event["payload"].get("operation_ref") == ref
    ]


def _expected(component):
    hashes = component["packet_local_sha256"]
    return {
        "terminal_result_sha256": hashes["terminal_result"],
        "lifecycle_history_sha256": hashes["lifecycle_history"],
        "trace_records_sha256": hashes["trace_records"],
        "reference_provenance": "test controlled source",
    }


def _append_records(trace, count=1, prefix="a"):
    ledger = TraceLedger(trace)
    for index in range(count):
        ledger.append("tool_result", "private result", {
            "tool": "write_file",
            "ok": True,
            "edited": {f"{prefix}-{index}.txt": f"{index + 1}" * 64},
        })


def _component(root, state="completed", *, count=1, prefix="a"):
    if state in {"completed", "failed"}:
        _started(root, _queued(root))
        ref = OPERATION
        trace = AgentTrace(root, OWNER, JOURNEY, ref)
        _append_records(trace, count=count, prefix=prefix)
        service = _service(root)
        result = {"reason": "EXTERNAL_ACTION_FAILED"} if state == "failed" else trace.projection(state)
        service._terminal(OWNER, ref, WorkerOutcome(state, result))
    else:
        process = Process()
        service = _service(root)
        queued = start_operation(
            authorized=_authorized(root),
            service=service,
            process_factory=Factory(process, root),
        )
        assert process.resumed.wait(10), "worker never resumed"
        ref = queued.operation_ref
        trace = AgentTrace(root, OWNER, JOURNEY, ref)
        _append_records(trace, count=count, prefix=prefix)
        cancel_operation(
            action="operation.cancel",
            raw=_cancel_raw(service.snapshot(OWNER, ref), ref),
            owner_ref=OWNER,
            service=service,
        )
    terminal_result = service.result(OWNER, ref)
    records = trace.read()
    return build_gateway_effect_component(
        terminal_result=terminal_result,
        lifecycle_history=_lifecycle(root, ref),
        trace_records=records,
    ), terminal_result, records


@pytest.mark.parametrize("state", ["completed", "failed", "cancelled"])
def test_live_gateway_effect_component_verifies_all_terminal_states(tmp_path, state):
    component, _terminal, _records = _component(tmp_path, state, prefix=state)

    result = verify_gateway_effect_component(
        component, expected_hashes=_expected(component))

    assert result["internal_consistency"]["verdict"] == "MATCH"
    assert result["expected_correspondence"]["verdict"] == "MATCH"
    assert result["effect_coverage"]["retained_observations"] == 1
    assert result["effect_coverage"]["known_observations"][0]["record_sha256"]
    assert result["effect_coverage"]["known_observations"][0]["json_pointer"] == "/payload/meta/edited"
    assert result["semantic_correctness"]["verdict"] == "UNVERIFIABLE"
    assert "NOT_EFFECT_ABSENCE" in result["effect_coverage"]["unobserved_scope"]
    assert f"{state}-0.txt" not in json.dumps(component["trace_preview"])


def test_missing_gateway_effect_is_unavailable_not_no_effect():
    result = verify_gateway_effect_component(None)

    assert result["verdict"] == "UNAVAILABLE"
    assert result["effect_coverage"]["verdict"] == "UNAVAILABLE"
    assert "no gateway_effect component" in result["effect_coverage"]["limits"][0]


@pytest.mark.parametrize("mutation", ["removed", "reordered"])
def test_removed_or_reordered_trace_records_fail_against_terminal_binding(tmp_path, mutation):
    component, terminal_result, records = _component(tmp_path, count=2)
    changed = records[1:] if mutation == "removed" else list(reversed(records))

    bad = build_gateway_effect_component(
        terminal_result=terminal_result,
        lifecycle_history=component["lifecycle_history"],
        trace_records=changed,
    )
    result = verify_gateway_effect_component(bad)

    assert result["internal_consistency"]["verdict"] == "DRIFT"


def test_mixed_identity_trace_records_fail_even_when_records_are_valid(tmp_path):
    component, terminal_result, _records = _component(tmp_path / "main")
    other_root = tmp_path / "other"
    other_root.mkdir()
    other = AgentTrace(other_root, "owner_" + "b" * 32, JOURNEY, OPERATION)
    _append_records(other, prefix="other")

    bad = build_gateway_effect_component(
        terminal_result=terminal_result,
        lifecycle_history=component["lifecycle_history"],
        trace_records=other.read(),
    )
    result = verify_gateway_effect_component(bad)

    assert result["internal_consistency"]["verdict"] == "DRIFT"


def test_redacted_trace_record_does_not_inherit_exactness(tmp_path):
    component, terminal_result, records = _component(tmp_path)
    redacted = [dict(records[0], payload={"redacted": True})]

    bad = build_gateway_effect_component(
        terminal_result=terminal_result,
        lifecycle_history=component["lifecycle_history"],
        trace_records=redacted,
    )
    result = verify_gateway_effect_component(bad)

    assert result["internal_consistency"]["verdict"] == "DRIFT"


def test_preview_buckets_unknown_kind_without_echoing_submitted_label():
    preview = trace_export_preview([{
        "schema": "flywheel.gateway-agent-record/v1",
        "kind": "secret-kind-from-private-trace",
        "payload": {"content": "private"},
    }])

    encoded = json.dumps(preview)
    assert "secret-kind-from-private-trace" not in encoded
    assert preview["record_kinds"] == {"malformed": 1}
    assert "MALFORMED" in preview["sensitive_payload_categories"]


def test_coherent_rewrite_needs_separate_expected_hashes_to_drift(tmp_path):
    original, _terminal, _records = _component(tmp_path / "original", prefix="old")
    rewritten, _terminal2, _records2 = _component(tmp_path / "rewritten", prefix="new")

    packet_only = verify_gateway_effect_component(rewritten)
    compared = verify_gateway_effect_component(
        rewritten, expected_hashes=_expected(original))

    assert packet_only["internal_consistency"]["verdict"] == "MATCH"
    assert packet_only["expected_correspondence"]["verdict"] == "UNAVAILABLE"
    assert compared["internal_consistency"]["verdict"] == "MATCH"
    assert compared["expected_correspondence"]["verdict"] == "DRIFT"


def test_corrupt_optional_canonical_base64_fails_after_component_rehash(tmp_path):
    component, _terminal, _records = _component(tmp_path)
    component["trace_record_canonical_base64"][0]["canonical_base64"] = "not base64!"
    body = {key: value for key, value in component.items() if key != "component_sha256"}
    component["component_sha256"] = canonical_sha256(body)

    result = verify_gateway_effect_component(component)

    assert result["internal_consistency"]["verdict"] == "DRIFT"

def test_coherently_rehashed_projection_must_keep_canonical_limits(tmp_path):
    component, _terminal, _records = _component(tmp_path)
    projection = component["terminal_result"]["result"]
    projection.pop("omissions")
    projection.pop("does_not_prove")
    projection["claims_execution_truth"] = True
    projection.pop("projection_sha256")
    projection["projection_sha256"] = canonical_sha256(projection)
    terminal = component["terminal_result"]
    terminal_event = component["lifecycle_history"][-1]
    terminal_event["payload"]["result_sha256"] = canonical_sha256(terminal)
    terminal_event["event_sha256"] = canonical_sha256({
        key: value for key, value in terminal_event.items()
        if key != "event_sha256"
    })
    component["packet_local_sha256"]["terminal_result"] = canonical_sha256(terminal)
    component["packet_local_sha256"]["lifecycle_history"] = canonical_sha256(
        component["lifecycle_history"])
    body = {key: value for key, value in component.items()
            if key != "component_sha256"}
    component["component_sha256"] = canonical_sha256(body)

    result = verify_gateway_effect_component(component)

    assert result["internal_consistency"]["verdict"] == "DRIFT"
