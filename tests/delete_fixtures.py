"""Planted custody for the deletion tests: a gateway trace and a captured
turn (content capture on), each holding a long canary."""
from __future__ import annotations

import os

from harness.capture_hooks.protocol import commitment
from trace_enc_fakes import long_canary

OWNER = "owner_" + "a" * 32
JOURNEY = "jrn_" + "b" * 32
OPERATION = "op_" + "c" * 32
SESSION = "0f6d2c1e-4b7a-4c55-9a51-2f0e7c9d1a3b"
CANARY = long_canary(seed=23)


def plant_trace(home, operation=OPERATION, text=CANARY) -> str:
    from harness.gateway_agent_trace import AgentTrace
    (home / "state").mkdir(parents=True, exist_ok=True)
    trace = AgentTrace(home / "state", OWNER, JOURNEY, operation)
    trace.append("request", {"goal": "summarize the page"})
    trace.append("result", {"final": text})
    return trace.ref


def plant_turn(home, text=CANARY, session=SESSION, key="pid-1") -> dict:
    from harness.trace_capture_settings import DEFAULTS
    from harness.trace_turn_store import TurnStore
    (home / "state").mkdir(parents=True, exist_ok=True)
    store = TurnStore(home, OWNER, settings={**DEFAULTS, "content": "on"})
    store.prompt("claude-code", session, key, text=text)
    return store.stop("claude-code", session, key, text="answer: " + text[:200])


def plant_commitment_turn(home, session=SESSION, key="pid-9") -> dict:
    from harness.trace_turn_store import TurnStore
    store = TurnStore(home, OWNER)
    salt = os.urandom(32)
    store.prompt("claude-code", session, key, commitment=commitment("prompt", salt, "p"),
                 salt=salt)
    return store.stop("claude-code", session, key, commitment=commitment("answer", salt, "a"),
                      salt=salt)


def custody_bytes(home) -> bytes:
    return b"".join(p.read_bytes() for p in home.rglob("*") if p.is_file())
