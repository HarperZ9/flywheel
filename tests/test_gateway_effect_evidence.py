import copy
import json

import pytest

from harness.evidence_json import canonical_sha256
from harness.gateway_agent_trace import AgentTrace, TraceLedger
from harness.gateway_effect_evidence import (
    EffectEvidenceError,
    derive_effect_evidence,
    validate_effect_evidence,
)

OWNER = "owner_" + "a" * 32
JOURNEY = "jrn_" + "b" * 32
OP = "op_" + "c" * 32
BASIS = "d" * 64


def _trace(tmp_path):
    return AgentTrace(tmp_path, OWNER, JOURNEY, OP)


def _derive(records, trace_ref):
    return derive_effect_evidence(
        records,
        trace_ref=trace_ref,
        terminal_state="cancelled",
        terminal_basis_event_type="cancel_requested",
        terminal_basis_event_sha256=BASIS,
    )


def test_cancelled_terminal_derives_content_free_edit_fingerprint(tmp_path):
    writer = _trace(tmp_path)
    TraceLedger(writer).append("tool_result", "private result", {
        "tool": "write_file", "ok": True,
        "edited": {"example.txt": "a" * 64},
    })
    records = writer.read()

    facts = _derive(records, writer.ref)

    assert facts["known_observation_count"] == 1
    assert facts["known_observations_omitted"] == 0
    observation, = facts["known_observations"]
    assert observation["trace_sequence"] == 0
    assert observation["record_sha256"] == records[0]["record_sha256"]
    assert observation["json_pointer"] == "/payload/meta/edited"
    assert observation["value_sha256"] == canonical_sha256(
        records[0]["payload"]["meta"]["edited"])
    assert "example.txt" not in json.dumps(facts)
    assert "private result" not in json.dumps(facts)
    assert "NOT_CURRENT_FILESYSTEM_STATE" in facts["unknown_effect_scope"]


def test_fabricated_descriptor_fails_against_exact_records(tmp_path):
    writer = _trace(tmp_path)
    writer.append("progress", {"status": "running"})
    records = writer.read()
    submitted = _derive(records, writer.ref)
    submitted["known_observation_count"] = 1
    submitted["known_observations"] = [{
        "kind": "tool_result_edit_fingerprint",
        "trace_sequence": 0,
        "record_sha256": records[0]["record_sha256"],
        "record_kind": "ledger",
        "payload_kind": "tool_result",
        "json_pointer": "/payload/meta/edited",
        "value_sha256": "e" * 64,
    }]
    submitted["known_observations_digest"] = canonical_sha256(
        submitted["known_observations"])

    with pytest.raises(EffectEvidenceError):
        validate_effect_evidence(
            records,
            trace_ref=writer.ref,
            terminal_state="cancelled",
            terminal_basis_event_type="cancel_requested",
            terminal_basis_event_sha256=BASIS,
            submitted=submitted,
        )


def test_omitted_retained_observation_fails_even_when_rehashed(tmp_path):
    writer = _trace(tmp_path)
    ledger = TraceLedger(writer)
    ledger.append("tool_result", "first private result", {
        "tool": "write_file", "ok": True,
        "edited": {"one.txt": "1" * 64},
    })
    ledger.append("tool_result", "second private result", {
        "tool": "edit_file", "ok": True,
        "edited": {"two.txt": "2" * 64},
    })
    records = writer.read()
    submitted = _derive(records, writer.ref)
    submitted["known_observation_count"] = 1
    submitted["known_observations"] = submitted["known_observations"][:1]
    submitted["known_observations_omitted"] = 0
    submitted["known_observations_digest"] = canonical_sha256(
        submitted["known_observations"])

    with pytest.raises(EffectEvidenceError):
        validate_effect_evidence(
            records,
            trace_ref=writer.ref,
            terminal_state="cancelled",
            terminal_basis_event_type="cancel_requested",
            terminal_basis_event_sha256=BASIS,
            submitted=submitted,
        )


@pytest.mark.parametrize("field,value", [
    ("known_observation_count", True),
    ("known_observations_omitted", False),
    ("known_observation_count", 1.0),
])
def test_numeric_type_mutations_fail_canonical_comparison(tmp_path, field, value):
    writer = _trace(tmp_path)
    TraceLedger(writer).append("tool_result", "private result", {
        "tool": "write_file", "ok": True,
        "edited": {"example.txt": "a" * 64},
    })
    records = writer.read()
    submitted = _derive(records, writer.ref)
    submitted[field] = value

    with pytest.raises(EffectEvidenceError):
        validate_effect_evidence(
            records,
            trace_ref=writer.ref,
            terminal_state="cancelled",
            terminal_basis_event_type="cancel_requested",
            terminal_basis_event_sha256=BASIS,
            submitted=submitted,
        )


def test_bool_sequence_is_rejected_before_derivation(tmp_path):
    writer = _trace(tmp_path)
    TraceLedger(writer).append("tool_result", "private result", {
        "tool": "write_file", "ok": True,
        "edited": {"example.txt": "a" * 64},
    })
    records = writer.read()
    records[0] = dict(records[0], sequence=False)

    with pytest.raises(EffectEvidenceError):
        _derive(records, writer.ref)


