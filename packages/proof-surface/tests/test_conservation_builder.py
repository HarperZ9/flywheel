"""Conservation wedge: an invariant check must be able to fail on a known-bad input.

Harvest of dogfood passes 0105/0106/0107 (mass-conservation, stoichiometric
invariant, reaction-network corpus -- three converging implemented artifacts).
A claimed transformation must conserve a declared invariant, proven by
independent witnesses AND falsified by a REQUIRED negative fixture that must
break it. A verifier that can't fail on a known-bad input is not a verifier.
"""

from __future__ import annotations

from proof_surface.conservation import (
    build_conservation_packet,
    validate_conservation_packet,
)

_HEX = "a" * 64


def _packet(*, witnesses=None, negative_fixture=None):
    return build_conservation_packet(
        sources=[{"ref": "dogfood:pass-0106", "sha256": _HEX}],
        transformation={
            "description": "closed reaction network A<->B",
            "domain": "chemistry",
        },
        invariant={"name": "total mass", "declared": "sum of species amounts"},
        witnesses=witnesses
        if witnesses is not None
        else [
            {
                "kind": "algebraic",
                "drift": 0.0,
                "tolerance": 1e-12,
                "method": "l^T S == 0",
            },
            {
                "kind": "numeric",
                "drift": 4e-15,
                "tolerance": 1e-10,
                "method": "euler integrate",
            },
        ],
        negative_fixture=negative_fixture
        if negative_fixture is not None
        else {
            "description": "leaky open network",
            "drift": 0.456,
            "tolerance": 0.01,
            "breaks_invariant": True,
        },
        claim="closed network conserves total mass",
        scope="one reaction network",
        packet_id="cons-1",
    )


def test_conserved_with_breaking_fixture_is_a_match():
    packet = _packet()
    assert validate_conservation_packet(packet) == []
    assert packet["verdicts"]["overall"] == "MATCH"


def test_a_failing_witness_is_a_drift():
    packet = _packet(
        witnesses=[
            {"kind": "numeric", "drift": 0.3, "tolerance": 1e-10, "method": "euler"}
        ]
    )
    assert packet["verdicts"]["overall"] == "DRIFT"
    assert validate_conservation_packet(packet) == []


def test_non_breaking_negative_fixture_is_rejected():
    # A "check" whose negative fixture does not break has no discriminating power.
    packet = _packet(
        negative_fixture={
            "description": "supposedly bad",
            "drift": 0.0,
            "tolerance": 0.01,
            "breaks_invariant": False,
        }
    )
    assert any(
        "negative_fixture" in i.path for i in validate_conservation_packet(packet)
    )


def test_fixture_claiming_break_but_within_tolerance_is_rejected():
    # breaks_invariant=True but drift <= tolerance is a contradiction.
    packet = _packet(
        negative_fixture={
            "description": "claims to break",
            "drift": 0.005,
            "tolerance": 0.01,
            "breaks_invariant": True,
        }
    )
    assert any(
        "negative_fixture" in i.path for i in validate_conservation_packet(packet)
    )


def test_no_witnesses_is_rejected():
    packet = _packet(witnesses=[])
    assert any("witnesses" in i.path for i in validate_conservation_packet(packet))


def test_unknown_witness_kind_is_rejected():
    packet = _packet(
        witnesses=[{"kind": "vibes", "drift": 0.0, "tolerance": 1e-9, "method": "m"}]
    )
    assert any(
        "witnesses[0].kind" in i.path for i in validate_conservation_packet(packet)
    )
