"""Freeze pipeline for the rubric-repair family.

For every applicable (seed, operator) mutant: execute the seed's reference
module AND the broken module through the real installed verifiers machinery
over the repair battery, mirroring the child driver's per-fixture error
semantics; derive kill flags from the disagreements; apply the kill-check
(a mutant ships only when it flips at least two rows, one of which can then
be shown as the visible symptom while at least one stays hidden and scored);
select the three visible rows deterministically; concentrate hidden credit on
the kill set; and assert the frozen no-op ceiling (the verbatim broken module
scores 0.0 when it breaks the structural gate, at most the regression share
otherwise) before anything is written.
"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from verifiers_component_forge.families import rubric_contract as rc
from verifiers_component_forge.families import rubric_repair as rr
from verifiers_component_forge.families import (
    rubric_repair_grammar as rrg,
)
from verifiers_component_forge.harness import runner

NOOP_CEILING = 0.2


def _load_rubric(source: str, tag: str):
    import verifiers as vf

    module = types.ModuleType(tag)
    sys.modules[tag] = module
    exec(compile(source, f"<{tag}>", "exec"), module.__dict__)  # noqa: S102 -- executing our own reference source is the design
    env = module.load_environment()
    rubric = env.rubric
    if isinstance(rubric, vf.RubricGroup):
        rubric = rubric.rubrics[0]
    return rubric


def _replay(rubric, fixtures: list[dict]) -> list[dict]:
    """Mirror child driver R: one score_rollout per fixture, exceptions
    contained per fixture as {"error": ...} so kill flags reflect exactly
    what the child would report."""
    from verifiers.types import State

    async def one(fx: dict) -> dict:
        state = State(
            {
                "prompt": fx["prompt"],
                "completion": fx["completion"],
                "answer": fx["answer"],
                "info": fx["info"],
                "task": {},
            }
        )
        await rubric.score_rollout(state)
        return {
            "reward": float(state["reward"]),
            "metrics": {k: float(v) for k, v in state["metrics"].items()},
        }

    results = []
    for fx in fixtures:
        try:
            results.append(asyncio.run(one(fx)))
        except BaseException as e:  # noqa: BLE001 -- mirrors the driver's containment
            results.append({"error": f"{type(e).__name__}: {e}"})
    return results


def _matches(got: dict, want: dict) -> bool:
    return runner.match_fraction([got], [want]) == 1.0


def _broken_gate_passes(broken_rubric, contract: rc.Contract) -> bool:
    import verifiers as vf

    names = [getattr(f, "__name__", "?") for f in broken_rubric.funcs]
    weights = [float(w) for w in broken_rubric.weights]
    return (
        type(broken_rubric).score_rollout is vf.Rubric.score_rollout
        and names == [c.name for c in contract.criteria]
        and weights == [float(w) for w in contract.effective_weights]
    )


def build_rubric_repair() -> dict:
    out: dict[str, dict] = {}
    for mutant in rr.all_mutants():
        contract = mutant.contract
        battery = rrg.battery_for(contract)
        reference = rc.reference_module_source(contract)
        ref_rubric = _load_rubric(reference, "reference_module")
        broken_rubric = _load_rubric(mutant.broken_source, "broken_module")

        expect = _replay(ref_rubric, battery)
        broken_out = _replay(broken_rubric, battery)
        kill = [not _matches(b, e) for b, e in zip(broken_out, expect)]
        kill_ix = [i for i, k in enumerate(kill) if k]
        agree_ix = [i for i, k in enumerate(kill) if not k]
        if len(kill_ix) < 2:
            continue  # symptom would exhaust the kill set; mutant is unshippable

        visible_ix = ([kill_ix[0]] + agree_ix[:2] + kill_ix[1:])[:3]
        hidden_ix = [i for i in range(len(battery)) if i not in visible_ix]
        hidden_kills = [i for i in hidden_ix if kill[i]]
        hidden_agrees = [i for i in hidden_ix if not kill[i]]
        if not hidden_kills:
            raise AssertionError(f"{mutant.instance_id}: no hidden kill row")

        weight_of: dict[int, float] = {}
        if hidden_agrees:
            for i in hidden_kills:
                weight_of[i] = rr.KILL_SHARE / len(hidden_kills)
            for i in hidden_agrees:
                weight_of[i] = rr.REGRESSION_SHARE / len(hidden_agrees)
        else:
            for i in hidden_kills:
                weight_of[i] = 1.0 / len(hidden_kills)

        gate_passes = _broken_gate_passes(broken_rubric, contract)
        if gate_passes:
            noop = runner.match_fraction(
                [broken_out[i] for i in hidden_ix],
                [expect[i] for i in hidden_ix],
                [weight_of[i] for i in hidden_ix],
            )
        else:
            noop = 0.0
        if noop >= NOOP_CEILING:
            raise AssertionError(f"{mutant.instance_id}: verbatim broken scores {noop}")

        def row(i: int, battery=battery, expect=expect) -> dict:
            return {
                "cell": battery[i]["cell"],
                "fixture": {
                    "prompt": battery[i]["prompt"],
                    "completion": battery[i]["completion"],
                    "answer": battery[i]["answer"],
                    "info": battery[i]["info"],
                },
                "expect": expect[i],
            }

        visible = [row(i) for i in visible_ix]
        visible[0]["observed"] = broken_out[visible_ix[0]]
        hidden = []
        for i in hidden_ix:
            r = row(i)
            r["kill"] = kill[i]
            r["weight"] = round(weight_of[i], 12)
            hidden.append(r)

        out[mutant.instance_id] = {
            "seed": contract.variant_id,
            "operator": mutant.operator.name,
            "gate_breaking": not gate_passes,
            "noop_score": round(noop, 12),
            "contract": {
                "table_ix": contract.table_ix,
                "names": [c.name for c in contract.criteria],
                "kinds": [[c.name, c.kind, c.param] for c in contract.criteria],
                "weights": list(contract.effective_weights),
                "exclusion": contract.exclusion,
                "negative": contract.negative,
            },
            "broken_source": mutant.broken_source,
            "visible": visible,
            "fixtures": hidden,
        }
    return out
