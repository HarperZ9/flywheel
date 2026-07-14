"""canary_tripwire.py -- the credo-safe form of the context bomb.

Tracebit's context bombs (2026-07, frozen in the discourse dataset) plant
a string in a decoy resource so an ATTACKING agent's own safety guardrails
halt it. It works (~90% agent-success reduction across five models) but the
control is the attacker MODEL choosing to refuse: soft, model-dependent,
and strippable by an attacker who runs a model without those guardrails.
Tracebit says as much: you still must investigate and contain.

This is the hard version. We plant a unique canary token in a decoy
resource, and the control is OUR detection of that token being READ back
in a tool output, not any model deciding to stop. A tripped canary is a
containment signal that does not depend on a guardrail existing in any
model. It composes with the soft layer (you may also make the token a
refusal-prone string) but never relies on it.

Determinism note: the token needs unpredictability, but the harness forbids
Math.random-style nondeterminism in some contexts, so the token derives
from os.urandom via secrets, which is a real entropy source (this is a
security primitive, not a reproducible-artifact one).
"""
from __future__ import annotations

import secrets

SCHEMA = "flywheel.canary-tripwire/v1"
_PREFIX = "FLYWHEEL-CANARY-"


def mint_canary(label: str) -> dict:
    """A unique, unguessable canary token tagged with what decoy it guards."""
    return {"token": _PREFIX + secrets.token_hex(16), "label": str(label)}


def scan_for_canary(text: str, canaries: list) -> "dict | None":
    """Return the first canary whose token appears in `text`, else None.
    A canary appearing in a tool output means a decoy resource was read: a
    hard access signal, independent of any model's behaviour."""
    hay = text or ""
    for c in canaries or []:
        if c.get("token") and c["token"] in hay:
            return dict(c)
    return None


class Tripwire:
    """Plant canaries, then check every tool output for a read. A trip is a
    HARD containment signal: contain the run and investigate, do not ask a
    model to refuse."""

    def __init__(self, canaries: "list | None" = None):
        self.canaries = list(canaries or [])

    def plant(self, label: str) -> dict:
        c = mint_canary(label)
        self.canaries.append(c)
        return c

    def check(self, tool_output: str) -> dict:
        hit = scan_for_canary(tool_output, self.canaries)
        if hit is None:
            return {"schema": SCHEMA, "tripped": False,
                    "note": "no canary read; the tripwire detects access, "
                            "it does not depend on a model refusing"}
        return {"schema": SCHEMA, "tripped": True, "hit": hit,
                "action": "contain",
                "note": "a decoy resource was READ (canary token surfaced in "
                        "a tool output): a hard access signal detected by us, "
                        "not a refusal by the model. Contain the run and "
                        "investigate; do not trust the model to have stopped."}
