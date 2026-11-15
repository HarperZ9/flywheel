"""Typed failure codes: negative signals are first-class, not prose.

Harvest of research/rl-scaling-receipt-spine.md and mycology-network-intelligence.md
-- both independently require distinct typed codes for negative signals (missing
evidence, stale criteria, unjoinable action identity, failed route, unverifiable
claims) instead of prose-only failures. A failure_labels entry MUST be a known
code so a checker can branch on the failure class deterministically.
"""

from __future__ import annotations

from proof_surface._failure import FAILURE_CODES, validate_failure_labels
from proof_surface._validate import Issue
from proof_surface.agent_action import (
    build_agent_action_packet,
    validate_agent_action_packet,
)

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


def _packet(failure_labels=None):
    return build_agent_action_packet(
        _TRACE,
        _AUTH,
        claim="one call",
        scope="demo",
        packet_id="aa-fail",
        failure_labels=failure_labels,
    )


def test_vocabulary_covers_the_research_named_codes():
    for code in (
        "binding_failed",
        "unjoinable_action",
        "verification_unverifiable",
        "stale_criterion",
        "authority_gap",
        "evidence_gap",
        "duplicate_idempotency_key",
        "external_request_id_missing",
        "failed_route",
    ):
        assert code in FAILURE_CODES


def test_validator_accepts_known_codes():
    issues: list[Issue] = []
    validate_failure_labels(["evidence_gap", "stale_criterion"], issues)
    assert issues == []


def test_validator_rejects_an_unknown_code():
    issues: list[Issue] = []
    validate_failure_labels(["kinda_broke"], issues)
    assert len(issues) == 1
    assert "kinda_broke" in issues[0].message


def test_validator_rejects_a_non_string_entry():
    issues: list[Issue] = []
    validate_failure_labels([{"code": "evidence_gap"}], issues)
    assert issues  # unhashable / non-str must not crash and must be rejected


def test_validator_none_and_missing_are_fine():
    issues: list[Issue] = []
    validate_failure_labels(None, issues)
    assert issues == []


def test_packet_with_typed_failures_validates():
    packet = _packet(["evidence_gap", "verification_unverifiable"])
    assert validate_agent_action_packet(packet) == []
    assert packet["failure_labels"] == ["evidence_gap", "verification_unverifiable"]


def test_failure_labels_omitted_by_default():
    packet = _packet()
    assert "failure_labels" not in packet
    assert validate_agent_action_packet(packet) == []


def test_packet_with_unknown_failure_code_is_rejected():
    packet = _packet()
    packet["failure_labels"] = ["totally_made_up"]
    assert any(
        i.path.startswith("$.failure_labels")
        for i in validate_agent_action_packet(packet)
    )
