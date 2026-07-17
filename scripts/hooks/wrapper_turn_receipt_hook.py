"""wrapper_turn_receipt_hook.py -- the post-pass for external wrappers.

The prompt hook (wrapper_scaffold_hook.py) freezes sources before the
model works; this stop hook completes the guarantee: when the wrapper's
turn ends, the prompt and final answer are sent to the gateway's
POST /api/scaffold, which chains a turn receipt (prompt hash, answer
hash, frozen sources) into the audit ledger. Together the pair gives
any harness the same per-message spine the engine's own routes carry.

Protocol-lenient: reads a JSON event on stdin, finds the prompt and the
final answer under common keys, and stays silent. Fails open: a dead
gateway or an unrecognized event shape costs nothing and never blocks
the wrapper. No receipt is faked; a turn that could not be banked is
simply not banked.
"""
from __future__ import annotations

import json
import sys
import urllib.request

GATEWAY = "http://127.0.0.1:8799"


def _first(event: dict, keys: tuple) -> str:
    for k in keys:
        v = event.get(k)
        if isinstance(v, str) and v.strip():
            return v
    return ""


def main() -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0
    prompt = _first(event, ("prompt", "user_prompt", "message", "input"))
    answer = _first(event, ("answer", "final_message", "response",
                            "last_assistant_message", "output"))
    if not prompt and not answer:
        return 0
    try:
        body = json.dumps({"prompt": prompt, "answer": answer}).encode()
        req = urllib.request.Request(
            GATEWAY + "/api/scaffold", data=body,
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=30).read()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
