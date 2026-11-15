"""Rollout-receipt wedge: RL / post-training runs with default-deny promotion.

Harvest of research/rl-scaling-receipt-spine.md Lanes 1-2: a post-training run
packet (rollout id, policy/checkpoint ref, verifier ref, reward digest, sandbox
receipt, dataset mutation ref) that keeps reward score, verifier verdict,
admission policy, and promotion decision as SEPARATE records. A model is promoted
only if the verifier said MATCH and admission said allow.
"""

from __future__ import annotations

from proof_surface.rollout_receipt import (
    build_rollout_receipt_packet,
    validate_rollout_receipt_packet,
)

_HEX = "a" * 64

_ROLLOUT = {
    "rollout_id": "r-42",
    "policy_ref": "policy:ppo-v3",
    "checkpoint_ref": "ckpt:step-12000",
    "verifier_ref": "verifier:unit-suite",
    "reward_digest": _HEX,
    "sandbox_receipt": "sandbox:run-9",
    "dataset_mutation_ref": "ds:append-77",
}


def _packet(*, verdict="MATCH", admission="allow"):
    return build_rollout_receipt_packet(
        sources=[{"ref": "run:r-42", "sha256": _HEX}],
        rollout=_ROLLOUT,
        reward={"score": 0.87, "model_ref": "model:ppo-v3"},
        verifier={"verdict": verdict, "evidence": ["unit suite exit 0"]},
        admission={"decision": admission, "reasons": []},
        claim="rollout r-42 verified",
        scope="one post-training step",
        packet_id="ro-1",
    )


def test_match_and_allow_derives_promote():
    packet = _packet()
    assert validate_rollout_receipt_packet(packet) == []
    assert packet["verdicts"]["overall"] == "MATCH"
    assert packet["promotion"]["decision"] == "promote"


def test_drift_verifier_derives_reject():
    packet = _packet(verdict="DRIFT")
    assert packet["promotion"]["decision"] == "reject"
    assert validate_rollout_receipt_packet(packet) == []


def test_blocked_admission_never_promotes():
    packet = _packet(admission="block")
    assert packet["promotion"]["decision"] == "reject"


def test_unverifiable_or_escalate_holds():
    assert _packet(verdict="UNVERIFIABLE")["promotion"]["decision"] == "hold"
    assert _packet(admission="escalate")["promotion"]["decision"] == "hold"


def test_hand_forged_promote_without_backing_is_rejected():
    # A packet claiming "promote" on a DRIFT verifier must not validate.
    packet = _packet(verdict="DRIFT")
    packet["promotion"] = {"decision": "promote", "reason": "ship it"}
    assert any("promotion" in i.path for i in validate_rollout_receipt_packet(packet))


def test_reward_digest_must_be_hex():
    packet = _packet()
    packet["rollout"]["reward_digest"] = "not-a-digest"
    assert any(
        "reward_digest" in i.path for i in validate_rollout_receipt_packet(packet)
    )


def test_unknown_admission_decision_is_rejected():
    packet = _packet()
    packet["admission"]["decision"] = "vibe-check"
    assert any("admission" in i.path for i in validate_rollout_receipt_packet(packet))
