"""superproject.py -- the modular integration spine: Flywheel and its lanes.

Flywheel is the one platform. The flagship tools (gather, crucible, index,
forum, learn, telos) and the trained-model lane (local-model) are LANES inside
it -- each an organ of the reconcile. This module is the seam that composes
them: each lane is an organ with a role (perceive, verify, structure,
orchestrate, reconcile) and a routing edge to the next, and Flywheel itself is
the composer/reconciler that binds the loop closed.

Each lane's `doctor` emits a `next_actions` route, and those routes form a
closed spine: gather<->crucible (verify claims), index<->forum
(route/context), Flywheel reconciles the whole workflow. This manifest binds
the harness clusters onto that spine so the ecosystem reads as one modular
design under one platform, each lane uplifted to its role.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Organ:
    flagship: str
    version: str                 # live version confirmed via doctor
    role: str                    # the organ's function in the reconcile
    harness_modules: list        # the local native modules that instantiate it
    routes_to: str               # next_actions target (the spine edge)


# The five organs of the reconcile, each a flagship peer + its native harness cluster.
MANIFEST: dict[str, Organ] = {
    "perception": Organ(
        "gather", "1.6.0", "source receipt + witnessed digest + re-verifiable corpus",
        ["scout", "feeds", "intake", "gather adapters"], routes_to="crucible"),
    "verification": Organ(
        "crucible", "1.1.0", "register -> steelman -> measure -> refine -> witness MATCH/DRIFT",
        ["oracle", "witness", "adversarial_corpus", "calibration",
         "externalization_ablation", "quorum"], routes_to="gather"),
    "structure": Organ(
        "index", "2.8.0", "workspace map + verified wiki + structural verification",
        ["wiki", "second_brain", "structure_mapping"], routes_to="forum"),
    "orchestration": Organ(
        "forum", "1.12.0", "witnessed causal ledger + model-agnostic routing",
        ["router", "escalation", "budget_control", "evolve"], routes_to="index"),
    "reconciliation": Organ(
        "telos", "0.2.0", "the primary engine: perceive->verify->carry-proof, five-tool workflow",
        ["loop", "chain", "transitive_witness", "proof_cache", "boot", "flywheel"],
        routes_to="telos"),
}


# The broader flagship roster beyond the MCP spine (verified present in c:/dev/public/
# this session, but NOT MCP-probed here — marked 'declared', not 'live'). These are
# mission-tier flagships, not the domain-application bricks (build-*, calibrate-pro).
@dataclass
class Flagship:
    name: str
    role: str
    repo: str
    tier: str = "declared"       # 'live' (MCP doctor MATCH) | 'declared' (in repo, not probed)


EXTENDED: dict[str, Flagship] = {
    "emet": Flagship("emet", "faithfulness / re-derivability verification (frozen vectors)",
                     "public/emet"),
    "accountable-surface": Flagship(
        "accountable-surface", "the end-tool: perceive / gate / memory / 3-channel "
        "actuation / grounding", "public/accountable-surface"),
    "learn": Flagship("learn", "accountable learning forge (education flagship)",
                      "public/learn"),
    "proof-surface": Flagship("proof-surface", "agent-action proof packets",
                              "public/proof-surface"),
    "coherence-membrane": Flagship(
        "coherence-membrane", "origin concept: externalize a stateless mind's organs as "
        "a verified body", "public/coherence-membrane"),
    "studio-engine": Flagship(
        "studio-engine", "native creative-verification engine (perceive->generate->"
        "critique->refine->witness)", "public/build-engine"),
    "mneme": Flagship(
        "mneme", "durable cross-session memory with content-addressed recall",
        "public/mneme"),
    "plexus": Flagship(
        "plexus", "cross-flagship capability discovery + auto-wiring interop mesh",
        "public/plexus"),
    "relay": Flagship(
        "relay", "accountable multi-endpoint agent: failover, gated tool loop, "
        "witnessed ledger, MCP", "public/relay"),
}


def roster() -> dict:
    """The full flagship roster: the 5-organ MCP SPINE (live, doctor-verified) plus the
    EXTENDED mission-tier flagships (declared, present in repo, not MCP-probed here)."""
    spine_flags = {o.flagship for o in MANIFEST.values()}
    ext = {f.name: f.role for f in EXTENDED.values() if f.name not in spine_flags}
    return {"spine_live": sorted(spine_flags), "n_spine": len(spine_flags),
            "extended_declared": ext, "n_extended": len(ext),
            "total_flagships": len(spine_flags) + len(ext),
            "note": "spine = MCP-live (doctor MATCH this session); extended = declared in "
                    "c:/dev/public, NOT MCP-probed here. Domain bricks (build-*, "
                    "calibrate-pro) are not counted as mission flagships."}


def spine() -> dict:
    """The composition spine: organs + the closed routing graph. `closed` is True iff
    every route target is itself an organ (the ecosystem composes without dangling edges)."""
    organs = {name: o.flagship for name, o in MANIFEST.items()}
    flagships = {o.flagship for o in MANIFEST.values()}
    routes = {o.flagship: o.routes_to for o in MANIFEST.values()}
    closed = all(t in flagships for t in routes.values())
    return {"organs": organs, "flagships": sorted(flagships),
            "routes": routes, "closed": closed,
            "reconciler": "flywheel"}


def probe_live(doctors: dict | None = None) -> dict:
    """Annotate the manifest with live health, if doctor envelopes are supplied
    (keyed by flagship name). Graceful: with no doctors, reports the static manifest as
    'declared' — the harness never hard-depends on the MCP edge."""
    doctors = doctors or {}
    rows = []
    for name, o in MANIFEST.items():
        d = doctors.get(o.flagship)
        rows.append({"organ": name, "flagship": o.flagship, "version": o.version,
                     "role": o.role, "harness_modules": o.harness_modules,
                     "routes_to": o.routes_to,
                     "health": (d.get("status") if isinstance(d, dict) else "declared")})
    live = sum(1 for r in rows if r["health"] == "MATCH")
    return {"organs": rows, "n_organs": len(rows), "live": live,
            "all_live": (live == len(rows)) if doctors else None,
            "spine_closed": spine()["closed"]}


def compose_report(doctors: dict | None = None) -> str:
    p = probe_live(doctors)
    lines = [f"Project Telos superproject spine — {p['n_organs']} organs, "
             f"spine {'CLOSED' if p['spine_closed'] else 'OPEN'}, reconciler=flywheel"]
    for r in p["organs"]:
        h = r["health"]
        lines.append(f"  {r['organ']:15} -> {r['flagship']:8} v{r['version']:6} [{h}]  "
                     f"{r['role']}")
        lines.append(f"  {'':15}    native: {', '.join(r['harness_modules'])} -> {r['routes_to']}")
    return "\n".join(lines)
