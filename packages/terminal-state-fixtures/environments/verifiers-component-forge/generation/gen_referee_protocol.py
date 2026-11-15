"""Freeze pipeline for the referee-protocol family.

For every spec: execute the reference module through the REAL
``MultiTurnEnv.rollout`` with a canned scripted client over the script
battery, freeze transcripts, rewards, metrics, and stop reasons, and
cross-check every frozen row against the independent pure fold
(referee_protocol_fold) before anything is written. A script the reference
cannot terminate exactly at its last reply, or a rollout row the fold
disagrees with, aborts generation instead of freezing a wrong oracle.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from verifiers_component_forge.families import referee_protocol as rp
from verifiers_component_forge.families import (
    referee_protocol_scripts as rps,
)
from verifiers_component_forge.families.referee_protocol_fold import (
    fold_episode,
)

logging.getLogger("verifiers").setLevel(logging.ERROR)


def _make_script_client(replies: list[str]):
    import verifiers as vf
    from verifiers.clients import Client
    from verifiers.types import Response, ResponseMessage

    class GenScriptClient(Client):
        def __init__(self):
            super().__init__(client_or_config=object())
            self.replies = list(replies)
            self.served = 0

        def setup_client(self, config):
            raise NotImplementedError

        async def to_native_tool(self, tool):
            raise NotImplementedError

        async def to_native_prompt(self, messages):
            return messages, {}

        async def get_native_response(
            self, prompt, model, sampling_args, tools=None, **kwargs
        ):
            if not self.replies:
                raise vf.Error("generation script exhausted")
            self.served += 1
            return self.replies.pop(0)

        async def raise_from_native_response(self, response):
            pass

        async def from_native_response(self, response):
            return Response(
                id=f"gen-{self.served}",
                created=0,
                model="canned",
                usage=None,
                message=ResponseMessage(
                    role="assistant",
                    content=response,
                    finish_reason="stop",
                    is_truncated=False,
                ),
            )

        async def close(self):
            pass

    return GenScriptClient()


def _replay_reference(env, rubric, script: dict) -> dict:
    client = _make_script_client(script["replies"])
    input_row = {
        "prompt": script["prompt"],
        "answer": script["answer"],
        "info": {},
    }

    async def run() -> dict:
        state = await env.rollout(input_row, client, "canned", {})
        if state.get("error") is not None or client.replies:
            raise AssertionError(
                f"reference did not follow script: stop={state.get('stop_condition')} "
                f"unconsumed={len(client.replies)}"
            )
        transcript = [
            [str(m.role), str(m.content or "")] for m in state["completion"] or []
        ]
        await rubric.score_rollout(state)
        return {
            "transcript": transcript,
            "reward": float(state["reward"]),
            "metrics": {k: float(v) for k, v in state["metrics"].items()},
            "stop_reason": str(state.get("stop_reason", "")),
        }

    return asyncio.run(run())


def build_referee_protocol() -> dict:
    import verifiers as vf

    out: dict[str, dict] = {}
    for spec in rp.all_specs():
        source = rp.reference_module_source(spec)
        module = types.ModuleType("reference_module")
        sys.modules["reference_module"] = module
        exec(compile(source, "<reference_module>", "exec"), module.__dict__)  # noqa: S102 -- executing our own reference source is the design
        env = module.load_environment()
        if type(env).rollout is not vf.MultiTurnEnv.rollout:
            raise AssertionError(f"{spec.variant_id}: reference overrides rollout")
        rubric = env.rubric
        if isinstance(rubric, vf.RubricGroup):
            rubric = rubric.rubrics[0]

        def freeze(script: dict, spec=spec, env=env, rubric=rubric) -> dict:
            expect = _replay_reference(env, rubric, script)
            folded = fold_episode(spec, script["replies"])
            if expect != folded:
                raise AssertionError(
                    f"{spec.variant_id}/{script['cell']}: rollout and fold disagree\n"
                    f"rollout: {expect}\nfold:    {folded}"
                )
            return {
                "cell": script["cell"],
                "script": {
                    "replies": script["replies"],
                    "prompt": script["prompt"],
                    "answer": script["answer"],
                },
                "expect": expect,
            }

        out[spec.variant_id] = {
            "spec": {
                "alphabet_ix": spec.alphabet_ix,
                "alphabet": spec.alphabet,
                "repeat_rule": spec.repeat_rule,
                "schedule": spec.schedule,
                "cap": spec.cap,
                "target_ix": spec.target_ix,
                "words": spec.words,
                "opening_prompt": spec.opening_prompt,
            },
            "worked": [freeze(rps.worked_for(spec))],
            "scripts": [freeze(s) for s in rps.scripts_for(spec)],
        }
    return out
