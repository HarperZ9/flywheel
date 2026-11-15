"""Boundary fixture: sufficient is not necessary (no biconditional overclaim).

Harvest of dogfood pass 0108 (Detailed-Balance Markov Receipt). Its
`stationary_not_reversible` fixture shows the goal (stationarity) holding while
the claimed condition (detailed balance / reversibility) fails -- proving the
condition is sufficient but NOT necessary. The optional boundary_fixture makes
that machine-checkable so a packet can't overclaim "condition <=> goal".
"""

from __future__ import annotations

from proof_surface.conservation import (
    build_conservation_packet,
    validate_conservation_packet,
)

_HEX = "a" * 64


def _packet(boundary_fixture=None):
    packet = build_conservation_packet(
        sources=[{"ref": "dogfood:pass-0108", "sha256": _HEX}],
        transformation={
            "description": "reversible Markov kernel",
            "domain": "stochastic",
        },
        invariant={"name": "stationarity", "declared": "pi P = pi"},
        witnesses=[
            {
                "kind": "algebraic",
                "drift": 0.0,
                "tolerance": 1e-12,
                "method": "detailed balance residual",
            },
            {
                "kind": "numeric",
                "drift": 9e-16,
                "tolerance": 1e-10,
                "method": "L1 to pi after 200 steps",
            },
        ],
        negative_fixture={
            "description": "row_stochastic_not_stationary",
            "drift": 0.2,
            "tolerance": 0.01,
            "breaks_invariant": True,
        },
        claim="detailed balance implies stationarity",
        scope="one finite kernel",
        packet_id="cons-db",
    )
    if boundary_fixture is not None:
        packet["boundary_fixture"] = boundary_fixture
    return packet


def test_valid_boundary_fixture_validates():
    # stationary (goal) but not reversible (condition) -> sufficient, not necessary.
    packet = _packet(
        {
            "description": "stationary_not_reversible",
            "goal_holds": True,
            "condition_holds": False,
        }
    )
    assert validate_conservation_packet(packet) == []


def test_boundary_fixture_is_optional():
    assert validate_conservation_packet(_packet()) == []
    assert "boundary_fixture" not in _packet()


def test_boundary_fixture_where_goal_fails_is_rejected():
    # If the goal does not hold, it is a negative case, not a sufficiency boundary.
    packet = _packet(
        {"description": "x", "goal_holds": False, "condition_holds": False}
    )
    assert any(
        "boundary_fixture" in i.path for i in validate_conservation_packet(packet)
    )


def test_boundary_fixture_where_condition_also_holds_is_rejected():
    # If the condition also holds, it demonstrates nothing about necessity.
    packet = _packet({"description": "x", "goal_holds": True, "condition_holds": True})
    assert any(
        "boundary_fixture" in i.path for i in validate_conservation_packet(packet)
    )


def test_boundary_fixture_flags_must_be_boolean():
    packet = _packet(
        {"description": "x", "goal_holds": "yes", "condition_holds": False}
    )
    assert any(
        i.path == "$.boundary_fixture.goal_holds"
        for i in validate_conservation_packet(packet)
    )
