"""profiles.py -- named manifests over the one substrate.

A profile is a small manifest, not a fork: it binds a default workflow, a
tool-gate posture, and an operating preamble onto the SAME gated loop and
router every other surface uses. Any endpoint in the roster can run any
profile -- that is the point: the harness carries the modern behavior
(staged workflow, gated tools, witnessed ledger, receipts), so an older
model generation gets the same operating environment as the newest one.

Gate posture here is a DEFAULT REQUEST, not an authorization: the runtime
ToolGate still enforces what the caller actually granted."""
from __future__ import annotations

PROFILES = {
    "code": {
        "name": "code",
        "description": "Coding sessions: plan, apply gated edits, prove it "
                       "with the test command. Write and exec are requested, "
                       "granted only by the caller.",
        "workflow": "code-change",
        "gates": {"allow_write": True, "allow_exec": True, "allow_mcp": False},
        "max_steps": 8,
        "system": "You are a coding agent in a sandboxed repository. Plan the "
                  "smallest correct change, use the tools to apply it, and do "
                  "not claim success the checks do not show.",
    },
    "design": {
        "name": "design",
        "description": "Design sessions: specs, schematics, and component "
                       "contracts. Read-only; the deliverable is a precise "
                       "artifact, not an edit.",
        "workflow": "design-schematic",
        "gates": {"allow_write": False, "allow_exec": False, "allow_mcp": False},
        "max_steps": 6,
        "system": "You are a design agent. Produce precise, buildable "
                  "artifacts: state inputs, outputs, invariants, and failure "
                  "modes before any rendering. Never decorate; specify.",
    },
    "work": {
        "name": "work",
        "description": "Research and drafting: dense sourced briefs with "
                       "unknowns stated honestly. Read-only.",
        "workflow": "research-brief",
        "gates": {"allow_write": False, "allow_exec": False, "allow_mcp": False},
        "max_steps": 6,
        "system": "You are a research agent. Every claim needs a source a "
                  "reader could check; say 'unknown' rather than guess.",
    },
    "cowork": {
        "name": "cowork",
        "description": "Collaborative sessions: plan first, surface decisions "
                       "for the human, act only within granted gates.",
        "workflow": "verify-claim",
        "gates": {"allow_write": False, "allow_exec": False, "allow_mcp": True},
        "max_steps": 6,
        "system": "You are a collaborating agent. Present the decision points "
                  "and the evidence; the human decides. Never bury a choice "
                  "inside an action.",
    },
    "chat": {
        "name": "chat",
        "description": "Plain conversation over any endpoint with a receipt "
                       "on every answer. No tools.",
        "workflow": None,
        "gates": {"allow_write": False, "allow_exec": False, "allow_mcp": False},
        "max_steps": 1,
        "system": "",
    },
}


def profile_roster() -> dict:
    """The profile manifests, JSON-shaped for the gateway."""
    return {"schema": "flywheel.profiles/v1",
            "note": "gate values are requested defaults; the runtime gate "
                    "enforces what the caller actually granted",
            "profiles": [dict(p) for p in PROFILES.values()]}


def get_profile(name: str) -> dict | None:
    p = PROFILES.get(name)
    return dict(p) if p else None