def test_empty_trace_keeps_unknown_scope(tmp_path):
    writer = _trace(tmp_path)

    facts = _derive(writer.read(), writer.ref)

    assert facts["known_observation_count"] == 0
    assert facts["known_observations"] == []
    assert "NOT_EFFECT_ABSENCE" in facts["unknown_effect_scope"]
    assert "UNRECORDED_ACTIONS_NOT_EXCLUDED" in facts["unknown_effect_scope"]


def test_unsupported_edit_metadata_is_not_echoed_as_an_observation(tmp_path):
    writer = _trace(tmp_path)
    TraceLedger(writer).append("tool_result", "private result", {
        "tool": "write_file", "ok": True,
        "edited": {"secret-name.txt": "not-a-digest"},
    })

    facts = _derive(writer.read(), writer.ref)

    assert facts["known_observation_count"] == 0
    assert facts["known_observations"] == []
    assert "secret-name.txt" not in json.dumps(facts)
    assert "TOOLS_WITHOUT_POST_EFFECT_FINGERPRINTS_REMAIN_UNKNOWN" in (
        facts["unknown_effect_scope"])


@pytest.mark.parametrize("tool_value", [[], {}])
def test_non_string_tool_metadata_is_unrecognized_not_an_exception(tmp_path, tool_value):
    writer = _trace(tmp_path)
    TraceLedger(writer).append("tool_result", "private result", {
        "tool": tool_value, "ok": True,
        "edited": {"secret-name.txt": "a" * 64},
    })

    facts = _derive(writer.read(), writer.ref)

    assert facts["known_observation_count"] == 0
    assert facts["known_observations"] == []
    assert "secret-name.txt" not in json.dumps(facts)


def test_result_witnesses_are_summarized_without_private_records(tmp_path):
    writer = _trace(tmp_path)
    writer.append("result", {
        "action_witness": {
            "schema": "flywheel.byte-witness-chain/v1",
            "count": 2,
            "head_sha256": "e" * 64,
            "records": [{"private": "action detail"}],
            "does_not_prove": ["semantic correctness"],
        },
        "tool_call_receipts": {
            "schema": "flywheel.tool-call-receipt/v1",
            "dir": "private-receipts",
            "count": 3,
            "chain_head_sha256": "f" * 64,
        },
    })

    facts = _derive(writer.read(), writer.ref)

    assert facts["action_witness"] == {
        "status": "present",
        "kind": "reported_action_witness_summary",
        "trace_sequence": 0,
        "record_sha256": writer.head,
        "record_kind": "result",
        "payload_kind": "result",
        "value_sha256": canonical_sha256(
            writer.read()[0]["payload"]["action_witness"]),
        "count": 2,
        "head_sha256": "e" * 64,
        "json_pointer": "/payload/action_witness",
    }
    assert facts["tool_call_receipts"] == {
        "status": "present",
        "kind": "reported_tool_call_receipts_summary",
        "trace_sequence": 0,
        "record_sha256": writer.head,
        "record_kind": "result",
        "payload_kind": "result",
        "value_sha256": canonical_sha256(
            writer.read()[0]["payload"]["tool_call_receipts"]),
        "count": 3,
        "chain_head_sha256": "f" * 64,
        "json_pointer": "/payload/tool_call_receipts",
    }
    assert "action detail" not in json.dumps(facts)
    assert "private-receipts" not in json.dumps(facts)


def test_witness_on_non_result_record_is_not_labeled_as_result_evidence(tmp_path):
    writer = _trace(tmp_path)
    writer.append("progress", {"action_witness": {
        "count": 1, "head_sha256": "b" * 64,
        "records": ["secret-witness-detail"]}})

    facts = _derive(writer.read(), writer.ref)

    assert facts["action_witness"]["status"] == "unavailable"
    assert facts["action_witness"]["reason"] == "UNSUPPORTED_SOURCE_RECORD_KIND"
    assert facts["action_witness"]["record_kind"] == "progress"
    assert "payload_kind" not in facts["action_witness"]
    assert "secret-witness-detail" not in json.dumps(facts)


def test_visible_cap_keeps_total_count_and_digest(tmp_path, monkeypatch):
    import harness.gateway_effect_evidence as module

    monkeypatch.setattr(module, "MAX_VISIBLE_OBSERVATIONS", 1)
    writer = _trace(tmp_path)
    ledger = TraceLedger(writer)
    for index in range(2):
        ledger.append("tool_result", "private", {
            "tool": "write_file", "ok": True,
            "edited": {f"{index}.txt": f"{index}" * 64},
        })
    records = writer.read()

    facts = _derive(records, writer.ref)
    visible_only = copy.deepcopy(facts)
    visible_only["known_observation_count"] = len(
        visible_only["known_observations"])
    visible_only["known_observations_omitted"] = 0
    visible_only["known_observations_digest"] = canonical_sha256(
        visible_only["known_observations"])

    assert facts["known_observation_count"] == 2
    assert facts["known_observations_omitted"] == 1
    with pytest.raises(EffectEvidenceError):
        validate_effect_evidence(
            records,
            trace_ref=writer.ref,
            terminal_state="cancelled",
            terminal_basis_event_type="cancel_requested",
            terminal_basis_event_sha256=BASIS,
            submitted=visible_only,
        )
