"""Prose renderer for referee-protocol instances.

Renders entirely from the FROZEN entry: the referee rules with exact
feedback strings, the state and rubric contracts, the pinned MultiTurnEnv
skeleton (hardcoded so the task measures composition against a stated
contract, not training-data recency), and one worked script with its frozen
transcript and reward. Eval-time rendering never re-executes anything.
"""

from __future__ import annotations

import json

from .rubric_contract_prompt import EMISSION_LINES

_SKELETON = """import verifiers as vf
from datasets import Dataset


class Referee(vf.MultiTurnEnv):
    async def setup_state(self, state):
        # initialize your episode state fields here; mutate and return state
        return state

    async def env_response(self, messages, state, **kwargs):
        guess = (messages[-1].content or "").strip()   # the latest player turn
        turn = len(state["trajectory"])                # 1-based turn just played
        # ... classify the guess, update counters ...
        # To END the episode, attach the FINAL message and return []:
        #     state["final_env_response"] = [{"role": "user", "content": "..."}]
        #     return []
        # Otherwise reply normally:
        return [{"role": "user", "content": "..."}]


def load_environment(**kwargs):
    rubric = vf.Rubric(
        funcs=[episode_reward, turns_used, invalid_inputs],
        weights=[1.0, 0.0, 0.0],
    )
    dataset = Dataset.from_list([{"question": "stub", "answer": "stub"}])
    return Referee(dataset=dataset, rubric=rubric, **kwargs)"""

_DIGEST = (
    "Pinned API facts for the installed verifiers: `MultiTurnEnv.rollout` is "
    "`@final`; never override it or the episode scores zero. The loop calls "
    "`env_response(messages, state)` after every model turn; `messages[-1]` "
    "is the latest assistant message and `len(state['trajectory'])` is the "
    "1-based number of the turn just played. Setting "
    "`state['final_env_response']` to a one-message list ends the episode "
    "and appends that message to the transcript. Reward functions receive "
    "`state` as a keyword argument; do not pass `max_turns`."
)


def _rule_lines(spec: dict) -> list[str]:
    t = spec["alphabet"]
    lines = [
        f"The hidden target word is {spec['words']['target']!r}; hardcode it.",
        "Each assistant turn is one guess. Classify it in this exact order:",
        (
            f"1. SOLVE: the stripped guess equals the target exactly -> the "
            f"episode ends; the final message is {t['solved']!r}. Record the "
            "1-based solve turn."
        ),
        (
            "2. INVALID: after str.strip(), the guess is not a nonempty string "
            "of ASCII letters that equals its own lowercase -> feedback "
            f"{t['invalid']!r}; add 1 to the invalid count. Invalid guesses are "
            "never remembered as guesses."
        ),
    ]
    step = 3
    if spec["repeat_rule"]:
        lines.append(
            f"{step}. REPEAT: the guess equals an earlier VALID guess -> "
            f"feedback {t['repeat']!r}. Repeats change no counters."
        )
        step += 1
    if t["relation"] == "lex":
        lines.append(
            f"{step}. RELATION: feedback {t['a']!r} when the guess sorts "
            f"strictly before the target (Python `<` on str), else {t['b']!r}."
        )
    else:
        lines.append(
            f"{step}. RELATION: feedback {t['a']!r} when the guess shares at "
            "least 3 distinct letters with the target "
            f"(len(set(guess) & set(target)) >= 3), else {t['b']!r}."
        )
    if spec["repeat_rule"]:
        lines.append("Valid non-repeat guesses are remembered in order.")
    lines += [
        (
            f"CAP: the episode allows {spec['cap']} guesses. When turn "
            f"{spec['cap']} does not solve, the episode ends and the final "
            f"message is {t['cap']!r} INSTEAD of that turn's feedback; counters "
            "still update first. When it does solve, SOLVE WINS: the final "
            f"message is {t['solved']!r}."
        ),
        (
            'STOP REASON: set state["stop_reason"] to "solved" or "cap" at the '
            "moment the episode ends."
        ),
    ]
    return lines


def _schedule_lines(spec: dict) -> list[str]:
    if spec["schedule"] == "decay":
        return [
            (
                "`episode_reward` (weight 1.0): solved on turn t -> "
                "max(10 - 2*(t - 1), 3) / 10. Not solved -> 0."
            ),
        ]
    return [
        (
            "`episode_reward` (weight 1.0): solved with k invalid inputs -> "
            "max(8 - k, 2) / 10. Not solved -> 1/10 when k == 0, else 0."
        ),
    ]


def render_prompt(entry: dict) -> str:
    spec = entry["spec"]
    lines: list[str] = []
    a = lines.append
    a(
        "Write a Python module implementing EXACTLY the deterministic "
        "referee below as a verifiers MultiTurnEnv, plus its Rubric."
    )
    a("")
    a("## Referee rules")
    a("")
    lines += _rule_lines(spec)
    a("")
    a("## State contract")
    a("")
    a(
        '`setup_state` initializes `state["invalid_count"] = 0`, '
        '`state["solve_turn"] = 0`, and `state["stop_reason"] = ""`; the '
        "referee updates them as defined above (`solve_turn` stays 0 when "
        "unsolved)."
    )
    a("")
    a("## Rubric contract")
    a("")
    a(
        "`vf.Rubric(funcs=[episode_reward, turns_used, invalid_inputs], "
        "weights=[1.0, 0.0, 0.0])`, names and order exact."
    )
    lines += _schedule_lines(spec)
    a(
        "`turns_used` (weight 0.0): float(len(state['trajectory'])). "
        "`invalid_inputs` (weight 0.0): float of the invalid count."
    )
    a("")
    a("## Pinned skeleton and API digest")
    a("")
    a(_DIGEST)
    a("")
    a("```python")
    a(_SKELETON)
    a("```")
    a("")
    a("## Worked script (illustrative only; never scored)")
    a("")
    worked = entry["worked"][0]
    a(f"Player turns, in order: {worked['script']['replies']!r}")
    expect = worked["expect"]
    a(f"Resulting transcript: {json.dumps(expect['transcript'])}")
    a(
        f"-> reward {expect['reward']!r}, stop_reason "
        f"{expect['stop_reason']!r}, metrics "
        f"{json.dumps(expect['metrics'], sort_keys=True)}"
    )
    a("")
    lines += EMISSION_LINES
    return "\n".join(lines)
