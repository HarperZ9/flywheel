"""Child driver R: structural-gate an agent-emitted environment module, then
replay hidden fixtures through the REAL ``verifiers.Rubric.score_rollout``.

Runs under ``python -I`` with a scrubbed environment. Receives one JSON
document on stdin::

    {
      "module_source": str,
      "inputs": {
        "contract": {"names": [str, ...], "weights": [float, ...]},
        "fixtures": [{"prompt": ..., "completion": ..., "answer": ...,
                      "info": {...}}, ...]
      },
      "sys_paths": [str, ...]
    }

and emits one JSON document on stdout::

    {
      "gate": {"score_rollout_is_real": bool, "names_match": bool,
               "weights_match": bool},
      "results": [{"reward": float, "metrics": {...}} | {"error": str}, ...]
    }

The gate pins three structural facts before any credit: the rubric still uses
the library's own ``score_rollout`` (no bespoke scoring loop smuggled in), the
reward-function names match the contract exactly and in order, and the weight
vector equals the contract. Scoring semantics beyond that are established by
the fixture replay itself, through the same call path ``vf-eval`` uses. Oracle
expectations never reach this process; the parent compares.
"""

from __future__ import annotations

import asyncio
import json
import sys
import types


def main() -> int:
    request = json.load(sys.stdin)
    for p in request["sys_paths"]:
        if p not in sys.path:
            sys.path.append(p)

    import verifiers as vf
    from verifiers.types import State

    contract = request["inputs"]["contract"]
    fixtures = request["inputs"]["fixtures"]

    def all_failed(msg: str) -> int:
        json.dump(
            {
                "gate": {
                    "score_rollout_is_real": False,
                    "names_match": False,
                    "weights_match": False,
                },
                "results": [{"error": msg}] * len(fixtures),
            },
            sys.stdout,
        )
        return 0

    module = types.ModuleType("agent_module")
    # Registered before exec: dataclass machinery (among others) resolves
    # the defining module through sys.modules.
    sys.modules["agent_module"] = module
    try:
        exec(  # noqa: S102 -- executing the agent module is the driver's job
            compile(request["module_source"], "<agent_module>", "exec"), module.__dict__
        )
        env = module.load_environment()  # type: ignore[attr-defined]
        rubric = env.rubric
        # SingleTurnEnv composes the user rubric into a RubricGroup alongside
        # its own monitor rubric; the contract is about the USER rubric, so
        # gate and replay against that member (first, by construction).
        if isinstance(rubric, vf.RubricGroup):
            rubric = rubric.rubrics[0]
    except BaseException as e:  # noqa: BLE001 -- a broken module fails everything, reported not raised
        return all_failed(f"module: {type(e).__name__}: {e}")

    names = [getattr(f, "__name__", "?") for f in rubric.funcs]
    weights = [float(w) for w in rubric.weights]
    gate = {
        "score_rollout_is_real": type(rubric).score_rollout is vf.Rubric.score_rollout,
        "names_match": names == contract["names"],
        "weights_match": weights == [float(w) for w in contract["weights"]],
    }

    async def replay() -> list[object]:
        results: list[object] = []
        for fx in fixtures:
            try:
                state = State(
                    {
                        "prompt": fx.get("prompt", ""),
                        "completion": fx["completion"],
                        "answer": fx.get("answer", ""),
                        "info": fx.get("info", {}),
                        "task": fx.get("task", {}),
                    }
                )
                await rubric.score_rollout(state)  # writes reward/metrics into state
                results.append(
                    {
                        "reward": float(state["reward"]),
                        "metrics": {k: float(v) for k, v in state["metrics"].items()},
                    }
                )
            except BaseException as e:  # noqa: BLE001 -- per-fixture containment
                results.append({"error": f"{type(e).__name__}: {e}"})
        return results

    results = asyncio.run(replay())
    json.dump({"gate": gate, "results": results}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
