"""Child driver P: run an agent-emitted parser module over hidden inputs.

Runs under ``python -I`` with a scrubbed environment. Receives one JSON
document on stdin::

    {"module_source": str, "inputs": [recipe, ...], "sys_paths": [str, ...]}

and emits one JSON document on stdout::

    {"results": [str | null | {"error": str}, ...]}

Each recipe rebuilds a completion shape locally (never pickled):

- ``{"kind": "text", "value": str}`` -- a plain string completion
- ``{"kind": "chat", "messages": [{"role": str, "content": ...}, ...]}`` --
  dict-style chat messages; ``content`` is a string or a list of
  ``{"type": "text", "text": str}`` parts
- ``{"kind": "attr", "messages": [...]}`` -- the same messages exposed as
  attribute-style objects (``m.role`` / ``m.content``), the shape some client
  libraries hand back

The agent module must export ``build_parser()`` returning the parser object
whose ``parse_answer`` is probed. Oracle expectations never reach this
process; the parent compares.
"""

from __future__ import annotations

import json
import sys
import types


def _build_completion(recipe: dict) -> object:
    kind = recipe["kind"]
    if kind == "text":
        return recipe["value"]
    messages = []
    for m in recipe["messages"]:
        content = m["content"]
        if isinstance(content, list):
            content = [dict(part) for part in content]
        messages.append({"role": m["role"], "content": content})
    if kind == "chat":
        return messages
    if kind == "attr":
        out = []
        for m in messages:
            bag = types.SimpleNamespace(role=m["role"], content=m["content"])
            out.append(bag)
        return out
    raise ValueError(f"unknown recipe kind: {kind!r}")


def main() -> int:
    request = json.load(sys.stdin)
    for p in request["sys_paths"]:
        if p not in sys.path:
            sys.path.append(p)

    module = types.ModuleType("agent_module")
    # Registered before exec: dataclass machinery (among others) resolves
    # the defining module through sys.modules.
    sys.modules["agent_module"] = module
    try:
        exec(  # noqa: S102 -- executing the agent module is the driver's job
            compile(request["module_source"], "<agent_module>", "exec"), module.__dict__
        )
        build_parser = module.build_parser  # type: ignore[attr-defined]
        parser = build_parser()
    except BaseException as e:  # noqa: BLE001 -- a broken module fails all probes, reported not raised
        json.dump(
            {
                "results": [{"error": f"module: {type(e).__name__}: {e}"}]
                * len(request["inputs"])
            },
            sys.stdout,
        )
        return 0

    results: list[object] = []
    for recipe in request["inputs"]:
        try:
            completion = _build_completion(recipe)
            value = parser.parse_answer(completion)
            results.append(
                value
                if isinstance(value, str) or value is None
                else {"error": f"non-string result: {type(value).__name__}"}
            )
        except BaseException as e:  # noqa: BLE001 -- per-probe containment
            results.append({"error": f"{type(e).__name__}: {e}"})

    json.dump({"results": results}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
