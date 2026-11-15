"""Witness tier: no tier inflation past the strongest executed verifier.

Shared-spine gate (src/proof_surface/_witness_tier.py) wired into
research_claim. A packet may declare the verifier tier it targeted, the
strongest tier that actually executed, and whether the target slot ran
(EXECUTED) or honestly did not (tool unavailable / fenced). The gate: the
promotion rung may never exceed the strongest executed tier's rung mapping --
a rung above what actually ran is unwitnessed. Off-ladder honesty rungs
(UNVERIFIABLE, REFUTED) claim no achievement and are never capped.
"""

from __future__ import annotations

from proof_surface.research_claim import (
    build_research_claim_packet,
    validate_research_claim_packet,
)

_HEX = "a" * 64


def _paths(issues):
    return [i.path for i in issues]


def _packet(witness_tier=None, promotion=None, attempts=None):
    packet = build_research_claim_packet(
        statement="for all n >= 1, sum_{k=1}^n k = n(n+1)/2",
        sources=[{"ref": "probe log", "sha256": _HEX}],
        attempts=attempts
        or [{"attempt_id": "a1", "method": "numeric-probe", "result": "bounded"}],
        checks=[
            {"checker": "numeric-probe", "status": "pass", "evidence": ["n=1..1000"]}
        ],
        claim="the identity held under a bounded probe",
        scope="bounded probe; not a general proof",
        packet_id="rc-wt",
        promotion=promotion,
    )
    if witness_tier is not None:
        packet["witness_tier"] = witness_tier
    return packet


def _tier(target, strongest, status):
    return {
        "declared_target_verifier": target,
        "strongest_executed_tier": strongest,
        "target_slot_status": status,
    }


def test_witness_tier_is_optional():
    assert validate_research_claim_packet(_packet()) == []


def test_executed_target_at_matching_rung_validates():
    packet = _packet(
        witness_tier=_tier(
            "crucible-rederivation", "crucible-rederivation", "EXECUTED"
        ),
    )
    # Default derived promotion is CRUCIBLE_MATCH; the tier was actually run.
    assert validate_research_claim_packet(packet) == []


def test_fenced_target_caps_promotion():
    # Declared kernel-proof, only a numeric probe ran: CRUCIBLE_MATCH is inflation.
    packet = _packet(
        witness_tier=_tier("kernel-proof", "numeric-probe", "NOT_EXECUTED_FENCED"),
    )
    issues = validate_research_claim_packet(packet)
    assert any(p == "$.promotion" for p in _paths(issues))


def test_fenced_target_within_cap_validates():
    packet = _packet(
        witness_tier=_tier("kernel-proof", "numeric-probe", "NOT_EXECUTED_FENCED"),
        promotion="PROBE_MATCH",
    )
    assert validate_research_claim_packet(packet) == []


def test_tool_unavailable_caps_promotion():
    packet = _packet(
        witness_tier=_tier(
            "kernel-proof", "manual-review", "NOT_EXECUTED_TOOL_UNAVAILABLE"
        ),
        promotion="PROBE_MATCH",
    )
    issues = validate_research_claim_packet(packet)
    assert any(p == "$.promotion" for p in _paths(issues))


def test_promotion_above_strongest_executed_rejected_even_when_executed():
    # The target ran, but LAW_CANDIDATE outranks what any executed tier witnessed.
    packet = _packet(
        witness_tier=_tier(
            "crucible-rederivation", "crucible-rederivation", "EXECUTED"
        ),
        promotion="LAW_CANDIDATE",
    )
    issues = validate_research_claim_packet(packet)
    assert any(p == "$.promotion" for p in _paths(issues))


def test_off_ladder_unverifiable_is_never_capped():
    packet = _packet(
        witness_tier=_tier("kernel-proof", "none", "NOT_EXECUTED_FENCED"),
        promotion="UNVERIFIABLE",
    )
    assert validate_research_claim_packet(packet) == []


def test_off_ladder_refuted_is_never_capped():
    packet = _packet(
        witness_tier=_tier("kernel-proof", "numeric-probe", "NOT_EXECUTED_FENCED"),
        attempts=[
            {"attempt_id": "a1", "method": "counterexample", "result": "refuted"}
        ],
    )
    # A standing counterexample derives REFUTED; the tier gate must not block it.
    assert packet["promotion"] == "REFUTED"
    assert validate_research_claim_packet(packet) == []


def test_executed_slot_weaker_than_target_is_contradiction():
    packet = _packet(
        witness_tier=_tier("kernel-proof", "numeric-probe", "EXECUTED"),
        promotion="PROBE_MATCH",
    )
    issues = validate_research_claim_packet(packet)
    assert any("witness_tier.strongest_executed_tier" in p for p in _paths(issues))


def test_unknown_tier_rejected():
    packet = _packet(
        witness_tier=_tier("vibes-check", "numeric-probe", "NOT_EXECUTED_FENCED"),
        promotion="PROBE_MATCH",
    )
    issues = validate_research_claim_packet(packet)
    assert any("witness_tier.declared_target_verifier" in p for p in _paths(issues))


def test_unknown_slot_status_rejected():
    packet = _packet(
        witness_tier=_tier("kernel-proof", "numeric-probe", "SORT_OF_RAN"),
        promotion="PROBE_MATCH",
    )
    issues = validate_research_claim_packet(packet)
    assert any("witness_tier.target_slot_status" in p for p in _paths(issues))


def test_unknown_witness_tier_field_rejected():
    tier = _tier("kernel-proof", "numeric-probe", "NOT_EXECUTED_FENCED")
    tier["excuse"] = "ran out of time"
    packet = _packet(witness_tier=tier, promotion="PROBE_MATCH")
    issues = validate_research_claim_packet(packet)
    assert any("witness_tier.excuse" in p for p in _paths(issues))


def test_builder_passes_witness_tier_through():
    tier = _tier("kernel-proof", "numeric-probe", "NOT_EXECUTED_FENCED")
    packet = build_research_claim_packet(
        statement="s",
        sources=[{"ref": "r"}],
        attempts=[{"attempt_id": "a1", "method": "probe", "result": "bounded"}],
        checks=[{"checker": "probe", "status": "pass", "evidence": ["ok"]}],
        claim="c",
        scope="s",
        packet_id="rc-wt-b",
        promotion="PROBE_MATCH",
        witness_tier=tier,
    )
    assert packet["witness_tier"] == tier
    assert validate_research_claim_packet(packet) == []
