"""Falsifiers for the context-envelope producer (harness/context_envelope.py).

Gap D: the index lane becomes a real catalog inside Flywheel. The producer must
call the index lane, return a project-telos.context-envelope/v1 document, stamp
a stable fingerprint over unchanged content, and degrade to UNVERIFIABLE (never
crash) when the lane is unavailable.
"""
import json

from harness.context_envelope import (
    build_context_envelope, envelope_fingerprint, MATCH, UNVERIFIABLE)


def test_envelope_carries_the_context_envelope_schema():
    # The producer is online on this workstation (index lane installed), so a
    # real call should return the v1 schema with a MATCH verdict. Use a real
    # repo name as focus so the index lane returns an envelope, not a focus
    # rejection (index rejects a focus that names no real repo).
    env = build_context_envelope(".", budget=400, focus="local-model", lane_timeout=30.0)
    assert env["schema"] == "project-telos.context-envelope/v1"
    # Either MATCH (lane up) or UNVERIFIABLE (lane down) -- both are honest.
    assert env["verification_verdict"] in (MATCH, UNVERIFIABLE)


def test_fingerprint_is_stable_across_calls_for_unchanged_content():
    # Two calls over the same workspace + budget + focus must hash identically.
    env1 = build_context_envelope(".", budget=400, focus="loop", lane_timeout=30.0)
    env2 = build_context_envelope(".", budget=400, focus="loop", lane_timeout=30.0)
    assert envelope_fingerprint(env1) == envelope_fingerprint(env2)


def test_unavailable_lane_is_unverifiable_not_a_crash():
    # Point at a bogus root and a lane command that cannot start; the producer
    # must return UNVERIFIABLE with a failure_code, never raise.
    import harness.lanes as lanes
    orig = lanes.resolve_mcp_command
    lanes.resolve_mcp_command = lambda name: ["definitely-not-a-real-binary-xyz"]
    try:
        env = build_context_envelope(".", budget=200, lane_timeout=3.0)
    finally:
        lanes.resolve_mcp_command = orig
    assert env["verification_verdict"] == UNVERIFIABLE
    assert env["failure_code"] == "index_lane_unavailable"
    assert "reason" in env


def test_fingerprint_moves_when_content_shape_changes():
    # An envelope with different retained content must produce a different hash.
    env_a = {"retained_names": ["index", "gather"], "root": "/x", "verification_verdict": MATCH}
    env_b = {"retained_names": ["index", "forum"], "root": "/x", "verification_verdict": MATCH}
    assert envelope_fingerprint(env_a) != envelope_fingerprint(env_b)
