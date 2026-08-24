"""Falsifiers for the context-envelope producer (harness/context_envelope.py).

Gap D: the index lane becomes a real catalog inside Flywheel. The producer must
call the index lane, return a project-telos.context-envelope/v1 document, stamp
a stable fingerprint over unchanged content, and degrade to UNVERIFIABLE (never
crash) when the lane is unavailable.
"""
import json
from pathlib import Path

from harness.context_envelope import (
    build_context_envelope, envelope_fingerprint, MATCH, UNVERIFIABLE)

# The index lane rejects a focus that names no real repo, and it answers such a
# request with an `index.focus-rejection/v1` document instead of an envelope. So
# the focus has to name THIS checkout, whatever it is called. Hard-coding
# "local-model" passed only in a checkout of that name: from a git worktree, or
# from a CI runner that checks out to a different directory, every call came
# back a rejection and the schema assertion failed for a reason that had nothing
# to do with the producer.
FOCUS = Path(".").resolve().name
REJECTION = "index.focus-rejection/v1"


def test_envelope_carries_the_context_envelope_schema():
    # lane_timeout is generous on purpose: each call spawns the index MCP
    # server and rescans the workspace, and on a cold or loaded runner that
    # costs far more than a warm local run. The test bounds correctness,
    # not speed.
    env = build_context_envelope(".", budget=400, focus=FOCUS, lane_timeout=180.0)
    # Named separately from the assertion below so a rejection reports itself as
    # a rejection rather than as a mysterious schema mismatch.
    assert env["schema"] != REJECTION, (
        f"the index lane rejected focus {FOCUS!r}; the test is asking about a "
        "repo the lane does not know, not about the producer")
    assert env["schema"] == "project-telos.context-envelope/v1"
    # Either MATCH (lane up) or UNVERIFIABLE (lane down) is honest. Measured
    # 2026-07-28: the main checkout answers MATCH and a worktree answers
    # UNVERIFIABLE, because the lane indexes the former and not the latter.
    assert env["verification_verdict"] in (MATCH, UNVERIFIABLE)


def test_fingerprint_is_stable_across_calls_for_unchanged_content():
    # Two calls over the same workspace + budget + focus must hash identically.
    # The focus is the checkout's own name for the reason above, and this test
    # needs it for a second reason: with an unknown focus both calls returned
    # the SAME rejection document, so the fingerprints matched while the
    # producer was never exercised at all.
    env1 = build_context_envelope(".", budget=400, focus=FOCUS, lane_timeout=180.0)
    env2 = build_context_envelope(".", budget=400, focus=FOCUS, lane_timeout=180.0)
    assert env1["schema"] != REJECTION
    assert envelope_fingerprint(env1) == envelope_fingerprint(env2)


def test_unavailable_lane_is_unverifiable_not_a_crash():
    # Point at a bogus root and a lane command that cannot start; the producer
    # must return UNVERIFIABLE with a failure_code, never raise.
    import harness.lanes as lanes
    from harness.mcp_client import LaunchSpec
    orig = lanes.resolve_mcp_launch
    lanes.resolve_mcp_launch = lambda name: LaunchSpec(
        ("definitely-not-a-real-binary-xyz",))
    try:
        env = build_context_envelope(".", budget=200, lane_timeout=3.0)
    finally:
        lanes.resolve_mcp_launch = orig
    assert env["verification_verdict"] == UNVERIFIABLE
    assert env["failure_code"] == "index_lane_unavailable"
    assert "reason" in env


def test_context_envelope_uses_runtime_launch_spec(monkeypatch):
    import harness.lanes as lanes
    import harness.mcp_client as mcp_client
    from harness.mcp_client import LaunchSpec

    expected = LaunchSpec(("index-runtime",), "/source")
    seen = []

    class UnavailableClient:
        def __init__(self, launch, **kwargs):
            seen.append(launch)

        def __enter__(self):
            raise OSError("offline")

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(lanes, "resolve_mcp_launch", lambda name: expected,
                        raising=False)
    monkeypatch.setattr(lanes, "resolve_mcp_command", lambda name: ["portable"])
    monkeypatch.setattr(mcp_client, "MCPClient", UnavailableClient)
    build_context_envelope(".", lane_timeout=1.0)
    assert seen == [expected]


def test_fingerprint_moves_when_content_shape_changes():
    # An envelope with different retained content must produce a different hash.
    env_a = {"retained_names": ["index", "gather"], "root": "/x", "verification_verdict": MATCH}
    env_b = {"retained_names": ["index", "forum"], "root": "/x", "verification_verdict": MATCH}
    assert envelope_fingerprint(env_a) != envelope_fingerprint(env_b)
