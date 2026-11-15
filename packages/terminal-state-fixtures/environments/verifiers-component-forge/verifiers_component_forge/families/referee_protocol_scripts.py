"""Script grammar for the referee-protocol family.

Each spec gets a deterministic battery of scripted player conversations
pinning every branch of the state machine: solve on turn 1, solve mid-game,
solve exactly at the cap (the stated solve-beats-cap winner), an unsolved cap
run, an all-invalid run, a repeat chain, invalid-then-solve, and a mixed run
touching invalid + repeat + both relation tokens. Every script terminates the
episode exactly at its final reply, which the fold asserts.

Expectations are never written here: the generator executes the reference
module through the real rollout over these scripts and freezes what comes
back, then cross-checks against the pure fold.
"""

from __future__ import annotations

from .referee_protocol import RefereeSpec

INVALID_INPUTS = ("Nope!", "two words", "MiXeD", "12345", "SHOUTING")


def _pad_wrong(spec: RefereeSpec, n: int) -> list[str]:
    """n distinct-feedback wrong guesses, alternating both relation words."""
    w = spec.words
    return [w["wrong_a"] if i % 2 == 0 else w["wrong_b"] for i in range(n)]


def scripts_for(spec: RefereeSpec) -> list[dict]:
    target = spec.words["target"]
    cap = spec.cap
    w1, w2 = spec.words["wrong_a"], spec.words["wrong_b"]

    def row(cell: str, replies: list[str]) -> dict:
        return {
            "cell": cell,
            "replies": replies,
            "prompt": [{"role": "user", "content": spec.opening_prompt}],
            "answer": target,
        }

    return [
        row("solve-turn-1", [target]),
        row("solve-turn-2", [w1, target]),
        row("solve-at-cap", _pad_wrong(spec, cap - 1) + [target]),
        row("cap-unsolved", _pad_wrong(spec, cap)),
        row(
            "all-invalid",
            [INVALID_INPUTS[i % len(INVALID_INPUTS)] for i in range(cap)],
        ),
        row("repeat-chain", [w1] * cap),
        row("invalid-then-solve", [INVALID_INPUTS[0], target]),
        row(
            "mixed-then-cap",
            ([w1, INVALID_INPUTS[1], w1, w2] + _pad_wrong(spec, cap))[:cap],
        ),
    ]


def worked_for(spec: RefereeSpec) -> dict:
    """One display script for the prompt, never scored: an invalid input,
    a wrong guess, then the solve, touching three branches in three turns."""
    return {
        "cell": "worked-invalid-wrong-solve",
        "replies": [INVALID_INPUTS[2], spec.words["wrong_b"], spec.words["target"]],
        "prompt": [{"role": "user", "content": spec.opening_prompt}],
        "answer": spec.words["target"],
    }
