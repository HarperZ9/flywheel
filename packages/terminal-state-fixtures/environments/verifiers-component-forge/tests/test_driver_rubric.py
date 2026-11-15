"""Driver R smoke tests: the real-library scoring path, end to end.

Pinned claims: a contract-faithful module passes the structural gate and
matches reference rewards exactly; a weight-normalizing module (the classic
mistake the rubric-contract family exists to catch) passes the name gate but
fails the weight gate AND diverges on fixtures; a module that swaps in its own
scoring loop trips the score_rollout identity gate.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from verifiers_component_forge.harness import runner

CONTRACT = {
    "names": ["exactness", "brevity", "length_chars"],
    "weights": [0.7, 0.3, 0.0],
}

FAITHFUL_MODULE = """
import verifiers as vf
from datasets import Dataset

def exactness(completion, answer, **kwargs):
    return 1.0 if completion == answer else 0.0

def brevity(completion, **kwargs):
    return 1.0 if len(completion) <= 10 else 0.0

def length_chars(completion, **kwargs):
    return float(len(completion))

def load_environment(**kwargs):
    rubric = vf.Rubric(funcs=[exactness, brevity, length_chars], weights=[0.7, 0.3, 0.0])
    dataset = Dataset.from_list([{"question": "q", "answer": "a"}])
    return vf.SingleTurnEnv(dataset=dataset, rubric=rubric, **kwargs)
"""

# The classic mistake: normalizing weights so they sum to 1 across ALL funcs,
# dragging the 0-weight informational metric into the denominator.
NORMALIZING_MODULE = FAITHFUL_MODULE.replace(
    "weights=[0.7, 0.3, 0.0]", "weights=[0.7 / 1.0, 0.3 / 1.0, 0.1]"
)

BESPOKE_LOOP_MODULE = """
import verifiers as vf
from datasets import Dataset

def exactness(completion, answer, **kwargs):
    return 1.0 if completion == answer else 0.0

def brevity(completion, **kwargs):
    return 1.0 if len(completion) <= 10 else 0.0

def length_chars(completion, **kwargs):
    return float(len(completion))

class MyRubric(vf.Rubric):
    async def score_rollout(self, state):
        return await super().score_rollout(state)

def load_environment(**kwargs):
    rubric = MyRubric(funcs=[exactness, brevity, length_chars], weights=[0.7, 0.3, 0.0])
    dataset = Dataset.from_list([{"question": "q", "answer": "a"}])
    return vf.SingleTurnEnv(dataset=dataset, rubric=rubric, **kwargs)
"""

FIXTURES = [
    {"prompt": "q", "completion": "a", "answer": "a", "info": {}},
    {"prompt": "q", "completion": "a very long completion", "answer": "a", "info": {}},
    {"prompt": "q", "completion": "wrong", "answer": "a", "info": {}},
]

# Reference expectations for the faithful rubric, derived by hand from the
# contract: reward = 0.7*exactness + 0.3*brevity + 0.0*length.
EXPECTED = [
    {"reward": 1.0, "metrics": {"exactness": 1.0, "brevity": 1.0, "length_chars": 1.0}},
    {
        "reward": 0.0,
        "metrics": {"exactness": 0.0, "brevity": 0.0, "length_chars": 22.0},
    },
    {"reward": 0.3, "metrics": {"exactness": 0.0, "brevity": 1.0, "length_chars": 5.0}},
]


def _run(module: str) -> runner.ChildResult:
    return asyncio.run(
        runner.run_child(
            "child_driver_rubric.py",
            module,
            {"contract": CONTRACT, "fixtures": FIXTURES},
            wall_clock=90.0,
        )
    )


def test_faithful_module_passes_gate_and_matches_reference():
    result = _run(FAITHFUL_MODULE)
    assert result.ok, (result.failure, result.stderr_tail)
    gate = result.payload["gate"]
    assert gate == {
        "score_rollout_is_real": True,
        "names_match": True,
        "weights_match": True,
    }
    assert runner.match_fraction(result.payload["results"], EXPECTED) == 1.0


def test_weight_normalizer_fails_weight_gate_and_diverges():
    result = _run(NORMALIZING_MODULE)
    assert result.ok, (result.failure, result.stderr_tail)
    gate = result.payload["gate"]
    assert gate["names_match"] is True
    assert gate["weights_match"] is False
    # And the divergence is visible in the replay itself, on the fixture
    # where the smuggled 0.1 weight moves the reward.
    assert runner.match_fraction(result.payload["results"], EXPECTED) < 1.0


def test_bespoke_scoring_loop_trips_identity_gate():
    result = _run(BESPOKE_LOOP_MODULE)
    assert result.ok, (result.failure, result.stderr_tail)
    assert result.payload["gate"]["score_rollout_is_real"] is False
