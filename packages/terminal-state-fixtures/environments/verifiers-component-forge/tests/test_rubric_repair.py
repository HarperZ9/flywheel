"""Oracle soundness for the rubric-repair family.

Hand-derived kill sets for specific operators; frozen-file invariants
(kill-check honored, weights sum to one, no-op ceiling frozen below 0.2);
regeneration byte-match; and discrimination through the REAL environment:
the reference module repairs every sampled instance to 1.0 while the
verbatim broken module scores its frozen no-op ceiling."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import verifiers as vf
from verifiers.types import State

import verifiers_component_forge as forge
from verifiers_component_forge.families.rubric_contract import (
    all_contracts,
    reference_module_source,
)
from verifiers_component_forge.families.rubric_repair import (
    OPERATORS,
    REGRESSION_SHARE,
)

DATA = (
    Path(__file__).resolve().parents[1]
    / "verifiers_component_forge"
    / "data"
    / "rubric_repair.json"
)

GATE_BREAKING = {op.name for op in OPERATORS if op.gate_breaking}


def _frozen() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def _contract_for(seed_vid: str):
    return next(c for c in all_contracts() if c.variant_id == seed_vid)


# ---- hand-derived kill sets -------------------------------------------------


def test_boundary_strict_kill_set_by_hand():
    # Seed s0 = table 8, brevity bound 24. `<=` vs `<` differs ONLY at
    # exactly 24 characters: the two at-boundary rows and nothing else.
    entry = _frozen()["rr-s0-boundary-strict"]
    assert entry["visible"][0]["cell"] == "len-at-boundary"
    assert entry["visible"][0]["observed"]["metrics"]["brevity"] == 0.0
    assert entry["visible"][0]["expect"]["metrics"]["brevity"] == 1.0
    hidden_kills = [p["cell"] for p in entry["fixtures"] if p["kill"]]
    assert hidden_kills == ["len-at-boundary-alt"]
    assert abs(entry["noop_score"] - REGRESSION_SHARE) < 1e-9
    assert not entry["gate_breaking"]


def test_exclusion_on_diagnostic_kill_set_by_hand():
    # Only rows carrying excluded=True can expose a guard on the diagnostic.
    entry = _frozen()["rr-s1-exclusion-on-diagnostic"]
    assert entry["visible"][0]["cell"] == "excluded-true"
    hidden_kills = [p["cell"] for p in entry["fixtures"] if p["kill"]]
    assert hidden_kills == ["excluded-true-partial"]
    # The symptom is the diagnostic zeroing out while the reward stays right.
    sym = entry["visible"][0]
    assert sym["observed"]["reward"] == sym["expect"]["reward"]
    assert sym["observed"]["metrics"] != sym["expect"]["metrics"]


def test_exact_strip_kill_set_by_hand():
    entry = _frozen()["rr-s0-exact-strip"]
    kills = {entry["visible"][0]["cell"]} | {
        p["cell"] for p in entry["fixtures"] if p["kill"]
    }
    assert kills == {"whitespace-pad", "whitespace-pad-leading"}


def test_gate_breaking_operators_freeze_noop_zero():
    data = _frozen()
    entry = data["rr-s0-weights-normalized"]
    assert entry["gate_breaking"]
    assert entry["noop_score"] == 0.0
    for vid, e in data.items():
        assert e["gate_breaking"] == (e["operator"] in GATE_BREAKING), vid


# ---- frozen-file invariants -------------------------------------------------


def test_frozen_structure_and_ceilings():
    data = _frozen()
    assert len(data) == 77  # 83 applicable mutants minus the 6 guard-dropped
    # verifiers scores a raising reward func as 0.0 itself, so dropping the
    # reference's try/except is behaviorally invisible: the kill-check must
    # have refused every guard-dropped mutant rather than shipping noise.
    assert not any(e["operator"] == "guard-dropped" for e in data.values())
    for vid, entry in data.items():
        names = set(entry["contract"]["names"])
        assert len(entry["visible"]) == 3, vid
        assert "observed" in entry["visible"][0], vid
        assert entry["visible"][0]["observed"] != entry["visible"][0]["expect"], vid
        assert len(entry["fixtures"]) >= 14, vid
        assert any(p["kill"] for p in entry["fixtures"]), vid
        assert abs(sum(p["weight"] for p in entry["fixtures"]) - 1.0) < 1e-6, vid
        assert entry["noop_score"] < 0.2, vid
        for row in entry["fixtures"] + entry["visible"]:
            assert set(row["expect"]["metrics"].keys()) == names, vid
        # the repair is re-derivable: the broken module is a real module that
        # differs from the reference the contract fully determines
        reference = reference_module_source(_contract_for(entry["seed"]))
        assert entry["broken_source"] != reference, vid
        compile(entry["broken_source"], "<broken>", "exec")


def test_frozen_matches_regeneration():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "generation"))
    import generate

    regenerated = generate._dumps(generate.build_rubric_repair())
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


def test_reference_repairs_and_verbatim_broken_hits_its_ceiling():
    data = _frozen()
    env = forge.load_environment()

    # A logic mutant: reference repair scores 1.0; the no-op submission
    # (returning the broken module verbatim) earns exactly the frozen
    # regression share, through the real child driver.
    vid = "rr-s0-boundary-strict"
    entry = data[vid]
    row = _row_for(env, vid)
    reference = reference_module_source(_contract_for(entry["seed"]))

    state = _score(env, row, "Repaired.\n\n```python\n" + reference + "\n```\n")
    assert state["reward"] == 1.0, state["metrics"]
    assert state["metrics"]["structural_gate_pass"] == 1.0

    state2 = _score(
        env, row, "Looks fine.\n\n```python\n" + entry["broken_source"] + "\n```\n"
    )
    assert abs(state2["reward"] - entry["noop_score"]) < 1e-9

    # A gate-breaking mutant: the verbatim broken module zeroes on the gate.
    vid3 = "rr-s0-weights-normalized"
    entry3 = data[vid3]
    row3 = _row_for(env, vid3)
    state3 = _score(env, row3, "```python\n" + entry3["broken_source"] + "\n```\n")
    assert state3["reward"] == 0.0
    assert state3["metrics"]["structural_gate_pass"] == 0.0
