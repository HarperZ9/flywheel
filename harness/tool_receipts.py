"""tool_receipts.py — sign each tool execution so a narrated result can't be forged.

The hash-chained session ledger already proves entries were not reordered or
edited after the fact (integrity). This adds AUTHENTICITY: each tool execution is
HMAC-signed with a per-run key the model never sees, so a claimed "I ran the tests
and they passed" can be cross-checked against the signed record of what actually
ran. Cheap (a single HMAC), non-learned, and it closes the gap between the
accept-time receipt and the individual tool calls inside the agentic loop.

Standard library only (hmac + hashlib + os.urandom for the key).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os

SCHEMA = "flywheel.tool-receipt/v1"


def new_session_key() -> bytes:
    """A fresh per-run signing key. Held in-process by the loop, never shown to
    the model, so the model cannot forge a valid signed tool result."""
    return os.urandom(32)


def _preimage(name: str, args, ok: bool, rc, output: str) -> bytes:
    body = {
        "name": name,
        "args": args if isinstance(args, dict) else {},
        "ok": bool(ok),
        "rc": rc,
        "output_sha256": hashlib.sha256((output or "").encode("utf-8")).hexdigest(),
    }
    return json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")


def sign_call(key: bytes, *, name: str, args, ok: bool, rc=None, output: str = "") -> str:
    return hmac.new(key, _preimage(name, args, ok, rc, output), hashlib.sha256).hexdigest()


def verify_call(key: bytes, sig: str, *, name: str, args, ok: bool, rc=None,
                output: str = "") -> bool:
    expected = sign_call(key, name=name, args=args, ok=ok, rc=rc, output=output)
    return hmac.compare_digest(expected, sig or "")


def sign_result(key: bytes, result) -> str:
    """Sign a ToolResult (name, args, ok, output)."""
    return sign_call(key, name=result.name, args=result.args, ok=result.ok,
                     output=result.output)


def verify_result(key: bytes, sig: str, result) -> bool:
    return verify_call(key, sig, name=result.name, args=result.args, ok=result.ok,
                       output=result.output)
