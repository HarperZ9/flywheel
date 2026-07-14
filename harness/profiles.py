"""profiles.py -- deep operating profiles over the one substrate.

A profile is not a name with a prompt: it is a full operating manifest that
binds, onto the SAME gated loop and router, a differentiated set of tools, a
default staged workflow, a planning template (the stages a plan for this
kind of work moves through), an index scope (what structure the work reads),
and a surface (which of the app's features this profile foregrounds). Any
endpoint runs any profile, so an older model generation gets the whole
operating environment, not just an instruction.

Gate posture is a DEFAULT REQUEST, never an authorization: the runtime
ToolGate enforces what the caller actually granted."""
from __future__ import annotations

# The gated builtin tools a profile may request (local_tools.ToolExecutor).
_READ = ["read", "grep", "glob"]
_EDIT = _READ + ["apply_patch", "run"]

PROFILES = {
    "code": {
        "name": "code",
        "description": "Coding sessions: read the structure, plan the smallest "
                       "correct change, apply it under the gate, and prove it "
                       "with the tests. The IDE lane and the workspace agent "
                       "are the surface.",
        "workflow": "code-change",
        "gates": {"allow_write": True, "allow_exec": True, "allow_mcp": False},
        "max_steps": 8,
        "tools": _EDIT + ["lsp"],
        "planning": ["read structure", "smallest correct change",
                     "apply under gate", "prove with tests"],
        "index_scope": "symbols + dependency graph",
        "surface": ["Code", "Agent", "Projects"],
        "system": "You are a coding agent in a sandboxed repository. Plan the "
                  "smallest correct change, use the tools to apply it, and do "
                  "not claim success the checks do not show.",
    },
    "design": {
        "name": "design",
        "description": "Design and architecture: specs, interface contracts, "
                       "and schematics. Read-only; the deliverable is a "
                       "precise, buildable artifact, not an edit. The Studio "
                       "and Projects graph are the surface.",
        "workflow": "design-schematic",
        "gates": {"allow_write": False, "allow_exec": False, "allow_mcp": False},
        "max_steps": 6,
        "tools": _READ,
        "planning": ["requirements", "interfaces", "invariants",
                     "failure modes", "schematic"],
        "index_scope": "module boundaries + knowledge graph",
        "surface": ["Studio", "Projects", "Plan"],
        "system": "You are a design agent. Produce precise, buildable "
                  "artifacts: state inputs, outputs, invariants, and failure "
                  "modes before any rendering. Never decorate; specify.",
    },
    "work": {
        "name": "work",
        "description": "Deep research and drafting: gather evidence from the "
                       "hard places, weigh it, and write a dense sourced brief "
                       "with unknowns kept honest. Gather, Crucible, and "
                       "Memory are the surface.",
        "workflow": "research-brief",
        "gates": {"allow_write": False, "allow_exec": False, "allow_mcp": True},
        "max_steps": 6,
        "tools": _READ + ["mcp"],
        "planning": ["question", "sources", "evidence", "synthesis",
                     "open questions"],
        "index_scope": "corpus + citations",
        "surface": ["Companion", "Memory", "Workflows"],
        "system": "You are a research agent. Every claim needs a source a "
                  "reader could check; say 'unknown' rather than guess.",
    },
    "cowork": {
        "name": "cowork",
        "description": "Collaborative sessions: plan first, surface the "
                       "decisions and their evidence for the human, and act "
                       "only within granted gates. The Companion and "
                       "Workflows are the surface.",
        "workflow": "verify-claim",
        "gates": {"allow_write": False, "allow_exec": False, "allow_mcp": True},
        "max_steps": 6,
        "tools": _READ + ["mcp"],
        "planning": ["decisions", "evidence", "options", "recommendation"],
        "index_scope": "shared context",
        "surface": ["Companion", "Workflows", "Agent"],
        "system": "You are a collaborating agent. Present the decision points "
                  "and the evidence; the human decides. Never bury a choice "
                  "inside an action.",
    },
    "learn": {
        "name": "learn",
        "description": "The academy: academic tutoring, programming "
                       "instruction, and a knowledge academy over your own "
                       "material. Assess, practice, grade, and reach a mastery "
                       "verdict. The Learn lane is the surface.",
        "workflow": None,
        "gates": {"allow_write": False, "allow_exec": False, "allow_mcp": False},
        "max_steps": 4,
        "tools": _READ,
        "planning": ["assess", "prerequisites", "retrieval practice",
                     "grade", "mastery verdict"],
        "index_scope": "curriculum + prior mastery",
        "surface": ["Companion", "Memory"],
        "system": "You are a tutor. Diagnose what the learner does not yet "
                  "understand, teach the prerequisite first, and grade "
                  "honestly; never confirm mastery the work does not show.",
    },
    "train": {
        "name": "train",
        "description": "The local-model flywheel harness: watch the corpus, "
                       "the training run, and the verified-inference duel that "
                       "measures the harness against using a model raw. "
                       "Read-only observation; training start stays "
                       "operator-gated.",
        "workflow": None,
        "gates": {"allow_write": False, "allow_exec": False, "allow_mcp": False},
        "max_steps": 1,
        "tools": [],
        "planning": ["corpus", "train", "evaluate", "duel", "publish gate"],
        "index_scope": "run root + benchmark receipts",
        "surface": ["Endpoints", "Receipts"],
        "system": "",
    },
    "chat": {
        "name": "chat",
        "description": "Plain conversation over any endpoint with a receipt "
                       "on every answer. No tools.",
        "workflow": None,
        "gates": {"allow_write": False, "allow_exec": False, "allow_mcp": False},
        "max_steps": 1,
        "tools": [],
        "planning": [],
        "index_scope": "",
        "surface": ["Companion"],
        "system": "",
    },
}


def profile_roster() -> dict:
    """The deep profile manifests, JSON-shaped for the gateway."""
    return {"schema": "flywheel.profiles/v2",
            "note": "gate values are requested defaults; the runtime gate "
                    "enforces what the caller actually granted",
            "profiles": [dict(p) for p in PROFILES.values()]}


def get_profile(name: str) -> "dict | None":
    p = PROFILES.get(name)
    return dict(p) if p else None
