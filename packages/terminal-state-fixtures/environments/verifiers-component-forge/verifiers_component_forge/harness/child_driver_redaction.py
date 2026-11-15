"""Child driver D: run an emitted redaction function over hidden records.

Receives ``{"module_source": str, "inputs": [record, ...], "sys_paths": [...]}``
and emits ``{"results": [dict | {"error": str}, ...]}``. Expected redacted
outputs never enter the child; the parent compares terminal JSON state.
"""

from __future__ import annotations

import json
import sys
import types


def _plain_json(value):
    return json.loads(json.dumps(value, sort_keys=True))


def main() -> int:
    request = json.load(sys.stdin)
    for path in request["sys_paths"]:
        if path not in sys.path:
            sys.path.append(path)

    module = types.ModuleType("agent_module")
    sys.modules["agent_module"] = module
    try:
        exec(  # noqa: S102 -- executing the agent module is the driver's job
            compile(request["module_source"], "<agent_module>", "exec"), module.__dict__
        )
        redact_record = module.redact_record  # type: ignore[attr-defined]
    except BaseException as e:  # noqa: BLE001
        json.dump(
            {
                "results": [
                    {"error": f"module: {type(e).__name__}: {e}"}
                    for _ in request["inputs"]
                ]
            },
            sys.stdout,
        )
        return 0

    results: list[object] = []
    for record in request["inputs"]:
        try:
            result = redact_record(_plain_json(record))
            if not isinstance(result, dict):
                result = {"error": f"non-dict result: {type(result).__name__}"}
            else:
                result = _plain_json(result)
            results.append(result)
        except BaseException as e:  # noqa: BLE001
            results.append({"error": f"{type(e).__name__}: {e}"})

    json.dump({"results": results}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
