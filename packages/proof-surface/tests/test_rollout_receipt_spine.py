"""Rollout spine hardening: verdict consistency + paid-compute accountability.

Audit findings: (1) rollout_receipt carried TWO verdict fields
($.verdicts.overall and $.verifier.verdict) with no consistency rule between
them -- a packet could show a MATCH verifier and a DRIFT overall; (2) the wedge
that IS the paid-GPU domain (RL post-training) had no compute_lease, though the
primitive existed on agent_action. The lease module is now shared spine.
"""

from __future__ import annotations

from proof_surface.rollout_receipt import (
    build_rollout_receipt_packet,
    validate_rollout_receipt_packet,
)

_HEX = "a" * 64

_LEASE = {
    "budget_ref": "budget:q3-training",
    "queue_id": "slurm-8841",
    "terminal_status": "succeeded",
    "external_request_id": "job-abc123",
}


def _packet(**kw):
    return build_rollout_receipt_packet(
        sources=[{"ref": "run:r-42", "sha256": _HEX}],
        rollout={
            "rollout_id": "r-42",
            "policy_ref": "policy:v3",
            "checkpoint_ref": "ckpt:12000",
            "verifier_ref": "verifier:suite",
            "reward_digest": _HEX,
        },
        reward={"score": 0.87},
        verifier={"verdict": "MATCH", "evidence": ["exit 0"]},
        admission={"decision": "allow", "reasons": []},
        claim="c",
        scope="s",
        packet_id="ro",
        **kw,
    )


def test_overall_must_mirror_the_verifier_verdict():
    # The audit hole: MATCH verifier with a hand-edited DRIFT overall.
    packet = _packet()
    packet["verdicts"]["overall"] = "DRIFT"
    assert any(
        i.path == "$.verdicts.overall" for i in validate_rollout_receipt_packet(packet)
    )


def test_builder_derived_verdicts_stay_consistent():
    packet = _packet()
    assert packet["verdicts"]["overall"] == packet["verifier"]["verdict"]
    assert validate_rollout_receipt_packet(packet) == []


def test_compute_lease_on_a_rollout_validates():
    packet = _packet(compute_lease=dict(_LEASE))
    assert packet["compute_lease"]["queue_id"] == "slurm-8841"
    assert validate_rollout_receipt_packet(packet) == []


def test_compute_lease_is_optional():
    packet = _packet()
    assert "compute_lease" not in packet
    assert validate_rollout_receipt_packet(packet) == []


def test_bad_terminal_status_is_rejected():
    lease = dict(_LEASE)
    lease["terminal_status"] = "vibing"
    packet = _packet(compute_lease=lease)
    assert any(
        "compute_lease" in i.path for i in validate_rollout_receipt_packet(packet)
    )


def test_lease_missing_budget_ref_is_rejected():
    lease = dict(_LEASE)
    del lease["budget_ref"]
    packet = _packet(compute_lease=lease)
    assert any(
        "compute_lease" in i.path for i in validate_rollout_receipt_packet(packet)
    )
