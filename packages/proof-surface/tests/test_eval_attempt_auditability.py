"""Auditability gate: latent reasoning plus no replay leaves no audit surface.

Harvest of the operator-supplied verification-frontier corpus (LLMs that reason
in latent loops instead of visible chain-of-thought). When the reasoning trace
is not available AND there is no replay ref, a `correct` outcome has nothing an
independent checker can inspect or re-run -- so it may not be scored MATCH.
"""

from __future__ import annotations

from proof_surface.eval_attempt import (
    build_eval_attempt_packet,
    validate_eval_attempt_packet,
)

_HEX = "a" * 64


def _packet(*, trace_available=None, replay_ref="replay:xyz"):
    boundaries = {"had_ground_truth": False, "had_internet": False, "had_tools": True}
    if trace_available is not None:
        boundaries["reasoning_trace_available"] = trace_available
    attempt = {
        "attempt_id": "att-1",
        "prompt_ref": "prompt:abc",
        "model_ref": "model:latent-loop",
        "replay_ref": replay_ref,
    }
    return build_eval_attempt_packet(
        sources=[{"ref": "run:att-1", "sha256": _HEX}],
        benchmark={
            "benchmark_ref": "arc-agi-2",
            "task_id": "task-007",
            "authority_receipt": "arcprize:eval-set-v2",
        },
        attempt=attempt,
        result={"outcome": "correct", "score": 1.0},
        boundaries=boundaries,
        claim="task solved",
        scope="one task",
        packet_id="ea-audit",
    )


def test_latent_reasoning_with_replay_is_still_a_match():
    packet = _packet(trace_available=False, replay_ref="replay:xyz")
    assert packet["verdicts"]["overall"] == "MATCH"
    assert validate_eval_attempt_packet(packet) == []


def test_latent_reasoning_without_replay_derives_unverifiable():
    packet = _packet(trace_available=False, replay_ref=None)
    assert packet["verdicts"]["overall"] == "UNVERIFIABLE"
    assert validate_eval_attempt_packet(packet) == []


def test_forged_match_with_no_audit_surface_is_rejected():
    packet = _packet(trace_available=False, replay_ref=None)
    packet["verdicts"]["overall"] = "MATCH"
    assert any(
        i.path == "$.verdicts.overall" for i in validate_eval_attempt_packet(packet)
    )


def test_visible_trace_without_replay_is_still_a_match():
    # The trace itself is an audit surface.
    packet = _packet(trace_available=True, replay_ref=None)
    assert packet["verdicts"]["overall"] == "MATCH"
    assert validate_eval_attempt_packet(packet) == []


def test_boundary_field_is_optional_for_backward_compat():
    packet = _packet(trace_available=None, replay_ref=None)
    assert packet["verdicts"]["overall"] == "MATCH"
    assert validate_eval_attempt_packet(packet) == []


def test_non_boolean_trace_flag_is_rejected():
    packet = _packet(trace_available=False)
    packet["boundaries"]["reasoning_trace_available"] = "nope"
    assert any(
        "reasoning_trace_available" in i.path
        for i in validate_eval_attempt_packet(packet)
    )
