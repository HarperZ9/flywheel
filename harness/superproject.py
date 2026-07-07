"""superproject.py — the modular integration spine: harness organs <-> flagship peers.

The local-model harness is the ENGINE. The five Project-Telos flagships are the mature,
external versions of the same organs. This module is the seam that composes them WITHOUT
either absorbing the other: the harness has native, zero-dependency organs that run
standalone, and each can delegate to its flagship PEER through the shared action-envelope
protocol when the MCP edge is present. MCP is the lone optional edge; the manifest below
is static data and always available.

Each flagship's `doctor` emits a `next_actions` route, and those routes already form a
closed spine (verified live 2026-07-06): gather<->crucible (verify claims), index<->forum
(route/context), telos reconciles the five-tool golden workflow. This manifest binds the
harness clusters onto that spine so the whole ecosystem reads as one modular design, each
point uplifted to its role.
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


def spine() -> dict:
    """The composition spine: organs + the closed routing graph. `closed` is True iff
    every route target is itself an organ (the ecosystem composes without dangling edges)."""
    organs = {name: o.flagship for name, o in MANIFEST.items()}
    flagships = {o.flagship for o in MANIFEST.values()}
    routes = {o.flagship: o.routes_to for o in MANIFEST.values()}
    closed = all(t in flagships for t in routes.values())
    return {"organs": organs, "flagships": sorted(flagships),
            "routes": routes, "closed": closed,
            "reconciler": "telos"}


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
             f"spine {'CLOSED' if p['spine_closed'] else 'OPEN'}, reconciler=telos"]
    for r in p["organs"]:
        h = r["health"]
        lines.append(f"  {r['organ']:15} -> {r['flagship']:8} v{r['version']:6} [{h}]  "
                     f"{r['role']}")
        lines.append(f"  {'':15}    native: {', '.join(r['harness_modules'])} -> {r['routes_to']}")
    return "\n".join(lines)
