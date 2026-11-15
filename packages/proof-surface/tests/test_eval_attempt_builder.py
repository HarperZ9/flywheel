"""Eval-attempt wedge: a single benchmark attempt, with contamination honesty.

Harvest of dogfood pass 0085 (arc_agi_eval cluster) + pass 0096 (rank #3
EvalAttemptProofPacket): replayable attempts, prompt/model boundaries, tool-use
records, and benchmark authority receipts. The load-bearing honesty gate: a
`correct` outcome is contamination -- not a pass -- if the attempt had
ground-truth access.
"""

from __future__ import annotations

from proof_surface.eval_attempt import (
    build_eval_attempt_packet,
    validate_eval_attempt_packet,
)

_HEX = "a" * 64

_BENCHMARK = {
    "benchmark_ref": "arc-agi-2",
    "task_id": "task-007",
    "authority_receipt": "arcprize:eval-set-v2",
    "split": "evaluation",
}
_ATTEMPT = {
    "attempt_id": "att-1",
    "prompt_ref": "prompt:abc",
    "model_ref": "model:opus",
    "tool_use": [{"tool": "python", "ref": "run:9"}],
    "replay_ref": "replay:xyz",
}


def _packet(*, outcome="correct", had_ground_truth=False):
    return build_eval_attempt_packet(
        sources=[{"ref": "run:att-1", "sha256": _HEX}],
        benchmark=_BENCHMARK,
        attempt=_ATTEMPT,
        result={"outcome": outcome, "score": 1.0},
        boundaries={
            "had_ground_truth": had_ground_truth,
            "had_internet": False,
            "had_tools": True,
        },
        claim="task-007 solved",
        scope="one ARC-AGI task",
        packet_id="ea-1",
    )


def test_clean_correct_attempt_is_a_match():
    packet = _packet()
    assert validate_eval_attempt_packet(packet) == []
    assert packet["verdicts"]["overall"] == "MATCH"


def test_incorrect_attempt_is_a_drift():
    assert _packet(outcome="incorrect")["verdicts"]["overall"] == "DRIFT"


def test_abstained_attempt_is_unverifiable():
    assert _packet(outcome="abstained")["verdicts"]["overall"] == "UNVERIFIABLE"


def test_contaminated_correct_is_rejected():
    # A "correct" that had the answer is contamination, not a pass.
    packet = _packet(outcome="correct", had_ground_truth=True)
    assert any("boundaries" in i.path for i in validate_eval_attempt_packet(packet))


def test_contaminated_attempt_is_not_scored_as_match():
    packet = _packet(outcome="correct", had_ground_truth=True)
    assert packet["verdicts"]["overall"] == "UNVERIFIABLE"


def test_unknown_outcome_is_rejected():
    packet = _packet()
    packet["result"]["outcome"] = "vibes"
    assert any("result.outcome" in i.path for i in validate_eval_attempt_packet(packet))


def test_missing_benchmark_authority_is_rejected():
    packet = _packet()
    del packet["benchmark"]["authority_receipt"]
    assert any(
        "benchmark.authority_receipt" in i.path
        for i in validate_eval_attempt_packet(packet)
    )
