"""print_mode.py -- `flywheel code -p` output for scripts and CI.

text         the final answer on stdout, a one-line footer on stderr
json         one JSON object when the request finishes
stream-json  one JSON object per loop event as it happens, then the result

The result object carries the final answer, steps, seconds, the test verdict
when a test command was set, the ledger head and whether the chain verifies,
token counts as the provider reported them, and the saved session id. The exit
code is 0, 1 when the test gate failed or the model could not be reached.
"""
from __future__ import annotations

import json
import sys

SCHEMA = "flywheel.code-result/v1"


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def stream_event(event: dict) -> None:
    body = dict(event)
    body["event"] = body.pop("type", None)
    _emit({"type": "event", **body})


def result_object(session, result) -> dict:
    return {"schema": SCHEMA, "type": "result", "final": result.final,
            "steps": result.steps, "seconds": round(result.seconds, 3),
            "tests_pass": result.tests_pass, "ledger_head": result.checkpoint,
            "chain_ok": result.verified, "usage": result.usage,
            "session_id": session.session_id or None, "mode": session.executor.mode}


def run_print(session, prompt: str, fmt: str) -> int:
    from harness.local_agent import BackendError
    if fmt == "stream-json":
        session.on_event = stream_event
    elif fmt == "json":
        session.on_event = None
    try:
        result = session.turn(prompt)
    except BackendError as e:
        if fmt == "text":
            print(f"[error] {e}", file=sys.stderr)
        else:
            _emit({"schema": SCHEMA, "type": "error", "error": str(e)})
        return 1
    if fmt == "text":
        from .cli import footer
        print(result.final)
        print(footer(result), file=sys.stderr)
    else:
        _emit(result_object(session, result))
    return 1 if result.tests_pass is False else 0
