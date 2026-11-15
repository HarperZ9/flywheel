"""referee-protocol family: deterministic referee state machines.

An INSTANCE is a fully normative referee spec: a guessing game where the
model-side player (a canned script at scoring time) emits guesses and the
agent-built MultiTurnEnv referees them with an exact feedback alphabet, an
invalid-input rule, an optional REPEAT memory rule, a hard turn cap enforced
by the referee itself through ``final_env_response``, and a reward schedule
stated in tenths. Solve beats cap when both land on the same turn; that
winner is stated in the contract and realized by evaluating the guess before
the cap check.

The single source of truth is ``reference_module_source``: the module an
ideal agent would emit. The generator executes that source through the real
``MultiTurnEnv.rollout`` with a canned scripted client to freeze transcripts,
rewards, metrics, and stop reasons; an independent pure fold of the state
machine (referee_protocol_fold) cross-checks every frozen row.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---- feedback alphabets -----------------------------------------------------
# (relation, token strings). relation "lex": guess < target -> a, > -> b.
# relation "overlap": len(set(guess) & set(target)) >= 3 -> a, else b.

ALPHABETS: tuple[dict, ...] = (
    {
        "relation": "lex",
        "a": "HIGHER",
        "b": "LOWER",
        "invalid": "INVALID",
        "repeat": "REPEAT",
        "solved": "SOLVED",
        "cap": "OUT-OF-TURNS",
    },
    {
        "relation": "lex",
        "a": "[UP]",
        "b": "[DOWN]",
        "invalid": "[BAD]",
        "repeat": "[SEEN]",
        "solved": "[HIT]",
        "cap": "[END]",
    },
    {
        "relation": "overlap",
        "a": "WARM",
        "b": "COLD",
        "invalid": "INVALID",
        "repeat": "AGAIN",
        "solved": "FOUND",
        "cap": "EXHAUSTED",
    },
    {
        "relation": "overlap",
        "a": "STRONG",
        "b": "FAINT",
        "invalid": "NOISE",
        "repeat": "ECHO",
        "solved": "LOCK",
        "cap": "TIMEOUT",
    },
)

# ---- target rows ------------------------------------------------------------
# (target, below, above, near, far): below/above are lexicographic wrong
# guesses, near/far are letter-overlap wrong guesses (>= 3 shared letters vs
# 0). Hand-built; _check_target_rows() verifies every relation at import.

TARGET_ROWS: tuple[tuple[str, str, str, str, str], ...] = (
    ("candle", "bright", "member", "lanced", "shrimp"),
    ("silver", "quartz", "temple", "livers", "wombat"),
    ("hollow", "garden", "prince", "wool", "trims"),
    ("magnet", "insect", "worker", "gamete", "shrub"),
    ("purple", "outset", "rocket", "pulped", "chains"),
    ("thread", "sicken", "wander", "dearth", "buoy"),
    ("violet", "quaint", "zigzag", "olive", "punch"),
    ("effort", "candor", "poster", "forte", "chink"),
)


def _overlap(a: str, b: str) -> int:
    return len(set(a) & set(b))


def _check_target_rows() -> None:
    for target, below, above, near, far in TARGET_ROWS:
        words = (target, below, above, near, far)
        assert all(w.isascii() and w.isalpha() and w == w.lower() for w in words)
        assert below < target < above, target
        assert _overlap(near, target) >= 3, target
        assert _overlap(far, target) == 0, target
        assert len({target, below, above}) == 3 and len({target, near, far}) == 3


_check_target_rows()

CAPS = (3, 5, 7, 9)
SCHEDULES = ("decay", "flat-penalty")


@dataclass(frozen=True)
class RefereeSpec:
    alphabet_ix: int
    repeat_rule: bool
    schedule: str
    cap: int
    target_ix: int

    @property
    def variant_id(self) -> str:
        return (
            f"rp-a{self.alphabet_ix}-rep{int(self.repeat_rule)}"
            f"-{'s0' if self.schedule == 'decay' else 's1'}-c{self.cap}"
        )

    @property
    def alphabet(self) -> dict:
        return ALPHABETS[self.alphabet_ix]

    @property
    def words(self) -> dict:
        target, below, above, near, far = TARGET_ROWS[self.target_ix]
        if self.alphabet["relation"] == "lex":
            return {"target": target, "wrong_a": below, "wrong_b": above}
        return {"target": target, "wrong_a": near, "wrong_b": far}

    @property
    def opening_prompt(self) -> str:
        return "Guess my word. Reply with exactly one lowercase word per turn."


def all_specs() -> list[RefereeSpec]:
    out = []
    ordinal = 0
    for alphabet_ix in range(len(ALPHABETS)):
        for repeat_rule in (False, True):
            for schedule in SCHEDULES:
                for cap in CAPS:
                    out.append(
                        RefereeSpec(
                            alphabet_ix,
                            repeat_rule,
                            schedule,
                            cap,
                            ordinal % len(TARGET_ROWS),
                        )
                    )
                    ordinal += 1
    return out


# ---- reference module -------------------------------------------------------


def _relation_expr(spec: RefereeSpec) -> str:
    t = spec.alphabet
    if t["relation"] == "lex":
        return f"{t['a']!r} if guess < TARGET else {t['b']!r}"
    return f"{t['a']!r} if len(set(guess) & set(TARGET)) >= 3 else {t['b']!r}"


def _schedule_lines(spec: RefereeSpec) -> list[str]:
    if spec.schedule == "decay":
        return [
            "def episode_reward(state, **kwargs):",
            '    if state["stop_reason"] == "solved":',
            '        return max(10 - 2 * (state["solve_turn"] - 1), 3) / 10',
            "    return 0.0",
        ]
    return [
        "def episode_reward(state, **kwargs):",
        '    if state["stop_reason"] == "solved":',
        '        return max(8 - state["invalid_count"], 2) / 10',
        '    return 1 / 10 if state["invalid_count"] == 0 else 0.0',
    ]


def reference_module_source(spec: RefereeSpec) -> str:
    """The module an ideal agent would emit for this referee spec."""
    t = spec.alphabet
    repeat_setup = ['        state["guesses"] = []'] if spec.repeat_rule else []
    if spec.repeat_rule:
        classify = [
            '        elif guess in state["guesses"]:',
            f"            feedback = {t['repeat']!r}",
            "        else:",
            '            state["guesses"].append(guess)',
            f"            feedback = {_relation_expr(spec)}",
        ]
    else:
        classify = [
            "        else:",
            f"            feedback = {_relation_expr(spec)}",
        ]
    lines = [
        "import verifiers as vf",
        "from datasets import Dataset",
        "",
        f"TARGET = {spec.words['target']!r}",
        f"CAP = {spec.cap}",
        "",
        "",
        "class Referee(vf.MultiTurnEnv):",
        "    async def setup_state(self, state):",
        '        state["invalid_count"] = 0',
        '        state["solve_turn"] = 0',
        '        state["stop_reason"] = ""',
        *repeat_setup,
        "        return state",
        "",
        "    async def env_response(self, messages, state, **kwargs):",
        '        guess = (messages[-1].content or "").strip()',
        '        turn = len(state["trajectory"])',
        "        if guess == TARGET:",
        '            state["solve_turn"] = turn',
        '            state["stop_reason"] = "solved"',
        (
            '            state["final_env_response"] = ['
            f'{{"role": "user", "content": {t["solved"]!r}}}]'
        ),
        "            return []",
        "        if not (guess.isascii() and guess.isalpha() and guess == guess.lower()):",
        '            state["invalid_count"] += 1',
        f"            feedback = {t['invalid']!r}",
        *classify,
        "        if turn >= CAP:",
        '            state["stop_reason"] = "cap"',
        (
            '            state["final_env_response"] = ['
            f'{{"role": "user", "content": {t["cap"]!r}}}]'
        ),
        "            return []",
        '        return [{"role": "user", "content": feedback}]',
        "",
        "",
        *_schedule_lines(spec),
        "",
        "",
        "def turns_used(state, **kwargs):",
        '    return float(len(state["trajectory"]))',
        "",
        "",
        "def invalid_inputs(state, **kwargs):",
        '    return float(state["invalid_count"])',
        "",
        "",
        "def load_environment(**kwargs):",
        "    rubric = vf.Rubric(",
        "        funcs=[episode_reward, turns_used, invalid_inputs],",
        "        weights=[1.0, 0.0, 0.0],",
        "    )",
        '    dataset = Dataset.from_list([{"question": "stub", "answer": "stub"}])',
        "    return Referee(dataset=dataset, rubric=rubric, **kwargs)",
        "",
    ]
    return "\n".join(lines)
