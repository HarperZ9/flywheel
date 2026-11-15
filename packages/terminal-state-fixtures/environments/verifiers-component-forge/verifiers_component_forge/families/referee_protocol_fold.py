"""Pure-function fold of the referee state machine.

An independent hand-model of the referee-protocol contract with no verifiers
dependency: fold one scripted episode to its expected transcript, reward,
metrics, and stop reason. The generator freezes what the REAL
``MultiTurnEnv.rollout`` produces from the reference module; this fold
cross-checks every frozen row at generation time and again in tests, so the
frozen expectations are pinned from two directions that share no code.
"""

from __future__ import annotations

from .referee_protocol import RefereeSpec


def _valid(guess: str) -> bool:
    return guess.isascii() and guess.isalpha() and guess == guess.lower()


def fold_episode(spec: RefereeSpec, replies: list[str]) -> dict:
    """Fold a full scripted episode. The script must terminate the episode
    exactly at its last reply (solve, or the cap turn); anything else raises,
    which the generator treats as a malformed script."""
    t = spec.alphabet
    target = spec.words["target"]
    transcript: list[list[str]] = []
    seen: list[str] = []
    invalid_count = 0
    solve_turn = 0
    stop_reason = ""

    for turn, reply in enumerate(replies, start=1):
        transcript.append(["assistant", reply])
        guess = reply.strip()
        if guess == target:
            solve_turn = turn
            stop_reason = "solved"
            transcript.append(["user", t["solved"]])
            if turn != len(replies):
                raise AssertionError("script continues past solve")
            break
        if not _valid(guess):
            invalid_count += 1
            feedback = t["invalid"]
        elif spec.repeat_rule and guess in seen:
            feedback = t["repeat"]
        else:
            if spec.repeat_rule:
                seen.append(guess)
            if t["relation"] == "lex":
                feedback = t["a"] if guess < target else t["b"]
            else:
                feedback = t["a"] if len(set(guess) & set(target)) >= 3 else t["b"]
        if turn >= spec.cap:
            stop_reason = "cap"
            transcript.append(["user", t["cap"]])
            if turn != len(replies):
                raise AssertionError("script continues past cap")
            break
        transcript.append(["user", feedback])
    else:
        raise AssertionError("script ended without solve or cap")

    if spec.schedule == "decay":
        reward = (
            max(10 - 2 * (solve_turn - 1), 3) / 10 if stop_reason == "solved" else 0.0
        )
    else:
        if stop_reason == "solved":
            reward = max(8 - invalid_count, 2) / 10
        else:
            reward = 1 / 10 if invalid_count == 0 else 0.0

    return {
        "transcript": transcript,
        "reward": reward,
        "metrics": {
            "episode_reward": reward,
            "turns_used": float(len(replies)),
            "invalid_inputs": float(invalid_count),
        },
        "stop_reason": stop_reason,
    }
