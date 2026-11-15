"""Evidence references: the action receipt carries the incumbent-system pointers.

Harvest of dogfood pass 0064 ("Required Telos Receipt Fields": trace_refs,
eval_refs, model_refs, runtime_refs). The six trace_adapters evidence importers
emit exactly these native refs; without an evidence_refs block on the packet the
adapter output has nowhere to land. adapter_refs() is the bridge.
"""

from __future__ import annotations

from proof_surface.agent_action import (
    build_agent_action_packet,
    validate_agent_action_packet,
)
from proof_surface.agent_action._evidence import adapter_refs
from proof_surface.trace_adapters import (
    import_braintrust_experiment,
    import_mlflow_run,
)

_HEX = "a" * 64

_TRACE = {
    "trace_id": "t1",
    "service": "svc",
    "spans": [
        {
            "span_id": "s1",
            "name": "http.post",
            "attributes": {
                "tool": "http",
                "action_kind": "write",
                "target": "api/orders",
                "side_effect_class": "external",
            },
        }
    ],
}
_AUTH = {
    "receipt_id": "grant-1",
    "allowed_actions": ["write"],
    "allowed_targets": ["api/orders"],
}


def _packet(evidence_refs=None):
    return build_agent_action_packet(
        _TRACE,
        _AUTH,
        claim="one call",
        scope="demo",
        packet_id="aa-ev",
        evidence_refs=evidence_refs,
    )


def test_adapter_refs_extracts_native_refs_from_an_evidence_import():
    refs = adapter_refs(import_braintrust_experiment({"experiment_id": "e1"}))
    assert {"ref": "braintrust:experiment:e1"} in refs


def test_evidence_refs_from_adapters_validate():
    evidence_refs = {
        "eval_refs": adapter_refs(
            import_braintrust_experiment({"experiment_id": "e1", "eval_ref": "ev1"})
        ),
        "model_refs": adapter_refs(
            import_mlflow_run({"info": {"run_id": "r1"}, "data": {}})
        ),
    }
    packet = _packet(evidence_refs)
    assert validate_agent_action_packet(packet) == []
    assert any(
        r["ref"] == "braintrust:experiment:e1"
        for r in packet["evidence_refs"]["eval_refs"]
    )


def test_evidence_refs_is_optional_and_omitted_by_default():
    packet = _packet()
    assert "evidence_refs" not in packet
    assert validate_agent_action_packet(packet) == []


def test_unknown_evidence_bucket_is_rejected():
    packet = _packet()
    packet["evidence_refs"] = {"telemetry_refs": [{"ref": "x"}]}
    assert any("evidence_refs" in i.path for i in validate_agent_action_packet(packet))


def test_evidence_bucket_must_be_a_list():
    packet = _packet()
    packet["evidence_refs"] = {"trace_refs": {"ref": "otel:trace:t1"}}
    assert any(
        i.path == "$.evidence_refs.trace_refs"
        for i in validate_agent_action_packet(packet)
    )


def test_evidence_ref_bad_sha_is_rejected():
    packet = _packet()
    packet["evidence_refs"] = {
        "runtime_refs": [{"ref": "dvc:stage:train", "sha256": "not-a-digest"}]
    }
    assert any(
        i.path == "$.evidence_refs.runtime_refs[0].sha256"
        for i in validate_agent_action_packet(packet)
    )


def test_evidence_ref_hex_sha_is_accepted():
    packet = _packet({"runtime_refs": [{"ref": "dvc:stage:train", "sha256": _HEX}]})
    assert validate_agent_action_packet(packet) == []
