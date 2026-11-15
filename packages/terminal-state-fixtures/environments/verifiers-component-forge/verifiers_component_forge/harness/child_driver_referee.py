"""Child driver M: replay scripted conversations through the REAL
``verifiers.MultiTurnEnv.rollout`` against an agent-emitted referee env.

Runs under ``python -I`` with a scrubbed environment. Receives one JSON
document on stdin::

    {
      "module_source": str,
      "inputs": {"scripts": [{"replies": [str, ...],
                              "prompt": [...], "answer": str}, ...]},
      "sys_paths": [str, ...]
    }

and emits one JSON document on stdout::

    {
      "gate": {"rollout_is_real": bool},
      "results": [{"transcript": [[role, content], ...], "reward": float,
                   "metrics": {...}, "stop_reason": str,
                   "stop_condition": str} | {"error": str}, ...]
    }

The gate pins one structural fact: the env still runs the library's own
``MultiTurnEnv.rollout`` (``@final`` has no runtime force, so identity is
asserted). Everything else is established by replay through the same loop
``vf-eval`` uses: a canned client feeds the scripted player turns and raises
a sentinel if the env keeps asking after the script ends, so a referee that
fails to terminate zeroes that script instead of hanging. Oracle expectations
never reach this process; the parent compares.
"""

from __future__ import annotations

import asyncio
import json
import sys
import types

SCRIPT_TIMEOUT_SECONDS = 20.0


def main() -> int:
    request = json.load(sys.stdin)
    for p in request["sys_paths"]:
        if p not in sys.path:
            sys.path.append(p)

    import verifiers as vf
    from verifiers.clients import Client
    from verifiers.types import Response, ResponseMessage

    scripts = request["inputs"]["scripts"]

    class ScriptExhausted(vf.Error):
        pass

    class ScriptClient(Client):
        def __init__(self, replies: list[str]):
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
                raise ScriptExhausted("script exhausted: env did not terminate")
            self.served += 1
            return self.replies.pop(0)

        async def raise_from_native_response(self, response):
            pass

        async def from_native_response(self, response):
            return Response(
                id=f"canned-{self.served}",
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

    def all_failed(msg: str) -> int:
        json.dump(
            {
                "gate": {"rollout_is_real": False},
                "results": [{"error": msg}] * len(scripts),
            },
            sys.stdout,
        )
        return 0

    module = types.ModuleType("agent_module")
    sys.modules["agent_module"] = module
    try:
        exec(  # noqa: S102 -- executing the agent module is the driver's job
            compile(request["module_source"], "<agent_module>", "exec"), module.__dict__
        )
        env = module.load_environment()  # type: ignore[attr-defined]
        rubric = env.rubric
        if isinstance(rubric, vf.RubricGroup):
            rubric = rubric.rubrics[0]
    except BaseException as e:  # noqa: BLE001 -- a broken module fails everything, reported not raised
        return all_failed(f"module: {type(e).__name__}: {e}")

    gate = {"rollout_is_real": type(env).rollout is vf.MultiTurnEnv.rollout}

    async def replay_one(script: dict) -> dict:
        client = ScriptClient(script["replies"])
        input_row = {
            "prompt": script.get("prompt", []),
            "answer": script.get("answer", ""),
            "info": {},
        }
        state = await asyncio.wait_for(
            env.rollout(input_row, client, "canned", {}),
            timeout=SCRIPT_TIMEOUT_SECONDS,
        )
        if state.get("error") is not None or client.replies:
            # exhaustion sentinel, env error, or early termination with
            # unconsumed script turns: the episode did not follow the script
            raise RuntimeError(
                f"episode aborted: stop={state.get('stop_condition')} "
                f"unconsumed={len(client.replies)}"
            )
        transcript = []
        for message in state["completion"] or []:
            role = getattr(message, "role", None) or message["role"]
            content = getattr(message, "content", None)
            if content is None and isinstance(message, dict):
                content = message.get("content")
            transcript.append([str(role), str(content or "")])
        await rubric.score_rollout(state)
        return {
            "transcript": transcript,
            "reward": float(state["reward"]),
            "metrics": {k: float(v) for k, v in state["metrics"].items()},
            "stop_reason": str(state.get("stop_reason", "")),
            "stop_condition": str(state.get("stop_condition", "")),
        }

    async def replay() -> list[object]:
        results: list[object] = []
        for script in scripts:
            try:
                results.append(await replay_one(script))
            except BaseException as e:  # noqa: BLE001 -- per-script containment
                results.append({"error": f"{type(e).__name__}: {e}"})
        return results

    results = asyncio.run(replay())
    json.dump({"gate": gate, "results": results}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
