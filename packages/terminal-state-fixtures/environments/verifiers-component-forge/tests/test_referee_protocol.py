"""Oracle soundness for the referee-protocol family.

Hand-derived episodes computed with pencil against the frozen file; the
independent pure fold swept over every frozen script; structural invariants;
regeneration byte-match; and discrimination through the REAL environment:
the reference solves to 1.0, a rollout override (even a delegating one)
zeroes on the identity gate, and a wrong reward schedule earns exactly the
transcript-only partial credit."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import verifiers as vf
from verifiers.types import State

import verifiers_component_forge as forge
from verifiers_component_forge.families.referee_protocol import (
    all_specs,
    reference_module_source,
)
from verifiers_component_forge.families.referee_protocol_fold import (
    fold_episode,
)

DATA = (
    Path(__file__).resolve().parents[1]
    / "verifiers_component_forge"
    / "data"
    / "referee_protocol.json"
)


def _frozen() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def _script(entry: dict, cell: str) -> dict:
    return next(s for s in entry["scripts"] if s["cell"] == cell)


def _spec_for(variant_id: str):
    return next(s for s in all_specs() if s.variant_id == variant_id)


# ---- hand-derived episodes --------------------------------------------------


def test_solve_at_cap_by_hand():
    # rp-a0-rep0-s0-c3 uses target row 0: bright < candle < member.
    # [bright, member, candle]: HIGHER, LOWER, then solve ON the cap turn.
    # Solve beats cap; decay schedule: max(10 - 2*2, 3)/10 = 0.6.
    row = _script(_frozen()["rp-a0-rep0-s0-c3"], "solve-at-cap")
    assert row["script"]["replies"] == ["bright", "member", "candle"]
    assert row["expect"]["transcript"] == [
        ["assistant", "bright"],
        ["user", "HIGHER"],
        ["assistant", "member"],
        ["user", "LOWER"],
        ["assistant", "candle"],
        ["user", "SOLVED"],
    ]
    assert row["expect"]["reward"] == 0.6
    assert row["expect"]["stop_reason"] == "solved"
    assert row["expect"]["metrics"] == {
        "episode_reward": 0.6,
        "turns_used": 3.0,
        "invalid_inputs": 0.0,
    }


def test_repeat_chain_by_hand():
    # rp-a0-rep1-s0-c3 shares target row 0. [bright, bright, bright]:
    # HIGHER, then REPEAT, then the cap message replaces turn 3's feedback.
    row = _script(_frozen()["rp-a0-rep1-s0-c3"], "repeat-chain")
    assert row["expect"]["transcript"] == [
        ["assistant", "bright"],
        ["user", "HIGHER"],
        ["assistant", "bright"],
        ["user", "REPEAT"],
        ["assistant", "bright"],
        ["user", "OUT-OF-TURNS"],
    ]
    assert row["expect"]["reward"] == 0.0
    assert row["expect"]["stop_reason"] == "cap"


def test_invalid_then_solve_flat_penalty_by_hand():
    # rp-a0-rep0-s1-c3 uses target row 4 (purple). One invalid then the
    # solve: flat-penalty pays max(8 - 1, 2)/10 = 0.7.
    row = _script(_frozen()["rp-a0-rep0-s1-c3"], "invalid-then-solve")
    assert row["script"]["replies"] == ["Nope!", "purple"]
    assert row["expect"]["transcript"][1] == ["user", "INVALID"]
    assert row["expect"]["reward"] == 0.7
    assert row["expect"]["metrics"]["invalid_inputs"] == 1.0


def test_overlap_alphabet_by_hand():
    # rp-a2-rep0-s0-c3 uses target row 0: lanced shares >=3 letters with
    # candle (WARM), shrimp shares none (COLD); unsolved cap run.
    row = _script(_frozen()["rp-a2-rep0-s0-c3"], "cap-unsolved")
    assert row["expect"]["transcript"] == [
        ["assistant", "lanced"],
        ["user", "WARM"],
        ["assistant", "shrimp"],
        ["user", "COLD"],
        ["assistant", "lanced"],
        ["user", "EXHAUSTED"],
    ]
    assert row["expect"]["reward"] == 0.0
    assert row["expect"]["stop_reason"] == "cap"


# ---- the independent fold sweeps every frozen row ---------------------------


def test_fold_matches_every_frozen_script():
    for variant_id, entry in _frozen().items():
        spec = _spec_for(variant_id)
        for row in entry["scripts"] + entry["worked"]:
            folded = fold_episode(spec, row["script"]["replies"])
            assert folded == row["expect"], f"{variant_id}/{row['cell']}"


# ---- frozen-file invariants -------------------------------------------------


def test_frozen_structure():
    data = _frozen()
    assert len(data) == 64
    names = {"episode_reward", "turns_used", "invalid_inputs"}
    for variant_id, entry in data.items():
        assert len(entry["scripts"]) == 8, variant_id
        assert len(entry["worked"]) == 1, variant_id
        reasons = set()
        for row in entry["scripts"]:
            expect = row["expect"]
            reasons.add(expect["stop_reason"])
            assert set(expect["metrics"]) == names, variant_id
            # rewards are stated in exact tenths
            assert abs(expect["reward"] * 10 - round(expect["reward"] * 10)) < 1e-12
            transcript = expect["transcript"]
            assert transcript[0][0] == "assistant" and transcript[-1][0] == "user"
            assert [r for r, _ in transcript] == ["assistant", "user"] * (
                len(transcript) // 2
            ), variant_id
        assert reasons == {"solved", "cap"}, variant_id


def test_frozen_matches_regeneration():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "generation"))
    import generate

    regenerated = generate._dumps(generate.build_referee_protocol())
    assert regenerated == DATA.read_text(encoding="utf-8")


# ---- discrimination through the real environment ----------------------------


def _score(env, row, reply_text: str) -> State:
    rubric = env.rubric
    if isinstance(rubric, vf.RubricGroup):
        rubric = rubric.rubrics[0]
    state = State(
        {
            "prompt": row["question"],
            "completion": [{"role": "assistant", "content": reply_text}],
            "answer": row["answer"],
            "info": row["info"],
            "task": {},
        }
    )
    asyncio.run(rubric.score_rollout(state))
    return state


def _row_for(env, variant_id: str) -> dict:
    dataset = env.get_dataset()
    for i in range(len(dataset)):
        if dataset[i]["answer"] == variant_id:
            return dataset[i]
    raise AssertionError(f"no dataset row for {variant_id}")


def test_reference_scores_one_and_cheats_hit_their_ceilings():
    env = forge.load_environment()
    vid = "rp-a0-rep0-s0-c3"
    row = _row_for(env, vid)
    source = reference_module_source(_spec_for(vid))

    state = _score(env, row, "My referee.\n\n```python\n" + source + "\n```\n")
    assert state["reward"] == 1.0, state["metrics"]
    assert state["metrics"]["structural_gate_pass"] == 1.0
    assert state["metrics"]["probe_error_fraction"] == 0.0

    # Overriding rollout, even to delegate to super(), breaks the identity
    # gate: the family measures composition inside the pinned loop.
    override = source.replace(
        "class Referee(vf.MultiTurnEnv):",
        "class Referee(vf.MultiTurnEnv):\n"
        "    async def rollout(self, input, client, model, sampling_args=None):\n"
        "        return await super().rollout(input, client, model, sampling_args)\n",
    )
    assert override != source
    state2 = _score(env, row, "```python\n" + override + "\n```\n")
    assert state2["reward"] == 0.0
    assert state2["metrics"]["structural_gate_pass"] == 0.0

    # A wrong decay slope leaves every transcript intact and flips rewards
    # only where the solve turn matters: hand count gives 6.5/8 exactly.
    wrong = source.replace(
        'max(10 - 2 * (state["solve_turn"] - 1), 3) / 10',
        'max(10 - (state["solve_turn"] - 1), 3) / 10',
    )
    assert wrong != source
    state3 = _score(env, row, "```python\n" + wrong + "\n```\n")
    assert abs(state3["reward"] - 6.5 / 8) < 1e-9
    assert state3["metrics"]["structural_gate_pass"] == 1.0
