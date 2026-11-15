"""Compute-lease receipts: paid GPU / cluster work is an accountable external write.

Harvest of research/rl-scaling-receipt-spine.md Lane 3: treat paid GPU jobs and
cluster workers as external writes with idempotency keys, budget refs, queue ids,
and terminal status. Modeled as an optional compute_lease on an external/
irreversible side-effect -- a lease on a read is an error.
"""

from __future__ import annotations

from proof_surface.agent_action import (
    build_agent_action_packet,
    validate_agent_action_packet,
)

_TRACE = {
    "trace_id": "t1",
    "service": "trainer",
    "spans": [
        {
            "span_id": "s1",
            "name": "gpu.job",
            "attributes": {
                "tool.name": "slurm",
                "action.kind": "submit",
                "action.target": "cluster/gpu-queue",
                "side_effect.class": "external",
            },
        }
    ],
}
_AUTH = {
    "receipt_id": "grant-1",
    "allowed_actions": ["submit"],
    "allowed_targets": ["cluster/gpu-queue"],
}

_LEASE = {
    "budget_ref": "budget:q3-training",
    "queue_id": "slurm-8841",
    "terminal_status": "succeeded",
    "external_request_id": "job-abc123",
}


def _packet():
    return build_agent_action_packet(
        _TRACE, _AUTH, claim="ran a job", scope="demo", packet_id="aa-lease"
    )


def test_compute_lease_on_an_external_side_effect_validates():
    packet = _packet()
    packet["side_effects"][0]["compute_lease"] = dict(_LEASE)
    assert validate_agent_action_packet(packet) == []


def test_unknown_terminal_status_is_rejected():
    packet = _packet()
    lease = dict(_LEASE)
    lease["terminal_status"] = "vibing"
    packet["side_effects"][0]["compute_lease"] = lease
    assert any("compute_lease" in i.path for i in validate_agent_action_packet(packet))


def test_compute_lease_on_a_read_side_effect_is_rejected():
    packet = _packet()
    packet["side_effects"][0]["class"] = "read"
    packet["side_effects"][0]["compute_lease"] = dict(_LEASE)
    assert any("compute_lease" in i.path for i in validate_agent_action_packet(packet))


def test_compute_lease_missing_budget_ref_is_rejected():
    packet = _packet()
    lease = dict(_LEASE)
    del lease["budget_ref"]
    packet["side_effects"][0]["compute_lease"] = lease
    assert any("compute_lease" in i.path for i in validate_agent_action_packet(packet))


def test_compute_lease_is_optional():
    assert validate_agent_action_packet(_packet()) == []
